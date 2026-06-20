from __future__ import annotations

from scripts.run_local_release_gate import _redact


def test_release_gate_redacts_project_and_temporary_paths(tmp_path):
    root = tmp_path / "project"
    temporary = tmp_path / "scratch"
    value = f"failed at {root}/src and {temporary}/dist"
    redacted = _redact(value, root, temporary)
    assert str(root) not in redacted
    assert str(temporary) not in redacted
    assert "<PROJECT_ROOT>/src" in redacted
    assert "<TEMP_DIR>/dist" in redacted


def test_release_gate_redacts_unrecognized_absolute_paths(tmp_path):
    root = tmp_path / "project"
    temporary = tmp_path / "scratch"
    value = "tool used /opt/private/bin and C:\\Users\\name\\tool.exe and \\\\server\\share\\secret"
    redacted = _redact(value, root, temporary)
    assert "/opt/private/bin" not in redacted
    assert "C:\\Users" not in redacted
    assert "server\\share" not in redacted
    assert redacted.count("<ABSOLUTE_PATH>") == 3


def test_release_gate_does_not_redact_urls_or_markers(tmp_path):
    root = tmp_path / "project"
    temporary = tmp_path / "scratch"
    value = "https://example.test/path <PROJECT_ROOT>/src"
    assert _redact(value, root, temporary) == value


def test_release_gate_output_is_owner_only(tmp_path):
    import json
    import os
    import stat

    from scripts.run_local_release_gate import _atomic_json

    output = tmp_path / "gate.json"
    _atomic_json(output, {"status": "passed"})
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "passed"
    if os.name != "nt":
        assert stat.S_IMODE(output.stat().st_mode) == 0o600
