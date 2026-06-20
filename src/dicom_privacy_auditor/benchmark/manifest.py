from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ..jsonio import validate_payload, write_json

MANIFEST_VERSION = "1.0"


@dataclass
class Injection:
    injection_id: str
    stratum: str
    location_kind: str
    path: str
    value: str
    value_sha256: str
    keyword: str | None = None
    tag: str | None = None
    bbox_xyxy: tuple[int, int, int, int] | None = None
    description: str | None = None
    expected_action: str = "remove_or_transform"


def _validated_case_id(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value) is None:
        raise ValueError("case_id must be a portable 1-128 character identifier")
    return value


def _validated_relative_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or "\x00" in normalized
        or ":" in normalized
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError(f"Unsafe benchmark relative path: {value!r}")
    return path.as_posix()


@dataclass
class CaseRecord:
    case_id: str
    relative_path: str
    modality: str
    clean_control: bool
    injections: list[Injection] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.case_id = _validated_case_id(self.case_id)
        self.relative_path = _validated_relative_path(self.relative_path)


@dataclass
class BenchmarkManifest:
    benchmark_name: str
    version: str
    manifest_version: str
    seed: int
    standard_reference: str
    cases: list[CaseRecord]
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        case_ids = [case.case_id for case in self.cases]
        relative_paths = [case.relative_path for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("benchmark manifest contains duplicate case_id values")
        if len(relative_paths) != len(set(relative_paths)):
            raise ValueError("benchmark manifest contains duplicate relative_path values")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def write(self, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_json(target, self.to_dict(), schema_name="benchmark-manifest")

    @classmethod
    def read(cls, path: str | Path) -> BenchmarkManifest:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        validate_payload(payload, "benchmark-manifest")
        cases: list[CaseRecord] = []
        for raw_case in payload["cases"]:
            case_payload = dict(raw_case)
            injections = [Injection(**item) for item in case_payload.pop("injections", [])]
            cases.append(CaseRecord(injections=injections, **case_payload))
        return cls(cases=cases, **{key: value for key, value in payload.items() if key != "cases"})
