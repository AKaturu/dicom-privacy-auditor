from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class IodAttribute:
    module_id: str
    path: tuple[str, ...]
    type: str | None
    module_usage: str
    conditional_statement: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["path"] = list(self.path)
        return payload


@dataclass(frozen=True)
class IodContext:
    sop_class_uid: str
    sop_class_name: str | None
    ciod_id: str | None
    ciod_name: str | None
    registry_edition: str | None
    registry_source: str | None
    resolved: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IodEvaluationSummary:
    context: IodContext
    defined_attributes: int = 0
    undefined_attributes: int = 0
    type_1: int = 0
    type_1c: int = 0
    type_2: int = 0
    type_2c: int = 0
    type_3: int = 0
    unresolved_conditions: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["context"] = self.context.to_dict()
        return payload
