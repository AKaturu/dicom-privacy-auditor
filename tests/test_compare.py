from pydicom.dataset import Dataset

from dicom_privacy_auditor.compare import compare_datasets


def finding_codes(report):
    return {finding.code for finding in report.findings}


def test_compare_detects_retained_identifier_date_and_uid():
    source = Dataset()
    source.PatientName = "DOE^JANE"
    source.StudyDate = "20200101"
    source.StudyInstanceUID = "2.25.123"

    candidate = Dataset()
    candidate.PatientName = "DOE^JANE"
    candidate.StudyDate = "20200101"
    candidate.StudyInstanceUID = "2.25.123"

    codes = finding_codes(compare_datasets(source, candidate, include_standalone_findings=False))
    assert "SOURCE_VALUE_RETAINED" in codes
    assert "SOURCE_DATE_UNCHANGED" in codes
    assert "SOURCE_UID_UNCHANGED" in codes


def test_compare_does_not_flag_changed_values():
    source = Dataset()
    source.PatientName = "DOE^JANE"
    source.StudyDate = "20200101"
    source.StudyInstanceUID = "2.25.123"

    candidate = Dataset()
    candidate.PatientName = ""
    candidate.StudyDate = ""
    candidate.StudyInstanceUID = "2.25.456"

    codes = finding_codes(compare_datasets(source, candidate, include_standalone_findings=False))
    assert "SOURCE_VALUE_RETAINED" not in codes
    assert "SOURCE_DATE_UNCHANGED" not in codes
    assert "SOURCE_UID_UNCHANGED" not in codes
