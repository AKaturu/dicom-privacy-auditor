from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path

from ..jsonio import write_json
from ..permissions import restrict_file
from .evaluate import evaluate_pair
from .generate import DICOM_RIGHTS_NOTICE, OFFICIAL_SOURCE_URL, download_and_generate, generate_tables
from .models import PolicySelection, ProfileOption
from .policy import (
    DATA_DIR_ENV,
    EDITION_ENV,
    StandardsDataNotInstalledError,
    all_code_rules,
    all_rules,
    clear_caches,
    data_status,
    default_data_dir,
    get_rule,
    resolve_code_rule,
    resolve_rule,
    table_metadata,
)


def _options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--option", action="append", choices=[item.value for item in ProfileOption], default=[]
    )
    parser.add_argument("--safe-private-tag", action="append", default=[])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-ps315")
    parser.add_argument(
        "--data-dir",
        type=Path,
        help=f"User-local generated table directory (or set {DATA_DIR_ENV})",
    )
    parser.add_argument(
        "--edition",
        help=f"Generated table edition to use (or set {EDITION_ENV}; default 2026c)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser(
        "prepare-data",
        help="Generate a user-local rule cache from an official Part 15 DOCX",
    )
    source_group = prepare.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", type=Path, help="Path to a user-supplied official Part 15 DOCX")
    source_group.add_argument(
        "--download",
        action="store_true",
        help="Temporarily download the current official Part 15 DOCX from DICOM/NEMA",
    )
    prepare.add_argument(
        "--url",
        default=OFFICIAL_SOURCE_URL,
        help="HTTPS source used with --download (defaults to the official current DOCX)",
    )
    prepare.add_argument(
        "--output",
        type=Path,
        help="Output directory for the user-local generated tables",
    )

    info = sub.add_parser("info", help="Show local standards-data status and provenance")
    info.add_argument("--json", action="store_true")
    rules = sub.add_parser("rules", help="Query locally generated Table E.1-1 data")
    rules.add_argument("--tag")
    rules.add_argument("--name")
    _options(rules)
    codes = sub.add_parser("codes", help="Query locally generated Table E.1-2 coded-content rules")
    codes.add_argument("--code")
    codes.add_argument("--scheme")
    codes.add_argument("--value-type")
    codes.add_argument("--meaning")
    _options(codes)
    evaluate = sub.add_parser("evaluate", help="Evaluate a source/output DICOM pair")
    evaluate.add_argument("source", type=Path)
    evaluate.add_argument("candidate", type=Path)
    evaluate.add_argument("--json", dest="json_path", type=Path)
    evaluate.add_argument("--csv", dest="csv_path", type=Path)
    evaluate.add_argument("--disclose-paths", action="store_true")
    evaluate.add_argument("--iod-aware", action="store_true", help="Apply a user-local PS3.3 IOD registry")
    evaluate.add_argument("--iod-registry", type=Path, help="Explicit local IOD registry JSON")
    _options(evaluate)
    return parser


def _configure_runtime(args: argparse.Namespace) -> None:
    if args.data_dir:
        os.environ[DATA_DIR_ENV] = str(args.data_dir.expanduser().resolve())
    if args.edition:
        os.environ[EDITION_ENV] = args.edition
    clear_caches()


def _prepare(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.edition:
        parser.error("prepare-data requires --edition, for example --edition 2026c")
    output = args.output or args.data_dir or default_data_dir()
    print(DICOM_RIGHTS_NOTICE)
    print(
        "The official document and complete extracted tables are not redistributed by this project. "
        "The DOCX will be parsed locally; a downloaded temporary copy is deleted after generation."
    )
    try:
        if args.download:
            paths = download_and_generate(edition=args.edition, output=output, url=args.url)
        else:
            paths = generate_tables(args.source, edition=args.edition, output=output)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    os.environ[DATA_DIR_ENV] = str(Path(output).expanduser().resolve())
    os.environ[EDITION_ENV] = args.edition
    clear_caches()
    payload = {
        "installed": True,
        "edition": args.edition,
        "data_dir": str(Path(output).expanduser().resolve()),
        "files": [str(path) for path in paths],
        "bundled_with_project": False,
        "rights_notice": DICOM_RIGHTS_NOTICE,
    }
    print(json.dumps(payload, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_runtime(args)

    if args.command == "prepare-data":
        return _prepare(args, parser)
    if args.command == "info":
        status = data_status()
        if status["installed"]:
            try:
                status["provenance"] = table_metadata()
            except StandardsDataNotInstalledError:
                status["installed"] = False
        print(
            json.dumps(status, indent=2)
            if args.json
            else "\n".join(f"{key}: {value}" for key, value in status.items())
        )
        return 0

    try:
        selection = PolicySelection.from_strings(args.option, safe_private_tags=args.safe_private_tag)
        if args.command == "codes":
            code_matches = list(all_code_rules())
            if args.code:
                code_matches = [rule for rule in code_matches if rule.code_value == args.code]
            if args.scheme:
                code_matches = [rule for rule in code_matches if rule.coding_scheme_designator == args.scheme]
            if args.value_type:
                code_matches = [rule for rule in code_matches if rule.value_type == args.value_type]
            if args.meaning:
                needle = args.meaning.casefold()
                code_matches = [rule for rule in code_matches if needle in rule.code_meaning.casefold()]
            print(
                json.dumps([resolve_code_rule(rule, selection).to_dict() for rule in code_matches], indent=2)
            )
            return 0
        if args.command == "rules":
            attribute_matches = list(all_rules())
            if args.tag:
                rule = get_rule(args.tag)
                attribute_matches = [rule] if rule else []
            if args.name:
                needle = args.name.casefold()
                attribute_matches = [rule for rule in attribute_matches if needle in rule.name.casefold()]
            print(
                json.dumps([resolve_rule(rule, selection).to_dict() for rule in attribute_matches], indent=2)
            )
            return 0
        evaluation = evaluate_pair(
            args.source,
            args.candidate,
            selection,
            disclose_paths=args.disclose_paths,
            iod_aware=args.iod_aware,
            iod_registry_path=args.iod_registry,
        )
    except StandardsDataNotInstalledError as exc:
        parser.error(str(exc))

    payload = evaluation.to_dict()
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.json_path, payload, schema_name="ps315-evaluation")
    if args.csv_path:
        args.csv_path.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "path",
                    "tag",
                    "keyword",
                    "rule_name",
                    "expected",
                    "observed",
                    "status",
                    "reason",
                    "manual_review",
                    "iod_context",
                ],
            )
            writer.writeheader()
            for row in payload["results"]:
                writer.writerow(
                    {
                        **row,
                        "expected": "/".join(row["expected"]),
                        "iod_context": json.dumps(row.get("iod_context")),
                    }
                )
        restrict_file(args.csv_path)
    print(json.dumps(payload["summary"], indent=2))
    return 1 if payload["summary"]["fail"] or payload["summary"].get("operational_fail", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
