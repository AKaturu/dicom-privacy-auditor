from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from dicom_privacy_auditor.dicomweb.client import DicomwebConfig
from dicom_privacy_auditor.http_utils import validate_http_url
from dicom_privacy_auditor.ps315.generate import download_official_docx


def test_http_url_validation_rejects_unsafe_forms() -> None:
    with pytest.raises(ValueError, match="http"):
        validate_http_url("file:///tmp/secret")
    with pytest.raises(ValueError, match="credentials"):
        validate_http_url("https://user:secret@example.test/path")
    with pytest.raises(ValueError, match="fragment"):
        validate_http_url("https://example.test/path#fragment")
    with pytest.raises(ValueError, match="query"):
        validate_http_url("https://example.test/path?token=x", allow_query=False)
    assert validate_http_url("https://example.test/path?limit=1").hostname == "example.test"


def test_dicomweb_authentication_requires_https() -> None:
    with pytest.raises(ValueError, match="Authenticated DICOMweb"):
        DicomwebConfig(
            base_url="http://127.0.0.1:8042",
            allow_insecure_http=True,
            bearer_token_env="TOKEN",
        )


def test_standards_download_enforces_size_and_docx(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class Response:
        def __init__(self, payload: bytes, declared: int | None = None):
            self._stream = io.BytesIO(payload)
            self.headers = {"Content-Length": str(declared if declared is not None else len(payload))}

        def read(self, size: int = -1) -> bytes:
            return self._stream.read(size)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Opener:
        response: Response

        def open(self, *_args, **_kwargs):
            return self.response

    opener = Opener()
    monkeypatch.setattr("dicom_privacy_auditor.ps315.generate.build_no_redirect_opener", lambda: opener)
    opener.response = Response(b"too-large", declared=1000)
    with pytest.raises(RuntimeError, match="max_bytes"):
        download_official_docx(
            "https://example.test/part15.docx", destination=tmp_path / "a.docx", max_bytes=10
        )
    assert not (tmp_path / "a.docx.part").exists()

    opener.response = Response(b"not-a-zip")
    with pytest.raises(RuntimeError, match="valid DOCX"):
        download_official_docx("https://example.test/part15.docx", destination=tmp_path / "b.docx")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("[Content_Types].xml", "<Types/>")
    opener.response = Response(archive.getvalue())
    result = download_official_docx("https://example.test/part15.docx", destination=tmp_path / "c.docx")
    assert result.is_file()


def test_authenticated_remote_orthanc_requires_https() -> None:
    from dicom_privacy_auditor.adapters.orthanc import OrthancAdapter

    with pytest.raises(ValueError, match="Authenticated remote Orthanc"):
        OrthancAdapter(
            {
                "base_url": "http://192.0.2.10:8042",
                "allow_insecure_http": True,
                "username": "user",
                "password": "password",
                "allow_literal_credentials": True,
            }
        )


def test_dicomweb_rejects_invalid_uids_before_request(monkeypatch: pytest.MonkeyPatch) -> None:
    from dicom_privacy_auditor.dicomweb.client import DicomwebClient

    client = DicomwebClient(DicomwebConfig(base_url="http://127.0.0.1:8042", allow_insecure_http=True))
    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: pytest.fail("request attempted"))
    with pytest.raises(ValueError, match="valid DICOM UID"):
        client.search_series("../../escape")
    with pytest.raises(ValueError, match="valid DICOM UID"):
        client.retrieve_study("https://example.invalid", Path("unused"))
    client.close()


def test_dicomweb_redacts_proxy_authorization() -> None:
    config = DicomwebConfig(
        base_url="https://example.test/dicom-web",
        headers={"Proxy-Authorization": "secret"},
        allow_literal_secret_headers=True,
    )
    assert config.redacted()["headers"]["Proxy-Authorization"] == "<redacted>"
