from __future__ import annotations

from typing import Any

from .base import DeidentificationAdapter
from .directory import DirectoryPipelineAdapter
from .orthanc import OrthancAdapter
from .rsna import RsnaAnonymizerAdapter, RsnaCtpAdapter


def create_adapter(name: str, config: dict[str, Any]) -> DeidentificationAdapter:
    if name == "orthanc":
        return OrthancAdapter(config)
    if name == "rsna-anonymizer":
        return RsnaAnonymizerAdapter(config)
    if name == "rsna-ctp":
        return RsnaCtpAdapter(config)
    if name == "directory":
        return DirectoryPipelineAdapter(config)
    raise ValueError(f"Unknown adapter: {name}")
