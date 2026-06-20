from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from dicom_privacy_auditor.dicomweb import DicomwebClient, DicomwebConfig
from dicom_privacy_auditor.dicomweb.client import DicomwebError


class Handler(BaseHTTPRequestHandler):
    stored = b""

    def log_message(self, *_args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Allow", "GET,POST,OPTIONS")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/studies"):
            body = json.dumps([{"0020000D": {"vr": "UI", "Value": ["1.2.3"]}}]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/dicom+json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        Handler.stored = self.rfile.read(length)
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/dicom+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_dicomweb_https_guard_and_qido_stow(tmp_path):
    try:
        DicomwebClient(DicomwebConfig(base_url="http://example.test"))
        raise AssertionError("expected HTTPS guard")
    except ValueError:
        pass
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = DicomwebConfig(base_url=f"http://127.0.0.1:{server.server_port}", allow_insecure_http=True)
    sample = tmp_path / "sample.dcm"
    sample.write_bytes(b"DICOM")
    try:
        with DicomwebClient(config) as client:
            assert client.capabilities()["allow"]
            assert len(client.search_studies(max_results=1)) == 1
            result = client.store_instances([sample])
            assert result["instances"] == 1
            assert b"DICOM" in Handler.stored
    finally:
        server.shutdown()
        server.server_close()


def test_dicomweb_security_and_size_guards(tmp_path):
    with pytest.raises(ValueError, match="Literal authentication headers"):
        DicomwebConfig(
            base_url="https://example.test",
            headers={"Authorization": "Bearer secret"},
        )
    with pytest.raises(ValueError, match="allow_insecure_tls"):
        DicomwebConfig(base_url="https://example.test", verify_tls=False)
    config = DicomwebConfig(base_url="https://example.test", max_request_bytes=3)
    sample = tmp_path / "large.dcm"
    sample.write_bytes(b"DICOM")
    with DicomwebClient(config) as client:
        with pytest.raises(DicomwebError, match="max_request_bytes"):
            client.store_instances([sample])
