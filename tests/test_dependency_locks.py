from __future__ import annotations

from pathlib import Path

from scripts.check_dependency_locks import check
from scripts.compile_lock import normalize_uv_lock


def test_repository_dependency_roots_and_lock_are_synchronized():
    root = Path(__file__).resolve().parents[1]
    assert check(root) == []


def test_dependency_guard_detects_unhashed_entry(tmp_path):
    (tmp_path / "requirements" / "locks").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["requests>=2"]\n')
    (tmp_path / "requirements" / "lock-input.txt").write_text("requests>=2\n")
    (tmp_path / "requirements" / "locks" / "cp313-linux-x86_64-runtime.txt").write_text("requests==2.0\n")
    assert any("unhashed or malformed" in item for item in check(tmp_path))


def test_lock_normalizer_collapses_uv_continuations():
    payload = """
# generated
requests==2.34.2 \
    --hash=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
    --hash=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
"""
    assert normalize_uv_lock(payload) == [
        "requests==2.34.2 "
        "--hash=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa "
        "--hash=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
    ]


def test_lock_normalizer_rejects_unhashed_entries():
    import pytest

    with pytest.raises(ValueError, match="unhashed"):
        normalize_uv_lock("requests==2.34.2\n")


def test_dependency_guard_detects_validation_pin_drift(tmp_path):
    (tmp_path / "requirements" / "locks").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text('[project]\ndependencies=["requests>=2"]\n')
    (tmp_path / "requirements" / "lock-input.txt").write_text("requests>=2\n")
    digest = "a" * 64
    (tmp_path / "requirements" / "locks" / "cp313-linux-x86_64-runtime.txt").write_text(
        f"requests==2.0 --hash=sha256:{digest}\n"
    )
    (tmp_path / "requirements-reproducible.txt").write_text("requests==2.1\n")
    assert any("mismatch" in item for item in check(tmp_path))
