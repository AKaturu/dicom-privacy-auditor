from __future__ import annotations

from copy import deepcopy

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.sequence import Sequence
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from dicom_privacy_auditor.corpus import evaluate_corpus


def _write(path, ds):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = ds.SOPClassUID
    meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    file_ds.update(ds)
    file_ds.save_as(path, enforce_file_format=True)


def _dataset(patient, study, series, sop, date):
    ds = Dataset()
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = sop
    ds.StudyInstanceUID = study
    ds.SeriesInstanceUID = series
    ds.PatientID = patient
    ds.StudyDate = date
    return ds


def test_corpus_detects_collisions_and_inconsistent_dates(tmp_path):
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    study = generate_uid()
    series = generate_uid()
    s1 = _dataset("P1", study, series, generate_uid(), "20200101")
    s2 = _dataset("P1", study, series, generate_uid(), "20200110")
    c1 = deepcopy(s1)
    c2 = deepcopy(s2)
    c1.PatientID = "PX"
    c2.PatientID = "PX"
    c1.StudyDate = "20200106"
    c2.StudyDate = "20200120"  # shifts 5 and 10 days
    c1.SOPInstanceUID = generate_uid()
    c2.SOPInstanceUID = generate_uid()
    # Force a UID collision for two distinct source SOP UIDs.
    c2.SOPInstanceUID = c1.SOPInstanceUID
    _write(source / "a.dcm", s1)
    _write(source / "b.dcm", s2)
    _write(candidate / "a.dcm", c1)
    _write(candidate / "b.dcm", c2)
    report = evaluate_corpus(source, candidate)
    codes = {item.code for item in report.findings}
    assert "uid_collision" in codes
    assert "date_shift_inconsistent" in codes
    assert report.pairs == 2


def test_corpus_detects_reference_uid_that_breaks_identity_mapping(tmp_path):
    source = tmp_path / "source-ref"
    candidate = tmp_path / "candidate-ref"
    source.mkdir()
    candidate.mkdir()
    study = generate_uid()
    series = generate_uid()
    referenced_source_uid = generate_uid()
    reference_holder_uid = generate_uid()
    referenced = _dataset("P1", study, series, referenced_source_uid, "20200101")
    holder = _dataset("P1", study, series, reference_holder_uid, "20200101")
    item = Dataset()
    item.ReferencedSOPClassUID = SecondaryCaptureImageStorage
    item.ReferencedSOPInstanceUID = referenced_source_uid
    holder.ReferencedImageSequence = Sequence([item])

    candidate_referenced = deepcopy(referenced)
    mapped_uid = generate_uid()
    candidate_referenced.SOPInstanceUID = mapped_uid
    candidate_holder = deepcopy(holder)
    candidate_holder.SOPInstanceUID = generate_uid()
    candidate_holder.ReferencedImageSequence[0].ReferencedSOPInstanceUID = generate_uid()

    _write(source / "referenced.dcm", referenced)
    _write(source / "holder.dcm", holder)
    _write(candidate / "referenced.dcm", candidate_referenced)
    _write(candidate / "holder.dcm", candidate_holder)
    report = evaluate_corpus(source, candidate)
    codes = {item.code for item in report.findings}
    assert "reference_uid_inconsistent" in codes


def test_corpus_rejects_symbolic_link_files(tmp_path):
    import os

    import pytest

    if not hasattr(os, "symlink"):
        pytest.skip("symbolic links are unavailable")
    source = tmp_path / "source-link"
    candidate = tmp_path / "candidate-link"
    source.mkdir()
    candidate.mkdir()
    ds = _dataset("P1", generate_uid(), generate_uid(), generate_uid(), "20200101")
    outside = tmp_path / "outside.dcm"
    _write(outside, ds)
    try:
        (source / "linked.dcm").symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are not permitted")
    _write(candidate / "linked.dcm", deepcopy(ds))
    with pytest.raises(ValueError, match="symbolic-link"):
        evaluate_corpus(source, candidate)
