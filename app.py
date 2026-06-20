from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from dicom_privacy_auditor.audit import audit_file
from dicom_privacy_auditor.compare import compare_files

st.set_page_config(page_title="DICOM Privacy Auditor", page_icon="🩻", layout="wide")
st.title("DICOM Privacy Auditor")
st.caption(
    "Research and quality-assurance prototype. It does not certify DICOM PS3.15, HIPAA, GDPR, "
    "or institutional-policy compliance. Zero findings do not prove that an object is safe."
)


def _save_upload(uploaded, directory: Path) -> Path:
    safe_name = Path(uploaded.name).name or "uploaded.dcm"
    target = directory / safe_name
    target.write_bytes(uploaded.getbuffer())
    return target


def _findings_frame(reports) -> pd.DataFrame:
    rows = []
    for report in reports:
        for finding in report.findings:
            rows.append(
                {
                    "file": Path(report.source).name,
                    "severity": finding.severity,
                    "code": finding.code,
                    "category": finding.category,
                    "path": finding.path,
                    "message": finding.message,
                    "evidence": finding.value_preview,
                    "recommendation": finding.recommendation,
                }
            )
    return pd.DataFrame(rows)


audit_tab, compare_tab, about_tab = st.tabs(
    ["Audit files", "Compare source and output", "About the benchmark"]
)

with audit_tab:
    uploads = st.file_uploader("Upload one or more DICOM objects", accept_multiple_files=True, key="audit")
    col1, col2, col3 = st.columns(3)
    include_dates = col1.checkbox("Flag date/time attributes", value=True)
    review_uids = col2.checkbox("Flag instance UIDs for review", value=False)
    pixel_scan = col3.checkbox("Experimental pixel border scan", value=True)
    show_values = st.checkbox(
        "Show raw values (unsafe: may copy identifiers into the browser and downloads)", value=False
    )
    show_source_paths = st.checkbox("Include original filenames in reports (unsafe)", value=False)

    if uploads:
        with tempfile.TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            reports = []
            for upload in uploads:
                path = _save_upload(upload, temp_dir)
                report = audit_file(
                    path,
                    include_dates=include_dates,
                    include_uid_review=review_uids,
                    inspect_pixels=pixel_scan,
                    show_values=show_values,
                    show_source_paths=show_source_paths,
                )
                if show_source_paths:
                    report.source = upload.name
                reports.append(report)

            total = sum(report.finding_count for report in reports)
            highest = max((report.highest_severity for report in reports), default="info")
            unreadable = sum(not report.readable for report in reports)
            left, middle, right = st.columns(3)
            left.metric("Files", len(reports))
            middle.metric("Findings", total)
            right.metric("Unreadable", unreadable)
            st.write(f"Highest severity: **{highest.upper()}**")

            frame = _findings_frame(reports)
            if frame.empty:
                st.success("No configured rules fired. This is not proof that the files are de-identified.")
            else:
                st.dataframe(frame, use_container_width=True, hide_index=True)
            payload = [report.to_dict() for report in reports]
            st.download_button(
                "Download JSON audit",
                data=json.dumps(payload, indent=2),
                file_name="dicom_privacy_audit.json",
                mime="application/json",
            )

with compare_tab:
    source_upload = st.file_uploader("Original/source object", key="source")
    candidate_upload = st.file_uploader("Candidate de-identified object", key="candidate")
    compare_show_values = st.checkbox("Show raw comparison values (unsafe)", value=False, key="compare_raw")
    compare_show_paths = st.checkbox(
        "Include original filenames in comparison report (unsafe)", value=False, key="compare_paths"
    )
    if source_upload and candidate_upload:
        with tempfile.TemporaryDirectory() as temp:
            temp_dir = Path(temp)
            # Separate folders permit two uploads with the same filename.
            source_dir = temp_dir / "source"
            candidate_dir = temp_dir / "candidate"
            source_dir.mkdir()
            candidate_dir.mkdir()
            source_path = _save_upload(source_upload, source_dir)
            candidate_path = _save_upload(candidate_upload, candidate_dir)
            report = compare_files(
                source_path,
                candidate_path,
                show_values=compare_show_values,
                show_source_paths=compare_show_paths,
            )
            if compare_show_paths:
                report.source = candidate_upload.name
            left, middle, right = st.columns(3)
            left.metric("Findings", report.finding_count)
            middle.metric("Risk score", report.risk_score)
            right.metric("Highest severity", report.highest_severity.upper())
            frame = _findings_frame([report])
            if frame.empty:
                st.success("No configured standalone or paired-comparison rules fired.")
            else:
                st.dataframe(frame, use_container_width=True, hide_index=True)
            st.download_button(
                "Download comparison JSON",
                data=json.dumps(report.to_dict(), indent=2),
                file_name="dicom_privacy_comparison.json",
                mime="application/json",
            )

with about_tab:
    st.subheader("What the repository can test")
    st.markdown(
        """
The synthetic benchmark injects artificial identifiers into ten strata:
standard metadata, nested sequences, private attributes, free text, filenames,
dates/times, UIDs, pixel annotations, File Meta Information, and the 128-byte preamble.

The command-line workflow can generate a seeded corpus, run built-in or external
one-file-at-a-time pipelines, evaluate residual identifiers, calculate Wilson 95%
confidence intervals, compare paired workflows with an exact McNemar test, and
produce manuscript-oriented tables and figures.
        """
    )
    st.warning(
        "The pixel detector is an experimental review signal, not OCR. The built-in baseline is a transparent "
        "benchmark comparator, not a production de-identification engine."
    )
