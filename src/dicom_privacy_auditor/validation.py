from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pydicom
from pydicom.dataset import Dataset


@dataclass
class ValidationResult:
    readable: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid_basic(self) -> bool:
        return self.readable and not self.errors

    def to_dict(self) -> dict[str, object]:
        return {
            "readable": self.readable,
            "valid_basic": self.valid_basic,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def validate_dataset(dataset: Dataset) -> ValidationResult:
    result = ValidationResult(readable=True)
    for keyword in ("SOPClassUID", "SOPInstanceUID"):
        if not getattr(dataset, keyword, None):
            result.errors.append(f"Missing required identity attribute: {keyword}")

    file_meta = getattr(dataset, "file_meta", None)
    if file_meta:
        media_sop = str(getattr(file_meta, "MediaStorageSOPInstanceUID", ""))
        sop = str(getattr(dataset, "SOPInstanceUID", ""))
        if media_sop and sop and media_sop != sop:
            result.errors.append("MediaStorageSOPInstanceUID does not match SOPInstanceUID")
        media_class = str(getattr(file_meta, "MediaStorageSOPClassUID", ""))
        sop_class = str(getattr(dataset, "SOPClassUID", ""))
        if media_class and sop_class and media_class != sop_class:
            result.errors.append("MediaStorageSOPClassUID does not match SOPClassUID")
        if not getattr(file_meta, "TransferSyntaxUID", None):
            result.errors.append("Missing TransferSyntaxUID in file meta")
    else:
        result.warnings.append("No File Meta Information")

    if "PixelData" in dataset:
        required = (
            "Rows",
            "Columns",
            "SamplesPerPixel",
            "PhotometricInterpretation",
            "BitsAllocated",
            "BitsStored",
            "HighBit",
            "PixelRepresentation",
        )
        missing = [keyword for keyword in required if getattr(dataset, keyword, None) is None]
        if missing:
            result.errors.append("PixelData present but pixel module is missing: " + ", ".join(missing))
        else:
            try:
                _ = dataset.pixel_array
            except Exception as exc:
                result.warnings.append(f"Pixel decoding failed: {type(exc).__name__}: {exc}")
    return result


def validate_file(path: str | Path, *, force: bool = False) -> ValidationResult:
    try:
        dataset = pydicom.dcmread(path, force=force)
    except Exception as exc:
        return ValidationResult(readable=False, errors=[f"{type(exc).__name__}: {exc}"])
    return validate_dataset(dataset)
