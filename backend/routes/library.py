"""Browse the local library and trigger scans.

Route handlers stay thin: they call helpers in `backend.db` / `backend.scanner` and
return the result. No SQL lives here.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import enrich
from ..config import settings
from ..db import get_library
from ..scanner import scan_library
from ..tmdb import TMDBError, TMDBNotConfigured

router = APIRouter(prefix="/api/library", tags=["library"])


class MatchRequest(BaseModel):
    tmdb_id: int


@router.get("")
async def list_library() -> dict:
    """Return the full library: movies plus shows with their grouped episodes."""
    return get_library()


@router.post("/scan")
async def scan() -> dict:
    """(Re)scan the configured library folders and return what changed."""
    result = scan_library()
    return asdict(result)


@router.post("/enrich")
async def enrich_endpoint() -> dict:
    """Match pending movies/shows to TMDB and cache their metadata + images."""
    if not settings.tmdb_configured:
        raise HTTPException(status_code=400, detail="TMDB_API_KEY is not configured")
    try:
        return await enrich.enrich_library()
    except TMDBNotConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TMDBError as exc:
        raise HTTPException(status_code=502, detail=f"TMDB error: {exc}") from exc


@router.get("/movies/{movie_id}/matches")
async def movie_matches(movie_id: int, q: str, year: int | None = None) -> dict:
    """List TMDB candidates for manually fixing a movie's match."""
    if not settings.tmdb_configured:
        raise HTTPException(status_code=400, detail="TMDB_API_KEY is not configured")
    try:
        return {"results": await enrich.movie_match_candidates(q, year)}
    except TMDBError as exc:
        raise HTTPException(status_code=502, detail=f"TMDB error: {exc}") from exc


@router.post("/movies/{movie_id}/match")
async def movie_set_match(movie_id: int, body: MatchRequest) -> dict:
    """Force a movie to a specific TMDB id (manual fix-match)."""
    if not settings.tmdb_configured:
        raise HTTPException(status_code=400, detail="TMDB_API_KEY is not configured")
    try:
        return await enrich.match_movie_manual(movie_id, body.tmdb_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TMDBError as exc:
        raise HTTPException(status_code=502, detail=f"TMDB error: {exc}") from exc


@router.get("/search")
async def search_library(q: str = "") -> dict:
    """Search the local library by title (simple case-insensitive contains)."""
    q_lower = q.strip().lower()
    if not q_lower:
        return {"query": q, "results": []}
    lib = get_library()
    results: list[dict] = []
    for movie in lib["movies"]:
        name = (movie.get("title") or movie.get("parsed_title") or "").lower()
        if q_lower in name:
            results.append({"type": "movie", **movie})
    for show in lib["shows"]:
        name = (show.get("title") or show.get("parsed_title") or "").lower()
        if q_lower in name:
            results.append({"type": "show", **show})
    return {"query": q, "results": results}
