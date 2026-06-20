#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

CONFIG_SCHEMAS = {
    "dicomweb.example.json": "dicomweb-config.schema.json",
    "external-validation.example.json": "external-validation-config.schema.json",
    "orthanc.example.json": "adapter-config.schema.json",
    "rsna-anonymizer.example.json": "adapter-config.schema.json",
    "rsna-ctp.example.json": "adapter-config.schema.json",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def check(root: Path) -> list[str]:
    public = root / "schemas"
    packaged = root / "src" / "dicom_privacy_auditor" / "schemas"
    errors: list[str] = []
    public_names = {path.name for path in public.glob("*.schema.json")}
    packaged_names = {path.name for path in packaged.glob("*.schema.json")}
    if public_names != packaged_names:
        missing_public = sorted(packaged_names - public_names)
        missing_packaged = sorted(public_names - packaged_names)
        if missing_public:
            errors.append(f"schemas missing from public directory: {', '.join(missing_public)}")
        if missing_packaged:
            errors.append(f"schemas missing from package: {', '.join(missing_packaged)}")
    for name in sorted(public_names | packaged_names):
        public_path = public / name
        package_path = packaged / name
        if not public_path.is_file() or not package_path.is_file():
            continue
        if public_path.read_bytes() != package_path.read_bytes():
            errors.append(f"public/package schema drift: {name}")
        try:
            schema = _load(package_path)
            Draft202012Validator.check_schema(schema)
            if schema.get("type") == "object" and "additionalProperties" not in schema:
                errors.append(f"top-level object schema lacks explicit additionalProperties policy: {name}")
        except Exception as exc:
            errors.append(f"invalid schema {name}: {exc}")

    for config_name, schema_name in CONFIG_SCHEMAS.items():
        config_path = root / "configs" / config_name
        schema_path = packaged / schema_name
        try:
            payload = _load(config_path)
            schema = _load(schema_path)
            validation_errors = sorted(
                Draft202012Validator(schema).iter_errors(payload), key=lambda item: list(item.absolute_path)
            )
            for error in validation_errors:
                location = ".".join(str(part) for part in error.absolute_path) or "<root>"
                errors.append(f"{config_name} fails {schema_name} at {location}: {error.message}")
        except Exception as exc:
            errors.append(f"could not validate {config_name}: {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate schemas, mirrors, and example configurations")
    parser.add_argument("root", type=Path, nargs="?", default=Path.cwd())
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    errors = check(args.root.resolve())
    payload = {"ok": not errors, "errors": errors}
    if args.as_json:
        print(json.dumps(payload, indent=2))
    elif errors:
        for error in errors:
            print(f"ERROR: {error}")
    else:
        print("Schema integrity check passed")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
