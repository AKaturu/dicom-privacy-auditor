import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

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


def test_pixel_redaction_replaces_only_the_reviewed_region_and_round_trips(tmp_path):
    pixels = np.full((12, 12), 20, dtype=np.uint16)
    pixels[4:8, 3:9] = np.arange(24, dtype=np.uint16).reshape(4, 6) + 200
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = generate_uid()
    dataset.set_pixel_data(pixels, "MONOCHROME2", 12, generate_instance_uid=False)

    cleaned, stats = baseline_deidentify_dataset(dataset, pixel_bboxes=[(3, 4, 9, 8)])
    cleaned_pixels = np.asarray(cleaned.pixel_array)
    outside = np.ones(pixels.shape, dtype=bool)
    outside[4:8, 3:9] = False

    assert stats.pixel_regions_cleaned == 1
    assert np.array_equal(cleaned_pixels[outside], pixels[outside])
    assert np.unique(cleaned_pixels[4:8, 3:9]).size == 1
    assert not np.array_equal(cleaned_pixels[4:8, 3:9], pixels[4:8, 3:9])
    assert cleaned.BurnedInAnnotation == "NO"
    assert cleaned.file_meta.TransferSyntaxUID == ExplicitVRLittleEndian

    destination = tmp_path / "cleaned.dcm"
    cleaned.save_as(destination, enforce_file_format=True)
    reloaded = pydicom.dcmread(destination)
    assert np.array_equal(reloaded.pixel_array, cleaned_pixels)
