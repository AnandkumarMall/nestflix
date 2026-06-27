"""TMDB discovery rows (Trending, New Releases) for titles not in the local library.

NOTE: stub for the base skeleton. Real implementation lands in
`feature/tmdb-discovery`.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/discovery", tags=["discovery"])


@router.get("/trending")
async def trending() -> dict:
    """Return TMDB trending titles. Stubbed for now."""
    return {"items": []}


@router.get("/new-releases")
async def new_releases() -> dict:
    """Return recent theatrical / streaming releases from TMDB. Stubbed for now."""
    return {"items": []}
