"""SQLite access layer. All database connections and schema setup live here.

Route handlers must never run SQL directly — they call helpers in this module (and the
recommender package). Connections enable foreign keys and return dict-like rows.
"""

from __future__ import annotations

import json
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
    row = conn.execute("SELECT id FROM movies WHERE media_file_id = ?", (media_file_id,)).fetchone()
    return row["id"]


def upsert_show(conn: sqlite3.Connection, parsed_title: str) -> int:
    """Insert or fetch a show by its parsed title. Returns the show id."""
    conn.execute(
        "INSERT INTO shows (parsed_title) VALUES (?) ON CONFLICT(parsed_title) DO NOTHING",
        (parsed_title,),
    )
    row = conn.execute("SELECT id FROM shows WHERE parsed_title = ?", (parsed_title,)).fetchone()
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
        movies = [
            dict(r)
            for r in conn.execute("""
                SELECT m.id, m.tmdb_id, m.parsed_title, m.title, m.year, m.overview,
                       m.poster_path, m.backdrop_path, m.rating, m.runtime, m.genres,
                       m.match_status, f.id AS media_file_id, f.path, f.container
                FROM movies m
                JOIN media_files f ON f.id = m.media_file_id
                ORDER BY COALESCE(m.title, m.parsed_title)
                """).fetchall()
        ]

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
                           f.id AS media_file_id, f.path, f.container
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


# ---------------------------------------------------------------------------
# Profiles (used by the profiles route).
# ---------------------------------------------------------------------------


def list_profiles() -> list[dict]:
    """Return all profiles, oldest first."""
    conn = get_db()
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT id, name, avatar_color, created_at FROM profiles ORDER BY id"
            ).fetchall()
        ]
    finally:
        conn.close()


def create_profile(name: str, avatar_color: str) -> dict:
    """Insert a profile and return it."""
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO profiles (name, avatar_color) VALUES (?, ?)",
            (name, avatar_color),
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": name, "avatar_color": avatar_color}
    finally:
        conn.close()


def delete_profile(profile_id: int) -> bool:
    """Delete a profile (history cascades). Returns False if it didn't exist."""
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# TMDB response cache (used only by backend.tmdb).
# ---------------------------------------------------------------------------


def tmdb_cache_get(cache_key: str, max_age_hours: float | None = None) -> dict | None:
    """Return a cached TMDB response (parsed) or None if missing/stale.

    `max_age_hours=None` ignores age (cache forever); a number treats entries older
    than that as a miss so callers re-fetch slowly-changing data like trending.
    """
    conn = get_db()
    try:
        if max_age_hours is None:
            row = conn.execute(
                "SELECT response FROM tmdb_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT response FROM tmdb_cache
                WHERE cache_key = ?
                  AND fetched_at >= datetime('now', ?)
                """,
                (cache_key, f"-{max_age_hours} hours"),
            ).fetchone()
        return json.loads(row["response"]) if row else None
    finally:
        conn.close()


def tmdb_cache_put(cache_key: str, response: dict) -> None:
    """Store (or refresh) a raw TMDB response under `cache_key`."""
    conn = get_db()
    try:
        conn.execute(
            """
            INSERT INTO tmdb_cache (cache_key, response, fetched_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(cache_key) DO UPDATE SET
                response = excluded.response,
                fetched_at = excluded.fetched_at
            """,
            (cache_key, json.dumps(response, separators=(",", ":"))),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Enrichment reads/writes (used by backend.enrich).
# ---------------------------------------------------------------------------


def get_pending_movies(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Movies that still need a TMDB match (match_status = 'pending')."""
    return conn.execute(
        "SELECT id, parsed_title, year FROM movies WHERE match_status = 'pending'"
    ).fetchall()


def get_pending_shows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Shows that still need a TMDB match."""
    return conn.execute(
        "SELECT id, parsed_title, year FROM shows WHERE match_status = 'pending'"
    ).fetchall()


def update_movie_metadata(conn: sqlite3.Connection, movie_id: int, meta: dict) -> None:
    """Write TMDB-derived fields onto a movie and mark it matched."""
    conn.execute(
        """
        UPDATE movies SET
            tmdb_id = :tmdb_id, title = :title, year = :year, overview = :overview,
            poster_path = :poster_path, backdrop_path = :backdrop_path,
            rating = :rating, runtime = :runtime, genres = :genres,
            cast = :cast, keywords = :keywords, match_status = 'matched'
        WHERE id = :id
        """,
        {**meta, "id": movie_id},
    )


def update_show_metadata(conn: sqlite3.Connection, show_id: int, meta: dict) -> None:
    """Write TMDB-derived fields onto a show and mark it matched."""
    conn.execute(
        """
        UPDATE shows SET
            tmdb_id = :tmdb_id, title = :title, year = :year, overview = :overview,
            poster_path = :poster_path, backdrop_path = :backdrop_path,
            rating = :rating, genres = :genres, keywords = :keywords,
            match_status = 'matched'
        WHERE id = :id
        """,
        {**meta, "id": show_id},
    )


def mark_movie_unmatched(conn: sqlite3.Connection, movie_id: int) -> None:
    """Flag a movie as having no TMDB match (kept browsable, fixable later)."""
    conn.execute("UPDATE movies SET match_status = 'unmatched' WHERE id = ?", (movie_id,))


def mark_show_unmatched(conn: sqlite3.Connection, show_id: int) -> None:
    """Flag a show as having no TMDB match (kept browsable, fixable later)."""
    conn.execute("UPDATE shows SET match_status = 'unmatched' WHERE id = ?", (show_id,))


def get_movie(conn: sqlite3.Connection, movie_id: int) -> sqlite3.Row | None:
    """Fetch a single movie row by id (used by the manual fix-match path)."""
    return conn.execute(
        "SELECT id, parsed_title, year FROM movies WHERE id = ?", (movie_id,)
    ).fetchone()


# ---------------------------------------------------------------------------
# Playback: stream resolution, resume progress, and Continue Watching.
# ---------------------------------------------------------------------------


def get_media_file(conn: sqlite3.Connection, media_file_id: int) -> sqlite3.Row | None:
    """Fetch a media file row (path/container/kind) for streaming."""
    return conn.execute(
        "SELECT id, path, container, kind, size FROM media_files WHERE id = ?",
        (media_file_id,),
    ).fetchone()


def get_media_display(conn: sqlite3.Connection, media_file_id: int) -> dict | None:
    """Title/artwork for a media file (movie or episode), for the player header + rows."""
    movie = conn.execute(
        """
        SELECT title, parsed_title, year, poster_path, backdrop_path
        FROM movies WHERE media_file_id = ?
        """,
        (media_file_id,),
    ).fetchone()
    if movie is not None:
        return {
            "kind": "movie",
            "title": movie["title"] or movie["parsed_title"],
            "year": movie["year"],
            "poster_path": movie["poster_path"],
            "backdrop_path": movie["backdrop_path"],
        }

    episode = conn.execute(
        """
        SELECT e.season, e.episode, e.title AS episode_title, e.still_path,
               s.title AS show_title, s.parsed_title, s.poster_path, s.backdrop_path
        FROM episodes e
        JOIN shows s ON s.id = e.show_id
        WHERE e.media_file_id = ?
        """,
        (media_file_id,),
    ).fetchone()
    if episode is not None:
        return {
            "kind": "episode",
            "title": episode["show_title"] or episode["parsed_title"],
            "season": episode["season"],
            "episode": episode["episode"],
            "episode_title": episode["episode_title"],
            "poster_path": episode["poster_path"],
            "backdrop_path": episode["backdrop_path"],
            "still_path": episode["still_path"],
        }
    return None


def get_watch_progress(
    conn: sqlite3.Connection, profile_id: int, media_file_id: int
) -> sqlite3.Row | None:
    """Resume position for one (profile, media file), or None if never watched."""
    return conn.execute(
        """
        SELECT position_seconds, duration_seconds, completed
        FROM watch_progress
        WHERE profile_id = ? AND media_file_id = ?
        """,
        (profile_id, media_file_id),
    ).fetchone()


def upsert_watch_progress(
    conn: sqlite3.Connection,
    profile_id: int,
    media_file_id: int,
    position_seconds: float,
    duration_seconds: float,
    completed: bool,
) -> None:
    """Insert or update the resume position for a (profile, media file)."""
    conn.execute(
        """
        INSERT INTO watch_progress
            (profile_id, media_file_id, position_seconds, duration_seconds, completed,
             updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(profile_id, media_file_id) DO UPDATE SET
            position_seconds = excluded.position_seconds,
            duration_seconds = excluded.duration_seconds,
            completed = excluded.completed,
            updated_at = excluded.updated_at
        """,
        (
            profile_id,
            media_file_id,
            position_seconds,
            duration_seconds,
            int(completed),
        ),
    )


def record_watch_event(
    conn: sqlite3.Connection,
    profile_id: int,
    media_file_id: int,
    event: str,
    pct: float,
) -> None:
    """Append a behavioral event (start/progress/finish/abandon) for the taste model."""
    conn.execute(
        """
        INSERT INTO watch_events (profile_id, media_file_id, event, pct)
        VALUES (?, ?, ?, ?)
        """,
        (profile_id, media_file_id, event, pct),
    )


def get_continue_watching(conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    """In-progress (not completed) titles for the Continue Watching row, newest first."""
    rows = conn.execute(
        """
        SELECT wp.media_file_id, wp.position_seconds, wp.duration_seconds, wp.updated_at
        FROM watch_progress wp
        WHERE wp.profile_id = ? AND wp.completed = 0 AND wp.position_seconds > 0
        ORDER BY wp.updated_at DESC
        """,
        (profile_id,),
    ).fetchall()
    items: list[dict] = []
    for row in rows:
        display = get_media_display(conn, row["media_file_id"])
        if display is None:
            continue  # file removed since last watch — skip gracefully
        items.append(
            {
                "media_file_id": row["media_file_id"],
                "position_seconds": row["position_seconds"],
                "duration_seconds": row["duration_seconds"],
                **display,
            }
        )
    return items


# ---------------------------------------------------------------------------
# Recommender reads (used by backend.recommender). All SQL stays here; the
# recommender package consumes plain dicts and does the math.
# ---------------------------------------------------------------------------


def _json_list(raw: str | None) -> list[str]:
    """Parse a JSON-array column (genres/keywords/cast) into a list of strings.

    Tolerates NULL and malformed JSON (returns []) so a bad row can't break ranking.
    """
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [str(v) for v in value] if isinstance(value, list) else []


def get_titles_for_features(conn: sqlite3.Connection) -> list[dict]:
    """Every movie + show with the metadata the recommender turns into feature vectors.

    A "title" is the unit we recommend: a movie (one media file) or a show (its episode
    media files grouped). Shows have no cast/runtime in TMDB show details, so those
    default to empty/None. ``media_file_ids`` lets the caller map watch events back to a
    title; ``primary_media_file_id`` is what a "Play" link should target.
    """
    titles: list[dict] = []

    for r in conn.execute("""
        SELECT m.id, m.title, m.parsed_title, m.year, m.rating, m.runtime,
               m.genres, m.keywords, m.cast, m.poster_path, m.backdrop_path,
               m.media_file_id
        FROM movies m
        WHERE m.match_status != 'unmatched' OR m.poster_path IS NOT NULL
        """).fetchall():
        titles.append(
            {
                "kind": "movie",
                "id": r["id"],
                "title": r["title"] or r["parsed_title"],
                "year": r["year"],
                "rating": r["rating"],
                "runtime": r["runtime"],
                "genres": _json_list(r["genres"]),
                "keywords": _json_list(r["keywords"]),
                "cast": _json_list(r["cast"]),
                "poster_path": r["poster_path"],
                "backdrop_path": r["backdrop_path"],
                "media_file_ids": [r["media_file_id"]],
                "primary_media_file_id": r["media_file_id"],
            }
        )

    for s in conn.execute("""
        SELECT id, title, parsed_title, year, rating, genres, keywords,
               poster_path, backdrop_path
        FROM shows
        WHERE match_status != 'unmatched' OR poster_path IS NOT NULL
        """).fetchall():
        episodes = conn.execute(
            "SELECT media_file_id FROM episodes WHERE show_id = ? ORDER BY season, episode",
            (s["id"],),
        ).fetchall()
        media_ids = [e["media_file_id"] for e in episodes]
        titles.append(
            {
                "kind": "show",
                "id": s["id"],
                "title": s["title"] or s["parsed_title"],
                "year": s["year"],
                "rating": s["rating"],
                "runtime": None,
                "genres": _json_list(s["genres"]),
                "keywords": _json_list(s["keywords"]),
                "cast": [],
                "poster_path": s["poster_path"],
                "backdrop_path": s["backdrop_path"],
                "media_file_ids": media_ids,
                "primary_media_file_id": media_ids[0] if media_ids else None,
            }
        )

    return titles


def get_watch_history(conn: sqlite3.Connection, profile_id: int) -> list[dict]:
    """Per watched media file: completion + behavioral signals, newest first.

    Combines ``watch_progress`` (resume position / completed flag) with ``watch_events``
    (finish / abandon counts). Returns one row per media file; mapping those to titles and
    deriving recency/taste weights is done in the recommender (``rows.home_rows``), not
    here.
    """
    rows = conn.execute(
        """
        SELECT
            wp.media_file_id,
            wp.completed,
            CASE WHEN wp.duration_seconds > 0
                 THEN wp.position_seconds / wp.duration_seconds ELSE 0 END AS pct,
            wp.updated_at,
            COALESCE(SUM(CASE WHEN we.event = 'finish'  THEN 1 ELSE 0 END), 0) AS finishes,
            COALESCE(SUM(CASE WHEN we.event = 'abandon' THEN 1 ELSE 0 END), 0) AS abandons
        FROM watch_progress wp
        LEFT JOIN watch_events we
               ON we.media_file_id = wp.media_file_id
              AND we.profile_id = wp.profile_id
        WHERE wp.profile_id = ?
        GROUP BY wp.media_file_id
        ORDER BY wp.updated_at DESC
        """,
        (profile_id,),
    ).fetchall()
    return [
        {
            "media_file_id": r["media_file_id"],
            "completed": bool(r["completed"]),
            "pct": float(r["pct"] or 0.0),
            "updated_at": r["updated_at"],
            "finishes": r["finishes"],
            "abandons": r["abandons"],
        }
        for r in rows
    ]


def get_completed_count(conn: sqlite3.Connection, profile_id: int) -> int:
    """How many titles this profile has finished — drives the model-activation threshold."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM watch_progress WHERE profile_id = ? AND completed = 1",
        (profile_id,),
    ).fetchone()
    return int(row["n"])


def get_finished_media_ids(conn: sqlite3.Connection, profile_id: int) -> set[int]:
    """Media file ids the profile has finished — excluded from recommendation rows."""
    rows = conn.execute(
        "SELECT media_file_id FROM watch_progress WHERE profile_id = ? AND completed = 1",
        (profile_id,),
    ).fetchall()
    return {r["media_file_id"] for r in rows}


def get_ratings(conn: sqlite3.Connection, profile_id: int) -> dict[tuple[str, int], int]:
    """Explicit thumbs signals keyed by ('movie'|'show', id) → value (+1 / -1)."""
    rows = conn.execute(
        "SELECT movie_id, show_id, value FROM ratings WHERE profile_id = ?",
        (profile_id,),
    ).fetchall()
    out: dict[tuple[str, int], int] = {}
    for r in rows:
        if r["movie_id"] is not None:
            out[("movie", r["movie_id"])] = r["value"]
        elif r["show_id"] is not None:
            out[("show", r["show_id"])] = r["value"]
    return out


def upsert_rating(
    conn: sqlite3.Connection,
    profile_id: int,
    *,
    movie_id: int | None = None,
    show_id: int | None = None,
    value: int,
) -> None:
    """Record a thumbs up/down for a movie or show, replacing any prior value.

    Exactly one of ``movie_id`` / ``show_id`` must be set. Done as delete-then-insert
    because the nullable target columns can't be covered by a single UNIQUE constraint.
    """
    if (movie_id is None) == (show_id is None):
        raise ValueError("exactly one of movie_id / show_id must be set")
    if movie_id is not None:
        conn.execute(
            "DELETE FROM ratings WHERE profile_id = ? AND movie_id = ?",
            (profile_id, movie_id),
        )
    else:
        conn.execute(
            "DELETE FROM ratings WHERE profile_id = ? AND show_id = ?",
            (profile_id, show_id),
        )
    conn.execute(
        "INSERT INTO ratings (profile_id, movie_id, show_id, value) VALUES (?, ?, ?, ?)",
        (profile_id, movie_id, show_id, value),
    )


def get_profile_stats(
    conn: sqlite3.Connection, profile_id: int, *, top_genres: int = 8, recent: int = 10
) -> dict:
    """Viewing summary for the Stats page: totals, thumbs, top genres, recent finishes.

    All derived from existing tables (``watch_progress`` / ``ratings`` + title metadata) —
    no new storage. A profile with no history returns zeroed totals and empty lists.
    """
    finished = conn.execute(
        "SELECT COUNT(*) AS n FROM watch_progress WHERE profile_id = ? AND completed = 1",
        (profile_id,),
    ).fetchone()["n"]
    seconds = conn.execute(
        "SELECT COALESCE(SUM(position_seconds), 0) AS s FROM watch_progress WHERE profile_id = ?",
        (profile_id,),
    ).fetchone()["s"]
    rating_row = conn.execute(
        """
        SELECT COALESCE(SUM(value = 1), 0)  AS up,
               COALESCE(SUM(value = -1), 0) AS down
        FROM ratings WHERE profile_id = ?
        """,
        (profile_id,),
    ).fetchone()

    # Finished titles (movies + episodes→shows), newest first, with genres for tallying.
    rows = conn.execute(
        """
        SELECT 'movie' AS kind, m.id AS id, m.title AS title, m.parsed_title AS parsed,
               m.poster_path AS poster, m.genres AS genres, wp.updated_at AS updated_at
        FROM watch_progress wp
        JOIN movies m ON m.media_file_id = wp.media_file_id
        WHERE wp.profile_id = ? AND wp.completed = 1
        UNION ALL
        SELECT 'show', s.id, s.title, s.parsed_title, s.poster_path, s.genres, wp.updated_at
        FROM watch_progress wp
        JOIN episodes e ON e.media_file_id = wp.media_file_id
        JOIN shows s ON s.id = e.show_id
        WHERE wp.profile_id = ? AND wp.completed = 1
        ORDER BY updated_at DESC
        """,
        (profile_id, profile_id),
    ).fetchall()

    genre_counts: dict[str, int] = {}
    recently_finished: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for r in rows:
        for g in _json_list(r["genres"]):
            genre_counts[g] = genre_counts.get(g, 0) + 1
        key = (r["kind"], r["id"])
        if key not in seen and len(recently_finished) < recent:
            seen.add(key)
            recently_finished.append(
                {
                    "kind": r["kind"],
                    "id": r["id"],
                    "title": r["title"] or r["parsed"],
                    "poster_path": r["poster"],
                }
            )

    top = sorted(genre_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top_genres]
    return {
        "titles_finished": int(finished),
        "seconds_watched": float(seconds),
        "ratings": {"up": int(rating_row["up"]), "down": int(rating_row["down"])},
        "top_genres": [{"name": name, "count": count} for name, count in top],
        "recently_finished": recently_finished,
    }


if __name__ == "__main__":  # `python -m backend.db` initializes the database.
    init_db()
    print(f"Initialized database at {settings.db_path}")
