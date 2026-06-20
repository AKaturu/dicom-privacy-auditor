#!/usr/bin/env python3
"""Run all release checks that do not require external datasets, services, or credentials."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact(value: str, root: Path, temporary: Path) -> str:
    replacements = [
        (str(root), "<PROJECT_ROOT>"),
        (str(temporary), "<TEMP_DIR>"),
        (str(Path(sys.prefix).resolve()), "<PYTHON_ENV>"),
        (str(Path(sys.executable).parent.resolve()), "<PYTHON_BIN>"),
        (str(Path(sys.executable).resolve().parent.parent), "<PYTHON_RUNTIME>"),
        (str(Path.home()), "<HOME>"),
    ]
    redacted = value
    for raw, marker in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if raw and raw != "/":
            redacted = redacted.replace(raw, marker)
    redacted = re.sub(
        r"(?<![A-Za-z0-9_.:/\\>~-])/(?:[^\s'\"<>]+)",
        "<ABSOLUTE_PATH>",
        redacted,
    )
    redacted = re.sub(
        r"(?<![A-Za-z0-9_.:/\\>~-])[A-Za-z]:[\\/][^\s'\"<>]+",
        "<ABSOLUTE_PATH>",
        redacted,
    )
    redacted = re.sub(
        r"(?<![A-Za-z0-9_.:/\\>~-])\\\\[^\s'\"<>]+",
        "<ABSOLUTE_PATH>",
        redacted,
    )
    return redacted


def _run(
    name: str,
    command: list[str],
    *,
    root: Path,
    temporary: Path,
    timeout: int,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    env = {**os.environ, "PYTHONPATH": f"{root / 'src'}{os.pathsep}{root}"}
    if extra_env:
        env.update(extra_env)
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        returncode = completed.returncode
        output = completed.stdout or ""
        status = "passed" if returncode == 0 else "failed"
    except subprocess.TimeoutExpired as exc:
        returncode = 124
        raw = exc.stdout or ""
        output = raw.decode(errors="replace") if isinstance(raw, bytes) else raw
        output += f"\nTimed out after {timeout} seconds."
        status = "failed"
    duration = round(time.monotonic() - started, 3)
    redacted = _redact(output, root, temporary)
    return {
        "name": name,
        "status": status,
        "returncode": returncode,
        "duration_seconds": duration,
        "command": " ".join(shlex.quote(_redact(part, root, temporary)) for part in command),
        "output_tail": redacted[-12000:],
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("validation/local-release-gate.json"))
    parser.add_argument("--skip-reproducible", action="store_true")
    parser.add_argument("--timeout", type=int, default=900, help="Per-check timeout in seconds")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    python = sys.executable
    started_at = _now()

    with tempfile.TemporaryDirectory(prefix="dpa-release-gate-") as raw:
        temporary = Path(raw)
        dist = temporary / "dist"
        checks: list[tuple[str, list[str], dict[str, str] | None]] = [
            ("action-pins", [python, "scripts/check_action_pins.py"], None),
            ("workflow-yaml", [python, "scripts/check_workflow_integrity.py", str(root)], None),
            ("schema-integrity", [python, "scripts/check_schema_integrity.py", str(root)], None),
            ("dependency-locks", [python, "scripts/check_dependency_locks.py", str(root)], None),
            ("installed-dependencies", [python, "-m", "pip", "check"], None),
            ("ruff", [python, "-m", "ruff", "check", "."], None),
            ("ruff-format", [python, "-m", "ruff", "format", "--check", "."], None),
            ("compileall", [python, "-m", "compileall", "-q", "src", "scripts", "tests"], None),
            ("documentation", [python, "scripts/check_documentation.py", str(root)], None),
            ("mypy", [python, "-m", "mypy"], None),
            (
                "bandit-medium-high",
                [
                    python,
                    "-m",
                    "bandit",
                    "-q",
                    "-r",
                    "src",
                    "scripts",
                    "-ll",
                ],
                None,
            ),
            (
                "tests-and-coverage",
                [
                    python,
                    "-m",
                    "pytest",
                    "-p",
                    "pytest_cov",
                    "--cov=dicom_privacy_auditor",
                    "--cov-report=term-missing",
                    "--cov-fail-under=85",
                ],
                {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
            ),
            (
                "build",
                [python, "scripts/build_release_distributions.py", str(root), "--output", str(dist)],
                {"SOURCE_DATE_EPOCH": "1781913600"},
            ),
            (
                "distribution-policy",
                [python, "scripts/check_distribution_contents.py", str(root), str(dist)],
                None,
            ),
            ("package-metadata", [python, "scripts/check_package_metadata.py", str(dist)], None),
            ("clean-wheel-smoke", [python, "scripts/smoke_clean_wheel.py", str(dist)], None),
        ]
        if not args.skip_reproducible:
            checks.append(
                (
                    "reproducible-distributions",
                    [python, "scripts/verify_reproducible_build.py", str(root)],
                    None,
                )
            )

        results = [
            _run(
                name,
                command,
                root=root,
                temporary=temporary,
                timeout=args.timeout,
                extra_env=environment,
            )
            for name, command, environment in checks
        ]
        if args.skip_reproducible:
            results.append(
                {
                    "name": "reproducible-distributions",
                    "status": "skipped",
                    "returncode": None,
                    "duration_seconds": 0.0,
                    "command": None,
                    "output_tail": "Skipped by explicit command-line option.",
                }
            )

    failed = [item["name"] for item in results if item["status"] == "failed"]
    skipped = [item["name"] for item in results if item["status"] == "skipped"]
    payload = {
        "schema_version": "1.0",
        "release": "0.7.2",
        "started_at": started_at,
        "finished_at": _now(),
        "environment": {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
        "scope": "Local checks only; excludes external datasets, services, reviewers, and signing credentials.",
        "status": "passed" if not failed and not skipped else ("partial" if not failed else "failed"),
        "failed_checks": failed,
        "skipped_checks": skipped,
        "checks": results,
    }
    schema_path = root / "schemas" / "local-release-gate.schema.json"
    Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8"))).validate(payload)
    _atomic_json(output, payload)
    print(json.dumps({"status": payload["status"], "output": str(output), "failed": failed}, indent=2))
    return 0 if not failed and not skipped else (3 if not failed else 1)


if __name__ == "__main__":
    raise SystemExit(main())
