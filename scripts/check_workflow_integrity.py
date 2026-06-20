#!/usr/bin/env python3
"""Parse GitHub Actions workflow YAML and enforce a minimal structural contract."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def validate_workflow(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        payload: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return [f"{path}: invalid YAML: {exc}"]
    # PyYAML follows YAML 1.1 and parses the GitHub Actions key ``on`` as
    # boolean true. Normalize that mapping key after safe parsing.
    if isinstance(payload, dict) and True in payload and "on" not in payload:
        payload["on"] = payload.pop(True)
    if not isinstance(payload, dict):
        return [f"{path}: workflow root must be a mapping"]
    for key in ("name", "on", "jobs"):
        if key not in payload:
            errors.append(f"{path}: missing top-level key {key!r}")
    jobs = payload.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append(f"{path}: jobs must be a non-empty mapping")
    elif any(not isinstance(job, dict) for job in jobs.values()):
        errors.append(f"{path}: every job must be a mapping")
    return errors


def check(root: Path) -> list[str]:
    workflow_dir = root / ".github" / "workflows"
    paths = sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))
    if not paths:
        return [f"{workflow_dir}: no workflow files found"]
    return [error for path in paths for error in validate_workflow(path)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = check(args.root.resolve())
    if errors:
        print("\n".join(errors))
        return 1
    print("GitHub Actions workflow YAML is valid and structurally complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
