from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class AdapterResult:
    status: str
    runtime_seconds: float
    details: dict[str, Any] = field(default_factory=dict)


class DeidentificationAdapter(Protocol):
    name: str

    def probe(self) -> dict[str, Any]: ...

    def process(self, source: Path, destination: Path, *, case_id: str) -> AdapterResult: ...

    def close(self) -> None: ...
