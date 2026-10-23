"""Local SQLite store for everything the tool learns from use.

SQLite because it needs no server, lives in a single file next to the
application and never leaves the machine — the same constraint that shapes the
rest of the pipeline.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DEFAULT_PATH = Path("var/learning.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS professionals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    council TEXT NOT NULL DEFAULT 'CRM',
    council_number TEXT NOT NULL,
    council_state TEXT,
    full_name TEXT NOT NULL,
    normalised_name TEXT NOT NULL,
    specialty TEXT,
    operator_code TEXT,
    source TEXT NOT NULL,
    confirmations INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (council, council_number, council_state)
);

CREATE INDEX IF NOT EXISTS idx_professionals_name ON professionals (normalised_name);

CREATE TABLE IF NOT EXISTS field_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    extraction_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    outcome TEXT NOT NULL,
    value_read TEXT,
    value_final TEXT,
    source TEXT,
    confidence REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_field_events_field ON field_events (field_name, outcome);
"""


MIGRATIONS = {
    "professionals": {"operator_code": "ALTER TABLE professionals ADD COLUMN operator_code TEXT"},
}


def _migrate(connection: sqlite3.Connection) -> None:
    """Adds columns introduced after a database was first created."""
    for table, columns in MIGRATIONS.items():
        existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
        for column, statement in columns.items():
            if column not in existing:
                connection.execute(statement)


def connect(path: Path = DEFAULT_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    _migrate(connection)
    return connection


@contextmanager
def session(path: Path = DEFAULT_PATH) -> Iterator[sqlite3.Connection]:
    connection = connect(path)
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()
