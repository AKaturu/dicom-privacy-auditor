from __future__ import annotations

from pathlib import Path


def test_repository_does_not_contain_part15_document_or_complete_tables():
    root = Path(__file__).resolve().parents[1]
    prohibited = [
        *root.glob("vendor/part15*.docx"),
        *root.glob("src/dicom_privacy_auditor/data/ps315_*_table_e1_*.json"),
    ]
    assert prohibited == []


def test_manifest_does_not_package_vendor_standards_documents():
    root = Path(__file__).resolve().parents[1]
    manifest = (root / "MANIFEST.in").read_text(encoding="utf-8")
    assert "vendor" not in manifest
    assert "part15" not in manifest.casefold()


def test_trademark_notice_is_present_in_public_documentation():
    root = Path(__file__).resolve().parents[1]
    required = [root / "README.md", root / "docs" / "LEGAL_NOTICES.md", root / "NOTICE"]
    phrase = "DICOM® is the registered trademark of the National Electrical Manufacturers Association"
    for path in required:
        assert phrase in path.read_text(encoding="utf-8")
