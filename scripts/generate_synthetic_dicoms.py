from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid


def base_dataset(path: Path) -> FileDataset:
    file_meta = FileMetaDataset()
    file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    file_meta.MediaStorageSOPInstanceUID = generate_uid()
    file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_meta.ImplementationClassUID = generate_uid()

    ds = FileDataset(str(path), {}, file_meta=file_meta, preamble=b"\0" * 128)
    ds.SOPClassUID = file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.Modality = "OT"
    ds.Rows = 64
    ds.Columns = 64
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = np.zeros((64, 64), dtype=np.uint8).tobytes()
    return ds


def write_leaky(path: Path) -> None:
    ds = base_dataset(path)
    ds.PatientName = "DOE^JANE"
    ds.PatientID = "MRN-884211"
    ds.PatientBirthDate = "19790513"
    ds.PatientAddress = "44 SAMPLE STREET^^RALEIGH^NC^27601"
    ds.InstitutionName = "Example Medical Center"
    ds.ReferringPhysicianName = "SMITH^ALEX"
    ds.AccessionNumber = "ACC-2026-000042"
    ds.StudyDate = "20260619"
    ds.StudyDescription = "Head CT - patient email jane.doe@example.org"
    ds.BurnedInAnnotation = "YES"

    request_item = Dataset()
    request_item.RequestedProcedureDescription = "MRN: MRN-884211; patient Jane Doe"
    ds.RequestAttributesSequence = Sequence([request_item])

    private_block = ds.private_block(0x0011, "AUDITOR_TEST", create=True)
    private_block.add_new(0x01, "LO", "Jane Doe internal routing note")
    ds.save_as(path, enforce_file_format=True)


def write_cleaner(path: Path) -> None:
    ds = base_dataset(path)
    ds.PatientName = ""
    ds.PatientID = ""
    ds.StudyDescription = "RESEARCH DATASET"
    ds.PatientIdentityRemoved = "YES"
    ds.DeidentificationMethod = "Synthetic example; direct identifiers removed"
    ds.LongitudinalTemporalInformationModified = "REMOVED"
    ds.BurnedInAnnotation = "NO"
    ds.RecognizableVisualFeatures = "NO"
    ds.save_as(path, enforce_file_format=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, nargs="?", default=Path("sample_data"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    write_leaky(args.output / "DOE_JANE_head_ct.dcm")
    write_cleaner(args.output / "0000000000000001.dcm")
    print(f"Wrote synthetic DICOM files to {args.output.resolve()}")


if __name__ == "__main__":
    main()
