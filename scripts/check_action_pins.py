from __future__ import annotations

import re
import sys
from pathlib import Path

PIN = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)


def check(root: str | Path = ".github/workflows") -> list[str]:
    failures: list[str] = []
    for path in sorted(Path(root).glob("*.y*ml")):
        for match in USES.finditer(path.read_text(encoding="utf-8")):
            value = match.group(1)
            if value.startswith("./") or value.startswith("docker://"):
                continue
            if "@" not in value:
                failures.append(f"{path}: action has no ref: {value}")
                continue
            action, ref = value.rsplit("@", 1)
            if not PIN.fullmatch(ref):
                failures.append(f"{path}: {action} is not pinned to a 40-character commit SHA: {ref}")
    return failures


def main() -> int:
    failures = check(sys.argv[1] if len(sys.argv) > 1 else ".github/workflows")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print("All external GitHub Actions are pinned to immutable commit SHAs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
