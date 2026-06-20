from __future__ import annotations

import json
import os
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dicom_privacy_auditor.adapters.orthanc import OrthancAdapter
from dicom_privacy_auditor.adapters.rsna import RsnaCtpAdapter


def _assert_owner_only(path):
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


class _OrthancHandler(BaseHTTPRequestHandler):
    uploaded = b""
    upload_status = "Success"
    delete_count = 0

    def log_message(self, *_args):
        return None

    def do_GET(self):
        if self.path == "/system":
            body = json.dumps({"Version": "test", "ApiVersion": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        if self.path == "/instances":
            type(self).uploaded = body
            response = json.dumps({"ID": "abc", "Status": type(self).upload_status}).encode()
        elif self.path == "/instances/abc/anonymize":
            response = type(self).uploaded
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def do_DELETE(self):
        type(self).delete_count += 1
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()


def test_orthanc_adapter_uploads_anonymizes_and_cleans_up(tmp_path):
    _OrthancHandler.upload_status = "Success"
    _OrthancHandler.delete_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OrthancHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source = tmp_path / "input.dcm"
        source.write_bytes(b"DICOM-BYTES")
        destination = tmp_path / "output.dcm"
        adapter = OrthancAdapter({"base_url": f"http://127.0.0.1:{server.server_port}"})
        assert adapter.probe()["reachable"] is True
        result = adapter.process(source, destination, case_id="case-1")
        assert result.status == "ok"
        assert destination.read_bytes() == b"DICOM-BYTES"
        _assert_owner_only(destination)
        assert _OrthancHandler.delete_count == 1
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_orthanc_does_not_delete_preexisting_already_stored_instance(tmp_path):
    _OrthancHandler.upload_status = "AlreadyStored"
    _OrthancHandler.delete_count = 0
    server = ThreadingHTTPServer(("127.0.0.1", 0), _OrthancHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source = tmp_path / "input.dcm"
        source.write_bytes(b"DICOM-BYTES")
        destination = tmp_path / "output.dcm"
        adapter = OrthancAdapter({"base_url": f"http://127.0.0.1:{server.server_port}"})
        result = adapter.process(source, destination, case_id="already-there")
        assert result.status == "ok"
        assert result.details["uploaded_status"] == "AlreadyStored"
        assert _OrthancHandler.delete_count == 0
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_orthanc_security_guards(monkeypatch):
    with pytest.raises(ValueError, match="must use HTTPS"):
        OrthancAdapter({"base_url": "http://orthanc.example.test"})
    with pytest.raises(ValueError, match="Literal Orthanc credentials"):
        OrthancAdapter({"base_url": "http://127.0.0.1:8042", "username": "admin"})
    with pytest.raises(ValueError, match="verify_tls=false"):
        OrthancAdapter({"base_url": "https://orthanc.example.test", "verify_tls": False})
    monkeypatch.setenv("ORTHANC_TEST_USER", "user")
    monkeypatch.setenv("ORTHANC_TEST_PASSWORD", "secret")
    adapter = OrthancAdapter(
        {
            "base_url": "https://orthanc.example.test",
            "username_env": "ORTHANC_TEST_USER",
            "password_env": "ORTHANC_TEST_PASSWORD",
        }
    )
    assert adapter.username == "user"
    assert adapter.password == "secret"


def test_rsna_ctp_directory_adapter_waits_for_pipeline_output(tmp_path):
    incoming = tmp_path / "incoming"
    outgoing = tmp_path / "outgoing"
    incoming.mkdir()
    outgoing.mkdir()
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            for path in incoming.glob("*.dcm"):
                (outgoing / path.name).write_bytes(path.read_bytes())
                return
            time.sleep(0.01)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    source = tmp_path / "source.dcm"
    source.write_bytes(b"PROCESSED")
    destination = tmp_path / "destination.dcm"
    adapter = RsnaCtpAdapter(
        {"input_dir": str(incoming), "output_dir": str(outgoing), "timeout_seconds": 2, "poll_seconds": 0.02}
    )
    try:
        result = adapter.process(source, destination, case_id="safe-case")
        assert result.status == "ok"
        assert destination.read_bytes() == b"PROCESSED"
        _assert_owner_only(destination)
        assert not any(outgoing.iterdir())
    finally:
        stop.set()
        thread.join(timeout=1)
        adapter.close()


def test_rsna_anonymizer_adapter_uses_real_dicom_networking(tmp_path):
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid
    from pynetdicom import AE, evt
    from pynetdicom.sop_class import Verification

    from dicom_privacy_auditor.adapters.rsna import RsnaAnonymizerAdapter

    output_dir = tmp_path / "rsna-output"
    output_dir.mkdir()

    def handle_store(event):
        dataset = event.dataset
        dataset.file_meta = event.file_meta
        dataset.PatientName = "ANON"
        dataset.save_as(output_dir / "produced.dcm", enforce_file_format=True)
        return 0x0000

    server_ae = AE(ae_title="ANONYMIZER")
    server_ae.add_supported_context(Verification)
    server_ae.add_supported_context(SecondaryCaptureImageStorage, ExplicitVRLittleEndian)
    server = server_ae.start_server(
        ("127.0.0.1", 0), block=False, evt_handlers=[(evt.EVT_C_STORE, handle_store)]
    )
    port = server.server_address[1]

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    source = tmp_path / "network-source.dcm"
    dataset = FileDataset(str(source), {}, file_meta=meta, preamble=b"\0" * 128)
    dataset.SOPClassUID = SecondaryCaptureImageStorage
    dataset.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    dataset.PatientName = "DOE^JANE"
    dataset.PatientID = "P001"
    dataset.save_as(source, enforce_file_format=True)

    adapter = RsnaAnonymizerAdapter(
        {
            "host": "127.0.0.1",
            "port": port,
            "called_ae_title": "ANONYMIZER",
            "calling_ae_title": "DPAUDITOR",
            "output_dir": str(output_dir),
            "timeout_seconds": 3,
            "poll_seconds": 0.02,
        }
    )
    destination = tmp_path / "network-output.dcm"
    try:
        assert adapter.probe()["reachable"] is True
        result = adapter.process(source, destination, case_id="network-case")
        assert result.status == "ok"
        assert str(pydicom.dcmread(destination).PatientName) == "ANON"
        _assert_owner_only(destination)
        assert not any(output_dir.iterdir())
    finally:
        adapter.close()
        server.shutdown()


def test_directory_adapter_rejects_unsafe_case_id_and_overlapping_roots(tmp_path):
    from dicom_privacy_auditor.adapters.directory import DirectoryPipelineAdapter

    shared = tmp_path / "shared"
    shared.mkdir()
    with pytest.raises(ValueError, match="must not overlap"):
        DirectoryPipelineAdapter({"input_dir": str(shared), "output_dir": str(shared)})

    incoming = tmp_path / "incoming-safe"
    outgoing = tmp_path / "outgoing-safe"
    adapter = DirectoryPipelineAdapter({"input_dir": str(incoming), "output_dir": str(outgoing)})
    source = tmp_path / "source-safe.dcm"
    source.write_bytes(b"DICOM")
    try:
        with pytest.raises(ValueError, match="case_id"):
            adapter.process(source, tmp_path / "destination.dcm", case_id="../escape")
    finally:
        adapter.close()


def test_directory_adapter_enforces_input_byte_limit(tmp_path):
    from dicom_privacy_auditor.adapters.directory import DirectoryPipelineAdapter

    adapter = DirectoryPipelineAdapter(
        {
            "input_dir": str(tmp_path / "incoming-limit"),
            "output_dir": str(tmp_path / "outgoing-limit"),
            "max_input_bytes": 3,
            "timeout_seconds": 0.1,
            "poll_seconds": 0.01,
        }
    )
    source = tmp_path / "large-source.dcm"
    source.write_bytes(b"TOO-LARGE")
    try:
        with pytest.raises(RuntimeError, match="max_bytes"):
            adapter.process(source, tmp_path / "limited-output.dcm", case_id="safe")
        assert not any((tmp_path / "incoming-limit").iterdir())
    finally:
        adapter.close()


def test_orthanc_adapter_enforces_input_byte_limit_without_network(tmp_path):
    source = tmp_path / "large-input.dcm"
    source.write_bytes(b"TOO-LARGE")
    destination = tmp_path / "never-created.dcm"
    adapter = OrthancAdapter(
        {"base_url": "http://127.0.0.1:9", "max_request_bytes": 3, "timeout_seconds": 0.1}
    )
    with pytest.raises(RuntimeError, match="max_request_bytes"):
        adapter.process(source, destination, case_id="bounded")
    assert not destination.exists()


def test_adapter_rejects_symlink_source_and_destination(tmp_path):
    from dicom_privacy_auditor.permissions import atomic_copy_private

    source = tmp_path / "source.dcm"
    source.write_bytes(b"DICOM")
    source_link = tmp_path / "source-link.dcm"
    destination_target = tmp_path / "destination-target.dcm"
    destination_target.write_bytes(b"OLD")
    destination_link = tmp_path / "destination-link.dcm"
    try:
        source_link.symlink_to(source)
        destination_link.symlink_to(destination_target)
    except OSError:
        pytest.skip("symbolic links are unavailable on this platform")
    with pytest.raises(ValueError, match="Source"):
        atomic_copy_private(source_link, tmp_path / "out.dcm")
    with pytest.raises(ValueError, match="Destination"):
        atomic_copy_private(source, destination_link)
    assert destination_target.read_bytes() == b"OLD"
