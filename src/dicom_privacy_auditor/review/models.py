from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

REVIEW_STATUSES = (
    "confirmed_identifier",
    "false_positive",
    "acceptable_retention",
    "needs_secondary_review",
    "not_reviewed",
)
REVIEW_SCOPES = ("case", "metadata", "pixel", "region")


@dataclass(frozen=True)
class ReviewCase:
    case_id: str
    source_path: str
    candidate_path: str
    study_uid: str | None = None
    series_uid: str | None = None
    source_sop_uid: str | None = None
    candidate_sop_uid: str | None = None
    modality: str | None = None
    frame_count: int = 1
    status: str = "pending"
    assigned_reviewer: str | None = None
    priority: int = 0
    updated_at: str | None = None

    def to_dict(self, *, disclose_paths: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if not disclose_paths:
            payload["source_path"] = "redacted"
            payload["candidate_path"] = "redacted"
        return payload


@dataclass(frozen=True)
class ReviewDecision:
    decision_id: int | None
    case_id: str
    reviewer: str
    scope: str
    target: str
    status: str
    comment: str = ""
    frame_number: int | None = None
    region: tuple[int, int, int, int] | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["region"] = list(self.region) if self.region is not None else None
        return payload


@dataclass
class AgreementReport:
    reviewer_a: str
    reviewer_b: str
    labels: list[str]
    matched_targets: int
    exact_agreement: float | None
    cohen_kappa: float | None
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    unmatched_a: int = 0
    unmatched_b: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
