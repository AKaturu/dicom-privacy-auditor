from __future__ import annotations

import argparse
import ipaddress
import json
import os
import subprocess
import sys
from pathlib import Path

from .review.migrations import migrate_database
from .review.models import REVIEW_SCOPES, REVIEW_STATUSES, ReviewDecision
from .review.store import ReviewStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-review")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="Create a paired source/candidate review database")
    create.add_argument("source", type=Path)
    create.add_argument("candidate", type=Path)
    create.add_argument("database", type=Path)
    create.add_argument("--title", default="DICOM privacy review")
    create.add_argument("--overwrite", action="store_true")
    summary = sub.add_parser("summary")
    summary.add_argument("database", type=Path)
    schema_info = sub.add_parser("schema-info", help="Show review database schema status")
    schema_info.add_argument("database", type=Path)
    migrate = sub.add_parser("migrate", help="Upgrade a review database with a safety backup")
    migrate.add_argument("database", type=Path)
    migrate.add_argument("--no-backup", action="store_true")
    decide = sub.add_parser("decide")
    decide.add_argument("database", type=Path)
    decide.add_argument("case_id")
    decide.add_argument("--reviewer", required=True)
    decide.add_argument("--scope", choices=REVIEW_SCOPES, required=True)
    decide.add_argument("--target", required=True)
    decide.add_argument("--status", choices=REVIEW_STATUSES, required=True)
    decide.add_argument("--comment", default="")
    decide.add_argument("--frame", type=int)
    decide.add_argument("--region", nargs=4, type=int)
    export = sub.add_parser("export")
    export.add_argument("database", type=Path)
    export.add_argument("output", type=Path)
    export.add_argument("--disclose-paths", action="store_true")
    agreement = sub.add_parser("agreement")
    agreement.add_argument("database", type=Path)
    agreement.add_argument("reviewer_a")
    agreement.add_argument("reviewer_b")
    disagreements = sub.add_parser(
        "disagreements", help="Create a blinded-review disagreement/adjudication packet"
    )
    disagreements.add_argument("database", type=Path)
    disagreements.add_argument("reviewer_a")
    disagreements.add_argument("reviewer_b")
    disagreements.add_argument("--output", type=Path)
    integrity = sub.add_parser("integrity-check", help="Check SQLite and foreign-key integrity")
    integrity.add_argument("database", type=Path)
    serve = sub.add_parser("serve")
    serve.add_argument("database", type=Path)
    serve.add_argument("--port", type=int, default=8502)
    serve.add_argument("--address", default="127.0.0.1")
    serve.add_argument(
        "--allow-network",
        action="store_true",
        help="Explicitly permit binding the review UI to a non-loopback address",
    )
    serve.add_argument(
        "--unblinded",
        action="store_true",
        help="Allow reviewers to see other reviewers' decisions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = ReviewStore(args.database)
    if args.command == "create":
        count = store.initialize(args.source, args.candidate, title=args.title, overwrite=args.overwrite)
        print(json.dumps({"database": str(args.database), "cases": count}, indent=2))
        return 0
    if args.command == "summary":
        print(json.dumps(store.summary(), indent=2))
        return 0
    if args.command == "schema-info":
        print(json.dumps(store.schema_info(), indent=2))
        return 0
    if args.command == "migrate":
        print(json.dumps(migrate_database(args.database, backup=not args.no_backup), indent=2))
        return 0
    if args.command == "decide":
        decision_id = store.add_decision(
            ReviewDecision(
                None,
                args.case_id,
                args.reviewer,
                args.scope,
                args.target,
                args.status,
                args.comment,
                args.frame,
                tuple(args.region) if args.region else None,
            )
        )
        print(json.dumps({"decision_id": decision_id}, indent=2))
        return 0
    if args.command == "export":
        print(store.export(args.output, disclose_paths=args.disclose_paths))
        return 0
    if args.command == "agreement":
        print(json.dumps(store.agreement(args.reviewer_a, args.reviewer_b).to_dict(), indent=2))
        return 0
    if args.command == "disagreements":
        if args.output:
            print(store.export_disagreements(args.output, args.reviewer_a, args.reviewer_b))
        else:
            print(json.dumps(store.disagreement_report(args.reviewer_a, args.reviewer_b), indent=2))
        return 0
    if args.command == "integrity-check":
        payload = store.integrity_check()
        print(json.dumps(payload, indent=2))
        return 0 if payload["ok"] else 2
    try:
        is_loopback = args.address.casefold() == "localhost" or ipaddress.ip_address(args.address).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback and not args.allow_network:
        raise SystemExit("Refusing non-loopback review UI binding without --allow-network")
    app = Path(__file__).with_name("review_app.py")
    env = {
        **os.environ,
        "DICOM_PRIVACY_REVIEW_DB": str(args.database.resolve()),
        "DICOM_PRIVACY_REVIEW_BLINDED": "0" if args.unblinded else "1",
    }
    return subprocess.call(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app),
            "--server.port",
            str(args.port),
            "--server.address",
            args.address,
            "--server.headless",
            "true",
        ],
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
