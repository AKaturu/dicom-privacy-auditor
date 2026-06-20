from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pydicom
from PIL import Image


def _frame(array: np.ndarray, index: int) -> np.ndarray:
    if array.ndim <= 2:
        return array
    if array.ndim == 3 and array.shape[-1] in (3, 4):
        return array
    return array[min(max(index, 0), array.shape[0] - 1)]


def render_frame(
    path: str | Path,
    frame_number: int = 0,
    *,
    window_center: float | None = None,
    window_width: float | None = None,
) -> Image.Image:
    ds = pydicom.dcmread(path)
    array = _frame(np.asarray(ds.pixel_array), frame_number).astype(np.float32)
    slope = float(getattr(ds, "RescaleSlope", 1) or 1)
    intercept = float(getattr(ds, "RescaleIntercept", 0) or 0)
    array = array * slope + intercept
    if array.ndim == 3 and array.shape[-1] in (3, 4):
        clipped = np.clip(array, 0, 255).astype(np.uint8)
        return Image.fromarray(clipped[..., :3])
    center = window_center
    width = window_width
    if center is None:
        raw = getattr(ds, "WindowCenter", None)
        if raw is not None:
            center = float(raw[0] if isinstance(raw, (list, tuple)) else raw)
    if width is None:
        raw = getattr(ds, "WindowWidth", None)
        if raw is not None:
            width = float(raw[0] if isinstance(raw, (list, tuple)) else raw)
    if center is not None and width and width > 0:
        low, high = center - width / 2.0, center + width / 2.0
    else:
        finite = array[np.isfinite(array)]
        if finite.size == 0:
            low, high = 0.0, 1.0
        else:
            low, high = np.percentile(finite, [1, 99])
            if high <= low:
                high = low + 1
    normalized = np.clip((array - low) / (high - low), 0, 1)
    if str(getattr(ds, "PhotometricInterpretation", "")) == "MONOCHROME1":
        normalized = 1 - normalized
    return Image.fromarray((normalized * 255).astype(np.uint8), mode="L")


def frame_count(path: str | Path) -> int:
    ds = pydicom.dcmread(path, stop_before_pixels=True)
    return int(getattr(ds, "NumberOfFrames", 1) or 1)


def image_metadata(path: str | Path) -> dict[str, Any]:
    ds = pydicom.dcmread(path, stop_before_pixels=True)
    return {
        "rows": int(getattr(ds, "Rows", 0) or 0),
        "columns": int(getattr(ds, "Columns", 0) or 0),
        "frames": int(getattr(ds, "NumberOfFrames", 1) or 1),
        "photometric_interpretation": str(getattr(ds, "PhotometricInterpretation", "")),
        "transfer_syntax": str(getattr(getattr(ds, "file_meta", None), "TransferSyntaxUID", "")),
    }
