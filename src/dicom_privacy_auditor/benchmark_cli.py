from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark.evaluate import BenchmarkEvaluation, evaluate_run, mcnemar_exact
from .benchmark.report import create_plots
from .benchmark.runner import run_adapter_pipeline, run_builtin_pipeline, run_external_pipeline
from .benchmark.synthetic import generate_benchmark
from .jsonio import write_json as atomic_write_json


def _load_evaluation(path: Path) -> BenchmarkEvaluation:
    payload = json.loads(path.read_text(encoding="utf-8"))
    # McNemar only needs pipeline plus injection IDs/removal states. Rehydrate through
    # lightweight local imports to keep the public JSON schema stable.
    from .benchmark.evaluate import CaseEvaluation, InjectionResult

    cases = []
    for case_payload in payload["cases"]:
        injections = [InjectionResult(**item) for item in case_payload.pop("injections")]
        cases.append(CaseEvaluation(injections=injections, **case_payload))
    return BenchmarkEvaluation(
        pipeline=payload["pipeline"],
        benchmark_name=payload["benchmark_name"],
        cases=cases,
        summary=payload["summary"],
        by_stratum=payload["by_stratum"],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a deterministic synthetic benchmark")
    generate.add_argument("output", type=Path)
    generate.add_argument("--cases-per-stratum", type=int, default=5)
    generate.add_argument("--clean-controls", type=int, default=10)
    generate.add_argument("--seed", type=int, default=20260619)
    generate.add_argument("--overwrite", action="store_true")

    run = subparsers.add_parser("run", help="Run a built-in or external pipeline")
    run.add_argument("benchmark", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--pipeline", choices=["noop", "metadata-only", "baseline"], default="baseline")
    run.add_argument("--external-name")
    run.add_argument("--adapter", choices=["orthanc", "rsna-anonymizer", "rsna-ctp", "directory"])
    run.add_argument("--adapter-config", type=Path)
    run.add_argument("--external-command", nargs="+")
    run.add_argument("--timeout", type=int, default=120)
    run.add_argument("--output-name-mode", choices=["preserve", "safe"], default="preserve")
    run.add_argument("--overwrite", action="store_true")

    evaluate = subparsers.add_parser("evaluate", help="Evaluate a completed benchmark run")
    evaluate.add_argument("benchmark", type=Path)
    evaluate.add_argument("run", type=Path)
    evaluate.add_argument("output", type=Path)

    all_cmd = subparsers.add_parser("all", help="Generate, run, evaluate, and plot a benchmark")
    all_cmd.add_argument("workspace", type=Path)
    all_cmd.add_argument("--cases-per-stratum", type=int, default=5)
    all_cmd.add_argument("--clean-controls", type=int, default=10)
    all_cmd.add_argument("--seed", type=int, default=20260619)
    all_cmd.add_argument("--pipeline", choices=["noop", "metadata-only", "baseline"], default="baseline")
    all_cmd.add_argument("--overwrite", action="store_true")

    plot = subparsers.add_parser("plot", help="Create figures from evaluation.json")
    plot.add_argument("evaluation", type=Path)
    plot.add_argument("output", type=Path)

    compare = subparsers.add_parser("compare", help="McNemar exact comparison of two evaluations")
    compare.add_argument("evaluation_a", type=Path)
    compare.add_argument("evaluation_b", type=Path)
    compare.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "generate":
        manifest = generate_benchmark(
            args.output,
            cases_per_stratum=args.cases_per_stratum,
            clean_controls=args.clean_controls,
            seed=args.seed,
            overwrite=args.overwrite,
        )
        print(json.dumps(manifest.to_dict(), indent=2))
        return 0

    if args.command == "run":
        if args.adapter:
            if not args.adapter_config:
                raise SystemExit("--adapter-config is required with --adapter")
            config = json.loads(args.adapter_config.read_text(encoding="utf-8"))
            run_manifest = run_adapter_pipeline(
                args.benchmark,
                args.output,
                adapter_name=args.adapter,
                config=config,
                overwrite=args.overwrite,
            )
        elif args.external_command:
            run_manifest = run_external_pipeline(
                args.benchmark,
                args.output,
                name=args.external_name or "external",
                command=args.external_command,
                timeout_seconds=args.timeout,
                output_name_mode=args.output_name_mode,
                overwrite=args.overwrite,
            )
        else:
            run_manifest = run_builtin_pipeline(
                args.benchmark,
                args.output,
                pipeline=args.pipeline,
                overwrite=args.overwrite,
            )
        print(
            json.dumps({"pipeline": run_manifest.pipeline_name, "cases": len(run_manifest.cases)}, indent=2)
        )
        return 0

    if args.command == "evaluate":
        evaluation = evaluate_run(args.benchmark, args.run, output_dir=args.output)
        print(json.dumps(evaluation.summary, indent=2))
        return 0

    if args.command == "all":
        benchmark = args.workspace / "benchmark"
        run = args.workspace / f"run-{args.pipeline}"
        evaluation_dir = args.workspace / f"evaluation-{args.pipeline}"
        generate_benchmark(
            benchmark,
            cases_per_stratum=args.cases_per_stratum,
            clean_controls=args.clean_controls,
            seed=args.seed,
            overwrite=args.overwrite,
        )
        run_builtin_pipeline(benchmark, run, pipeline=args.pipeline, overwrite=args.overwrite)
        evaluation = evaluate_run(benchmark, run, output_dir=evaluation_dir)
        try:
            create_plots(evaluation_dir / "evaluation.json", evaluation_dir / "figures")
        except ModuleNotFoundError as exc:
            print(
                f"Plotting skipped because an optional dependency is missing: {exc}. "
                "Install with pip install -e '.[analysis]'."
            )
        print(json.dumps(evaluation.summary, indent=2))
        return 0

    if args.command == "plot":
        try:
            generated = create_plots(args.evaluation, args.output)
        except ModuleNotFoundError as exc:
            print(f"Plotting requires the analysis extra: {exc}. Install with pip install -e '.[analysis]'.")
            return 1
        print(json.dumps([str(path) for path in generated], indent=2))
        return 0

    if args.command == "compare":
        result = mcnemar_exact(_load_evaluation(args.evaluation_a), _load_evaluation(args.evaluation_b))
        text = json.dumps(result, indent=2)
        if args.output:
            atomic_write_json(args.output, result)
        print(text)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
