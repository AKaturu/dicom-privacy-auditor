from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pydicom
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset
from pydicom.errors import InvalidDicomError

from .detectors import (
    evidence_preview,
    filename_risk,
    fingerprint,
    is_nonempty,
    normalize_value,
    suspicious_text_patterns,
)
from .models import AuditReport, Finding
from .pixel import scan_text_like_border
from .profiles import (
    DATE_TIME_KEYWORDS,
    DIRECT_IDENTIFIER_KEYWORDS,
    FREE_TEXT_KEYWORDS,
    GRAPHIC_OR_EMBEDDED_KEYWORDS,
    PIXEL_RISK_FLAGS,
    SAFE_UID_KEYWORDS,
)


def _tag_string(element: DataElement) -> str:
    return f"({element.tag.group:04X},{element.tag.element:04X})"


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def walk_dataset(dataset: Dataset, prefix: str = "root") -> Iterator[tuple[str, DataElement]]:
    """Yield all elements and preserve sequence-item paths."""
    for element in dataset:
        element_path = f"{prefix}/{element.keyword or _tag_string(element)}"
        yield element_path, element
        if element.VR == "SQ":
            for index, item in enumerate(element.value):
                yield from walk_dataset(item, f"{element_path}[{index}]")


def _value_evidence(value: object, *, show_values: bool) -> dict[str, Any]:
    text = normalize_value(value)
    return {
        "value_preview": evidence_preview(value, show_values=show_values),
        "value_hash": fingerprint(value),
        "value_length": len(text) if text else 0,
    }


def _finding_for_identifier(path: str, element: DataElement, *, show_values: bool) -> Finding | None:
    if element.keyword not in DIRECT_IDENTIFIER_KEYWORDS or not is_nonempty(element):
        return None
    severity, rationale = DIRECT_IDENTIFIER_KEYWORDS[element.keyword]
    return Finding(
        code="DIRECT_IDENTIFIER_PRESENT",
        severity=severity,
        category="metadata",
        message=f"{element.name} is populated: {rationale}.",
        path=path,
        tag=_tag_string(element),
        keyword=element.keyword or None,
        recommendation="Remove, replace, or transform this attribute under the applicable de-identification profile.",
        **_value_evidence(element.value, show_values=show_values),
    )


def _findings_for_element(
    path: str,
    element: DataElement,
    *,
    include_dates: bool,
    include_uid_review: bool,
    show_values: bool,
) -> list[Finding]:
    findings: list[Finding] = []

    direct = _finding_for_identifier(path, element, show_values=show_values)
    if direct:
        findings.append(direct)

    if element.tag.is_private:
        findings.append(
            Finding(
                code="PRIVATE_ATTRIBUTE_PRESENT",
                severity="high",
                category="private-tag",
                message="Private DICOM attribute is present; its semantics may be vendor-specific.",
                path=path,
                tag=_tag_string(element),
                keyword=element.keyword or None,
                recommendation="Review the private creator and remove private attributes unless specifically justified.",
                **_value_evidence(element.value, show_values=show_values),
            )
        )

    if element.keyword in FREE_TEXT_KEYWORDS and is_nonempty(element):
        text = normalize_value(element.value)
        findings.append(
            Finding(
                code="FREE_TEXT_REVIEW",
                severity="medium",
                category="free-text",
                message=f"{element.name} is free text and may contain identifying information.",
                path=path,
                tag=_tag_string(element),
                keyword=element.keyword,
                recommendation="Review or sanitize free text before data release.",
                **_value_evidence(element.value, show_values=show_values),
            )
        )
        patterns = suspicious_text_patterns(text)
        if patterns:
            findings.append(
                Finding(
                    code="IDENTIFIER_PATTERN_IN_TEXT",
                    severity="high",
                    category="free-text",
                    message="Free text contains: " + ", ".join(patterns) + ".",
                    path=path,
                    tag=_tag_string(element),
                    keyword=element.keyword,
                    recommendation="Remove or replace the detected identifier before release.",
                    evidence={"patterns": patterns},
                    **_value_evidence(element.value, show_values=show_values),
                )
            )

    if (
        include_dates
        and (element.keyword in DATE_TIME_KEYWORDS or element.VR in {"DA", "DT", "TM"})
        and is_nonempty(element)
    ):
        findings.append(
            Finding(
                code="DATE_TIME_PRESENT",
                severity="medium",
                category="temporal",
                message=f"{element.name} is populated and may permit longitudinal linkage.",
                path=path,
                tag=_tag_string(element),
                keyword=element.keyword or None,
                recommendation="Apply the project-specific date retention, removal, or shifting policy consistently.",
                **_value_evidence(element.value, show_values=show_values),
            )
        )

    if (
        include_uid_review
        and element.VR == "UI"
        and element.keyword not in SAFE_UID_KEYWORDS
        and is_nonempty(element)
    ):
        findings.append(
            Finding(
                code="UID_REVIEW",
                severity="low",
                category="linkage",
                message=f"{element.name} is an instance-level UID that may permit linkage to source data.",
                path=path,
                tag=_tag_string(element),
                keyword=element.keyword or None,
                recommendation="Verify that the UID was consistently remapped unless the Retain UIDs Option is intended.",
                **_value_evidence(element.value, show_values=show_values),
            )
        )

    if element.keyword in PIXEL_RISK_FLAGS and normalize_value(element.value).upper() in {"YES", "Y"}:
        findings.append(
            Finding(
                code="PIXEL_REVIEW_REQUIRED",
                severity="critical",
                category="pixel-data",
                message=PIXEL_RISK_FLAGS[element.keyword] + ".",
                path=path,
                tag=_tag_string(element),
                keyword=element.keyword,
                recommendation="Perform validated pixel-level inspection or cleaning before release.",
                **_value_evidence(element.value, show_values=show_values),
            )
        )

    if element.keyword in GRAPHIC_OR_EMBEDDED_KEYWORDS and is_nonempty(element):
        severity, rationale = GRAPHIC_OR_EMBEDDED_KEYWORDS[element.keyword]
        findings.append(
            Finding(
                code="EMBEDDED_CONTENT_REVIEW",
                severity=severity,
                category="embedded-content",
                message=rationale + ".",
                path=path,
                tag=_tag_string(element),
                keyword=element.keyword,
                recommendation="Apply object-specific cleaning or remove the content before release.",
                **_value_evidence(element.value, show_values=False),
            )
        )

    if element.tag.group == 0x0004:
        findings.append(
            Finding(
                code="DIRECTORY_RECORD_ATTRIBUTE_PRESENT",
                severity="high",
                category="filesystem",
                message="A group 0004 directory/file-set attribute is present outside a dedicated DICOMDIR review.",
                path=path,
                tag=_tag_string(element),
                keyword=element.keyword or None,
                recommendation="Remove group 0004 elements from ordinary SOP Instances and rebuild DICOMDIR from de-identified files.",
            )
        )

    return findings


def audit_dataset(
    dataset: Dataset,
    *,
    source: str = "<memory>",
    include_dates: bool = True,
    include_uid_review: bool = False,
    inspect_filename: bool = True,
    inspect_pixels: bool = False,
    show_values: bool = False,
    show_source_paths: bool = False,
) -> AuditReport:
    findings: list[Finding] = []

    source_id = fingerprint(Path(source).name) if source else None
    report_source = (
        source if show_source_paths or source in {"", "<memory>"} else f"<redacted-source:{source_id}>"
    )
    if inspect_filename and source not in {"", "<memory>"}:
        reason = filename_risk(Path(source))
        if reason:
            findings.append(
                Finding(
                    code="FILENAME_REVIEW",
                    severity="high",
                    category="filesystem",
                    message=reason + ".",
                    path=str(source) if show_source_paths else report_source,
                    recommendation="Rename exported files using a non-identifying UID, hash, or sequence number.",
                    value_hash=fingerprint(Path(source).name),
                    value_length=len(Path(source).name),
                    value_preview=(Path(source).name if show_values else "<redacted filename>"),
                )
            )

    for path, element in walk_dataset(dataset):
        findings.extend(
            _findings_for_element(
                path,
                element,
                include_dates=include_dates,
                include_uid_review=include_uid_review,
                show_values=show_values,
            )
        )

    file_meta = getattr(dataset, "file_meta", None)
    if file_meta:
        for path, element in walk_dataset(file_meta, prefix="file_meta"):
            if element.keyword in {
                "SourceApplicationEntityTitle",
                "SendingApplicationEntityTitle",
                "ReceivingApplicationEntityTitle",
            } and is_nonempty(element):
                findings.append(
                    Finding(
                        code="FILE_META_IDENTITY_PRESENT",
                        severity="high",
                        category="file-meta",
                        message=f"{element.name} may disclose an originating system or organization.",
                        path=path,
                        tag=_tag_string(element),
                        keyword=element.keyword,
                        recommendation="Replace File Meta Information with values identifying the de-identifying application.",
                        **_value_evidence(element.value, show_values=show_values),
                    )
                )

    preamble = getattr(dataset, "preamble", None)
    if preamble and any(preamble):
        findings.append(
            Finding(
                code="NONZERO_PREAMBLE_REVIEW",
                severity="medium",
                category="file-meta",
                message="The 128-byte DICOM preamble contains non-zero data.",
                path="preamble",
                recommendation="Replace the preamble during de-identification and verify no application-specific content remains.",
                value_hash=hashlib.sha256(bytes(preamble)).hexdigest()[:12],
                value_length=len(preamble),
                value_preview="<redacted binary preamble>",
            )
        )

    identity_removed = normalize_value(getattr(dataset, "PatientIdentityRemoved", "")).upper()
    if identity_removed != "YES":
        findings.append(
            Finding(
                code="IDENTITY_REMOVAL_NOT_DECLARED",
                severity="high",
                category="conformance-indicator",
                message="PatientIdentityRemoved is absent or not set to YES.",
                path="root/PatientIdentityRemoved",
                tag="(0012,0062)",
                keyword="PatientIdentityRemoved",
                value_preview=identity_removed or "<missing>",
                value_hash=fingerprint(identity_removed),
                value_length=len(identity_removed),
                recommendation="For a claimed de-identified export, document identity removal in the DICOM dataset.",
            )
        )
    else:
        method = normalize_value(getattr(dataset, "DeidentificationMethod", ""))
        method_codes = getattr(dataset, "DeidentificationMethodCodeSequence", None)
        if not method and not method_codes:
            findings.append(
                Finding(
                    code="DEIDENTIFICATION_METHOD_UNDOCUMENTED",
                    severity="medium",
                    category="conformance-indicator",
                    message="Identity removal is declared, but no de-identification method is documented.",
                    path="root",
                    recommendation="Populate DeidentificationMethod or DeidentificationMethodCodeSequence as appropriate.",
                )
            )

    has_pixel_data = "PixelData" in dataset
    burned_flag = normalize_value(getattr(dataset, "BurnedInAnnotation", "")).upper()
    recognizable_flag = normalize_value(getattr(dataset, "RecognizableVisualFeatures", "")).upper()
    if has_pixel_data and burned_flag not in {"NO", "N"}:
        findings.append(
            Finding(
                code="PIXEL_STATUS_UNCONFIRMED",
                severity="medium" if burned_flag == "" else "high",
                category="pixel-data",
                message="Pixel data is present and absence of burned-in identifiers is not explicitly established.",
                path="root/PixelData",
                tag="(7FE0,0010)",
                keyword="PixelData",
                recommendation="Use a validated visual or OCR-assisted pixel review workflow before release.",
            )
        )
    if has_pixel_data and recognizable_flag == "":
        findings.append(
            Finding(
                code="VISUAL_FEATURE_STATUS_UNKNOWN",
                severity="low",
                category="pixel-data",
                message="RecognizableVisualFeatures is not populated.",
                path="root",
                recommendation="Determine whether facial or other recognizable anatomy requires a dedicated cleaning step.",
            )
        )

    if inspect_pixels and has_pixel_data:
        scan = scan_text_like_border(dataset)
        if not scan.analyzable:
            findings.append(
                Finding(
                    code="PIXEL_SCAN_UNAVAILABLE",
                    severity="low",
                    category="pixel-data",
                    message=scan.reason or "Pixel data could not be analyzed.",
                    path="root/PixelData",
                    recommendation="Use a decoder compatible with the transfer syntax and perform visual review.",
                )
            )
        elif scan.suspicious:
            findings.append(
                Finding(
                    code="PIXEL_TEXT_LIKE_REGION",
                    severity="high",
                    category="pixel-data",
                    message="Experimental scan found a dense high-contrast border region compatible with burned-in annotation.",
                    path="root/PixelData",
                    recommendation="Visually inspect and, when appropriate, redact the indicated region using a validated workflow.",
                    evidence={"edge_density": scan.score, "bbox_xyxy": scan.bbox},
                )
            )

    sop_instance = normalize_value(getattr(dataset, "SOPInstanceUID", ""))
    transfer_syntax = None
    if file_meta:
        transfer_syntax = normalize_value(getattr(file_meta, "TransferSyntaxUID", "")) or None
    return AuditReport(
        source=report_source,
        source_id=source_id,
        readable=True,
        sop_class_uid=normalize_value(getattr(dataset, "SOPClassUID", "")) or None,
        sop_instance_uid_hash=fingerprint(sop_instance),
        modality=normalize_value(getattr(dataset, "Modality", "")) or None,
        transfer_syntax_uid=transfer_syntax,
        findings=findings,
        metadata={"show_values": show_values, "pixel_scan": inspect_pixels},
    )


def audit_file(
    path: str | Path,
    *,
    force: bool = False,
    include_dates: bool = True,
    include_uid_review: bool = False,
    inspect_pixels: bool = False,
    show_values: bool = False,
    show_source_paths: bool = False,
) -> AuditReport:
    path = Path(path)
    try:
        dataset = pydicom.dcmread(path, force=force)
    except (InvalidDicomError, OSError, ValueError, KeyError) as exc:
        return AuditReport(
            source=str(path) if show_source_paths else f"<redacted-source:{fingerprint(path.name)}>",
            source_id=fingerprint(path.name),
            file_sha256=_sha256_file(path),
            readable=False,
            error=f"{type(exc).__name__}: {exc}",
        )
    report = audit_dataset(
        dataset,
        source=str(path),
        include_dates=include_dates,
        include_uid_review=include_uid_review,
        inspect_pixels=inspect_pixels,
        show_values=show_values,
        show_source_paths=show_source_paths,
    )
    report.file_sha256 = _sha256_file(path)
    return report


def _candidate_files(path: Path) -> Iterator[Path]:
    if path.is_file():
        yield path
        return
    for candidate in sorted(path.rglob("*")):
        if candidate.is_file() and not candidate.name.startswith("."):
            yield candidate


def audit_path(
    path: str | Path,
    *,
    force: bool = False,
    include_dates: bool = True,
    include_uid_review: bool = False,
    inspect_pixels: bool = False,
    show_values: bool = False,
    show_source_paths: bool = False,
) -> list[AuditReport]:
    root = Path(path)
    return [
        audit_file(
            candidate,
            force=force,
            include_dates=include_dates,
            include_uid_review=include_uid_review,
            inspect_pixels=inspect_pixels,
            show_values=show_values,
            show_source_paths=show_source_paths,
        )
        for candidate in _candidate_files(root)
    ]


def reports_to_json(reports: list[AuditReport], *, indent: int = 2) -> str:
    return json.dumps([report.to_dict() for report in reports], indent=indent)
