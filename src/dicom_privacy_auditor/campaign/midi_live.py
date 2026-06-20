from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pydicom

from .. import __version__
from ..adapters.factory import create_adapter
from ..benchmark.manifest import _validated_relative_path
from ..benchmark.midi import evaluate_midi
from ..deidentify import UIDMapper, baseline_deidentify_file
from ..jsonio import validate_payload, write_json

DEFAULT_OFFICIAL_VALIDATOR_TIMEOUT_SECONDS = 3600.0
CAMPAIGN_TOOLS = {"noop", "baseline", "orthanc", "rsna-anonymizer", "rsna-ctp", "directory"}


@dataclass
class ToolCampaignResult:
    tool: str
    status: str
    source_instances: int
    processed_instances: int
    failed_instances: int
    runtime_seconds: float
    output_directory: str
    evaluation_directory: str | None = None
    evaluation_summary: dict[str, Any] | None = None
    probe: dict[str, Any] | None = None
    failures: list[dict[str, str]] = field(default_factory=list)
    official_validation: dict[str, Any] | None = None
    application_version: str = __version__
    configuration_sha256: str | None = None
    source_manifest_sha256: str | None = None
    selected_instances: int | None = None
    skipped_instances: int = 0
    checkpoint_file: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _validated_tool(value: str) -> str:
    if value not in CAMPAIGN_TOOLS:
        raise ValueError(f"Unsupported campaign tool: {value}")
    return value


def _private_mode(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _append_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    _private_mode(path, 0o600)


def _roots_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _contained_output(root: Path, relative: Path) -> Path:
    candidate = (root / relative).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"campaign output path escapes its root: {relative}")
    return candidate


def _workspace_child(workspace: Path, relative: Path) -> Path:
    candidate = (workspace / relative).resolve()
    if workspace != candidate and workspace not in candidate.parents:
        raise ValueError(f"campaign workspace path escapes its root: {relative}")
    return candidate


def _load_import_manifest(imported: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = imported / "midi_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_payload(payload, "midi-import")
    actions_relative = _validated_relative_path(str(payload.get("actions_file", "")))
    raw_actions_path = imported / actions_relative
    if raw_actions_path.is_symlink():
        raise ValueError("MIDI actions file must not be a symbolic link")
    actions_path = raw_actions_path.resolve()
    if imported != actions_path and imported not in actions_path.parents:
        raise ValueError("MIDI actions file escapes the imported directory")
    return manifest_path, payload


def _json_sha256(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _case_id(relative: str) -> str:
    return hashlib.sha256(relative.encode()).hexdigest()[:24]


def _dicom_files(root: Path) -> list[Path]:
    root = root.resolve()
    output: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError(f"DICOM campaign trees must not contain symbolic-link files: {path}")
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError(f"DICOM campaign file escapes its configured root: {path}")
        try:
            pydicom.dcmread(resolved, stop_before_pixels=True)
        except Exception:
            continue
        output.append(resolved)
    return output


def _stream_tail(value: str | bytes | None, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-limit:]


def _official_validate(
    command: list[str],
    *,
    imported: Path,
    candidate: Path,
    output: Path,
    timeout_seconds: float = DEFAULT_OFFICIAL_VALIDATOR_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    if not command or any(not isinstance(part, str) or not part.strip() for part in command):
        raise ValueError("official validator command must contain nonempty string tokens")
    if timeout_seconds <= 0:
        raise ValueError("official validator timeout must be greater than zero")
    argv = [
        part.format(imported=str(imported), candidate=str(candidate), output=str(output)) for part in command
    ]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": argv,
            "returncode": None,
            "timed_out": True,
            "timeout_seconds": timeout_seconds,
            "stdout_tail": _stream_tail(exc.stdout),
            "stderr_tail": _stream_tail(exc.stderr),
        }
    return {
        "argv": argv,
        "returncode": completed.returncode,
        "timed_out": False,
        "timeout_seconds": timeout_seconds,
        "stdout_tail": _stream_tail(completed.stdout),
        "stderr_tail": _stream_tail(completed.stderr),
    }


def _select_shard(paths: list[Path], root: Path, shard_index: int, shard_count: int) -> list[Path]:
    if shard_count < 1:
        raise ValueError("shard_count must be at least 1")
    if not 0 <= shard_index < shard_count:
        raise ValueError("shard_index must satisfy 0 <= shard_index < shard_count")
    if shard_count == 1:
        return paths
    return [
        path
        for path in paths
        if int(hashlib.sha256(path.relative_to(root).as_posix().encode()).hexdigest(), 16) % shard_count
        == shard_index
    ]


def preflight_campaign(
    imported_dir: str | Path,
    *,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    imported = Path(imported_dir).resolve()
    if not imported.is_dir():
        raise FileNotFoundError(imported)
    manifest_path, manifest = _load_import_manifest(imported)
    resolved_source = Path(source_root).resolve() if source_root else Path(manifest["dicom_root"]).resolve()
    actions_path = (imported / _validated_relative_path(manifest["actions_file"])).resolve()
    source_exists = resolved_source.is_dir()
    source_files = _dicom_files(resolved_source) if source_exists else []
    return {
        "status": "ready" if source_exists and actions_path.is_file() and source_files else "blocked",
        "imported_directory": str(imported),
        "manifest_sha256": _file_sha256(manifest_path),
        "source_root": str(resolved_source),
        "source_root_overridden": source_root is not None,
        "source_root_exists": source_exists,
        "actions_file_exists": actions_path.is_file(),
        "dicom_instances": len(source_files),
        "manifest_action_count": manifest.get("action_count"),
        "unresolved_source_paths": manifest.get("unresolved_source_paths"),
    }


def finalize_tool(
    imported_dir: str | Path,
    workspace: str | Path,
    *,
    tool: str,
    official_validator_command: list[str] | None = None,
    official_validator_timeout_seconds: float = DEFAULT_OFFICIAL_VALIDATOR_TIMEOUT_SECONDS,
    source_root: str | Path | None = None,
) -> ToolCampaignResult:
    imported = Path(imported_dir).resolve()
    workspace_path = Path(workspace).resolve()
    tool = _validated_tool(tool)
    manifest_path, manifest = _load_import_manifest(imported)
    resolved_source = Path(source_root).resolve() if source_root else Path(manifest["dicom_root"]).resolve()
    if not resolved_source.is_dir():
        raise FileNotFoundError(
            f"MIDI source root is unavailable: {resolved_source}. Use --source-root after migrating the corpus."
        )
    output_root = _workspace_child(workspace_path, Path("outputs") / tool)
    evaluation_root = _workspace_child(workspace_path, Path("evaluations") / tool)
    if any(
        _roots_overlap(root, protected)
        for root in (output_root, evaluation_root)
        for protected in (imported, resolved_source)
    ):
        raise ValueError("campaign output/evaluation directories must not overlap imported or source data")
    source_instances = len(_dicom_files(resolved_source))
    processed_instances = len(_dicom_files(output_root))
    if processed_instances < source_instances:
        raise RuntimeError(
            f"Tool output is incomplete: found {processed_instances} of {source_instances} DICOM instances"
        )
    started = time.perf_counter()
    evaluation = evaluate_midi(imported, output_root, evaluation_root, source_root=resolved_source)
    official = None
    if official_validator_command:
        official = _official_validate(
            official_validator_command,
            imported=imported,
            candidate=output_root,
            output=evaluation_root,
            timeout_seconds=official_validator_timeout_seconds,
        )
    result = ToolCampaignResult(
        tool=tool,
        status="complete",
        source_instances=source_instances,
        processed_instances=processed_instances,
        failed_instances=0,
        runtime_seconds=time.perf_counter() - started,
        output_directory=str(output_root),
        evaluation_directory=str(evaluation_root),
        evaluation_summary=evaluation.summary,
        probe={"status": "finalize-only"},
        official_validation=official,
        source_manifest_sha256=_file_sha256(manifest_path),
        selected_instances=source_instances,
    )
    run_dir = _workspace_child(workspace_path, Path("runs"))
    run_dir.mkdir(parents=True, exist_ok=True)
    _private_mode(run_dir, 0o700)
    write_json(run_dir / f"{tool}.json", result.to_dict(), schema_name="campaign-tool-result")
    return result


def run_tool(
    imported_dir: str | Path,
    workspace: str | Path,
    *,
    tool: str,
    adapter_config: dict[str, Any] | None = None,
    overwrite: bool = False,
    official_validator_command: list[str] | None = None,
    official_validator_timeout_seconds: float = DEFAULT_OFFICIAL_VALIDATOR_TIMEOUT_SECONDS,
    source_root: str | Path | None = None,
    shard_index: int = 0,
    shard_count: int = 1,
    evaluate: bool = True,
) -> ToolCampaignResult:
    imported = Path(imported_dir).resolve()
    tool = _validated_tool(tool)
    manifest_path, manifest = _load_import_manifest(imported)
    source_root = Path(source_root).resolve() if source_root else Path(manifest["dicom_root"]).resolve()
    if not source_root.is_dir():
        raise FileNotFoundError(
            f"MIDI source root is unavailable: {source_root}. Use --source-root after migrating the corpus."
        )
    all_source_files = _dicom_files(source_root)
    source_files = _select_shard(all_source_files, source_root, shard_index, shard_count)
    workspace_path = Path(workspace).resolve()
    output_root = _workspace_child(workspace_path, Path("outputs") / tool)
    evaluation_root = _workspace_child(workspace_path, Path("evaluations") / tool)
    if any(
        _roots_overlap(root, protected)
        for root in (output_root, evaluation_root)
        for protected in (imported, source_root)
    ):
        raise ValueError("campaign output/evaluation directories must not overlap imported or source data")
    if output_root.exists() and overwrite and shard_count == 1:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    _private_mode(output_root, 0o700)
    started = time.perf_counter()
    failures: list[dict[str, str]] = []
    processed = 0
    skipped = 0
    checkpoint_dir = _workspace_child(workspace_path, Path("checkpoints"))
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    _private_mode(checkpoint_dir, 0o700)
    checkpoint_path = checkpoint_dir / f"{tool}-shard-{shard_index}-of-{shard_count}.jsonl"
    normalized_config = adapter_config or {}
    configuration_sha256 = _json_sha256(normalized_config)
    source_manifest_sha256 = _file_sha256(manifest_path)
    mapper = UIDMapper(salt=f"DPA-MIDI-{tool}")
    adapter = create_adapter(tool, normalized_config) if tool not in {"baseline", "noop"} else None
    try:
        probe = adapter.probe() if adapter is not None else {"status": "builtin", "tool": tool}
        if probe.get("reachable") is False:
            raise ConnectionError(f"{tool} adapter probe reported unreachable")
    except Exception as exc:
        if adapter is not None:
            adapter.close()
        result = ToolCampaignResult(
            tool=tool,
            status="failed",
            source_instances=len(source_files),
            processed_instances=0,
            failed_instances=len(source_files),
            runtime_seconds=time.perf_counter() - started,
            output_directory=str(output_root),
            probe={"status": "probe_failed", "error": f"{type(exc).__name__}: {exc}"},
            failures=[{"case_id": "adapter-probe", "error": f"{type(exc).__name__}: {exc}"}],
            configuration_sha256=configuration_sha256,
            source_manifest_sha256=source_manifest_sha256,
        )
        run_dir = _workspace_child(workspace_path, Path("runs"))
        run_dir.mkdir(parents=True, exist_ok=True)
        _private_mode(run_dir, 0o700)
        write_json(run_dir / f"{tool}.json", result.to_dict(), schema_name="campaign-tool-result")
        return result
    try:
        for source in source_files:
            relative = source.relative_to(source_root)
            destination = _contained_output(output_root, relative)
            if destination.exists() and not overwrite:
                try:
                    pydicom.dcmread(destination, stop_before_pixels=True)
                    processed += 1
                    skipped += 1
                    continue
                except Exception:
                    destination.unlink(missing_ok=True)
            destination.parent.mkdir(parents=True, exist_ok=True)
            try:
                if tool == "baseline":
                    baseline_deidentify_file(source, destination, uid_mapper=mapper)
                elif tool == "noop":
                    shutil.copy2(source, destination)
                else:
                    if adapter is None:
                        raise RuntimeError(f"Adapter was not created for tool: {tool}")
                    adapter_result = adapter.process(
                        source, destination, case_id=_case_id(relative.as_posix())
                    )
                    if adapter_result.status not in {"ok", "success"}:
                        raise RuntimeError(f"Adapter status: {adapter_result.status}")
                pydicom.dcmread(destination, stop_before_pixels=True)
                processed += 1
                _append_private_json(
                    checkpoint_path,
                    {"case_id": _case_id(relative.as_posix()), "status": "complete"},
                )
            except Exception as exc:
                failure = {"case_id": _case_id(relative.as_posix()), "error": f"{type(exc).__name__}: {exc}"}
                failures.append(failure)
                _append_private_json(checkpoint_path, {**failure, "status": "failed"})
    finally:
        if adapter is not None:
            adapter.close()
    evaluation = None
    full_corpus_ready = len(_dicom_files(output_root)) >= len(all_source_files)
    if evaluate and full_corpus_ready:
        evaluation = evaluate_midi(imported, output_root, evaluation_root, source_root=source_root)
    official = None
    if official_validator_command and evaluation is not None:
        official = _official_validate(
            official_validator_command,
            imported=imported,
            candidate=output_root,
            output=evaluation_root,
            timeout_seconds=official_validator_timeout_seconds,
        )
    runtime = time.perf_counter() - started
    result = ToolCampaignResult(
        tool=tool,
        status=("complete" if not failures and full_corpus_ready else "partial" if processed else "failed"),
        source_instances=len(all_source_files),
        processed_instances=processed,
        failed_instances=len(failures),
        runtime_seconds=runtime,
        output_directory=str(output_root),
        evaluation_directory=str(evaluation_root) if evaluation is not None else None,
        evaluation_summary=evaluation.summary if evaluation is not None else None,
        probe=probe,
        failures=failures,
        official_validation=official,
        configuration_sha256=configuration_sha256,
        source_manifest_sha256=source_manifest_sha256,
        selected_instances=len(source_files),
        skipped_instances=skipped,
        checkpoint_file=str(checkpoint_path),
    )
    run_dir = _workspace_child(workspace_path, Path("runs"))
    run_dir.mkdir(parents=True, exist_ok=True)
    _private_mode(run_dir, 0o700)
    write_json(run_dir / f"{tool}.json", result.to_dict(), schema_name="campaign-tool-result")
    return result


def run_campaign(
    imported_dir: str | Path,
    workspace: str | Path,
    tools: list[dict[str, Any]],
    *,
    overwrite: bool = False,
    source_root: str | Path | None = None,
) -> dict[str, Any]:
    validate_payload({"tools": tools}, "midi-campaign")
    results: list[ToolCampaignResult] = []
    for item in tools:
        results.append(
            run_tool(
                imported_dir,
                workspace,
                tool=item["name"],
                adapter_config=item.get("config", {}),
                overwrite=overwrite,
                official_validator_command=item.get("official_validator_command"),
                official_validator_timeout_seconds=item.get(
                    "official_validator_timeout_seconds", DEFAULT_OFFICIAL_VALIDATOR_TIMEOUT_SECONDS
                ),
                source_root=source_root,
            )
        )
    payload = {
        "schema_version": "1.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "application_version": __version__,
        "campaign_definition_sha256": _json_sha256(tools),
        "imported": str(Path(imported_dir).resolve()),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "machine": platform.machine(),
        },
        "results": [item.to_dict() for item in results],
    }
    destination = Path(workspace) / "campaign.json"
    write_json(destination, payload, schema_name="campaign-result")
    return payload
