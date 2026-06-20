from __future__ import annotations

import zipfile

from scripts.check_distribution_contents import check, prohibited_name, unsafe_archive_name


def test_distribution_policy_names_and_archive_paths():
    assert prohibited_name("vendor/part15-current.docx")
    assert prohibited_name("certificate.p12")
    assert prohibited_name("review.sqlite")
    assert unsafe_archive_name("../../escape")
    assert unsafe_archive_name("/absolute/path")
    assert not unsafe_archive_name("package/data.json")


def test_distribution_policy_detects_private_keys_and_unsafe_archives(tmp_path):
    key = tmp_path / "innocent.txt"
    key.write_text("-----BEGIN " + "PRIVATE KEY-----\nredacted\n")
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("../escape.txt", "bad")
    violations = check([tmp_path])
    assert any("private key material" in item for item in violations)
    assert any("unsafe archive path" in item for item in violations)


def test_distribution_policy_accepts_normal_release_content(tmp_path):
    (tmp_path / "README.md").write_text("safe")
    archive = tmp_path / "release.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("package/file.txt", "safe")
    assert check([tmp_path]) == []


def test_distribution_policy_rejects_embedded_keys_duplicates_and_links(tmp_path):
    import io
    import tarfile

    archive = tmp_path / "hostile.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("package/innocent.txt", "-----BEGIN " + "PRIVATE KEY-----\nredacted")
        handle.writestr("package/duplicate.txt", "one")
        handle.writestr("package/duplicate.txt", "two")
    violations = check([archive])
    assert any("embedded private key material" in item for item in violations)
    assert any("duplicate archive member" in item for item in violations)

    linked = tmp_path / "linked.tar"
    with tarfile.open(linked, "w") as handle:
        link = tarfile.TarInfo("package/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "target"
        handle.addfile(link)
        regular = tarfile.TarInfo("package/file.txt")
        payload = b"safe"
        regular.size = len(payload)
        handle.addfile(regular, io.BytesIO(payload))
    assert any("link or special archive member" in item for item in check([linked]))


def test_distribution_policy_rejects_excessive_declared_size(tmp_path):
    from scripts.check_distribution_contents import inspect_archive

    archive = tmp_path / "large.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("package/file.txt", "12345")
    violations = inspect_archive(archive, max_member_bytes=4)
    assert any("declared size" in item for item in violations)
