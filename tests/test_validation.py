from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage

from dicom_privacy_auditor.validation import validate_dataset


def test_basic_validation_detects_meta_mismatch():
    ds = Dataset()
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = "2.25.1"
    ds.file_meta = FileMetaDataset()
    ds.file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    ds.file_meta.MediaStorageSOPInstanceUID = "2.25.2"
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    result = validate_dataset(ds)
    assert not result.valid_basic
    assert any("does not match" in error for error in result.errors)
