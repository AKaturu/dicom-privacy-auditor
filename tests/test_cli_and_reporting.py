from __future__ import annotations

import json
import sys

from dicom_privacy_auditor.benchmark.evaluate import evaluate_run, mcnemar_exact
from dicom_privacy_auditor.benchmark.report import create_plots
from dicom_privacy_auditor.benchmark.runner import run_external_pipeline
from dicom_privacy_auditor.benchmark.synthetic import generate_benchmark
from dicom_privacy_auditor.benchmark_cli import main as benchmark_main
from dicom_privacy_auditor.cli import main as audit_main
from dicom_privacy_auditor.compare_cli import main as compare_main
from dicom_privacy_auditor.deidentify_cli import main as deidentify_main


def test_audit_compare_and_deidentify_clis(tmp_path):
    benchmark = tmp_path / "benchmark"
    manifest = generate_benchmark(benchmark, cases_per_stratum=1, clean_controls=0, seed=19)
    standard = next(case for case in manifest.cases if case.metadata["stratum"] == "standard_metadata")
    source = benchmark / standard.relative_path

    audit_json = tmp_path / "audit.json"
    audit_csv = tmp_path / "audit.csv"
    assert audit_main([str(source), "--json", str(audit_json), "--csv", str(audit_csv)]) == 0
    assert audit_json.exists() and audit_csv.exists()
    assert audit_main([str(tmp_path / "missing.dcm")]) == 1

    candidate = tmp_path / "candidate.dcm"
    assert deidentify_main([str(source), str(candidate), "--uid-salt", "test"]) == 0
    comparison = tmp_path / "comparison.json"
    assert compare_main([str(source), str(candidate), "--json", str(comparison)]) == 0
    assert comparison.exists()
    assert compare_main([str(source), str(tmp_path / "missing.dcm")]) == 1


def test_external_runner_and_reporting(tmp_path):
    benchmark = tmp_path / "benchmark"
    generate_benchmark(benchmark, cases_per_stratum=1, clean_controls=1, seed=21)
    external = tmp_path / "external"
    command = [
        sys.executable,
        "-S",
        "-c",
        "import shutil,sys; shutil.copy2(sys.argv[1], sys.argv[2])",
        "{input}",
        "{output}",
    ]
    run_external_pipeline(
        benchmark,
        external,
        name="external-noop",
        command=command,
        output_name_mode="preserve",
    )
    evaluation_dir = tmp_path / "evaluation"
    evaluation = evaluate_run(benchmark, external, output_dir=evaluation_dir)
    assert evaluation.summary["residual_injections"] == 10
    figures = create_plots(evaluation_dir / "evaluation.json", evaluation_dir / "figures")
    assert len(figures) == 2
    assert all(path.exists() for path in figures)


def test_benchmark_cli_paths_and_mcnemar(tmp_path):
    benchmark = tmp_path / "benchmark"
    assert (
        benchmark_main(
            [
                "generate",
                str(benchmark),
                "--cases-per-stratum",
                "1",
                "--clean-controls",
                "1",
                "--seed",
                "23",
            ]
        )
        == 0
    )
    noop_run = tmp_path / "run-noop"
    baseline_run = tmp_path / "run-baseline"
    assert benchmark_main(["run", str(benchmark), str(noop_run), "--pipeline", "noop"]) == 0
    assert benchmark_main(["run", str(benchmark), str(baseline_run), "--pipeline", "baseline"]) == 0

    noop_eval_dir = tmp_path / "eval-noop"
    baseline_eval_dir = tmp_path / "eval-baseline"
    assert benchmark_main(["evaluate", str(benchmark), str(noop_run), str(noop_eval_dir)]) == 0
    assert benchmark_main(["evaluate", str(benchmark), str(baseline_run), str(baseline_eval_dir)]) == 0
    assert (
        benchmark_main(["plot", str(noop_eval_dir / "evaluation.json"), str(noop_eval_dir / "figures")]) == 0
    )

    comparison_path = tmp_path / "mcnemar.json"
    assert (
        benchmark_main(
            [
                "compare",
                str(noop_eval_dir / "evaluation.json"),
                str(baseline_eval_dir / "evaluation.json"),
                "--output",
                str(comparison_path),
            ]
        )
        == 0
    )
    comparison = json.loads(comparison_path.read_text())
    assert comparison["discordant_pairs"] == 10

    noop = evaluate_run(benchmark, noop_run)
    baseline = evaluate_run(benchmark, baseline_run)
    direct = mcnemar_exact(noop, baseline)
    assert direct["b_removed_a_failed"] == 10


def test_benchmark_all_command(tmp_path):
    workspace = tmp_path / "all"
    assert (
        benchmark_main(
            [
                "all",
                str(workspace),
                "--pipeline",
                "metadata-only",
                "--cases-per-stratum",
                "1",
                "--clean-controls",
                "1",
                "--overwrite",
            ]
        )
        == 0
    )
    payload = json.loads((workspace / "evaluation-metadata-only" / "evaluation.json").read_text())
    assert payload["summary"]["residual_injections"] == 2
