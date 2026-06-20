from __future__ import annotations

import hashlib
import tarfile

from scripts.package_native_release import _project_version, _write_tar_gz


def test_native_tar_archive_metadata_is_reproducible(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    executable = staging / "DICOMPrivacyAuditor-CLI"
    executable.write_bytes(b"binary")
    executable.chmod(0o755)
    (staging / "README.txt").write_text("readme")
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_tar_gz(staging, first, "package", epoch=1781913600)
    _write_tar_gz(staging, second, "package", epoch=1781913600)
    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    with tarfile.open(first) as archive:
        members = {item.name: item for item in archive.getmembers()}
    assert members["package/DICOMPrivacyAuditor-CLI"].mode == 0o755
    assert members["package/README.txt"].mode == 0o644
    assert all(item.uid == 0 and item.gid == 0 and item.mtime == 1781913600 for item in members.values())


def test_native_packaging_reads_version_from_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "9.8.7"\n')
    assert _project_version(tmp_path) == "9.8.7"
