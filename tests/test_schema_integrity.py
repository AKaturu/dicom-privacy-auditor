from __future__ import annotations

import json
from pathlib import Path

from scripts.check_schema_integrity import check


def test_repository_schemas_and_examples_are_synchronized():
    root = Path(__file__).resolve().parents[1]
    assert check(root) == []


def test_schema_check_detects_public_package_drift(tmp_path):
    root = Path(__file__).resolve().parents[1]
    for name in ("schemas", "configs"):
        target = tmp_path / name
        target.symlink_to(root / name, target_is_directory=True)
    package = tmp_path / "src" / "dicom_privacy_auditor" / "schemas"
    package.mkdir(parents=True)
    for source in (root / "src" / "dicom_privacy_auditor" / "schemas").glob("*.schema.json"):
        package.joinpath(source.name).write_bytes(source.read_bytes())
    path = package / "review-export.schema.json"
    payload = json.loads(path.read_text())
    payload["title"] = "drifted"
    path.write_text(json.dumps(payload))
    assert any("schema drift" in item for item in check(tmp_path))
