from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from dicom_privacy_auditor.review.store import ReviewStore
from dicom_privacy_auditor.review_app import parse_region

APP_PATH = Path(__file__).parents[1] / "src" / "dicom_privacy_auditor" / "review_app.py"


def _element_with_label(elements, label: str):
    return next(element for element in elements if element.label == label)


def test_parse_region_validates_shape_and_bounds() -> None:
    assert parse_region("") is None
    assert parse_region("1, 2, 5, 8") == (1, 2, 5, 8)
    with pytest.raises(ValueError, match="four comma-separated"):
        parse_region("1,2,3")
    with pytest.raises(ValueError, match="nonnegative"):
        parse_region("-1,2,5,8")
    with pytest.raises(ValueError, match="x2 > x1"):
        parse_region("5,2,5,8")


def test_review_app_explains_missing_database(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DICOM_PRIVACY_REVIEW_DB", str(tmp_path / "missing.sqlite"))

    app = AppTest.from_file(str(APP_PATH), default_timeout=10).run()

    assert not app.exception
    assert any("Create a review database" in item.value for item in app.info)


def test_review_app_loads_case_and_saves_decision(
    monkeypatch,
    tmp_path,
    review_dicom_writer,
) -> None:
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    review_dicom_writer(source / "case.dcm", patient="PHI")
    review_dicom_writer(candidate / "case.dcm", patient="")
    database = tmp_path / "review.sqlite"
    ReviewStore(database).initialize(source, candidate)
    monkeypatch.setenv("DICOM_PRIVACY_REVIEW_DB", str(database))
    monkeypatch.setenv("DICOM_PRIVACY_REVIEW_BLINDED", "1")

    app = AppTest.from_file(str(APP_PATH), default_timeout=10).run()

    assert not app.exception
    assert [item.value for item in app.subheader] == ["Source", "Candidate"]
    _element_with_label(app.button, "Save decision").click().run()
    assert not app.exception
    assert any("Saved decision" in item.value for item in app.success)
    decisions = ReviewStore(database).decisions(reviewer="reviewer-1")
    assert len(decisions) == 1
    assert decisions[0].scope == "case"
    assert decisions[0].target == "whole-case"
    assert decisions[0].status == "confirmed_identifier"
