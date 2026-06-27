"""Stream media files, serve subtitles, and persist watch progress (resume).

Handlers only parse input, call helpers, and shape the response — streaming logic lives
in ``backend.streaming``, codec decisions in ``backend.media_probe``, and all SQL in
``backend.db``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import db, media_probe, streaming

router = APIRouter(prefix="/api/playback", tags=["playback"])

# A title is "finished" once watched this far — used to mark completed + log a finish.
_COMPLETE_FRACTION = 0.92


class ProgressBody(BaseModel):
    profile_id: int
    media_file_id: int
    position_seconds: float
    duration_seconds: float = 0.0
    event: Literal["start", "abandon", "progress", "finish"] | None = None


def _resolve_media_path(media_file_id: int) -> Path:
    """Look up a media file id, validate it's inside the library and present on disk."""
    conn = db.get_db()
    try:
        media_file = db.get_media_file(conn, media_file_id)
    finally:
        conn.close()
    if media_file is None:
        raise HTTPException(status_code=404, detail="media file not found")
    path = Path(media_file["path"])
    if not streaming.is_within_library(path):
        raise HTTPException(status_code=403, detail="file is outside the library")
    if not path.exists():
        raise HTTPException(status_code=404, detail="media file is missing on disk")
    return path


# ---------------------------------------------------------------------------
# Resume progress + Continue Watching (static paths declared before /{id}/...).
# ---------------------------------------------------------------------------


@router.get("/continue")
async def continue_watching(profile_id: int) -> dict:
    """Return in-progress titles for the Continue Watching row."""
    conn = db.get_db()
    try:
        items = db.get_continue_watching(conn, profile_id)
    finally:
        conn.close()
    return {"profile_id": profile_id, "items": items}


@router.get("/progress")
async def read_progress(profile_id: int, media_file_id: int) -> dict:
    """Return the saved resume position for a (profile, media file)."""
    conn = db.get_db()
    try:
        row = db.get_watch_progress(conn, profile_id, media_file_id)
    finally:
        conn.close()
    if row is None:
        return {"position_seconds": 0.0, "duration_seconds": 0.0, "completed": False}
    return {
        "position_seconds": row["position_seconds"],
        "duration_seconds": row["duration_seconds"],
        "completed": bool(row["completed"]),
    }


@router.post("/progress")
async def save_progress(body: ProgressBody) -> dict:
    """Persist the current playback position and log a watch event."""
    pct = (
        body.position_seconds / body.duration_seconds
        if body.duration_seconds > 0
        else 0.0
    )
    completed = pct >= _COMPLETE_FRACTION
    event = body.event or ("finish" if completed else "progress")
    conn = db.get_db()
    try:
        db.upsert_watch_progress(
            conn,
            body.profile_id,
            body.media_file_id,
            body.position_seconds,
            body.duration_seconds,
            completed,
        )
        db.record_watch_event(conn, body.profile_id, body.media_file_id, event, pct)
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=400, detail="unknown profile or media file"
        ) from exc
    finally:
        conn.close()
    return {"ok": True, "completed": completed}


# ---------------------------------------------------------------------------
# Per-file info, streaming, and subtitles.
# ---------------------------------------------------------------------------


@router.get("/{media_file_id}/info")
async def playback_info(media_file_id: int) -> dict:
    """Codec/play-mode decision plus display metadata, for the player to set up."""
    path = _resolve_media_path(media_file_id)
    conn = db.get_db()
    try:
        media_file = db.get_media_file(conn, media_file_id)
        display = db.get_media_display(conn, media_file_id) or {}
    finally:
        conn.close()

    info = await run_in_threadpool(media_probe.probe, path)
    play_mode = media_probe.decide_play_mode(media_file["container"], info)
    return {
        "media_file_id": media_file_id,
        "play_mode": play_mode,
        "container": media_file["container"],
        "video_codec": info.video_codec if info else None,
        "audio_codec": info.audio_codec if info else None,
        "duration_seconds": info.duration_seconds if info else None,
        "width": info.width if info else None,
        "height": info.height if info else None,
        "ffmpeg_available": media_probe.ffmpeg_available(),
        "subtitles": streaming.subtitle_tracks(path, info),
        **display,
    }


@router.get("/{media_file_id}/stream")
async def stream(media_file_id: int, request: Request, t: float = 0.0) -> Response:
    """Stream a media file, choosing direct/remux/transcode automatically.

    ``t`` (seconds) is the start offset for the ffmpeg modes (remux/transcode); direct
    play ignores it and uses native Range seeking instead.
    """
    path = _resolve_media_path(media_file_id)
    conn = db.get_db()
    try:
        media_file = db.get_media_file(conn, media_file_id)
    finally:
        conn.close()

    info = await run_in_threadpool(media_probe.probe, path)
    play_mode = media_probe.decide_play_mode(media_file["container"], info)

    if play_mode == "direct":
        return streaming.range_response(
            path, request.headers.get("range"), media_file["container"]
        )
    if play_mode == "unavailable":
        raise HTTPException(
            status_code=409,
            detail="ffmpeg is required to play this file but is not installed",
        )
    return await streaming.ffmpeg_stream(path, play_mode, max(0.0, t))


@router.get("/{media_file_id}/subtitles")
async def subtitles(media_file_id: int) -> dict:
    """List available subtitle tracks (embedded text streams + sidecar files)."""
    path = _resolve_media_path(media_file_id)
    info = await run_in_threadpool(media_probe.probe, path)
    return {"tracks": streaming.subtitle_tracks(path, info)}


@router.get("/{media_file_id}/subtitles/{track}.vtt")
async def subtitle_vtt(media_file_id: int, track: str) -> Response:
    """Return one subtitle track as WebVTT (extract embedded or convert a sidecar)."""
    path = _resolve_media_path(media_file_id)
    vtt = await run_in_threadpool(streaming.subtitle_to_vtt, path, track)
    if vtt is None:
        raise HTTPException(status_code=404, detail="subtitle track not available")
    return Response(content=vtt, media_type="text/vtt")
