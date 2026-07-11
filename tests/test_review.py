from __future__ import annotations

import json

from dicom_privacy_auditor.review.models import ReviewDecision
from dicom_privacy_auditor.review.render import render_frame
from dicom_privacy_auditor.review.store import ReviewStore, metadata_diff


def test_review_store_decisions_export_and_agreement(tmp_path, review_dicom_writer):
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    review_dicom_writer(source / "case.dcm", patient="PHI")
    review_dicom_writer(candidate / "case.dcm", patient="")
    database = tmp_path / "review.sqlite"
    store = ReviewStore(database)
    assert store.initialize(source, candidate) == 1
    case = store.list_cases()[0]
    assert metadata_diff(case.source_path, case.candidate_path)
    assert render_frame(case.source_path).size == (2, 2)
    for reviewer in ("a", "b"):
        store.add_decision(ReviewDecision(None, case.case_id, reviewer, "case", "whole", "false_positive"))
    report = store.agreement("a", "b")
    assert report.exact_agreement == 1.0
    assert report.cohen_kappa is None  # both reviewers used one constant label
    output = tmp_path / "export.json"
    store.export(output)
    payload = json.loads(output.read_text())
    assert payload["cases"][0]["source_path"] == "redacted"
    assert payload["summary"]["cases"] == 1


def test_review_disagreement_packet_integrity_and_permissions(tmp_path, review_dicom_writer):
    import os
    import stat

    from dicom_privacy_auditor.jsonio import validate_json_file

    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    review_dicom_writer(source / "case.dcm", patient="PHI")
    review_dicom_writer(candidate / "case.dcm", patient="")
    database = tmp_path / "review.sqlite"
    store = ReviewStore(database)
    assert store.initialize(source, candidate) == 1
    case = store.list_cases()[0]
    store.add_decision(
        ReviewDecision(None, case.case_id, "reviewer-a", "metadata", "PatientID", "confirmed_identifier")
    )
    store.add_decision(
        ReviewDecision(None, case.case_id, "reviewer-b", "metadata", "PatientID", "false_positive")
    )
    store.add_decision(
        ReviewDecision(None, case.case_id, "reviewer-a", "pixel", "burned-in", "false_positive")
    )
    packet = store.disagreement_report("reviewer-a", "reviewer-b")
    assert packet["summary"] == {
        "disagreement": 1,
        "unmatched_a": 1,
        "unmatched_b": 0,
        "items_requiring_adjudication": 2,
    }
    assert [item["state"] for item in packet["items"]] == ["disagreement", "unmatched_a"]
    output = tmp_path / "disagreements.json"
    store.export_disagreements(output, "reviewer-a", "reviewer-b")
    validate_json_file(output, "review-disagreements")
    integrity = store.integrity_check()
    assert integrity["ok"] is True
    assert integrity["quick_check"] == ["ok"]
    if os.name == "posix":
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
        assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_agreement_uses_latest_decision_per_target(tmp_path, review_dicom_writer):
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    review_dicom_writer(source / "case.dcm")
    review_dicom_writer(candidate / "case.dcm")
    store = ReviewStore(tmp_path / "review.sqlite")
    store.initialize(source, candidate)
    case_id = store.list_cases()[0].case_id
    store.add_decision(
        ReviewDecision(
            None,
            case_id,
            "a",
            "case",
            "whole",
            "confirmed_identifier",
            created_at="2026-01-01T00:00:00+00:00",
        )
    )
    store.add_decision(
        ReviewDecision(
            None,
            case_id,
            "a",
            "case",
            "whole",
            "false_positive",
            created_at="2026-01-02T00:00:00+00:00",
        )
    )
    store.add_decision(
        ReviewDecision(
            None,
            case_id,
            "b",
            "case",
            "whole",
            "false_positive",
            created_at="2026-01-01T00:00:00+00:00",
        )
    )
    assert store.agreement("a", "b").exact_agreement == 1.0


def test_review_store_does_not_create_missing_database(tmp_path):
    import pytest

    database = tmp_path / "missing.sqlite"
    store = ReviewStore(database)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        store.list_cases()
    assert not database.exists()


def test_metadata_diff_accepts_none_sequence_values(monkeypatch):
    from pydicom.dataset import Dataset

    dataset = Dataset()
    dataset.add_new((0x0040, 0xA730), "SQ", [])
    dataset[(0x0040, 0xA730)]._value = None
    monkeypatch.setattr(
        "dicom_privacy_auditor.review.store.pydicom.dcmread",
        lambda *args, **kwargs: dataset,
    )

    assert metadata_diff("source.dcm", "candidate.dcm") == []
