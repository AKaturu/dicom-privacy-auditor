from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

_SAFE_CASE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def validate_case_id(value: str) -> str:
    case_id = str(value).strip()
    if not _SAFE_CASE_ID.fullmatch(case_id) or case_id in {".", ".."}:
        raise ValueError("case_id must contain only letters, numbers, dot, underscore, or hyphen")
    return case_id


def validate_watched_directories(input_dir: Path, output_dir: Path) -> None:
    if input_dir.is_symlink() or output_dir.is_symlink():
        raise ValueError("watched input/output directories must not be symbolic links")
    input_resolved = input_dir.resolve()
    output_resolved = output_dir.resolve()
    if (
        input_resolved == output_resolved
        or input_resolved in output_resolved.parents
        or output_resolved in input_resolved.parents
    ):
        raise ValueError("watched input and output directories must not overlap")


def safe_ref(value: str | Path) -> str:
    return "sha256:" + hashlib.sha256(str(value).encode()).hexdigest()[:16]


def load_config(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Adapter configuration must be a JSON object")
    return payload


def command_tokens(command: str | list[str] | None) -> list[str] | None:
    if command is None:
        return None
    return shlex.split(command) if isinstance(command, str) else list(command)


def launch(command: str | list[str] | None, *, cwd: str | Path | None = None) -> subprocess.Popen | None:
    tokens = command_tokens(command)
    if not tokens:
        return None
    return subprocess.Popen(
        tokens,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def terminate(process: subprocess.Popen | None, timeout: float = 10.0) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def wait_for_new_file(
    root: Path,
    before: dict[Path, tuple[int, int]],
    *,
    timeout_seconds: float,
    poll_seconds: float,
) -> Path:
    if timeout_seconds <= 0 or poll_seconds <= 0:
        raise ValueError("timeout_seconds and poll_seconds must be positive")
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"watched output root must be a regular directory: {root}")
    deadline = time.monotonic() + timeout_seconds
    stable: dict[Path, tuple[int, int, int]] = {}
    while time.monotonic() < deadline:
        for path in root.rglob("*"):
            if path.is_symlink():
                raise ValueError(f"watched output must not contain symbolic links: {path}")
            if not path.is_file():
                continue
            stat = path.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            if before.get(path) == signature:
                continue
            old = stable.get(path)
            if old and old[:2] == signature:
                count = old[2] + 1
            else:
                count = 1
            stable[path] = (signature[0], signature[1], count)
            if count >= 2 and signature[0] > 0:
                return path
        time.sleep(poll_seconds)
    raise TimeoutError(f"No new stable output file appeared within {timeout_seconds} seconds")


def snapshot(root: Path) -> dict[Path, tuple[int, int]]:
    if root.is_symlink():
        raise ValueError(f"watched output root must not be a symbolic link: {root}")
    if not root.exists():
        return {}
    output: dict[Path, tuple[int, int]] = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"watched output must not contain symbolic links: {path}")
        if path.is_file():
            stat_result = path.stat()
            output[path] = (stat_result.st_size, stat_result.st_mtime_ns)
    return output
