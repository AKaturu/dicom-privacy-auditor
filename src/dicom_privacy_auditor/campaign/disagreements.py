from __future__ import annotations

import csv
import json
from collections import Counter
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..permissions import atomic_write_text, restrict_file
from .evidence import _canonical_status, _sha256


def _label(value: Any, *, blank: str = "<blank>") -> str:
    text = str(value if value is not None else "").strip()
    return text if text else blank


def _iter_result_csv(path: Path, *, label: str) -> Iterator[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or "action_id" not in reader.fieldnames or "status" not in reader.fieldnames:
            raise ValueError(f"{label} CSV must contain action_id and status columns")
        for row in reader:
            action_id = _label(row.get("action_id"), blank="")
            if not action_id:
                raise ValueError(f"every {label} row requires action_id")
            yield {
                "action_id": action_id,
                "action": _label(row.get("action")),
                "category": _label(row.get("category")),
                "reason": _label(row.get("reason")),
                "status": _canonical_status(row.get("status", "")),
                "source_present": _label(row.get("source_present")),
                "candidate_present": _label(row.get("candidate_present")),
            }


def _top(counter: Counter[tuple[str, ...]], fields: tuple[str, ...], *, limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, count in counter.most_common(limit):
        row = {field: value for field, value in zip(fields, key, strict=True)}
        row["count"] = count
        rows.append(row)
    return rows


def _render_markdown(payload: dict[str, Any]) -> str:
    def table(title: str, rows: list[dict[str, Any]], fields: list[str]) -> str:
        if not rows:
            return f"## {title}\n\nNo rows.\n"
        header = "| " + " | ".join(fields + ["count"]) + " |"
        divider = "| " + " | ".join("---" for _ in fields + ["count"]) + " |"
        body = [
            "| "
            + " | ".join(str(row.get(field, "")) for field in fields + ["count"])
            + " |"
            for row in rows
        ]
        return f"## {title}\n\n" + "\n".join([header, divider, *body]) + "\n"

    lines = [
        "# MIDI-B Parity Disagreement Review",
        "",
        f"Generated: {payload['created_at']}",
        "",
        "## Summary",
        "",
        f"- Internal rows: {payload['internal_row_count']}",
        f"- Official rows: {payload['official_row_count']}",
        f"- Union actions: {payload['union_action_count']}",
        f"- Exact status matches: {payload['exact_status_matches']}",
        f"- Exact status agreement: {payload['exact_status_agreement']}",
        f"- Disagreements: {payload['disagreement_count']}",
        "",
        "This report is an aggregate review artifact. It excludes raw answer values, patient identifiers, "
        "file paths, and DICOM pixel data.",
        "",
        table(
            "Top Action/Status Disagreements",
            payload["top_action_status_disagreements"],
            ["action", "internal_status", "official_status"],
        ),
        table("Top Actions", payload["top_actions"], ["action"]),
        table("Top Categories", payload["top_categories"], ["category"]),
        table(
            "Top Internal Reasons",
            payload["top_internal_reasons"],
            ["reason", "internal_status", "official_status"],
        ),
    ]
    tag_summary = payload.get("tag_enrichment")
    if tag_summary:
        lines.extend(
            [
                "## Tag Enrichment",
                "",
                f"- Actions rows scanned: {tag_summary['actions_rows_scanned']}",
                f"- Disagreement IDs matched to action metadata: {tag_summary['matched_disagreement_actions']}",
                "",
                table("Top Tag Names", tag_summary["top_tag_names"], ["tag_name"]),
                table(
                    "Top Action/Tag/Status Disagreements",
                    tag_summary["top_action_tag_status_disagreements"],
                    ["action", "tag_name", "internal_status", "official_status"],
                ),
            ]
        )
    lines.extend(
        [
            "## Interpretation Guardrails",
            "",
            "- Use this report to prioritize reviewer investigation, not as a standalone clinical validation claim.",
            "- Status disagreements may reflect evaluator policy differences, official runtime patches, "
            "or implementation defects in either comparator.",
            "- Public artifacts should include aggregate counts, hashes, and methods only.",
            "",
        ]
    )
    return "\n".join(lines)


def analyze_parity_disagreements(
    internal_file: str | Path,
    official_file: str | Path,
    output_json: str | Path,
    *,
    report_markdown: str | Path | None = None,
    actions_jsonl: str | Path | None = None,
    top_n: int = 25,
    sample_limit: int = 0,
) -> dict[str, Any]:
    """Create aggregate, reviewer-safe summaries of internal/official MIDI disagreement clusters."""
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    if sample_limit < 0:
        raise ValueError("sample_limit must be non-negative")

    internal_path = Path(internal_file)
    official_path = Path(official_file)
    destination = Path(output_json)
    destination.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(report_markdown) if report_markdown else None
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
    actions_path = Path(actions_jsonl) if actions_jsonl else None

    action_counter: Counter[tuple[str, ...]] = Counter()
    category_counter: Counter[tuple[str, ...]] = Counter()
    reason_counter: Counter[tuple[str, ...]] = Counter()
    action_status_counter: Counter[tuple[str, ...]] = Counter()
    category_status_counter: Counter[tuple[str, ...]] = Counter()
    presence_counter: Counter[tuple[str, ...]] = Counter()
    confusion: Counter[tuple[str, ...]] = Counter()
    samples: list[dict[str, str]] = []
    official_count = 0
    internal_count = 0
    exact_matches = 0
    disagreement_count = 0
    tag_enrichment: dict[str, Any] | None = None
    official_by_id: dict[str, tuple[str, str]] = {}
    discrepant_by_id: dict[str, tuple[str, str, str]] = {}

    def record_disagreement(
        *,
        action_id: str,
        action: str,
        category: str,
        reason: str,
        internal_status: str,
        official_status: str,
        source_present: str,
        candidate_present: str,
    ) -> None:
        nonlocal disagreement_count
        disagreement_count += 1
        action_counter[(action,)] += 1
        category_counter[(category,)] += 1
        reason_counter[(reason, internal_status, official_status)] += 1
        action_status_counter[(action, internal_status, official_status)] += 1
        category_status_counter[(category, internal_status, official_status)] += 1
        presence_counter[(source_present, candidate_present, internal_status, official_status)] += 1
        if len(samples) < sample_limit:
            samples.append(
                {
                    "action_id": action_id,
                    "action": action,
                    "category": category,
                    "reason": reason,
                    "internal_status": internal_status,
                    "official_status": official_status,
                }
            )
        discrepant_by_id[action_id] = (action, internal_status, official_status)

    for row in _iter_result_csv(official_path, label="official"):
        official_count += 1
        if row["action_id"] in official_by_id:
            raise ValueError(f"duplicate official action_id: {row['action_id']}")
        official_by_id[row["action_id"]] = (row["action"], row["status"])

    for row in _iter_result_csv(internal_path, label="internal"):
        internal_count += 1
        official_row = official_by_id.pop(row["action_id"], None)
        internal_status = row["status"]
        official_status = str(official_row[1]) if official_row else "missing"
        confusion[(internal_status, official_status)] += 1
        if internal_status == official_status:
            exact_matches += 1
            continue
        record_disagreement(
            action_id=row["action_id"],
            action=row["action"] or (str(official_row[0]) if official_row else "<blank>"),
            category=row["category"],
            reason=row["reason"],
            internal_status=internal_status,
            official_status=official_status,
            source_present=row["source_present"],
            candidate_present=row["candidate_present"],
        )

    for action_id, (action, official_status) in official_by_id.items():
        confusion[("missing", str(official_status))] += 1
        record_disagreement(
            action_id=str(action_id),
            action=_label(action),
            category="<missing internal>",
            reason="internal row missing",
            internal_status="missing",
            official_status=str(official_status),
            source_present="<missing internal>",
            candidate_present="<missing internal>",
        )
    official_by_id.clear()

    if actions_path:
        tag_counter: Counter[tuple[str, ...]] = Counter()
        action_tag_status_counter: Counter[tuple[str, ...]] = Counter()
        actions_rows_scanned = 0
        matched = 0
        with actions_path.open(encoding="utf-8") as handle:
            for line in handle:
                actions_rows_scanned += 1
                row = json.loads(line)
                action_id = _label(row.get("action_id"), blank="")
                if not action_id:
                    continue
                mismatch = discrepant_by_id.get(action_id)
                if mismatch is None:
                    continue
                matched += 1
                tag_name = _label(row.get("tag_name"))
                tag_counter[(tag_name,)] += 1
                action_tag_status_counter[(mismatch[0], tag_name, mismatch[1], mismatch[2])] += 1
        tag_enrichment = {
            "actions_sha256": _sha256(actions_path),
            "actions_rows_scanned": actions_rows_scanned,
            "matched_disagreement_actions": matched,
            "top_tag_names": _top(tag_counter, ("tag_name",), limit=top_n),
            "top_action_tag_status_disagreements": _top(
                action_tag_status_counter,
                ("action", "tag_name", "internal_status", "official_status"),
                limit=top_n,
            ),
        }

    try:
        union_count = exact_matches + disagreement_count
        payload: dict[str, Any] = {
            "schema_version": "1.0",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "internal_sha256": _sha256(internal_path),
            "official_sha256": _sha256(official_path),
            "internal_row_count": internal_count,
            "official_row_count": official_count,
            "union_action_count": union_count,
            "exact_status_matches": exact_matches,
            "exact_status_agreement": exact_matches / union_count if union_count else None,
            "disagreement_count": disagreement_count,
            "confusion": {"|".join(key): value for key, value in sorted(confusion.items())},
            "top_actions": _top(action_counter, ("action",), limit=top_n),
            "top_categories": _top(category_counter, ("category",), limit=top_n),
            "top_internal_reasons": _top(
                reason_counter, ("reason", "internal_status", "official_status"), limit=top_n
            ),
            "top_action_status_disagreements": _top(
                action_status_counter, ("action", "internal_status", "official_status"), limit=top_n
            ),
            "top_category_status_disagreements": _top(
                category_status_counter, ("category", "internal_status", "official_status"), limit=top_n
            ),
            "top_presence_status_disagreements": _top(
                presence_counter,
                ("source_present", "candidate_present", "internal_status", "official_status"),
                limit=top_n,
            ),
            "sample_limit": sample_limit,
            "sample_disagreements": samples,
        }
        if tag_enrichment:
            payload["tag_enrichment"] = tag_enrichment

        atomic_write_text(destination, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        restrict_file(destination)
        if report_path:
            atomic_write_text(report_path, _render_markdown(payload))
            restrict_file(report_path)
        return payload
    finally:
        official_by_id.clear()
        discrepant_by_id.clear()
