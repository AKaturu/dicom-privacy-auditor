from __future__ import annotations

import csv
import json
import sqlite3
from contextlib import closing
from copy import deepcopy

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from dicom_privacy_auditor.benchmark.midi import evaluate_midi, import_midi, inspect_answer_key, read_actions


def _write(path, *, patient_id, sop_uid, study_uid, study_date, description, pixels):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = sop_uid
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = sop_uid
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientID = patient_id
    ds.StudyDate = study_date
    ds.StudyDescription = description
    ds.Modality = "OT"
    ds.Rows, ds.Columns = pixels.shape
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.PixelData = pixels.astype(np.uint8).tobytes()
    ds.save_as(path, enforce_file_format=True)


def _mapping(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source", "target"])
        writer.writerows(rows)


def test_midi_sqlite_import_and_action_evaluation(tmp_path):
    source_root = tmp_path / "source"
    candidate_root = tmp_path / "candidate"
    source_root.mkdir()
    candidate_root.mkdir()
    old_sop, new_sop = generate_uid(), generate_uid()
    retained_old_sop, retained_new_sop = generate_uid(), generate_uid()
    old_study, new_study = generate_uid(), generate_uid()
    pixels = np.arange(64, dtype=np.uint8).reshape(8, 8)
    source_path = source_root / "case.dcm"
    candidate_path = candidate_root / "case.dcm"
    _write(
        source_path,
        patient_id="OLDPAT",
        sop_uid=old_sop,
        study_uid=old_study,
        study_date="20200101",
        description="SECRET SAFE",
        pixels=pixels,
    )
    changed_pixels = deepcopy(pixels)
    changed_pixels[0:2, 0:2] = 0
    _write(
        candidate_path,
        patient_id="NEWPAT",
        sop_uid=new_sop,
        study_uid=new_study,
        study_date="20210101",
        description="SAFE",
        pixels=changed_pixels,
    )
    retained_source = source_root / "retained.dcm"
    retained_candidate = candidate_root / "retained.dcm"
    _write(
        retained_source,
        patient_id="OLDPAT2",
        sop_uid=retained_old_sop,
        study_uid=generate_uid(),
        study_date="20200102",
        description="SAFE",
        pixels=pixels,
    )
    _write(
        retained_candidate,
        patient_id="NEWPAT2",
        sop_uid=retained_new_sop,
        study_uid=generate_uid(),
        study_date="20210102",
        description="SAFE",
        pixels=pixels,
    )

    db = tmp_path / "answer_key.sqlite"
    with closing(sqlite3.connect(db)) as connection:
        connection.execute(
            """CREATE TABLE answer_key (
                action TEXT, category TEXT, sop_instance_uid TEXT, patient_id TEXT,
                tag TEXT, tag_name TEXT, value TEXT, relative_path TEXT,
                x1 INTEGER, y1 INTEGER, x2 INTEGER, y2 INTEGER
            )"""
        )
        rows = [
            (
                "date shifted",
                "HIPAA",
                old_sop,
                "OLDPAT",
                "00080020",
                "StudyDate",
                None,
                "case.dcm",
                None,
                None,
                None,
                None,
            ),
            (
                "patid consistent",
                "TCIA",
                old_sop,
                "OLDPAT",
                "00100020",
                "PatientID",
                None,
                "case.dcm",
                None,
                None,
                None,
                None,
            ),
            (
                "tag retained",
                "DICOM",
                old_sop,
                "OLDPAT",
                "00081030",
                "StudyDescription",
                None,
                "case.dcm",
                None,
                None,
                None,
                None,
            ),
            (
                "text notnull",
                "DICOM",
                old_sop,
                "OLDPAT",
                "00081030",
                "StudyDescription",
                None,
                "case.dcm",
                None,
                None,
                None,
                None,
            ),
            (
                "text removed",
                "HIPAA",
                old_sop,
                "OLDPAT",
                "00081030",
                "StudyDescription",
                "SECRET",
                "case.dcm",
                None,
                None,
                None,
                None,
            ),
            (
                "text retained",
                "TCIA",
                old_sop,
                "OLDPAT",
                "00081030",
                "StudyDescription",
                "SAFE",
                "case.dcm",
                None,
                None,
                None,
                None,
            ),
            (
                "uid changed",
                "DICOM",
                old_sop,
                "OLDPAT",
                "0020000D",
                "StudyInstanceUID",
                None,
                "case.dcm",
                None,
                None,
                None,
                None,
            ),
            (
                "uid consistent",
                "DICOM",
                old_sop,
                "OLDPAT",
                "0020000D",
                "StudyInstanceUID",
                old_study,
                "case.dcm",
                None,
                None,
                None,
                None,
            ),
            ("pixels hidden", "HIPAA", old_sop, "OLDPAT", None, None, None, "case.dcm", 0, 0, 2, 2),
            (
                "pixels retained",
                "DICOM",
                retained_old_sop,
                "OLDPAT2",
                None,
                None,
                None,
                "retained.dcm",
                None,
                None,
                None,
                None,
            ),
        ]
        connection.executemany("INSERT INTO answer_key VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        connection.commit()
    patient_map = tmp_path / "patient.csv"
    uid_map = tmp_path / "uid.csv"
    _mapping(patient_map, [("OLDPAT", "NEWPAT"), ("OLDPAT2", "NEWPAT2")])
    _mapping(uid_map, [(old_sop, new_sop), (old_study, new_study), (retained_old_sop, retained_new_sop)])

    schema = inspect_answer_key(db)
    assert schema[0]["recognized_action_value_count"] == 10
    imported = tmp_path / "imported"
    manifest = import_midi(db, source_root, imported, patient_mapping=patient_map, uid_mapping=uid_map)
    assert manifest.action_count == 10
    assert manifest.unresolved_source_paths == 0
    evaluation = evaluate_midi(imported, candidate_root, tmp_path / "evaluation")
    assert evaluation.summary["passed"] == 10
    assert evaluation.summary["failed"] == 0
    assert evaluation.summary["score"] == 1.0
    assert (tmp_path / "evaluation" / "MIDI_REPORT.md").exists()


def test_mapping_reader_accepts_descriptive_public_headers(tmp_path):
    from dicom_privacy_auditor.benchmark.midi import _read_mapping

    path = tmp_path / "mapping.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["OriginalPatientID", "AnonymizedPatientID"])
        writer.writerow(["P001", "MIDI001"])
    assert _read_mapping(path) == {"P001": "MIDI001"}


def test_midi_import_accepts_official_answer_data_payload(tmp_path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    sop_uid = generate_uid()
    patient_id = "8371727310"
    _write(
        source_root / "case.dcm",
        patient_id=patient_id,
        sop_uid=sop_uid,
        study_uid=generate_uid(),
        study_date="20200101",
        description="SECRET SAFE",
        pixels=np.zeros((8, 8), dtype=np.uint8),
    )
    db = tmp_path / "official.sqlite"
    payload = {
        "0": {
            "scope": "<Instance>",
            "tag": "<(0008,0012)>",
            "tag_ds": "<(0008,0012)>",
            "tag_name": "<Instance Creation Date>",
            "value": "<20151225>",
            "action": "<date_shifted>",
            "action_text": "<20151225>",
            "answer_category": ["date"],
        },
        "1": {
            "scope": "<Instance>",
            "tag": None,
            "tag_ds": None,
            "tag_name": None,
            "value": None,
            "action": "<pixels_hidden>",
            "action_text": '<{"text":"JT","top_left":[2,3],"bottom_right":[5,7]}>',
            "answer_category": [],
        },
    }
    with closing(sqlite3.connect(db)) as connection:
        connection.execute(
            """CREATE TABLE answer_data (
                PatientID TEXT,
                SOPInstanceUID TEXT,
                AnswerData TEXT
            )"""
        )
        connection.execute(
            "INSERT INTO answer_data VALUES (?, ?, ?)",
            (patient_id, sop_uid, json.dumps(payload)),
        )
        connection.commit()

    schema = inspect_answer_key(db)
    assert schema[0]["payload_column"] == "AnswerData"
    assert schema[0]["recognized_action_values"] == ["date shifted", "pixels hidden"]
    imported = tmp_path / "imported"
    manifest = import_midi(db, source_root, imported)
    assert manifest.action_count == 2
    assert manifest.unresolved_source_paths == 0
    actions = read_actions(imported / "actions.jsonl")
    assert actions[0].tag == "00080012"
    assert actions[0].tag_name == "Instance Creation Date"
    assert actions[0].value == "20151225"
    assert actions[0].source_relative_path == "case.dcm"
    assert actions[1].bbox_xyxy == (2, 3, 5, 7)


def test_midi_import_uses_private_permissions_and_rejects_overlap(tmp_path):
    import os
    import stat

    import pytest

    source = tmp_path / "source"
    source.mkdir()
    _write(
        source / "case.dcm",
        patient_id="P1",
        sop_uid=generate_uid(),
        study_uid=generate_uid(),
        study_date="20200101",
        description="SECRET",
        pixels=np.zeros((2, 2), dtype=np.uint8),
    )
    db = tmp_path / "answer.sqlite"
    with closing(sqlite3.connect(db)) as connection:
        connection.execute("CREATE TABLE answers(action TEXT, relative_path TEXT)")
        connection.execute("INSERT INTO answers VALUES (?, ?)", ("text removed", "case.dcm"))
        connection.commit()

    with pytest.raises(ValueError, match="must not overlap"):
        import_midi(db, source, source / "imported")

    imported = tmp_path / "imported"
    import_midi(db, source, imported)
    if os.name != "nt":
        assert stat.S_IMODE(imported.stat().st_mode) == 0o700
        assert stat.S_IMODE((imported / "actions.jsonl").stat().st_mode) == 0o600
        assert stat.S_IMODE((imported / "midi_manifest.json").stat().st_mode) == 0o600


def test_midi_evaluation_rejects_manifest_traversal_and_output_overlap(tmp_path):
    import json

    import pytest

    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    sop_uid = generate_uid()
    pixels = np.zeros((2, 2), dtype=np.uint8)
    _write(
        source / "case.dcm",
        patient_id="P1",
        sop_uid=sop_uid,
        study_uid=generate_uid(),
        study_date="20200101",
        description="SECRET",
        pixels=pixels,
    )
    _write(
        candidate / "case.dcm",
        patient_id="P2",
        sop_uid=sop_uid,
        study_uid=generate_uid(),
        study_date="20210101",
        description="SAFE",
        pixels=pixels,
    )
    db = tmp_path / "answer.sqlite"
    with closing(sqlite3.connect(db)) as connection:
        connection.execute(
            "CREATE TABLE answers(action TEXT, sop_instance_uid TEXT, relative_path TEXT, value TEXT)"
        )
        connection.execute(
            "INSERT INTO answers VALUES (?, ?, ?, ?)",
            ("text removed", sop_uid, "case.dcm", "SECRET"),
        )
        connection.commit()
    imported = tmp_path / "imported"
    import_midi(db, source, imported)

    with pytest.raises(ValueError, match="must not overlap"):
        evaluate_midi(imported, candidate, candidate / "evaluation")

    manifest_path = imported / "midi_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["actions_file"] = "../outside.jsonl"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsafe benchmark relative path"):
        evaluate_midi(imported, candidate, tmp_path / "evaluation")
