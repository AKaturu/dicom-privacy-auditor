"""Preflight and provenance helpers for external validation resources."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import socket
import sqlite3
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from typing import Any

import requests
from jsonschema import Draft202012Validator

from .http_utils import validate_http_url
from .permissions import restrict_file


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str
    required: bool = True
    fingerprint: str | None = None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_fingerprint(path: Path, *, content: bool = False) -> str:
    """Fingerprint a directory deterministically, optionally hashing every file byte."""
    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        stat = item.stat()
        record = f"{item.relative_to(path).as_posix()}\0{stat.st_size}"
        if content:
            record += f"\0{_sha256(item)}"
        digest.update((record + "\n").encode())
    prefix = "content-sha256:" if content else "inventory-sha256:"
    return prefix + digest.hexdigest()


def _path_check(
    name: str, value: str | None, *, directory: bool = False, fingerprint_mode: str = "none"
) -> Check:
    if not value:
        return Check(name, "missing", "not configured")
    path = Path(value).expanduser()
    valid = path.is_dir() if directory else path.is_file()
    if not valid:
        return Check(name, "missing", f"not found: {path}")
    fingerprint = fingerprint_mode != "none"
    digest = (
        _directory_fingerprint(path, content=fingerprint_mode == "content")
        if directory and fingerprint
        else (_sha256(path) if fingerprint else None)
    )
    return Check(name, "ready", str(path.resolve()), fingerprint=digest)


def _directory_check(
    name: str, value: str | None, *, fingerprint_mode: str = "none", required_when_missing: bool = True
) -> Check | None:
    if not value and not required_when_missing:
        return None
    return _path_check(name, value, directory=True, fingerprint_mode=fingerprint_mode)


def _command_check(name: str, command: str | None, *, fingerprint_mode: str = "none") -> Check:
    if not command:
        return Check(name, "missing", "not configured")
    try:
        parts = shlex.split(command, posix=os.name != "nt")
    except ValueError as exc:
        return Check(name, "invalid", f"invalid command syntax: {exc}")
    if not parts:
        return Check(name, "invalid", "empty command")
    executable = parts[0]
    if os.name == "nt" and len(executable) >= 2 and executable[0] == executable[-1] == '"':
        executable = executable[1:-1]
    found = shutil.which(executable)
    digest = _sha256(Path(found)) if found and fingerprint_mode != "none" and Path(found).is_file() else None
    return Check(
        name, "ready" if found else "missing", found or f"command not found: {parts[0]}", fingerprint=digest
    )


def _http_check(name: str, url: str | None, *, timeout: float, auth_env: str | None) -> Check:
    if not url:
        return Check(name, "missing", "not configured")
    try:
        validate_http_url(url, require_https=bool(auth_env))
    except ValueError as exc:
        return Check(name, "invalid", str(exc))
    headers = {"User-Agent": "dicom-privacy-auditor-preflight"}
    if auth_env:
        token = os.environ.get(auth_env)
        if not token:
            return Check(name, "missing", f"authentication environment variable is unset: {auth_env}")
        headers["Authorization"] = token
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
        )
        try:
            if 300 <= response.status_code < 400:
                return Check(name, "invalid", f"HTTP redirect refused ({response.status_code}): {url}")
            if response.status_code >= 400:
                return Check(name, "unreachable", f"HTTP {response.status_code}: {url}")
            return Check(name, "ready", f"HTTP {response.status_code}: {url}")
        finally:
            response.close()
    except requests.RequestException as exc:
        return Check(name, "unreachable", f"{url}: {exc}")


def _tcp_check(name: str, host: str | None, port: int | None, *, timeout: float) -> Check:
    if not host or not port:
        return Check(name, "missing", "host/port not configured")
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return Check(name, "ready", f"connected to {host}:{port}")
    except OSError as exc:
        return Check(name, "unreachable", f"{host}:{port}: {exc}")


def _sqlite_table_count(path: Path, table: str) -> int | None:
    try:
        with sqlite3.connect(path) as connection:
            row = connection.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.Error:
        return None


def _read_log_signals(log_path: Path | None) -> dict[str, Any]:
    if log_path is None or not log_path.is_file():
        return {"log_found": False, "error_count": 0, "run_complete": False, "last_error": None}
    error_count = 0
    run_complete = False
    last_error = None
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if "[ERROR]" in line:
                    error_count += 1
                    last_error = line.strip()
                if "Run Complete" in line:
                    run_complete = True
    except OSError:
        return {"log_found": False, "error_count": 0, "run_complete": False, "last_error": None}
    return {
        "log_found": True,
        "error_count": error_count,
        "run_complete": run_complete,
        "last_error": last_error,
    }


def monitor_official_validator(config: dict[str, Any]) -> dict[str, Any] | None:
    """Summarize an official MIDI-B validator run without exposing local paths."""
    output_dir = config.get("official_validator_output_dir")
    log_dir = config.get("official_validator_log_dir")
    run_name = config.get("official_validator_run_name")
    if not output_dir and not log_dir:
        return None

    stale_after_minutes = float(config.get("official_validator_stale_after_minutes", 60))
    output_root = Path(output_dir).expanduser() if output_dir else None
    run_dir = output_root / run_name if output_root and run_name else output_root
    log_root = Path(log_dir).expanduser() if log_dir else None

    latest_log = None
    if log_root and log_root.is_dir():
        log_files = sorted(log_root.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
        latest_log = log_files[0] if log_files else None

    result_db = run_dir / "validation_results.db" if run_dir else None
    result_db_bytes = result_db.stat().st_size if result_db and result_db.is_file() else None
    validation_table_present = (
        _sqlite_table_count(result_db, "validation_results") == 1
        if result_db and result_db.is_file() and result_db_bytes
        else False
    )
    pixel_validation = run_dir / "pixel_validation.xlsx" if run_dir else None
    scoring_instance = run_dir / "scoring_report_instance.xlsx" if run_dir else None
    scoring_series = run_dir / "scoring_report_series.xlsx" if run_dir else None
    signals = _read_log_signals(latest_log)

    latest_mtime = None
    for candidate in [result_db, pixel_validation, scoring_instance, scoring_series, latest_log]:
        if candidate and candidate.exists():
            mtime = candidate.stat().st_mtime
            latest_mtime = mtime if latest_mtime is None else max(latest_mtime, mtime)

    if validation_table_present:
        status = "completed"
        detail = "validation_results table is present"
    elif signals["error_count"] > 0:
        status = "failed"
        detail = "latest official-validator log contains errors"
    elif signals["run_complete"]:
        status = "failed"
        detail = "run completed without a persisted validation_results table"
    elif latest_mtime:
        age_minutes = (datetime.now(timezone.utc).timestamp() - latest_mtime) / 60
        status = "running" if age_minutes <= stale_after_minutes else "stale"
        detail = f"latest validator artifact is {age_minutes:.1f} minutes old"
    else:
        status = "not_started"
        detail = "no official-validator artifacts found"

    return {
        "schema_version": "1.0",
        "status": status,
        "detail": detail,
        "run_name": run_name,
        "run_dir_configured": bool(run_dir),
        "log_dir_configured": bool(log_root),
        "latest_log_name": latest_log.name if latest_log else None,
        "result_db_name": result_db.name if result_db else None,
        "result_db_bytes": result_db_bytes,
        "validation_results_table": validation_table_present,
        "pixel_validation_present": bool(pixel_validation and pixel_validation.is_file()),
        "scoring_report_present": bool(
            (scoring_instance and scoring_instance.is_file()) or (scoring_series and scoring_series.is_file())
        ),
        "log_error_count": signals["error_count"],
        "log_run_complete": signals["run_complete"],
        "last_error": signals["last_error"],
    }


def validate_config(config: dict[str, Any]) -> None:
    schema_path = files("dicom_privacy_auditor.schemas").joinpath("external-validation-config.schema.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(config), key=lambda item: list(item.path))
    if errors:
        detail = "; ".join(
            f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors
        )
        raise ValueError(f"invalid external-validation configuration: {detail}")


def run_preflight(config: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    timeout = float(config.get("http_timeout_seconds", 5))
    fingerprint_mode = config.get("fingerprint_mode") or (
        "inventory" if config.get("fingerprint_resources", False) else "none"
    )
    auth_env = config.get("http_auth_environment_variable")
    checks: list[Check] = [
        _path_check(
            "midi_b_corpus", config.get("midi_b_corpus"), directory=True, fingerprint_mode=fingerprint_mode
        ),
        _path_check("midi_b_answer_key", config.get("midi_b_answer_key"), fingerprint_mode=fingerprint_mode),
        _path_check("midi_b_uid_mapping", config.get("midi_b_uid_mapping"), fingerprint_mode=fingerprint_mode),
        _path_check(
            "midi_b_patient_mapping", config.get("midi_b_patient_mapping"), fingerprint_mode=fingerprint_mode
        ),
        _command_check(
            "official_validator", config.get("official_validator_command"), fingerprint_mode=fingerprint_mode
        ),
        _command_check(
            "rsna_anonymizer", config.get("rsna_anonymizer_command"), fingerprint_mode=fingerprint_mode
        ),
        _command_check("rsna_ctp", config.get("rsna_ctp_command"), fingerprint_mode=fingerprint_mode),
        _http_check("orthanc_http", config.get("orthanc_http_url"), timeout=timeout, auth_env=auth_env),
        _tcp_check(
            "orthanc_dimse",
            config.get("orthanc_dimse_host"),
            config.get("orthanc_dimse_port"),
            timeout=timeout,
        ),
        _http_check("dicomweb", config.get("dicomweb_url"), timeout=timeout, auth_env=auth_env),
    ]
    for check in [
        _directory_check(
            "official_validator_output_dir",
            config.get("official_validator_output_dir"),
            fingerprint_mode=fingerprint_mode,
            required_when_missing=False,
        ),
        _directory_check(
            "official_validator_log_dir",
            config.get("official_validator_log_dir"),
            fingerprint_mode=fingerprint_mode,
            required_when_missing=False,
        ),
    ]:
        if check:
            checks.append(check)
    reviewers = config.get("reviewers") or []
    checks.append(
        Check(
            "blinded_reviewers",
            "ready" if len(reviewers) >= 2 else "missing",
            f"configured reviewers: {len(reviewers)}",
        )
    )
    required_env = config.get("required_environment_variables") or []
    absent = [name for name in required_env if not os.environ.get(name)]
    checks.append(
        Check(
            "credentials",
            "ready" if not absent else "missing",
            "all configured" if not absent else f"unset: {', '.join(absent)}",
        )
    )
    optional = set(config.get("optional_checks") or [])
    checks = [replace(item, required=item.name not in optional) for item in checks]
    payload = [asdict(item) for item in checks]
    required_checks = [item for item in checks if item.required]
    result = {
        "schema_version": "1.0",
        "status": "ready" if all(item.status == "ready" for item in required_checks) else "blocked",
        "checks": payload,
        "ready": sum(item.status == "ready" for item in checks),
        "required_ready": sum(item.status == "ready" for item in required_checks),
        "required_total": len(required_checks),
        "total": len(checks),
        "limitations": [
            "A ready preflight confirms resource availability, not clinical safety or regulatory compliance.",
            "Inventory fingerprints cover relative paths and file sizes; use content mode for byte-level corpus identity.",
            "Institutional authorization and data-use approvals must be verified outside this tool.",
        ],
    }
    monitor = monitor_official_validator(config)
    if monitor is not None:
        result["official_validator_monitor"] = monitor
    return result


def _redact_check_details(result: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(result))
    for item in redacted.get("checks", []):
        if (
            item.get("name")
            in {
                "midi_b_corpus",
                "midi_b_answer_key",
                "midi_b_uid_mapping",
                "midi_b_patient_mapping",
                "official_validator",
                "official_validator_output_dir",
                "official_validator_log_dir",
                "rsna_anonymizer",
                "rsna_ctp",
            }
            and item.get("status") == "ready"
        ):
            item["detail"] = "configured resource available"
    return redacted


def build_resource_lock(config: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Build a portable lock containing only stable resource identities, never secrets or paths."""
    stable_config = {
        key: value
        for key, value in config.items()
        if key
        not in {
            "midi_b_corpus",
            "midi_b_answer_key",
            "midi_b_uid_mapping",
            "midi_b_patient_mapping",
            "official_validator_command",
            "official_validator_output_dir",
            "official_validator_log_dir",
            "rsna_anonymizer_command",
            "rsna_ctp_command",
            "http_auth_environment_variable",
            "required_environment_variables",
        }
    }
    identities = {
        item["name"]: item["fingerprint"] for item in result.get("checks", []) if item.get("fingerprint")
    }
    canonical = json.dumps(stable_config, sort_keys=True, separators=(",", ":")).encode()
    return {
        "schema_version": "1.0",
        "config_sha256": hashlib.sha256(canonical).hexdigest(),
        "resource_fingerprints": identities,
    }


def verify_resource_lock(lock: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    expected = lock.get("resource_fingerprints") or {}
    actual = {item["name"]: item.get("fingerprint") for item in current.get("checks", [])}
    changed = {
        name: {"expected": digest, "actual": actual.get(name)}
        for name, digest in expected.items()
        if actual.get(name) != digest
    }
    missing = sorted(name for name in expected if name not in actual or actual.get(name) is None)
    return {
        "schema_version": "1.0",
        "status": "verified" if not changed and not missing else "drift",
        "changed": changed,
        "missing": missing,
        "verified": len(expected) - len(changed),
        "total": len(expected),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dicom-privacy-external", description="External validation readiness preflight"
    )
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--redact-paths", action="store_true")
    parser.add_argument("--write-lock", type=Path)
    parser.add_argument("--verify-lock", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        result = run_preflight(config)
        lock_verification = None
        if args.verify_lock:
            lock_verification = verify_resource_lock(
                json.loads(args.verify_lock.read_text(encoding="utf-8")), result
            )
            result["resource_lock"] = lock_verification
        if args.write_lock:
            args.write_lock.parent.mkdir(parents=True, exist_ok=True)
            args.write_lock.write_text(
                json.dumps(build_resource_lock(config, result), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            restrict_file(args.write_lock)
        if args.redact_paths:
            result = _redact_check_details(result)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"status": "invalid", "error": str(exc)}, indent=2, sort_keys=True))
        return 3
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text + "\n", encoding="utf-8")
        restrict_file(args.output)
    print(text)
    if result.get("resource_lock", {}).get("status") == "drift":
        return 4
    return 0 if result["status"] == "ready" else 2


if __name__ == "__main__":
    raise SystemExit(main())
