"""SQLite connection handling and schema migrations."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

MIGRATIONS_PACKAGE = "partsdb.db.migrations"


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    """Open a database with foreign keys enforced and rows addressable by column name."""
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def schema_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def _migrations() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for entry in resources.files(MIGRATIONS_PACKAGE).iterdir():
        name = entry.name
        if name.endswith(".sql") and name[:4].isdigit():
            found.append((int(name[:4]), entry.read_text(encoding="utf-8")))
    return sorted(found)


def latest_version() -> int:
    migrations = _migrations()
    return migrations[-1][0] if migrations else 0


def migrate(conn: sqlite3.Connection) -> int:
    """Apply any pending migrations, each in its own transaction. Returns the new version."""
    current = schema_version(conn)
    for version, script in _migrations():
        if version <= current:
            continue
        try:
            conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {version};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.rollback()
            raise
        current = version
    return current
