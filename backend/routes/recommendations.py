"""Personalized home-screen rows from the recommender.

NOTE: stub for the base skeleton. Real implementation lands in
`feature/recommendation-engine`.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/rows")
async def home_rows(profile_id: int) -> dict:
    """Return ordered home-screen rows for a profile. Stubbed for now."""
    return {"profile_id": profile_id, "rows": []}
