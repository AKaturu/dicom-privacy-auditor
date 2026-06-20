from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

CURRENT_SCHEMA_VERSION = 2


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def current_version(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
    ).fetchone()
    if row is None:
        return 0
    try:
        value = connection.execute("SELECT schema_version FROM sessions WHERE id=1").fetchone()
    except sqlite3.OperationalError:
        return 1
    return int(value[0]) if value else int(connection.execute("PRAGMA user_version").fetchone()[0] or 1)


def migrate_connection(connection: sqlite3.Connection) -> list[int]:
    version = current_version(connection)
    applied: list[int] = []
    if version == 0:
        return applied
    if version > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"Review database schema {version} is newer than supported schema {CURRENT_SCHEMA_VERSION}"
        )
    connection.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
        version INTEGER PRIMARY KEY,
        applied_at TEXT NOT NULL,
        description TEXT NOT NULL
        )"""
    )
    if version < 2:
        case_columns = _columns(connection, "cases")
        if "assigned_reviewer" not in case_columns:
            connection.execute("ALTER TABLE cases ADD COLUMN assigned_reviewer TEXT")
        if "priority" not in case_columns:
            connection.execute("ALTER TABLE cases ADD COLUMN priority INTEGER NOT NULL DEFAULT 0")
        if "updated_at" not in case_columns:
            connection.execute("ALTER TABLE cases ADD COLUMN updated_at TEXT")
        connection.execute(
            "UPDATE cases SET updated_at=COALESCE(updated_at, ?) WHERE updated_at IS NULL", (_now(),)
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_cases_assignment ON cases(assigned_reviewer, priority DESC, status)"
        )
        connection.execute("UPDATE sessions SET schema_version=2 WHERE id=1")
        connection.execute("PRAGMA user_version=2")
        connection.execute(
            "INSERT OR REPLACE INTO schema_migrations(version, applied_at, description) VALUES (2, ?, ?)",
            (_now(), "Add reviewer assignment, priority, timestamps, and migration ledger"),
        )
        applied.append(2)
    connection.commit()
    return applied


def migrate_database(path: str | Path, *, backup: bool = True) -> dict[str, object]:
    database = Path(path)
    if not database.is_file():
        raise FileNotFoundError(database)
    backup_path: Path | None = None
    if backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_path = database.with_suffix(database.suffix + f".bak-{stamp}")
        shutil.copy2(database, backup_path)
    connection = sqlite3.connect(database)
    try:
        before = current_version(connection)
        applied = migrate_connection(connection)
        after = current_version(connection)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return {
        "database": str(database),
        "before": before,
        "after": after,
        "applied": applied,
        "backup": str(backup_path) if backup_path else None,
    }
