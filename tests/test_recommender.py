"""Recommendation engine: features, taste profile, learned model, rows, and routes.

All offline — no TMDB or network. Library metadata is seeded straight into SQLite.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import db
from backend.config import settings
from backend.main import app
from backend.recommender import model as model_mod
from backend.recommender import rows as rows_mod
from backend.recommender.features import build_vocabulary, feature_vector
from backend.recommender.taste_profile import (
    TasteProfile,
    build_taste_profile,
    content_scores,
    watch_weight,
)

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_movie(
    title, *, genres, keywords=None, cast=None, year=2000, rating=7.0, runtime=120
):
    """Insert a matched movie with metadata. Returns (movie_id, media_file_id)."""
    conn = db.get_db()
    try:
        mid = db.upsert_media_file(conn, f"/lib/{title}.mp4", 1, 0.0, "mp4", "movie")
        movie_id = db.upsert_movie(conn, mid, title, year)
        conn.execute(
            """UPDATE movies SET title=?, genres=?, keywords=?, cast=?, rating=?,
               runtime=?, match_status='matched' WHERE id=?""",
            (
                title,
                json.dumps(genres),
                json.dumps(keywords or []),
                json.dumps(cast or []),
                rating,
                runtime,
                movie_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return movie_id, mid


def _watch(profile_id, media_file_id, *, completed, pct, event=None):
    """Record watch progress + an event for a media file."""
    conn = db.get_db()
    try:
        db.upsert_watch_progress(
            conn, profile_id, media_file_id, pct * 100, 100.0, completed
        )
        if event:
            db.record_watch_event(conn, profile_id, media_file_id, event, pct)
        conn.commit()
    finally:
        conn.close()


def _default_profile() -> int:
    conn = db.get_db()
    try:
        return conn.execute("SELECT id FROM profiles LIMIT 1").fetchone()["id"]
    finally:
        conn.close()


def _title(title="X", **kw):
    base = {
        "kind": "movie",
        "id": 1,
        "title": title,
        "year": 2000,
        "rating": 7.0,
        "runtime": 120,
        "genres": [],
        "keywords": [],
        "cast": [],
        "poster_path": None,
        "backdrop_path": None,
        "media_file_ids": [1],
        "primary_media_file_id": 1,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# features
# ---------------------------------------------------------------------------


def test_vocabulary_and_vector_shape():
    titles = [
        _title(genres=["Action", "Sci-Fi"], keywords=["robot"], cast=["A"]),
        _title(genres=["Drama"], keywords=["love"], cast=["B"]),
    ]
    vocab = build_vocabulary(titles)
    assert set(vocab.genres) == {"Action", "Sci-Fi", "Drama"}
    vec = feature_vector(titles[0], vocab)
    assert vec.shape == (vocab.dim,)
    assert len(vocab.feature_names) == vocab.dim


def test_vector_multi_hot_and_scalars():
    titles = [_title(genres=["Action", "Sci-Fi"])]
    vocab = build_vocabulary(titles)
    vec = feature_vector(titles[0], vocab)
    # The two genres present are 1, the trailing scalars are in [0, 1].
    assert vec[vocab.genre_offset + vocab.genres.index("Action")] == 1.0
    assert vec[vocab.genre_offset + vocab.genres.index("Sci-Fi")] == 1.0
    scalars = vec[vocab.scalar_offset :]
    assert np.all((scalars >= 0.0) & (scalars <= 1.0))


def test_vector_handles_missing_metadata():
    vocab = build_vocabulary([_title(genres=["Action"])])
    blank = _title(genres=[], rating=None, year=None, runtime=None)
    vec = feature_vector(blank, vocab)
    assert vec.shape == (vocab.dim,)
    assert np.all(np.isfinite(vec))


# ---------------------------------------------------------------------------
# taste profile
# ---------------------------------------------------------------------------


def test_watch_weight_signs():
    assert watch_weight({"rating": 1, "recency": 1.0}) > 0
    assert watch_weight({"rating": -1, "recency": 1.0}) < 0
    assert watch_weight({"completed": True, "recency": 1.0}) > 0
    assert watch_weight({"abandoned": True, "pct": 0.05, "recency": 1.0}) < 0


def test_taste_prefers_liked_genre():
    titles = [
        _title(id=1, genres=["Sci-Fi"]),
        _title(id=2, genres=["Romance"]),
        _title(id=3, genres=["Sci-Fi"]),
    ]
    vocab = build_vocabulary(titles)
    entries = [{"title": titles[0], "completed": True, "recency": 1.0, "rating": 1}]
    taste = build_taste_profile(entries, vocab)
    assert taste.has_signal
    assert any("Sci-Fi" in f for f in taste.dominant_features)

    cand = np.vstack([feature_vector(titles[1], vocab), feature_vector(titles[2], vocab)])
    scores = content_scores(taste.vector, cand)
    # The Sci-Fi candidate (index 1) outranks the Romance one (index 0).
    assert scores[1] > scores[0]


def test_taste_no_signal_when_empty():
    vocab = build_vocabulary([_title(genres=["Action"])])
    taste = build_taste_profile([], vocab)
    assert not taste.has_signal
    assert isinstance(taste, TasteProfile)


# ---------------------------------------------------------------------------
# model
# ---------------------------------------------------------------------------


def _model_entries(n_finished, n_unfinished):
    titles = [
        _title(id=i, genres=["Action"] if i % 2 == 0 else ["Drama"], rating=8.0)
        for i in range(n_finished + n_unfinished)
    ]
    vocab = build_vocabulary(titles)
    entries = []
    for i in range(n_finished):
        entries.append({"title": titles[i], "completed": True, "finishes": 1})
    for i in range(n_unfinished):
        entries.append(
            {"title": titles[n_finished + i], "completed": False, "finishes": 0}
        )
    return entries, vocab


def test_model_below_threshold_returns_none(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "model_min_samples", 12)
    entries, vocab = _model_entries(2, 2)
    assert model_mod.train(1, entries, vocab, completed_count=2) is None


def test_model_single_class_returns_none(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "model_min_samples", 3)
    entries, vocab = _model_entries(4, 0)  # all finished → one class
    assert model_mod.train(1, entries, vocab, completed_count=4) is None


def test_model_trains_persists_and_predicts(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "model_min_samples", 4)
    entries, vocab = _model_entries(4, 4)
    trained = model_mod.train(1, entries, vocab, completed_count=4)
    assert trained is not None
    assert trained.metrics["n_samples"] == 8

    reloaded = model_mod.load_model(1)
    assert reloaded is not None
    probs = model_mod.predict(reloaded, [e["title"] for e in entries])
    assert probs.shape == (8,)
    assert np.all((probs >= 0.0) & (probs <= 1.0))


def test_model_corrupt_pickle_loads_none(temp_db):
    settings.ensure_dirs()
    path = settings.models_dir / "profile_1.pkl"
    path.write_bytes(b"not a pickle")
    assert model_mod.load_model(1) is None


def test_should_retrain_cadence(temp_db, monkeypatch):
    monkeypatch.setattr(settings, "model_min_samples", 4)
    monkeypatch.setattr(settings, "retrain_every", 5)
    assert model_mod.should_retrain(1, 2) is False  # below threshold
    # No model yet but threshold met → train.
    assert model_mod.should_retrain(1, 5) is True
    entries, vocab = _model_entries(4, 4)
    model_mod.train(1, entries, vocab, completed_count=5)
    # Already trained at this count → skip.
    assert model_mod.should_retrain(1, 5) is False
    # Off-cadence count → skip; on-cadence multiple → retrain.
    assert model_mod.should_retrain(1, 7) is False
    assert model_mod.should_retrain(1, 10) is True


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------


def test_home_rows_cold_start(temp_db):
    _seed_movie("A", genres=["Action"], rating=8.0)
    _seed_movie("B", genres=["Action"], rating=6.0)
    rows = rows_mod.home_rows(_default_profile())
    assert rows  # non-empty even with no history
    assert any(r["key"] == "popular" for r in rows)


def test_home_rows_personalized_excludes_finished(temp_db):
    _, watched_mid = _seed_movie("Matrix", genres=["Sci-Fi"], cast=["Keanu"], rating=8.0)
    _seed_movie("Inception", genres=["Sci-Fi"], rating=8.0)
    _seed_movie("Notebook", genres=["Romance"], rating=7.0)
    pid = _default_profile()
    _watch(pid, watched_mid, completed=True, pct=1.0, event="finish")

    rows = rows_mod.home_rows(pid)
    assert any(r["key"] == "top_picks" for r in rows)
    all_titles = [it["title"] for r in rows for it in r["items"]]
    assert "Matrix" not in all_titles  # finished → excluded
    # Every recommended card carries an explanation.
    for r in rows:
        for it in r["items"]:
            assert it["reason"]


def test_similar_titles(temp_db):
    m1, _ = _seed_movie("Matrix", genres=["Sci-Fi"], cast=["Keanu"])
    _seed_movie("Inception", genres=["Sci-Fi"])
    _seed_movie("Notebook", genres=["Romance"])
    sims = rows_mod.similar_titles("movie", m1)
    assert sims
    assert sims[0]["title"] == "Inception"  # closest by shared Sci-Fi genre


def test_similar_unknown_title_is_empty(temp_db):
    _seed_movie("A", genres=["Action"])
    assert rows_mod.similar_titles("movie", 999) == []


# ---------------------------------------------------------------------------
# routes
# ---------------------------------------------------------------------------


def test_rows_endpoint(temp_db):
    _seed_movie("A", genres=["Action"], rating=8.0)
    pid = _default_profile()
    with TestClient(app) as client:
        r = client.get(f"/api/recommendations/rows?profile_id={pid}")
    assert r.status_code == 200
    assert "rows" in r.json()


def test_similar_endpoint(temp_db):
    m1, _ = _seed_movie("Matrix", genres=["Sci-Fi"])
    _seed_movie("Inception", genres=["Sci-Fi"])
    with TestClient(app) as client:
        r = client.get(f"/api/recommendations/similar?kind=movie&id={m1}")
    assert r.status_code == 200
    assert r.json()["items"]


def test_rate_endpoint_and_validation(temp_db):
    m1, _ = _seed_movie("Matrix", genres=["Sci-Fi"])
    pid = _default_profile()
    with TestClient(app) as client:
        ok = client.post(
            "/api/recommendations/rate",
            json={"profile_id": pid, "movie_id": m1, "value": 1},
        )
        assert ok.status_code == 200

        # Both ids set → 400.
        bad = client.post(
            "/api/recommendations/rate",
            json={"profile_id": pid, "movie_id": m1, "show_id": 1, "value": 1},
        )
        assert bad.status_code == 400

    conn = db.get_db()
    try:
        ratings = db.get_ratings(conn, pid)
    finally:
        conn.close()
    assert ratings[("movie", m1)] == 1


def test_rate_rejects_bad_value(temp_db):
    pid = _default_profile()
    with TestClient(app) as client:
        r = client.post(
            "/api/recommendations/rate",
            json={"profile_id": pid, "movie_id": 1, "value": 5},
        )
    assert r.status_code == 422  # pydantic Literal rejects it
