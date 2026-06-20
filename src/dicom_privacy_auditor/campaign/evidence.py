from __future__ import annotations

import hashlib
import json
import os
import random
import shutil
import tarfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from ..permissions import atomic_write_text, restrict_directory, restrict_file

_SENSITIVE_KEYS = {
    "argv",
    "candidate_ref",
    "checkpoint_file",
    "dicom_root",
    "evaluation_directory",
    "output_directory",
    "relative_path",
    "source_directory",
    "source_ref",
    "source_root",
    "stderr_tail",
    "stdout_tail",
}
MAX_EVIDENCE_ARCHIVE_MEMBERS = 10_000
MAX_EVIDENCE_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _looks_like_absolute_path(value: str) -> bool:
    if value.startswith(("/", "\\")):
        return True
    return len(value) >= 3 and value[1:3] in {":\\", ":/"} and value[0].isalpha()


def _redact(value: Any, key: str | None = None) -> Any:
    if key in _SENSITIVE_KEYS:
        return "redacted"
    if isinstance(value, str) and _looks_like_absolute_path(value):
        return "redacted"
    if isinstance(value, dict):
        return {item_key: _redact(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def generate_review_sample(
    evaluation_file: str | Path,
    output_file: str | Path,
    *,
    failures_per_stratum: int = 25,
    controls_per_stratum: int = 10,
    seed: int = 20260620,
) -> dict[str, Any]:
    """Create a deterministic, action-stratified blinded review sample manifest."""
    if failures_per_stratum < 0 or controls_per_stratum < 0:
        raise ValueError("sample sizes must be non-negative")
    source = Path(evaluation_file)
    payload = json.loads(source.read_text(encoding="utf-8"))
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in payload.get("results", []):
        status = str(item.get("status", "unknown"))
        outcome = "failure" if status not in {"pass", "passed", "success"} else "control"
        grouped[(str(item.get("action", "unknown")), outcome)].append(item)

    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    strata: list[dict[str, Any]] = []
    for (action, outcome), rows in sorted(grouped.items()):
        limit = failures_per_stratum if outcome == "failure" else controls_per_stratum
        ordered = sorted(rows, key=lambda item: str(item.get("action_id", "")))
        chosen = rng.sample(ordered, min(limit, len(ordered))) if limit else []
        for item in chosen:
            selected.append(
                {
                    "review_id": hashlib.sha256(f"{seed}:{item.get('action_id')}".encode()).hexdigest()[:24],
                    "action_id": item.get("action_id"),
                    "action": action,
                    "sampling_stratum": outcome,
                    "source_ref": item.get("source_ref"),
                    "candidate_ref": item.get("candidate_ref"),
                }
            )
        strata.append({"action": action, "outcome": outcome, "available": len(rows), "selected": len(chosen)})

    result = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_evaluation_sha256": _sha256(source),
        "seed": seed,
        "failures_per_stratum": failures_per_stratum,
        "controls_per_stratum": controls_per_stratum,
        "selected_count": len(selected),
        "strata": strata,
        "cases": sorted(selected, key=lambda item: item["review_id"]),
    }
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(result, indent=2, sort_keys=True) + "\n")
    restrict_file(destination)
    return result


def compare_evaluators(
    internal_file: str | Path,
    official_file: str | Path,
    output_file: str | Path,
) -> dict[str, Any]:
    """Compare normalized action-level results from internal and official evaluators."""
    internal_path, official_path = Path(internal_file), Path(official_file)
    internal = json.loads(internal_path.read_text(encoding="utf-8"))
    official = json.loads(official_path.read_text(encoding="utf-8"))

    def index(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
        rows = payload.get("results")
        if not isinstance(rows, list):
            raise ValueError("evaluation JSON must contain a results array")
        indexed = {}
        for row in rows:
            action_id = str(row.get("action_id", "")).strip()
            if not action_id:
                raise ValueError("every evaluation result requires action_id")
            if action_id in indexed:
                raise ValueError(f"duplicate action_id: {action_id}")
            indexed[action_id] = row
        return indexed

    left, right = index(internal), index(official)
    all_ids = sorted(set(left) | set(right))
    confusion: Counter[str] = Counter()
    discrepancies: list[dict[str, Any]] = []
    for action_id in all_ids:
        lrow, rrow = left.get(action_id), right.get(action_id)
        lstatus = str(lrow.get("status")) if lrow else "missing"
        rstatus = str(rrow.get("status")) if rrow else "missing"
        confusion[f"{lstatus}|{rstatus}"] += 1
        if lstatus != rstatus:
            discrepancies.append(
                {
                    "action_id": action_id,
                    "action": (lrow or rrow or {}).get("action"),
                    "internal_status": lstatus,
                    "official_status": rstatus,
                }
            )
    matched = len(all_ids) - len(discrepancies)
    result = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "internal_sha256": _sha256(internal_path),
        "official_sha256": _sha256(official_path),
        "union_action_count": len(all_ids),
        "exact_status_matches": matched,
        "exact_status_agreement": matched / len(all_ids) if all_ids else None,
        "confusion": dict(sorted(confusion.items())),
        "discrepancy_count": len(discrepancies),
        "discrepancies": discrepancies,
    }
    destination = Path(output_file)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(result, indent=2, sort_keys=True) + "\n")
    restrict_file(destination)
    return result


def build_evidence_package(
    workspace: str | Path,
    destination: str | Path,
    *,
    campaign_id: str,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Assemble a redacted, checksummed campaign evidence directory."""
    source_input, target_input = Path(workspace), Path(destination)
    if source_input.is_symlink() or target_input.is_symlink():
        raise ValueError("evidence workspace and destination must not be symbolic links")
    source, target = source_input.resolve(), target_input.resolve()
    if not source.is_dir():
        raise FileNotFoundError(source)
    if source == target or source in target.parents or target in source.parents:
        raise ValueError("evidence workspace and destination must not overlap")
    if target.exists():
        if not overwrite:
            raise FileExistsError(target)
        if not target.is_dir():
            raise ValueError("existing evidence destination must be a directory")
        shutil.rmtree(target)
    target.mkdir(parents=True)
    restrict_directory(target)
    copied: list[str] = []
    for folder in ("runs", "evaluations", "reports"):
        root = source / folder
        if not root.exists():
            continue
        if root.is_symlink():
            raise ValueError(f"evidence source folder must not be a symbolic link: {root}")
        for path in sorted(root.rglob("*.json")):
            if path.is_symlink():
                raise ValueError(f"evidence source JSON must not be a symbolic link: {path}")
            resolved = path.resolve()
            if source not in resolved.parents:
                raise ValueError(f"evidence source JSON escapes workspace: {path}")
            relative = path.relative_to(source)
            output = target / relative
            output.parent.mkdir(parents=True, exist_ok=True)
            restrict_directory(output.parent)
            payload = json.loads(path.read_text(encoding="utf-8"))
            atomic_write_text(output, json.dumps(_redact(payload), indent=2, sort_keys=True) + "\n")
            restrict_file(output)
            copied.append(relative.as_posix())
    status = {
        "campaign_id": campaign_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_workspace": "redacted",
        "copied_json_files": copied,
        "claim_boundary": "Evidence assembly does not establish external validation or regulatory compliance.",
    }
    status_path = target / "STATUS.json"
    atomic_write_text(status_path, json.dumps(status, indent=2, sort_keys=True) + "\n")
    restrict_file(status_path)
    sums = []
    for path in sorted(target.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS.txt":
            sums.append(f"{_sha256(path)}  {path.relative_to(target).as_posix()}")
    checksum_path = target / "SHA256SUMS.txt"
    atomic_write_text(checksum_path, "\n".join(sums) + "\n")
    restrict_file(checksum_path)
    return {**status, "destination": str(target), "file_count": len(sums)}


def _validate_evidence_limits(max_members: int, max_uncompressed_bytes: int) -> None:
    if max_members < 1:
        raise ValueError("max_members must be at least 1")
    if max_uncompressed_bytes < 1:
        raise ValueError("max_uncompressed_bytes must be at least 1")


def _safe_posix_member_name(name: str) -> bool:
    if not name or "\\" in name or name.startswith("/"):
        return False
    # Reject syntax that PurePosixPath would normalize away before validation.
    raw_parts = name.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        return False
    if len(raw_parts[0]) == 2 and raw_parts[0][0].isalpha() and raw_parts[0][1] == ":":
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _extract_evidence_archive(
    package_path: Path,
    destination: Path,
    *,
    max_members: int,
    max_uncompressed_bytes: int,
) -> None:
    members: list[tarfile.TarInfo] = []
    names: set[str] = set()
    uncompressed_bytes = 0
    with tarfile.open(package_path, "r:gz") as archive:
        for member in archive:
            if len(members) >= max_members:
                raise ValueError(f"evidence archive exceeds the {max_members}-member limit")
            if not _safe_posix_member_name(member.name):
                raise ValueError(f"unsafe archive member: {member.name}")
            if member.name in names:
                raise ValueError(f"duplicate archive member: {member.name}")
            if not (member.isfile() or member.isdir()):
                raise ValueError(f"unsupported archive member type: {member.name}")
            if member.size < 0:
                raise ValueError(f"invalid archive member size: {member.name}")
            uncompressed_bytes += member.size if member.isfile() else 0
            if uncompressed_bytes > max_uncompressed_bytes:
                raise ValueError(
                    f"evidence archive exceeds the {max_uncompressed_bytes}-byte uncompressed limit"
                )
            candidate = (destination / member.name).resolve()
            if destination not in candidate.parents and candidate != destination:
                raise ValueError(f"unsafe archive member: {member.name}")
            names.add(member.name)
            members.append(member)
        archive.extractall(destination, members=members, filter="data")


def _validate_evidence_directory_limits(
    root: Path,
    *,
    max_members: int,
    max_uncompressed_bytes: int,
) -> list[str]:
    unsafe_entries: list[str] = []
    member_count = 0
    uncompressed_bytes = 0
    for path in root.rglob("*"):
        member_count += 1
        if member_count > max_members:
            raise ValueError(f"evidence package exceeds the {max_members}-member limit")
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            unsafe_entries.append(relative)
            continue
        if path.is_file():
            uncompressed_bytes += path.stat().st_size
            if uncompressed_bytes > max_uncompressed_bytes:
                raise ValueError(
                    f"evidence package exceeds the {max_uncompressed_bytes}-byte uncompressed limit"
                )
        elif not path.is_dir():
            unsafe_entries.append(relative)
    return sorted(unsafe_entries)


def verify_evidence_package(
    package: str | Path,
    *,
    max_members: int = MAX_EVIDENCE_ARCHIVE_MEMBERS,
    max_uncompressed_bytes: int = MAX_EVIDENCE_UNCOMPRESSED_BYTES,
) -> dict[str, Any]:
    """Verify a bounded evidence directory or tar.gz archive against its SHA-256 manifest."""
    _validate_evidence_limits(max_members, max_uncompressed_bytes)
    package_input = Path(package)
    if package_input.is_symlink():
        raise ValueError("evidence package must not be a symbolic link")
    package_path = package_input.resolve()
    temporary: Path | None = None
    root = package_path
    if package_path.is_file():
        import tempfile

        temporary = Path(tempfile.mkdtemp(prefix="dpa-evidence-verify-"))
        try:
            _extract_evidence_archive(
                package_path,
                temporary,
                max_members=max_members,
                max_uncompressed_bytes=max_uncompressed_bytes,
            )
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        roots = [item for item in temporary.iterdir() if item.is_dir()]
        root = roots[0] if len(roots) == 1 else temporary
    elif not package_path.is_dir():
        raise FileNotFoundError(package_path)
    try:
        unsafe_entries = _validate_evidence_directory_limits(
            root,
            max_members=max_members,
            max_uncompressed_bytes=max_uncompressed_bytes,
        )
        manifest = root / "SHA256SUMS.txt"
        if manifest.is_symlink():
            raise ValueError("checksum manifest must not be a symbolic link")
        if not manifest.is_file():
            raise FileNotFoundError(f"missing checksum manifest: {manifest}")
        expected: dict[str, str] = {}
        malformed: list[str] = []
        duplicate_manifest_paths: list[str] = []
        for line in manifest.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parts = line.split("  ", 1)
            checksum = parts[0].lower() if parts else ""
            name = parts[1] if len(parts) == 2 else ""
            if (
                len(parts) != 2
                or len(checksum) != 64
                or any(character not in "0123456789abcdef" for character in checksum)
                or not _safe_posix_member_name(name)
            ):
                malformed.append(line)
                continue
            if name in expected:
                duplicate_manifest_paths.append(name)
                continue
            expected[name] = checksum
        actual_files = {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_file() and not path.is_symlink() and path.name != "SHA256SUMS.txt"
        }
        missing = sorted(set(expected) - set(actual_files))
        unexpected = sorted(set(actual_files) - set(expected))
        mismatched = sorted(
            name
            for name in set(expected) & set(actual_files)
            if _sha256(actual_files[name]) != expected[name]
        )
        duplicate_manifest_paths = sorted(set(duplicate_manifest_paths))
        valid = not (
            malformed or duplicate_manifest_paths or unsafe_entries or missing or unexpected or mismatched
        )
        return {
            "schema_version": "1.1",
            "package": str(package_path),
            "valid": valid,
            "manifest_entries": len(expected),
            "limits": {
                "max_members": max_members,
                "max_uncompressed_bytes": max_uncompressed_bytes,
            },
            "malformed_manifest_lines": malformed,
            "duplicate_manifest_paths": duplicate_manifest_paths,
            "unsafe_entries": unsafe_entries,
            "missing_files": missing,
            "unexpected_files": unexpected,
            "checksum_mismatches": mismatched,
        }
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)


def archive_evidence_package(
    evidence_directory: str | Path,
    archive_path: str | Path,
    *,
    source_date_epoch: int = 0,
    overwrite: bool = False,
    max_members: int = MAX_EVIDENCE_ARCHIVE_MEMBERS,
    max_uncompressed_bytes: int = MAX_EVIDENCE_UNCOMPRESSED_BYTES,
) -> dict[str, Any]:
    """Create a deterministic gzip-compressed tar archive from a verified evidence directory."""
    source_input, output_input = Path(evidence_directory), Path(archive_path)
    if source_input.is_symlink() or output_input.is_symlink():
        raise ValueError("evidence directory and archive path must not be symbolic links")
    source = source_input.resolve()
    output = output_input.resolve()
    if source == output or source in output.parents:
        raise ValueError("evidence archive must be outside the evidence directory")
    verification = verify_evidence_package(
        source,
        max_members=max_members,
        max_uncompressed_bytes=max_uncompressed_bytes,
    )
    if not verification["valid"]:
        raise ValueError("evidence package failed checksum verification")
    if output.exists() and not overwrite:
        raise FileExistsError(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.unlink(missing_ok=True)
    import gzip

    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=source_date_epoch) as gz:
                with tarfile.open(fileobj=gz, mode="w") as tar:
                    for path in sorted(source.rglob("*")):
                        if path.is_symlink():
                            raise ValueError(f"evidence package contains a symbolic link: {path}")
                        relative = Path(source.name) / path.relative_to(source)
                        info = tar.gettarinfo(str(path), arcname=relative.as_posix())
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        info.mtime = source_date_epoch
                        info.mode = 0o600 if path.is_file() else 0o700
                        if path.is_file():
                            with path.open("rb") as handle:
                                tar.addfile(info, handle)
                        elif path.is_dir():
                            tar.addfile(info)
                        else:
                            raise ValueError(f"unsupported evidence entry: {path}")
        os.replace(temporary, output)
        restrict_file(output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return {
        "archive": str(output),
        "sha256": _sha256(output),
        "source_date_epoch": source_date_epoch,
        "verified_file_count": verification["manifest_entries"],
    }
