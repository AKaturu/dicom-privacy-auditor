from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CorpusFinding:
    code: str
    severity: str
    scope: str
    source_key: str | None
    candidate_key: str | None
    message: str
    count: int = 1
    examples: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["examples"] = list(self.examples)
        return payload


@dataclass
class CorpusReport:
    source: str
    candidate: str
    pairing: str
    pairs: int
    source_only: int
    candidate_only: int
    findings: list[CorpusFinding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "candidate": self.candidate,
            "pairing": self.pairing,
            "pairs": self.pairs,
            "source_only": self.source_only,
            "candidate_only": self.candidate_only,
            "metrics": self.metrics,
            "findings": [item.to_dict() for item in self.findings],
        }
