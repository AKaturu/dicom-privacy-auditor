from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__
from .benchmark.evaluate import evaluate_run, mcnemar_exact
from .benchmark.report import create_plots
from .benchmark.runner import run_builtin_pipeline
from .benchmark.synthetic import generate_benchmark
from .corpus import evaluate_corpus
from .jsonio import write_json
from .publication import generate_publication_package
from .review.store import ReviewStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_demo(
    output: str | Path,
    *,
    cases_per_stratum: int = 1,
    clean_controls: int = 2,
    seed: int = 20260620,
    overwrite: bool = False,
    plots: bool = True,
) -> dict[str, Any]:
    root = Path(output).resolve()
    if root.exists() and any(root.iterdir()):
        if not overwrite:
            raise FileExistsError(f"Demo output is not empty: {root}")
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    benchmark = root / "benchmark"
    generate_benchmark(
        benchmark,
        cases_per_stratum=cases_per_stratum,
        clean_controls=clean_controls,
        seed=seed,
        overwrite=True,
    )
    evaluations = {}
    for pipeline in ("noop", "metadata-only", "baseline"):
        run_dir = root / f"run-{pipeline}"
        evaluation_dir = root / f"evaluation-{pipeline}"
        run_builtin_pipeline(benchmark, run_dir, pipeline=pipeline, overwrite=True)
        evaluation = evaluate_run(benchmark, run_dir, output_dir=evaluation_dir)
        if plots:
            try:
                create_plots(evaluation_dir / "evaluation.json", evaluation_dir / "figures")
            except ImportError:
                pass
        evaluations[pipeline] = evaluation

    comparisons = {
        "noop_vs_metadata_only": mcnemar_exact(evaluations["noop"], evaluations["metadata-only"]),
        "metadata_only_vs_baseline": mcnemar_exact(evaluations["metadata-only"], evaluations["baseline"]),
    }
    write_json(root / "paired_comparisons.json", comparisons, schema_name="paired-comparisons")
    summary = {name: value.summary for name, value in evaluations.items()}
    write_json(root / "summary.json", summary, schema_name="pipeline-summary")

    corpus = evaluate_corpus(benchmark, root / "run-metadata-only")
    write_json(root / "corpus-report.json", corpus.to_dict(), schema_name="corpus-report")

    review_db = root / "human-review.db"
    review_cases = ReviewStore(review_db).initialize(
        benchmark, root / "run-metadata-only", title="Synthetic demonstration review", overwrite=True
    )
    publication = generate_publication_package(
        root,
        root / "publication",
        title="Synthetic DICOM privacy-audit demonstration",
        review_database=review_db,
    )

    manifest = {
        "schema_version": "1.0",
        "generated_at": _now(),
        "software_version": __version__,
        "synthetic_results": True,
        "seed": seed,
        "cases_per_stratum": cases_per_stratum,
        "clean_controls": clean_controls,
        "pipelines": list(evaluations),
        "review_cases": review_cases,
        "summary": summary,
        "artifacts": {
            "benchmark_manifest": "benchmark/manifest.json",
            "review_database": "human-review.db",
            "corpus_report": "corpus-report.json",
            "publication_manifest": "publication/publication_manifest.json",
        },
    }
    write_json(root / "demo_manifest.json", manifest, schema_name="demo-manifest")
    readme = f"""# DICOM Privacy Auditor synthetic demonstration

Generated with version `{__version__}` on `{manifest["generated_at"]}`.

This package contains entirely synthetic DICOM objects and deliberately seeded artificial identifiers. It demonstrates the audit, benchmark, corpus-consistency, review, and manuscript-report workflows. It is not clinical validation and contains no real patient information.

## Key outputs

- `summary.json`: pipeline-level reference results
- `corpus-report.json`: collection-wide consistency findings
- `human-review.db`: review workstation database with {review_cases} pending synthetic cases
- `publication/`: manuscript-ready tables, methods template, figures, and reproducibility manifest
"""
    (root / "DEMO_README.md").write_text(readme, encoding="utf-8")
    manifest["demo_manifest_sha256"] = _hash(root / "demo_manifest.json")
    manifest["publication_manifest"] = publication.get("manifest_path")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-demo")
    parser.add_argument("output", type=Path)
    parser.add_argument("--cases-per-stratum", type=int, default=1)
    parser.add_argument("--clean-controls", type=int, default=2)
    parser.add_argument("--seed", type=int, default=20260620)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-plots", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_demo(
        args.output,
        cases_per_stratum=args.cases_per_stratum,
        clean_controls=args.clean_controls,
        seed=args.seed,
        overwrite=args.overwrite,
        plots=not args.no_plots,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
