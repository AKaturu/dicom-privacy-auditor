from __future__ import annotations

import argparse
import json
from pathlib import Path

from .deidentify import UIDMapper, baseline_deidentify_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dicom-privacy-baseline-deid",
        description="Run the transparent research baseline de-identifier on one DICOM file.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--uid-salt", default="DPA-BENCHMARK-ONLY")
    parser.add_argument(
        "--pixel-bbox",
        nargs=4,
        action="append",
        type=int,
        metavar=("X1", "Y1", "X2", "Y2"),
        help="Synthetic/reviewed pixel rectangle to clean; may be repeated",
    )
    args = parser.parse_args(argv)
    stats = baseline_deidentify_file(
        args.source,
        args.destination,
        uid_mapper=UIDMapper(args.uid_salt),
        pixel_bboxes=[tuple(values) for values in (args.pixel_bbox or [])],
    )
    print(json.dumps(stats.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
