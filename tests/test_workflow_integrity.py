from __future__ import annotations

from pathlib import Path

from scripts.check_workflow_integrity import check, validate_workflow


def test_repository_workflows_parse_and_have_required_structure():
    root = Path(__file__).resolve().parents[1]
    assert check(root) == []


def test_invalid_workflow_yaml_is_rejected(tmp_path):
    workflow = tmp_path / "broken.yml"
    workflow.write_text(
        "name: broken\non: push\njobs:\n  test:\n    run: pip --only-binary=:all: -r lock.txt\n"
    )
    errors = validate_workflow(workflow)
    assert errors and "invalid YAML" in errors[0]
