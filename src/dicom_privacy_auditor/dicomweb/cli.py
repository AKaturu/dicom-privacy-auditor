from __future__ import annotations

import argparse
import json
from pathlib import Path

import pydicom

from .client import DicomwebClient, DicomwebConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-dicomweb")
    parser.add_argument("--config", type=Path, required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("probe")
    search = sub.add_parser("search-studies")
    search.add_argument("--query", action="append", default=[], help="key=value QIDO parameter")
    search.add_argument("--page-size", type=int, default=100)
    search.add_argument("--max-results", type=int)
    retrieve = sub.add_parser("retrieve-study")
    retrieve.add_argument("study_uid")
    retrieve.add_argument("destination", type=Path)
    store = sub.add_parser("store-study")
    store.add_argument("directory", type=Path)
    store.add_argument("--study-uid")
    return parser


def _params(items: list[str]) -> dict[str, str]:
    output: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Query parameter must be key=value: {item}")
        key, value = item.split("=", 1)
        output[key] = value
    return output


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = DicomwebConfig.from_json(args.config)
    with DicomwebClient(config) as client:
        if args.command == "probe":
            output_payload: object = client.capabilities()
        elif args.command == "search-studies":
            output_payload = client.search_studies(
                _params(args.query), page_size=args.page_size, max_results=args.max_results
            )
        elif args.command == "retrieve-study":
            paths = client.retrieve_study(args.study_uid, args.destination)
            output_payload = {
                "study_uid": args.study_uid,
                "instances": len(paths),
                "destination": str(args.destination),
            }
        else:
            paths = []
            for path in sorted(args.directory.rglob("*")):
                if not path.is_file():
                    continue
                try:
                    pydicom.dcmread(path, stop_before_pixels=True)
                except Exception:
                    continue
                paths.append(path)
            output_payload = client.store_instances(paths, study_uid=args.study_uid)
    print(json.dumps(output_payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
