from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from dicom_privacy_auditor.adapter_cli import main as adapter_main
from dicom_privacy_auditor.demo import main as demo_main
from dicom_privacy_auditor.midi_cli import main as midi_main
from dicom_privacy_auditor.ps315.cli import main as ps315_main
from dicom_privacy_auditor.publication.cli import main as report_main


def _write(path: Path, patient_name: str = "PHI") -> FileDataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientName = patient_name
    ds.PatientID = "P1"
    ds.Modality = "OT"
    ds.save_as(path, enforce_file_format=True)
    return ds


def test_ps315_cli_info_rules_codes_and_evaluate(tmp_path: Path) -> None:
    assert ps315_main(["info", "--json"]) == 0
    assert ps315_main(["rules", "--tag", "00100010"]) == 0
    assert ps315_main(["codes", "--code", "121022"]) == 0
    source = tmp_path / "source.dcm"
    candidate = tmp_path / "candidate.dcm"
    source_ds = _write(source, "DOE^JANE")
    candidate_ds = source_ds.copy()
    candidate_ds.PatientName = ""
    candidate_ds.PatientID = ""
    candidate_ds.SOPInstanceUID = generate_uid()
    candidate_ds.file_meta.MediaStorageSOPInstanceUID = candidate_ds.SOPInstanceUID
    candidate_ds.StudyInstanceUID = generate_uid()
    candidate_ds.save_as(candidate, enforce_file_format=True)
    output = tmp_path / "ps315.json"
    assert ps315_main(["evaluate", str(source), str(candidate), "--json", str(output)]) in {0, 1}
    assert output.is_file()


def test_midi_cli_inspect_import_and_evaluate(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    candidate_root = tmp_path / "candidate"
    source_root.mkdir()
    candidate_root.mkdir()
    source = _write(source_root / "case.dcm", "SECRET")
    candidate = source.copy()
    candidate.PatientName = ""
    candidate.save_as(candidate_root / "case.dcm", enforce_file_format=True)
    answer = tmp_path / "answers.sqlite"
    connection = sqlite3.connect(answer)
    connection.execute(
        "CREATE TABLE answers(action TEXT, sop_instance_uid TEXT, tag TEXT, value TEXT, relative_path TEXT)"
    )
    connection.execute(
        "INSERT INTO answers VALUES (?,?,?,?,?)",
        ("text removed", str(source.SOPInstanceUID), "00100010", "SECRET", "case.dcm"),
    )
    connection.commit()
    connection.close()
    assert midi_main(["inspect", str(answer)]) == 0
    imported = tmp_path / "imported"
    assert midi_main(["import", str(answer), str(source_root), str(imported)]) == 0
    assert midi_main(["evaluate", str(imported), str(candidate_root), str(tmp_path / "eval")]) == 0


def test_directory_adapter_probe_cli(tmp_path: Path) -> None:
    config = tmp_path / "directory.json"
    config.write_text(json.dumps({"input_dir": str(tmp_path / "in"), "output_dir": str(tmp_path / "out")}))
    assert adapter_main(["probe", "directory", str(config)]) == 0


def test_demo_and_report_cli_dispatch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("dicom_privacy_auditor.demo.run_demo", lambda *a, **k: {"ok": True})
    assert demo_main([str(tmp_path / "demo"), "--overwrite", "--no-plots"]) == 0
    monkeypatch.setattr(
        "dicom_privacy_auditor.publication.cli.generate_publication_package", lambda *a, **k: {"ok": True}
    )
    assert report_main(["generate", str(tmp_path), str(tmp_path / "report")]) == 0
