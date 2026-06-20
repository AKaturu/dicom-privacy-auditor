from __future__ import annotations

import csv
import hashlib
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pydicom

from ..jsonio import write_json
from .migrations import CURRENT_SCHEMA_VERSION, current_version, migrate_connection
from .models import REVIEW_SCOPES, REVIEW_STATUSES, AgreementReport, ReviewCase, ReviewDecision

_SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY CHECK (id=1),
  created_at TEXT NOT NULL,
  source_root TEXT NOT NULL,
  candidate_root TEXT NOT NULL,
  title TEXT NOT NULL,
  schema_version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS cases (
  case_id TEXT PRIMARY KEY,
  source_path TEXT NOT NULL,
  candidate_path TEXT NOT NULL,
  study_uid TEXT,
  series_uid TEXT,
  source_sop_uid TEXT,
  candidate_sop_uid TEXT,
  modality TEXT,
  frame_count INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'pending',
  assigned_reviewer TEXT,
  priority INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
  decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
  reviewer TEXT NOT NULL,
  scope TEXT NOT NULL,
  target TEXT NOT NULL,
  status TEXT NOT NULL,
  comment TEXT NOT NULL DEFAULT '',
  frame_number INTEGER,
  x1 INTEGER, y1 INTEGER, x2 INTEGER, y2 INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cases_assignment ON cases(assigned_reviewer, priority DESC, status);
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL,
  description TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_decisions_case ON decisions(case_id);
CREATE INDEX IF NOT EXISTS idx_decisions_reviewer ON decisions(reviewer);
CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_latest_key
  ON decisions(case_id, reviewer, scope, target, COALESCE(frame_number,-1), COALESCE(x1,-1), COALESCE(y1,-1), COALESCE(x2,-1), COALESCE(y2,-1), created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _restrict_permissions(path: Path) -> None:
    """Best-effort owner-only permissions for review data containing local paths/comments."""

    try:
        os.chmod(path, 0o600)
    except OSError:
        # Some Windows/network filesystems do not implement POSIX mode bits.
        return


def _decision_key(item: ReviewDecision) -> tuple[Any, ...]:
    return (item.case_id, item.scope, item.target, item.frame_number, item.region)


def _latest_decisions(items: list[ReviewDecision]) -> dict[tuple[Any, ...], ReviewDecision]:
    result: dict[tuple[Any, ...], ReviewDecision] = {}
    for item in items:
        key = _decision_key(item)
        marker = (item.created_at or "", item.decision_id or -1)
        previous = result.get(key)
        previous_marker = (previous.created_at or "", previous.decision_id or -1) if previous else None
        if previous_marker is None or marker >= previous_marker:
            result[key] = item
    return result


def _case_id(relative: str, source_uid: str | None, candidate_uid: str | None) -> str:
    material = f"{relative}|{source_uid or ''}|{candidate_uid or ''}"
    return hashlib.sha256(material.encode()).hexdigest()[:24]


def _read_header(path: Path) -> dict[str, Any] | None:
    try:
        ds = pydicom.dcmread(path, stop_before_pixels=True, force=False)
    except Exception:
        return None
    return {
        "study_uid": str(getattr(ds, "StudyInstanceUID", "")) or None,
        "series_uid": str(getattr(ds, "SeriesInstanceUID", "")) or None,
        "sop_uid": str(getattr(ds, "SOPInstanceUID", "")) or None,
        "modality": str(getattr(ds, "Modality", "")) or None,
        "frames": int(getattr(ds, "NumberOfFrames", 1) or 1),
    }


def _dicom_files(root: Path) -> dict[str, Path]:
    output: dict[str, Path] = {}
    if root.is_file():
        output[root.name] = root
        return output
    for path in sorted(root.rglob("*")):
        if path.is_file() and _read_header(path) is not None:
            output[path.relative_to(root).as_posix()] = path
    return output


class ReviewStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def initialize(
        self,
        source_root: str | Path,
        candidate_root: str | Path,
        *,
        title: str = "DICOM privacy review",
        overwrite: bool = False,
    ) -> int:
        source = Path(source_root).expanduser().resolve()
        candidate = Path(candidate_root).expanduser().resolve()
        if self.path.exists() and overwrite:
            self.path.unlink()
        if self.path.exists():
            raise FileExistsError(f"Review database already exists: {self.path}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        source_files = _dicom_files(source)
        candidate_files = _dicom_files(candidate)
        common = sorted(set(source_files) & set(candidate_files))
        if not common:
            raise ValueError("No source/candidate DICOM files matched by relative path")
        descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        try:
            with closing(sqlite3.connect(self.path)) as connection:
                connection.executescript(_SCHEMA)
                connection.execute(
                    "INSERT INTO sessions VALUES (1,?,?,?,?,?)",
                    (_now(), str(source), str(candidate), title, CURRENT_SCHEMA_VERSION),
                )
                count = 0
                for relative in common:
                    s = _read_header(source_files[relative])
                    c = _read_header(candidate_files[relative])
                    if s is None or c is None:
                        continue
                    case = ReviewCase(
                        case_id=_case_id(relative, s["sop_uid"], c["sop_uid"]),
                        source_path=str(source_files[relative]),
                        candidate_path=str(candidate_files[relative]),
                        study_uid=s["study_uid"],
                        series_uid=s["series_uid"],
                        source_sop_uid=s["sop_uid"],
                        candidate_sop_uid=c["sop_uid"],
                        modality=s["modality"] or c["modality"],
                        frame_count=max(s["frames"], c["frames"]),
                    )
                    connection.execute(
                        """INSERT INTO cases
                        (case_id, source_path, candidate_path, study_uid, series_uid, source_sop_uid,
                         candidate_sop_uid, modality, frame_count, status, assigned_reviewer, priority, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            case.case_id,
                            case.source_path,
                            case.candidate_path,
                            case.study_uid,
                            case.series_uid,
                            case.source_sop_uid,
                            case.candidate_sop_uid,
                            case.modality,
                            case.frame_count,
                            case.status,
                            case.assigned_reviewer,
                            case.priority,
                            _now(),
                        ),
                    )
                    count += 1
                connection.execute(f"PRAGMA user_version={CURRENT_SCHEMA_VERSION}")
                connection.execute(
                    "INSERT OR REPLACE INTO schema_migrations(version, applied_at, description) VALUES (?,?,?)",
                    (CURRENT_SCHEMA_VERSION, _now(), "Initial schema"),
                )
                connection.commit()
        except Exception:
            self.path.unlink(missing_ok=True)
            raise
        _restrict_permissions(self.path)
        return count

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(f"Review database does not exist: {self.path}")
        connection = sqlite3.connect(f"{self.path.resolve().as_uri()}?mode=rw", uri=True)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        migrate_connection(connection)
        return connection

    def schema_info(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            version = current_version(connection)
            rows = connection.execute(
                "SELECT version, applied_at, description FROM schema_migrations ORDER BY version"
            ).fetchall()
        return {
            "database": str(self.path),
            "schema_version": version,
            "current_schema_version": CURRENT_SCHEMA_VERSION,
            "up_to_date": version == CURRENT_SCHEMA_VERSION,
            "migrations": [dict(row) for row in rows],
        }

    def assign_case(self, case_id: str, reviewer: str | None, *, priority: int = 0) -> None:
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                "UPDATE cases SET assigned_reviewer=?, priority=?, updated_at=? WHERE case_id=?",
                (reviewer.strip() if reviewer else None, int(priority), _now(), case_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(case_id)
            connection.commit()

    def session(self, *, disclose_paths: bool = False) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM sessions WHERE id=1").fetchone()
            if row is None:
                raise ValueError("Review database is not initialized")
            payload = dict(row)
            if not disclose_paths:
                payload["source_root"] = "redacted"
                payload["candidate_root"] = "redacted"
            return payload

    def list_cases(self, *, status: str | None = None) -> list[ReviewCase]:
        query = "SELECT * FROM cases"
        params: tuple[Any, ...] = ()
        if status:
            query += " WHERE status=?"
            params = (status,)
        query += " ORDER BY study_uid, series_uid, source_sop_uid"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        return [ReviewCase(**dict(row)) for row in rows]

    def get_case(self, case_id: str) -> ReviewCase:
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
        if row is None:
            raise KeyError(case_id)
        return ReviewCase(**dict(row))

    def add_decision(self, decision: ReviewDecision) -> int:
        if decision.scope not in REVIEW_SCOPES:
            raise ValueError(f"Unsupported scope: {decision.scope}")
        if decision.status not in REVIEW_STATUSES:
            raise ValueError(f"Unsupported review status: {decision.status}")
        if not decision.reviewer.strip():
            raise ValueError("Reviewer is required")
        region = decision.region or (None, None, None, None)
        with closing(self._connect()) as connection:
            cursor = connection.execute(
                """INSERT INTO decisions
                (case_id, reviewer, scope, target, status, comment, frame_number, x1, y1, x2, y2, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    decision.case_id,
                    decision.reviewer.strip(),
                    decision.scope,
                    decision.target,
                    decision.status,
                    decision.comment,
                    decision.frame_number,
                    *region,
                    decision.created_at or _now(),
                ),
            )
            connection.execute(
                "UPDATE cases SET status=?, updated_at=? WHERE case_id=?",
                (
                    "needs_review" if decision.status == "needs_secondary_review" else "reviewed",
                    _now(),
                    decision.case_id,
                ),
            )
            connection.commit()
            if cursor.lastrowid is None:
                raise RuntimeError("Review decision insert did not return a row id")
            return int(cursor.lastrowid)

    def decisions(self, *, reviewer: str | None = None, case_id: str | None = None) -> list[ReviewDecision]:
        clauses: list[str] = []
        params: list[Any] = []
        if reviewer:
            clauses.append("reviewer=?")
            params.append(reviewer)
        if case_id:
            clauses.append("case_id=?")
            params.append(case_id)
        query = "SELECT * FROM decisions"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, decision_id"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        output: list[ReviewDecision] = []
        for row in rows:
            values = dict(row)
            region_values = tuple(values.pop(key) for key in ("x1", "y1", "x2", "y2"))
            values["region"] = None if all(item is None for item in region_values) else region_values
            output.append(ReviewDecision(**values))
        return output

    def summary(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            total = connection.execute("SELECT COUNT(*) FROM cases").fetchone()[0]
            status_rows = connection.execute(
                "SELECT status, COUNT(*) n FROM cases GROUP BY status"
            ).fetchall()
            decision_rows = connection.execute(
                "SELECT status, COUNT(*) n FROM decisions GROUP BY status"
            ).fetchall()
            reviewers = [
                row[0]
                for row in connection.execute("SELECT DISTINCT reviewer FROM decisions ORDER BY reviewer")
            ]
        return {
            "cases": total,
            "case_statuses": {row[0]: row[1] for row in status_rows},
            "decision_statuses": {row[0]: row[1] for row in decision_rows},
            "reviewers": reviewers,
        }

    def export(self, output: str | Path, *, disclose_paths: bool = False) -> Path:
        destination = Path(output)
        database_digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        decision_rows = [item.to_dict() for item in self.decisions()]
        payload = {
            "schema_version": "1.1",
            "exported_at": _now(),
            "database_sha256": database_digest,
            "session": self.session(disclose_paths=disclose_paths),
            "summary": self.summary(),
            "cases": [item.to_dict(disclose_paths=disclose_paths) for item in self.list_cases()],
            "decisions": decision_rows,
        }
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.suffix.lower() == ".csv":
            with destination.open("w", newline="", encoding="utf-8") as handle:
                fieldnames = list(ReviewDecision(None, "", "", "case", "", "not_reviewed").to_dict())
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(decision_rows)
        else:
            write_json(destination, payload, schema_name="review-export")
        _restrict_permissions(destination)
        return destination

    def integrity_check(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            quick = [str(row[0]) for row in connection.execute("PRAGMA quick_check").fetchall()]
            foreign_keys = [dict(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()]
        return {
            "database": str(self.path),
            "database_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
            "quick_check": quick,
            "foreign_key_violations": foreign_keys,
            "ok": quick == ["ok"] and not foreign_keys,
        }

    def disagreement_report(self, reviewer_a: str, reviewer_b: str) -> dict[str, Any]:
        a = _latest_decisions(self.decisions(reviewer=reviewer_a))
        b = _latest_decisions(self.decisions(reviewer=reviewer_b))
        rows: list[dict[str, Any]] = []
        counts = {"disagreement": 0, "unmatched_a": 0, "unmatched_b": 0}
        for key in sorted(set(a) | set(b), key=str):
            left = a.get(key)
            right = b.get(key)
            if left is not None and right is not None and left.status == right.status:
                continue
            if left is None:
                state = "unmatched_b"
            elif right is None:
                state = "unmatched_a"
            else:
                state = "disagreement"
            counts[state] += 1
            case_id, scope, target, frame_number, region = key
            rows.append(
                {
                    "case_id": case_id,
                    "scope": scope,
                    "target": target,
                    "frame_number": frame_number,
                    "region": list(region) if region is not None else None,
                    "state": state,
                    "reviewer_a_decision": left.to_dict() if left else None,
                    "reviewer_b_decision": right.to_dict() if right else None,
                }
            )
        return {
            "schema_version": "1.0",
            "generated_at": _now(),
            "reviewer_a": reviewer_a,
            "reviewer_b": reviewer_b,
            "summary": {**counts, "items_requiring_adjudication": len(rows)},
            "items": rows,
        }

    def export_disagreements(self, output: str | Path, reviewer_a: str, reviewer_b: str) -> Path:
        destination = write_json(
            output,
            self.disagreement_report(reviewer_a, reviewer_b),
            schema_name="review-disagreements",
        )
        _restrict_permissions(destination)
        return destination

    def agreement(self, reviewer_a: str, reviewer_b: str) -> AgreementReport:
        a = {key: item.status for key, item in _latest_decisions(self.decisions(reviewer=reviewer_a)).items()}
        b = {key: item.status for key, item in _latest_decisions(self.decisions(reviewer=reviewer_b)).items()}
        common = sorted(set(a) & set(b), key=str)
        labels = sorted(set(a.values()) | set(b.values()))
        confusion = {left: {right: 0 for right in labels} for left in labels}
        for key in common:
            confusion[a[key]][b[key]] += 1
        n = len(common)
        exact = sum(a[key] == b[key] for key in common) / n if n else None
        kappa: float | None = None
        if n:
            p_e = 0.0
            for label in labels:
                p_a = sum(a[key] == label for key in common) / n
                p_b = sum(b[key] == label for key in common) / n
                p_e += p_a * p_b
            if p_e < 1:
                kappa = ((exact or 0.0) - p_e) / (1 - p_e)
        return AgreementReport(
            reviewer_a=reviewer_a,
            reviewer_b=reviewer_b,
            labels=labels,
            matched_targets=n,
            exact_agreement=exact,
            cohen_kappa=kappa,
            confusion=confusion,
            unmatched_a=len(set(a) - set(b)),
            unmatched_b=len(set(b) - set(a)),
        )


def metadata_diff(source_path: str | Path, candidate_path: str | Path) -> list[dict[str, Any]]:
    source = pydicom.dcmread(source_path, stop_before_pixels=True)
    candidate = pydicom.dcmread(candidate_path, stop_before_pixels=True)

    def flatten(ds, prefix: str = "") -> dict[str, tuple[str, str, str]]:
        output: dict[str, tuple[str, str, str]] = {}
        for element in ds:
            keyword = element.keyword or str(element.tag)
            path = f"{prefix}.{keyword}" if prefix else keyword
            if element.VR == "SQ":
                for index, item in enumerate(element.value):
                    output.update(flatten(item, f"{path}[{index}]"))
            else:
                output[path] = (str(element.tag), element.VR, str(element.value))
        return output

    left = flatten(source)
    right = flatten(candidate)
    rows: list[dict[str, Any]] = []
    for path in sorted(set(left) | set(right)):
        left_value = left.get(path)
        right_value = right.get(path)
        if left_value == right_value:
            state = "unchanged"
        elif left_value is None:
            state = "added"
        elif right_value is None:
            state = "removed"
        else:
            state = "changed"
        rows.append(
            {
                "path": path,
                "tag": (left_value or right_value or ("", "", ""))[0],
                "vr": (left_value or right_value or ("", "", ""))[1],
                "source": left_value[2] if left_value else None,
                "candidate": right_value[2] if right_value else None,
                "state": state,
            }
        )
    return rows
