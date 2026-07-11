from importlib.metadata import version

from dicom_privacy_auditor import __version__


def test_package_version_matches_distribution_metadata() -> None:
    assert __version__ == version("dicom-privacy-auditor")
