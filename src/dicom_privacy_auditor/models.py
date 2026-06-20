from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SEVERITY_ORDER = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}
SEVERITY_WEIGHTS = {"info": 0, "low": 1, "medium": 3, "high": 7, "critical": 12}


@dataclass(frozen=True)
class Finding:
    """A single privacy-risk finding.

    ``value_preview`` is redacted by default by the audit engine. ``value_hash`` is a
    one-way SHA-256 prefix that allows repeated values to be correlated without
    copying the original value into reports.
    """

    code: str
    severity: str
    category: str
    message: str
    path: str | None = None
    tag: str | None = None
    keyword: str | None = None
    value_preview: str | None = None
    value_hash: str | None = None
    value_length: int | None = None
    recommendation: str | None = None
    evidence: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AuditReport:
    """Audit result for one DICOM object or path-level artifact."""

    source: str
    readable: bool
    source_id: str | None = None
    file_sha256: str | None = None
    sop_class_uid: str | None = None
    sop_instance_uid_hash: str | None = None
    modality: str | None = None
    transfer_syntax_uid: str | None = None
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def highest_severity(self) -> str:
        if not self.findings:
            return "info"
        return max(self.findings, key=lambda f: SEVERITY_ORDER.get(f.severity, 0)).severity

    @property
    def risk_score(self) -> int:
        return sum(SEVERITY_WEIGHTS.get(f.severity, 0) for f in self.findings)

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    def counts_by_severity(self) -> dict[str, int]:
        counts = {key: 0 for key in SEVERITY_ORDER}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts

    def counts_by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.category] = counts.get(finding.category, 0) + 1
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": str(Path(self.source)),
            "source_id": self.source_id,
            "file_sha256": self.file_sha256,
            "readable": self.readable,
            "sop_class_uid": self.sop_class_uid,
            "sop_instance_uid_hash": self.sop_instance_uid_hash,
            "modality": self.modality,
            "transfer_syntax_uid": self.transfer_syntax_uid,
            "highest_severity": self.highest_severity,
            "risk_score": self.risk_score,
            "finding_count": self.finding_count,
            "counts_by_severity": self.counts_by_severity(),
            "counts_by_category": self.counts_by_category(),
            "error": self.error,
            "metadata": self.metadata,
            "findings": [finding.to_dict() for finding in self.findings],
        }
