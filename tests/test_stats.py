"""Stats page: aggregation and routes (offline, no TMDB)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.main import app

pytestmark = pytest.mark.usefixtures("temp_db")


# Seed helpers (reusing patterns from test_recommender)


def _seed_movie(title, *, genres, year=2000, rating=7.0):
    """Insert a matched movie. Returns (movie_id, media_file_id)."""
    conn = db.get_db()
    try:
        mid = db.upsert_media_file(conn, f"/lib/{title}.mp4", 1, 0.0, "mp4", "movie")
        movie_id = db.upsert_movie(conn, mid, title, year)
        conn.execute(
            "UPDATE movies SET title=?, genres=?, rating=?, match_status='matched' WHERE id=?",
            (title, json.dumps(genres), rating, movie_id),
        )
        conn.commit()
    finally:
        conn.close()
    return movie_id, mid


def _seed_show(title, *, genres, episodes=2):
    """Insert a matched show with episodes. Returns (show_id, media_file_ids)."""
    conn = db.get_db()
    try:
        show_id = db.upsert_show(conn, title)
        media_ids = []
        for s in range(1, 2):
            for e in range(1, episodes + 1):
                mid = db.upsert_media_file(
                    conn, f"/lib/{title}/s{s}e{e}.mp4", 1, 0.0, "mp4", "episode"
                )
                db.upsert_episode(conn, show_id, mid, s, e)
                media_ids.append(mid)
        conn.execute(
            "UPDATE shows SET title=?, genres=?, match_status='matched' WHERE id=?",
            (title, json.dumps(genres), show_id),
        )
        conn.commit()
    finally:
        conn.close()
    return show_id, media_ids


def _watch(profile_id, media_file_id, *, completed):
    """Mark a media file as watched (completed)."""
    conn = db.get_db()
    try:
        db.upsert_watch_progress(
            conn, profile_id, media_file_id, 100.0, 100.0, completed
        )
        if completed:
            db.record_watch_event(conn, profile_id, media_file_id, "finish", 1.0)
        conn.commit()
    finally:
        conn.close()


def _rate(profile_id, *, movie_id=None, show_id=None, value):
    """Record a thumbs rating."""
    conn = db.get_db()
    try:
        db.upsert_rating(conn, profile_id, movie_id=movie_id, show_id=show_id, value=value)
        conn.commit()
    finally:
        conn.close()


def _default_profile() -> int:
    conn = db.get_db()
    try:
        return conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
    finally:
        conn.close()


# Tests


def test_stats_empty_profile():
    """Empty profile returns zeroed stats."""
    profile_id = _default_profile()
    conn = db.get_db()
    try:
        stats = db.get_profile_stats(conn, profile_id)
    finally:
        conn.close()

    assert stats["titles_finished"] == 0
    assert stats["seconds_watched"] == 0
    assert stats["ratings"]["up"] == 0
    assert stats["ratings"]["down"] == 0
    assert stats["top_genres"] == []
    assert stats["recently_finished"] == []


def test_stats_with_watches():
    """After seeding movies and watches, stats aggregate correctly."""
    profile_id = _default_profile()

    m1_id, m1_mid = _seed_movie("SciFi Film", genres=["Sci-Fi", "Action"])
    m2_id, m2_mid = _seed_movie("Comedy", genres=["Comedy"])
    s1_id, s1_mids = _seed_show("Drama Show", genres=["Drama"])

    _watch(profile_id, m1_mid, completed=True)
    _watch(profile_id, m2_mid, completed=True)
    _watch(profile_id, s1_mids[0], completed=True)  # One episode

    _rate(profile_id, movie_id=m1_id, value=1)  # Thumbs up
    _rate(profile_id, movie_id=m2_id, value=-1)  # Thumbs down

    conn = db.get_db()
    try:
        stats = db.get_profile_stats(conn, profile_id)
    finally:
        conn.close()

    assert stats["titles_finished"] == 3
    assert stats["seconds_watched"] == 300.0  # 3 × 100 seconds
    assert stats["ratings"]["up"] == 1
    assert stats["ratings"]["down"] == 1

    # Top genres: Sci-Fi (1), Action (1), Comedy (1), Drama (1).
    # All tied; sorted by name alphabetically.
    top = {g["name"]: g["count"] for g in stats["top_genres"]}
    assert top.get("Sci-Fi") == 1
    assert top.get("Action") == 1
    assert top.get("Comedy") == 1
    assert top.get("Drama") == 1

    # Recently finished: 3 titles, newest first (but order is insertion order in SQL,
    # which is UNION ordering). Check the count.
    assert len(stats["recently_finished"]) == 3
    titles = {t["id"]: t for t in stats["recently_finished"]}
    assert m1_id in titles
    assert m2_id in titles
    assert s1_id in titles


def test_stats_route():
    """GET /api/stats returns the profile stats."""
    profile_id = _default_profile()
    m1_id, m1_mid = _seed_movie("Test", genres=["Action"])
    _watch(profile_id, m1_mid, completed=True)
    _rate(profile_id, movie_id=m1_id, value=1)

    client = TestClient(app)
    resp = client.get(f"/api/stats?profile_id={profile_id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["profile_id"] == profile_id
    assert data["titles_finished"] == 1
    assert data["seconds_watched"] == 100.0
    assert data["ratings"]["up"] == 1
    assert len(data["recently_finished"]) == 1
