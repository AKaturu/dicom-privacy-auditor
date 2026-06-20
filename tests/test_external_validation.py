from pathlib import Path

from dicom_privacy_auditor.external_validation import (
    build_resource_lock,
    run_preflight,
    verify_resource_lock,
)


def test_external_preflight_reports_blockers(tmp_path: Path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    key = tmp_path / "key.sqlite"
    key.write_bytes(b"sqlite")
    monkeypatch.delenv("DPA_TEST_TOKEN", raising=False)
    result = run_preflight(
        {
            "midi_b_corpus": str(corpus),
            "midi_b_answer_key": str(key),
            "reviewers": ["a"],
            "required_environment_variables": ["DPA_TEST_TOKEN"],
        }
    )
    assert result["status"] == "blocked"
    indexed = {item["name"]: item for item in result["checks"]}
    assert indexed["midi_b_corpus"]["status"] == "ready"
    assert indexed["blinded_reviewers"]["status"] == "missing"
    assert indexed["credentials"]["status"] == "missing"


def test_external_preflight_optional_checks_and_fingerprints(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "case.dcm").write_bytes(b"dicom")
    key = tmp_path / "key.sqlite"
    key.write_bytes(b"sqlite")
    result = run_preflight(
        {
            "midi_b_corpus": str(corpus),
            "midi_b_answer_key": str(key),
            "fingerprint_resources": True,
            "optional_checks": [
                "official_validator",
                "rsna_anonymizer",
                "rsna_ctp",
                "orthanc_http",
                "orthanc_dimse",
                "dicomweb",
                "blinded_reviewers",
                "credentials",
            ],
        }
    )
    assert result["status"] == "ready"
    indexed = {item["name"]: item for item in result["checks"]}
    assert indexed["midi_b_corpus"]["fingerprint"].startswith("inventory-sha256:")
    assert len(indexed["midi_b_answer_key"]["fingerprint"]) == 64
    assert indexed["official_validator"]["required"] is False


def test_external_preflight_rejects_unknown_configuration_key():
    import pytest

    with pytest.raises(ValueError, match="invalid external-validation configuration"):
        run_preflight({"unexpected_secret": "value"})


def test_external_preflight_handles_quoted_command(tmp_path: Path, monkeypatch):
    executable = tmp_path / "tool with spaces"
    executable.write_text("tool", encoding="utf-8")
    monkeypatch.setattr(
        "dicom_privacy_auditor.external_validation.shutil.which",
        lambda value: str(executable) if value == str(executable) else None,
    )
    result = run_preflight(
        {
            "official_validator_command": f'"{executable}" --version',
            "optional_checks": [
                "midi_b_corpus",
                "midi_b_answer_key",
                "rsna_anonymizer",
                "rsna_ctp",
                "orthanc_http",
                "orthanc_dimse",
                "dicomweb",
                "blinded_reviewers",
                "credentials",
            ],
        }
    )
    assert result["status"] == "ready"


def test_content_fingerprint_detects_same_size_byte_change(tmp_path: Path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    sample = corpus / "case.dcm"
    sample.write_bytes(b"AAAA")
    first = run_preflight(
        {
            "midi_b_corpus": str(corpus),
            "fingerprint_mode": "content",
            "optional_checks": [
                "midi_b_answer_key",
                "official_validator",
                "rsna_anonymizer",
                "rsna_ctp",
                "orthanc_http",
                "orthanc_dimse",
                "dicomweb",
                "blinded_reviewers",
                "credentials",
            ],
        }
    )
    sample.write_bytes(b"BBBB")
    second = run_preflight(
        {
            "midi_b_corpus": str(corpus),
            "fingerprint_mode": "content",
            "optional_checks": [
                "midi_b_answer_key",
                "official_validator",
                "rsna_anonymizer",
                "rsna_ctp",
                "orthanc_http",
                "orthanc_dimse",
                "dicomweb",
                "blinded_reviewers",
                "credentials",
            ],
        }
    )
    assert first["checks"][0]["fingerprint"] != second["checks"][0]["fingerprint"]


def test_resource_lock_detects_drift(tmp_path: Path):
    key = tmp_path / "key.sqlite"
    key.write_bytes(b"first")
    config = {
        "midi_b_answer_key": str(key),
        "fingerprint_mode": "content",
        "optional_checks": [
            "midi_b_corpus",
            "official_validator",
            "rsna_anonymizer",
            "rsna_ctp",
            "orthanc_http",
            "orthanc_dimse",
            "dicomweb",
            "blinded_reviewers",
            "credentials",
        ],
    }
    first = run_preflight(config)
    lock = build_resource_lock(config, first)
    assert verify_resource_lock(lock, first)["status"] == "verified"
    key.write_bytes(b"later")
    assert verify_resource_lock(lock, run_preflight(config))["status"] == "drift"


def test_authenticated_http_requires_https(monkeypatch):
    monkeypatch.setenv("TOKEN", "Bearer secret")
    result = run_preflight(
        {
            "orthanc_http_url": "http://example.test/system",
            "http_auth_environment_variable": "TOKEN",
            "optional_checks": [
                "midi_b_corpus",
                "midi_b_answer_key",
                "official_validator",
                "rsna_anonymizer",
                "rsna_ctp",
                "orthanc_dimse",
                "dicomweb",
                "blinded_reviewers",
                "credentials",
            ],
        }
    )
    indexed = {item["name"]: item for item in result["checks"]}
    assert indexed["orthanc_http"]["status"] == "invalid"


def test_external_http_tcp_and_cli_paths(tmp_path: Path, monkeypatch, capsys):
    import json

    from dicom_privacy_auditor.external_validation import main

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code
            self.closed = False

        def close(self):
            self.closed = True

    responses = iter([Response(200), Response(302), Response(503)])
    monkeypatch.setattr(
        "dicom_privacy_auditor.external_validation.requests.get", lambda *a, **k: next(responses)
    )

    class SocketContext:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "dicom_privacy_auditor.external_validation.socket.create_connection", lambda *a, **k: SocketContext()
    )
    monkeypatch.setenv("TOKEN", "Bearer secret")
    config = {
        "orthanc_http_url": "https://example.test/system",
        "dicomweb_url": "https://example.test/dicomweb",
        "orthanc_dimse_host": "localhost",
        "orthanc_dimse_port": 4242,
        "http_auth_environment_variable": "TOKEN",
        "reviewers": ["a", "b"],
        "optional_checks": [
            "midi_b_corpus",
            "midi_b_answer_key",
            "official_validator",
            "rsna_anonymizer",
            "rsna_ctp",
            "credentials",
        ],
    }
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    output = tmp_path / "result.json"
    lock = tmp_path / "resources.lock.json"
    assert main([str(config_path), "--output", str(output), "--write-lock", str(lock), "--redact-paths"]) == 2
    assert output.is_file() and lock.is_file()
    assert "Bearer secret" not in output.read_text(encoding="utf-8")


def test_external_cli_invalid_config_and_lock_drift(tmp_path: Path, capsys):
    import json

    from dicom_privacy_auditor.external_validation import main

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    assert main([str(invalid)]) == 3
    assert '"status": "invalid"' in capsys.readouterr().out

    key = tmp_path / "key"
    key.write_bytes(b"first")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "midi_b_answer_key": str(key),
                "fingerprint_mode": "content",
                "optional_checks": [
                    "midi_b_corpus",
                    "official_validator",
                    "rsna_anonymizer",
                    "rsna_ctp",
                    "orthanc_http",
                    "orthanc_dimse",
                    "dicomweb",
                    "blinded_reviewers",
                    "credentials",
                ],
            }
        ),
        encoding="utf-8",
    )
    lock = tmp_path / "lock.json"
    assert main([str(config), "--write-lock", str(lock)]) == 0
    key.write_bytes(b"later")
    assert main([str(config), "--verify-lock", str(lock)]) == 4
