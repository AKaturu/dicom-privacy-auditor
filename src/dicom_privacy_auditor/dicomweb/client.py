from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..http_utils import validate_http_url


class DicomwebError(RuntimeError):
    pass


def _close_response(response: Any) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()


@dataclass(frozen=True)
class DicomwebConfig:
    base_url: str
    headers: dict[str, str] = field(default_factory=dict)
    bearer_token_env: str | None = None
    username_env: str | None = None
    password_env: str | None = None
    verify_tls: bool | str = True
    timeout_seconds: float = 60.0
    max_retries: int = 3
    allow_insecure_http: bool = False
    allow_insecure_tls: bool = False
    allow_literal_secret_headers: bool = False
    include_error_body: bool = False
    max_response_bytes: int = 2 * 1024 * 1024 * 1024
    max_request_bytes: int = 2 * 1024 * 1024 * 1024

    def __post_init__(self) -> None:
        parsed = validate_http_url(self.base_url, allow_query=False)
        if parsed.scheme.lower() == "http" and not self.allow_insecure_http:
            raise ValueError("DICOMweb base_url must use HTTPS unless allow_insecure_http=true")
        if self.verify_tls is False and not self.allow_insecure_tls:
            raise ValueError("verify_tls=false requires allow_insecure_tls=true")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("timeout_seconds must be positive and max_retries cannot be negative")
        if self.max_response_bytes <= 0 or self.max_request_bytes <= 0:
            raise ValueError("DICOMweb request/response limits must be positive")
        secret_headers = {key.lower() for key in self.headers} & {
            "authorization",
            "cookie",
            "proxy-authorization",
        }
        if secret_headers and not self.allow_literal_secret_headers:
            raise ValueError(
                "Literal authentication headers are disabled; use bearer_token_env or username_env/password_env"
            )
        authentication_configured = bool(
            secret_headers or self.bearer_token_env or self.username_env or self.password_env
        )
        if authentication_configured and parsed.scheme.lower() != "https":
            raise ValueError("Authenticated DICOMweb endpoints must use HTTPS")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DicomwebConfig:
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"Unknown DICOMweb configuration fields: {sorted(unknown)}")
        return cls(**payload)

    @classmethod
    def from_json(cls, path: str | Path) -> DicomwebConfig:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def redacted(self) -> dict[str, Any]:
        payload = {
            "base_url": self.base_url,
            "headers": {
                key: "<redacted>"
                if key.lower() in {"authorization", "cookie", "proxy-authorization"}
                else value
                for key, value in self.headers.items()
            },
            "bearer_token_env": self.bearer_token_env,
            "username_env": self.username_env,
            "password_env": self.password_env,
            "verify_tls": self.verify_tls,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "allow_insecure_http": self.allow_insecure_http,
            "allow_insecure_tls": self.allow_insecure_tls,
            "allow_literal_secret_headers": self.allow_literal_secret_headers,
            "include_error_body": self.include_error_body,
            "max_response_bytes": self.max_response_bytes,
            "max_request_bytes": self.max_request_bytes,
        }
        return payload


def _validated_uid(value: str, label: str) -> str:
    text = str(value)
    component = r"(?:0|[1-9][0-9]*)"
    if len(text) > 64 or re.fullmatch(rf"{component}(?:\.{component})*", text) is None:
        raise ValueError(f"{label} is not a valid DICOM UID")
    return text


class DicomwebClient:
    def __init__(self, config: DicomwebConfig):
        self.config = config
        self.base_url = config.base_url.rstrip("/") + "/"
        self.session = requests.Session()
        retry = Retry(
            total=config.max_retries,
            connect=config.max_retries,
            read=config.max_retries,
            status=config.max_retries,
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS", "POST"}),
            status_forcelist=(429, 500, 502, 503, 504),
            backoff_factor=0.5,
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.mount("http://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(config.headers)
        if config.bearer_token_env:
            token = os.environ.get(config.bearer_token_env)
            if not token:
                raise ValueError(f"Environment variable {config.bearer_token_env} is not set")
            self.session.headers["Authorization"] = f"Bearer {token}"
        if config.username_env or config.password_env:
            if not config.username_env or not config.password_env:
                raise ValueError("Both username_env and password_env are required for basic authentication")
            username = os.environ.get(config.username_env)
            password = os.environ.get(config.password_env)
            if username is None or password is None:
                raise ValueError("DICOMweb basic-auth environment variables are not set")
            self.session.auth = (username, password)

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> DicomwebClient:
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def _request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.config.timeout_seconds)
        kwargs.setdefault("verify", self.config.verify_tls)
        kwargs.setdefault("allow_redirects", False)
        response = self.session.request(method, self._url(path), **kwargs)
        if int(response.headers.get("Content-Length", "0") or 0) > self.config.max_response_bytes:
            _close_response(response)
            raise DicomwebError("DICOMweb response exceeded max_response_bytes")
        if 300 <= response.status_code < 400:
            _close_response(response)
            raise DicomwebError(f"{method} {path} returned a refused redirect ({response.status_code})")
        if not response.ok:
            suffix = ""
            if self.config.include_error_body and response.content:
                suffix = ": " + response.text[:500].replace("\r", " ").replace("\n", " ")
            status_code = response.status_code
            _close_response(response)
            raise DicomwebError(f"{method} {path} returned HTTP {status_code}{suffix}")
        return response

    def capabilities(self) -> dict[str, Any]:
        response = self._request("OPTIONS", "studies")
        try:
            return {
                "status": response.status_code,
                "allow": response.headers.get("Allow"),
                "config": self.config.redacted(),
            }
        finally:
            _close_response(response)

    def search_studies(
        self,
        params: dict[str, Any] | None = None,
        *,
        page_size: int = 100,
        max_results: int | None = None,
        max_pages: int = 1000,
    ) -> list[dict[str, Any]]:
        if page_size <= 0 or max_pages <= 0:
            raise ValueError("page_size and max_pages must be positive")
        output: list[dict[str, Any]] = []
        offset = 0
        seen_pages: set[str] = set()
        page_number = 0
        while True:
            query = {**(params or {}), "limit": page_size, "offset": offset}
            response = self._request(
                "GET", "studies", params=query, headers={"Accept": "application/dicom+json"}
            )
            try:
                rows = response.json()
            finally:
                _close_response(response)
            page_number += 1
            if page_number > max_pages:
                raise DicomwebError(f"QIDO-RS exceeded max_pages={max_pages}")
            if not isinstance(rows, list):
                raise DicomwebError("QIDO-RS response was not a JSON array")
            signature = json.dumps(rows, sort_keys=True, separators=(",", ":"))
            if rows and signature in seen_pages:
                raise DicomwebError("QIDO-RS repeated a page; refusing an infinite pagination loop")
            seen_pages.add(signature)
            output.extend(rows)
            if len(rows) < page_size or (max_results is not None and len(output) >= max_results):
                break
            offset += len(rows)
        return output[:max_results] if max_results is not None else output

    def search_series(self, study_uid: str) -> list[dict[str, Any]]:
        study_uid = _validated_uid(study_uid, "study_uid")
        response = self._request(
            "GET", f"studies/{study_uid}/series", headers={"Accept": "application/dicom+json"}
        )
        try:
            return response.json()
        finally:
            _close_response(response)

    def search_instances(self, study_uid: str, series_uid: str | None = None) -> list[dict[str, Any]]:
        study_uid = _validated_uid(study_uid, "study_uid")
        if series_uid is not None:
            series_uid = _validated_uid(series_uid, "series_uid")
        path = (
            f"studies/{study_uid}/instances"
            if series_uid is None
            else f"studies/{study_uid}/series/{series_uid}/instances"
        )
        response = self._request("GET", path, headers={"Accept": "application/dicom+json"})
        try:
            return response.json()
        finally:
            _close_response(response)

    @staticmethod
    def _multipart_parts(content: bytes, content_type: str) -> list[bytes]:
        if "multipart/" not in content_type.lower():
            return [content]
        raw = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + content
        message = BytesParser(policy=default).parsebytes(raw)
        parts: list[bytes] = []
        for part in message.iter_parts():
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes) and payload:
                parts.append(payload)
        if not parts:
            raise DicomwebError("Malformed multipart DICOMweb response contained no decodable parts")
        return parts

    def retrieve_study(self, study_uid: str, destination: str | Path) -> list[Path]:
        study_uid = _validated_uid(study_uid, "study_uid")
        response = self._request(
            "GET",
            f"studies/{study_uid}",
            headers={"Accept": 'multipart/related; type="application/dicom"'},
            stream=True,
        )
        content = bytearray()
        try:
            for chunk in response.iter_content(1024 * 1024):
                content.extend(chunk)
                if len(content) > self.config.max_response_bytes:
                    raise DicomwebError("WADO-RS payload exceeded max_response_bytes")
            parts = self._multipart_parts(
                bytes(content), response.headers.get("Content-Type", "application/dicom")
            )
        finally:
            _close_response(response)
        root = Path(destination)
        root.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        import pydicom

        for index, payload in enumerate(parts):
            with tempfile.NamedTemporaryFile(dir=root, delete=False, suffix=".part") as handle:
                handle.write(payload)
                temporary = Path(handle.name)
            try:
                ds = pydicom.dcmread(temporary, stop_before_pixels=True)
                uid = str(getattr(ds, "SOPInstanceUID", ""))
                safe_uid = re.sub(r"[^0-9.]", "_", uid) or f"instance-{index:06d}"
                final = root / f"{safe_uid}.dcm"
                if final.exists():
                    final = root / f"{safe_uid}-{index:06d}.dcm"
                temporary.replace(final)
                paths.append(final)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise DicomwebError(f"WADO-RS part {index} was not a readable DICOM instance") from None
        return paths

    @staticmethod
    def _multipart_body(paths: Iterable[Path]) -> tuple[bytes, str]:
        boundary = "dpa-" + secrets.token_hex(16)
        chunks: list[bytes] = []
        for path in paths:
            payload = path.read_bytes()
            chunks.extend(
                [
                    f"--{boundary}\r\n".encode(),
                    b"Content-Type: application/dicom\r\n",
                    b"Content-Transfer-Encoding: binary\r\n\r\n",
                    payload,
                    b"\r\n",
                ]
            )
        chunks.append(f"--{boundary}--\r\n".encode())
        return b"".join(chunks), boundary

    def store_instances(self, paths: Iterable[str | Path], *, study_uid: str | None = None) -> dict[str, Any]:
        normalized = [Path(path) for path in paths]
        if not normalized:
            raise ValueError("At least one DICOM instance is required for STOW-RS")
        missing = [str(path) for path in normalized if not path.is_file()]
        if missing:
            raise FileNotFoundError(f"STOW-RS input files do not exist: {missing[:3]}")
        request_bytes = sum(path.stat().st_size for path in normalized)
        if request_bytes > self.config.max_request_bytes:
            raise DicomwebError("STOW-RS payload exceeded max_request_bytes")
        body, boundary = self._multipart_body(normalized)
        if study_uid is not None:
            study_uid = _validated_uid(study_uid, "study_uid")
        endpoint = "studies" if study_uid is None else f"studies/{study_uid}"
        response = self._request(
            "POST",
            endpoint,
            data=body,
            headers={
                "Content-Type": f'multipart/related; type="application/dicom"; boundary={boundary}',
                "Accept": "application/dicom+json, application/json",
            },
        )
        payload: Any
        try:
            try:
                payload = response.json()
            except ValueError:
                payload = {"body": response.text[:1000]}
            return {"status": response.status_code, "instances": len(normalized), "response": payload}
        finally:
            _close_response(response)
