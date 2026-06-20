from __future__ import annotations

import argparse
import json
from pathlib import Path

from .generate import generate_publication_package


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-report")
    sub = parser.add_subparsers(dest="command", required=True)
    generate = sub.add_parser("generate", help="Generate manuscript-ready tables and templates")
    generate.add_argument("workspace", type=Path)
    generate.add_argument("output", type=Path)
    generate.add_argument("--title", default="DICOM de-identification benchmark report")
    generate.add_argument("--review-db", type=Path)
    generate.add_argument("--disclose-paths", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = generate_publication_package(
        args.workspace,
        args.output,
        title=args.title,
        review_database=args.review_db,
        disclose_paths=args.disclose_paths,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
