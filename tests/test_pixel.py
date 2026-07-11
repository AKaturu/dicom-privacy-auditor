import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from dicom_privacy_auditor.benchmark.synthetic import generate_benchmark
from dicom_privacy_auditor.pixel import patch_similarity, scan_text_like_border


def _pixel_dataset(pixels: np.ndarray, photometric: str = "MONOCHROME2") -> Dataset:
    dataset = Dataset()
    dataset.file_meta = FileMetaDataset()
    dataset.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = generate_uid()
    dataset.set_pixel_data(
        np.asarray(pixels),
        photometric,
        8,
        generate_instance_uid=False,
    )
    return dataset


def test_experimental_pixel_scan_detects_synthetic_annotation(tmp_path):
    manifest = generate_benchmark(tmp_path / "benchmark", cases_per_stratum=1, clean_controls=0, seed=3)
    case = next(case for case in manifest.cases if case.metadata["stratum"] == "pixel_annotation")
    ds = pydicom.dcmread(tmp_path / "benchmark" / case.relative_path)
    result = scan_text_like_border(ds)
    assert result.analyzable
    assert result.suspicious
    assert result.bbox is not None


def test_pixel_scan_reports_missing_and_undecodable_pixels() -> None:
    missing = scan_text_like_border(Dataset())
    malformed_dataset = Dataset()
    malformed_dataset.PixelData = b"not-a-pixel-module"
    malformed = scan_text_like_border(malformed_dataset)

    assert not missing.analyzable
    assert missing.reason == "No PixelData"
    assert not malformed.analyzable
    assert malformed.reason is not None
    assert malformed.reason.startswith("Pixel decoding failed:")


def test_pixel_scan_rejects_tiny_images() -> None:
    result = scan_text_like_border(_pixel_dataset(np.zeros((8, 8), dtype=np.uint8)))

    assert not result.analyzable
    assert result.reason == "Unsupported pixel shape"


def test_pixel_scan_accepts_constant_image_without_flagging() -> None:
    result = scan_text_like_border(_pixel_dataset(np.full((64, 64), 20, dtype=np.uint8)))

    assert result.analyzable
    assert not result.suspicious
    assert result.score == 0.0
    assert result.bbox is None


def test_pixel_scan_ignores_high_contrast_center_region() -> None:
    pixels = np.zeros((64, 64), dtype=np.uint8)
    pixels[20:44, 20:44] = np.indices((24, 24)).sum(axis=0) % 2 * 255

    result = scan_text_like_border(_pixel_dataset(pixels))

    assert result.analyzable
    assert not result.suspicious
    assert result.bbox is None


def test_pixel_scan_handles_multiframe_color_pixels() -> None:
    pixels = np.zeros((2, 64, 64, 3), dtype=np.uint8)
    pixels[0, :12, 8:40, :] = np.indices((12, 32)).sum(axis=0)[..., None] % 2 * 255

    result = scan_text_like_border(_pixel_dataset(pixels, "RGB"))

    assert result.analyzable
    assert result.suspicious
    assert result.bbox is not None


def test_patch_similarity_handles_equal_constant_and_invalid_shapes() -> None:
    constant = np.ones((4, 4), dtype=np.uint8)

    assert patch_similarity(constant, constant.copy()) == 1.0
    assert patch_similarity(constant, np.zeros((4, 4), dtype=np.uint8)) == 0.0
    assert patch_similarity(constant, np.zeros((3, 3), dtype=np.uint8)) == -1.0
    assert patch_similarity(np.array([]), np.array([])) == -1.0
