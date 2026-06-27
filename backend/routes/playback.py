"""Stream media files and persist watch progress (resume / Continue Watching).

NOTE: stub for the base skeleton. Real streaming + resume lands in
`feature/streaming-player`.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/playback", tags=["playback"])


@router.get("/continue")
async def continue_watching(profile_id: int) -> dict:
    """Return in-progress titles for the Continue Watching row. Stubbed for now."""
    return {"profile_id": profile_id, "items": []}


@router.post("/progress")
async def save_progress() -> dict:
    """Persist the current playback position. Stubbed for now."""
    return {"ok": True}
