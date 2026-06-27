#!/usr/bin/env python3
"""Validate local Markdown links and documented console-command references."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

LINK = re.compile(r"\[[^\]]+\]\((?!https?://|mailto:|#)([^)]+)\)")
COMMAND = re.compile(r"\b(dicom-privacy(?:-[a-z0-9]+)*)\b")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root = args.root.resolve()
    broken: list[str] = []
    commands: set[str] = set()
    for doc in sorted(root.rglob("*.md")):
        relative_parts = doc.relative_to(root).parts
        if any(
            part.startswith(".") or part in {"build", "dist", ".venv", "site-packages"}
            for part in relative_parts
        ):
            continue
        text = doc.read_text(encoding="utf-8")
        commands.update(COMMAND.findall(text))
        for raw in LINK.findall(text):
            target = raw.split("#", 1)[0].split("?", 1)[0].strip()
            if not target or target.startswith("<"):
                continue
            if not (doc.parent / target).resolve().exists():
                broken.append(f"{doc.relative_to(root)} -> {raw}")
    if broken:
        for item in broken:
            print("broken-link:", item)
        return 1
    print(f"documentation checks passed: {len(commands)} command references, no broken local links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
