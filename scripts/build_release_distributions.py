#!/usr/bin/env python3
"""Build a wheel and normalized reproducible sdist for a release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from normalize_sdist import DEFAULT_SOURCE_DATE_EPOCH, normalize_sdist


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_distributions(
    root: Path, output: Path, *, epoch: int, clean: bool = False
) -> list[dict[str, object]]:
    root = root.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if clean:
        for pattern in ("*.whl", "*.tar.gz"):
            for path in output.glob(pattern):
                path.unlink()
    elif list(output.glob("*.whl")) or list(output.glob("*.tar.gz")):
        raise FileExistsError(f"Refusing to mix release artifacts in non-empty output directory: {output}")

    env = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch), "PYTHONHASHSEED": "0"}
    subprocess.run(
        [sys.executable, "-m", "build", "--no-isolation", "--outdir", str(output)],
        cwd=root,
        env=env,
        check=True,
    )
    wheels = sorted(output.glob("*.whl"))
    sdists = sorted(output.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise RuntimeError(
            f"Expected one wheel and one sdist, found {len(wheels)} wheel(s), {len(sdists)} sdist(s)"
        )
    normalize_sdist(sdists[0], epoch=epoch)
    return [
        {"name": path.name, "sha256": _sha256(path), "size_bytes": path.stat().st_size}
        for path in (wheels[0], sdists[0])
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dist"))
    parser.add_argument("--clean", action="store_true")
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)),
    )
    args = parser.parse_args(argv)
    output = args.output if args.output.is_absolute() else args.root / args.output
    artifacts = build_distributions(args.root, output, epoch=args.source_date_epoch, clean=args.clean)
    print(json.dumps({"artifacts": artifacts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
