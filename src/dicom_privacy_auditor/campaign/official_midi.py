from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

from ..benchmark.midi import MIDI_ACTIONS, _normalized_action, _parse_tag, _unwrap_answer_value
from ..permissions import restrict_file


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clean_uid(value: Any) -> str:
    return str(_unwrap_answer_value(value) or "").strip()


def _load_uid_new_to_old(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or {"id_old", "id_new"} - set(reader.fieldnames):
            raise ValueError("UID mapping CSV must contain id_old and id_new columns")
        for row in reader:
            old_uid, new_uid = _clean_uid(row.get("id_old")), _clean_uid(row.get("id_new"))
            if old_uid and new_uid and new_uid not in mapping:
                mapping[new_uid] = old_uid
    return mapping


class _AnswerPayloadLookup:
    def __init__(self, path: Path, *, cache_size: int = 2048) -> None:
        self.connection = sqlite3.connect(path)
        self.cache_size = cache_size
        self.cache: OrderedDict[str, tuple[str, dict[str, Any]]] = OrderedDict()

    def close(self) -> None:
        self.connection.close()

    def _load_payload(self, sop_instance_uid: str) -> tuple[str, dict[str, Any]] | None:
        cached = self.cache.get(sop_instance_uid)
        if cached is not None:
            self.cache.move_to_end(sop_instance_uid)
            return cached
        row = self.connection.execute(
            "SELECT rowid, AnswerData FROM answer_data WHERE SOPInstanceUID = ?",
            (sop_instance_uid,),
        ).fetchone()
        if row is None:
            return None
        rowid, payload_text = row
        payload = json.loads(payload_text)
        if isinstance(payload, list):
            payload = {str(index): item for index, item in enumerate(payload)}
        if not isinstance(payload, dict):
            return None
        loaded = (str(rowid), payload)
        self.cache[sop_instance_uid] = loaded
        if len(self.cache) > self.cache_size:
            self.cache.popitem(last=False)
        return loaded

    def get(self, sop_instance_uid: str, payload_key: str) -> tuple[str, dict[str, Any]] | None:
        loaded = self._load_payload(sop_instance_uid)
        if loaded is None:
            return None
        rowid, payload = loaded
        entry = payload.get(payload_key)
        if not isinstance(entry, dict):
            return None
        return rowid, entry


def _status_from_check_passed(value: Any) -> str:
    if value is None:
        return "unresolved"
    text = str(value).strip().lower()
    if text in {"1", "1.0", "true", "pass", "passed", "yes"}:
        return "pass"
    if text in {"0", "0.0", "false", "fail", "failed", "no"}:
        return "fail"
    return text or "unresolved"


def _official_rows(path: Path) -> tuple[list[str], sqlite3.Connection]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        columns = [row[1] for row in connection.execute("PRAGMA table_info(validation_results)")]
        required = {"check_index", "check_passed", "action", "instance"}
        missing = sorted(required - set(columns))
        if missing:
            raise ValueError(f"official validation_results table is missing columns: {', '.join(missing)}")
        return columns, connection
    except Exception:
        connection.close()
        raise


def _action_id(
    *,
    answer_rowid: str,
    payload_key: str,
    action: str,
    sop_instance_uid: str,
    tag: str | None,
    value: str | None,
) -> str:
    raw_id = f"{answer_rowid}:{payload_key}"
    payload = f"answer_data|{raw_id}|{action}|{sop_instance_uid}|{tag}|{value}"
    return hashlib.sha256(payload.encode()).hexdigest()[:24]


def normalize_official_midi_results(
    official_db: str | Path,
    answer_db: str | Path,
    uid_mapping: str | Path,
    output: str | Path,
    *,
    unmatched_output: str | Path | None = None,
) -> dict[str, Any]:
    """Convert official MIDI validator SQLite rows to action_id/action/status CSV rows."""
    official_path = Path(official_db)
    answer_path = Path(answer_db)
    uid_mapping_path = Path(uid_mapping)
    destination = Path(output)
    unmatched_destination = Path(unmatched_output) if unmatched_output else None
    for label, path in (
        ("official_db", official_path),
        ("answer_db", answer_path),
        ("uid_mapping", uid_mapping_path),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    if unmatched_destination:
        unmatched_destination.parent.mkdir(parents=True, exist_ok=True)

    uid_new_to_old = _load_uid_new_to_old(uid_mapping_path)
    answer_lookup = _AnswerPayloadLookup(answer_path)
    _, connection = _official_rows(official_path)

    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    unmatched_temporary: Path | None = None
    unmatched_handle = None
    if unmatched_destination:
        unmatched_descriptor, unmatched_name = tempfile.mkstemp(
            prefix=f".{unmatched_destination.name}.", dir=unmatched_destination.parent
        )
        unmatched_temporary = Path(unmatched_name)
        unmatched_handle = os.fdopen(unmatched_descriptor, "w", newline="", encoding="utf-8")

    total_rows = 0
    normalized_rows = 0
    unmatched_rows = 0
    action_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["action_id", "action", "status"])
            writer.writeheader()
            unmatched_writer = None
            if unmatched_handle:
                unmatched_writer = csv.DictWriter(
                    unmatched_handle,
                    fieldnames=[
                        "official_rowid",
                        "instance",
                        "old_sop_instance_uid",
                        "check_index",
                        "action",
                        "reason",
                    ],
                )
                unmatched_writer.writeheader()

            query = "SELECT rowid AS __official_rowid__, * FROM validation_results"
            for row in connection.execute(query):
                total_rows += 1
                candidate_instance = _clean_uid(row["instance"])
                old_sop = uid_new_to_old.get(candidate_instance, candidate_instance)
                payload_key = str(row["check_index"]).strip()
                payload_match = answer_lookup.get(old_sop, payload_key)
                action = _normalized_action(row["action"])
                if not payload_match or not payload_key:
                    unmatched_rows += 1
                    if unmatched_writer:
                        unmatched_writer.writerow(
                            {
                                "official_rowid": row["__official_rowid__"],
                                "instance": candidate_instance,
                                "old_sop_instance_uid": old_sop,
                                "check_index": payload_key,
                                "action": action,
                                "reason": "missing_answer_payload",
                            }
                        )
                    continue
                answer_rowid, answer_entry = payload_match
                action = _normalized_action(answer_entry.get("action"))
                if action not in MIDI_ACTIONS:
                    unmatched_rows += 1
                    if unmatched_writer:
                        unmatched_writer.writerow(
                            {
                                "official_rowid": row["__official_rowid__"],
                                "instance": candidate_instance,
                                "old_sop_instance_uid": old_sop,
                                "check_index": payload_key,
                                "action": action,
                                "reason": "unrecognized_action",
                            }
                        )
                    continue
                tag = _parse_tag(
                    answer_entry.get("tag") or answer_entry.get("tag_ds"),
                    _unwrap_answer_value(answer_entry.get("tag_name")),
                )
                value = _unwrap_answer_value(answer_entry.get("value"))
                status = _status_from_check_passed(row["check_passed"])
                writer.writerow(
                    {
                        "action_id": _action_id(
                            answer_rowid=answer_rowid,
                            payload_key=payload_key,
                            action=action,
                            sop_instance_uid=old_sop,
                            tag=tag,
                            value=value,
                        ),
                        "action": action,
                        "status": status,
                    }
                )
                normalized_rows += 1
                action_counts[action] = action_counts.get(action, 0) + 1
                status_counts[status] = status_counts.get(status, 0) + 1

            handle.flush()
            os.fsync(handle.fileno())
            if unmatched_handle:
                unmatched_handle.flush()
                os.fsync(unmatched_handle.fileno())

        temporary.replace(destination)
        restrict_file(destination)
        if unmatched_destination and unmatched_temporary:
            unmatched_handle.close()
            unmatched_handle = None
            unmatched_temporary.replace(unmatched_destination)
            restrict_file(unmatched_destination)

        return {
            "schema_version": "1.0",
            "official_db_sha256": _sha256(official_path),
            "answer_db_sha256": _sha256(answer_path),
            "uid_mapping_sha256": _sha256(uid_mapping_path),
            "output": str(destination),
            "output_sha256": _sha256(destination),
            "total_rows": total_rows,
            "normalized_rows": normalized_rows,
            "unmatched_rows": unmatched_rows,
            "unmatched_output": str(unmatched_destination) if unmatched_destination else None,
            "action_counts": dict(sorted(action_counts.items())),
            "status_counts": dict(sorted(status_counts.items())),
        }
    finally:
        answer_lookup.close()
        connection.close()
        if unmatched_handle:
            unmatched_handle.close()
        temporary.unlink(missing_ok=True)
        if unmatched_temporary:
            unmatched_temporary.unlink(missing_ok=True)
