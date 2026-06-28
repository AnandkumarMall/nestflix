"""Personalized recommendation rows, "More Like This", and thumbs ratings.

Thin handlers: they validate input and call the recommender package / db helpers. All
ranking logic lives in ``backend.recommender``; all SQL lives in ``backend.db``.
"""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from .. import db
from ..config import settings
from ..recommender import model as model_mod
from ..recommender import rows as rows_mod
from ..recommender.features import build_vocabulary

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


class RatingBody(BaseModel):
    profile_id: int
    movie_id: int | None = None
    show_id: int | None = None
    value: Literal[-1, 1]


@router.get("/rows")
async def home_rows(profile_id: int) -> dict:
    """Ordered, explainable home-screen rows for a profile.

    Heavy lifting (numpy/sklearn) runs in a threadpool so it never blocks the event loop.
    """
    rows = await run_in_threadpool(rows_mod.home_rows, profile_id)
    return {"profile_id": profile_id, "rows": rows}


@router.get("/similar")
async def similar(kind: Literal["movie", "show"], id: int) -> dict:
    """Content-similarity neighbors of a title, for the detail page's More Like This."""
    items = await run_in_threadpool(rows_mod.similar_titles, kind, id)
    return {"kind": kind, "id": id, "items": items}


@router.get("/ratings")
async def ratings(profile_id: int) -> dict:
    """All thumbs signals for a profile, so the UI can reflect saved ratings."""
    conn = db.get_db()
    try:
        items = db.get_ratings(conn, profile_id)
    finally:
        conn.close()
    return {
        "ratings": [
            {"kind": kind, "id": title_id, "value": value}
            for (kind, title_id), value in items.items()
        ]
    }


@router.post("/rate")
async def rate(body: RatingBody) -> dict:
    """Record a thumbs up/down. Exactly one of movie_id / show_id must be provided."""
    if (body.movie_id is None) == (body.show_id is None):
        raise HTTPException(
            status_code=400, detail="provide exactly one of movie_id or show_id"
        )
    conn = db.get_db()
    try:
        db.upsert_rating(
            conn,
            body.profile_id,
            movie_id=body.movie_id,
            show_id=body.show_id,
            value=body.value,
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=400, detail="unknown profile or title") from exc
    finally:
        conn.close()
    return {"ok": True}


@router.post("/retrain")
async def retrain(profile_id: int) -> dict:
    """Force a retrain of the profile's "will I finish this?" model (dev/debug).

    Returns the training metrics, or a clear reason the model can't train yet (too few
    completed watches, or only one outcome class so far).
    """

    def _run() -> dict:
        conn = db.get_db()
        try:
            titles = db.get_titles_for_features(conn)
            history = db.get_watch_history(conn, profile_id)
            completed_count = db.get_completed_count(conn, profile_id)
        finally:
            conn.close()

        vocab = build_vocabulary(titles)
        by_media = {mid: t for t in titles for mid in t["media_file_ids"]}
        entries = [
            {
                "title": by_media[h["media_file_id"]],
                "completed": h["completed"],
                "finishes": h["finishes"],
            }
            for h in history
            if h["media_file_id"] in by_media
        ]
        trained = model_mod.train(
            profile_id, entries, vocab, completed_count=completed_count
        )
        if trained is None:
            return {
                "trained": False,
                "reason": (
                    f"need >= {settings.model_min_samples} watched titles across both "
                    "finished and unfinished outcomes"
                ),
                "samples": len(entries),
            }
        return {"trained": True, "metrics": trained.metrics}

    return await run_in_threadpool(_run)
