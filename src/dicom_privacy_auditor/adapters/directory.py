from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..permissions import atomic_copy_private
from .base import AdapterResult
from .util import (
    launch,
    snapshot,
    terminate,
    validate_case_id,
    validate_watched_directories,
    wait_for_new_file,
)


class DirectoryPipelineAdapter:
    """Adapter for a watched input/output directory pipeline such as RSNA CTP."""

    name = "directory"

    def __init__(self, config: dict[str, Any], *, name: str = "directory"):
        self.name = name
        self.input_dir = Path(config["input_dir"]).resolve()
        self.output_dir = Path(config["output_dir"]).resolve()
        self.timeout = float(config.get("timeout_seconds", 120))
        self.poll = float(config.get("poll_seconds", 0.5))
        self.startup_seconds = float(config.get("startup_seconds", 0))
        self.max_input_bytes = int(config.get("max_input_bytes", 2 * 1024 * 1024 * 1024))
        self.max_output_bytes = int(config.get("max_output_bytes", 2 * 1024 * 1024 * 1024))
        self.cleanup_output = bool(config.get("cleanup_output", True))
        if (
            self.timeout <= 0
            or self.poll <= 0
            or self.startup_seconds < 0
            or self.max_input_bytes <= 0
            or self.max_output_bytes <= 0
        ):
            raise ValueError(
                "directory adapter timeout/poll/byte limits must be positive and startup non-negative"
            )
        self.input_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        validate_watched_directories(self.input_dir, self.output_dir)
        self.process_handle = launch(config.get("start_command"), cwd=config.get("working_directory"))
        self.stop_process = bool(config.get("stop_process_on_close", self.process_handle is not None))
        if self.process_handle and self.startup_seconds:
            time.sleep(self.startup_seconds)

    def probe(self) -> dict[str, Any]:
        return {
            "adapter": self.name,
            "input_directory_exists": self.input_dir.is_dir(),
            "output_directory_exists": self.output_dir.is_dir(),
            "managed_process_running": bool(self.process_handle and self.process_handle.poll() is None),
        }

    def process(self, source: Path, destination: Path, *, case_id: str) -> AdapterResult:
        start = time.perf_counter()
        safe_case_id = validate_case_id(case_id)
        before = snapshot(self.output_dir)
        safe_input = self.input_dir / f"{safe_case_id}.dcm"
        if safe_input.exists() or safe_input.is_symlink():
            raise FileExistsError(f"directory adapter input already exists: {safe_input}")
        atomic_copy_private(source, safe_input, max_bytes=self.max_input_bytes)
        produced: Path | None = None
        try:
            produced = wait_for_new_file(
                self.output_dir, before, timeout_seconds=self.timeout, poll_seconds=self.poll
            )
            atomic_copy_private(produced, destination, max_bytes=self.max_output_bytes)
        finally:
            safe_input.unlink(missing_ok=True)
            if self.cleanup_output and produced is not None and not produced.is_symlink():
                produced.unlink(missing_ok=True)
        return AdapterResult(
            status="ok",
            runtime_seconds=time.perf_counter() - start,
            details={"case_id": case_id, "output_bytes": destination.stat().st_size},
        )

    def close(self) -> None:
        if self.stop_process:
            terminate(self.process_handle)
