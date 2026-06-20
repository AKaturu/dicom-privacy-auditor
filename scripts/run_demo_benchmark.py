from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from dicom_privacy_auditor.benchmark.evaluate import evaluate_run, mcnemar_exact
from dicom_privacy_auditor.benchmark.report import create_plots
from dicom_privacy_auditor.benchmark.runner import run_builtin_pipeline
from dicom_privacy_auditor.benchmark.synthetic import generate_benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path("examples/demo_workspace"))
    parser.add_argument("--cases-per-stratum", type=int, default=2)
    parser.add_argument("--clean-controls", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20260619)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.workspace.exists() and args.overwrite:
        shutil.rmtree(args.workspace)
    args.workspace.mkdir(parents=True, exist_ok=True)
    benchmark = args.workspace / "benchmark"
    generate_benchmark(
        benchmark,
        cases_per_stratum=args.cases_per_stratum,
        clean_controls=args.clean_controls,
        seed=args.seed,
        overwrite=args.overwrite,
    )

    evaluations = {}
    for pipeline in ("noop", "metadata-only", "baseline"):
        run_dir = args.workspace / f"run-{pipeline}"
        evaluation_dir = args.workspace / f"evaluation-{pipeline}"
        run_builtin_pipeline(benchmark, run_dir, pipeline=pipeline, overwrite=args.overwrite)
        evaluation = evaluate_run(benchmark, run_dir, output_dir=evaluation_dir)
        create_plots(evaluation_dir / "evaluation.json", evaluation_dir / "figures")
        evaluations[pipeline] = evaluation

    comparisons = {
        "noop_vs_metadata_only": mcnemar_exact(evaluations["noop"], evaluations["metadata-only"]),
        "metadata_only_vs_baseline": mcnemar_exact(evaluations["metadata-only"], evaluations["baseline"]),
    }
    (args.workspace / "paired_comparisons.json").write_text(
        json.dumps(comparisons, indent=2), encoding="utf-8"
    )
    summary = {name: evaluation.summary for name, evaluation in evaluations.items()}
    (args.workspace / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
