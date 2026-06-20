from __future__ import annotations

import json
import os
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class ReportValidationError(ValueError):
    pass


def load_schema(name: str) -> dict[str, Any]:
    filename = name if name.endswith(".schema.json") else f"{name}.schema.json"
    resource = resources.files("dicom_privacy_auditor.schemas").joinpath(filename)
    return json.loads(resource.read_text(encoding="utf-8"))


def validate_payload(payload: Any, schema_name: str) -> None:
    validator = Draft202012Validator(load_schema(schema_name))
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.absolute_path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise ReportValidationError(f"{schema_name} validation failed at {location}: {first.message}")


def write_json(path: str | Path, payload: Any, *, schema_name: str | None = None) -> Path:
    destination = Path(path)
    normalized = json.loads(json.dumps(payload, ensure_ascii=False))
    if schema_name:
        validate_payload(normalized, schema_name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(normalized, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def validate_json_file(path: str | Path, schema_name: str) -> None:
    validate_payload(json.loads(Path(path).read_text(encoding="utf-8")), schema_name)
