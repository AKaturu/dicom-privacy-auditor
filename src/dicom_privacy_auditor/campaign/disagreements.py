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


def _rule(
    *,
    family: str,
    disposition: str,
    confidence: str,
    basis: str,
    next_step: str,
    publication_treatment: str,
) -> dict[str, str]:
    return {
        "family": family,
        "disposition": disposition,
        "confidence": confidence,
        "basis": basis,
        "next_step": next_step,
        "publication_treatment": publication_treatment,
    }


def _adjudicate_action_cluster(action: str, internal_status: str, official_status: str) -> dict[str, str]:
    key = (action, internal_status, official_status)
    if key in {
        ("date shifted", "fail", "pass"),
        ("uid changed", "fail", "pass"),
        ("uid consistent", "fail", "pass"),
    }:
        return _rule(
            family="date_uid_presence_mapping_policy",
            disposition="internal_strict_false_negative_relative_to_official",
            confidence="high",
            basis=(
                "The official-compatible validator treats removal of the original value, including a "
                "missing candidate tag, as passing for changed-value checks; the internal comparator "
                "requires a present non-empty replacement or exact UID mapping."
            ),
            next_step="Add or use an official-compatible evaluator profile; keep strict replacement checks as sensitivity analysis.",
            publication_treatment="Use the official-compatible status for MIDI-B benchmark scoring.",
        )
    if key == ("pixels retained", "unresolved", "pass"):
        return _rule(
            family="pixel_comparison_capability",
            disposition="internal_unresolved_relative_to_official_digest_pass",
            confidence="high",
            basis=(
                "The internal comparator could not decode or compare pixel arrays, while the "
                "official-compatible result passed its retained-pixel check."
            ),
            next_step="Report as official pass and track the internal pixel decode limitation separately.",
            publication_treatment="Do not count this as a de-identification failure; disclose the internal unresolved count.",
        )
    if key == ("pixels hidden", "fail", "pass"):
        return _rule(
            family="pixel_semantic_ocr_policy",
            disposition="official_ocr_pass_internal_pixel_delta_fail",
            confidence="medium",
            basis=(
                "The official-compatible validator uses OCR/removal semantics for hidden text, while "
                "the internal comparator requires changed pixels in the bounding region."
            ),
            next_step="Manually spot-review the five hidden-pixel cases before making semantic image-redaction claims.",
            publication_treatment="Use official status for benchmark scoring; flag as manual-review priority.",
        )
    if action in {"text retained", "text removed"}:
        if internal_status == "fail" and official_status == "pass":
            return _rule(
                family="text_tokenization_policy",
                disposition="likely_internal_literal_false_negative_relative_to_official",
                confidence="medium_high",
                basis=(
                    "The official-compatible validator lowercases, strips wrapper characters, and "
                    "falls back to token-level checks; the internal comparator uses stricter literal "
                    "substring matching."
                ),
                next_step="Use sampled tag-level review to confirm the largest text clusters and align an official-compatible profile.",
                publication_treatment="Report official-compatible scoring; describe internal literal checks as conservative sensitivity.",
            )
        return _rule(
            family="text_tokenization_policy",
            disposition="sample_review_required",
            confidence="medium",
            basis=(
                "The two comparators disagree under different text matching policies, and the "
                "aggregate report intentionally omits raw values needed for final semantic review."
            ),
            next_step="Sample raw candidate/answer pairs under governed local access before claiming true semantic pass/fail.",
            publication_treatment="Do not use this cluster for strong semantic performance claims without sampled review.",
        )
    if action in {"tag retained", "text notnull"}:
        return _rule(
            family="tag_presence_null_policy",
            disposition="presence_or_null_representation_mismatch",
            confidence="medium",
            basis=(
                "The official-compatible validator evaluates tabular indexed values and null markers; "
                "the internal comparator evaluates pydicom element presence and stripped string content."
            ),
            next_step="Run tag-level sampled review for empty, null-marker, and absent-element cases.",
            publication_treatment="Treat as comparator-policy mismatch until sampled review confirms true candidate defects.",
        )
    return _rule(
        family="unclassified",
        disposition="manual_review_required",
        confidence="low",
        basis="No specific adjudication rule matched this action/status combination.",
        next_step="Inspect a governed sample and update the adjudication rubric.",
        publication_treatment="Exclude from strong claims until reviewed.",
    )


def _adjudicate_category_cluster(category: str, internal_status: str, official_status: str) -> dict[str, str]:
    if category in {"uid", "class_uid"} and internal_status == "fail" and official_status == "pass":
        return _rule(
            family="uid_presence_mapping_policy",
            disposition="internal_strict_false_negative_relative_to_official",
            confidence="high",
            basis="UID-family rows follow the changed/consistent UID policy mismatch identified at action level.",
            next_step="Use official-compatible UID semantics for MIDI-B scoring and strict UID replacement as sensitivity.",
            publication_treatment="Report as official-compatible pass cluster, not a confirmed candidate failure.",
        )
    if category.startswith("date") and internal_status == "fail" and official_status == "pass":
        return _rule(
            family="date_presence_policy",
            disposition="internal_strict_false_negative_relative_to_official",
            confidence="high",
            basis="Date-family rows follow the official policy where absent original dates pass changed-date checks.",
            next_step="Use official-compatible date-shift semantics for MIDI-B scoring.",
            publication_treatment="Report as official-compatible pass cluster, not a confirmed candidate failure.",
        )
    if category == "<blank>":
        return _rule(
            family="mixed_or_missing_answer_category",
            disposition="adjudicate_by_action_family",
            confidence="medium",
            basis=(
                "The normalized answer row did not carry a specific category in the aggregate report; "
                "the action-level adjudication is more informative for this bucket."
            ),
            next_step="Use action/status adjudications and optional tag-name enrichment for final reviewer tables.",
            publication_treatment="Do not present blank-category counts as a standalone semantic error family.",
        )
    if category in {"dicom_standard", "lut"}:
        return _rule(
            family="dicom_standard_presence_policy",
            disposition="presence_or_null_representation_mismatch",
            confidence="medium",
            basis="These rows are dominated by tag-retained/text-not-null presence semantics rather than raw PHI leakage.",
            next_step="Sample empty/null-marker and absent-element cases before semantic defect claims.",
            publication_treatment="Report as comparator-policy mismatch pending sampled review.",
        )
    if category in {"person_name", "patient_name", "description", "patient_address;comment"}:
        return _rule(
            family="text_phi_tokenization_policy",
            disposition="text_matching_policy_mismatch",
            confidence="medium",
            basis="These rows are text-bearing PHI categories where literal and tokenized checks can diverge.",
            next_step="Prioritize governed sampled review because these categories are most relevant to semantic PHI claims.",
            publication_treatment="Avoid strong semantic claims without sampled reviewer signoff.",
        )
    return _rule(
        family="unclassified",
        disposition="manual_review_required",
        confidence="low",
        basis="No specific category rule matched this category/status combination.",
        next_step="Inspect a governed sample and update the adjudication rubric.",
        publication_treatment="Exclude from strong claims until reviewed.",
    )


def _confusion_summary(confusion: dict[str, int]) -> dict[str, Any]:
    total = sum(confusion.values())
    official_pass = sum(count for key, count in confusion.items() if key.split("|")[-1] == "pass")
    official_fail = sum(count for key, count in confusion.items() if key.split("|")[-1] == "fail")
    internal_pass = sum(count for key, count in confusion.items() if key.split("|")[0] == "pass")
    internal_fail = sum(count for key, count in confusion.items() if key.split("|")[0] == "fail")
    return {
        "total": total,
        "official_pass": official_pass,
        "official_fail": official_fail,
        "official_score": official_pass / total if total else None,
        "internal_pass": internal_pass,
        "internal_fail": internal_fail,
        "internal_score_from_confusion": internal_pass / total if total else None,
    }


def _render_adjudication_markdown(payload: dict[str, Any]) -> str:
    def table(title: str, rows: list[dict[str, Any]], fields: list[str]) -> str:
        if not rows:
            return f"## {title}\n\nNo rows.\n"
        header = "| " + " | ".join(fields) + " |"
        divider = "| " + " | ".join("---" for _ in fields) + " |"
        body = ["| " + " | ".join(str(row.get(field, "")) for field in fields) + " |" for row in rows]
        return f"## {title}\n\n" + "\n".join([header, divider, *body]) + "\n"

    summary = payload["summary"]
    confusion = payload["confusion_summary"]
    lines = [
        "# MIDI-B Disagreement Category Adjudication",
        "",
        f"Generated: {payload['created_at']}",
        "",
        "## Scope",
        "",
        "This is an aggregate, reviewer-safe adjudication of disagreement families. It uses the prior "
        "disagreement report plus source-code review of the official-compatible validator and does not "
        "include raw answer values, patient identifiers, source paths, or pixel data.",
        "",
        "## Outcome",
        "",
        f"- Total disagreement rows: {summary['total_disagreements']}",
        f"- Action-cluster rows adjudicated in this report: {summary['action_cluster_rows']}",
        f"- Action-cluster coverage: {summary['action_cluster_coverage']}",
        f"- Official-compatible score from confusion matrix: {confusion['official_score']}",
        f"- Internal strict score from confusion matrix: {confusion['internal_score_from_confusion']}",
        "",
        "Publication treatment: report the official-compatible MIDI-B score with the confusion matrix. "
        "Use the internal strict score as a sensitivity analysis, not as the primary official-validator "
        "performance claim. Medium- and low-confidence clusters still need governed sampled review before "
        "strong semantic PHI-retention claims.",
        "",
        table(
            "Action Cluster Adjudication",
            payload["action_adjudications"],
            ["action", "internal_status", "official_status", "count", "family", "disposition", "confidence"],
        ),
        table(
            "Category Cluster Adjudication",
            payload["category_adjudications"],
            ["category", "internal_status", "official_status", "count", "family", "disposition", "confidence"],
        ),
        table(
            "Disposition Summary",
            payload["disposition_summary"],
            ["disposition", "count"],
        ),
        "## Reviewer Priorities",
        "",
        "1. Add an official-compatible evaluator profile for date/UID/tag/text/pixel semantics.",
        "2. Sample text-bearing PHI clusters before making semantic PHI-retention claims.",
        "3. Sample null-marker and absent-element cases for tag presence/null disagreements.",
        "4. Manually inspect the five hidden-pixel disagreements because they are small and clinically visible.",
        "",
    ]
    return "\n".join(lines)


def adjudicate_parity_disagreements(
    disagreement_json: str | Path,
    output_json: str | Path,
    *,
    report_markdown: str | Path | None = None,
) -> dict[str, Any]:
    """Adjudicate aggregate MIDI parity disagreement clusters without exposing raw values."""
    source = Path(disagreement_json)
    destination = Path(output_json)
    destination.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(report_markdown) if report_markdown else None
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)

    source_payload = json.loads(source.read_text(encoding="utf-8"))
    total_disagreements = int(source_payload.get("disagreement_count", 0))
    action_adjudications: list[dict[str, Any]] = []
    category_adjudications: list[dict[str, Any]] = []
    disposition_counter: Counter[tuple[str, ...]] = Counter()
    confidence_counter: Counter[tuple[str, ...]] = Counter()
    action_cluster_rows = 0
    category_cluster_rows = 0

    for row in source_payload.get("top_action_status_disagreements", []):
        count = int(row.get("count", 0))
        rule = _adjudicate_action_cluster(
            _label(row.get("action")),
            _label(row.get("internal_status")),
            _label(row.get("official_status")),
        )
        action_cluster_rows += count
        disposition_counter[(rule["disposition"],)] += count
        confidence_counter[(rule["confidence"],)] += count
        action_adjudications.append({**row, **rule})

    for row in source_payload.get("top_category_status_disagreements", []):
        count = int(row.get("count", 0))
        rule = _adjudicate_category_cluster(
            _label(row.get("category")),
            _label(row.get("internal_status")),
            _label(row.get("official_status")),
        )
        category_cluster_rows += count
        category_adjudications.append({**row, **rule})

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_disagreement_json_sha256": _sha256(source),
        "source_disagreement_schema_version": source_payload.get("schema_version"),
        "summary": {
            "total_disagreements": total_disagreements,
            "action_cluster_count": len(action_adjudications),
            "action_cluster_rows": action_cluster_rows,
            "action_cluster_coverage": action_cluster_rows / total_disagreements if total_disagreements else None,
            "category_cluster_count": len(category_adjudications),
            "category_cluster_rows": category_cluster_rows,
            "category_cluster_coverage": category_cluster_rows / total_disagreements if total_disagreements else None,
        },
        "confusion_summary": _confusion_summary(source_payload.get("confusion", {})),
        "disposition_summary": _top(disposition_counter, ("disposition",), limit=50),
        "confidence_summary": _top(confidence_counter, ("confidence",), limit=10),
        "action_adjudications": action_adjudications,
        "category_adjudications": category_adjudications,
        "publication_position": {
            "primary_score": "official_compatible_validator_score",
            "sensitivity_score": "internal_strict_evaluator_score",
            "strong_semantic_claims": "defer_until_medium_low_confidence_clusters_have_sampled_reviewer_signoff",
        },
    }
    atomic_write_text(destination, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    restrict_file(destination)
    if report_path:
        atomic_write_text(report_path, _render_adjudication_markdown(payload))
        restrict_file(report_path)
    return payload


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
