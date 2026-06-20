from __future__ import annotations

import argparse
import json
from pathlib import Path

from .benchmark.midi import evaluate_midi, import_midi, inspect_answer_key


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-midi")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Inspect a MIDI-B SQLite answer key")
    inspect.add_argument("answer_key", type=Path)
    imported = sub.add_parser("import", help="Normalize a MIDI-B answer key and index its source DICOM files")
    imported.add_argument("answer_key", type=Path)
    imported.add_argument("dicom_root", type=Path)
    imported.add_argument("output", type=Path)
    imported.add_argument("--dataset-name", default="MIDI-B")
    imported.add_argument("--patient-mapping", type=Path)
    imported.add_argument("--uid-mapping", type=Path)
    imported.add_argument(
        "--column-map", type=Path, help="JSON mapping normalized field names to SQLite columns"
    )
    imported.add_argument("--overwrite", action="store_true")
    evaluate = sub.add_parser(
        "evaluate", help="Evaluate candidate DICOM files against an imported MIDI-B key"
    )
    evaluate.add_argument("imported", type=Path)
    evaluate.add_argument("candidate", type=Path)
    evaluate.add_argument("output", type=Path)
    evaluate.add_argument("--patient-mapping", type=Path)
    evaluate.add_argument("--uid-mapping", type=Path)
    evaluate.add_argument(
        "--source-root",
        type=Path,
        help="Override the source path stored in a migrated MIDI import manifest",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        print(json.dumps(inspect_answer_key(args.answer_key), indent=2))
        return 0
    if args.command == "import":
        overrides = json.loads(args.column_map.read_text(encoding="utf-8")) if args.column_map else None
        manifest = import_midi(
            args.answer_key,
            args.dicom_root,
            args.output,
            dataset_name=args.dataset_name,
            patient_mapping=args.patient_mapping,
            uid_mapping=args.uid_mapping,
            column_overrides=overrides,
            overwrite=args.overwrite,
        )
        print(json.dumps(manifest.to_dict(), indent=2))
        return 0
    evaluation = evaluate_midi(
        args.imported,
        args.candidate,
        args.output,
        patient_mapping=args.patient_mapping,
        uid_mapping=args.uid_mapping,
        source_root=args.source_root,
    )
    print(json.dumps(evaluation.summary, indent=2))
    return 1 if evaluation.summary["failed"] or evaluation.summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
