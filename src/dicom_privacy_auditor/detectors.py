from __future__ import annotations

import hashlib
import re
from pathlib import Path

from pydicom.dataelem import DataElement
from pydicom.multival import MultiValue

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}(?!\d)")
SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
DATE_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}[-/]?(?:0[1-9]|1[0-2])[-/]?(?:0[1-9]|[12]\d|3[01])(?!\d)")
IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
LABELED_ID_RE = re.compile(
    r"\b(?:MRN|MEDICAL\s*RECORD|PATIENT\s*ID|ACCESSION|VISIT|ACCOUNT)\s*[:#-]?\s*[A-Z0-9-]{4,}\b",
    re.IGNORECASE,
)
NAME_LABEL_RE = re.compile(r"\b(?:PATIENT|NAME)\s*[:=-]\s*[A-Z][A-Z' -]{2,}", re.IGNORECASE)
PERSON_NAME_RE = re.compile(r"\b[A-Z][A-Z' -]{1,}\^[A-Z][A-Z' -]{1,}\b", re.IGNORECASE)
SAFE_FILENAME_RE = re.compile(
    r"^(?:[0-9]+|[0-9a-f]{16,}|(?:\d+\.){3,}\d+|IM-?\d+|IMG-?\d+|image-?\d+|case-?\d+)$",
    re.IGNORECASE,
)


def normalize_value(value: object) -> str:
    """Return a bounded, printable value for rule checks and reports."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return f"<bytes:{len(value)}>"
    if isinstance(value, (list, tuple, MultiValue)):
        text = "\\".join(str(item) for item in value)
    else:
        text = str(value)
    return text.replace("\x00", "").strip()


def fingerprint(value: object, length: int = 12) -> str | None:
    text = normalize_value(value)
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def evidence_preview(value: object, *, show_values: bool = False, max_length: int = 80) -> str:
    text = normalize_value(value)
    if not text:
        return ""
    if show_values:
        return text if len(text) <= max_length else text[: max_length - 1] + "…"
    return f"<redacted sha256:{fingerprint(text)} length:{len(text)}>"


def suspicious_text_patterns(text: str) -> list[str]:
    patterns: list[str] = []
    if EMAIL_RE.search(text):
        patterns.append("email address")
    if PHONE_RE.search(text):
        patterns.append("telephone number")
    if SSN_RE.search(text):
        patterns.append("SSN-like value")
    if LABELED_ID_RE.search(text):
        patterns.append("labeled patient/record identifier")
    if NAME_LABEL_RE.search(text):
        patterns.append("labeled person name")
    if PERSON_NAME_RE.search(text):
        patterns.append("DICOM person-name pattern")
    if IP_RE.search(text):
        patterns.append("IPv4-like address")
    return patterns


def filename_risk(path: Path) -> str | None:
    stem = path.stem.strip()
    if not stem:
        return None
    if EMAIL_RE.search(stem) or PHONE_RE.search(stem) or LABELED_ID_RE.search(stem):
        return "Filename contains an explicit identifier pattern"
    if "^" in stem or "," in stem:
        return "Filename resembles a person-name encoding"
    if not SAFE_FILENAME_RE.fullmatch(stem) and re.search(r"[A-Za-z]{3,}[_ -][A-Za-z]{2,}", stem):
        return "Filename contains multiple alphabetic tokens and should be reviewed"
    return None


def is_nonempty(element: DataElement) -> bool:
    text = normalize_value(element.value)
    return bool(text) and text not in {"<bytes:0>", "None"}
