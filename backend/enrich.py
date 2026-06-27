"""Match scanned library items to TMDB and cache their metadata + images.

Run after a scan. For every movie/show still marked 'pending', search TMDB, write the
real title/overview/genres/etc. back to SQLite, download poster + backdrop to
`data/images/`, and flag the row 'matched' or 'unmatched'. Idempotent and best-effort:
a single failed title never aborts the run, and missing images don't fail a match.

All TMDB calls go through `backend.tmdb` (per CLAUDE.md).
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from . import db, tmdb
from .config import settings

logger = logging.getLogger(__name__)


def _image_filename(tmdb_path: str, size: str) -> str:
    """Disk filename for a cached image, namespaced by size (e.g. w342_abc.jpg).

    Both separators are collapsed so the result is always a single flat filename — a
    second line of defense against path traversal beyond the route's input validation.
    """
    stem = tmdb_path.strip("/\\").replace("/", "_").replace("\\", "_")
    return f"{size}_{stem}"


def cached_image_path(tmdb_path: str, size: str) -> Path:
    """Where a given TMDB image is cached on disk (may not exist yet)."""
    return settings.images_dir / _image_filename(tmdb_path, size)


async def ensure_image_cached(tmdb_path: str, size: str = "w342") -> Path | None:
    """Download a TMDB image to disk if not already cached. Returns its path or None."""
    if not tmdb_path:
        return None
    dest = cached_image_path(tmdb_path, size)
    # Containment guard: the resolved path must stay inside the images dir.
    images_dir = settings.images_dir.resolve()
    if not dest.resolve().is_relative_to(images_dir):
        return None
    if dest.exists():
        return dest
    try:
        settings.ensure_dirs()
        data = await tmdb.get_image(tmdb_path, size)
        dest.write_bytes(data)
        return dest
    except Exception:  # images are best-effort; a miss just means a UI placeholder
        logger.warning("image cache failed for %s (%s)", tmdb_path, size, exc_info=True)
        return None


def _movie_meta(parsed_year: int | None, details: dict) -> dict:
    """Map a TMDB movie-details payload to our movies columns."""
    release = details.get("release_date") or ""
    credits = details.get("credits") or {}
    keywords = (details.get("keywords") or {}).get("keywords") or []
    return {
        "tmdb_id": details.get("id"),
        "title": details.get("title"),
        "year": int(release[:4]) if release[:4].isdigit() else parsed_year,
        "overview": details.get("overview"),
        "poster_path": details.get("poster_path"),
        "backdrop_path": details.get("backdrop_path"),
        "rating": details.get("vote_average"),
        "runtime": details.get("runtime"),
        "genres": json.dumps([g["name"] for g in details.get("genres", [])]),
        "cast": json.dumps([c["name"] for c in (credits.get("cast") or [])[:10]]),
        "keywords": json.dumps([k["name"] for k in keywords]),
    }


def _show_meta(parsed_year: int | None, details: dict) -> dict:
    """Map a TMDB tv-details payload to our shows columns."""
    first_air = details.get("first_air_date") or ""
    keywords = (details.get("keywords") or {}).get("results") or []
    return {
        "tmdb_id": details.get("id"),
        "title": details.get("name"),
        "year": int(first_air[:4]) if first_air[:4].isdigit() else parsed_year,
        "overview": details.get("overview"),
        "poster_path": details.get("poster_path"),
        "backdrop_path": details.get("backdrop_path"),
        "rating": details.get("vote_average"),
        "genres": json.dumps([g["name"] for g in details.get("genres", [])]),
        "keywords": json.dumps([k["name"] for k in keywords]),
    }


async def _cache_meta_images(meta: dict) -> None:
    await ensure_image_cached(meta.get("poster_path") or "", "w342")
    await ensure_image_cached(meta.get("backdrop_path") or "", "w780")


async def enrich_movie(
    conn: sqlite3.Connection, movie_id: int, parsed_title: str, year: int | None
) -> bool:
    """Match one movie to TMDB and persist. Returns True if matched."""
    hit = await tmdb.search_movie(parsed_title, year)
    if not hit:
        db.mark_movie_unmatched(conn, movie_id)
        return False
    details = await tmdb.movie_details(hit["id"])
    meta = _movie_meta(year, details)
    db.update_movie_metadata(conn, movie_id, meta)
    await _cache_meta_images(meta)
    return True


async def enrich_show(
    conn: sqlite3.Connection, show_id: int, parsed_title: str, year: int | None
) -> bool:
    """Match one show to TMDB and persist. Returns True if matched."""
    hit = await tmdb.search_tv(parsed_title, year)
    if not hit:
        db.mark_show_unmatched(conn, show_id)
        return False
    details = await tmdb.tv_details(hit["id"])
    meta = _show_meta(year, details)
    db.update_show_metadata(conn, show_id, meta)
    await _cache_meta_images(meta)
    return True


async def movie_match_candidates(query: str, year: int | None = None) -> list[dict]:
    """Trimmed TMDB movie search results for the manual fix-match picker."""
    results = await tmdb.search_movies(query, year)
    return [
        {
            "tmdb_id": r.get("id"),
            "title": r.get("title"),
            "year": (r.get("release_date") or "")[:4] or None,
            "overview": r.get("overview"),
            "poster_path": r.get("poster_path"),
        }
        for r in results
    ]


async def match_movie_manual(movie_id: int, tmdb_id: int) -> dict:
    """Force a movie to a specific TMDB id (user override). Returns the new metadata."""
    details = await tmdb.movie_details(tmdb_id)
    conn = db.get_db()
    try:
        movie = db.get_movie(conn, movie_id)
        if movie is None:
            raise ValueError(f"movie {movie_id} not found")
        meta = _movie_meta(movie["year"], details)
        db.update_movie_metadata(conn, movie_id, meta)
        conn.commit()
    finally:
        conn.close()
    await _cache_meta_images(meta)
    return meta


async def enrich_library() -> dict:
    """Enrich every pending movie and show. Returns counts of what changed."""
    counts = {
        "movies_matched": 0,
        "movies_unmatched": 0,
        "shows_matched": 0,
        "shows_unmatched": 0,
        "errors": [],
    }
    conn = db.get_db()
    try:
        for row in db.get_pending_movies(conn):
            try:
                ok = await enrich_movie(
                    conn, row["id"], row["parsed_title"], row["year"]
                )
                counts["movies_matched" if ok else "movies_unmatched"] += 1
            except Exception as exc:
                counts["errors"].append(f"movie {row['parsed_title']!r}: {exc}")
            conn.commit()

        for row in db.get_pending_shows(conn):
            try:
                ok = await enrich_show(
                    conn, row["id"], row["parsed_title"], row["year"]
                )
                counts["shows_matched" if ok else "shows_unmatched"] += 1
            except Exception as exc:
                counts["errors"].append(f"show {row['parsed_title']!r}: {exc}")
            conn.commit()
    finally:
        conn.close()
    return counts
