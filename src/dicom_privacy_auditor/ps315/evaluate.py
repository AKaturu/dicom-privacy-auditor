from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pydicom
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.sequence import Sequence
from pydicom.uid import UID

from ..detectors import normalize_value
from ..iod.evaluate import iod_context_for_pair
from ..iod.registry import IodDataNotInstalledError
from .models import AttributeEvaluation, PolicySelection, ProfileEvaluation, ProfileOption
from .policy import get_code_rule, resolve_code_rule, rule_for_dataset_tag, table_metadata


def _safe_ref(path: str | Path) -> str:
    value = str(path)
    return f"sha256:{hashlib.sha256(value.encode()).hexdigest()[:16]}"


def _walk(dataset: Dataset, prefix: str = ""):
    for element in dataset:
        keyword = element.keyword or str(element.tag)
        path = f"{prefix}.{keyword}" if prefix else keyword
        yield path, element
        if element.VR == "SQ":
            for index, item in enumerate(element.value):
                yield from _walk(item, f"{path}[{index}]")


def _index(dataset: Dataset) -> dict[str, Any]:
    return {path: element for path, element in _walk(dataset)}


def _keyword_to_tag_paths(dataset: Dataset) -> dict[str, str]:
    output: dict[str, str] = {}

    def walk(ds: Dataset, keyword_prefix: str = "", tag_prefix: tuple[str, ...] = ()) -> None:
        for element in ds:
            keyword = element.keyword or str(element.tag)
            keyword_path = f"{keyword_prefix}.{keyword}" if keyword_prefix else keyword
            tag = f"{int(element.tag):08X}"
            tag_path = (*tag_prefix, tag)
            output[keyword_path] = "/".join(tag_path)
            if element.VR == "SQ":
                for index, item in enumerate(element.value):
                    walk(item, f"{keyword_path}[{index}]", tag_path)

    walk(dataset)
    return output


def _empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, bytes, bytearray, MultiValue, list, tuple, Sequence)):
        return len(value) == 0
    return False


def _valid_uid(value: Any) -> bool:
    try:
        uid = UID(str(value))
        return bool(uid.is_valid)
    except Exception:
        return False


def _observed(source_element, candidate_element) -> str:
    if candidate_element is None:
        return "X"
    # Zero-item sequences are zero-length attributes for profile evaluation.
    # This check must precede the generic SQ branch.
    if _empty(candidate_element.value):
        return "Z"
    if candidate_element.VR == "SQ":
        return "K" if source_element is not None else "PRESENT_SEQUENCE"
    if source_element is None:
        return "PRESENT"
    source_value = normalize_value(source_element.value)
    candidate_value = normalize_value(candidate_element.value)
    if source_value == candidate_value:
        return "K"
    if candidate_element.VR == "UI" and _valid_uid(candidate_element.value):
        return "U"
    return "D/C"


def _tokens(directive: str) -> set[str]:
    return {item.rstrip("*") for item in directive.split("/") if item}


def _satisfies(observed: str, directive: str) -> tuple[bool, bool, str]:
    allowed = _tokens(directive)
    if observed == "X":
        return ("X" in allowed, False, "attribute removed")
    if observed == "Z":
        return ("Z" in allowed, False, "attribute retained with zero length")
    if observed == "K":
        if "K" in allowed:
            return (True, False, "source value retained")
        if "C" in allowed:
            return (True, True, "cleaning cannot be proven when the value is unchanged")
        return (False, False, "source value retained when transformation was required")
    if observed == "U":
        return ("U" in allowed or "D" in allowed or "Z" in allowed, False, "UID changed to a valid UID")
    if observed == "D/C":
        valid = bool(allowed & {"D", "C", "Z"})
        manual = "C" in allowed
        return (
            valid,
            manual,
            "value changed; semantic cleaning requires review" if manual else "value changed",
        )
    return (False, True, "candidate contains an element that cannot be classified automatically")


def _uid_consistency(results: list[AttributeEvaluation], source: Dataset, candidate: Dataset) -> None:
    source_index = _index(source)
    candidate_index = _index(candidate)
    mapping: dict[str, str] = {}
    inconsistent: set[str] = set()
    for path, source_element in source_index.items():
        if source_element.VR != "UI" or path not in candidate_index:
            continue
        candidate_element = candidate_index[path]
        old = normalize_value(source_element.value)
        new = normalize_value(candidate_element.value)
        if old == new or not old:
            continue
        prior = mapping.setdefault(old, new)
        if prior != new:
            inconsistent.add(old)
    if not inconsistent:
        return
    for result in results:
        if result.observed == "U":
            result.status = "fail"
            result.reason = "UID replacement was not internally consistent across references"


_VALUE_ATTRIBUTES = {
    "TEXT": "TextValue",
    "PNAME": "PersonName",
    "DATE": "Date",
    "TIME": "Time",
    "DATETIME": "DateTime",
    "UIDREF": "UID",
    "CODE": "ConceptCodeSequence",
    "NUM": "MeasuredValueSequence",
    "COMPOSITE": "ReferencedSOPSequence",
    "IMAGE": "ReferencedSOPSequence",
    "WAVEFORM": "ReferencedSOPSequence",
}


def _content_key(item: Dataset) -> tuple[str, str, str] | None:
    sequence = getattr(item, "ConceptNameCodeSequence", None)
    if not sequence:
        return None
    code = sequence[0]
    scheme = str(getattr(code, "CodingSchemeDesignator", ""))
    value = str(getattr(code, "CodeValue", getattr(code, "LongCodeValue", "")))
    value_type = str(getattr(item, "ValueType", ""))
    return (scheme, value, value_type) if scheme and value and value_type else None


def _content_items(dataset: Dataset):
    def walk(sequence, prefix: str = "ContentSequence"):
        for index, item in enumerate(sequence or []):
            path = f"{prefix}[{index}]"
            yield path, item
            if getattr(item, "ContentSequence", None):
                yield from walk(item.ContentSequence, f"{path}.ContentSequence")

    yield from walk(getattr(dataset, "ContentSequence", None))


def _content_value(item: Dataset | None, value_type: str):
    if item is None:
        return None, False
    attribute = _VALUE_ATTRIBUTES.get(value_type)
    if not attribute:
        return "", True
    if not hasattr(item, attribute):
        return None, False
    value = getattr(item, attribute)
    if isinstance(value, Sequence):
        serial = []
        for sequence_item in value:
            serial.append(
                {
                    element.keyword or str(element.tag): normalize_value(element.value)
                    for element in sequence_item
                    if element.VR != "SQ"
                }
            )
        return str(serial), True
    return normalize_value(value), True


def _evaluate_code_rules(
    source: Dataset, candidate: Dataset, selection: PolicySelection
) -> list[AttributeEvaluation]:
    candidate_by_key: dict[tuple[str, str, str], list[tuple[str, Dataset]]] = {}
    for path, item in _content_items(candidate):
        key = _content_key(item)
        if key:
            candidate_by_key.setdefault(key, []).append((path, item))
    occurrence: dict[tuple[str, str, str], int] = {}
    output: list[AttributeEvaluation] = []
    for source_path, source_item in _content_items(source):
        key = _content_key(source_item)
        if not key:
            continue
        rule = get_code_rule(*key)
        if rule is None:
            continue
        ordinal = occurrence.get(key, 0)
        occurrence[key] = ordinal + 1
        candidates = candidate_by_key.get(key, [])
        candidate_item = candidates[ordinal][1] if ordinal < len(candidates) else None
        source_value, source_present = _content_value(source_item, key[2])
        candidate_value, candidate_present = _content_value(candidate_item, key[2])
        if candidate_item is None:
            observed = "X"
        elif not candidate_present or _empty(candidate_value):
            observed = "Z"
        elif source_present and source_value == candidate_value:
            observed = "K"
        elif key[2] == "UIDREF" and _valid_uid(candidate_value):
            observed = "U"
        else:
            observed = "D/C"
        resolution = resolve_code_rule(rule, selection)
        checks = [_satisfies(observed, directive) for directive in resolution.directives]
        passed = all(item[0] for item in checks)
        review = resolution.conflicts or any(item[1] for item in checks)
        output.append(
            AttributeEvaluation(
                path=f"{source_path}::{key[0]}:{key[1]}:{key[2]}",
                tag="CODE",
                keyword=rule.code_meaning,
                rule_name=f"Table E.1-2: {rule.code_meaning}",
                expected=list(resolution.directives),
                observed=observed,
                status="pass" if passed and not review else "review" if passed else "fail",
                reason="; ".join(dict.fromkeys(item[2] for item in checks)),
                manual_review=review,
            )
        )
    return output


def _file_meta_consistency_checks(candidate: Dataset) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    candidate_sop = str(getattr(candidate, "SOPInstanceUID", ""))
    meta_sop = str(getattr(getattr(candidate, "file_meta", None), "MediaStorageSOPInstanceUID", ""))
    if candidate_sop or meta_sop:
        checks.append(
            {
                "check": "file_meta_sop_instance_uid_consistency",
                "status": "pass" if candidate_sop and candidate_sop == meta_sop else "fail",
                "reason": (
                    "MediaStorageSOPInstanceUID matches SOPInstanceUID"
                    if candidate_sop and candidate_sop == meta_sop
                    else "MediaStorageSOPInstanceUID is missing or does not match SOPInstanceUID"
                ),
            }
        )
    candidate_class = str(getattr(candidate, "SOPClassUID", ""))
    meta_class = str(getattr(getattr(candidate, "file_meta", None), "MediaStorageSOPClassUID", ""))
    if candidate_class or meta_class:
        checks.append(
            {
                "check": "file_meta_sop_class_uid_consistency",
                "status": "pass" if candidate_class and candidate_class == meta_class else "fail",
                "reason": (
                    "MediaStorageSOPClassUID matches SOPClassUID"
                    if candidate_class and candidate_class == meta_class
                    else "MediaStorageSOPClassUID is missing or does not match SOPClassUID"
                ),
            }
        )
    return checks


def evaluate_pair(
    source_path: str | Path,
    candidate_path: str | Path,
    selection: PolicySelection | None = None,
    *,
    disclose_paths: bool = False,
    iod_aware: bool = False,
    iod_registry_path: str | Path | None = None,
) -> ProfileEvaluation:
    selection = selection or PolicySelection()
    source = pydicom.dcmread(source_path)
    candidate = pydicom.dcmread(candidate_path)
    source_index = _index(source)
    candidate_index = _index(candidate)
    results: list[AttributeEvaluation] = []
    iod_summary = None
    iod_context: dict[str, dict[str, Any]] = {}
    keyword_tag_paths = _keyword_to_tag_paths(source)
    keyword_tag_paths.update(_keyword_to_tag_paths(candidate))
    if iod_aware:
        try:
            summary_object, iod_context = iod_context_for_pair(
                source, candidate, registry_path=iod_registry_path
            )
            iod_summary = summary_object.to_dict()
        except IodDataNotInstalledError:
            raise

    for path, source_element in source_index.items():
        resolution = rule_for_dataset_tag(int(source_element.tag), selection)
        if resolution is None:
            continue
        candidate_element = candidate_index.get(path)
        observed = _observed(source_element, candidate_element)
        directives = list(resolution.directives)
        context = iod_context.get(keyword_tag_paths.get(path, "")) if iod_aware else None
        checks = [_satisfies(observed, directive) for directive in directives]
        passed = all(item[0] for item in checks)
        review = resolution.conflicts or any(item[1] for item in checks)
        reasons = list(dict.fromkeys(item[2] for item in checks))
        if context:
            if not context.get("defined_in_active_iod", True):
                directives = ["X"]
                passed = observed == "X"
                review = False
                reasons.append("IOD-aware override: attribute is not defined in the active IOD")
            else:
                if observed == "X" and not context.get("may_remove", True):
                    passed = False
                    reasons.append(f"IOD Type {context.get('attribute_type')} does not permit removal")
                if observed == "Z" and not context.get("may_zero", True):
                    passed = False
                    reasons.append(f"IOD Type {context.get('attribute_type')} requires a non-empty value")
                if context.get("condition") == "unresolved":
                    review = True
                    reasons.append("IOD conditional requirement could not be resolved automatically")
        status = "pass" if passed and not review else "review" if passed else "fail"
        results.append(
            AttributeEvaluation(
                path=path,
                tag=str(source_element.tag),
                keyword=source_element.keyword or "",
                rule_name=resolution.rule.name,
                expected=directives,
                observed=observed,
                status=status,
                reason="; ".join(dict.fromkeys(reasons)),
                manual_review=review,
                iod_context=context,
            )
        )

    # Flag newly introduced attributes only when every active policy directive
    # requires removal. Attributes that are legitimately generated by a
    # de-identification workflow (for example method documentation) are not
    # treated as failures merely because they were absent in the source.
    for path, candidate_element in candidate_index.items():
        if path in source_index:
            continue
        context = iod_context.get(keyword_tag_paths.get(path, "")) if iod_aware else None
        resolution = rule_for_dataset_tag(int(candidate_element.tag), selection)
        if context and not context.get("defined_in_active_iod", True):
            results.append(
                AttributeEvaluation(
                    path=path,
                    tag=str(candidate_element.tag),
                    keyword=candidate_element.keyword or "",
                    rule_name="IOD-aware attribute placement",
                    expected=["X"],
                    observed="PRESENT_SEQUENCE" if candidate_element.VR == "SQ" else "PRESENT",
                    status="fail",
                    reason="candidate introduced an attribute that is not defined in the active IOD",
                    manual_review=False,
                    iod_context=context,
                )
            )
            continue
        if resolution is None:
            continue
        directive_tokens = [_tokens(item) for item in resolution.directives]
        removal_or_zero_only = bool(directive_tokens) and all(
            tokens and tokens <= {"X", "Z"} for tokens in directive_tokens
        )
        if not removal_or_zero_only or _empty(candidate_element.value):
            continue
        results.append(
            AttributeEvaluation(
                path=path,
                tag=str(candidate_element.tag),
                keyword=candidate_element.keyword or "",
                rule_name=resolution.rule.name,
                expected=list(resolution.directives),
                observed="PRESENT_SEQUENCE" if candidate_element.VR == "SQ" else "PRESENT",
                status="fail",
                reason="candidate introduced an attribute that the selected profile requires to be removed",
                manual_review=False,
                iod_context=context,
            )
        )

    _uid_consistency(results, source, candidate)
    results.extend(_evaluate_code_rules(source, candidate, selection))
    operational: list[dict[str, Any]] = []

    operational.extend(_file_meta_consistency_checks(candidate))
    if ProfileOption.CLEAN_PIXEL_DATA in selection.options:
        same = getattr(source, "PixelData", None) == getattr(candidate, "PixelData", None)
        operational.append(
            {
                "option": ProfileOption.CLEAN_PIXEL_DATA.value,
                "status": "review" if same else "pass",
                "reason": "Pixel data is unchanged; confirm that no identifying text was present"
                if same
                else "Pixel data changed; inspect the affected regions",
            }
        )
    if ProfileOption.CLEAN_RECOGNIZABLE_VISUAL_FEATURES in selection.options:
        operational.append(
            {
                "option": ProfileOption.CLEAN_RECOGNIZABLE_VISUAL_FEATURES.value,
                "status": "review",
                "reason": "Recognizable visual features require modality-specific visual or algorithmic review",
            }
        )

    counts = {name: sum(item.status == name for item in results) for name in ("pass", "review", "fail")}
    counts["total"] = len(results)
    counts["operational_pass"] = sum(item.get("status") == "pass" for item in operational)
    counts["operational_review"] = sum(item.get("status") == "review" for item in operational)
    counts["operational_fail"] = sum(item.get("status") == "fail" for item in operational)
    metadata = table_metadata()
    return ProfileEvaluation(
        standard=metadata["standard"],
        edition=metadata["edition"],
        table=metadata["table"],
        selection=selection.to_dict(),
        source=str(source_path) if disclose_paths else _safe_ref(source_path),
        candidate=str(candidate_path) if disclose_paths else _safe_ref(candidate_path),
        results=results,
        operational_checks=operational,
        summary=counts,
        iod_summary=iod_summary,
    )
