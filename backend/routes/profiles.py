"""Multi-profile management. Profiles keep each viewer's taste and history separate.

This router is functional in the base skeleton (it only needs the profiles table) so the
app has a usable profile from first run.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import get_db

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    avatar_color: str = Field(default="#e50914", max_length=9)


@router.get("")
async def list_profiles() -> dict:
    """Return all profiles."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, avatar_color, created_at FROM profiles ORDER BY id"
        ).fetchall()
        return {"profiles": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.post("", status_code=201)
async def create_profile(body: ProfileIn) -> dict:
    """Create a new profile."""
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO profiles (name, avatar_color) VALUES (?, ?)",
            (body.name, body.avatar_color),
        )
        conn.commit()
        return {
            "id": cur.lastrowid,
            "name": body.name,
            "avatar_color": body.avatar_color,
        }
    finally:
        conn.close()


@router.delete("/{profile_id}")
async def delete_profile(profile_id: int) -> dict:
    """Delete a profile and its history (cascades)."""
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Profile not found")
        return {"ok": True}
    finally:
        conn.close()
