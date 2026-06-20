#!/usr/bin/env python3
"""Build native command-line and desktop executables with PyInstaller.

PyInstaller is not a cross-compiler. Run this script on each target operating
system, or use the included GitHub Actions release workflow.
"""

from __future__ import annotations

import argparse
import importlib.util
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def _run(command: list[str], *, cwd: Path) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def _check_native_dependencies() -> None:
    required = {
        "docx": "python-docx (install the native or standards extra)",
        "pynetdicom": "pynetdicom (install the native or adapters extra)",
    }
    missing = [
        description for module, description in required.items() if importlib.util.find_spec(module) is None
    ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            f"Native CLI build dependencies are missing: {joined}. Install with: pip install -e '.[native]'"
        )


def build(root: Path, output: Path, *, clean: bool = True) -> None:
    _check_native_dependencies()
    system = platform.system().lower()
    architecture = platform.machine().lower()
    build_root = root / "build" / "pyinstaller"
    spec_root = root / "build" / "spec"
    if clean:
        shutil.rmtree(build_root, ignore_errors=True)
        shutil.rmtree(spec_root, ignore_errors=True)
        shutil.rmtree(output, ignore_errors=True)
    build_root.mkdir(parents=True, exist_ok=True)
    spec_root.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    common = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--paths",
        str(root / "src"),
        "--collect-data",
        "dicom_privacy_auditor",
        "--distpath",
        str(output),
        "--specpath",
        str(spec_root),
        "--workpath",
        str(build_root),
    ]

    cli_name = "DICOMPrivacyAuditor-CLI"
    cli_command = [
        *common,
        "--onefile",
        "--console",
        "--name",
        cli_name,
        # The desktop application is shipped as a separate executable.  Do
        # not pull Tk into the CLI bundle merely because the installed
        # launcher also offers a convenience ``desktop`` subcommand.
        "--exclude-module",
        "dicom_privacy_auditor.desktop",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "_tkinter",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "pandas",
        str(root / "packaging" / "entry_cli.py"),
    ]
    _run(cli_command, cwd=root)

    desktop_command = [*common, "--name", "DICOMPrivacyAuditor", "--windowed"]
    if system == "darwin":
        # On macOS, an onedir .app is preferable for launch speed and signing.
        desktop_command.append("--onedir")
    else:
        desktop_command.append("--onefile")
    desktop_command.append(str(root / "packaging" / "entry_desktop.py"))
    _run(desktop_command, cwd=root)

    print(f"Built native artifacts for {system}/{architecture} in {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist") / "native",
        help="Directory for native build artifacts",
    )
    parser.add_argument("--no-clean", action="store_true", help="Keep previous build intermediates")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    build(root, args.output.resolve(), clean=not args.no_clean)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
