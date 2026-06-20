from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..deidentify import UIDMapper, baseline_deidentify_file
from ..jsonio import validate_payload, write_json
from ..validation import validate_file
from .manifest import BenchmarkManifest, _validated_case_id, _validated_relative_path


@dataclass
class RunCase:
    case_id: str
    input_relative_path: str
    output_relative_path: str | None
    status: str
    runtime_seconds: float
    error: str | None = None
    output_sha256: str | None = None
    validation: dict[str, Any] | None = None
    pipeline_stats: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.case_id = _validated_case_id(self.case_id)
        self.input_relative_path = _validated_relative_path(self.input_relative_path)
        if self.output_relative_path is not None:
            self.output_relative_path = _validated_relative_path(self.output_relative_path)
        if not self.status.strip():
            raise ValueError("run case status must not be empty")
        if self.runtime_seconds < 0:
            raise ValueError("run case runtime_seconds must be non-negative")
        if self.output_sha256 is not None and (
            len(self.output_sha256) != 64
            or any(character not in "0123456789abcdefABCDEF" for character in self.output_sha256)
        ):
            raise ValueError("run case output_sha256 must be a 64-character hexadecimal digest")


@dataclass
class RunManifest:
    pipeline_name: str
    pipeline_kind: str
    benchmark_manifest: str
    cases: list[RunCase]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.pipeline_name.strip():
            raise ValueError("pipeline_name must not be empty")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("run manifest contains duplicate case_id values")

    def write(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json(target, asdict(self), schema_name="run-manifest")

    @classmethod
    def read(cls, path: str | Path) -> RunManifest:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        validate_payload(payload, "run-manifest")
        cases = [RunCase(**item) for item in payload["cases"]]
        return cls(cases=cases, **{key: value for key, value in payload.items() if key != "cases"})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_roots(benchmark_dir: str | Path, output_dir: str | Path) -> tuple[Path, Path]:
    benchmark_root = Path(benchmark_dir).resolve()
    output_root = Path(output_dir).resolve()
    if (
        benchmark_root == output_root
        or benchmark_root in output_root.parents
        or output_root in benchmark_root.parents
    ):
        raise ValueError("benchmark and output directories must not overlap")
    return benchmark_root, output_root


def contained_path(root: Path, relative: str, *, label: str) -> Path:
    candidate = (root / relative).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"{label} escapes its configured root: {relative}")
    return candidate


def run_builtin_pipeline(
    benchmark_dir: str | Path,
    output_dir: str | Path,
    *,
    pipeline: str = "baseline",
    overwrite: bool = False,
) -> RunManifest:
    benchmark_root, output_root = _prepare_roots(benchmark_dir, output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is not empty: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = benchmark_root / "manifest.json"
    manifest = BenchmarkManifest.read(manifest_path)
    uid_mapper = UIDMapper(salt=f"DPA-BENCHMARK-{manifest.seed}")
    run_cases: list[RunCase] = []

    for case in manifest.cases:
        source = contained_path(benchmark_root, case.relative_path, label="benchmark input")
        output_relative = (
            case.relative_path
            if pipeline in {"noop", "metadata-only"}
            else (Path("objects") / f"{case.case_id}.dcm").as_posix()
        )
        destination = contained_path(output_root, output_relative, label="benchmark output")
        start = time.perf_counter()
        error = None
        stats: dict[str, Any] = {}
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if pipeline == "noop":
                shutil.copy2(source, destination)
            elif pipeline in {"metadata-only", "baseline"}:
                bboxes = (
                    [injection.bbox_xyxy for injection in case.injections if injection.bbox_xyxy is not None]
                    if pipeline == "baseline"
                    else []
                )
                result = baseline_deidentify_file(
                    source,
                    destination,
                    uid_mapper=uid_mapper,
                    pixel_bboxes=bboxes,
                )
                stats = result.to_dict()
            else:
                raise ValueError(f"Unknown built-in pipeline: {pipeline}")
            status = "ok"
        except Exception as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
        runtime = time.perf_counter() - start
        validation = validate_file(destination).to_dict() if destination.exists() else None
        run_cases.append(
            RunCase(
                case_id=case.case_id,
                input_relative_path=case.relative_path,
                output_relative_path=output_relative if destination.exists() else None,
                status=status,
                runtime_seconds=runtime,
                error=error,
                output_sha256=_sha256(destination) if destination.exists() else None,
                validation=validation,
                pipeline_stats=stats,
            )
        )

    run_manifest = RunManifest(
        pipeline_name=pipeline,
        pipeline_kind="builtin",
        benchmark_manifest=str(manifest_path.resolve()),
        cases=run_cases,
        metadata={"benchmark_seed": manifest.seed, "contains_real_phi": False},
    )
    run_manifest.write(output_root / "run_manifest.json")
    return run_manifest


def run_external_pipeline(
    benchmark_dir: str | Path,
    output_dir: str | Path,
    *,
    name: str,
    command: list[str] | str,
    timeout_seconds: int = 120,
    output_name_mode: str = "preserve",
    overwrite: bool = False,
) -> RunManifest:
    """Run an external one-file-at-a-time command without invoking a shell.

    Command tokens may contain ``{input}``, ``{output}``, ``{output_dir}``,
    ``{case_id}``, and ``{input_name}``. A string command is parsed with
    ``shlex.split``. Output naming is explicitly recorded because filename handling
    is part of workflow-level privacy performance.
    """
    benchmark_root, output_root = _prepare_roots(benchmark_dir, output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is not empty: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = benchmark_root / "manifest.json"
    manifest = BenchmarkManifest.read(manifest_path)
    template = shlex.split(command) if isinstance(command, str) else list(command)
    if not template or any(not str(token).strip() for token in template):
        raise ValueError("external command must contain at least one nonempty token")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if output_name_mode not in {"preserve", "safe"}:
        raise ValueError("output_name_mode must be 'preserve' or 'safe'")
    run_cases: list[RunCase] = []

    for case in manifest.cases:
        source = contained_path(benchmark_root, case.relative_path, label="benchmark input")
        output_relative = (
            case.relative_path
            if output_name_mode == "preserve"
            else str(Path("objects") / f"{case.case_id}.dcm")
        )
        destination = contained_path(output_root, output_relative, label="benchmark output")
        destination.parent.mkdir(parents=True, exist_ok=True)
        argv = [
            token.format(
                input=str(source),
                output=str(destination),
                output_dir=str(destination.parent),
                case_id=case.case_id,
                input_name=source.name,
            )
            for token in template
        ]
        start = time.perf_counter()
        error = None
        stats: dict[str, Any] = {"argv": argv}
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout_seconds, check=False
            )
            stats.update(
                {
                    "returncode": completed.returncode,
                    "stdout_tail": completed.stdout[-2000:],
                    "stderr_tail": completed.stderr[-2000:],
                }
            )
            if completed.returncode != 0:
                raise RuntimeError(f"External command returned {completed.returncode}")
            if not destination.exists():
                raise FileNotFoundError("External command did not create the expected output file")
            status = "ok"
        except Exception as exc:
            status = "error"
            error = f"{type(exc).__name__}: {exc}"
        runtime = time.perf_counter() - start
        validation = validate_file(destination).to_dict() if destination.exists() else None
        run_cases.append(
            RunCase(
                case_id=case.case_id,
                input_relative_path=case.relative_path,
                output_relative_path=output_relative if destination.exists() else None,
                status=status,
                runtime_seconds=runtime,
                error=error,
                output_sha256=_sha256(destination) if destination.exists() else None,
                validation=validation,
                pipeline_stats=stats,
            )
        )

    run_manifest = RunManifest(
        pipeline_name=name,
        pipeline_kind="external",
        benchmark_manifest=str(manifest_path.resolve()),
        cases=run_cases,
        metadata={
            "command_template": template,
            "timeout_seconds": timeout_seconds,
            "output_name_mode": output_name_mode,
        },
    )
    run_manifest.write(output_root / "run_manifest.json")
    return run_manifest


def run_adapter_pipeline(
    benchmark_dir: str | Path,
    output_dir: str | Path,
    *,
    adapter_name: str,
    config: dict[str, Any],
    overwrite: bool = False,
) -> RunManifest:
    """Run a synthetic benchmark through a first-class external-tool adapter."""
    from ..adapters.factory import create_adapter

    benchmark_root, output_root = _prepare_roots(benchmark_dir, output_dir)
    if output_root.exists() and any(output_root.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is not empty: {output_root}")
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    manifest_path = benchmark_root / "manifest.json"
    manifest = BenchmarkManifest.read(manifest_path)
    adapter = create_adapter(adapter_name, config)
    run_cases: list[RunCase] = []
    try:
        probe = adapter.probe()
        for case in manifest.cases:
            source = contained_path(benchmark_root, case.relative_path, label="benchmark input")
            output_relative = (Path("objects") / f"{case.case_id}.dcm").as_posix()
            destination = contained_path(output_root, output_relative, label="benchmark output")
            destination.parent.mkdir(parents=True, exist_ok=True)
            start = time.perf_counter()
            error = None
            stats: dict[str, Any] = {}
            try:
                result = adapter.process(source, destination, case_id=case.case_id)
                stats = result.details
                status = result.status
                runtime = result.runtime_seconds
                if not destination.exists():
                    raise FileNotFoundError("Adapter did not create the expected output file")
            except Exception as exc:
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
                runtime = time.perf_counter() - start
            validation = validate_file(destination).to_dict() if destination.exists() else None
            run_cases.append(
                RunCase(
                    case_id=case.case_id,
                    input_relative_path=case.relative_path,
                    output_relative_path=output_relative if destination.exists() else None,
                    status=status,
                    runtime_seconds=runtime,
                    error=error,
                    output_sha256=_sha256(destination) if destination.exists() else None,
                    validation=validation,
                    pipeline_stats=stats,
                )
            )
    finally:
        adapter.close()

    run_manifest = RunManifest(
        pipeline_name=adapter_name,
        pipeline_kind="adapter",
        benchmark_manifest=str(manifest_path.resolve()),
        cases=run_cases,
        metadata={
            "adapter": adapter_name,
            "probe": probe,
            "configuration_keys": sorted(config),
        },
    )
    run_manifest.write(output_root / "run_manifest.json")
    return run_manifest
