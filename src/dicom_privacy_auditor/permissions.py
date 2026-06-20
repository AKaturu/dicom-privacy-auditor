"""Private, atomic filesystem helpers for potentially sensitive local artifacts."""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

PRIVATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR
PRIVATE_DIRECTORY_MODE = stat.S_IRWXU


def restrict_file(path: str | Path) -> Path:
    """Restrict an existing regular file to its owner and refuse symbolic links."""

    target = Path(path)
    if target.is_symlink():
        raise ValueError(f"Refusing to change permissions through a symbolic link: {target}")
    if not target.is_file():
        raise FileNotFoundError(target)
    os.chmod(target, PRIVATE_FILE_MODE)
    return target


def restrict_directory(path: str | Path) -> Path:
    """Restrict an existing directory to its owner and refuse symbolic links."""

    target = Path(path)
    if target.is_symlink():
        raise ValueError(f"Refusing to change permissions through a symbolic link: {target}")
    if not target.is_dir():
        raise NotADirectoryError(target)
    os.chmod(target, PRIVATE_DIRECTORY_MODE)
    return target


def validate_file_transfer(source: str | Path, destination: str | Path) -> tuple[Path, Path]:
    """Validate one regular-file transfer without following source/destination symlinks."""

    source_path = Path(source)
    destination_path = Path(destination)
    if source_path.is_symlink() or not source_path.is_file():
        raise ValueError(f"Source must be a regular non-symbolic-link file: {source_path}")
    if destination_path.is_symlink():
        raise ValueError(f"Destination must not be a symbolic link: {destination_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.parent.is_symlink():
        raise ValueError(f"Destination parent must not be a symbolic link: {destination_path.parent}")
    if source_path.resolve() == destination_path.resolve(strict=False):
        raise ValueError("Source and destination must be different files")
    return source_path, destination_path


def atomic_write_bytes_private(path: str | Path, payload: bytes) -> Path:
    """Atomically write owner-only bytes without following an existing destination symlink."""

    destination = Path(path)
    if destination.is_symlink():
        raise ValueError(f"Destination must not be a symbolic link: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.parent.is_symlink():
        raise ValueError(f"Destination parent must not be a symbolic link: {destination.parent}")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, PRIVATE_FILE_MODE)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def atomic_copy_private(source: str | Path, destination: str | Path, *, max_bytes: int | None = None) -> Path:
    """Atomically copy a regular file into an owner-only destination.

    ``max_bytes`` bounds both the initial source size and bytes streamed, so a
    concurrently growing file cannot bypass the configured limit.
    """

    source_path, destination_path = validate_file_transfer(source, destination)
    if max_bytes is not None and max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if max_bytes is not None and source_path.stat().st_size > max_bytes:
        raise RuntimeError(f"Source exceeded max_bytes ({max_bytes})")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination_path.name}.", dir=destination_path.parent
    )
    temporary = Path(temporary_name)
    try:
        copied = 0
        with source_path.open("rb") as input_handle, os.fdopen(descriptor, "wb") as output_handle:
            while chunk := input_handle.read(1024 * 1024):
                copied += len(chunk)
                if max_bytes is not None and copied > max_bytes:
                    raise RuntimeError(f"Source exceeded max_bytes ({max_bytes})")
                output_handle.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        os.replace(temporary, destination_path)
        os.chmod(destination_path, PRIVATE_FILE_MODE)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination_path


def atomic_write_text(path: str | Path, payload: str, *, encoding: str = "utf-8") -> Path:
    """Atomically write owner-only text without following destination symlinks."""
    return atomic_write_bytes_private(path, payload.encode(encoding))
