from __future__ import annotations

import csv
import hashlib
from collections import defaultdict
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pydicom
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue

from .models import CorpusFinding, CorpusReport

_UID_IDENTITY_KEYWORDS = {
    "StudyInstanceUID",
    "SeriesInstanceUID",
    "SOPInstanceUID",
    "FrameOfReferenceUID",
    "SynchronizationFrameOfReferenceUID",
    "ConcatenationUID",
    "DimensionOrganizationUID",
    "TrackingUID",
}


def _safe_ref(path: str | Path) -> str:
    return "sha256:" + hashlib.sha256(str(path).encode()).hexdigest()[:16]


def _read(path: Path) -> Dataset | None:
    try:
        return pydicom.dcmread(path, force=False)
    except Exception:
        return None


def _scan(root: Path) -> dict[str, tuple[Path, Dataset]]:
    if not root.exists():
        raise FileNotFoundError(root)
    output: dict[str, tuple[Path, Dataset]] = {}
    paths = [root] if root.is_file() else sorted(root.rglob("*"))
    for path in paths:
        if not path.is_file():
            continue
        if path.is_symlink():
            raise ValueError(f"Corpus trees must not contain symbolic-link files: {path}")
        resolved = path.resolve()
        if root.is_dir() and root != resolved and root not in resolved.parents:
            raise ValueError(f"Corpus file escapes its configured root: {path}")
        ds = _read(resolved)
        if ds is not None:
            key = resolved.name if root.is_file() else resolved.relative_to(root).as_posix()
            output[key] = (resolved, ds)
    return output


def _load_mapping(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}
    headers = list(rows[0])
    source = next(
        (item for item in headers if item.casefold() in {"source", "source_path", "original"}), headers[0]
    )
    candidate = next(
        (item for item in headers if item.casefold() in {"candidate", "candidate_path", "output"}),
        headers[1] if len(headers) > 1 else headers[0],
    )
    return {str(row[source]): str(row[candidate]) for row in rows if row.get(source) and row.get(candidate)}


def _pair(
    source: dict[str, tuple[Path, Dataset]],
    candidate: dict[str, tuple[Path, Dataset]],
    mapping: dict[str, str],
) -> tuple[list[tuple[str, str, Dataset, Dataset]], set[str], set[str]]:
    pairs: list[tuple[str, str, Dataset, Dataset]] = []
    used_candidate: set[str] = set()
    for source_key, (_, source_ds) in source.items():
        candidate_key = mapping.get(source_key, source_key)
        if candidate_key in candidate:
            pairs.append((source_key, candidate_key, source_ds, candidate[candidate_key][1]))
            used_candidate.add(candidate_key)
    return pairs, set(source) - {item[0] for item in pairs}, set(candidate) - used_candidate


def _values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, MultiValue):
        return [str(item) for item in value]
    return [str(value)]


def _walk(ds: Dataset, prefix: str = "") -> Iterable[tuple[str, Any]]:
    for element in ds:
        keyword = element.keyword or str(element.tag)
        path = f"{prefix}.{keyword}" if prefix else keyword
        yield path, element
        if element.VR == "SQ":
            for index, item in enumerate(element.value):
                yield from _walk(item, f"{path}[{index}]")


def _date_value(text: str, vr: str) -> date | None:
    try:
        if vr == "DA" and len(text) >= 8:
            return datetime.strptime(text[:8], "%Y%m%d").date()
        if vr == "DT" and len(text) >= 8:
            return datetime.strptime(text[:8], "%Y%m%d").date()
    except ValueError:
        return None
    return None


def _patient_key(ds: Dataset) -> str:
    return str(getattr(ds, "PatientID", "")) or str(getattr(ds, "PatientName", "")) or "unknown"


def _mapping_findings(
    name: str,
    mappings: dict[str, set[str]],
    reverse: dict[str, set[str]],
    *,
    retained_is_warning: bool = False,
) -> list[CorpusFinding]:
    findings: list[CorpusFinding] = []
    for source_value, targets in mappings.items():
        if len(targets) > 1:
            findings.append(
                CorpusFinding(
                    f"{name}_one_to_many",
                    "high",
                    name,
                    _safe_ref(source_value),
                    None,
                    f"One source {name} maps to multiple candidate values",
                    len(targets),
                    tuple(_safe_ref(item) for item in sorted(targets)[:5]),
                )
            )
        if retained_is_warning and source_value in targets:
            findings.append(
                CorpusFinding(
                    f"{name}_retained",
                    "medium",
                    name,
                    _safe_ref(source_value),
                    _safe_ref(source_value),
                    f"Source {name} was retained",
                    1,
                )
            )
    for target, sources in reverse.items():
        if len(sources) > 1:
            findings.append(
                CorpusFinding(
                    f"{name}_collision",
                    "critical",
                    name,
                    None,
                    _safe_ref(target),
                    f"Multiple source {name} values collide in one candidate value",
                    len(sources),
                    tuple(_safe_ref(item) for item in sorted(sources)[:5]),
                )
            )
    return findings


def evaluate_corpus(
    source_root: str | Path,
    candidate_root: str | Path,
    *,
    mapping_csv: str | Path | None = None,
    disclose_paths: bool = False,
) -> CorpusReport:
    raw_source = Path(source_root).expanduser()
    raw_candidate = Path(candidate_root).expanduser()
    if raw_source.is_symlink() or raw_candidate.is_symlink():
        raise ValueError("Corpus roots must not be symbolic links")
    source_path = raw_source.resolve()
    candidate_path = raw_candidate.resolve()
    source = _scan(source_path)
    candidate = _scan(candidate_path)
    mapping = _load_mapping(Path(mapping_csv)) if mapping_csv else {}
    pairs, source_only, candidate_only = _pair(source, candidate, mapping)
    findings: list[CorpusFinding] = []
    uid_map: dict[str, set[str]] = defaultdict(set)
    uid_reverse: dict[str, set[str]] = defaultdict(set)
    identity_uid_map: dict[str, set[str]] = defaultdict(set)
    patient_map: dict[str, set[str]] = defaultdict(set)
    patient_reverse: dict[str, set[str]] = defaultdict(set)
    date_shifts: dict[str, set[int]] = defaultdict(set)
    referenced_expectations: list[tuple[str, str, str, str]] = []
    readable = 0
    meta_consistent = 0

    for source_key, candidate_key, sds, cds in pairs:
        readable += 1
        source_patient = _patient_key(sds)
        candidate_patient = _patient_key(cds)
        patient_map[source_patient].add(candidate_patient)
        patient_reverse[candidate_patient].add(source_patient)
        source_index = {path: element for path, element in _walk(sds)}
        candidate_index = {path: element for path, element in _walk(cds)}
        for path, source_element in source_index.items():
            candidate_element = candidate_index.get(path)
            if candidate_element is None:
                continue
            if source_element.VR == "UI":
                old_values = _values(source_element.value)
                new_values = _values(candidate_element.value)
                for old, new in zip(old_values, new_values, strict=False):
                    uid_map[old].add(new)
                    uid_reverse[new].add(old)
                    if (source_element.keyword or "") in _UID_IDENTITY_KEYWORDS:
                        identity_uid_map[old].add(new)
                    else:
                        referenced_expectations.append((source_key, path, old, new))
            if source_element.VR in {"DA", "DT"}:
                old_date = _date_value(str(source_element.value), source_element.VR)
                new_date = _date_value(str(candidate_element.value), candidate_element.VR)
                if old_date and new_date:
                    date_shifts[source_patient].add((new_date - old_date).days)
        candidate_sop = str(getattr(cds, "SOPInstanceUID", ""))
        meta_sop = str(getattr(getattr(cds, "file_meta", None), "MediaStorageSOPInstanceUID", ""))
        candidate_class = str(getattr(cds, "SOPClassUID", ""))
        meta_class = str(getattr(getattr(cds, "file_meta", None), "MediaStorageSOPClassUID", ""))
        if candidate_sop and candidate_sop == meta_sop and candidate_class and candidate_class == meta_class:
            meta_consistent += 1
        else:
            findings.append(
                CorpusFinding(
                    "file_meta_inconsistent",
                    "high",
                    "instance",
                    source_key,
                    candidate_key,
                    "Candidate File Meta UIDs do not match the main dataset",
                )
            )

    findings.extend(_mapping_findings("uid", uid_map, uid_reverse))
    findings.extend(_mapping_findings("pseudonym", patient_map, patient_reverse, retained_is_warning=True))
    for patient, shifts in date_shifts.items():
        if len(shifts) > 1:
            findings.append(
                CorpusFinding(
                    "date_shift_inconsistent",
                    "high",
                    "patient",
                    _safe_ref(patient),
                    None,
                    "A source patient has multiple date-shift offsets",
                    len(shifts),
                    tuple(str(item) for item in sorted(shifts)[:10]),
                )
            )
    for source_key, path, old, observed_new in referenced_expectations:
        expected = identity_uid_map.get(old, set())
        if expected and observed_new not in expected:
            findings.append(
                CorpusFinding(
                    "reference_uid_inconsistent",
                    "critical",
                    "reference",
                    _safe_ref(old),
                    _safe_ref(observed_new),
                    f"Referenced UID at {path} does not use the corpus mapping",
                    1,
                    (_safe_ref(source_key),),
                )
            )

    metrics = {
        "readable_pairs": readable,
        "file_meta_consistent": meta_consistent,
        "unique_source_uids": len(uid_map),
        "unique_candidate_uids": len(uid_reverse),
        "unique_source_patients": len(patient_map),
        "unique_candidate_pseudonyms": len(patient_reverse),
        "patients_with_date_values": len(date_shifts),
        "critical_findings": sum(item.severity == "critical" for item in findings),
        "high_findings": sum(item.severity == "high" for item in findings),
    }
    return CorpusReport(
        source=str(source_path) if disclose_paths else _safe_ref(source_path),
        candidate=str(candidate_path) if disclose_paths else _safe_ref(candidate_path),
        pairing="mapping_csv" if mapping else "relative_path",
        pairs=len(pairs),
        source_only=len(source_only),
        candidate_only=len(candidate_only),
        findings=findings,
        metrics=metrics,
    )
