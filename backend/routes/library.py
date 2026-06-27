"""Browse the local library and trigger scans.

Route handlers stay thin: they call helpers in `backend.db` / `backend.scanner` and
return the result. No SQL lives here.
"""

from __future__ import annotations

from fastapi import APIRouter

from ..db import get_library
from ..scanner import scan_library

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
async def list_library() -> dict:
    """Return the full library: movies plus shows with their grouped episodes."""
    return get_library()


@router.post("/scan")
async def scan() -> dict:
    """(Re)scan the configured library folders and return what changed."""
    result = scan_library()
    return result.as_dict()


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
