from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..dicomweb import DicomwebClient, DicomwebConfig
from ..jsonio import write_json
from .workflow import index_studies, process_directory, process_study


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-study")
    sub = parser.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index")
    index.add_argument("source", type=Path)
    process = sub.add_parser("process-local")
    process.add_argument("source", type=Path)
    process.add_argument("destination", type=Path)
    process.add_argument(
        "--pipeline",
        default="baseline",
        choices=["baseline", "noop", "orthanc", "rsna-anonymizer", "rsna-ctp", "directory"],
    )
    process.add_argument("--adapter-config", type=Path)
    process.add_argument("--overwrite", action="store_true")
    process.add_argument("--quarantine", type=Path)
    process.add_argument("--commit-partial", action="store_true")
    web = sub.add_parser("process-dicomweb")
    web.add_argument("study_uid")
    web.add_argument("workspace", type=Path)
    web.add_argument("--source-config", type=Path, required=True)
    web.add_argument("--destination-config", type=Path, required=True)
    web.add_argument(
        "--pipeline",
        default="baseline",
        choices=["baseline", "noop", "orthanc", "rsna-anonymizer", "rsna-ctp", "directory"],
    )
    web.add_argument("--adapter-config", type=Path)
    web.add_argument("--overwrite", action="store_true")
    return parser


def _json(path: Path | None) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path else {}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "index":
        studies = index_studies(args.source)
        print(json.dumps({uid: len(paths) for uid, paths in studies.items()}, indent=2))
        return 0
    if args.command == "process-local":
        runs = process_directory(
            args.source,
            args.destination,
            pipeline=args.pipeline,
            adapter_config=_json(args.adapter_config),
            overwrite=args.overwrite,
            quarantine_root=args.quarantine,
        )
        print(json.dumps([run.to_dict() for run in runs], indent=2))
        return 1 if any(run.status == "failed" for run in runs) else 0
    source_dir = args.workspace / "source"
    processed_dir = args.workspace / "processed"
    args.workspace.mkdir(parents=True, exist_ok=True)
    with DicomwebClient(DicomwebConfig.from_json(args.source_config)) as source_client:
        source_client.retrieve_study(args.study_uid, source_dir)
    run = process_study(
        list(index_studies(source_dir).get(args.study_uid, [])),
        processed_dir,
        pipeline=args.pipeline,
        adapter_config=_json(args.adapter_config),
        overwrite=args.overwrite,
        quarantine_root=args.workspace / "quarantine",
    )
    if run.status != "complete":
        stored = {"status": "skipped", "reason": "Study processing was not complete"}
    else:
        output_paths = sorted(Path(run.output_directory).glob("*.dcm"))
        with DicomwebClient(DicomwebConfig.from_json(args.destination_config)) as destination_client:
            stored = destination_client.store_instances(output_paths)
    payload = {"run": run.to_dict(), "store": stored}
    write_json(args.workspace / "dicomweb-run.json", payload, schema_name="dicomweb-study-run")
    print(json.dumps(payload, indent=2))
    return 0 if run.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
