"""Multi-profile management. Profiles keep each viewer's taste and history separate.

This router is functional in the base skeleton (it only needs the profiles table) so the
app has a usable profile from first run.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import db

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    avatar_color: str = Field(default="#e50914", max_length=9)


@router.get("")
async def list_profiles() -> dict:
    """Return all profiles."""
    return {"profiles": db.list_profiles()}


@router.post("", status_code=201)
async def create_profile(body: ProfileIn) -> dict:
    """Create a new profile."""
    return db.create_profile(body.name, body.avatar_color)


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int) -> dict:
    """Delete a profile and its history (cascades)."""
    if not db.delete_profile(profile_id):
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"ok": True}
