from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dicom_privacy_auditor.demo import run_demo
from dicom_privacy_auditor.dicomweb.client import DicomwebClient, DicomwebConfig, DicomwebError
from dicom_privacy_auditor.jsonio import ReportValidationError, load_schema, validate_json_file, write_json
from dicom_privacy_auditor.review.migrations import CURRENT_SCHEMA_VERSION, migrate_database
from dicom_privacy_auditor.review.store import ReviewStore
from scripts.build_executables import _check_native_dependencies
from scripts.check_action_pins import check


def test_all_actions_are_immutable_pins() -> None:
    assert check() == []


def test_schema_resources_and_atomic_validation(tmp_path: Path) -> None:
    assert load_schema("evaluation")["title"]
    destination = tmp_path / "bad.json"
    with pytest.raises(ReportValidationError):
        write_json(destination, {"pipeline": "x"}, schema_name="evaluation")
    assert not destination.exists()
    valid = {"pipeline": "x", "benchmark_name": "b", "summary": {}, "by_stratum": [], "cases": []}
    write_json(destination, valid, schema_name="evaluation")
    validate_json_file(destination, "evaluation")


def test_review_database_v1_migrates_with_backup(tmp_path: Path) -> None:
    database = tmp_path / "review.db"
    connection = sqlite3.connect(database)
    connection.executescript("""
    CREATE TABLE sessions (id INTEGER PRIMARY KEY, created_at TEXT, source_root TEXT, candidate_root TEXT, title TEXT, schema_version INTEGER);
    INSERT INTO sessions VALUES (1,'now','source','candidate','legacy',1);
    CREATE TABLE cases (case_id TEXT PRIMARY KEY, source_path TEXT, candidate_path TEXT, study_uid TEXT, series_uid TEXT, source_sop_uid TEXT, candidate_sop_uid TEXT, modality TEXT, frame_count INTEGER, status TEXT);
    CREATE TABLE decisions (decision_id INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT, reviewer TEXT, scope TEXT, target TEXT, status TEXT, comment TEXT, frame_number INTEGER, x1 INTEGER, y1 INTEGER, x2 INTEGER, y2 INTEGER, created_at TEXT);
    INSERT INTO cases VALUES ('case','s','c',NULL,NULL,NULL,NULL,'OT',1,'pending');
    """)
    connection.commit()
    connection.close()
    result = migrate_database(database)
    assert result["before"] == 1 and result["after"] == CURRENT_SCHEMA_VERSION
    assert Path(str(result["backup"])).is_file()
    store = ReviewStore(database)
    info = store.schema_info()
    assert info["up_to_date"] is True
    case = store.get_case("case")
    assert case.priority == 0 and case.assigned_reviewer is None and case.updated_at


def test_dicomweb_repeated_page_and_malformed_multipart(monkeypatch: pytest.MonkeyPatch) -> None:
    client = DicomwebClient(DicomwebConfig(base_url="https://example.test"))

    class Response:
        ok = True
        status_code = 200
        headers = {}
        content = b""

        def json(self):
            return [{"id": 1}]

    monkeypatch.setattr(client, "_request", lambda *_args, **_kwargs: Response())
    with pytest.raises(DicomwebError, match="repeated a page"):
        client.search_studies(page_size=1)
    with pytest.raises(DicomwebError, match="no decodable parts"):
        client._multipart_parts(b"not-a-multipart-body", "multipart/related; boundary=missing")
    client.close()


def test_complete_demo_and_publication_package(tmp_path: Path) -> None:
    result = run_demo(tmp_path / "demo", cases_per_stratum=1, clean_controls=1, overwrite=True, plots=False)
    root = tmp_path / "demo"
    assert result["summary"]["noop"]["residual_injections"] == 10
    assert result["summary"]["baseline"]["removed_injections"] == 10
    assert (root / "human-review.db").is_file()
    assert (root / "publication" / "MANUSCRIPT_REPORT.md").is_file()
    assert (root / "publication" / "tables" / "table_overall.tex").is_file()
    validate_json_file(root / "demo_manifest.json", "demo-manifest")
    validate_json_file(root / "publication" / "publication_manifest.json", "publication-manifest")


def test_native_build_dependency_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.build_executables.importlib.util.find_spec",
        lambda name: None if name == "docx" else object(),
    )
    with pytest.raises(RuntimeError, match="python-docx"):
        _check_native_dependencies()


def test_publication_package_redacts_paths_and_uses_private_permissions(tmp_path: Path) -> None:
    import json
    import stat

    from dicom_privacy_auditor.publication.generate import generate_publication_package

    workspace = tmp_path / "secret-workspace"
    evaluation = workspace / "evaluation-test"
    evaluation.mkdir(parents=True)
    payload = {
        "schema_version": "1.0",
        "pipeline": "test",
        "benchmark_name": "synthetic",
        "cases": [],
        "summary": {
            "cases": 1,
            "injections": 1,
            "removed_injections": 1,
            "residual_injections": 0,
            "removal_rate": 1.0,
            "removal_rate_ci95": [0.2, 1.0],
            "basic_valid_outputs": 1,
            "mean_runtime_seconds": 0.1,
        },
        "by_stratum": [],
    }
    (evaluation / "evaluation.json").write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "publication"
    manifest = generate_publication_package(workspace, output)
    appendix = (output / "REPRODUCIBILITY_APPENDIX.md").read_text(encoding="utf-8")
    assert str(workspace.resolve()) not in appendix
    assert manifest["paths_disclosed"] is False
    assert all(not Path(item["path"]).is_absolute() for item in manifest["inputs"])
    assert stat.S_IMODE(output.stat().st_mode) == 0o700
    for path in output.rglob("*"):
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600
        elif path.is_dir():
            assert stat.S_IMODE(path.stat().st_mode) == 0o700
