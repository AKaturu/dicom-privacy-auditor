from __future__ import annotations

import argparse
import json
from pathlib import Path

from .disagreements import analyze_parity_disagreements
from .evidence import (
    MAX_EVIDENCE_ARCHIVE_MEMBERS,
    MAX_EVIDENCE_UNCOMPRESSED_BYTES,
    archive_evidence_package,
    build_evidence_package,
    compare_evaluators,
    compare_evaluators_streaming,
    generate_review_sample,
    verify_evidence_package,
)
from .midi_live import (
    DEFAULT_OFFICIAL_VALIDATOR_TIMEOUT_SECONDS,
    finalize_tool,
    preflight_campaign,
    run_campaign,
    run_tool,
)
from .official_midi import normalize_official_midi_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dicom-privacy-campaign")
    sub = parser.add_subparsers(dest="command", required=True)
    tool = sub.add_parser("run-tool", help="Process a complete imported MIDI-B corpus through one live tool")
    tool.add_argument("imported", type=Path)
    tool.add_argument("workspace", type=Path)
    tool.add_argument(
        "--tool",
        required=True,
        choices=["noop", "baseline", "orthanc", "rsna-anonymizer", "rsna-ctp", "directory"],
    )
    tool.add_argument("--config", type=Path)
    tool.add_argument("--official-validator-command", type=Path, help="JSON array command template")
    tool.add_argument(
        "--official-validator-timeout-seconds",
        type=float,
        default=DEFAULT_OFFICIAL_VALIDATOR_TIMEOUT_SECONDS,
        help="Maximum runtime for the official validator command (default: 3600)",
    )
    tool.add_argument("--overwrite", action="store_true")
    tool.add_argument(
        "--source-root", type=Path, help="Override the source path stored in the MIDI import manifest"
    )
    tool.add_argument("--shard-index", type=int, default=0)
    tool.add_argument("--shard-count", type=int, default=1)
    tool.add_argument(
        "--no-evaluate", action="store_true", help="Process files without running final MIDI evaluation"
    )
    preflight = sub.add_parser("preflight", help="Validate an imported MIDI corpus before a long campaign")
    preflight.add_argument("imported", type=Path)
    preflight.add_argument("--source-root", type=Path)
    finalize = sub.add_parser("finalize-tool", help="Evaluate an already processed complete tool output")
    finalize.add_argument("imported", type=Path)
    finalize.add_argument("workspace", type=Path)
    finalize.add_argument("--tool", required=True)
    finalize.add_argument("--official-validator-command", type=Path)
    finalize.add_argument(
        "--official-validator-timeout-seconds",
        type=float,
        default=DEFAULT_OFFICIAL_VALIDATOR_TIMEOUT_SECONDS,
        help="Maximum runtime for the official validator command (default: 3600)",
    )
    finalize.add_argument("--source-root", type=Path)
    sample = sub.add_parser("review-sample", help="Create a deterministic stratified human-review sample")
    sample.add_argument("evaluation", type=Path)
    sample.add_argument("output", type=Path)
    sample.add_argument("--failures-per-stratum", type=int, default=25)
    sample.add_argument("--controls-per-stratum", type=int, default=10)
    sample.add_argument("--seed", type=int, default=20260620)
    parity = sub.add_parser("parity", help="Compare internal and normalized official action-level results")
    parity.add_argument("internal", type=Path)
    parity.add_argument("official", type=Path)
    parity.add_argument("output", type=Path)
    parity_stream = sub.add_parser(
        "parity-stream", help="Compare large CSV/JSON evaluator outputs with bounded memory"
    )
    parity_stream.add_argument("internal", type=Path)
    parity_stream.add_argument("official", type=Path)
    parity_stream.add_argument("output", type=Path)
    parity_stream.add_argument("--discrepancy-limit", type=int, default=10_000)
    normalize = sub.add_parser(
        "normalize-official-midi",
        help="Normalize official MIDI validator SQLite results to action_id/action/status CSV",
    )
    normalize.add_argument("official_db", type=Path)
    normalize.add_argument("answer_db", type=Path)
    normalize.add_argument("uid_mapping", type=Path)
    normalize.add_argument("output", type=Path)
    normalize.add_argument("--unmatched-output", type=Path)
    review = sub.add_parser(
        "review-disagreements",
        help="Summarize evaluator disagreement clusters without exposing raw values",
    )
    review.add_argument("internal", type=Path)
    review.add_argument("official", type=Path)
    review.add_argument("output", type=Path)
    review.add_argument("--report-markdown", type=Path)
    review.add_argument("--actions-jsonl", type=Path)
    review.add_argument("--top-n", type=int, default=25)
    review.add_argument("--sample-limit", type=int, default=0)
    evidence = sub.add_parser(
        "evidence-package", help="Build a redacted, checksummed campaign evidence package"
    )
    evidence.add_argument("workspace", type=Path)
    evidence.add_argument("destination", type=Path)
    evidence.add_argument("--campaign-id", required=True)
    evidence.add_argument("--overwrite", action="store_true")
    verify = sub.add_parser("verify-evidence", help="Verify an evidence directory or tar.gz archive")
    verify.add_argument("package", type=Path)
    verify.add_argument("--max-members", type=int, default=MAX_EVIDENCE_ARCHIVE_MEMBERS)
    verify.add_argument(
        "--max-uncompressed-bytes",
        type=int,
        default=MAX_EVIDENCE_UNCOMPRESSED_BYTES,
    )
    archive = sub.add_parser("archive-evidence", help="Create a deterministic verified evidence tar.gz")
    archive.add_argument("evidence_directory", type=Path)
    archive.add_argument("archive", type=Path)
    archive.add_argument("--source-date-epoch", type=int, default=0)
    archive.add_argument("--overwrite", action="store_true")
    archive.add_argument("--max-members", type=int, default=MAX_EVIDENCE_ARCHIVE_MEMBERS)
    archive.add_argument(
        "--max-uncompressed-bytes",
        type=int,
        default=MAX_EVIDENCE_UNCOMPRESSED_BYTES,
    )
    all_tools = sub.add_parser("run", help="Run a JSON campaign definition")
    all_tools.add_argument("imported", type=Path)
    all_tools.add_argument("workspace", type=Path)
    all_tools.add_argument("definition", type=Path)
    all_tools.add_argument("--overwrite", action="store_true")
    all_tools.add_argument(
        "--source-root",
        type=Path,
        help="Override the source path stored in a migrated MIDI import manifest",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "review-sample":
        payload = generate_review_sample(
            args.evaluation,
            args.output,
            failures_per_stratum=args.failures_per_stratum,
            controls_per_stratum=args.controls_per_stratum,
            seed=args.seed,
        )
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "parity":
        payload = compare_evaluators(args.internal, args.official, args.output)
        print(json.dumps(payload, indent=2))
        return 0 if payload["discrepancy_count"] == 0 else 2
    if args.command == "parity-stream":
        payload = compare_evaluators_streaming(
            args.internal,
            args.official,
            args.output,
            discrepancy_limit=args.discrepancy_limit,
        )
        print(json.dumps(payload, indent=2))
        return 0 if payload["discrepancy_count"] == 0 else 2
    if args.command == "normalize-official-midi":
        payload = normalize_official_midi_results(
            args.official_db,
            args.answer_db,
            args.uid_mapping,
            args.output,
            unmatched_output=args.unmatched_output,
        )
        print(json.dumps(payload, indent=2))
        return 0 if payload["unmatched_rows"] == 0 else 2
    if args.command == "review-disagreements":
        payload = analyze_parity_disagreements(
            args.internal,
            args.official,
            args.output,
            report_markdown=args.report_markdown,
            actions_jsonl=args.actions_jsonl,
            top_n=args.top_n,
            sample_limit=args.sample_limit,
        )
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "evidence-package":
        payload = build_evidence_package(
            args.workspace, args.destination, campaign_id=args.campaign_id, overwrite=args.overwrite
        )
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "verify-evidence":
        payload = verify_evidence_package(
            args.package,
            max_members=args.max_members,
            max_uncompressed_bytes=args.max_uncompressed_bytes,
        )
        print(json.dumps(payload, indent=2))
        return 0 if payload["valid"] else 2
    if args.command == "archive-evidence":
        payload = archive_evidence_package(
            args.evidence_directory,
            args.archive,
            source_date_epoch=args.source_date_epoch,
            overwrite=args.overwrite,
            max_members=args.max_members,
            max_uncompressed_bytes=args.max_uncompressed_bytes,
        )
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "preflight":
        payload = preflight_campaign(args.imported, source_root=args.source_root)
        print(json.dumps(payload, indent=2))
        return 0 if payload["status"] == "ready" else 1
    if args.command == "finalize-tool":
        command = (
            json.loads(args.official_validator_command.read_text(encoding="utf-8"))
            if args.official_validator_command
            else None
        )
        result = finalize_tool(
            args.imported,
            args.workspace,
            tool=args.tool,
            official_validator_command=command,
            official_validator_timeout_seconds=args.official_validator_timeout_seconds,
            source_root=args.source_root,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0
    if args.command == "run-tool":
        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else {}
        command = (
            json.loads(args.official_validator_command.read_text(encoding="utf-8"))
            if args.official_validator_command
            else None
        )
        result = run_tool(
            args.imported,
            args.workspace,
            tool=args.tool,
            adapter_config=config,
            overwrite=args.overwrite,
            official_validator_command=command,
            official_validator_timeout_seconds=args.official_validator_timeout_seconds,
            source_root=args.source_root,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            evaluate=not args.no_evaluate,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status == "complete" else 1
    definition = json.loads(args.definition.read_text(encoding="utf-8"))
    payload = run_campaign(
        args.imported,
        args.workspace,
        definition["tools"],
        overwrite=args.overwrite,
        source_root=args.source_root,
    )
    print(json.dumps(payload, indent=2))
    return 0 if all(item["status"] == "complete" for item in payload["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
