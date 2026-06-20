from __future__ import annotations

import json
import zipfile
from copy import deepcopy

from pydicom.dataset import Dataset, FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from dicom_privacy_auditor.iod.evaluate import iod_context_for_pair, type_constraints
from dicom_privacy_auditor.iod.registry import load_registry, prepare_registry, resolve_context
from dicom_privacy_auditor.ps315.evaluate import evaluate_pair


def _source_bundle(path):
    data = {
        "ciods.json": [{"name": "Secondary Capture", "id": "secondary-capture"}],
        "sops.json": [
            {
                "name": "Secondary Capture Image Storage",
                "id": str(SecondaryCaptureImageStorage),
                "ciod": "Secondary Capture",
            }
        ],
        "ciod_to_modules.json": [
            {"ciodId": "secondary-capture", "moduleId": "patient", "usage": "M", "conditionalStatement": None}
        ],
        "module_to_attributes.json": [
            {"moduleId": "patient", "path": "patient:00100010", "tag": "(0010,0010)", "type": "2"},
            {"moduleId": "patient", "path": "patient:00100020", "tag": "(0010,0020)", "type": "1"},
        ],
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, payload in data.items():
            z.writestr("standard/" + name, json.dumps(payload))


def _write(path, ds):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = ds.SOPClassUID
    meta.MediaStorageSOPInstanceUID = ds.SOPInstanceUID
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    file_ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    file_ds.update(ds)
    file_ds.save_as(path, enforce_file_format=True)


def test_local_iod_registry_and_ps315_override(tmp_path, monkeypatch):
    bundle = tmp_path / "iod.zip"
    _source_bundle(bundle)
    registry = prepare_registry(bundle, edition="fixture", output=tmp_path / "cache")
    monkeypatch.setenv("DICOM_PRIVACY_IOD_DATA_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DICOM_PRIVACY_IOD_EDITION", "fixture")
    load_registry.cache_clear()
    assert resolve_context(str(SecondaryCaptureImageStorage)).resolved
    source = Dataset()
    source.SOPClassUID = SecondaryCaptureImageStorage
    source.SOPInstanceUID = generate_uid()
    source.PatientName = "DOE^JANE"
    source.PatientID = "MRN"
    candidate = deepcopy(source)
    candidate.PatientName = ""
    del candidate.PatientID
    source_path = tmp_path / "source.dcm"
    candidate_path = tmp_path / "candidate.dcm"
    _write(source_path, source)
    _write(candidate_path, candidate)
    summary, context = iod_context_for_pair(source, candidate, registry_path=registry)
    assert summary.context.resolved
    assert context["00100020"]["attribute_type"] == "1"
    evaluation = evaluate_pair(source_path, candidate_path, iod_aware=True, iod_registry_path=registry)
    patient_id = next(item for item in evaluation.results if item.keyword == "PatientID")
    assert patient_id.status == "fail"
    assert "does not permit removal" in patient_id.reason
    assert evaluation.iod_summary["context"]["ciod_id"] == "secondary-capture"


def test_type_constraints():
    assert type_constraints("1", True)["requires_nonempty"]
    assert not type_constraints("2", True)["may_remove"]
    assert type_constraints("1C", False)["condition"] == "unresolved"


def test_iod_aware_flags_candidate_only_undefined_attribute(tmp_path, monkeypatch):
    bundle = tmp_path / "iod.zip"
    _source_bundle(bundle)
    registry = prepare_registry(bundle, edition="fixture-added", output=tmp_path / "cache")
    monkeypatch.setenv("DICOM_PRIVACY_IOD_DATA_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("DICOM_PRIVACY_IOD_EDITION", "fixture-added")
    load_registry.cache_clear()
    source = Dataset()
    source.SOPClassUID = SecondaryCaptureImageStorage
    source.SOPInstanceUID = generate_uid()
    source.PatientID = "MRN"
    candidate = deepcopy(source)
    candidate.StudyDescription = "candidate-only attribute"
    source_path = tmp_path / "source-added.dcm"
    candidate_path = tmp_path / "candidate-added.dcm"
    _write(source_path, source)
    _write(candidate_path, candidate)
    evaluation = evaluate_pair(source_path, candidate_path, iod_aware=True, iod_registry_path=registry)
    added = next(item for item in evaluation.results if item.keyword == "StudyDescription")
    assert added.status == "fail"
    assert added.expected == ["X"]
    assert "not defined in the active IOD" in added.reason


def test_iod_registry_rejects_unsafe_edition_and_ambiguous_zip(tmp_path):
    import pytest

    from dicom_privacy_auditor.iod.registry import registry_path

    with pytest.raises(ValueError, match="IOD edition"):
        registry_path(data_dir=tmp_path, edition="../../escape")

    bundle = tmp_path / "duplicate.zip"
    _source_bundle(bundle)
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("other/ciods.json", "[]")
    with pytest.raises(ValueError, match="copies of ciods.json"):
        prepare_registry(bundle, edition="fixture", output=tmp_path / "cache")


def test_iod_registry_rejects_unsafe_zip_member_and_size_limit(tmp_path, monkeypatch):
    import pytest

    from dicom_privacy_auditor.iod import registry as registry_module

    bundle = tmp_path / "unsafe.zip"
    _source_bundle(bundle)
    with zipfile.ZipFile(bundle, "a") as archive:
        archive.writestr("../outside.json", "{}")
    with pytest.raises(ValueError, match="Unsafe IOD archive member"):
        prepare_registry(bundle, edition="fixture", output=tmp_path / "cache")

    bounded = tmp_path / "bounded.zip"
    _source_bundle(bounded)
    monkeypatch.setattr(registry_module, "MAX_IOD_JSON_BYTES", 2)
    with pytest.raises(ValueError, match="byte limit"):
        prepare_registry(bounded, edition="fixture", output=tmp_path / "cache")


def test_iod_registry_rejects_symlinked_directory_json(tmp_path):
    import os

    import pytest

    if not hasattr(os, "symlink"):
        pytest.skip("symbolic links are unavailable")
    source = tmp_path / "source"
    source.mkdir()
    outside = tmp_path / "outside.json"
    outside.write_text("[]", encoding="utf-8")
    try:
        (source / "ciods.json").symlink_to(outside)
    except OSError:
        pytest.skip("symbolic links are not permitted")
    for name in ("sops.json", "ciod_to_modules.json", "module_to_attributes.json"):
        (source / name).write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="symbolic link"):
        prepare_registry(source, edition="fixture", output=tmp_path / "cache")
