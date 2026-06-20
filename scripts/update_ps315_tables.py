#!/usr/bin/env python3
"""Generate user-local DICOM PS3.15 rule tables from an official Part 15 DOCX.

This compatibility wrapper delegates to the package generator. The project
intentionally does not store or redistribute the source DOCX or complete
extracted standards tables.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dicom_privacy_auditor.ps315.generate import (
    DICOM_RIGHTS_NOTICE,
    OFFICIAL_SOURCE_URL,
    download_and_generate,
    generate_tables,
)
from dicom_privacy_auditor.ps315.policy import default_data_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", required=True, help="Expected edition, for example 2026c")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source", type=Path, help="User-supplied official Part 15 DOCX")
    source.add_argument(
        "--download", action="store_true", help="Temporarily download the official current DOCX"
    )
    parser.add_argument("--url", default=OFFICIAL_SOURCE_URL, help="HTTPS URL used with --download")
    parser.add_argument("--output", type=Path, default=default_data_dir())
    args = parser.parse_args()

    print(DICOM_RIGHTS_NOTICE)
    if args.download:
        paths = download_and_generate(edition=args.edition, output=args.output, url=args.url)
    else:
        paths = generate_tables(args.source, edition=args.edition, output=args.output)
    for path in paths:
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
