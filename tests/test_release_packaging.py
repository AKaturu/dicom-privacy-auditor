from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from scripts.assemble_release_bundle import assemble
from scripts.package_source_release import collect_files, package_source


def test_source_package_is_reproducible_and_excludes_runtime_artifacts(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nname="x"\nversion="1.2.3"\n')
    (root / "README.md").write_text("hello")
    (root / ".coverage").write_text("runtime")
    (root / "build").mkdir()
    (root / "build" / "bad.txt").write_text("bad")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    package_source(root, first, epoch=1781913600)
    package_source(root, second, epoch=1781913600)
    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
    assert "dicom-privacy-auditor-v1.2.3/README.md" in names
    assert not any(".coverage" in name or "/build/" in name for name in names)
    assert all(not path.is_symlink() for path in collect_files(root))


def test_release_bundle_is_reproducible_and_has_valid_manifest(tmp_path):
    schema_root = Path(__file__).resolve().parents[1] / "schemas" / "release-manifest.schema.json"
    artifact = tmp_path / "artifact.whl"
    artifact.write_bytes(b"wheel")
    gate = tmp_path / "local-release-gate.json"
    gate.write_text("{}")
    first = tmp_path / "bundle-a.zip"
    second = tmp_path / "bundle-b.zip"
    one = assemble("0.7.0", [artifact, gate], first, schema_path=schema_root, epoch=1781913600)
    two = assemble("0.7.0", [artifact, gate], second, schema_path=schema_root, epoch=1781913600)
    assert one["sha256"] == two["sha256"]
    with zipfile.ZipFile(first) as archive:
        manifest = json.loads(archive.read("RELEASE-MANIFEST.json"))
        checksums = archive.read("SHA256SUMS.txt").decode()
    assert manifest["release"] == "0.7.0"
    assert manifest["local_release_gate"]["name"] == gate.name
    assert artifact.name in checksums


def _write_test_sdist(path: Path, *, mtime: int, unsafe_name: str | None = None) -> None:
    import gzip
    import io
    import tarfile

    with path.open("wb") as raw:
        with gzip.GzipFile(filename=path.name, mode="wb", fileobj=raw, mtime=mtime) as compressed:
            with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as archive:
                directory = tarfile.TarInfo("project-1.0")
                directory.type = tarfile.DIRTYPE
                directory.mode = 0o700
                directory.mtime = mtime
                archive.addfile(directory)
                member = tarfile.TarInfo(unsafe_name or "project-1.0/module.py")
                payload = b"print('hello')\n"
                member.size = len(payload)
                member.mode = 0o600
                member.mtime = mtime + 10
                archive.addfile(member, io.BytesIO(payload))


def test_sdist_normalization_is_reproducible_and_safe(tmp_path):
    import tarfile

    from scripts.normalize_sdist import normalize_sdist

    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_test_sdist(first, mtime=100)
    _write_test_sdist(second, mtime=200)
    first_digest = normalize_sdist(first, epoch=1781913600)
    second_digest = normalize_sdist(second, epoch=1781913600)
    assert first_digest == second_digest
    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, "r:gz") as archive:
        members = archive.getmembers()
    assert [member.name for member in members] == ["project-1.0", "project-1.0/module.py"]
    assert all(member.uid == 0 and member.gid == 0 for member in members)
    assert all(member.mtime == 1781913600 for member in members)
    assert members[0].mode == 0o755
    assert members[1].mode == 0o644


def test_sdist_normalization_rejects_unsafe_members(tmp_path):
    import pytest

    from scripts.normalize_sdist import normalize_sdist

    archive = tmp_path / "unsafe.tar.gz"
    _write_test_sdist(archive, mtime=100, unsafe_name="../escape.py")
    with pytest.raises(ValueError, match="Unsafe archive member"):
        normalize_sdist(archive, epoch=1781913600)


def test_runtime_sbom_attaches_root_dependency_edges():
    from scripts.generate_runtime_sbom import attach_direct_dependencies

    payload = {
        "components": [
            {"bom-ref": "a-ref", "name": "Package_A"},
            {"bom-ref": "b-ref", "name": "package-b"},
        ],
        "dependencies": [{"ref": "root-component"}, {"ref": "a-ref"}, {"ref": "b-ref"}],
    }
    result = attach_direct_dependencies(payload, {"package-a", "package-b"})
    root = next(item for item in result["dependencies"] if item["ref"] == "root-component")
    assert root["dependsOn"] == ["a-ref", "b-ref"]


def test_sdist_normalization_enforces_resource_limits(tmp_path):
    import pytest

    from scripts.normalize_sdist import normalize_sdist

    archive = tmp_path / "limited.tar.gz"
    _write_test_sdist(archive, mtime=100)
    with pytest.raises(ValueError, match="maximum is 1"):
        normalize_sdist(archive, epoch=1781913600, max_members=1)

    _write_test_sdist(archive, mtime=100)
    with pytest.raises(ValueError, match="maximum is 4"):
        normalize_sdist(archive, epoch=1781913600, max_member_bytes=4)

    _write_test_sdist(archive, mtime=100)
    with pytest.raises(ValueError, match="uncompressed bytes"):
        normalize_sdist(archive, epoch=1781913600, max_uncompressed_bytes=4)


def test_sdist_normalization_rejects_links_and_duplicate_members(tmp_path):
    import gzip
    import io
    import tarfile

    import pytest

    from scripts.normalize_sdist import normalize_sdist

    linked = tmp_path / "linked.tar.gz"
    with linked.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=1) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                link = tarfile.TarInfo("project/link")
                link.type = tarfile.SYMTYPE
                link.linkname = "target"
                archive.addfile(link)
    with pytest.raises(ValueError, match="links and special files"):
        normalize_sdist(linked, epoch=1781913600)

    duplicate = tmp_path / "duplicate.tar.gz"
    with duplicate.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=1) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for payload in (b"a", b"b"):
                    member = tarfile.TarInfo("project/file.txt")
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
    with pytest.raises(ValueError, match="Duplicate archive member"):
        normalize_sdist(duplicate, epoch=1781913600)


def test_source_packager_ignores_symlinks_inside_excluded_directories(tmp_path):
    from scripts.package_source_release import collect_files

    root = tmp_path / "project"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\nversion="0.7.1"\n', encoding="utf-8")
    (root / "README.md").write_text("ok", encoding="utf-8")
    excluded = root / ".venv" / "bin"
    excluded.mkdir(parents=True)
    target = root / "README.md"
    try:
        (excluded / "python").symlink_to(target)
    except OSError:
        return
    assert target in collect_files(root)
    assert all(".venv" not in path.parts for path in collect_files(root))
