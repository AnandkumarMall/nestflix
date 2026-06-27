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


# ---------------------------------------------------------------------------
# Library upserts (used by the scanner) and reads (used by the library route).
# All idempotent: re-running the scanner must not create duplicate rows.
# ---------------------------------------------------------------------------


def upsert_media_file(
    conn: sqlite3.Connection,
    path: str,
    size: int,
    mtime: float,
    container: str,
    kind: str,
) -> int:
    """Insert or update a media file by its unique path. Returns the row id."""
    conn.execute(
        """
        INSERT INTO media_files (path, size, mtime, container, kind)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            size = excluded.size,
            mtime = excluded.mtime,
            container = excluded.container,
            kind = excluded.kind
        """,
        (path, size, mtime, container, kind),
    )
    row = conn.execute("SELECT id FROM media_files WHERE path = ?", (path,)).fetchone()
    return row["id"]


def upsert_movie(
    conn: sqlite3.Connection, media_file_id: int, parsed_title: str, year: int | None
) -> int:
    """Insert or update the movie backed by a media file. Returns the movie id."""
    conn.execute(
        """
        INSERT INTO movies (media_file_id, parsed_title, year)
        VALUES (?, ?, ?)
        ON CONFLICT(media_file_id) DO UPDATE SET
            parsed_title = excluded.parsed_title,
            year = excluded.year
        """,
        (media_file_id, parsed_title, year),
    )
    row = conn.execute(
        "SELECT id FROM movies WHERE media_file_id = ?", (media_file_id,)
    ).fetchone()
    return row["id"]


def upsert_show(conn: sqlite3.Connection, parsed_title: str) -> int:
    """Insert or fetch a show by its parsed title. Returns the show id."""
    conn.execute(
        "INSERT INTO shows (parsed_title) VALUES (?) ON CONFLICT(parsed_title) DO NOTHING",
        (parsed_title,),
    )
    row = conn.execute(
        "SELECT id FROM shows WHERE parsed_title = ?", (parsed_title,)
    ).fetchone()
    return row["id"]


def upsert_episode(
    conn: sqlite3.Connection,
    show_id: int,
    media_file_id: int,
    season: int,
    episode: int,
) -> int:
    """Insert or update an episode keyed by (show, season, episode). Returns its id."""
    conn.execute(
        """
        INSERT INTO episodes (show_id, media_file_id, season, episode)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(show_id, season, episode) DO UPDATE SET
            media_file_id = excluded.media_file_id
        """,
        (show_id, media_file_id, season, episode),
    )
    row = conn.execute(
        "SELECT id FROM episodes WHERE show_id = ? AND season = ? AND episode = ?",
        (show_id, season, episode),
    ).fetchone()
    return row["id"]


def get_library() -> dict:
    """Return all movies and shows (with episodes grouped by season) as plain dicts."""
    conn = get_db()
    try:
        movies = [dict(r) for r in conn.execute("""
                SELECT m.id, m.tmdb_id, m.parsed_title, m.title, m.year, m.overview,
                       m.poster_path, m.backdrop_path, m.rating, m.runtime, m.genres,
                       m.match_status, f.path, f.container
                FROM movies m
                JOIN media_files f ON f.id = m.media_file_id
                ORDER BY COALESCE(m.title, m.parsed_title)
                """).fetchall()]

        shows = []
        for show in conn.execute("""
            SELECT id, tmdb_id, parsed_title, title, year, overview, poster_path,
                   backdrop_path, rating, genres, match_status
            FROM shows
            ORDER BY COALESCE(title, parsed_title)
            """).fetchall():
            episodes = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT e.id, e.season, e.episode, e.title, e.overview, e.still_path,
                           f.path, f.container
                    FROM episodes e
                    JOIN media_files f ON f.id = e.media_file_id
                    WHERE e.show_id = ?
                    ORDER BY e.season, e.episode
                    """,
                    (show["id"],),
                ).fetchall()
            ]
            show_dict = dict(show)
            show_dict["episodes"] = episodes
            shows.append(show_dict)

        return {"movies": movies, "shows": shows}
    finally:
        conn.close()


if __name__ == "__main__":  # `python -m backend.db` initializes the database.
    init_db()
    print(f"Initialized database at {settings.db_path}")
