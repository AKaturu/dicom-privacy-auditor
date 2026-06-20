from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class ProfileOption(str, Enum):
    RETAIN_SAFE_PRIVATE = "retain_safe_private"
    RETAIN_UIDS = "retain_uids"
    RETAIN_DEVICE_IDENTITY = "retain_device_identity"
    RETAIN_INSTITUTION_IDENTITY = "retain_institution_identity"
    RETAIN_PATIENT_CHARACTERISTICS = "retain_patient_characteristics"
    RETAIN_LONGITUDINAL_FULL_DATES = "retain_longitudinal_full_dates"
    RETAIN_LONGITUDINAL_MODIFIED_DATES = "retain_longitudinal_modified_dates"
    CLEAN_DESCRIPTORS = "clean_descriptors"
    CLEAN_STRUCTURED_CONTENT = "clean_structured_content"
    CLEAN_GRAPHICS = "clean_graphics"
    CLEAN_PIXEL_DATA = "clean_pixel_data"
    CLEAN_RECOGNIZABLE_VISUAL_FEATURES = "clean_recognizable_visual_features"


TABLE_OPTIONS: tuple[ProfileOption, ...] = (
    ProfileOption.RETAIN_SAFE_PRIVATE,
    ProfileOption.RETAIN_UIDS,
    ProfileOption.RETAIN_DEVICE_IDENTITY,
    ProfileOption.RETAIN_INSTITUTION_IDENTITY,
    ProfileOption.RETAIN_PATIENT_CHARACTERISTICS,
    ProfileOption.RETAIN_LONGITUDINAL_FULL_DATES,
    ProfileOption.RETAIN_LONGITUDINAL_MODIFIED_DATES,
    ProfileOption.CLEAN_DESCRIPTORS,
    ProfileOption.CLEAN_STRUCTURED_CONTENT,
    ProfileOption.CLEAN_GRAPHICS,
)


@dataclass(frozen=True)
class AttributeRule:
    name: str
    tag: str
    tag_hex: str | None
    retired: bool
    standard_composite_iod: bool
    actions: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodeRule:
    code_meaning: str
    code_value: str
    coding_scheme_designator: str
    value_type: str
    retired: bool
    standard_template: bool
    actions: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodeRuleResolution:
    rule: CodeRule
    directives: tuple[str, ...]
    directive_sources: tuple[str, ...]
    conflicts: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule.to_dict(),
            "directives": list(self.directives),
            "directive_sources": list(self.directive_sources),
            "conflicts": self.conflicts,
        }


@dataclass(frozen=True)
class PolicySelection:
    options: tuple[ProfileOption, ...] = ()
    safe_private_tags: frozenset[str] = frozenset()

    @classmethod
    def from_strings(
        cls,
        options: list[str] | tuple[str, ...] | None = None,
        *,
        safe_private_tags: list[str] | tuple[str, ...] | None = None,
    ) -> PolicySelection:
        selected = tuple(ProfileOption(item) for item in (options or []))
        normalized = frozenset(
            item.replace("(", "").replace(")", "").replace(",", "").upper()
            for item in (safe_private_tags or [])
        )
        return cls(options=selected, safe_private_tags=normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "options": [item.value for item in self.options],
            "safe_private_tags": sorted(self.safe_private_tags),
        }


@dataclass(frozen=True)
class RuleResolution:
    rule: AttributeRule
    directives: tuple[str, ...]
    directive_sources: tuple[str, ...]
    conflicts: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule.to_dict(),
            "directives": list(self.directives),
            "directive_sources": list(self.directive_sources),
            "conflicts": self.conflicts,
        }


@dataclass
class AttributeEvaluation:
    path: str
    tag: str
    keyword: str
    rule_name: str
    expected: list[str]
    observed: str
    status: str
    reason: str
    manual_review: bool = False
    iod_context: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProfileEvaluation:
    standard: str
    edition: str
    table: str
    selection: dict[str, Any]
    source: str
    candidate: str
    results: list[AttributeEvaluation] = field(default_factory=list)
    operational_checks: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    iod_summary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard": self.standard,
            "edition": self.edition,
            "table": self.table,
            "selection": self.selection,
            "source": self.source,
            "candidate": self.candidate,
            "summary": self.summary,
            "operational_checks": self.operational_checks,
            "iod_summary": self.iod_summary,
            "results": [item.to_dict() for item in self.results],
        }
