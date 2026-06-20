from __future__ import annotations

import sys

from dicom_privacy_auditor import __version__
from dicom_privacy_auditor.desktop import build_parser
from dicom_privacy_auditor.launcher import main


def test_unified_launcher_version(capsys) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_unified_launcher_help(capsys) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "audit" in output
    assert "benchmark" in output
    assert __version__ in output


def test_unified_launcher_rejects_unknown_command(capsys) -> None:
    assert main(["not-a-command"]) == 2
    assert "Unknown command" in capsys.readouterr().err


def test_desktop_parser_accepts_preselected_path(tmp_path) -> None:
    args = build_parser().parse_args([str(tmp_path)])
    assert args.path == tmp_path


def test_frozen_cli_directs_user_to_desktop_executable(monkeypatch, capsys) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "/tmp/DICOMPrivacyAuditor-CLI")
    assert main(["desktop"]) == 2
    assert "desktop executable" in capsys.readouterr().err
