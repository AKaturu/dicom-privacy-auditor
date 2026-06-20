import pydicom

from dicom_privacy_auditor.benchmark.synthetic import generate_benchmark
from dicom_privacy_auditor.pixel import scan_text_like_border


def test_experimental_pixel_scan_detects_synthetic_annotation(tmp_path):
    manifest = generate_benchmark(tmp_path / "benchmark", cases_per_stratum=1, clean_controls=0, seed=3)
    case = next(case for case in manifest.cases if case.metadata["stratum"] == "pixel_annotation")
    ds = pydicom.dcmread(tmp_path / "benchmark" / case.relative_path)
    result = scan_text_like_border(ds)
    assert result.analyzable
    assert result.suspicious
    assert result.bbox is not None
