from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from pydicom.dataset import Dataset

from .models import IodAttribute, IodEvaluationSummary
from .registry import attributes_for_sop, resolve_context


def tag_path_index(dataset: Dataset) -> dict[str, Any]:
    output: dict[str, Any] = {}

    def walk(ds: Dataset, prefix: tuple[str, ...] = ()) -> None:
        for element in ds:
            tag = f"{int(element.tag):08X}"
            current = (*prefix, tag)
            output["/".join(current)] = element
            if element.VR == "SQ":
                for item in element.value:
                    walk(item, current)

    walk(dataset)
    return output


def _registry_index(attributes: list[IodAttribute]) -> dict[str, list[IodAttribute]]:
    output: dict[str, list[IodAttribute]] = defaultdict(list)
    for item in attributes:
        output["/".join(item.path)].append(item)
    return output


def type_constraints(type_value: str | None, source_present: bool) -> dict[str, Any]:
    normalized = (type_value or "3").upper()
    conditional = normalized.endswith("C")
    base = normalized.rstrip("C")
    condition_assumed_true = conditional and source_present
    if base == "1" and (not conditional or condition_assumed_true):
        return {
            "may_remove": False,
            "may_zero": False,
            "requires_nonempty": True,
            "condition": "true" if conditional else "n/a",
        }
    if base == "2" and (not conditional or condition_assumed_true):
        return {
            "may_remove": False,
            "may_zero": True,
            "requires_nonempty": False,
            "condition": "true" if conditional else "n/a",
        }
    if conditional:
        return {"may_remove": True, "may_zero": True, "requires_nonempty": False, "condition": "unresolved"}
    return {"may_remove": True, "may_zero": True, "requires_nonempty": False, "condition": "n/a"}


def iod_context_for_pair(
    source: Dataset,
    candidate: Dataset,
    *,
    registry_path: str | Path | None = None,
) -> tuple[IodEvaluationSummary, dict[str, dict[str, Any]]]:
    sop_uid = str(getattr(source, "SOPClassUID", getattr(candidate, "SOPClassUID", "")))
    context = resolve_context(sop_uid, path=registry_path)
    summary = IodEvaluationSummary(context=context)
    if not context.resolved:
        summary.notes.append("SOP Class UID was not found in the local IOD registry")
        return summary, {}
    source_index = tag_path_index(source)
    candidate_index = tag_path_index(candidate)
    definitions = _registry_index(attributes_for_sop(sop_uid, path=registry_path))
    contextual: dict[str, dict[str, Any]] = {}
    all_paths = set(source_index) | set(candidate_index)
    for path in all_paths:
        rules = definitions.get(path, [])
        if not rules:
            summary.undefined_attributes += 1
            contextual[path] = {
                "defined_in_active_iod": False,
                "expected_iod_action": "X",
                "reason": "attribute path is not defined in the active IOD registry",
            }
            continue
        summary.defined_attributes += 1
        source_present = path in source_index
        chosen = sorted(
            rules, key=lambda item: ({"M": 0, "C": 1, "U": 2}.get(item.module_usage, 3), item.type or "9")
        )[0]
        type_value = (chosen.type or "3").upper()
        if type_value == "1":
            summary.type_1 += 1
        elif type_value == "1C":
            summary.type_1c += 1
        elif type_value == "2":
            summary.type_2 += 1
        elif type_value == "2C":
            summary.type_2c += 1
        else:
            summary.type_3 += 1
        constraints = type_constraints(type_value, source_present)
        if constraints["condition"] == "unresolved":
            summary.unresolved_conditions += 1
        contextual[path] = {
            "defined_in_active_iod": True,
            "module_id": chosen.module_id,
            "module_usage": chosen.module_usage,
            "attribute_type": type_value,
            "conditional_statement": chosen.conditional_statement,
            **constraints,
        }
    return summary, contextual
