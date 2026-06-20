from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

SOURCE_DATE_EPOCH = 1781913600


@dataclass(frozen=True)
class BuildArtifacts:
    wheel: Path
    sdist: Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_source(source: Path, destination: Path) -> None:
    ignored = shutil.ignore_patterns(
        ".git",
        ".venv",
        "dist",
        "build",
        "*.egg-info",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".hypothesis",
        ".coverage",
    )
    shutil.copytree(source, destination, ignore=ignored)


def build(source: Path, destination: Path) -> BuildArtifacts:
    env = {**os.environ, "SOURCE_DATE_EPOCH": str(SOURCE_DATE_EPOCH), "PYTHONHASHSEED": "0"}
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(destination)],
        cwd=source,
        env=env,
        check=True,
    )
    wheels = list(destination.glob("*.whl"))
    sdists = list(destination.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(
            f"Expected one wheel and one sdist, found {len(wheels)} wheel(s), {len(sdists)} sdist(s)"
        )
    subprocess.run(
        [
            sys.executable,
            str(source / "scripts" / "normalize_sdist.py"),
            str(sdists[0]),
            "--source-date-epoch",
            str(SOURCE_DATE_EPOCH),
        ],
        cwd=source,
        env=env,
        check=True,
    )
    return BuildArtifacts(wheel=wheels[0], sdist=sdists[0])


def main() -> int:
    project = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    with tempfile.TemporaryDirectory(prefix="dpa-repro-") as raw:
        root = Path(raw)
        first_source, second_source = root / "source-a", root / "source-b"
        copy_source(project, first_source)
        copy_source(project, second_source)
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(build, first_source, root / "dist-a")
            second_future = executor.submit(build, second_source, root / "dist-b")
            first = first_future.result()
            second = second_future.result()
        comparisons = {
            "wheel": (digest(first.wheel), digest(second.wheel)),
            "sdist": (digest(first.sdist), digest(second.sdist)),
        }
        failed = False
        for artifact, (first_hash, second_hash) in comparisons.items():
            print(f"{artifact}.first={first_hash}\n{artifact}.second={second_hash}")
            failed = failed or first_hash != second_hash
        if failed:
            print("Build artifacts were not byte-for-byte reproducible.", file=sys.stderr)
            return 1
    print("Wheel and normalized sdist builds are byte-for-byte reproducible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
