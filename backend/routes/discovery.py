"""TMDB discovery rows (Trending, New Releases) for titles not in the local library.

Thin handlers over `backend.tmdb`. Degrades to an empty list (not an error) when TMDB
is unconfigured so the home screen still renders.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import tmdb
from ..config import settings

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


@router.get("/trending")
async def trending(window: str = "week") -> dict:
    """Return TMDB trending titles for the given window ('day' or 'week')."""
    if not settings.tmdb_configured:
        return {"items": []}
    if window not in ("day", "week"):
        raise HTTPException(status_code=400, detail="window must be 'day' or 'week'")
    try:
        return {"items": await tmdb.trending("all", window)}
    except tmdb.TMDBError as exc:
        raise HTTPException(status_code=502, detail=f"TMDB error: {exc}") from exc


@router.get("/new-releases")
async def new_releases() -> dict:
    """Return movies currently in theaters / newly released from TMDB."""
    if not settings.tmdb_configured:
        return {"items": []}
    try:
        return {"items": await tmdb.now_playing()}
    except tmdb.TMDBError as exc:
        raise HTTPException(status_code=502, detail=f"TMDB error: {exc}") from exc
