#!/usr/bin/env python3
"""Normalize a Python source distribution into a safe, byte-reproducible tar.gz."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import stat
import tarfile
from io import BytesIO
from pathlib import Path, PurePosixPath

DEFAULT_SOURCE_DATE_EPOCH = 1781913600
DEFAULT_MAX_MEMBERS = 20_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_MEMBER_BYTES = 512 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _safe_name(name: str) -> str:
    if not name or "\\" in name or "\x00" in name:
        raise ValueError(f"Unsafe archive member name: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"Unsafe archive member path: {name!r}")
    return path.as_posix().rstrip("/")


def _normalized_info(source: tarfile.TarInfo, *, name: str, epoch: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.mtime = epoch
    info.pax_headers = {}
    if source.isdir():
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        info.size = 0
    elif source.isfile():
        info.type = tarfile.REGTYPE
        info.mode = 0o755 if source.mode & stat.S_IXUSR else 0o644
        info.size = source.size
    else:
        raise ValueError(
            f"Unsupported archive member type for {source.name!r}; links and special files are refused"
        )
    return info


def normalize_sdist(
    source: Path,
    output: Path | None = None,
    *,
    epoch: int,
    max_members: int = DEFAULT_MAX_MEMBERS,
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES,
    max_member_bytes: int = DEFAULT_MAX_MEMBER_BYTES,
) -> str:
    """Safely rewrite *source* with deterministic gzip/tar metadata and ordering."""

    if min(max_members, max_uncompressed_bytes, max_member_bytes) <= 0:
        raise ValueError("Archive resource limits must be positive")
    source = source.resolve()
    if not source.is_file() or source.is_symlink():
        raise FileNotFoundError(source)
    output = (output or source).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.unlink(missing_ok=True)

    members: list[tuple[str, tarfile.TarInfo, bytes | None]] = []
    names: set[str] = set()
    total_size = 0
    with tarfile.open(source, mode="r:gz") as archive:
        archive_members = archive.getmembers()
        if len(archive_members) > max_members:
            raise ValueError(
                f"Source distribution has {len(archive_members)} members; maximum is {max_members}"
            )
        for member in archive_members:
            name = _safe_name(member.name)
            if name in names:
                raise ValueError(f"Duplicate archive member: {name}")
            names.add(name)
            if member.size < 0 or member.size > max_member_bytes:
                raise ValueError(
                    f"Archive member {name!r} declares {member.size} bytes; maximum is {max_member_bytes}"
                )
            total_size += member.size
            if total_size > max_uncompressed_bytes:
                raise ValueError(
                    f"Source distribution declares {total_size} uncompressed bytes; "
                    f"maximum is {max_uncompressed_bytes}"
                )
            payload: bytes | None = None
            if member.isfile():
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ValueError(f"Could not read archive member: {name}")
                payload = extracted.read(member.size + 1)
                if len(payload) != member.size:
                    raise ValueError(f"Truncated or oversized archive member: {name}")
            members.append((name, member, payload))

    try:
        with temporary.open("wb") as raw:
            with gzip.GzipFile(
                filename="", mode="wb", fileobj=raw, mtime=epoch, compresslevel=9
            ) as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                    for name, original, payload in sorted(members, key=lambda item: item[0]):
                        info = _normalized_info(original, name=name, epoch=epoch)
                        archive.addfile(info, None if payload is None else BytesIO(payload))
        os.replace(temporary, output)
        os.chmod(output, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return _sha256(output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)),
    )
    parser.add_argument("--max-members", type=int, default=DEFAULT_MAX_MEMBERS)
    parser.add_argument("--max-uncompressed-bytes", type=int, default=DEFAULT_MAX_UNCOMPRESSED_BYTES)
    parser.add_argument("--max-member-bytes", type=int, default=DEFAULT_MAX_MEMBER_BYTES)
    args = parser.parse_args(argv)
    digest = normalize_sdist(
        args.source,
        args.output,
        epoch=args.source_date_epoch,
        max_members=args.max_members,
        max_uncompressed_bytes=args.max_uncompressed_bytes,
        max_member_bytes=args.max_member_bytes,
    )
    print(f"{digest}  {args.output or args.source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
