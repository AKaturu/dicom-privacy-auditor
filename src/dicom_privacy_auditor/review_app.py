from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import streamlit as st

from dicom_privacy_auditor.review.models import REVIEW_STATUSES, ReviewDecision
from dicom_privacy_auditor.review.render import render_frame
from dicom_privacy_auditor.review.store import ReviewStore, metadata_diff


def parse_region(value: str) -> tuple[int, int, int, int] | None:
    """Parse and validate an optional x1,y1,x2,y2 review region."""
    if not value.strip():
        return None
    try:
        parts = tuple(int(item.strip()) for item in value.split(","))
    except ValueError as exc:
        raise ValueError("Region must contain four comma-separated integers.") from exc
    if len(parts) != 4:
        raise ValueError("Region must contain four comma-separated integers.")
    x1, y1, x2, y2 = parts
    if min(parts) < 0:
        raise ValueError("Region coordinates must be nonnegative.")
    if x2 <= x1 or y2 <= y1:
        raise ValueError("Region must satisfy x2 > x1 and y2 > y1.")
    return x1, y1, x2, y2


def run_app() -> None:
    st.set_page_config(page_title="DICOM Privacy Review", layout="wide")
    st.title("DICOM Privacy Review Workstation")
    st.warning(
        "Local research workstation. It may display identifying source data. "
        "Do not expose it to an untrusted network."
    )

    db_default = os.environ.get("DICOM_PRIVACY_REVIEW_DB", "review.sqlite")
    db_path = Path(st.sidebar.text_input("Review database", db_default)).expanduser()
    reviewer = st.sidebar.text_input("Reviewer code", "reviewer-1")
    blinded = os.environ.get("DICOM_PRIVACY_REVIEW_BLINDED", "1").casefold() not in {
        "0",
        "false",
        "no",
    }
    st.sidebar.caption("Blinded review" if blinded else "Unblinded review")
    if not db_path.is_file():
        st.info("Create a review database with `dicom-privacy-review create`.")
        st.stop()

    store = ReviewStore(db_path)
    try:
        cases = store.list_cases()
    except (OSError, sqlite3.Error, ValueError) as exc:
        st.error(f"Unable to open the review database: {exc}")
        st.stop()
    if not cases:
        st.info("No cases are present.")
        st.stop()

    labels = [
        f"{case.modality or '?'} | {case.case_id}" + ("" if blinded else f" | {case.status}")
        for case in cases
    ]
    selected_label = st.sidebar.selectbox("Case", labels)
    case = cases[labels.index(selected_label)]
    if case.frame_count > 1:
        frame = st.sidebar.slider("Frame", 0, case.frame_count - 1, 0)
    else:
        frame = 0
        st.sidebar.caption("Frame 1 of 1")
    center = st.sidebar.number_input("Window center (0 = automatic)", value=0.0)
    width = st.sidebar.number_input("Window width (0 = automatic)", value=0.0, min_value=0.0)
    render_options = {"window_center": center or None, "window_width": width or None}

    left, right = st.columns(2)
    with left:
        st.subheader("Source")
        try:
            st.image(
                render_frame(case.source_path, frame, **render_options),
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Unable to render source: {exc}")
    with right:
        st.subheader("Candidate")
        try:
            st.image(
                render_frame(case.candidate_path, frame, **render_options),
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Unable to render candidate: {exc}")

    tab_diff, tab_decisions = st.tabs(["Metadata diff", "Adjudication"])
    with tab_diff:
        try:
            rows = metadata_diff(case.source_path, case.candidate_path)
        except Exception as exc:
            st.error(f"Unable to compare metadata: {exc}")
        else:
            states = st.multiselect(
                "States",
                ["changed", "removed", "added", "unchanged"],
                ["changed", "removed", "added"],
            )
            st.dataframe(
                [row for row in rows if row["state"] in states],
                use_container_width=True,
                hide_index=True,
            )

    with tab_decisions:
        scope = st.selectbox("Scope", ["case", "metadata", "pixel", "region"])
        target = st.text_input("Target", "whole-case" if scope == "case" else "")
        status = st.selectbox("Decision", REVIEW_STATUSES)
        comment = st.text_area("Comment")
        region_text = st.text_input("Region x1,y1,x2,y2 (optional)")
        if st.button("Save decision", type="primary"):
            try:
                if not reviewer.strip():
                    raise ValueError("Reviewer code is required.")
                region = parse_region(region_text)
                identifier = store.add_decision(
                    ReviewDecision(
                        None,
                        case.case_id,
                        reviewer,
                        scope,
                        target,
                        status,
                        comment,
                        frame,
                        region,
                    )
                )
            except (OSError, sqlite3.Error, ValueError) as exc:
                st.error(str(exc))
            else:
                st.success(f"Saved decision {identifier}")
        try:
            visible_decisions = store.decisions(
                reviewer=reviewer if blinded else None,
                case_id=case.case_id,
            )
        except (OSError, sqlite3.Error) as exc:
            st.error(f"Unable to load decisions: {exc}")
        else:
            st.dataframe(
                [item.to_dict() for item in visible_decisions],
                use_container_width=True,
            )


if __name__ == "__main__":
    run_app()
