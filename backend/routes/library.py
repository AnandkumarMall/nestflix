"""Browse and search the local library.

NOTE: stub for the base skeleton. Real implementation lands in the
`feature/library-scanner` and `feature/tmdb-enrichment` features.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/library", tags=["library"])


@router.get("")
async def list_library() -> dict:
    """Return the full library grouped into movies and shows. Stubbed for now."""
    return {"movies": [], "shows": []}


@router.get("/search")
async def search_library(q: str = "") -> dict:
    """Search the local library by title. Stubbed for now."""
    return {"query": q, "results": []}
