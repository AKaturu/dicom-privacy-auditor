from __future__ import annotations

import json
import sqlite3

import pytest

from dicom_privacy_auditor.campaign.disagreements import (
    adjudicate_parity_disagreements,
    analyze_parity_disagreements,
)
from dicom_privacy_auditor.campaign.evidence import (
    archive_evidence_package,
    build_evidence_package,
    compare_evaluators,
    compare_evaluators_streaming,
    generate_review_sample,
    verify_evidence_package,
)
from dicom_privacy_auditor.campaign.official_midi import normalize_official_midi_results


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


def test_streaming_parity_compares_csv_inputs_and_truncates_discrepancies(tmp_path):
    left = tmp_path / "internal.csv"
    left.write_text(
        "action_id,action,status\n"
        "a,uid changed,pass\n"
        "b,text removed,fail\n"
        "c,tag retained,unresolved\n",
        encoding="utf-8",
    )
    right = tmp_path / "official.csv"
    right.write_text(
        "action_id,action,status\n"
        "a,uid changed,True\n"
        "b,text removed,pass\n"
        "d,tag retained,False\n",
        encoding="utf-8",
    )

    result = compare_evaluators_streaming(left, right, tmp_path / "parity.json", discrepancy_limit=2)

    assert result["internal_row_count"] == 3
    assert result["official_row_count"] == 3
    assert result["union_action_count"] == 4
    assert result["exact_status_matches"] == 1
    assert result["discrepancy_count"] == 3
    assert result["discrepancies_truncated"] is True
    assert result["confusion"]["pass|pass"] == 1
    assert result["confusion"]["fail|pass"] == 1
    assert result["confusion"]["unresolved|missing"] == 1
    assert result["confusion"]["missing|fail"] == 1


def test_streaming_parity_rejects_duplicate_action_ids(tmp_path):
    left = tmp_path / "internal.csv"
    left.write_text("action_id,status\na,pass\na,fail\n", encoding="utf-8")
    right = tmp_path / "official.csv"
    right.write_text("action_id,status\na,pass\n", encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate internal action_id"):
        compare_evaluators_streaming(left, right, tmp_path / "parity.json")


def test_normalize_official_midi_reconstructs_action_ids(tmp_path):
    answer_db = tmp_path / "answer.db"
    with sqlite3.connect(answer_db) as connection:
        connection.execute("CREATE TABLE answer_data (SOPInstanceUID TEXT, AnswerData TEXT)")
        connection.execute(
            "INSERT INTO answer_data (SOPInstanceUID, AnswerData) VALUES (?, ?)",
            (
                "1.2.840.old",
                json.dumps(
                    {
                        "0": {
                            "tag": "<(0008,0005)>",
                            "tag_ds": "<(0008,0005)>",
                            "tag_name": "<Specific Character Set>",
                            "value": "<ISO_IR 100>",
                            "action": "<text_retained>",
                        }
                    }
                ),
            ),
        )

    official_db = tmp_path / "official.db"
    with sqlite3.connect(official_db) as connection:
        connection.execute(
            """
            CREATE TABLE validation_results (
                check_index INTEGER,
                check_passed INTEGER,
                action TEXT,
                answer_value TEXT,
                instance TEXT,
                tag TEXT,
                tag_name TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO validation_results
            (check_index, check_passed, action, answer_value, instance, tag, tag_name)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (0, 1, "<text_retained>", "<MUTATED>", "1.2.840.new", "<(0008,0005)>", "Specific Character Set"),
        )

    mapping = tmp_path / "uid_mapping.csv"
    mapping.write_text("id_old,id_new\n1.2.840.old,1.2.840.new\n", encoding="utf-8")

    output = tmp_path / "official-normalized.csv"
    result = normalize_official_midi_results(official_db, answer_db, mapping, output)

    rows = output.read_text(encoding="utf-8").splitlines()
    assert result["normalized_rows"] == 1
    assert result["unmatched_rows"] == 0
    assert rows[0] == "action_id,action,status"
    assert rows[1] == "9020ba1829209a3c5f6cea14,text retained,pass"


def test_analyze_parity_disagreements_summarizes_safe_clusters(tmp_path):
    internal = tmp_path / "internal.csv"
    internal.write_text(
        "action_id,action,category,status,reason,source_present,candidate_present\n"
        "a,text retained,dicom_standard,pass,retained,True,True\n"
        "b,text retained,patient_name,fail,missing token,True,True\n"
        "c,tag retained,dicom_standard,pass,tag retained,True,True\n"
        "d,pixels retained,,unresolved,Source object could not be resolved,False,True\n",
        encoding="utf-8",
    )
    official = tmp_path / "official.csv"
    official.write_text(
        "action_id,action,status\n"
        "a,text retained,pass\n"
        "b,text retained,pass\n"
        "c,tag retained,fail\n"
        "d,pixels retained,pass\n"
        "e,text removed,pass\n",
        encoding="utf-8",
    )
    actions = tmp_path / "actions.jsonl"
    actions.write_text(
        json.dumps({"action_id": "b", "tag_name": "Patient Name"}) + "\n"
        + json.dumps({"action_id": "c", "tag_name": "Image Type"}) + "\n"
        + json.dumps({"action_id": "d", "tag_name": "Pixel Data"}) + "\n",
        encoding="utf-8",
    )

    result = analyze_parity_disagreements(
        internal,
        official,
        tmp_path / "review.json",
        report_markdown=tmp_path / "review.md",
        actions_jsonl=actions,
        top_n=10,
        sample_limit=2,
    )

    assert result["internal_row_count"] == 4
    assert result["official_row_count"] == 5
    assert result["exact_status_matches"] == 1
    assert result["disagreement_count"] == 4
    assert result["confusion"]["fail|pass"] == 1
    assert result["confusion"]["missing|pass"] == 1
    assert result["top_action_status_disagreements"][0]["count"] == 1
    assert {row["tag_name"] for row in result["tag_enrichment"]["top_tag_names"]} >= {
        "Patient Name",
        "Image Type",
        "Pixel Data",
    }
    assert len(result["sample_disagreements"]) == 2
    assert (tmp_path / "review.md").read_text(encoding="utf-8").startswith(
        "# MIDI-B Parity Disagreement Review"
    )


def test_adjudicate_parity_disagreements_classifies_safe_clusters(tmp_path):
    source = tmp_path / "disagreement.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "disagreement_count": 12,
                "confusion": {
                    "fail|fail": 4,
                    "fail|pass": 7,
                    "pass|fail": 2,
                    "pass|pass": 8,
                    "unresolved|pass": 1,
                },
                "top_action_status_disagreements": [
                    {
                        "action": "date shifted",
                        "internal_status": "fail",
                        "official_status": "pass",
                        "count": 4,
                    },
                    {
                        "action": "text retained",
                        "internal_status": "fail",
                        "official_status": "pass",
                        "count": 3,
                    },
                    {
                        "action": "tag retained",
                        "internal_status": "pass",
                        "official_status": "fail",
                        "count": 2,
                    },
                    {
                        "action": "pixels retained",
                        "internal_status": "unresolved",
                        "official_status": "pass",
                        "count": 2,
                    },
                    {
                        "action": "unknown",
                        "internal_status": "pass",
                        "official_status": "fail",
                        "count": 1,
                    },
                ],
                "top_category_status_disagreements": [
                    {
                        "category": "uid",
                        "internal_status": "fail",
                        "official_status": "pass",
                        "count": 4,
                    },
                    {
                        "category": "dicom_standard",
                        "internal_status": "pass",
                        "official_status": "fail",
                        "count": 2,
                    },
                    {
                        "category": "patient_name",
                        "internal_status": "fail",
                        "official_status": "pass",
                        "count": 3,
                    },
                    {
                        "category": "<blank>",
                        "internal_status": "fail",
                        "official_status": "pass",
                        "count": 3,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = adjudicate_parity_disagreements(
        source,
        tmp_path / "adjudication.json",
        report_markdown=tmp_path / "ADJUDICATION.md",
    )

    assert result["summary"]["action_cluster_rows"] == 12
    assert result["summary"]["action_cluster_coverage"] == 1
    assert result["confusion_summary"]["official_pass"] == 16
    assert result["confusion_summary"]["official_score"] == 16 / 22
    dispositions = {row["disposition"] for row in result["action_adjudications"]}
    assert "internal_strict_false_negative_relative_to_official" in dispositions
    assert "presence_or_null_representation_mismatch" in dispositions
    assert "manual_review_required" in dispositions
    assert result["category_adjudications"][0]["family"] == "uid_presence_mapping_policy"
    assert (tmp_path / "ADJUDICATION.md").read_text(encoding="utf-8").startswith(
        "# MIDI-B Disagreement Category Adjudication"
    )


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
    import os
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
    if os.name != "nt":
        assert stat.S_IMODE(sample.stat().st_mode) == 0o600
        assert stat.S_IMODE(parity.stat().st_mode) == 0o600

    workspace = tmp_path / "workspace"
    (workspace / "runs").mkdir(parents=True)
    (workspace / "runs" / "run.json").write_text("{}", encoding="utf-8")
    evidence = tmp_path / "evidence"
    build_evidence_package(workspace, evidence, campaign_id="x")
    if os.name != "nt":
        assert stat.S_IMODE(evidence.stat().st_mode) == 0o700
        assert all(
            stat.S_IMODE(path.stat().st_mode) == 0o600 for path in evidence.rglob("*") if path.is_file()
        )
    with pytest.raises(ValueError, match="outside the evidence directory"):
        archive_evidence_package(evidence, evidence / "self.tar.gz")
