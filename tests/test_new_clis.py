from __future__ import annotations

import json
import sqlite3
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from dicom_privacy_auditor.campaign.cli import main as campaign_main
from dicom_privacy_auditor.corpus.cli import main as corpus_main
from dicom_privacy_auditor.dicomweb.cli import main as dicomweb_main
from dicom_privacy_auditor.iod.cli import main as iod_main
from dicom_privacy_auditor.review_cli import main as review_main
from dicom_privacy_auditor.study.cli import main as study_main


def _write(path, *, patient="P1", study=None):
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds = FileDataset(str(path), {}, file_meta=meta, preamble=b"\0" * 128)
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.StudyInstanceUID = study or generate_uid()
    ds.SeriesInstanceUID = generate_uid()
    ds.PatientID = patient
    ds.PatientName = "DOE^JANE"
    ds.save_as(path, enforce_file_format=True)
    return ds


def _iod_bundle(path):
    data = {
        "ciods.json": [{"name": "Secondary Capture", "id": "secondary-capture"}],
        "sops.json": [
            {
                "name": "Secondary Capture",
                "id": str(SecondaryCaptureImageStorage),
                "ciod": "Secondary Capture",
            }
        ],
        "ciod_to_modules.json": [
            {"ciodId": "secondary-capture", "moduleId": "patient", "usage": "M", "conditionalStatement": None}
        ],
        "module_to_attributes.json": [{"moduleId": "patient", "path": "patient:00100020", "type": "1"}],
    }
    with zipfile.ZipFile(path, "w") as z:
        for name, value in data.items():
            z.writestr("standard/" + name, json.dumps(value))


def test_review_iod_corpus_and_study_clis(tmp_path, monkeypatch):
    source = tmp_path / "source"
    candidate = tmp_path / "candidate"
    source.mkdir()
    candidate.mkdir()
    study = generate_uid()
    _write(source / "a.dcm", patient="PHI", study=study)
    _write(candidate / "a.dcm", patient="PX", study=study)
    database = tmp_path / "review.sqlite"
    assert review_main(["create", str(source), str(candidate), str(database)]) == 0
    assert review_main(["summary", str(database)]) == 0
    from dicom_privacy_auditor.review.store import ReviewStore

    case_id = ReviewStore(database).list_cases()[0].case_id
    assert (
        review_main(
            [
                "decide",
                str(database),
                case_id,
                "--reviewer",
                "r1",
                "--scope",
                "case",
                "--target",
                "whole",
                "--status",
                "false_positive",
            ]
        )
        == 0
    )
    assert (
        review_main(
            [
                "decide",
                str(database),
                case_id,
                "--reviewer",
                "r2",
                "--scope",
                "case",
                "--target",
                "whole",
                "--status",
                "false_positive",
            ]
        )
        == 0
    )
    assert review_main(["agreement", str(database), "r1", "r2"]) == 0
    assert review_main(["export", str(database), str(tmp_path / "review.json")]) == 0

    bundle = tmp_path / "iod.whl"
    _iod_bundle(bundle)
    cache = tmp_path / "iod-cache"
    assert (
        iod_main(["--data-dir", str(cache), "--edition", "fixture", "prepare-data", "--source", str(bundle)])
        == 0
    )
    monkeypatch.setenv("DICOM_PRIVACY_IOD_DATA_DIR", str(cache))
    monkeypatch.setenv("DICOM_PRIVACY_IOD_EDITION", "fixture")
    assert iod_main(["--data-dir", str(cache), "--edition", "fixture", "info", "--json"]) == 0
    assert (
        iod_main(["--data-dir", str(cache), "--edition", "fixture", "sop", str(SecondaryCaptureImageStorage)])
        == 0
    )

    report = tmp_path / "corpus.json"
    assert corpus_main(["evaluate", str(source), str(candidate), "--json", str(report)]) in {0, 1}
    assert report.exists()
    assert study_main(["index", str(source)]) == 0
    assert study_main(["process-local", str(source), str(tmp_path / "study-out"), "--pipeline", "noop"]) == 0


class WebHandler(BaseHTTPRequestHandler):
    dicom = b""

    def log_message(self, *_args):
        pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Allow", "GET,POST")
        self.end_headers()

    def do_GET(self):
        if self.path.startswith("/studies/1.2.3"):
            boundary = "abc123"
            body = (
                b"--"
                + boundary.encode()
                + b"\r\nContent-Type: application/dicom\r\n\r\n"
                + self.dicom
                + b"\r\n--"
                + boundary.encode()
                + b"--\r\n"
            )
            self.send_response(200)
            self.send_header(
                "Content-Type", f'multipart/related; type="application/dicom"; boundary={boundary}'
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            body = b"[]"
            self.send_response(200)
            self.send_header("Content-Type", "application/dicom+json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_dicomweb_cli_retrieve_and_store(tmp_path):
    original = tmp_path / "original.dcm"
    _write(original)
    WebHandler.dicom = original.read_bytes()
    server = HTTPServer(("127.0.0.1", 0), WebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    config = tmp_path / "web.json"
    config.write_text(
        json.dumps({"base_url": f"http://127.0.0.1:{server.server_port}", "allow_insecure_http": True})
    )
    try:
        assert dicomweb_main(["--config", str(config), "probe"]) == 0
        assert dicomweb_main(["--config", str(config), "search-studies", "--max-results", "1"]) == 0
        retrieved = tmp_path / "retrieved"
        assert dicomweb_main(["--config", str(config), "retrieve-study", "1.2.3", str(retrieved)]) == 0
        assert list(retrieved.glob("*.dcm"))
        assert dicomweb_main(["--config", str(config), "store-study", str(retrieved)]) == 0
    finally:
        server.shutdown()
        server.server_close()


def test_campaign_cli_fixture(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    ds = _write(images / "one.dcm")
    db = tmp_path / "answers.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE answers(action TEXT, sop_instance_uid TEXT, tag TEXT, value TEXT, relative_path TEXT)"
    )
    con.execute(
        "INSERT INTO answers VALUES (?,?,?,?,?)",
        ("text removed", str(ds.SOPInstanceUID), "00100010", "DOE^JANE", "one.dcm"),
    )
    con.commit()
    con.close()
    from dicom_privacy_auditor.benchmark.midi import import_midi

    imported = tmp_path / "imported"
    import_midi(db, images, imported)
    assert campaign_main(["run-tool", str(imported), str(tmp_path / "workspace"), "--tool", "noop"]) == 0
    definition = tmp_path / "campaign.json"
    definition.write_text(json.dumps({"tools": [{"name": "noop"}]}))
    assert campaign_main(["run", str(imported), str(tmp_path / "workspace2"), str(definition)]) == 0
