#!/usr/bin/env python3
"""Assemble a deterministic release bundle with checksums and a machine-readable manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import shutil
import stat
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

DEFAULT_SOURCE_DATE_EPOCH = 1781913600
EXTERNAL_LIMITATIONS = [
    "Complete official MIDI-B corpus execution",
    "Live frozen Orthanc and RSNA tool execution",
    "Official MIDI-B validator parity results",
    "Independent blinded human review and adjudication",
    "Authorized institutional PACS/DICOMweb validation",
    "Windows and macOS runner results for this exact source state",
    "Trusted Authenticode signing and Apple Developer ID notarization",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _timestamp(epoch: int) -> tuple[int, int, int, int, int, int]:
    return time.gmtime(max(epoch, 315532800))[:6]


def _media_type(path: Path) -> str:
    if path.suffix == ".whl":
        return "application/zip"
    if path.name.endswith(".tar.gz"):
        return "application/gzip"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def assemble(
    release: str,
    inputs: list[Path],
    output: Path,
    *,
    schema_path: Path,
    epoch: int,
) -> dict[str, Any]:
    existing = [path.resolve() for path in inputs if path.is_file()]
    if len(existing) != len(inputs):
        missing = [str(path) for path in inputs if not path.is_file()]
        raise FileNotFoundError(f"Missing release inputs: {missing}")
    names = [path.name for path in existing]
    if len(names) != len(set(names)):
        raise ValueError("Release input filenames must be unique")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dpa-release-bundle-") as raw:
        staging = Path(raw)
        artifacts: list[dict[str, Any]] = []
        for source in sorted(existing, key=lambda item: item.name):
            target = staging / source.name
            shutil.copy2(source, target)
            artifacts.append(
                {
                    "name": target.name,
                    "sha256": _sha256(target),
                    "size_bytes": target.stat().st_size,
                    "media_type": _media_type(target),
                }
            )
        checksums = "".join(f"{item['sha256']}  {item['name']}\n" for item in artifacts)
        (staging / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8")
        gate = next((item for item in artifacts if "local-release-gate" in item["name"]), None)
        manifest = {
            "schema_version": "1.0",
            "release": release,
            "source_date_epoch": epoch,
            "generated_at": datetime.fromtimestamp(epoch, timezone.utc).isoformat(),
            "local_release_gate": gate,
            "artifacts": artifacts,
            "external_validation_not_claimed": EXTERNAL_LIMITATIONS,
        }
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(manifest)
        (staging / "RELEASE-MANIFEST.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        timestamp = _timestamp(epoch)
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.unlink(missing_ok=True)
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for path in sorted(staging.iterdir(), key=lambda item: item.name):
                    info = zipfile.ZipInfo(path.name, date_time=timestamp)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (0o644 & 0xFFFF) << 16
                    info.flag_bits |= 0x800
                    archive.writestr(
                        info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
                    )
            os.replace(temporary, output)
            os.chmod(output, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    return {"output": str(output), "sha256": _sha256(output), "manifest": manifest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "--source-date-epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", DEFAULT_SOURCE_DATE_EPOCH)),
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "schemas" / "release-manifest.schema.json",
    )
    args = parser.parse_args(argv)
    result = assemble(
        args.release,
        args.inputs,
        args.output,
        schema_path=args.schema,
        epoch=args.source_date_epoch,
    )
    print(json.dumps({"output": result["output"], "sha256": result["sha256"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
