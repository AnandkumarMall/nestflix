"""Fetch TMDB recommendations for watched titles (external discovery).

This module supplements local recommendations with TMDB similar/recommendations
to help users discover titles not yet in their library.
"""

from __future__ import annotations

from typing import Any

from .. import db, tmdb


async def external_rows(profile_id: int, local_ids: set[int]) -> list[dict]:
    """TMDB-based discovery rows for a profile.

    Fetches similar titles from TMDB for the user's 2 most-recent watched items,
    filters to titles NOT in the local library, and returns "Discover Movies Like X" rows.

    Args:
        profile_id: Profile ID
        local_ids: Set of local movie/show IDs already in library (to filter out)

    Returns:
        List of discovery rows (empty if no TMDB data or all results in library)
    """
    conn = db.get_db()
    try:
        # Get 2 most-recent watched titles with TMDB IDs.
        history = conn.execute(
            """
            SELECT DISTINCT t.kind, t.id, t.tmdb_id, t.title, w.updated_at
            FROM watch_progress w
            JOIN media_files f ON f.id = w.media_file_id
            JOIN (
                SELECT 'movie' as kind, id, tmdb_id, title, media_file_id
                FROM movies WHERE tmdb_id IS NOT NULL
                UNION ALL
                SELECT 'show', s.id, s.tmdb_id, s.title, e.media_file_id
                FROM shows s JOIN episodes e ON e.show_id = s.id WHERE s.tmdb_id IS NOT NULL
            ) t ON t.media_file_id = w.media_file_id
            WHERE w.profile_id = ?
            ORDER BY w.updated_at DESC
            LIMIT 2
            """,
            (profile_id,),
        ).fetchall()
    finally:
        conn.close()

    if not history:
        return []

    rows = []
    for h in history:
        kind = h["kind"]
        tmdb_id = h["tmdb_id"]
        title = h["title"]

        try:
            # Fetch similar from TMDB.
            similar = await tmdb.recommendations(kind, tmdb_id)
        except tmdb.TMDBError:
            continue

        # Filter to titles NOT in local library.
        external_items = [
            {
                "tmdb_id": s.get("id"),
                "title": s.get("title") or s.get("name"),
                "poster_path": s.get("poster_path"),
                "backdrop_path": s.get("backdrop_path"),
                "in_library": False,
            }
            for s in similar[:20]
        ]

        if external_items:
            rows.append(
                {
                    "key": f"discover:{kind}:{tmdb_id}",
                    "title": f"Discover {kind.title()}s Like {title}",
                    "items": external_items,
                }
            )

    return rows
