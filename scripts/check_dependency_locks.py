#!/usr/bin/env python3
"""Check that runtime dependency roots and the hashed platform lock remain synchronized."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PIN_PATTERN = re.compile(
    r"^([A-Za-z0-9_.-]+)==([^\s]+)\s+--hash=sha256:[0-9a-f]{64}(?:\s+--hash=sha256:[0-9a-f]{64})*$"
)


def _requirements(path: Path) -> list[Requirement]:
    result: list[Requirement] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        result.append(Requirement(line))
    return result


def check(root: Path) -> list[str]:
    errors: list[str] = []
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project_roots = {
        canonicalize_name(Requirement(item).name) for item in pyproject["project"]["dependencies"]
    }
    input_requirements = _requirements(root / "requirements" / "lock-input.txt")
    input_roots = {canonicalize_name(item.name) for item in input_requirements}
    if project_roots != input_roots:
        missing = sorted(project_roots - input_roots)
        extra = sorted(input_roots - project_roots)
        if missing:
            errors.append(f"runtime roots missing from lock-input.txt: {', '.join(missing)}")
        if extra:
            errors.append(f"lock-input.txt contains non-runtime roots: {', '.join(extra)}")

    lock = root / "requirements" / "locks" / "cp313-linux-x86_64-runtime.txt"
    locked_names: set[str] = set()
    locked_versions: dict[str, str] = {}
    for line_number, raw in enumerate(lock.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = PIN_PATTERN.fullmatch(line)
        if not match:
            errors.append(f"unhashed or malformed lock entry at line {line_number}: {line}")
            continue
        name = canonicalize_name(match.group(1))
        if name in locked_names:
            errors.append(f"duplicate locked distribution: {name}")
        locked_names.add(name)
        locked_versions[name] = match.group(2)
    missing_locked = sorted(project_roots - locked_names)
    if missing_locked:
        errors.append(f"runtime roots missing from hashed lock: {', '.join(missing_locked)}")

    reproducible = root / "requirements-reproducible.txt"
    if reproducible.is_file():
        reproducible_versions: dict[str, str] = {}
        for requirement in _requirements(reproducible):
            exact = [item.version for item in requirement.specifier if item.operator == "=="]
            if len(exact) == 1:
                reproducible_versions[canonicalize_name(requirement.name)] = exact[0]
        for name in sorted(project_roots):
            expected = reproducible_versions.get(name)
            actual = locked_versions.get(name)
            if expected is None:
                errors.append(f"runtime root missing exact validation pin: {name}")
            elif actual is not None and actual != expected:
                errors.append(
                    f"runtime lock/version validation mismatch for {name}: lock={actual}, validation={expected}"
                )
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    errors = check(args.root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("Runtime dependency roots and hashed lock are synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
