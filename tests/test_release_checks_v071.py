from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_documentation_checker_passes_repository() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "scripts/check_documentation.py", str(root)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_documentation_checker_detects_broken_link(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("[missing](not-there.md)\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "check_documentation.py"
    result = subprocess.run(
        [sys.executable, str(script), str(tmp_path)], text=True, capture_output=True, check=False
    )
    assert result.returncode == 1
    assert "broken-link" in result.stdout
