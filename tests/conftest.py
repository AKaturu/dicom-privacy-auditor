from __future__ import annotations

import json
import os

import numpy as np
import pytest
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

ATTRIBUTE_OPTIONS = [
    "retain_safe_private",
    "retain_uids",
    "retain_device_identity",
    "retain_institution_identity",
    "retain_patient_characteristics",
    "retain_longitudinal_full_dates",
    "retain_longitudinal_modified_dates",
    "clean_descriptors",
    "clean_structured_content",
    "clean_graphics",
]


@pytest.fixture
def review_dicom_writer():
    def write(path, *, patient="SOURCE", pixels=None):
        pixel_array = np.asarray(
            pixels if pixels is not None else [[0, 1], [2, 3]],
            dtype=np.uint16,
        )
        metadata = FileMetaDataset()
        metadata.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        metadata.MediaStorageSOPInstanceUID = generate_uid()
        metadata.TransferSyntaxUID = ExplicitVRLittleEndian
        dataset = FileDataset(str(path), {}, file_meta=metadata, preamble=b"\0" * 128)
        dataset.SOPClassUID = SecondaryCaptureImageStorage
        dataset.SOPInstanceUID = metadata.MediaStorageSOPInstanceUID
        dataset.StudyInstanceUID = generate_uid()
        dataset.SeriesInstanceUID = generate_uid()
        dataset.PatientID = patient
        dataset.Modality = "OT"
        dataset.Rows, dataset.Columns = pixel_array.shape
        dataset.SamplesPerPixel = 1
        dataset.PhotometricInterpretation = "MONOCHROME2"
        dataset.BitsAllocated = 16
        dataset.BitsStored = 16
        dataset.HighBit = 15
        dataset.PixelRepresentation = 0
        dataset.PixelData = pixel_array.tobytes()
        dataset.save_as(path, enforce_file_format=True)

    return write


def _attribute(name: str, tag: str, tag_hex: str | None, basic: str, **overrides: str):
    row = {
        "name": name,
        "tag": tag,
        "tag_hex": tag_hex,
        "retired": "N",
        "standard_composite_iod": "Y",
        "basic_profile": basic,
    }
    row.update({option: overrides.get(option, "") for option in ATTRIBUTE_OPTIONS})
    return row


@pytest.fixture(scope="session", autouse=True)
def local_ps315_test_tables(tmp_path_factory: pytest.TempPathFactory):
    """Provide small synthetic tables without redistributing DICOM standards content."""

    directory = tmp_path_factory.mktemp("synthetic-ps315")
    attributes = [
        _attribute("Synthetic SOP Class UID rule", "(0008,0016)", "00080016", "K"),
        _attribute(
            "Synthetic SOP Instance UID rule",
            "(0008,0018)",
            "00080018",
            "U",
            retain_uids="K",
        ),
        _attribute("Synthetic Patient Name rule", "(0010,0010)", "00100010", "Z"),
        _attribute("Synthetic Patient ID rule", "(0010,0020)", "00100020", "Z"),
        _attribute(
            "Synthetic Study Instance UID rule",
            "(0020,000D)",
            "0020000D",
            "U",
            retain_uids="K",
        ),
        _attribute(
            "Synthetic Request Attributes Sequence rule",
            "(0040,0275)",
            "00400275",
            "K",
        ),
        _attribute("Synthetic Content Sequence rule", "(0040,A730)", "0040A730", "X"),
        _attribute(
            "Private Attributes",
            "ggggeeee where gggg is odd",
            None,
            "X",
            retain_safe_private="C",
        ),
    ]
    codes = [
        {
            "code_meaning": "Synthetic accession rule",
            "code_value": "121022",
            "coding_scheme_designator": "DCM",
            "value_type": "TEXT",
            "retired": "N",
            "standard_template": "Y",
            "basic_profile": "X",
            "retain_uids": "",
            "retain_device_identity": "",
            "retain_institution_identity": "",
            "retain_patient_characteristics": "",
            "retain_longitudinal_full_dates": "",
            "retain_longitudinal_modified_dates": "",
            "clean_descriptors": "",
        }
    ]
    common = {
        "schema_version": "test",
        "standard": "Synthetic PS3.15 test fixture",
        "edition": "test",
        "source_url": None,
        "source_sha256": "synthetic",
        "generated_locally": True,
        "redistributed_by_project": False,
        "rights_notice": "Synthetic test data; not DICOM Standard content.",
    }
    (directory / "ps315_test_table_e1_1.json").write_text(
        json.dumps(
            {
                **common,
                "table": "E.1-1",
                "title": "Synthetic attribute rules",
                "row_count": len(attributes),
                "rules": attributes,
            }
        ),
        encoding="utf-8",
    )
    (directory / "ps315_test_table_e1_2.json").write_text(
        json.dumps(
            {
                **common,
                "table": "E.1-2",
                "title": "Synthetic code rules",
                "row_count": len(codes),
                "rules": codes,
            }
        ),
        encoding="utf-8",
    )
    os.environ["DICOM_PRIVACY_PS315_DATA_DIR"] = str(directory)
    os.environ["DICOM_PRIVACY_PS315_EDITION"] = "test"
    from dicom_privacy_auditor.ps315.policy import clear_caches

    clear_caches()
    yield directory
    clear_caches()
