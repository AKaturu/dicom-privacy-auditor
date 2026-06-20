from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset

from .audit import _tag_string, audit_dataset, walk_dataset
from .detectors import evidence_preview, fingerprint, is_nonempty, normalize_value
from .models import AuditReport, Finding
from .pixel import patch_similarity
from .profiles import DATE_TIME_KEYWORDS, DIRECT_IDENTIFIER_KEYWORDS, FREE_TEXT_KEYWORDS, SAFE_UID_KEYWORDS


def _elements_by_path(dataset: Dataset) -> dict[str, DataElement]:
    return {path: element for path, element in walk_dataset(dataset)}


def _all_values(dataset: Dataset) -> dict[str, list[str]]:
    values: dict[str, list[str]] = defaultdict(list)
    for path, element in walk_dataset(dataset):
        if element.VR == "SQ" or not is_nonempty(element):
            continue
        values[normalize_value(element.value)].append(path)
    return values


def compare_datasets(
    source: Dataset,
    candidate: Dataset,
    *,
    source_name: str = "<source>",
    candidate_name: str = "<candidate>",
    show_values: bool = False,
    show_source_paths: bool = False,
    include_standalone_findings: bool = True,
) -> AuditReport:
    report = (
        audit_dataset(
            candidate,
            source=candidate_name,
            include_dates=False,
            include_uid_review=False,
            inspect_pixels=False,
            show_values=show_values,
            show_source_paths=show_source_paths,
        )
        if include_standalone_findings
        else AuditReport(
            source=(
                candidate_name
                if show_source_paths
                else f"<redacted-source:{fingerprint(Path(candidate_name).name)}>"
            ),
            readable=True,
        )
    )
    candidate_by_path = _elements_by_path(candidate)
    candidate_values = _all_values(candidate)

    for path, source_element in walk_dataset(source):
        if source_element.VR == "SQ" or not is_nonempty(source_element):
            continue
        value = normalize_value(source_element.value)
        source_sensitive = (
            source_element.keyword in DIRECT_IDENTIFIER_KEYWORDS
            or source_element.keyword in FREE_TEXT_KEYWORDS
            or source_element.tag.is_private
        )
        if source_sensitive and value in candidate_values:
            report.findings.append(
                Finding(
                    code="SOURCE_VALUE_RETAINED",
                    severity="critical" if source_element.keyword in {"PatientName", "PatientID"} else "high",
                    category="paired-comparison",
                    message=f"A source value from {source_element.name} remains in the candidate dataset.",
                    path=path,
                    tag=_tag_string(source_element),
                    keyword=source_element.keyword or None,
                    value_preview=evidence_preview(value, show_values=show_values),
                    value_hash=fingerprint(value),
                    value_length=len(value),
                    recommendation="Remove or transform the retained source value and re-run paired comparison.",
                    evidence={"candidate_paths": candidate_values[value]},
                )
            )

        candidate_element = candidate_by_path.get(path)
        if candidate_element is None or not is_nonempty(candidate_element):
            continue
        candidate_value = normalize_value(candidate_element.value)
        if (
            source_element.keyword in DATE_TIME_KEYWORDS or source_element.VR in {"DA", "DT", "TM"}
        ) and value == candidate_value:
            report.findings.append(
                Finding(
                    code="SOURCE_DATE_UNCHANGED",
                    severity="high",
                    category="paired-comparison",
                    message=f"{source_element.name} is unchanged from the source dataset.",
                    path=path,
                    tag=_tag_string(source_element),
                    keyword=source_element.keyword or None,
                    value_preview=evidence_preview(value, show_values=show_values),
                    value_hash=fingerprint(value),
                    value_length=len(value),
                    recommendation="Remove or consistently shift temporal information unless retention is explicitly intended.",
                )
            )
        if (
            source_element.VR == "UI"
            and source_element.keyword not in SAFE_UID_KEYWORDS
            and value == candidate_value
        ):
            report.findings.append(
                Finding(
                    code="SOURCE_UID_UNCHANGED",
                    severity="high",
                    category="paired-comparison",
                    message=f"{source_element.name} is unchanged from the source dataset.",
                    path=path,
                    tag=_tag_string(source_element),
                    keyword=source_element.keyword or None,
                    value_preview=evidence_preview(value, show_values=show_values),
                    value_hash=fingerprint(value),
                    value_length=len(value),
                    recommendation="Consistently remap instance-level UIDs unless the Retain UIDs Option is explicitly intended.",
                )
            )

    if "PixelData" in source and "PixelData" in candidate:
        try:
            source_pixels = np.asarray(source.pixel_array)
            candidate_pixels = np.asarray(candidate.pixel_array)
            if source_pixels.shape == candidate_pixels.shape:
                similarity = patch_similarity(source_pixels, candidate_pixels)
                if similarity >= 0.9999 and normalize_value(
                    getattr(source, "BurnedInAnnotation", "")
                ).upper() in {"YES", "Y"}:
                    report.findings.append(
                        Finding(
                            code="PIXEL_DATA_UNCHANGED_WITH_ANNOTATION_RISK",
                            severity="critical",
                            category="paired-comparison",
                            message="Pixel data is effectively unchanged despite a source burned-in-annotation risk flag.",
                            path="root/PixelData",
                            recommendation="Apply validated pixel cleaning and visually verify the output.",
                            evidence={"normalized_correlation": similarity},
                        )
                    )
        except Exception as exc:
            report.findings.append(
                Finding(
                    code="PAIRED_PIXEL_COMPARISON_UNAVAILABLE",
                    severity="low",
                    category="paired-comparison",
                    message=f"Pixel comparison could not be completed: {type(exc).__name__}.",
                    path="root/PixelData",
                    recommendation="Decode both objects with a supported transfer syntax and perform visual review.",
                )
            )

    if show_source_paths:
        paired_source = source_name
        paired_candidate = candidate_name
    else:
        paired_source = f"<redacted-source:{fingerprint(Path(source_name).name)}>"
        paired_candidate = f"<redacted-source:{fingerprint(Path(candidate_name).name)}>"
    report.metadata.update({"paired_source": paired_source, "paired_candidate": paired_candidate})
    return report


def compare_files(
    source_path: str | Path,
    candidate_path: str | Path,
    *,
    force: bool = False,
    show_values: bool = False,
    show_source_paths: bool = False,
) -> AuditReport:
    source_path = Path(source_path)
    candidate_path = Path(candidate_path)
    try:
        source = pydicom.dcmread(source_path, force=force)
        candidate = pydicom.dcmread(candidate_path, force=force)
    except Exception as exc:
        return AuditReport(
            source=(
                str(candidate_path)
                if show_source_paths
                else f"<redacted-source:{fingerprint(candidate_path.name)}>"
            ),
            readable=False,
            error=f"{type(exc).__name__}: {exc}",
            metadata={
                "paired_source": (
                    str(source_path)
                    if show_source_paths
                    else f"<redacted-source:{fingerprint(source_path.name)}>"
                )
            },
        )
    return compare_datasets(
        source,
        candidate,
        source_name=str(source_path),
        candidate_name=str(candidate_path),
        show_values=show_values,
        show_source_paths=show_source_paths,
    )
