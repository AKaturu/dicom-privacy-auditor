#!/usr/bin/env python3
"""Create a byte-reproducible, migration-ready source ZIP from a clean project tree."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import sys
import time
import zipfile
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".hypothesis",
    "__pycache__",
    "build",
    "dist",
    "reports",
    "workspaces",
}
EXCLUDED_FILENAMES = {".coverage", ".DS_Store", "Thumbs.db"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".sqlite3", ".p12", ".pfx", ".key"}
DEFAULT_SOURCE_DATE_EPOCH = 1781913600  # 2026-06-20T00:00:00Z


def release_version(root: Path) -> str:
    payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def collect_files(root: Path, output: Path | None = None) -> list[Path]:
    files: list[Path] = []
    output_resolved = output.resolve() if output else None
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root)
        if len(relative.parts) >= 2 and relative.parts[:2] == ("validation", "local"):
            continue
        if any(part in EXCLUDED_DIRECTORIES for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"Source archive refuses symbolic links: {path}")
        if not path.is_file():
            continue
        if path.name in EXCLUDED_FILENAMES or path.suffix.casefold() in EXCLUDED_SUFFIXES:
            continue
        if output_resolved and path.resolve() == output_resolved:
            continue
        files.append(path)
    return files


def _zip_timestamp(epoch: int) -> tuple[int, int, int, int, int, int]:
    value = max(epoch, 315532800)  # ZIP cannot represent dates before 1980.
    return time.gmtime(value)[:6]


def package_source(root: Path, output: Path, *, epoch: int) -> str:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    version = release_version(root)
    prefix = f"dicom-privacy-auditor-v{version}"
    timestamp = _zip_timestamp(epoch)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in collect_files(root, output):
                relative = path.relative_to(root).as_posix()
                info = zipfile.ZipInfo(f"{prefix}/{relative}", date_time=timestamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                executable = bool(path.stat().st_mode & stat.S_IXUSR)
                info.external_attr = ((0o755 if executable else 0o644) & 0xFFFF) << 16
                info.flag_bits |= 0x800
                archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)),
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    version = release_version(root)
    output = args.output or root / "dist" / f"dicom-privacy-auditor-v{version}-source.zip"
    digest = package_source(root, output, epoch=args.source_date_epoch)
    print(f"{digest}  {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
