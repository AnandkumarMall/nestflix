"""Per-profile viewing statistics for the Stats page.

Thin handler: validates input and calls ``backend.db.get_profile_stats``. All SQL lives
in ``backend.db``; nothing here computes against the database directly.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
async def profile_stats(profile_id: int) -> dict:
    """Viewing summary for a profile (totals, thumbs, top genres, recent finishes).

    A profile with no history degrades to zeroed totals and empty lists — never 500s.

    NOTE: This endpoint is unauthenticated. In a multi-profile setup, any client can
    request stats for any profile_id. This is acceptable for trusted-network-only (local
    home) setups. If auth is added later, validate profile ownership before querying.
    """
    if profile_id < 1:
        raise HTTPException(status_code=400, detail="profile_id must be >= 1")
    conn = db.get_db()
    try:
        stats = db.get_profile_stats(conn, profile_id)
    finally:
        conn.close()
    return {"profile_id": profile_id, **stats}
