from __future__ import annotations

from pathlib import Path

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from dicom_privacy_auditor.study import index_studies, process_directory


def _write(path, study):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = study
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientID = "PHI"
    ds.save_as(path, enforce_file_format=True)


def test_atomic_study_processing_and_resume(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    study = generate_uid()
    _write(source / "a.dcm", study)
    _write(source / "b.dcm", study)
    assert len(index_studies(source)[study]) == 2
    runs = process_directory(source, tmp_path / "out", pipeline="baseline")
    assert runs[0].status == "complete" and runs[0].processed_instances == 2
    resumed = process_directory(source, tmp_path / "out", pipeline="baseline")
    assert resumed[0].status == "complete"


def test_study_processing_rejects_overlap_and_symlink_sources(tmp_path):
    import os

    import pytest

    source = tmp_path / "source"
    source.mkdir()
    study = generate_uid()
    original = source / "a.dcm"
    _write(original, study)
    with pytest.raises(ValueError, match="must not overlap"):
        process_directory(source, source / "output", pipeline="noop")

    if not hasattr(os, "symlink"):
        return
    linked_root = tmp_path / "linked"
    linked_root.mkdir()
    try:
        (linked_root / "linked.dcm").symlink_to(original)
    except OSError:
        return
    with pytest.raises(ValueError, match="symbolic links"):
        index_studies(linked_root)


def test_study_resume_record_is_schema_validated(tmp_path):
    import json

    import pytest

    source = tmp_path / "source"
    source.mkdir()
    study = generate_uid()
    _write(source / "a.dcm", study)
    output = tmp_path / "output"
    runs = process_directory(source, output, pipeline="noop")
    checkpoint = Path(runs[0].output_directory) / "run.json"
    payload = json.loads(checkpoint.read_text(encoding="utf-8"))
    payload["source_instances"] = 0
    checkpoint.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="study-run validation failed"):
        process_directory(source, output, pipeline="noop")
