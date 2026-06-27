import pydicom

from dicom_privacy_auditor.benchmark.evaluate import evaluate_run
from dicom_privacy_auditor.benchmark.runner import run_builtin_pipeline
from dicom_privacy_auditor.benchmark.synthetic import STRATA, generate_benchmark


def test_benchmark_generation_is_balanced(tmp_path):
    root = tmp_path / "benchmark"
    manifest = generate_benchmark(root, cases_per_stratum=1, clean_controls=2, seed=7)
    assert len(manifest.cases) == len(STRATA) + 2
    assert sum(len(case.injections) for case in manifest.cases) == len(STRATA)
    assert (root / "manifest.json").exists()
    assert all((root / case.relative_path).exists() for case in manifest.cases)


def test_benchmark_generates_overlay_graphics_stratum(tmp_path):
    root = tmp_path / "benchmark"
    manifest = generate_benchmark(root, cases_per_stratum=1, clean_controls=0, seed=31)
    case = next(case for case in manifest.cases if case.metadata["stratum"] == "overlay_graphics")
    injection = case.injections[0]

    dataset = pydicom.dcmread(root / case.relative_path)

    assert injection.location_kind == "overlay_data"
    assert injection.keyword == "OverlayData"
    assert injection.value.encode("ascii") in dataset[(0x6000, 0x3000)].value


def test_noop_and_baseline_have_expected_end_to_end_behavior(tmp_path):
    benchmark = tmp_path / "benchmark"
    generate_benchmark(benchmark, cases_per_stratum=1, clean_controls=2, seed=11)

    noop = tmp_path / "noop"
    run_builtin_pipeline(benchmark, noop, pipeline="noop")
    noop_eval = evaluate_run(benchmark, noop)
    assert noop_eval.summary["residual_injections"] == len(STRATA)
    assert noop_eval.summary["auditor_detected_residuals"] == len(STRATA)
    assert noop_eval.summary["false_positive_controls"] == 0

    baseline = tmp_path / "baseline"
    run_builtin_pipeline(benchmark, baseline, pipeline="baseline")
    baseline_eval = evaluate_run(benchmark, baseline)
    assert baseline_eval.summary["removed_injections"] == len(STRATA)
    assert baseline_eval.summary["residual_injections"] == 0
    assert baseline_eval.summary["basic_valid_outputs"] == len(STRATA) + 2


def test_benchmark_manifest_rejects_unsafe_paths_and_duplicate_cases():
    import pytest

    from dicom_privacy_auditor.benchmark.manifest import BenchmarkManifest, CaseRecord

    with pytest.raises(ValueError, match="Unsafe benchmark relative path"):
        CaseRecord("case-1", "../../outside.dcm", "OT", False)
    with pytest.raises(ValueError, match="portable"):
        CaseRecord("../case", "objects/a.dcm", "OT", False)

    case = CaseRecord("case-1", "objects/a.dcm", "OT", False)
    with pytest.raises(ValueError, match="duplicate case_id"):
        BenchmarkManifest("test", "1", "1.0", 1, "fixture", [case, case])


def test_benchmark_runner_rejects_overlapping_roots_and_invalid_external_options(tmp_path):
    import pytest

    from dicom_privacy_auditor.benchmark.runner import run_external_pipeline

    benchmark = tmp_path / "benchmark"
    generate_benchmark(benchmark, cases_per_stratum=1, clean_controls=0, seed=13)
    with pytest.raises(ValueError, match="must not overlap"):
        run_builtin_pipeline(benchmark, benchmark / "output", pipeline="noop")
    with pytest.raises(ValueError, match="at least one nonempty token"):
        run_external_pipeline(benchmark, tmp_path / "external-empty", name="empty", command=[])
    with pytest.raises(ValueError, match="timeout_seconds must be positive"):
        run_external_pipeline(
            benchmark,
            tmp_path / "external-timeout",
            name="timeout",
            command=["tool"],
            timeout_seconds=0,
        )


def test_benchmark_runner_rejects_source_symlink_escape(tmp_path):
    import os

    import pytest

    if not hasattr(os, "symlink"):
        pytest.skip("symbolic links are unavailable")
    benchmark = tmp_path / "benchmark"
    manifest = generate_benchmark(benchmark, cases_per_stratum=1, clean_controls=0, seed=17)
    target = benchmark / manifest.cases[0].relative_path
    outside = tmp_path / "outside.dcm"
    target.replace(outside)
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are not permitted")
    with pytest.raises(ValueError, match="escapes its configured root"):
        run_builtin_pipeline(benchmark, tmp_path / "output", pipeline="noop")


def test_run_manifest_rejects_unsafe_output_and_provenance_mismatch(tmp_path):
    import json

    import pytest

    from dicom_privacy_auditor.benchmark.runner import RunCase, RunManifest

    with pytest.raises(ValueError, match="Unsafe benchmark relative path"):
        RunCase("case-1", "objects/a.dcm", "../../outside.dcm", "ok", 0.1)

    benchmark = tmp_path / "benchmark"
    manifest = generate_benchmark(benchmark, cases_per_stratum=1, clean_controls=0, seed=29)
    run = tmp_path / "run"
    run_builtin_pipeline(benchmark, run, pipeline="noop")
    payload = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
    payload["cases"][0]["input_relative_path"] = manifest.cases[-1].relative_path
    if payload["cases"][0]["case_id"] == manifest.cases[-1].case_id:
        payload["cases"][0]["input_relative_path"] = "objects/not-the-input.dcm"
    (run / "run_manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="input path mismatch"):
        evaluate_run(benchmark, run)

    case = RunCase("case-1", "objects/a.dcm", None, "error", 0.0)
    with pytest.raises(ValueError, match="duplicate case_id"):
        RunManifest("pipeline", "builtin", "manifest.json", [case, case])
