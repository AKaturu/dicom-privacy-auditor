#!/usr/bin/env python3
"""Install the built wheel in an isolated venv and smoke every console entry point."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import venv
from pathlib import Path


def run(
    command: list[str], environment: dict[str, str], timeout: int = 90
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    wheels = sorted(args.dist.glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit(f"expected exactly one wheel, found {len(wheels)}")

    with tempfile.TemporaryDirectory(prefix="dpa-wheel-smoke-") as raw:
        root = Path(raw)
        venv.EnvBuilder(with_pip=True, clear=True, system_site_packages=False).create(root)
        bindir = root / ("Scripts" if os.name == "nt" else "bin")
        python = bindir / ("python.exe" if os.name == "nt" else "python")
        environment = {
            **os.environ,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        environment.pop("PYTHONPATH", None)
        install = run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--force-reinstall",
                "--no-deps",
                str(wheels[0]),
            ],
            environment,
            300,
        )
        if install.returncode:
            print(install.stdout)
            return 1
        dependencies = run(
            [
                str(python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "numpy>=1.26,<3.0",
                "pydicom>=3.0,<4.0",
                "Pillow>=10,<13",
                "jsonschema>=4.23,<5",
                "requests>=2.33,<3",
            ],
            environment,
            300,
        )
        if dependencies.returncode:
            print(dependencies.stdout)
            return 1
        import_probe = run(
            [str(python), "-c", "import dicom_privacy_auditor,pydicom,PIL,jsonschema,requests"],
            environment,
        )
        if import_probe.returncode:
            print(import_probe.stdout)
            return 1

        probe_code = (
            "import importlib.metadata as m,json; "
            "print(json.dumps(sorted(e.name for e in "
            "m.entry_points(group='console_scripts') "
            "if e.value.startswith('dicom_privacy_auditor'))))"
        )
        probe = run([str(python), "-c", probe_code], environment)
        if probe.returncode:
            print(probe.stdout)
            return 1
        commands = json.loads(probe.stdout.strip().splitlines()[-1])
        failures: list[tuple[str, int, str]] = []
        for name in commands:
            candidates = [bindir / name]
            if os.name == "nt":
                candidates.insert(0, bindir / f"{name}.exe")
            executable = next((candidate for candidate in candidates if candidate.exists()), candidates[0])
            if not executable.exists():
                failures.append((name, 127, f"missing executable: {executable}"))
                continue
            result = run([str(executable), "--help"], environment)
            if result.returncode not in {0, 2} or not result.stdout.strip():
                failures.append((name, result.returncode, result.stdout[-500:]))

        version = run(
            [str(python), "-c", "import dicom_privacy_auditor as d; print(d.__version__)"],
            environment,
        )
        if version.returncode or version.stdout.strip() != "0.7.2":
            failures.append(("version", version.returncode, version.stdout))
        if failures:
            print(json.dumps(failures, indent=2))
            return 1
        print(json.dumps({"wheel": wheels[0].name, "entry_points": len(commands), "status": "passed"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
