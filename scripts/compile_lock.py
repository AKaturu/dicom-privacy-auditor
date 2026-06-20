#!/usr/bin/env python3
"""Regenerate a normalized, fully hashed runtime lock with uv."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

PIN_PATTERN = re.compile(
    r"^([A-Za-z0-9_.-]+)==([^\s]+)\s+--hash=sha256:[0-9a-f]{64}(?:\s+--hash=sha256:[0-9a-f]{64})*$"
)


def normalize_uv_lock(payload: str) -> list[str]:
    """Collapse uv continuation lines into the repository's deterministic lock format."""

    logical: list[str] = []
    buffer = ""
    for raw in payload.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        continued = stripped.endswith("\\")
        part = stripped[:-1].strip() if continued else stripped
        buffer = f"{buffer} {part}".strip()
        if continued:
            continue
        normalized = " ".join(buffer.split())
        if not PIN_PATTERN.fullmatch(normalized):
            raise ValueError(f"uv emitted an unhashed or unsupported lock entry: {normalized}")
        logical.append(normalized)
        buffer = ""
    if buffer:
        raise ValueError("uv lock output ended with an incomplete continuation")
    if not logical:
        raise ValueError("uv lock output contained no requirements")
    names = [PIN_PATTERN.fullmatch(item).group(1).casefold() for item in logical]  # type: ignore[union-attr]
    if len(names) != len(set(names)):
        raise ValueError("uv lock output contained duplicate distributions")
    return logical


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("requirements/lock-input.txt"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--python-version", default="3.13")
    parser.add_argument("--python-platform", default="x86_64-manylinux_2_28")
    args = parser.parse_args(argv)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dpa-lock-") as raw:
        generated = Path(raw) / "uv-lock.txt"
        command = [
            "uv",
            "pip",
            "compile",
            str(args.input),
            "--generate-hashes",
            "--no-annotate",
            "--no-header",
            "--no-emit-index-url",
            "--python-version",
            args.python_version,
            "--python-platform",
            args.python_platform,
            "--output-file",
            str(generated),
        ]
        try:
            completed = subprocess.run(command, check=False)
        except FileNotFoundError:
            print("uv is required to regenerate locks: https://docs.astral.sh/uv/", file=sys.stderr)
            return 2
        if completed.returncode != 0:
            return completed.returncode
        try:
            entries = normalize_uv_lock(generated.read_text(encoding="utf-8"))
        except ValueError as exc:
            print(f"Failed to normalize uv lock output: {exc}", file=sys.stderr)
            return 1
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{args.output.name}.", dir=args.output.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(
                    "# Canonical reproducibility lock: CPython "
                    f"{args.python_version}, Linux x86_64, manylinux-compatible.\n"
                )
                handle.write("# Regenerate with scripts/compile_lock.py and review every change.\n")
                handle.write("\n".join(entries) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, args.output)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
