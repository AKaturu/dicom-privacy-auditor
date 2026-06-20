from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pydicom.dataset import Dataset


@dataclass(frozen=True)
class PixelScanResult:
    analyzable: bool
    suspicious: bool
    score: float
    bbox: tuple[int, int, int, int] | None = None
    reason: str | None = None


def _normalize_frame(array: np.ndarray) -> np.ndarray:
    frame = np.asarray(array)
    if frame.ndim == 3 and frame.shape[-1] in {3, 4}:
        frame = frame[..., :3].mean(axis=-1)
    elif frame.ndim > 2:
        frame = frame.reshape((-1, *frame.shape[-2:]))[0]
    frame = frame.astype(np.float32)
    finite = np.isfinite(frame)
    if not finite.any():
        return np.zeros(frame.shape, dtype=np.float32)
    low, high = np.percentile(frame[finite], [1, 99])
    if high <= low:
        return np.zeros(frame.shape, dtype=np.float32)
    return np.clip((frame - low) / (high - low), 0, 1)


def scan_text_like_border(dataset: Dataset) -> PixelScanResult:
    """Experimental high-contrast border-region detector.

    This is deliberately not OCR and does not claim to prove the presence or absence
    of text. It identifies dense, high-contrast components near image borders where
    burned-in annotations commonly occur. The result must be treated as a review
    signal, not a de-identification decision.
    """
    if "PixelData" not in dataset:
        return PixelScanResult(False, False, 0.0, reason="No PixelData")
    try:
        image = _normalize_frame(dataset.pixel_array)
    except Exception as exc:  # compressed transfer syntax or malformed pixel module
        return PixelScanResult(False, False, 0.0, reason=f"Pixel decoding failed: {type(exc).__name__}")

    if image.ndim != 2 or min(image.shape) < 16:
        return PixelScanResult(False, False, 0.0, reason="Unsupported pixel shape")

    height, width = image.shape
    border_h = max(8, int(height * 0.25))
    border_w = max(8, int(width * 0.15))
    mask = np.zeros_like(image, dtype=bool)
    mask[:border_h, :] = True
    mask[-border_h:, :] = True
    mask[:, :border_w] = True
    mask[:, -border_w:] = True

    # Bright/dark local edges are a useful synthetic benchmark signal, but not OCR.
    gx = np.zeros_like(image)
    gy = np.zeros_like(image)
    gx[:, 1:] = np.abs(np.diff(image, axis=1))
    gy[1:, :] = np.abs(np.diff(image, axis=0))
    edge = np.maximum(gx, gy)
    candidate = mask & (edge >= 0.35)
    count = int(candidate.sum())
    density = count / max(int(mask.sum()), 1)

    if count:
        ys, xs = np.where(candidate)
        bbox = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    else:
        bbox = None

    suspicious = count >= 20 and density >= 0.0015
    return PixelScanResult(True, suspicious, float(density), bbox=bbox)


def patch_similarity(original: np.ndarray, candidate: np.ndarray) -> float:
    """Return normalized correlation in [-1, 1] for equal-shaped image patches."""
    a = np.asarray(original, dtype=np.float32).ravel()
    b = np.asarray(candidate, dtype=np.float32).ravel()
    if a.shape != b.shape or a.size == 0:
        return -1.0
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 1.0 if np.array_equal(original, candidate) else 0.0
    return float(np.dot(a, b) / denom)
