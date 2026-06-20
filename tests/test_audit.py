from pathlib import Path

from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from dicom_privacy_auditor.audit import audit_dataset


def codes(report):
    return [finding.code for finding in report.findings]


def test_detects_direct_identifiers():
    ds = Dataset()
    ds.PatientName = "DOE^JANE"
    ds.PatientID = "12345"
    report = audit_dataset(ds)
    assert codes(report).count("DIRECT_IDENTIFIER_PRESENT") == 2
    assert "IDENTITY_REMOVAL_NOT_DECLARED" in codes(report)
    assert report.highest_severity == "critical"


def test_detects_nested_identifier():
    item = Dataset()
    item.PatientID = "NESTED-123"
    ds = Dataset()
    ds.OtherPatientIDsSequence = Sequence([item])
    report = audit_dataset(ds)
    assert any(f.keyword == "PatientID" and "[0]" in (f.path or "") for f in report.findings)


def test_detects_private_attribute():
    ds = Dataset()
    block = ds.private_block(0x0011, "TEST_CREATOR", create=True)
    block.add_new(0x01, "LO", "secret")
    report = audit_dataset(ds)
    assert "PRIVATE_ATTRIBUTE_PRESENT" in codes(report)


def test_detects_identifier_pattern_in_free_text():
    ds = Dataset()
    ds.StudyDescription = "Contact patient at jane@example.org"
    report = audit_dataset(ds)
    assert "FREE_TEXT_REVIEW" in codes(report)
    assert "IDENTIFIER_PATTERN_IN_TEXT" in codes(report)


def test_filename_review():
    ds = Dataset()
    report = audit_dataset(ds, source=str(Path("DOE_JANE_CT.dcm")))
    assert "FILENAME_REVIEW" in codes(report)


def test_pixel_status_unknown():
    ds = Dataset()
    ds.PixelData = b"\x00\x01"
    report = audit_dataset(ds)
    assert "PIXEL_STATUS_UNCONFIRMED" in codes(report)


def test_declared_deidentification_without_method_is_flagged():
    ds = Dataset()
    ds.PatientIdentityRemoved = "YES"
    report = audit_dataset(ds)
    assert "IDENTITY_REMOVAL_NOT_DECLARED" not in codes(report)
    assert "DEIDENTIFICATION_METHOD_UNDOCUMENTED" in codes(report)
