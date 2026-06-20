from __future__ import annotations

import sqlite3
from pathlib import Path

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from dicom_privacy_auditor.benchmark.midi import import_midi
from dicom_privacy_auditor.campaign import finalize_tool, preflight_campaign, run_tool


def _write(path):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientID = "P1"
    ds.PatientName = "DOE^JANE"
    ds.save_as(path, enforce_file_format=True)
    return ds


def test_midi_campaign_noop_fixture(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    ds = _write(images / "one.dcm")
    db = tmp_path / "answers.sqlite"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE answers(action TEXT, sop_instance_uid TEXT, tag TEXT, value TEXT, relative_path TEXT)"
    )
    connection.execute(
        "INSERT INTO answers VALUES (?,?,?,?,?)",
        ("text removed", str(ds.SOPInstanceUID), "00100010", "DOE^JANE", "one.dcm"),
    )
    connection.commit()
    connection.close()
    imported = tmp_path / "imported"
    import_midi(db, images, imported)
    result = run_tool(imported, tmp_path / "campaign", tool="noop")
    assert result.status == "complete"
    assert result.evaluation_summary["failed"] == 1


def test_campaign_source_root_override_after_migration(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    ds = _write(images / "one.dcm")
    db = tmp_path / "answers.sqlite"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE answers(action TEXT, sop_instance_uid TEXT, tag TEXT, value TEXT, relative_path TEXT)"
    )
    connection.execute(
        "INSERT INTO answers VALUES (?,?,?,?,?)",
        ("text removed", str(ds.SOPInstanceUID), "00100010", "DOE^JANE", "one.dcm"),
    )
    connection.commit()
    connection.close()
    imported = tmp_path / "imported"
    import_midi(db, images, imported)
    moved = tmp_path / "moved-images"
    images.rename(moved)

    blocked = preflight_campaign(imported)
    assert blocked["status"] == "blocked"
    ready = preflight_campaign(imported, source_root=moved)
    assert ready["status"] == "ready"
    assert ready["source_root_overridden"] is True

    result = run_tool(imported, tmp_path / "campaign", tool="noop", source_root=moved)
    assert result.status == "complete"
    assert result.selected_instances == 1
    assert result.checkpoint_file is not None
    assert result.evaluation_summary is not None
    assert result.evaluation_summary["unresolved"] == 0


def test_campaign_shards_resume_then_finalize(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    datasets = [_write(images / f"{index}.dcm") for index in range(4)]
    db = tmp_path / "answers.sqlite"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE answers(action TEXT, sop_instance_uid TEXT, tag TEXT, value TEXT, relative_path TEXT)"
    )
    for index, ds in enumerate(datasets):
        connection.execute(
            "INSERT INTO answers VALUES (?,?,?,?,?)",
            ("text removed", str(ds.SOPInstanceUID), "00100010", "DOE^JANE", f"{index}.dcm"),
        )
    connection.commit()
    connection.close()
    imported = tmp_path / "imported"
    import_midi(db, images, imported)
    workspace = tmp_path / "campaign"

    first = run_tool(imported, workspace, tool="noop", shard_index=0, shard_count=2, evaluate=False)
    assert first.status == "partial"
    second = run_tool(imported, workspace, tool="noop", shard_index=1, shard_count=2)
    assert second.status == "complete"
    assert second.evaluation_summary is not None

    final = finalize_tool(imported, workspace, tool="noop")
    assert final.status == "complete"
    assert final.processed_instances == 4


def test_official_validator_timeout_is_structured(tmp_path, monkeypatch):
    import subprocess

    from dicom_privacy_auditor.campaign import midi_live

    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(
            ["validator"],
            timeout=0.5,
            output=b"partial stdout",
            stderr=b"partial stderr",
        )

    monkeypatch.setattr(subprocess, "run", timeout)
    result = midi_live._official_validate(
        ["validator", "{candidate}"],
        imported=tmp_path / "imported",
        candidate=tmp_path / "candidate",
        output=tmp_path / "output",
        timeout_seconds=0.5,
    )

    assert result["timed_out"] is True
    assert result["returncode"] is None
    assert result["timeout_seconds"] == 0.5
    assert result["stdout_tail"] == "partial stdout"
    assert result["stderr_tail"] == "partial stderr"


def test_official_validator_timeout_must_be_positive(tmp_path):
    import pytest

    from dicom_privacy_auditor.campaign import midi_live

    with pytest.raises(ValueError, match="greater than zero"):
        midi_live._official_validate(
            ["validator"],
            imported=tmp_path,
            candidate=tmp_path,
            output=tmp_path,
            timeout_seconds=0,
        )


def test_campaign_rejects_invalid_tool_and_overlapping_workspace(tmp_path):
    import pytest

    images = tmp_path / "images"
    images.mkdir()
    ds = _write(images / "one.dcm")
    db = tmp_path / "answers.sqlite"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE answers(action TEXT, sop_instance_uid TEXT, tag TEXT, value TEXT, relative_path TEXT)"
    )
    connection.execute(
        "INSERT INTO answers VALUES (?,?,?,?,?)",
        ("text removed", str(ds.SOPInstanceUID), "00100010", "DOE^JANE", "one.dcm"),
    )
    connection.commit()
    connection.close()
    imported = tmp_path / "imported"
    import_midi(db, images, imported)

    with pytest.raises(ValueError, match="Unsupported campaign tool"):
        run_tool(imported, tmp_path / "workspace", tool="../../escape")
    with pytest.raises(ValueError, match="must not overlap"):
        run_tool(imported, images, tool="noop")


def test_campaign_checkpoint_is_private(tmp_path):
    import os
    import stat

    images = tmp_path / "images"
    images.mkdir()
    ds = _write(images / "one.dcm")
    db = tmp_path / "answers.sqlite"
    connection = sqlite3.connect(db)
    connection.execute(
        "CREATE TABLE answers(action TEXT, sop_instance_uid TEXT, tag TEXT, value TEXT, relative_path TEXT)"
    )
    connection.execute(
        "INSERT INTO answers VALUES (?,?,?,?,?)",
        ("text removed", str(ds.SOPInstanceUID), "00100010", "DOE^JANE", "one.dcm"),
    )
    connection.commit()
    connection.close()
    imported = tmp_path / "imported"
    import_midi(db, images, imported)
    result = run_tool(imported, tmp_path / "workspace", tool="noop")
    assert result.checkpoint_file is not None
    if os.name != "nt":
        assert stat.S_IMODE(Path(result.checkpoint_file).stat().st_mode) == 0o600
