from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from ..jsonio import write_json
from .evaluate import evaluate_corpus


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-corpus")
    sub = parser.add_subparsers(dest="command", required=True)
    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("source", type=Path)
    evaluate.add_argument("candidate", type=Path)
    evaluate.add_argument("--mapping-csv", type=Path)
    evaluate.add_argument("--json", dest="json_path", type=Path)
    evaluate.add_argument("--csv", dest="csv_path", type=Path)
    evaluate.add_argument("--disclose-paths", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = evaluate_corpus(
        args.source, args.candidate, mapping_csv=args.mapping_csv, disclose_paths=args.disclose_paths
    )
    payload = report.to_dict()
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.json_path, payload, schema_name="corpus-report")
    if args.csv_path:
        args.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "code",
                    "severity",
                    "scope",
                    "source_key",
                    "candidate_key",
                    "message",
                    "count",
                    "examples",
                ],
            )
            writer.writeheader()
            for row in payload["findings"]:
                writer.writerow({**row, "examples": "|".join(row["examples"])})
        try:
            os.chmod(args.csv_path, 0o600)
        except OSError:
            pass
    print(json.dumps({"pairs": report.pairs, **report.metrics}, indent=2))
    return 1 if report.metrics["critical_findings"] or report.metrics["high_findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
