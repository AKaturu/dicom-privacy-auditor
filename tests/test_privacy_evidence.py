from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage

from dicom_privacy_auditor.audit import audit_dataset
from dicom_privacy_auditor.detectors import normalize_value


def test_person_name_normalization_is_not_character_split():
    ds = Dataset()
    ds.PatientName = "DOE^JANE"
    assert normalize_value(ds.PatientName) == "DOE^JANE"


def test_identifier_values_are_redacted_by_default():
    ds = Dataset()
    ds.PatientName = "DOE^JANE"
    finding = next(f for f in audit_dataset(ds).findings if f.code == "DIRECT_IDENTIFIER_PRESENT")
    assert "DOE" not in (finding.value_preview or "")
    assert finding.value_hash
    assert finding.value_length == 8


def test_identifier_values_can_be_shown_only_when_requested():
    ds = Dataset()
    ds.PatientName = "DOE^JANE"
    finding = next(
        f for f in audit_dataset(ds, show_values=True).findings if f.code == "DIRECT_IDENTIFIER_PRESENT"
    )
    assert finding.value_preview == "DOE^JANE"


def test_nonzero_preamble_and_file_meta_are_flagged(tmp_path):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = "2.25.1"
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    meta.SourceApplicationEntityTitle = "HOSPITAL_AE"
    ds = FileDataset(str(tmp_path / "x.dcm"), {}, file_meta=meta, preamble=b"A" + b"\0" * 127)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = "2.25.1"
    report = audit_dataset(ds)
    codes = {f.code for f in report.findings}
    assert "NONZERO_PREAMBLE_REVIEW" in codes
    assert "FILE_META_IDENTITY_PRESENT" in codes


def test_source_paths_are_redacted_by_default(tmp_path):
    from dicom_privacy_auditor.audit import audit_file
    from dicom_privacy_auditor.benchmark.synthetic import base_dataset

    path = tmp_path / "DOE_JANE_scan.dcm"
    ds = base_dataset(path, "redaction-case")
    ds.save_as(path, enforce_file_format=True)
    safe = audit_file(path)
    unsafe = audit_file(path, show_source_paths=True)
    assert "DOE_JANE" not in safe.source
    assert safe.source.startswith("<redacted-source:")
    assert unsafe.source == str(path)
