from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import zipfile
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

from ..jsonio import write_json
from .models import IodAttribute, IodContext

IOD_DATA_DIR_ENV = "DICOM_PRIVACY_IOD_DATA_DIR"
IOD_EDITION_ENV = "DICOM_PRIVACY_IOD_EDITION"
DEFAULT_EDITION = "user-generated"
IOD_SOURCE_FILENAMES = (
    "ciods.json",
    "sops.json",
    "ciod_to_modules.json",
    "module_to_attributes.json",
)
MAX_IOD_ARCHIVE_MEMBERS = 10_000
MAX_IOD_ARCHIVE_UNCOMPRESSED_BYTES = 1024 * 1024 * 1024
MAX_IOD_JSON_BYTES = 256 * 1024 * 1024


class IodDataNotInstalledError(RuntimeError):
    pass


def default_data_dir() -> Path:
    override = os.environ.get(IOD_DATA_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "DICOMPrivacyAuditor" / "iod"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "DICOMPrivacyAuditor" / "iod"
    root = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return root / "dicom-privacy-auditor" / "iod"


def _validated_edition(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", value) is None:
        raise ValueError(
            "IOD edition must be 1-64 characters using only letters, numbers, period, underscore, or hyphen"
        )
    return value


def registry_path(*, data_dir: str | Path | None = None, edition: str | None = None) -> Path:
    root = Path(data_dir).expanduser().resolve() if data_dir else default_data_dir()
    selected = _validated_edition(edition or os.environ.get(IOD_EDITION_ENV, DEFAULT_EDITION))
    return root / f"iod_registry_{selected}.json"


def data_status(*, data_dir: str | Path | None = None, edition: str | None = None) -> dict[str, Any]:
    path = registry_path(data_dir=data_dir, edition=edition)
    return {
        "installed": path.is_file(),
        "edition": edition or os.environ.get(IOD_EDITION_ENV, DEFAULT_EDITION),
        "registry": str(path),
        "data_dir": str(path.parent),
        "bundled_with_project": False,
        "setup": "Run dicom-privacy-iod prepare-data --source <directory-or-wheel> --edition <label>.",
    }


def _safe_zip_member_name(name: str) -> bool:
    if not name or "\\" in name or "\x00" in name:
        return False
    path = PurePosixPath(name)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def _read_bounded(handle: Any, *, limit: int, label: str) -> bytes:
    payload = handle.read(limit + 1)
    if len(payload) > limit:
        raise ValueError(f"{label} exceeds the {limit}-byte limit")
    return payload


def _directory_json_bytes(source: Path, filename: str) -> bytes:
    candidates = sorted(path for path in source.rglob(filename) if path.is_file() or path.is_symlink())
    if not candidates:
        raise FileNotFoundError(f"{filename} was not found under {source}")
    if len(candidates) != 1:
        raise ValueError(f"Ambiguous IOD source: found {len(candidates)} copies of {filename}")
    candidate = candidates[0]
    if candidate.is_symlink():
        raise ValueError(f"IOD source JSON must not be a symbolic link: {candidate}")
    resolved = candidate.resolve()
    if source != resolved and source not in resolved.parents:
        raise ValueError(f"IOD source JSON resolves outside the source directory: {candidate}")
    with candidate.open("rb") as handle:
        return _read_bounded(handle, limit=MAX_IOD_JSON_BYTES, label=filename)


def _zip_json_bytes(source: Path, filename: str) -> bytes:
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_IOD_ARCHIVE_MEMBERS:
            raise ValueError(f"IOD archive exceeds the {MAX_IOD_ARCHIVE_MEMBERS}-member limit")
        names: set[str] = set()
        total_size = 0
        for info in infos:
            if not _safe_zip_member_name(info.filename):
                raise ValueError(f"Unsafe IOD archive member: {info.filename}")
            if info.filename in names:
                raise ValueError(f"Duplicate IOD archive member: {info.filename}")
            if info.flag_bits & 0x1:
                raise ValueError(f"Encrypted IOD archive members are not supported: {info.filename}")
            names.add(info.filename)
            total_size += info.file_size
            if total_size > MAX_IOD_ARCHIVE_UNCOMPRESSED_BYTES:
                raise ValueError(
                    f"IOD archive exceeds the {MAX_IOD_ARCHIVE_UNCOMPRESSED_BYTES}-byte uncompressed limit"
                )
        candidates = [
            info for info in infos if not info.is_dir() and PurePosixPath(info.filename).name == filename
        ]
        if not candidates:
            raise FileNotFoundError(f"{filename} was not found in {source}")
        if len(candidates) != 1:
            raise ValueError(f"Ambiguous IOD archive: found {len(candidates)} copies of {filename}")
        selected = candidates[0]
        if selected.file_size > MAX_IOD_JSON_BYTES:
            raise ValueError(f"{filename} exceeds the {MAX_IOD_JSON_BYTES}-byte limit")
        with archive.open(selected) as handle:
            return _read_bounded(handle, limit=MAX_IOD_JSON_BYTES, label=filename)


def _json_source_bytes(source: Path, filename: str) -> bytes:
    if source.is_dir():
        return _directory_json_bytes(source, filename)
    if zipfile.is_zipfile(source):
        return _zip_json_bytes(source, filename)
    raise ValueError("IOD source must be a directory or ZIP/wheel containing generated DICOM JSON")


def _read_json_source(source: Path, filename: str) -> Any:
    try:
        return json.loads(_json_source_bytes(source, filename).decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"{filename} must be UTF-8 encoded") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{filename} is not valid JSON: {exc}") from exc


def _object_rows(value: Any, filename: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{filename} must contain a JSON array of objects")
    return value


def _source_sha256(source: Path) -> str:
    digest = hashlib.sha256()
    for filename in IOD_SOURCE_FILENAMES:
        payload = _json_source_bytes(source, filename)
        digest.update(filename.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def prepare_registry(
    source: str | Path,
    *,
    edition: str,
    output: str | Path | None = None,
) -> Path:
    src = Path(source).expanduser().resolve()
    ciods = _object_rows(_read_json_source(src, "ciods.json"), "ciods.json")
    sops = _object_rows(_read_json_source(src, "sops.json"), "sops.json")
    ciod_modules = _object_rows(
        _read_json_source(src, "ciod_to_modules.json"),
        "ciod_to_modules.json",
    )
    module_attributes = _object_rows(
        _read_json_source(src, "module_to_attributes.json"),
        "module_to_attributes.json",
    )
    ciod_by_name = {str(item["name"]): item for item in ciods}
    modules_by_ciod: dict[str, list[dict[str, Any]]] = {}
    for item in ciod_modules:
        modules_by_ciod.setdefault(str(item["ciodId"]), []).append(item)
    attributes_by_module: dict[str, list[dict[str, Any]]] = {}
    for item in module_attributes:
        attributes_by_module.setdefault(str(item["moduleId"]), []).append(item)
    sop_payload: dict[str, Any] = {}
    for sop in sops:
        ciod = ciod_by_name.get(str(sop.get("ciod", "")))
        ciod_id = str(ciod["id"]) if ciod else None
        attributes: list[dict[str, Any]] = []
        for module in modules_by_ciod.get(ciod_id or "", []):
            for attribute in attributes_by_module.get(str(module["moduleId"]), []):
                raw_path = str(attribute.get("path", ""))
                pieces = raw_path.split(":")[1:]
                tag_path = [
                    piece.upper().replace("(", "").replace(")", "").replace(",", "")
                    for piece in pieces
                    if piece
                ]
                if not tag_path:
                    continue
                attributes.append(
                    {
                        "module_id": str(module["moduleId"]),
                        "module_usage": str(module.get("usage") or "U"),
                        "conditional_statement": module.get("conditionalStatement"),
                        "path": tag_path,
                        "type": None
                        if attribute.get("type") in (None, "None", "")
                        else str(attribute.get("type")),
                    }
                )
        sop_payload[str(sop["id"])] = {
            "name": sop.get("name"),
            "ciod_id": ciod_id,
            "ciod_name": ciod.get("name") if ciod else sop.get("ciod"),
            "attributes": attributes,
        }
    payload = {
        "format": "dicom-privacy-iod-registry-v1",
        "edition": edition,
        "source_sha256": _source_sha256(src),
        "source_type": "user-supplied generated JSON",
        "rights_notice": "Registry generated locally. The DICOM Standard and source JSON are not redistributed by this project.",
        "sop_classes": sop_payload,
    }
    destination = registry_path(data_dir=output, edition=edition)
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, payload, schema_name="iod-registry")
    load_registry.cache_clear()
    return destination


@lru_cache(maxsize=8)
def load_registry(path_text: str | None = None) -> dict[str, Any]:
    path = Path(path_text) if path_text else registry_path()
    if not path.is_file():
        raise IodDataNotInstalledError(data_status()["setup"] + f" Registry path: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_context(sop_class_uid: str, *, path: str | Path | None = None) -> IodContext:
    registry = load_registry(str(path) if path else None)
    item = registry.get("sop_classes", {}).get(str(sop_class_uid))
    return IodContext(
        sop_class_uid=str(sop_class_uid),
        sop_class_name=item.get("name") if item else None,
        ciod_id=item.get("ciod_id") if item else None,
        ciod_name=item.get("ciod_name") if item else None,
        registry_edition=registry.get("edition"),
        registry_source=registry.get("source_sha256"),
        resolved=item is not None,
    )


def attributes_for_sop(sop_class_uid: str, *, path: str | Path | None = None) -> list[IodAttribute]:
    registry = load_registry(str(path) if path else None)
    item = registry.get("sop_classes", {}).get(str(sop_class_uid))
    if not item:
        return []
    return [
        IodAttribute(
            module_id=row["module_id"],
            path=tuple(row["path"]),
            type=row.get("type"),
            module_usage=row.get("module_usage", "U"),
            conditional_statement=row.get("conditional_statement"),
        )
        for row in item.get("attributes", [])
    ]
