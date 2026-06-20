from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pydicom

from .. import __version__
from ..adapters.factory import create_adapter
from ..deidentify import UIDMapper, baseline_deidentify_file
from ..jsonio import validate_payload, write_json


@dataclass
class StudyRun:
    study_uid: str
    status: str
    source_instances: int
    processed_instances: int
    failed_instances: int
    output_directory: str
    started_at: float
    ended_at: float
    pipeline: str = "unknown"
    configuration_sha256: str | None = None
    application_version: str | None = None
    candidate_study_uid: str | None = None
    failures: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in {"complete", "partial", "failed"}:
            raise ValueError(f"Unsupported study run status: {self.status}")
        if self.source_instances < 1 or self.processed_instances < 0 or self.failed_instances < 0:
            raise ValueError("Study run instance counts are invalid")
        if self.processed_instances + self.failed_instances != self.source_instances:
            raise ValueError("Study run processed and failed counts must equal source_instances")
        if self.ended_at < self.started_at:
            raise ValueError("Study run ended_at must not precede started_at")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _private_mode(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _validate_study_uid(value: str) -> str:
    if len(value) > 64 or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*", value) is None:
        raise ValueError(f"Invalid DICOM StudyInstanceUID: {value!r}")
    return value


def _resolved_source_file(path: Path) -> Path:
    if path.is_symlink():
        raise ValueError(f"Study source files must not be symbolic links: {path}")
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved


def _roots_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate_destination_roots(
    sources: list[Path],
    destination_root: Path,
    quarantine_root: Path | None,
) -> None:
    for source in sources:
        if _roots_overlap(destination_root, source.parent):
            raise ValueError("Study destination must not overlap a source directory")
        if quarantine_root is not None and _roots_overlap(quarantine_root, source.parent):
            raise ValueError("Study quarantine must not overlap a source directory")
    if quarantine_root is not None and _roots_overlap(destination_root, quarantine_root):
        raise ValueError("Study destination and quarantine directories must not overlap")


def index_studies(root: str | Path) -> dict[str, list[Path]]:
    base = Path(root).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(base)
    output: dict[str, list[Path]] = {}
    for path in sorted(base.rglob("*")) if base.is_dir() else [base]:
        if not path.is_file():
            continue
        resolved = _resolved_source_file(path)
        if base.is_dir() and base != resolved and base not in resolved.parents:
            raise ValueError(f"Study source file escapes its configured root: {path}")
        try:
            ds = pydicom.dcmread(resolved, stop_before_pixels=True)
        except Exception:
            continue
        uid = str(getattr(ds, "StudyInstanceUID", ""))
        if uid:
            _validate_study_uid(uid)
            output.setdefault(uid, []).append(resolved)
    return output


def _case_id(path: Path) -> str:
    return hashlib.sha256(str(path).encode()).hexdigest()[:24]


def process_study(
    paths: list[Path],
    destination_root: str | Path,
    *,
    pipeline: str = "baseline",
    adapter_config: dict[str, Any] | None = None,
    overwrite: bool = False,
    quarantine_root: str | Path | None = None,
    commit_partial: bool = False,
) -> StudyRun:
    if not paths:
        raise ValueError("Study has no instances")
    resolved_paths = [_resolved_source_file(Path(path)) for path in paths]
    if len(resolved_paths) != len(set(resolved_paths)):
        raise ValueError("Study source instance paths must be unique")
    destination_root_path = Path(destination_root).expanduser().resolve()
    quarantine_root_path = (
        Path(quarantine_root).expanduser().resolve() if quarantine_root is not None else None
    )
    _validate_destination_roots(resolved_paths, destination_root_path, quarantine_root_path)
    headers = [pydicom.dcmread(path, stop_before_pixels=True) for path in resolved_paths]
    study_uids = {str(getattr(item, "StudyInstanceUID", "")) for item in headers}
    if len(study_uids) != 1 or not next(iter(study_uids), ""):
        raise ValueError("All source instances must have the same non-empty StudyInstanceUID")
    study_uid = _validate_study_uid(next(iter(study_uids)))
    safe_study_uid = re.sub(r"[^0-9A-Za-z._-]", "_", study_uid)[:180] or "unknown-study"
    destination = (destination_root_path / safe_study_uid).resolve()
    if destination_root_path != destination and destination_root_path not in destination.parents:
        raise ValueError("Study destination escapes its configured root")
    checkpoint = destination / "run.json"
    if checkpoint.exists() and not overwrite:
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        validate_payload(payload, "study-run")
        if payload.get("status") == "complete":
            return StudyRun(**payload)
    if destination.exists() and overwrite:
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _private_mode(destination.parent, 0o700)
    staging = Path(tempfile.mkdtemp(prefix=f".{safe_study_uid}.", dir=destination.parent))
    _private_mode(staging, 0o700)
    started = time.time()
    processed = 0
    failures: list[dict[str, str]] = []
    normalized_config = adapter_config or {}
    configuration_sha256 = hashlib.sha256(
        json.dumps(normalized_config, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    mapper = UIDMapper(salt=f"DPA-STUDY-{study_uid}")
    adapter = create_adapter(pipeline, normalized_config) if pipeline not in {"baseline", "noop"} else None
    candidate_study_uid: str | None = None
    try:
        for index, source in enumerate(resolved_paths):
            target = staging / f"{index:08d}.dcm"
            try:
                if pipeline == "baseline":
                    baseline_deidentify_file(source, target, uid_mapper=mapper)
                elif pipeline == "noop":
                    shutil.copy2(source, target)
                else:
                    result = adapter.process(source, target, case_id=_case_id(source))  # type: ignore[union-attr]
                    if result.status not in {"ok", "success"}:
                        raise RuntimeError(f"adapter returned {result.status}")
                output_header = pydicom.dcmread(target, stop_before_pixels=True)
                observed_study_uid = str(getattr(output_header, "StudyInstanceUID", ""))
                if not observed_study_uid:
                    raise ValueError("Candidate output has no StudyInstanceUID")
                if candidate_study_uid is None:
                    candidate_study_uid = observed_study_uid
                elif candidate_study_uid != observed_study_uid:
                    raise ValueError("Candidate outputs do not share one StudyInstanceUID")
                processed += 1
            except Exception as exc:
                failures.append({"source": _case_id(source), "error": f"{type(exc).__name__}: {exc}"})
                if quarantine_root_path is not None:
                    quarantine = (quarantine_root_path / safe_study_uid).resolve()
                    if quarantine_root_path != quarantine and quarantine_root_path not in quarantine.parents:
                        raise ValueError("Study quarantine path escapes its configured root") from None
                    quarantine.mkdir(parents=True, exist_ok=True)
                    _private_mode(quarantine, 0o700)
                    shutil.copy2(source, quarantine / f"{index:08d}-{_case_id(source)}.dcm")
        status = "complete" if not failures else "partial" if processed else "failed"
        ended = time.time()
        publish_partial = bool(failures and commit_partial)
        if failures and not publish_partial:
            quarantine_base = (
                quarantine_root_path
                if quarantine_root_path is not None
                else destination_root_path / ".quarantine"
            )
            final_directory = quarantine_base / safe_study_uid
        else:
            final_directory = destination
        run = StudyRun(
            study_uid=study_uid,
            status=status,
            source_instances=len(resolved_paths),
            processed_instances=processed,
            failed_instances=len(failures),
            output_directory=str(final_directory),
            started_at=started,
            ended_at=ended,
            pipeline=pipeline,
            configuration_sha256=configuration_sha256,
            application_version=__version__,
            candidate_study_uid=candidate_study_uid,
            failures=failures,
        )
        write_json(staging / "run.json", run.to_dict(), schema_name="study-run")
        final_directory.parent.mkdir(parents=True, exist_ok=True)
        _private_mode(final_directory.parent, 0o700)
        if final_directory.exists():
            shutil.rmtree(final_directory)
        staging.replace(final_directory)
        return run
    finally:
        if adapter is not None:
            adapter.close()
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def process_directory(
    source_root: str | Path,
    destination_root: str | Path,
    **kwargs: Any,
) -> list[StudyRun]:
    source = Path(source_root).expanduser().resolve()
    destination = Path(destination_root).expanduser().resolve()
    if _roots_overlap(source, destination):
        raise ValueError("Study source and destination directories must not overlap")
    quarantine = kwargs.get("quarantine_root")
    if quarantine is not None and _roots_overlap(source, Path(quarantine).expanduser().resolve()):
        raise ValueError("Study source and quarantine directories must not overlap")
    studies = index_studies(source)
    return [process_study(paths, destination, **kwargs) for _, paths in sorted(studies.items())]
