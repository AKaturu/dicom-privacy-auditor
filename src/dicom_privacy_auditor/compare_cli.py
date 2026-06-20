from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .compare import compare_files
from .export import write_csv, write_json


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dicom-privacy-compare",
        description="Compare a source DICOM object with a de-identified candidate.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--json", dest="json_output", type=Path)
    parser.add_argument("--csv", dest="csv_output", type=Path)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--show-values", action="store_true", help="UNSAFE: include raw values")
    parser.add_argument(
        "--show-source-paths", action="store_true", help="UNSAFE: include original source paths"
    )
    args = parser.parse_args(argv)
    if not args.source.exists() or not args.candidate.exists():
        print("Both source and candidate files must exist.", file=sys.stderr)
        return 1
    report = compare_files(
        args.source,
        args.candidate,
        force=args.force,
        show_values=args.show_values,
        show_source_paths=args.show_source_paths,
    )
    if args.json_output:
        write_json([report], args.json_output)
    if args.csv_output:
        write_csv([report], args.csv_output)
    print(json.dumps(report.to_dict(), indent=2))
    return 0 if report.readable else 1


if __name__ == "__main__":
    raise SystemExit(main())
