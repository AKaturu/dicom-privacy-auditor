from __future__ import annotations

import argparse
import json
from pathlib import Path

from .adapters.factory import create_adapter
from .adapters.util import load_config
from .benchmark.runner import run_adapter_pipeline

ADAPTERS = ["orthanc", "rsna-anonymizer", "rsna-ctp", "directory"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-adapter")
    sub = parser.add_subparsers(dest="command", required=True)
    probe = sub.add_parser("probe", help="Check whether an adapter target is reachable")
    probe.add_argument("adapter", choices=ADAPTERS)
    probe.add_argument("config", type=Path)
    process = sub.add_parser("process", help="Process one DICOM object")
    process.add_argument("adapter", choices=ADAPTERS)
    process.add_argument("config", type=Path)
    process.add_argument("source", type=Path)
    process.add_argument("destination", type=Path)
    process.add_argument("--case-id", default="manual")
    run = sub.add_parser("run-benchmark", help="Run an imported/synthetic benchmark through an adapter")
    run.add_argument("adapter", choices=ADAPTERS)
    run.add_argument("config", type=Path)
    run.add_argument("benchmark", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(args.config)
    if args.command == "run-benchmark":
        run_manifest = run_adapter_pipeline(
            args.benchmark, args.output, adapter_name=args.adapter, config=config, overwrite=args.overwrite
        )
        print(
            json.dumps({"pipeline": run_manifest.pipeline_name, "cases": len(run_manifest.cases)}, indent=2)
        )
        return 0
    adapter = create_adapter(args.adapter, config)
    try:
        if args.command == "probe":
            print(json.dumps(adapter.probe(), indent=2))
            return 0
        adapter_result = adapter.process(args.source, args.destination, case_id=args.case_id)
        print(
            json.dumps(
                {
                    "status": adapter_result.status,
                    "runtime_seconds": adapter_result.runtime_seconds,
                    "details": adapter_result.details,
                },
                indent=2,
            )
        )
        return 0 if adapter_result.status == "ok" else 1
    finally:
        adapter.close()


if __name__ == "__main__":
    raise SystemExit(main())
