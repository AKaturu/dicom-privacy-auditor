#!/usr/bin/env python3
"""Run Twine metadata validation over every built Python distribution."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    args = parser.parse_args()
    artifacts = sorted([*args.dist.glob("*.whl"), *args.dist.glob("*.tar.gz")])
    if not artifacts:
        print("no Python distributions found")
        return 1
    return subprocess.run(
        [sys.executable, "-m", "twine", "check", *map(str, artifacts)],
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
