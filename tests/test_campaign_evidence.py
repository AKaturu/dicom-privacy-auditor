from __future__ import annotations

import json

import pytest

from dicom_privacy_auditor.campaign.evidence import (
    archive_evidence_package,
    build_evidence_package,
    compare_evaluators,
    generate_review_sample,
    verify_evidence_package,
)


def _evaluation(path, rows):
    path.write_text(json.dumps({"results": rows}), encoding="utf-8")
    return path


def test_review_sample_is_deterministic_and_stratified(tmp_path):
    rows = [{"action_id": f"f{i}", "action": "text removed", "status": "fail"} for i in range(4)] + [
        {"action_id": f"p{i}", "action": "text removed", "status": "pass"} for i in range(3)
    ]
    source = _evaluation(tmp_path / "evaluation.json", rows)
    first = generate_review_sample(
        source, tmp_path / "a.json", failures_per_stratum=2, controls_per_stratum=1, seed=7
    )
    second = generate_review_sample(
        source, tmp_path / "b.json", failures_per_stratum=2, controls_per_stratum=1, seed=7
    )
    assert first["cases"] == second["cases"]
    assert first["selected_count"] == 3


def test_compare_evaluators_reports_discrepancies(tmp_path):
    left = _evaluation(
        tmp_path / "left.json", [{"action_id": "a", "action": "uid changed", "status": "pass"}]
    )
    right = _evaluation(
        tmp_path / "right.json", [{"action_id": "a", "action": "uid changed", "status": "fail"}]
    )
    result = compare_evaluators(left, right, tmp_path / "parity.json")
    assert result["discrepancy_count"] == 1
    assert result["exact_status_agreement"] == 0


def test_evidence_package_redacts_paths_and_checksums(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "runs").mkdir(parents=True)
    (workspace / "runs" / "tool.json").write_text(
        json.dumps(
            {
                "tool": "x",
                "source_root": "/sensitive",
                "output_directory": "/also-sensitive",
                "official_validation": {
                    "argv": ["python", "/private/validator.py"],
                    "stdout_tail": "possible patient content",
                    "stderr_tail": "possible patient content",
                },
                "source_ref": "patient-name/study.dcm",
                "candidate_ref": "patient-name/output.dcm",
            }
        ),
        encoding="utf-8",
    )
    result = build_evidence_package(workspace, tmp_path / "evidence", campaign_id="campaign-1")
    copied = json.loads((tmp_path / "evidence" / "runs" / "tool.json").read_text())
    assert copied["source_root"] == "redacted"
    assert copied["output_directory"] == "redacted"
    assert copied["official_validation"]["argv"] == "redacted"
    assert copied["official_validation"]["stdout_tail"] == "redacted"
    assert copied["official_validation"]["stderr_tail"] == "redacted"
    assert copied["source_ref"] == "redacted"
    assert copied["candidate_ref"] == "redacted"
    assert result["file_count"] >= 2
    assert (tmp_path / "evidence" / "SHA256SUMS.txt").is_file()


def test_evidence_verifier_detects_tampering_and_unexpected_files(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "runs").mkdir(parents=True)
    (workspace / "runs" / "tool.json").write_text(json.dumps({"value": 1}), encoding="utf-8")
    build_evidence_package(workspace, tmp_path / "evidence", campaign_id="campaign-1")
    assert verify_evidence_package(tmp_path / "evidence")["valid"] is True
    (tmp_path / "evidence" / "runs" / "tool.json").write_text(json.dumps({"value": 2}), encoding="utf-8")
    result = verify_evidence_package(tmp_path / "evidence")
    assert result["valid"] is False
    assert result["checksum_mismatches"] == ["runs/tool.json"]


def test_evidence_archive_is_reproducible_and_verifiable(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "reports").mkdir(parents=True)
    (workspace / "reports" / "report.json").write_text(
        json.dumps({"nested": {"other": "/private/path"}}), encoding="utf-8"
    )
    evidence = tmp_path / "evidence"
    build_evidence_package(workspace, evidence, campaign_id="campaign-1")
    first = archive_evidence_package(evidence, tmp_path / "first.tar.gz", source_date_epoch=123)
    second = archive_evidence_package(evidence, tmp_path / "second.tar.gz", source_date_epoch=123)
    assert first["sha256"] == second["sha256"]
    assert verify_evidence_package(tmp_path / "first.tar.gz")["valid"] is True
    copied = json.loads((evidence / "reports" / "report.json").read_text())
    assert copied["nested"]["other"] == "redacted"


def test_evidence_verifier_rejects_duplicate_manifest_paths(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "runs").mkdir(parents=True)
    (workspace / "runs" / "tool.json").write_text(json.dumps({"value": 1}), encoding="utf-8")
    evidence = tmp_path / "evidence"
    build_evidence_package(workspace, evidence, campaign_id="campaign-1")
    manifest = evidence / "SHA256SUMS.txt"
    first = manifest.read_text(encoding="utf-8").splitlines()[0]
    manifest.write_text(manifest.read_text(encoding="utf-8") + first + "\n", encoding="utf-8")

    result = verify_evidence_package(evidence)

    assert result["valid"] is False
    assert result["duplicate_manifest_paths"]


def test_evidence_verifier_enforces_archive_resource_limits(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "reports").mkdir(parents=True)
    (workspace / "reports" / "report.json").write_text(json.dumps({"value": "large"}), encoding="utf-8")
    evidence = tmp_path / "evidence"
    build_evidence_package(workspace, evidence, campaign_id="campaign-1")
    archive = tmp_path / "evidence.tar.gz"
    archive_evidence_package(evidence, archive)

    import pytest

    with pytest.raises(ValueError, match="member limit"):
        verify_evidence_package(archive, max_members=1)
    with pytest.raises(ValueError, match="uncompressed limit"):
        verify_evidence_package(archive, max_uncompressed_bytes=1)


def test_evidence_verifier_rejects_duplicate_and_link_archive_members(tmp_path):
    import io
    import tarfile

    import pytest

    duplicate = tmp_path / "duplicate.tar.gz"
    with tarfile.open(duplicate, "w:gz") as archive:
        for payload in (b"one", b"two"):
            info = tarfile.TarInfo("evidence/file.json")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(ValueError, match="duplicate archive member"):
        verify_evidence_package(duplicate)

    linked = tmp_path / "linked.tar.gz"
    with tarfile.open(linked, "w:gz") as archive:
        info = tarfile.TarInfo("evidence/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        archive.addfile(info)
    with pytest.raises(ValueError, match="unsupported archive member type"):
        verify_evidence_package(linked)


def test_evidence_build_rejects_overlap_and_symlink_sources(tmp_path):
    from dicom_privacy_auditor.campaign.evidence import build_evidence_package

    workspace = tmp_path / "workspace"
    (workspace / "runs").mkdir(parents=True)
    (workspace / "runs" / "run.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="must not overlap"):
        build_evidence_package(workspace, workspace / "evidence", campaign_id="x")

    outside = tmp_path / "outside.json"
    outside.write_text("{}", encoding="utf-8")
    linked = workspace / "runs" / "linked.json"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are unavailable")
    with pytest.raises(ValueError, match="must not be a symbolic link"):
        build_evidence_package(workspace, tmp_path / "evidence", campaign_id="x")


def test_evidence_outputs_are_private_and_archive_cannot_be_inside_source(tmp_path):
    import stat

    from dicom_privacy_auditor.campaign.evidence import (
        archive_evidence_package,
        build_evidence_package,
        compare_evaluators,
        generate_review_sample,
    )

    evaluation = tmp_path / "evaluation.json"
    evaluation.write_text(
        json.dumps({"results": [{"action_id": "a", "action": "remove", "status": "fail"}]}),
        encoding="utf-8",
    )
    sample = tmp_path / "sample.json"
    parity = tmp_path / "parity.json"
    generate_review_sample(evaluation, sample)
    compare_evaluators(evaluation, evaluation, parity)
    assert stat.S_IMODE(sample.stat().st_mode) == 0o600
    assert stat.S_IMODE(parity.stat().st_mode) == 0o600

    workspace = tmp_path / "workspace"
    (workspace / "runs").mkdir(parents=True)
    (workspace / "runs" / "run.json").write_text("{}", encoding="utf-8")
    evidence = tmp_path / "evidence"
    build_evidence_package(workspace, evidence, campaign_id="x")
    assert stat.S_IMODE(evidence.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in evidence.rglob("*") if path.is_file())
    with pytest.raises(ValueError, match="outside the evidence directory"):
        archive_evidence_package(evidence, evidence / "self.tar.gz")
