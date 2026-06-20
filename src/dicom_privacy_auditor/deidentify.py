from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataelem import DataElement
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue
from pydicom.uid import UID

from .profiles import DATE_TIME_KEYWORDS, DIRECT_IDENTIFIER_KEYWORDS, FREE_TEXT_KEYWORDS, SAFE_UID_KEYWORDS


@dataclass
class DeidentificationStats:
    cleared_identifiers: int = 0
    cleaned_text: int = 0
    removed_private: int = 0
    cleared_dates: int = 0
    remapped_uids: int = 0
    pixel_regions_cleaned: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "cleared_identifiers": self.cleared_identifiers,
            "cleaned_text": self.cleaned_text,
            "removed_private": self.removed_private,
            "cleared_dates": self.cleared_dates,
            "remapped_uids": self.remapped_uids,
            "pixel_regions_cleaned": self.pixel_regions_cleaned,
            "warnings": self.warnings,
        }


class UIDMapper:
    """Consistent deterministic UID mapper for research benchmarking.

    The default salt is public and therefore not suitable for reversible production
    pseudonymization. Production use requires institutionally governed key handling.
    """

    def __init__(self, salt: str = "DPA-BENCHMARK-ONLY") -> None:
        self.salt = salt
        self._mapping: dict[str, str] = {}

    def map(self, value: str) -> str:
        if value not in self._mapping:
            digest = hashlib.sha256(f"{self.salt}|{value}".encode()).digest()[:16]
            self._mapping[value] = f"2.25.{int.from_bytes(digest, 'big')}"
        return self._mapping[value]


def _is_class_or_encoding_uid(element: DataElement) -> bool:
    keyword = element.keyword or ""
    return keyword in SAFE_UID_KEYWORDS or keyword.endswith("ClassUID") or keyword == "TransferSyntaxUID"


def _clean_elements(dataset: Dataset, mapper: UIDMapper, stats: DeidentificationStats) -> None:
    for element in list(dataset):
        if element.VR == "SQ":
            for item in element.value:
                _clean_elements(item, mapper, stats)
            continue
        if element.tag.is_private:
            del dataset[element.tag]
            stats.removed_private += 1
            continue
        keyword = element.keyword or ""
        if keyword in DIRECT_IDENTIFIER_KEYWORDS:
            element.value = ""
            stats.cleared_identifiers += 1
            continue
        if keyword in FREE_TEXT_KEYWORDS:
            element.value = "CLEANED"
            stats.cleaned_text += 1
            continue
        if keyword in DATE_TIME_KEYWORDS or element.VR in {"DA", "DT", "TM"}:
            element.value = ""
            stats.cleared_dates += 1
            continue
        if element.VR == "UI" and not _is_class_or_encoding_uid(element):
            is_multi = isinstance(element.value, (list, tuple, MultiValue))
            values = element.value if is_multi else [element.value]
            mapped = [UID(mapper.map(str(value))) for value in values if str(value)]
            element.value = mapped if is_multi else (mapped[0] if mapped else "")
            stats.remapped_uids += len(mapped)


def _clean_pixel_regions(
    dataset: Dataset, bboxes: list[tuple[int, int, int, int]], stats: DeidentificationStats
) -> None:
    if not bboxes or "PixelData" not in dataset:
        return
    try:
        pixels = np.asarray(dataset.pixel_array).copy()
    except Exception as exc:
        stats.warnings.append(f"Pixel decoding failed: {type(exc).__name__}: {exc}")
        return
    if pixels.ndim != 2:
        stats.warnings.append(
            f"Only single-frame 2D benchmark pixel cleaning is supported; shape={pixels.shape}"
        )
        return
    for x1, y1, x2, y2 in bboxes:
        x1, y1 = max(0, int(x1)), max(0, int(y1))
        x2, y2 = min(pixels.shape[1], int(x2)), min(pixels.shape[0], int(y2))
        if x2 <= x1 or y2 <= y1:
            continue
        # Use the local median so the benchmark cleaner does not add a stark black box.
        surround = pixels[
            max(0, y1 - 3) : min(pixels.shape[0], y2 + 3), max(0, x1 - 3) : min(pixels.shape[1], x2 + 3)
        ]
        fill = int(np.median(surround)) if surround.size else 0
        pixels[y1:y2, x1:x2] = fill
        stats.pixel_regions_cleaned += 1
    dataset.PixelData = np.ascontiguousarray(pixels).tobytes()
    if stats.pixel_regions_cleaned:
        dataset.BurnedInAnnotation = "NO"


def baseline_deidentify_dataset(
    dataset: Dataset,
    *,
    uid_mapper: UIDMapper | None = None,
    pixel_bboxes: list[tuple[int, int, int, int]] | None = None,
) -> tuple[Dataset, DeidentificationStats]:
    """Apply a transparent research baseline, not a PS3.15 conformance engine."""
    mapper = uid_mapper or UIDMapper()
    stats = DeidentificationStats()
    cleaned = copy.deepcopy(dataset)
    _clean_elements(cleaned, mapper, stats)
    _clean_pixel_regions(cleaned, pixel_bboxes or [], stats)

    cleaned.PatientIdentityRemoved = "YES"
    cleaned.DeidentificationMethod = "DPA baseline: clear IDs/dates/text; remove private; remap UIDs"
    cleaned.LongitudinalTemporalInformationModified = "REMOVED"
    cleaned.preamble = b"\0" * 128

    file_meta = getattr(cleaned, "file_meta", None)
    if file_meta is not None:
        for keyword in (
            "SourceApplicationEntityTitle",
            "SendingApplicationEntityTitle",
            "ReceivingApplicationEntityTitle",
        ):
            if keyword in file_meta:
                del file_meta[keyword]
        file_meta.ImplementationClassUID = UID(mapper.map("DPA-IMPLEMENTATION"))
        file_meta.ImplementationVersionName = "DPA_BASELINE_020"
        if getattr(cleaned, "SOPInstanceUID", None):
            file_meta.MediaStorageSOPInstanceUID = cleaned.SOPInstanceUID
        if getattr(cleaned, "SOPClassUID", None):
            file_meta.MediaStorageSOPClassUID = cleaned.SOPClassUID
    return cleaned, stats


def baseline_deidentify_file(
    source: str | Path,
    destination: str | Path,
    *,
    uid_mapper: UIDMapper | None = None,
    pixel_bboxes: list[tuple[int, int, int, int]] | None = None,
    force: bool = False,
) -> DeidentificationStats:
    source_path = Path(source)
    destination_path = Path(destination)
    dataset = pydicom.dcmread(source_path, force=force)
    cleaned, stats = baseline_deidentify_dataset(dataset, uid_mapper=uid_mapper, pixel_bboxes=pixel_bboxes)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.save_as(destination_path, enforce_file_format=True)
    return stats
