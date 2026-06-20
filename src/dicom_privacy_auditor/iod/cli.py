from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .registry import (
    IOD_DATA_DIR_ENV,
    IOD_EDITION_ENV,
    IodDataNotInstalledError,
    data_status,
    default_data_dir,
    load_registry,
    prepare_registry,
    resolve_context,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-iod")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--edition")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser(
        "prepare-data", help="Create a local IOD registry from user-supplied generated JSON"
    )
    prepare.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Directory, ZIP, or wheel containing ciods/sops/module JSON",
    )
    prepare.add_argument("--output", type=Path)
    info = sub.add_parser("info")
    info.add_argument("--json", action="store_true")
    sop = sub.add_parser("sop")
    sop.add_argument("uid")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.data_dir:
        os.environ[IOD_DATA_DIR_ENV] = str(args.data_dir.expanduser().resolve())
    if args.edition:
        os.environ[IOD_EDITION_ENV] = args.edition
    load_registry.cache_clear()
    if args.command == "prepare-data":
        if not args.edition:
            parser.error("prepare-data requires --edition")
        destination = prepare_registry(
            args.source, edition=args.edition, output=args.output or args.data_dir or default_data_dir()
        )
        print(
            json.dumps(
                {"installed": True, "registry": str(destination), "bundled_with_project": False}, indent=2
            )
        )
        return 0
    if args.command == "info":
        status = data_status()
        if status["installed"]:
            try:
                payload = load_registry()
                status["sop_classes"] = len(payload.get("sop_classes", {}))
                status["source_sha256"] = payload.get("source_sha256")
            except IodDataNotInstalledError:
                pass
        print(
            json.dumps(status, indent=2) if args.json else "\n".join(f"{k}: {v}" for k, v in status.items())
        )
        return 0
    try:
        print(json.dumps(resolve_context(args.uid).to_dict(), indent=2))
    except IodDataNotInstalledError as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
