#!/usr/bin/env python3
"""Reject prohibited standards, credentials, keys, databases, and unsafe release archives."""

from __future__ import annotations

import argparse
import stat
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import IO

SENSITIVE_FILENAMES = {
    ".env",
    "secrets.toml",
    "certificate.p12",
    "certificate.pfx",
    "id_rsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = {".p12", ".pfx", ".key", ".sqlite", ".sqlite3"}
IGNORED_DIRECTORIES = {
    ".git",
    ".venv",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
}
PRIVATE_KEY_MARKERS = (
    b"-----BEGIN " + b"PRIVATE KEY-----",
    b"-----BEGIN RSA " + b"PRIVATE KEY-----",
    b"-----BEGIN EC " + b"PRIVATE KEY-----",
    b"-----BEGIN OPENSSH " + b"PRIVATE KEY-----",
)
DEFAULT_MAX_ARCHIVE_MEMBERS = 100_000
DEFAULT_MAX_MEMBER_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024
MAX_KEY_SCAN_MEMBER_BYTES = 2_000_000
MAX_KEY_SCAN_TOTAL_BYTES = 100_000_000


def prohibited_name(name: str) -> bool:
    normalized = name.replace("\\", "/").casefold()
    filename = normalized.rsplit("/", 1)[-1]
    if filename.startswith("part15") and filename.endswith((".docx", ".pdf", ".odt", ".xml")):
        return True
    if "ps315_" in filename and "_table_e1_" in filename and filename.endswith(".json"):
        return True
    if filename in SENSITIVE_FILENAMES or Path(filename).suffix in SENSITIVE_SUFFIXES:
        return True
    return False


def unsafe_archive_name(name: str) -> bool:
    normalized = name.replace("\\", "/")
    if not normalized or "\x00" in normalized:
        return True
    path = PurePosixPath(normalized)
    return (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or normalized.startswith(("~/", "//"))
    )


def iter_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        yield path
        return
    for candidate in path.rglob("*"):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            relative = candidate.relative_to(path)
        except ValueError:
            relative = candidate
        if any(part in IGNORED_DIRECTORIES for part in relative.parts):
            continue
        yield candidate


def _stream_contains_private_key(handle: IO[bytes], *, limit: int) -> bool:
    payload = handle.read(limit + 1)
    if len(payload) > limit:
        return False
    return any(marker in payload for marker in PRIVATE_KEY_MARKERS)


def contains_private_key(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_KEY_SCAN_MEMBER_BYTES:
            return False
        with path.open("rb") as handle:
            return _stream_contains_private_key(handle, limit=MAX_KEY_SCAN_MEMBER_BYTES)
    except OSError:
        return False


def _common_archive_issues(
    archive_path: Path,
    names_and_sizes: Iterable[tuple[str, int]],
    *,
    max_members: int,
    max_member_bytes: int,
    max_uncompressed_bytes: int,
) -> tuple[list[str], set[str]]:
    issues: list[str] = []
    names: set[str] = set()
    total = 0
    count = 0
    for name, size in names_and_sizes:
        count += 1
        if count > max_members:
            issues.append(f"{archive_path}:archive has more than {max_members} members")
            break
        normalized = name.replace("\\", "/")
        if normalized in names:
            issues.append(f"{archive_path}:{name} (duplicate archive member)")
        names.add(normalized)
        if unsafe_archive_name(name):
            issues.append(f"{archive_path}:{name} (unsafe archive path)")
        if prohibited_name(name):
            issues.append(f"{archive_path}:{name}")
        if size < 0 or size > max_member_bytes:
            issues.append(f"{archive_path}:{name} (declared size {size} exceeds {max_member_bytes})")
        total += max(size, 0)
        if total > max_uncompressed_bytes:
            issues.append(f"{archive_path}:declared uncompressed size exceeds {max_uncompressed_bytes}")
            break
    return issues, names


def inspect_archive(
    path: Path,
    *,
    max_members: int = DEFAULT_MAX_ARCHIVE_MEMBERS,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
) -> list[str]:
    if min(max_members, max_member_bytes, max_uncompressed_bytes) <= 0:
        raise ValueError("Archive resource limits must be positive")
    issues: list[str] = []
    scanned = 0
    if path.suffix in {".whl", ".zip"}:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            common, _ = _common_archive_issues(
                path,
                ((item.filename, item.file_size) for item in infos),
                max_members=max_members,
                max_member_bytes=max_member_bytes,
                max_uncompressed_bytes=max_uncompressed_bytes,
            )
            issues.extend(common)
            for zip_info in infos[:max_members]:
                mode = (zip_info.external_attr >> 16) & 0o177777
                file_type = stat.S_IFMT(mode)
                if zip_info.flag_bits & 0x1:
                    issues.append(f"{path}:{zip_info.filename} (encrypted archive member)")
                if file_type and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                    issues.append(f"{path}:{zip_info.filename} (link or special archive member)")
                if (
                    not zip_info.is_dir()
                    and zip_info.file_size <= MAX_KEY_SCAN_MEMBER_BYTES
                    and scanned + zip_info.file_size <= MAX_KEY_SCAN_TOTAL_BYTES
                ):
                    scanned += zip_info.file_size
                    with archive.open(zip_info) as handle:
                        if _stream_contains_private_key(handle, limit=MAX_KEY_SCAN_MEMBER_BYTES):
                            issues.append(f"{path}:{zip_info.filename} (embedded private key material)")
        return issues
    if path.name.endswith((".tar.gz", ".tgz", ".tar")):
        with tarfile.open(path) as archive:
            members = archive.getmembers()
            common, _ = _common_archive_issues(
                path,
                ((item.name, item.size) for item in members),
                max_members=max_members,
                max_member_bytes=max_member_bytes,
                max_uncompressed_bytes=max_uncompressed_bytes,
            )
            issues.extend(common)
            for tar_info in members[:max_members]:
                if not (tar_info.isfile() or tar_info.isdir()):
                    issues.append(f"{path}:{tar_info.name} (link or special archive member)")
                if (
                    tar_info.isfile()
                    and tar_info.size <= MAX_KEY_SCAN_MEMBER_BYTES
                    and scanned + tar_info.size <= MAX_KEY_SCAN_TOTAL_BYTES
                ):
                    scanned += tar_info.size
                    extracted = archive.extractfile(tar_info)
                    if extracted is None:
                        issues.append(f"{path}:{tar_info.name} (unreadable archive member)")
                    elif _stream_contains_private_key(extracted, limit=MAX_KEY_SCAN_MEMBER_BYTES):
                        issues.append(f"{path}:{tar_info.name} (embedded private key material)")
        return issues
    return issues


def check(paths: list[Path]) -> list[str]:
    violations: list[str] = []
    for supplied in paths:
        if supplied.is_symlink():
            violations.append(f"{supplied}:symbolic-link release input")
            continue
        for candidate in iter_files(supplied):
            if prohibited_name(candidate.name):
                violations.append(str(candidate))
            if contains_private_key(candidate):
                violations.append(f"{candidate}:embedded private key material")
            try:
                violations.extend(inspect_archive(candidate))
            except (tarfile.TarError, zipfile.BadZipFile, OSError, RuntimeError) as exc:
                violations.append(f"{candidate}:unreadable release archive ({exc})")
    return sorted(set(violations))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    violations = check(args.paths)
    if violations:
        print("Prohibited or unsafe release content found:")
        for violation in violations:
            print(f"- {violation}")
        return 1
    print("No prohibited standards, credentials, keys, databases, or unsafe archive content found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
