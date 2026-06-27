"""SQLite access layer. All database connections and schema setup live here.

Route handlers must never run SQL directly — they call helpers in this module (and the
recommender package). Connections enable foreign keys and return dict-like rows.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .config import settings

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_db() -> sqlite3.Connection:
    """Open a connection with foreign keys enabled and Row access by column name.

    Caller is responsible for closing (use as a context manager or call .close()).
    """
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create all tables from schema.sql and seed a default profile if none exist."""
    settings.ensure_dirs()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_db()
    try:
        conn.executescript(schema)
        # Seed a default profile so the app is usable immediately.
        existing = conn.execute("SELECT COUNT(*) AS n FROM profiles").fetchone()["n"]
        if existing == 0:
            conn.execute(
                "INSERT INTO profiles (name, avatar_color) VALUES (?, ?)",
                ("Me", "#e50914"),
            )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":  # `python -m backend.db` initializes the database.
    init_db()
    print(f"Initialized database at {settings.db_path}")
