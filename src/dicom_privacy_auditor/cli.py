from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit_path
from .export import write_csv, write_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dicom-privacy-audit",
        description="Audit DICOM files for probable metadata, filesystem, and pixel-review privacy risks.",
    )
    parser.add_argument("path", type=Path, help="DICOM file or directory to audit")
    parser.add_argument("--json", dest="json_output", type=Path, help="Write a JSON report")
    parser.add_argument("--csv", dest="csv_output", type=Path, help="Write a CSV report")
    parser.add_argument("--force", action="store_true", help="Force pydicom to parse non-Part-10 files")
    parser.add_argument("--ignore-dates", action="store_true", help="Do not flag date/time attributes")
    parser.add_argument(
        "--review-uids", action="store_true", help="Flag instance-level UIDs for remapping review"
    )
    parser.add_argument(
        "--pixel-scan", action="store_true", help="Run the experimental high-contrast border-region scan"
    )
    parser.add_argument(
        "--show-source-paths",
        action="store_true",
        help="UNSAFE: include original source paths and filenames in console and reports",
    )
    parser.add_argument(
        "--show-values",
        action="store_true",
        help="UNSAFE: include raw DICOM values in console and reports instead of hashed/redacted evidence",
    )
    parser.add_argument(
        "--fail-on",
        choices=["never", "medium", "high", "critical"],
        default="never",
        help="Return exit status 2 when a finding at or above this severity is present",
    )
    return parser


def _should_fail(reports, threshold: str) -> bool:
    if threshold == "never":
        return False
    order = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
    target = order[threshold]
    return any(order.get(finding.severity, 0) >= target for report in reports for finding in report.findings)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.path.exists():
        print(f"Path does not exist: {args.path}", file=sys.stderr)
        return 1
    if args.show_values:
        print("WARNING: --show-values may copy identifiers into logs and report files.", file=sys.stderr)

    reports = audit_path(
        args.path,
        force=args.force,
        include_dates=not args.ignore_dates,
        include_uid_review=args.review_uids,
        inspect_pixels=args.pixel_scan,
        show_values=args.show_values,
        show_source_paths=args.show_source_paths,
    )
    if args.json_output:
        write_json(reports, args.json_output)
    if args.csv_output:
        write_csv(reports, args.csv_output)

    summary = {
        "files": len(reports),
        "readable": sum(report.readable for report in reports),
        "unreadable": sum(not report.readable for report in reports),
        "findings": sum(report.finding_count for report in reports),
        "max_risk_score": max((report.risk_score for report in reports), default=0),
        "raw_values_included": args.show_values,
        "source_paths_included": args.show_source_paths,
    }
    print(json.dumps(summary, indent=2))
    for report in reports:
        print(
            f"{report.source}: readable={report.readable} findings={report.finding_count} "
            f"risk={report.risk_score} highest={report.highest_severity}"
        )
        for finding in report.findings:
            evidence = f" evidence={finding.value_preview}" if finding.value_preview else ""
            print(f"  [{finding.severity.upper():8}] {finding.code}: {finding.message}{evidence}")

    return 2 if _should_fail(reports, args.fail_on) else 0


if __name__ == "__main__":
    raise SystemExit(main())
