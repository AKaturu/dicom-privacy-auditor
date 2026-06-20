from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from collections.abc import Iterable
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path, PureWindowsPath
from typing import Any, cast

import numpy as np
import pydicom
from pydicom.datadict import tag_for_keyword
from pydicom.tag import Tag

from ..jsonio import validate_payload, write_json
from ..permissions import restrict_file
from .manifest import _validated_case_id, _validated_relative_path

MIDI_ACTIONS = {
    "date shifted",
    "patid consistent",
    "pixels hidden",
    "pixels retained",
    "tag retained",
    "text notnull",
    "text removed",
    "text retained",
    "uid changed",
    "uid consistent",
}

ALIASES: dict[str, tuple[str, ...]] = {
    "action": ("action", "action_type", "actiontype", "action_text", "required_action"),
    "category": ("category", "answer_category", "answercategory", "rule_category"),
    "sop_instance_uid": (
        "sop_instance_uid",
        "sopinstanceuid",
        "instance_uid",
        "instanceuid",
        "source_sop_instance_uid",
    ),
    "patient_id": ("patient_id", "patientid", "source_patient_id", "sourcepatientid"),
    "tag": ("tag", "dicom_tag", "dicomtag", "element", "attribute_tag"),
    "tag_name": ("tag_name", "tagname", "keyword", "attribute_name"),
    "value": ("value", "answer_value", "text", "expected_value", "source_value", "phi_value"),
    "relative_path": ("relative_path", "filepath", "file_path", "filename", "path"),
    "frame": ("frame", "frame_number", "framenumber", "frame_index"),
    "x1": ("x1", "left", "xmin", "column_start"),
    "y1": ("y1", "top", "ymin", "row_start"),
    "x2": ("x2", "right", "xmax", "column_end"),
    "y2": ("y2", "bottom", "ymax", "row_end"),
    "coordinates": ("coordinates", "bbox", "bounding_box", "pixel_coordinates"),
}


@dataclass
class MidiAction:
    action_id: str
    action: str
    category: str | None
    sop_instance_uid: str | None
    patient_id: str | None
    tag: str | None
    tag_name: str | None
    value: str | None
    source_relative_path: str | None
    frame: int | None = None
    bbox_xyxy: tuple[int, int, int, int] | None = None
    raw_table: str | None = None
    raw_row_id: str | None = None

    def __post_init__(self) -> None:
        self.action_id = _validated_case_id(self.action_id)
        if self.action not in MIDI_ACTIONS:
            raise ValueError(f"Unsupported MIDI action: {self.action}")
        if self.source_relative_path is not None:
            self.source_relative_path = _validated_relative_path(self.source_relative_path)
        if self.frame is not None and self.frame < 0:
            raise ValueError("MIDI frame must be non-negative")
        if self.bbox_xyxy is not None:
            x1, y1, x2, y2 = self.bbox_xyxy
            if min(x1, y1) < 0 or x2 <= x1 or y2 <= y1:
                raise ValueError("MIDI bounding boxes must be non-negative with x2>x1 and y2>y1")


@dataclass
class MidiImportManifest:
    schema_version: str
    dataset_name: str
    source_answer_key_sha256: str
    source_answer_key_name: str
    dicom_root: str
    action_count: int
    action_counts: dict[str, int]
    category_counts: dict[str, int]
    tables: list[dict[str, Any]]
    patient_mapping: str | None
    uid_mapping: str | None
    actions_file: str
    unresolved_source_paths: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MidiActionResult:
    action_id: str
    action: str
    category: str | None
    status: str
    reason: str
    source_present: bool
    candidate_present: bool
    source_ref: str | None = None
    candidate_ref: str | None = None


@dataclass
class MidiEvaluation:
    dataset_name: str
    results: list[MidiActionResult]
    summary: dict[str, Any]
    by_action: list[dict[str, Any]]
    by_category: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "summary": self.summary,
            "by_action": self.by_action,
            "by_category": self.by_category,
            "results": [asdict(item) for item in self.results],
        }


def _private_mode(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _write_private_jsonl(path: Path, rows: list[MidiAction]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(asdict(row), ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
        _private_mode(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _contained_path(root: Path, relative: str, *, label: str) -> Path:
    normalized = _validated_relative_path(relative)
    candidate = (root / normalized).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError(f"{label} escapes its configured root: {relative}")
    return candidate


def _roots_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _normalized_action(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("_", " ")
    text = re.sub(r"[<>]", "", text)
    return re.sub(r"\s+", " ", text)


def inspect_answer_key(path: str | Path) -> list[dict[str, Any]]:
    db_path = Path(path)
    with closing(sqlite3.connect(db_path)) as connection:
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        ]
        output: list[dict[str, Any]] = []
        for table in tables:
            quoted = table.replace('"', '""')
            columns = [
                row[1]
                for row in connection.execute(
                    f'PRAGMA table_info("{quoted}")'  # nosec B608
                )
            ]
            count = connection.execute(
                f'SELECT COUNT(*) FROM "{quoted}"'  # nosec B608
            ).fetchone()[0]
            action_column = _find_column(columns, ALIASES["action"])
            recognized = 0
            values: list[str] = []
            if action_column:
                col = action_column.replace('"', '""')
                for (value,) in connection.execute(
                    f'SELECT DISTINCT "{col}" FROM "{quoted}" LIMIT 100'  # nosec B608
                ):
                    action = _normalized_action(value)
                    values.append(action)
                    recognized += action in MIDI_ACTIONS
            output.append(
                {
                    "table": table,
                    "rows": count,
                    "columns": columns,
                    "action_column": action_column,
                    "recognized_action_values": sorted(set(values) & MIDI_ACTIONS),
                    "recognized_action_value_count": recognized,
                }
            )
        return output


def _find_column(columns: Iterable[str], aliases: Iterable[str]) -> str | None:
    normalized = {_normalize_name(column): column for column in columns}
    for alias in aliases:
        if _normalize_name(alias) in normalized:
            return normalized[_normalize_name(alias)]
    return None


def _column_map(columns: list[str], overrides: dict[str, str] | None = None) -> dict[str, str | None]:
    overrides = overrides or {}
    output: dict[str, str | None] = {}
    for field, aliases in ALIASES.items():
        output[field] = overrides.get(field) or _find_column(columns, aliases)
    return output


def _parse_tag(value: Any, tag_name: str | None = None) -> str | None:
    if value not in (None, ""):
        text = str(value).strip().replace("(", "").replace(")", "").replace(",", "").replace(" ", "")
        if text.lower().startswith("0x"):
            text = text[2:]
        try:
            return f"{int(text, 16):08X}"
        except ValueError:
            pass
    if tag_name:
        found = tag_for_keyword(str(tag_name).strip())
        return f"{int(found):08X}" if found is not None else None
    return None


def _parse_bbox(row: sqlite3.Row, columns: dict[str, str | None]) -> tuple[int, int, int, int] | None:
    direct = [columns[key] for key in ("x1", "y1", "x2", "y2")]
    direct_columns = [column for column in direct if column is not None]
    if len(direct_columns) == 4:
        try:
            values = tuple(int(float(row[column])) for column in direct_columns)
            return cast(tuple[int, int, int, int], values)
        except (TypeError, ValueError):
            pass
    coordinate_column = columns.get("coordinates")
    if not coordinate_column or row[coordinate_column] in (None, ""):
        return None
    text = str(row[coordinate_column])
    numbers = [int(float(item)) for item in re.findall(r"-?\d+(?:\.\d+)?", text)]
    return cast(tuple[int, int, int, int], tuple(numbers[:4])) if len(numbers) >= 4 else None


def _safe_ref(value: str | Path | None) -> str | None:
    if value is None:
        return None
    return "sha256:" + hashlib.sha256(str(value).encode()).hexdigest()[:16]


def _scan_dicom_index(root: Path) -> tuple[dict[str, str], dict[str, str]]:
    by_uid: dict[str, str] = {}
    by_patient: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError(f"DICOM source trees must not contain symbolic-link files: {path}")
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError(f"DICOM source file escapes its configured root: {path}")
        try:
            ds = pydicom.dcmread(
                resolved, stop_before_pixels=True, specific_tags=["SOPInstanceUID", "PatientID"]
            )
        except Exception:
            continue
        relative = path.relative_to(root).as_posix()
        if getattr(ds, "SOPInstanceUID", None):
            by_uid[str(ds.SOPInstanceUID)] = relative
        if getattr(ds, "PatientID", None):
            by_patient.setdefault(str(ds.PatientID), relative)
    return by_uid, by_patient


def _mapping_column(headers: list[str], role: str) -> str | None:
    exact = {
        "source": (
            "source",
            "source_value",
            "source_id",
            "original",
            "original_value",
            "original_patient_id",
            "original_uid",
            "from",
            "phi",
            "synthetic",
            "old",
            "old_value",
            "input",
            "input_value",
        ),
        "target": (
            "target",
            "target_value",
            "target_id",
            "anonymized",
            "anonymized_value",
            "anonymized_patient_id",
            "anonymized_uid",
            "deidentified",
            "deidentified_value",
            "curated",
            "new",
            "new_value",
            "output",
            "output_value",
            "to",
        ),
    }[role]
    match = _find_column(headers, exact)
    if match:
        return match
    # Public mapping files evolve. Prefer headers that contain a directional
    # marker plus an identifier/value marker, e.g. OriginalPatientID.
    directional = {
        "source": ("source", "original", "from", "phi", "synthetic", "old", "input"),
        "target": ("target", "anonym", "deident", "curated", "new", "output", "to"),
    }[role]
    candidates: list[tuple[int, str]] = []
    for header in headers:
        normalized = _normalize_name(header)
        score = sum(marker in normalized for marker in directional)
        score += sum(marker in normalized for marker in ("patientid", "uid", "identifier", "value"))
        if score >= 2:
            candidates.append((score, header))
    return (
        sorted(candidates, key=lambda item: (-item[0], headers.index(item[1])))[0][1] if candidates else None
    )


def _read_mapping(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}
    headers = list(rows[0])
    source = _mapping_column(headers, "source")
    target = _mapping_column(headers, "target")
    if not source or not target or source == target:
        if len(headers) < 2:
            raise ValueError(f"Mapping file requires at least two columns: {path}")
        source, target = headers[:2]
    return {
        str(row[source]).strip(): str(row[target]).strip()
        for row in rows
        if row.get(source) not in (None, "") and row.get(target) not in (None, "")
    }


def import_midi(
    answer_key: str | Path,
    dicom_root: str | Path,
    output_dir: str | Path,
    *,
    dataset_name: str = "MIDI-B",
    patient_mapping: str | Path | None = None,
    uid_mapping: str | Path | None = None,
    column_overrides: dict[str, str] | None = None,
    overwrite: bool = False,
) -> MidiImportManifest:
    db_path = Path(answer_key).resolve()
    images_root = Path(dicom_root).resolve()
    output = Path(output_dir).resolve()
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    if not images_root.is_dir():
        raise FileNotFoundError(images_root)
    protected_sources = [db_path, images_root]
    protected_sources.extend(
        Path(item).resolve() for item in (patient_mapping, uid_mapping) if item is not None
    )
    if any(_roots_overlap(output, source) for source in protected_sources):
        raise ValueError("MIDI import output must not overlap its answer key, DICOM root, or mapping files")
    if output.exists() and any(output.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Output directory is not empty: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=True)
    _private_mode(output, 0o700)
    schema = inspect_answer_key(db_path)
    candidate_tables = [item for item in schema if item["recognized_action_values"]]
    if not candidate_tables:
        raise ValueError("No SQLite table containing recognized MIDI-B actions was found")
    by_uid, by_patient = _scan_dicom_index(images_root)
    actions: list[MidiAction] = []

    with closing(sqlite3.connect(db_path)) as connection:
        connection.row_factory = sqlite3.Row
        for table_info in candidate_tables:
            table = table_info["table"]
            quoted = table.replace('"', '""')
            columns = _column_map(table_info["columns"], column_overrides)
            if not columns["action"]:
                continue
            for row_number, row in enumerate(
                connection.execute(
                    f'SELECT rowid AS __rowid__, * FROM "{quoted}"'  # nosec B608
                ),
                1,
            ):
                action_name = _normalized_action(row[columns["action"]])
                if action_name not in MIDI_ACTIONS:
                    continue
                sop_uid = (
                    str(row[columns["sop_instance_uid"]]).strip()
                    if columns["sop_instance_uid"] and row[columns["sop_instance_uid"]] not in (None, "")
                    else None
                )
                patient_id = (
                    str(row[columns["patient_id"]]).strip()
                    if columns["patient_id"] and row[columns["patient_id"]] not in (None, "")
                    else None
                )
                relative = (
                    str(row[columns["relative_path"]]).strip()
                    if columns["relative_path"] and row[columns["relative_path"]] not in (None, "")
                    else None
                )
                if relative:
                    try:
                        if Path(relative).is_absolute():
                            relative = Path(relative).resolve().relative_to(images_root).as_posix()
                        elif PureWindowsPath(relative).is_absolute():
                            relative = None
                        else:
                            relative = _validated_relative_path(relative)
                    except ValueError:
                        relative = None
                if not relative and sop_uid:
                    relative = by_uid.get(sop_uid)
                if not relative and patient_id:
                    relative = by_patient.get(patient_id)
                tag_name = (
                    str(row[columns["tag_name"]]).strip()
                    if columns["tag_name"] and row[columns["tag_name"]] not in (None, "")
                    else None
                )
                tag = _parse_tag(row[columns["tag"]] if columns["tag"] else None, tag_name)
                value = (
                    str(row[columns["value"]])
                    if columns["value"] and row[columns["value"]] is not None
                    else None
                )
                category = (
                    str(row[columns["category"]]).strip()
                    if columns["category"] and row[columns["category"]] not in (None, "")
                    else None
                )
                frame = None
                if columns["frame"] and row[columns["frame"]] not in (None, ""):
                    try:
                        frame = int(row[columns["frame"]])
                    except (TypeError, ValueError):
                        pass
                raw_id = str(row["__rowid__"] if "__rowid__" in row.keys() else row_number)
                action_id = hashlib.sha256(
                    f"{table}|{raw_id}|{action_name}|{sop_uid}|{tag}|{value}".encode()
                ).hexdigest()[:24]
                actions.append(
                    MidiAction(
                        action_id=action_id,
                        action=action_name,
                        category=category,
                        sop_instance_uid=sop_uid,
                        patient_id=patient_id,
                        tag=tag,
                        tag_name=tag_name,
                        value=value,
                        source_relative_path=relative,
                        frame=frame,
                        bbox_xyxy=_parse_bbox(row, columns),
                        raw_table=table,
                        raw_row_id=raw_id,
                    )
                )

    actions_path = output / "actions.jsonl"
    _write_private_jsonl(actions_path, actions)
    patient_target = output / "patient_mapping.csv" if patient_mapping else None
    uid_target = output / "uid_mapping.csv" if uid_mapping else None
    if patient_mapping and patient_target is not None:
        shutil.copyfile(Path(patient_mapping), patient_target)
        _private_mode(patient_target, 0o600)
    if uid_mapping and uid_target is not None:
        shutil.copyfile(Path(uid_mapping), uid_target)
        _private_mode(uid_target, 0o600)
    action_counts = Counter(item.action for item in actions)
    category_counts = Counter(item.category or "unspecified" for item in actions)
    manifest = MidiImportManifest(
        schema_version="1.0",
        dataset_name=dataset_name,
        source_answer_key_sha256=_sha256(db_path),
        source_answer_key_name=db_path.name,
        dicom_root=str(images_root),
        action_count=len(actions),
        action_counts=dict(sorted(action_counts.items())),
        category_counts=dict(sorted(category_counts.items())),
        tables=schema,
        patient_mapping=patient_target.name if patient_target else None,
        uid_mapping=uid_target.name if uid_target else None,
        actions_file=actions_path.name,
        unresolved_source_paths=sum(item.source_relative_path is None for item in actions),
    )
    write_json(output / "midi_manifest.json", manifest.to_dict(), schema_name="midi-import")
    return manifest


def read_actions(path: Path) -> list[MidiAction]:
    actions: list[MidiAction] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if len(line) > 10 * 1024 * 1024:
                raise ValueError("MIDI action line exceeds the 10 MiB limit")
            payload = json.loads(line)
            if payload.get("bbox_xyxy") is not None:
                payload["bbox_xyxy"] = tuple(payload["bbox_xyxy"])
            actions.append(MidiAction(**payload))
    return actions


def _candidate_index(root: Path) -> tuple[dict[str, Path], dict[str, list[Path]]]:
    by_uid: dict[str, Path] = {}
    by_patient: dict[str, list[Path]] = defaultdict(list)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError(f"DICOM candidate trees must not contain symbolic-link files: {path}")
        resolved = path.resolve()
        if root != resolved and root not in resolved.parents:
            raise ValueError(f"DICOM candidate file escapes its configured root: {path}")
        try:
            ds = pydicom.dcmread(
                resolved, stop_before_pixels=True, specific_tags=["SOPInstanceUID", "PatientID"]
            )
        except Exception:
            continue
        if getattr(ds, "SOPInstanceUID", None):
            by_uid[str(ds.SOPInstanceUID)] = path
        if getattr(ds, "PatientID", None):
            by_patient[str(ds.PatientID)].append(path)
    return by_uid, by_patient


def _dataset_value(dataset, tag_hex: str | None):
    if not tag_hex:
        return None, False
    tag = Tag(int(tag_hex, 16))
    if tag not in dataset:
        return None, False
    return dataset[tag].value, True


def _pixel_arrays(source_path: Path, candidate_path: Path, frame: int | None):
    source = np.asarray(pydicom.dcmread(source_path).pixel_array)
    candidate = np.asarray(pydicom.dcmread(candidate_path).pixel_array)
    if source.ndim > 2:
        index = max(0, (frame or 1) - 1)
        source = source[index]
        candidate = candidate[index]
    return source, candidate


def _evaluate_action(
    action: MidiAction,
    source_path: Path | None,
    candidate_path: Path | None,
    patient_map: dict[str, str],
    uid_map: dict[str, str],
) -> MidiActionResult:
    common: dict[str, Any] = {
        "action_id": action.action_id,
        "action": action.action,
        "category": action.category,
        "source_present": bool(source_path and source_path.exists()),
        "candidate_present": bool(candidate_path and candidate_path.exists()),
        "source_ref": _safe_ref(source_path),
        "candidate_ref": _safe_ref(candidate_path),
    }
    if not source_path or not source_path.exists():
        return MidiActionResult(status="unresolved", reason="Source object could not be resolved", **common)
    if not candidate_path or not candidate_path.exists():
        return MidiActionResult(status="fail", reason="Candidate object could not be resolved", **common)
    try:
        source = pydicom.dcmread(source_path)
        candidate = pydicom.dcmread(candidate_path)
    except Exception as exc:
        return MidiActionResult(
            status="error", reason=f"DICOM read failed: {type(exc).__name__}: {exc}", **common
        )
    source_value, source_has = _dataset_value(source, action.tag)
    candidate_value, candidate_has = _dataset_value(candidate, action.tag)
    source_text = str(source_value or "")
    candidate_text = str(candidate_value or "")

    passed = False
    reason = ""
    if action.action == "date shifted":
        passed = source_has and candidate_has and bool(candidate_text) and source_text != candidate_text
        reason = "date changed" if passed else "date was absent, empty, or unchanged"
    elif action.action == "patid consistent":
        old = action.patient_id or str(getattr(source, "PatientID", ""))
        expected = patient_map.get(old)
        actual = str(getattr(candidate, "PatientID", ""))
        passed = bool(expected) and actual == expected
        reason = (
            "patient mapping matched" if passed else "candidate PatientID did not match the supplied mapping"
        )
    elif action.action == "tag retained":
        passed = candidate_has
        reason = "tag retained" if passed else "required tag is absent"
    elif action.action == "text notnull":
        passed = candidate_has and bool(candidate_text.strip())
        reason = "tag contains a value" if passed else "tag is absent or zero length"
    elif action.action == "text removed":
        needle = action.value or source_text
        passed = not needle or needle not in candidate_text
        reason = "specified text removed" if passed else "specified text remains"
    elif action.action == "text retained":
        needle = action.value or source_text
        passed = candidate_has and needle in candidate_text
        reason = "specified text retained" if passed else "specified text is missing"
    elif action.action == "uid changed":
        passed = source_has and candidate_has and bool(candidate_text) and source_text != candidate_text
        reason = "UID changed" if passed else "UID was absent, empty, or unchanged"
    elif action.action == "uid consistent":
        old = action.value or source_text or action.sop_instance_uid or ""
        expected = uid_map.get(old)
        passed = bool(expected) and candidate_text == expected
        reason = "UID mapping matched" if passed else "candidate UID did not match the supplied mapping"
    elif action.action in {"pixels hidden", "pixels retained"}:
        try:
            source_pixels, candidate_pixels = _pixel_arrays(source_path, candidate_path, action.frame)
            if source_pixels.shape != candidate_pixels.shape:
                passed = False
                reason = "pixel array shape changed"
            elif action.action == "pixels hidden":
                if not action.bbox_xyxy:
                    return MidiActionResult(
                        status="unresolved", reason="Pixel hiding action has no usable bounding box", **common
                    )
                x1, y1, x2, y2 = action.bbox_xyxy
                passed = not np.array_equal(source_pixels[y1:y2, x1:x2], candidate_pixels[y1:y2, x1:x2])
                reason = "target region changed" if passed else "target region is unchanged"
            else:
                passed = np.array_equal(source_pixels, candidate_pixels)
                reason = "pixels retained" if passed else "pixel values changed"
        except Exception as exc:
            return MidiActionResult(
                status="error", reason=f"Pixel comparison failed: {type(exc).__name__}: {exc}", **common
            )
    return MidiActionResult(status="pass" if passed else "fail", reason=reason, **common)


def _summarize(results: list[MidiActionResult], key: str) -> list[dict[str, Any]]:
    groups: dict[str, list[MidiActionResult]] = defaultdict(list)
    for result in results:
        groups[str(getattr(result, key) or "unspecified")].append(result)
    output = []
    for name, items in sorted(groups.items()):
        passed = sum(item.status == "pass" for item in items)
        scored = sum(item.status in {"pass", "fail"} for item in items)
        output.append(
            {
                key: name,
                "total": len(items),
                "scored": scored,
                "passed": passed,
                "failed": sum(item.status == "fail" for item in items),
                "unresolved": sum(item.status == "unresolved" for item in items),
                "errors": sum(item.status == "error" for item in items),
                "score": passed / scored if scored else None,
            }
        )
    return output


def evaluate_midi(
    imported_dir: str | Path,
    candidate_root: str | Path,
    output_dir: str | Path,
    *,
    patient_mapping: str | Path | None = None,
    uid_mapping: str | Path | None = None,
    source_root: str | Path | None = None,
) -> MidiEvaluation:
    imported = Path(imported_dir).resolve()
    candidate = Path(candidate_root).resolve()
    output = Path(output_dir).resolve()
    manifest_path = imported / "midi_manifest.json"
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_payload(manifest_payload, "midi-import")
    resolved_source_root = (
        Path(source_root).resolve()
        if source_root is not None
        else Path(manifest_payload["dicom_root"]).resolve()
    )
    if not imported.is_dir() or not candidate.is_dir() or not resolved_source_root.is_dir():
        raise FileNotFoundError("MIDI imported, candidate, and source directories must exist")
    if any(_roots_overlap(output, root) for root in (imported, candidate, resolved_source_root)):
        raise ValueError("MIDI evaluation output must not overlap imported, candidate, or source directories")
    output.mkdir(parents=True, exist_ok=True)
    _private_mode(output, 0o700)
    actions_path = _contained_path(imported, manifest_payload["actions_file"], label="MIDI actions file")
    actions = read_actions(actions_path)
    patient_path = (
        Path(patient_mapping)
        if patient_mapping
        else (
            _contained_path(imported, manifest_payload["patient_mapping"], label="MIDI patient mapping")
            if manifest_payload.get("patient_mapping")
            else None
        )
    )
    uid_path = (
        Path(uid_mapping)
        if uid_mapping
        else (
            _contained_path(imported, manifest_payload["uid_mapping"], label="MIDI UID mapping")
            if manifest_payload.get("uid_mapping")
            else None
        )
    )
    patient_map = _read_mapping(patient_path)
    uid_map = _read_mapping(uid_path)
    candidate_by_uid, candidate_by_patient = _candidate_index(candidate)
    results: list[MidiActionResult] = []

    for action in actions:
        source_path = (
            _contained_path(resolved_source_root, action.source_relative_path, label="MIDI source object")
            if action.source_relative_path
            else None
        )
        candidate_path = None
        mapped_uid = uid_map.get(action.sop_instance_uid or "")
        if mapped_uid:
            candidate_path = candidate_by_uid.get(mapped_uid)
        if candidate_path is None and action.sop_instance_uid:
            candidate_path = candidate_by_uid.get(action.sop_instance_uid)
        if candidate_path is None and action.patient_id:
            mapped_patient = patient_map.get(action.patient_id, action.patient_id)
            candidates = candidate_by_patient.get(mapped_patient, [])
            if len(candidates) == 1:
                candidate_path = candidates[0]
        if candidate_path is None and action.source_relative_path:
            possible = _contained_path(candidate, action.source_relative_path, label="MIDI candidate object")
            if possible.exists():
                candidate_path = possible
        results.append(_evaluate_action(action, source_path, candidate_path, patient_map, uid_map))

    scored = sum(item.status in {"pass", "fail"} for item in results)
    passed = sum(item.status == "pass" for item in results)
    summary = {
        "actions": len(results),
        "scored": scored,
        "passed": passed,
        "failed": sum(item.status == "fail" for item in results),
        "unresolved": sum(item.status == "unresolved" for item in results),
        "errors": sum(item.status == "error" for item in results),
        "score": passed / scored if scored else None,
    }
    evaluation = MidiEvaluation(
        dataset_name=manifest_payload["dataset_name"],
        results=results,
        summary=summary,
        by_action=_summarize(results, "action"),
        by_category=_summarize(results, "category"),
    )
    payload = evaluation.to_dict()
    write_json(output / "midi_evaluation.json", payload, schema_name="midi-evaluation")
    with (output / "midi_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=list(asdict(results[0]).keys()) if results else ["action_id"]
        )
        writer.writeheader()
        for result in results:
            writer.writerow(asdict(result))
    restrict_file(output / "midi_results.csv")
    lines = [
        f"# MIDI-B Evaluation: {evaluation.dataset_name}",
        "",
        f"- Score: {summary['score'] if summary['score'] is not None else 'NA'}",
        f"- Passed: {passed}/{scored} scored actions",
        f"- Unresolved: {summary['unresolved']}",
        f"- Errors: {summary['errors']}",
        "",
        "| Action | Total | Passed | Failed | Unresolved | Score |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in evaluation.by_action:
        score = "NA" if row["score"] is None else f"{row['score']:.6f}"
        lines.append(
            f"| {row['action']} | {row['total']} | {row['passed']} | {row['failed']} | {row['unresolved']} | {score} |"
        )
    report_path = output / "MIDI_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    restrict_file(report_path)
    return evaluation
