from __future__ import annotations

import io
import json
import os
import tarfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence

from dicom_privacy_auditor.audit import audit_dataset, audit_file, walk_dataset
from dicom_privacy_auditor.campaign.evidence import verify_evidence_package
from dicom_privacy_auditor.jsonio import write_json
from dicom_privacy_auditor.permissions import atomic_write_text


@settings(
    max_examples=75,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(st.binary(min_size=0, max_size=4096))
def test_arbitrary_bytes_never_escape_audit_boundary(tmp_path: Path, payload: bytes) -> None:
    path = tmp_path / "candidate.dcm"
    path.write_bytes(payload)
    report = audit_file(path, force=False)
    assert report.source.startswith("<redacted-source:")
    assert report.file_sha256 is not None
    assert isinstance(report.readable, bool)


@settings(max_examples=40, deadline=None)
@given(
    patient_name=st.text(max_size=128),
    patient_id=st.text(max_size=128),
    depth=st.integers(min_value=0, max_value=12),
)
def test_generated_nested_datasets_are_auditable(patient_name: str, patient_id: str, depth: int) -> None:
    root = Dataset()
    root.PatientName = patient_name
    root.PatientID = patient_id
    current = root
    for _ in range(depth):
        child = Dataset()
        current.ReferencedStudySequence = Sequence([child])
        current = child
    report = audit_dataset(root)
    assert report.readable is True
    assert len(list(walk_dataset(root))) >= depth
    assert all(finding.value_preview != patient_name for finding in report.findings)


@pytest.mark.parametrize(
    "member_name",
    [
        "../escape",
        "root/../../escape",
        "/absolute/path",
        "C:/Windows/System32/file",
        "root\\..\\escape",
        "./dot/file",
        "root//double/file",
    ],
)
def test_archive_path_traversal_variants_are_rejected(tmp_path: Path, member_name: str) -> None:
    archive_path = tmp_path / "hostile.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        payload = b"x"
        info = tarfile.TarInfo(member_name)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    with pytest.raises(ValueError, match="unsafe archive member"):
        verify_evidence_package(archive_path)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE])
def test_non_regular_archive_members_are_rejected(tmp_path: Path, kind: bytes) -> None:
    archive_path = tmp_path / "hostile.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo("evidence/hostile")
        info.type = kind
        info.linkname = "../../outside"
        archive.addfile(info)
    with pytest.raises(ValueError, match="unsupported archive member type"):
        verify_evidence_package(archive_path)


def test_atomic_json_preserves_previous_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "result.json"
    destination.write_text('{"state":"old"}\n', encoding="utf-8")

    def fail_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated crash"):
        write_json(destination, {"state": "new"})
    assert json.loads(destination.read_text(encoding="utf-8")) == {"state": "old"}
    assert not list(tmp_path.glob(".result.json.*"))


def test_atomic_text_preserves_previous_file_when_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "status.txt"
    destination.write_text("old", encoding="utf-8")
    monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("simulated crash")))
    with pytest.raises(OSError, match="simulated crash"):
        atomic_write_text(destination, "new")
    assert destination.read_text(encoding="utf-8") == "old"
    assert not list(tmp_path.glob(".status.txt.*"))


def test_atomic_writers_refuse_destination_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("safe", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symbolic links unavailable")
    with pytest.raises(ValueError, match="symbolic link"):
        atomic_write_text(link, "unsafe")
    assert target.read_text(encoding="utf-8") == "safe"
