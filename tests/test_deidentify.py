from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from dicom_privacy_auditor.deidentify import UIDMapper, baseline_deidentify_dataset


def test_baseline_removes_configured_risks_and_remaps_uids():
    nested = Dataset()
    nested.PatientID = "NESTED-123"
    ds = Dataset()
    ds.PatientName = "DOE^JANE"
    ds.PatientID = "123"
    ds.StudyDate = "20200101"
    ds.StudyDescription = "MRN: 123"
    ds.StudyInstanceUID = "2.25.100"
    ds.RequestAttributesSequence = Sequence([nested])
    block = ds.private_block(0x0011, "TEST", create=True)
    block.add_new(0x01, "LO", "secret")

    cleaned, stats = baseline_deidentify_dataset(ds, uid_mapper=UIDMapper("test"))
    assert cleaned.PatientName == ""
    assert cleaned.PatientID == ""
    assert cleaned.StudyDate == ""
    assert cleaned.StudyDescription == "CLEANED"
    assert cleaned.StudyInstanceUID != "2.25.100"
    assert cleaned.RequestAttributesSequence[0].PatientID == ""
    assert not any(element.tag.is_private for element in cleaned)
    assert cleaned.PatientIdentityRemoved == "YES"
    assert stats.cleared_identifiers >= 3


def test_uid_mapper_is_consistent():
    mapper = UIDMapper("test")
    assert mapper.map("2.25.1") == mapper.map("2.25.1")
    assert mapper.map("2.25.1") != mapper.map("2.25.2")
