from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..permissions import atomic_copy_private, validate_file_transfer
from .base import AdapterResult
from .directory import DirectoryPipelineAdapter
from .util import launch, snapshot, terminate, validate_case_id, wait_for_new_file


class RsnaCtpAdapter(DirectoryPipelineAdapter):
    """RSNA CTP adapter for DirectoryImportService -> anonymizer -> DirectoryStorageService pipelines."""

    def __init__(self, config: dict[str, Any]):
        super().__init__(config, name="rsna-ctp")


class RsnaAnonymizerAdapter:
    """Adapter for the RSNA DICOM Anonymizer running as a headless DICOM SCP.

    The adapter can launch ``rsna-anonymizer -c <ProjectModel.json>`` or
    connect to an already running project. It transmits one instance at a time
    and collects the newly written anonymized object from the project's storage tree.
    """

    name = "rsna-anonymizer"

    def __init__(self, config: dict[str, Any]):
        self.host = str(config.get("host", "127.0.0.1"))
        self.port = int(config.get("port", 1045))
        self.called_ae_title = str(config.get("called_ae_title", "ANONYMIZER"))
        self.calling_ae_title = str(config.get("calling_ae_title", "DPAUDITOR"))
        self.output_dir = Path(config["output_dir"]).resolve()
        self.timeout = float(config.get("timeout_seconds", 120))
        self.poll = float(config.get("poll_seconds", 0.5))
        self.startup_seconds = float(config.get("startup_seconds", 3))
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
            raise ValueError("RSNA timeout/poll/byte limits must be positive and startup non-negative")
        if self.output_dir.is_symlink():
            raise ValueError("RSNA output directory must not be a symbolic link")
        command = config.get("start_command")
        if command is None and config.get("project_model"):
            command = [config.get("executable", "rsna-anonymizer"), "-c", str(config["project_model"])]
        self.process_handle = launch(command, cwd=config.get("working_directory"))
        self.stop_process = bool(config.get("stop_process_on_close", self.process_handle is not None))
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if self.process_handle and self.startup_seconds:
            time.sleep(self.startup_seconds)

    def probe(self) -> dict[str, Any]:
        try:
            from pynetdicom import AE
            from pynetdicom.sop_class import Verification  # type: ignore[attr-defined]
        except ImportError as exc:
            raise RuntimeError("RSNA Anonymizer adapter requires the 'adapters' extra (pynetdicom)") from exc
        ae = AE(ae_title=self.calling_ae_title)
        ae.add_requested_context(Verification)
        association = ae.associate(self.host, self.port, ae_title=self.called_ae_title)
        if not association.is_established:
            return {"adapter": self.name, "reachable": False}
        status = association.send_c_echo()
        association.release()
        return {"adapter": self.name, "reachable": bool(status and status.Status == 0x0000)}

    def process(self, source: Path, destination: Path, *, case_id: str) -> AdapterResult:
        try:
            import pydicom
            from pynetdicom import AE
            from pynetdicom.presentation import build_context
        except ImportError as exc:
            raise RuntimeError("RSNA Anonymizer adapter requires the 'adapters' extra (pynetdicom)") from exc
        start = time.perf_counter()
        validate_case_id(case_id)
        source_path, destination_path = validate_file_transfer(source, destination)
        if source_path.stat().st_size > self.max_input_bytes:
            raise RuntimeError("RSNA source exceeded max_input_bytes")
        before = snapshot(self.output_dir)
        dataset = pydicom.dcmread(source_path)
        ae = AE(ae_title=self.calling_ae_title)
        transfer_syntax = str(dataset.file_meta.TransferSyntaxUID)
        ae.requested_contexts = [build_context(str(dataset.SOPClassUID), [transfer_syntax])]
        association = ae.associate(self.host, self.port, ae_title=self.called_ae_title)
        if not association.is_established:
            raise ConnectionError("Could not associate with the RSNA Anonymizer DICOM SCP")
        status = association.send_c_store(dataset)
        association.release()
        if not status or status.Status not in range(0x0000, 0x0100):
            code = getattr(status, "Status", None)
            raise RuntimeError(f"RSNA Anonymizer C-STORE failed with status {code!r}")
        produced = wait_for_new_file(
            self.output_dir, before, timeout_seconds=self.timeout, poll_seconds=self.poll
        )
        try:
            atomic_copy_private(produced, destination_path, max_bytes=self.max_output_bytes)
        finally:
            if self.cleanup_output and not produced.is_symlink():
                produced.unlink(missing_ok=True)
        return AdapterResult(
            status="ok",
            runtime_seconds=time.perf_counter() - start,
            details={
                "case_id": case_id,
                "c_store_status": int(status.Status),
                "output_bytes": destination.stat().st_size,
            },
        )

    def close(self) -> None:
        if self.stop_process:
            terminate(self.process_handle)
