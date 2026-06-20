from __future__ import annotations

import base64
import ipaddress
import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..http_utils import build_no_redirect_opener, validate_http_url
from ..permissions import atomic_write_bytes_private, validate_file_transfer
from .base import AdapterResult

LOGGER = logging.getLogger(__name__)


def _is_loopback_url(url: str) -> bool:
    host = urllib.parse.urlparse(url).hostname
    if host in {"localhost", "localhost.localdomain"}:
        return True
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


class OrthancAdapter:
    name = "orthanc"

    def __init__(self, config: dict[str, Any]):
        self.base_url = str(config.get("base_url", "http://127.0.0.1:8042")).rstrip("/")
        parsed = validate_http_url(self.base_url, allow_query=False)
        if parsed.scheme == "http" and not _is_loopback_url(self.base_url):
            if not bool(config.get("allow_insecure_http", False)):
                raise ValueError("Remote Orthanc endpoints must use HTTPS unless allow_insecure_http=true")

        literal_username = config.get("username")
        literal_password = config.get("password")
        username_env = config.get("username_env")
        password_env = config.get("password_env")
        if (literal_username is not None or literal_password is not None) and not bool(
            config.get("allow_literal_credentials", False)
        ):
            raise ValueError("Literal Orthanc credentials are disabled; use username_env/password_env")
        if username_env or password_env:
            if not username_env or not password_env:
                raise ValueError("Both Orthanc username_env and password_env are required")
            literal_username = os.environ.get(str(username_env))
            literal_password = os.environ.get(str(password_env))
            if literal_username is None or literal_password is None:
                raise ValueError("Orthanc credential environment variables are not set")
        self.username = literal_username
        self.password = literal_password
        if self.username is not None and parsed.scheme == "http" and not _is_loopback_url(self.base_url):
            raise ValueError("Authenticated remote Orthanc endpoints must use HTTPS")

        self.timeout = float(config.get("timeout_seconds", 120))
        self.max_request_bytes = int(config.get("max_request_bytes", 2 * 1024 * 1024 * 1024))
        self.max_response_bytes = int(config.get("max_response_bytes", 2 * 1024 * 1024 * 1024))
        self.include_error_body = bool(config.get("include_error_body", False))
        if self.timeout <= 0 or self.max_request_bytes <= 0 or self.max_response_bytes <= 0:
            raise ValueError("Orthanc timeout and request/response limits must be positive")

        verify_tls = config.get("verify_tls", True)
        allow_insecure_tls = bool(config.get("allow_insecure_tls", False))
        if verify_tls is False:
            if not allow_insecure_tls:
                raise ValueError("Orthanc verify_tls=false requires allow_insecure_tls=true")
            self.ssl_context: ssl.SSLContext | None = ssl._create_unverified_context()  # nosec B323
        elif isinstance(verify_tls, str):
            self.ssl_context = ssl.create_default_context(cafile=verify_tls)
        else:
            self.ssl_context = None

        self._opener = build_no_redirect_opener(self.ssl_context)

        self.cleanup_uploaded = bool(config.get("cleanup_uploaded", True))
        # Deleting an instance reported as AlreadyStored could remove a
        # pre-existing Orthanc object that this run did not create.
        self.cleanup_already_stored = bool(config.get("cleanup_already_stored", False))
        self.anonymize_body = {
            key: value
            for key, value in {
                "DicomVersion": config.get("dicom_version", "2023b"),
                "Keep": config.get("keep"),
                "Remove": config.get("remove"),
                "Replace": config.get("replace"),
                "KeepPrivateTags": config.get("keep_private_tags"),
                "Force": config.get("force"),
            }.items()
            if value is not None
        }

    def _request(
        self, method: str, path: str, data: bytes | None = None, content_type: str | None = None
    ) -> bytes:
        if data is not None and len(data) > self.max_request_bytes:
            raise RuntimeError("Orthanc request exceeded max_request_bytes")
        headers = {}
        if content_type:
            headers["Content-Type"] = content_type
        if self.username is not None:
            token = base64.b64encode(f"{self.username}:{self.password or ''}".encode()).decode()
            headers["Authorization"] = f"Basic {token}"
        request = urllib.request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                declared = int(response.headers.get("Content-Length", "0") or 0)
                if declared > self.max_response_bytes:
                    raise RuntimeError("Orthanc response exceeded max_response_bytes")
                payload = response.read(self.max_response_bytes + 1)
                if len(payload) > self.max_response_bytes:
                    raise RuntimeError("Orthanc response exceeded max_response_bytes")
                return payload
        except urllib.error.HTTPError as exc:
            suffix = ""
            if self.include_error_body:
                detail = exc.read(501).decode("utf-8", errors="replace")[:500]
                suffix = f": {detail}" if detail else ""
            raise RuntimeError(f"Orthanc HTTP {exc.code}{suffix}") from exc

    def probe(self) -> dict[str, Any]:
        payload = json.loads(self._request("GET", "/system"))
        return {
            "adapter": self.name,
            "reachable": True,
            "orthanc_version": payload.get("Version"),
            "api_version": payload.get("ApiVersion"),
        }

    def process(self, source: Path, destination: Path, *, case_id: str) -> AdapterResult:
        start = time.perf_counter()
        uploaded_id = None
        uploaded_status = None
        try:
            source_path, destination_path = validate_file_transfer(source, destination)
            if source_path.stat().st_size > self.max_request_bytes:
                raise RuntimeError("Orthanc source exceeded max_request_bytes")
            with source_path.open("rb") as handle:
                source_payload = handle.read(self.max_request_bytes + 1)
            if len(source_payload) > self.max_request_bytes:
                raise RuntimeError("Orthanc source exceeded max_request_bytes")
            response = json.loads(self._request("POST", "/instances", source_payload, "application/dicom"))
            uploaded_id = response.get("ID")
            uploaded_status = str(response.get("Status", ""))
            if not uploaded_id:
                raise RuntimeError("Orthanc upload response did not include an instance ID")
            body = json.dumps(self.anonymize_body).encode("utf-8")
            anonymized = self._request(
                "POST", f"/instances/{uploaded_id}/anonymize", body, "application/json"
            )
            atomic_write_bytes_private(destination_path, anonymized)
            return AdapterResult(
                status="ok",
                runtime_seconds=time.perf_counter() - start,
                details={
                    "case_id": case_id,
                    "uploaded_status": uploaded_status,
                    "bytes_written": len(anonymized),
                },
            )
        finally:
            may_delete = (uploaded_status or "").casefold() != "alreadystored" or self.cleanup_already_stored
            if uploaded_id and self.cleanup_uploaded and may_delete:
                try:
                    self._request("DELETE", f"/instances/{uploaded_id}")
                except Exception as exc:
                    LOGGER.warning("Orthanc cleanup failed for uploaded object %s: %s", uploaded_id, exc)

    def close(self) -> None:
        return None
