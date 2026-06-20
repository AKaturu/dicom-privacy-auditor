#!/usr/bin/env python3
"""Run a live Orthanc adapter smoke test against a dedicated local instance."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pydicom

from dicom_privacy_auditor.adapters.orthanc import OrthancAdapter


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, nargs="?", default=Path("sample_data/DOE_JANE_head_ct.dcm"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8042")
    parser.add_argument("--username", default="orthanc")
    parser.add_argument("--password", default="orthanc")
    args = parser.parse_args()

    adapter = OrthancAdapter(
        {
            "base_url": args.base_url,
            "username": args.username,
            "password": args.password,
            "dicom_version": "2023b",
            "cleanup_uploaded": True,
            "cleanup_already_stored": False,
        }
    )
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "anonymized.dcm"
        print(adapter.probe())
        result = adapter.process(args.source, output, case_id="live-smoke")
        candidate = pydicom.dcmread(output)
        assert output.stat().st_size > 0
        assert str(candidate.PatientName) != "DOE^JANE"
        print({"result": result.status, "output_bytes": output.stat().st_size})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
