#!/usr/bin/env python3
"""Generate a reproducible CycloneDX runtime SBOM with explicit root dependency edges."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def _runtime_roots(path: Path) -> set[str]:
    roots: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        roots.add(canonicalize_name(Requirement(line).name))
    if not roots:
        raise ValueError(f"No runtime dependency roots found in {path}")
    return roots


def attach_direct_dependencies(payload: dict[str, Any], roots: set[str]) -> dict[str, Any]:
    components = payload.get("components")
    dependencies = payload.get("dependencies")
    if not isinstance(components, list) or not isinstance(dependencies, list):
        raise ValueError("CycloneDX document is missing components or dependencies")
    refs: dict[str, str] = {}
    for component in components:
        if isinstance(component, dict) and isinstance(component.get("name"), str):
            ref = component.get("bom-ref")
            if isinstance(ref, str):
                refs[canonicalize_name(component["name"])] = ref
    missing = sorted(roots - set(refs))
    if missing:
        raise ValueError(f"Runtime dependency roots missing from SBOM: {missing}")
    root_entry = next(
        (entry for entry in dependencies if isinstance(entry, dict) and entry.get("ref") == "root-component"),
        None,
    )
    if root_entry is None:
        root_entry = {"ref": "root-component"}
        dependencies.append(root_entry)
    root_entry["dependsOn"] = sorted(refs[name] for name in roots)
    dependencies.sort(key=lambda item: str(item.get("ref", "")) if isinstance(item, dict) else "")
    return payload


def generate(root: Path, output: Path, *, lock: Path, roots_file: Path) -> None:
    root = root.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dpa-sbom-") as raw:
        temporary = Path(raw) / "sbom.json"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "cyclonedx_py",
                "requirements",
                str(lock),
                "--pyproject",
                str(root / "pyproject.toml"),
                "--output-reproducible",
                "--output-format",
                "JSON",
                "--output-file",
                str(temporary),
            ],
            cwd=root,
            check=True,
        )
        payload = json.loads(temporary.read_text(encoding="utf-8"))
    attach_direct_dependencies(payload, _runtime_roots(roots_file))
    staged = output.with_suffix(output.suffix + ".tmp")
    staged.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(staged, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist/SBOM-runtime.cdx.json"))
    parser.add_argument(
        "--lock",
        type=Path,
        default=Path("requirements/locks/cp313-linux-x86_64-runtime.txt"),
    )
    parser.add_argument("--roots", type=Path, default=Path("requirements/lock-input.txt"))
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    lock = args.lock if args.lock.is_absolute() else root / args.lock
    roots = args.roots if args.roots.is_absolute() else root / args.roots
    generate(root, output, lock=lock, roots_file=roots)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
