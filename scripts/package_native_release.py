#!/usr/bin/env python3
"""Package native PyInstaller outputs into a normalized versioned release archive."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import stat
import sys
import tarfile
import time
import zipfile
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

DEFAULT_SOURCE_DATE_EPOCH = 1781913600


def _project_version(root: Path) -> str:
    data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def _normalized_platform() -> tuple[str, str]:
    system_map = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}
    arch_map = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}
    system = system_map.get(platform.system(), platform.system().lower())
    machine = platform.machine().lower()
    return system, arch_map.get(machine, machine)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _copy_executables(
    root: Path, dist: Path, staging: Path, system: str, *, epoch: int, version: str
) -> None:
    cli_name = "DICOMPrivacyAuditor-CLI.exe" if system == "windows" else "DICOMPrivacyAuditor-CLI"
    gui_name = "DICOMPrivacyAuditor.exe" if system == "windows" else "DICOMPrivacyAuditor"

    cli = dist / cli_name
    if not cli.exists():
        raise FileNotFoundError(f"CLI executable not found: {cli}")
    shutil.copy2(cli, staging / cli.name)

    if system == "macos":
        app = dist / "DICOMPrivacyAuditor.app"
        if not app.exists():
            raise FileNotFoundError(f"macOS app bundle not found: {app}")
        shutil.copytree(app, staging / app.name, symlinks=True)
    else:
        gui = dist / gui_name
        if not gui.exists():
            raise FileNotFoundError(f"Desktop executable not found: {gui}")
        shutil.copy2(gui, staging / gui.name)

    shutil.copy2(root / "packaging" / "EXECUTABLE_README.txt", staging / "EXECUTABLE_README.txt")
    for name in ("LICENSE", "NOTICE", "SECURITY.md"):
        shutil.copy2(root / name, staging / name)

    build_info = {
        "application": "DICOM Privacy Auditor",
        "version": version,
        "operating_system": system,
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "source_revision": os.environ.get("GITHUB_SHA") or os.environ.get("SOURCE_REVISION"),
        "source_date_epoch": epoch,
        "research_prototype": True,
        "dicom_standard_content_bundled": False,
        "ps315_setup_required": True,
    }
    (staging / "BUILD_INFO.json").write_text(json.dumps(build_info, indent=2) + "\n", encoding="utf-8")

    if system != "windows":
        for executable in [staging / "DICOMPrivacyAuditor-CLI", staging / "DICOMPrivacyAuditor"]:
            if executable.exists() and executable.is_file():
                executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _zip_time(epoch: int) -> tuple[int, int, int, int, int, int]:
    return time.gmtime(max(epoch, 315532800))[:6]


def _write_zip(staging: Path, archive: Path, package_name: str, *, epoch: int) -> None:
    timestamp = _zip_time(epoch)
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
            for item in sorted(staging.rglob("*"), key=lambda path: path.relative_to(staging).as_posix()):
                if not item.is_file():
                    continue
                relative = (Path(package_name) / item.relative_to(staging)).as_posix()
                info = zipfile.ZipInfo(relative, date_time=timestamp)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_DEFLATED
                mode = stat.S_IMODE(item.stat().st_mode)
                info.external_attr = ((mode or 0o644) & 0xFFFF) << 16
                info.flag_bits |= 0x800
                handle.writestr(info, item.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
        os.replace(temporary, archive)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_tar_gz(staging: Path, archive: Path, package_name: str, *, epoch: int) -> None:
    temporary = archive.with_suffix(archive.suffix + ".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, mtime=epoch, compresslevel=9
            ) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as handle:
                    root_info = tarfile.TarInfo(package_name)
                    root_info.type = tarfile.DIRTYPE
                    root_info.mode = 0o755
                    root_info.mtime = epoch
                    handle.addfile(root_info)
                    for item in sorted(
                        staging.rglob("*"), key=lambda path: path.relative_to(staging).as_posix()
                    ):
                        arcname = (Path(package_name) / item.relative_to(staging)).as_posix()
                        info = handle.gettarinfo(str(item), arcname=arcname)
                        info.uid = 0
                        info.gid = 0
                        info.uname = ""
                        info.gname = ""
                        info.mtime = epoch
                        if info.isdir():
                            info.mode = 0o755
                        elif info.isfile():
                            info.mode = 0o755 if item.stat().st_mode & stat.S_IXUSR else 0o644
                        if info.isfile():
                            with item.open("rb") as source:
                                handle.addfile(info, source)
                        else:
                            handle.addfile(info)
        os.replace(temporary, archive)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def package(
    root: Path, dist: Path, release_dir: Path, *, epoch: int = DEFAULT_SOURCE_DATE_EPOCH
) -> list[Path]:
    system, arch = _normalized_platform()
    release_dir.mkdir(parents=True, exist_ok=True)
    version = _project_version(root)
    package_name = f"dicom-privacy-auditor-v{version}-{system}-{arch}"
    staging = release_dir / package_name
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    _copy_executables(root, dist, staging, system, epoch=epoch, version=version)

    if system == "windows":
        archive = release_dir / f"{package_name}.zip"
        archive.unlink(missing_ok=True)
        _write_zip(staging, archive, package_name, epoch=epoch)
    else:
        archive = release_dir / f"{package_name}.tar.gz"
        archive.unlink(missing_ok=True)
        _write_tar_gz(staging, archive, package_name, epoch=epoch)

    checksum = release_dir / f"{archive.name}.sha256"
    checksum.write_text(f"{_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    shutil.rmtree(staging)
    print(archive)
    print(checksum)
    return [archive, checksum]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist") / "native")
    parser.add_argument("--release-dir", type=Path, default=Path("dist") / "release")
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)),
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    package(root, args.dist.resolve(), args.release_dir.resolve(), epoch=args.source_date_epoch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
