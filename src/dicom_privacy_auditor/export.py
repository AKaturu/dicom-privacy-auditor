from __future__ import annotations

import csv
import json
from pathlib import Path

from .jsonio import write_json as atomic_write_json
from .models import AuditReport
from .permissions import restrict_file


def write_json(reports: list[AuditReport], output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(path, [report.to_dict() for report in reports], schema_name="audit-report-list")


def write_csv(reports: list[AuditReport], output: str | Path) -> None:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "source",
        "source_id",
        "file_sha256",
        "readable",
        "modality",
        "sop_class_uid",
        "sop_instance_uid_hash",
        "transfer_syntax_uid",
        "risk_score",
        "highest_severity",
        "code",
        "severity",
        "category",
        "path",
        "tag",
        "keyword",
        "message",
        "value_preview",
        "value_hash",
        "value_length",
        "recommendation",
        "evidence",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for report in reports:
            base = {
                "source": report.source,
                "source_id": report.source_id,
                "file_sha256": report.file_sha256,
                "readable": report.readable,
                "modality": report.modality,
                "sop_class_uid": report.sop_class_uid,
                "sop_instance_uid_hash": report.sop_instance_uid_hash,
                "transfer_syntax_uid": report.transfer_syntax_uid,
                "risk_score": report.risk_score,
                "highest_severity": report.highest_severity,
                "error": report.error,
            }
            if not report.findings:
                writer.writerow(base)
                continue
            for finding in report.findings:
                writer.writerow(
                    {
                        **base,
                        "code": finding.code,
                        "severity": finding.severity,
                        "category": finding.category,
                        "path": finding.path,
                        "tag": finding.tag,
                        "keyword": finding.keyword,
                        "message": finding.message,
                        "value_preview": finding.value_preview,
                        "value_hash": finding.value_hash,
                        "value_length": finding.value_length,
                        "recommendation": finding.recommendation,
                        "evidence": json.dumps(finding.evidence, sort_keys=True)
                        if finding.evidence
                        else None,
                    }
                )
    restrict_file(path)
