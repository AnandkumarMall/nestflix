"""Tests for TMDB enrichment: metadata mapping, matched/unmatched paths, manual fix.

TMDB is fully mocked; `asyncio.run` drives the async helpers so no event-loop plugin
is needed.
"""

from __future__ import annotations

import asyncio

from backend import db, enrich, tmdb

_MOVIE_DETAILS = {
    "id": 603,
    "title": "The Matrix",
    "release_date": "1999-03-30",
    "overview": "A hacker learns the truth.",
    "poster_path": "/poster.jpg",
    "backdrop_path": "/backdrop.jpg",
    "vote_average": 8.2,
    "runtime": 136,
    "genres": [{"name": "Action"}, {"name": "Science Fiction"}],
    "credits": {"cast": [{"name": "Keanu Reeves"}, {"name": "Carrie-Anne Moss"}]},
    "keywords": {"keywords": [{"name": "dystopia"}, {"name": "simulation"}]},
}


def _insert_movie(title="The Matrix", year=1999, path="/x/The.Matrix.1999.mkv"):
    conn = db.get_db()
    try:
        mf = db.upsert_media_file(conn, path, 100, 1.0, "mkv", "movie")
        movie_id = db.upsert_movie(conn, mf, title, year)
        conn.commit()
        return movie_id
    finally:
        conn.close()


def _mock_images(monkeypatch):
    async def fake_get_image(path, size="w342"):
        return b"\x89PNG"

    monkeypatch.setattr(tmdb, "get_image", fake_get_image)


def test_enrich_movie_writes_metadata_and_caches_images(temp_db, monkeypatch):
    async def fake_search(title, year=None):
        return {"id": 603}

    monkeypatch.setattr(tmdb, "search_movie", fake_search)
    monkeypatch.setattr(tmdb, "movie_details", lambda i: _async(_MOVIE_DETAILS))
    _mock_images(monkeypatch)
    _insert_movie()

    counts = asyncio.run(enrich.enrich_library())

    assert counts["movies_matched"] == 1
    assert counts["movies_unmatched"] == 0
    movie = db.get_library()["movies"][0]
    assert movie["title"] == "The Matrix"
    assert movie["match_status"] == "matched"
    assert movie["tmdb_id"] == 603
    assert "Action" in movie["genres"]
    # Poster + backdrop should have been written to the cache dir.
    assert enrich.cached_image_path("/poster.jpg", "w342").exists()
    assert enrich.cached_image_path("/backdrop.jpg", "w780").exists()


def test_enrich_movie_no_match_marks_unmatched(temp_db, monkeypatch):
    async def no_hit(title, year=None):
        return None

    monkeypatch.setattr(tmdb, "search_movie", no_hit)
    _insert_movie(title="Some Obscure Foreign Film")

    counts = asyncio.run(enrich.enrich_library())

    assert counts["movies_unmatched"] == 1
    assert db.get_library()["movies"][0]["match_status"] == "unmatched"


def test_enrich_is_idempotent_skips_matched(temp_db, monkeypatch):
    calls = {"n": 0}

    async def fake_search(title, year=None):
        calls["n"] += 1
        return {"id": 603}

    monkeypatch.setattr(tmdb, "search_movie", fake_search)
    monkeypatch.setattr(tmdb, "movie_details", lambda i: _async(_MOVIE_DETAILS))
    _mock_images(monkeypatch)
    _insert_movie()

    asyncio.run(enrich.enrich_library())
    asyncio.run(enrich.enrich_library())  # nothing pending the second time

    assert calls["n"] == 1


def test_manual_match_overrides_movie(temp_db, monkeypatch):
    monkeypatch.setattr(tmdb, "movie_details", lambda i: _async(_MOVIE_DETAILS))
    _mock_images(monkeypatch)
    movie_id = _insert_movie(title="Wrong Title", year=2000)

    meta = asyncio.run(enrich.match_movie_manual(movie_id, 603))

    assert meta["tmdb_id"] == 603
    assert db.get_library()["movies"][0]["title"] == "The Matrix"


def _async(value):
    async def _coro(*args, **kwargs):
        return value

    return _coro()
