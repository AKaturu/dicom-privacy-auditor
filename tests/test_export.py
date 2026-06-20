import json
import stat

from pydicom.dataset import Dataset

from dicom_privacy_auditor.audit import audit_dataset
from dicom_privacy_auditor.export import write_csv, write_json


def test_exports(tmp_path):
    ds = Dataset()
    ds.PatientName = "DOE^JANE"
    report = audit_dataset(ds)

    json_path = tmp_path / "report.json"
    csv_path = tmp_path / "report.csv"
    write_json([report], json_path)
    write_csv([report], csv_path)

    payload = json.loads(json_path.read_text())
    assert payload[0]["finding_count"] == 2
    assert "DIRECT_IDENTIFIER_PRESENT" in csv_path.read_text()
    assert stat.S_IMODE(json_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(csv_path.stat().st_mode) == 0o600
