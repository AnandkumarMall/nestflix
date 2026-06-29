"""Assemble the personalized home-screen rows from the content + learned signals.

This is the only recommender module the route layer talks to. It pulls the library and
watch history (via ``db``), builds the taste vector, optionally folds in the learned
re-ranker, and emits ordered, explainable rows:

* **Top Picks for You** — best blended score across the whole library.
* **Because You Watched <title>** — content neighbors of a recently finished title.
* **<Genre> You'll Like** — the profile's favorite genres, re-ranked.

With no history yet (cold start) it degrades to popularity/genre rows so the endpoint is
always useful and never 500s. Already-finished titles are filtered out everywhere.
"""

from __future__ import annotations

import numpy as np

from .. import db
from . import model as model_mod
from .features import build_vocabulary, feature_matrix, feature_vector
from .taste_profile import build_taste_profile, content_scores, explain

_ROW_SIZE = 20
_MIN_GENRE_ROW = 4  # don't show a genre row with fewer than this many picks.


def _to_item(title: dict, reason: str, score: float) -> dict:
    """Shape a title into the card payload the frontend renders."""
    return {
        "kind": title["kind"],
        "id": title["id"],
        "title": title["title"],
        "year": title["year"],
        "poster_path": title["poster_path"],
        "backdrop_path": title["backdrop_path"],
        "media_file_id": title["primary_media_file_id"],
        "reason": reason,
        "score": round(float(score), 4),
    }


def _is_finished(title: dict, finished_media: set[int]) -> bool:
    """A title is "done" when its (only) movie file has been completed."""
    mids = title["media_file_ids"]
    return bool(mids) and all(m in finished_media for m in mids)


def home_rows(profile_id: int) -> list[dict]:
    """Ordered, explainable recommendation rows for a profile."""
    conn = db.get_db()
    try:
        titles = db.get_titles_for_features(conn)
        history = db.get_watch_history(conn, profile_id)
        ratings = db.get_ratings(conn, profile_id)
        finished_media = db.get_finished_media_ids(conn, profile_id)
        completed_count = db.get_completed_count(conn, profile_id)
    finally:
        conn.close()

    if not titles:
        return []

    vocab = build_vocabulary(titles)
    by_media: dict[int, dict] = {}
    for t in titles:
        for mid in t["media_file_ids"]:
            by_media[mid] = t

    # Fold the per-file watch history up to one signal per title (newest watch wins for
    # recency; completion/abandon merged across episodes of a show).
    watched: dict[tuple[str, int], dict] = {}
    order: list[tuple[str, int]] = []
    for h in history:
        title = by_media.get(h["media_file_id"])
        if title is None:
            continue
        key = (title["kind"], title["id"])
        if key not in watched:
            watched[key] = {
                "title": title,
                "completed": False,
                "pct": 0.0,
                "abandoned": False,
                "rating": ratings.get(key, 0),
            }
            order.append(key)
        agg = watched[key]
        agg["completed"] = agg["completed"] or h["completed"]
        agg["pct"] = max(agg["pct"], h["pct"])
        agg["abandoned"] = agg["abandoned"] or h["abandons"] > 0

    # Recency: newest watched title gets the highest factor, decaying to 0.5.
    n = max(len(order), 1)
    for rank, key in enumerate(order):
        watched[key]["recency"] = 1.0 - 0.5 * (rank / n)

    entries = list(watched.values())
    taste = build_taste_profile(entries, vocab)

    candidates = [t for t in titles if not _is_finished(t, finished_media)]
    if not candidates:
        return []

    if not taste.has_signal:
        return _cold_start_rows(candidates, vocab)

    model = model_mod.maybe_retrain(
        profile_id, entries, vocab, completed_count=completed_count
    )

    cand_matrix = feature_matrix(candidates, vocab)
    content = np.clip(content_scores(taste.vector, cand_matrix), 0.0, None)
    if model is not None:
        proba = model_mod.predict(model, candidates)
        blended = 0.5 * content + 0.5 * proba
    else:
        blended = content

    rows: list[dict] = [_top_picks_row(candidates, cand_matrix, blended, taste, vocab)]
    rows.extend(_because_you_watched_rows(entries, candidates, cand_matrix, vocab))
    rows.extend(_genre_rows(candidates, blended, taste))
    return [r for r in rows if r["items"]]


def _top_picks_row(candidates, cand_matrix, blended, taste, vocab) -> dict:
    """The single best-blended-score row, with genre diversity + per-card explanations."""
    order = np.argsort(blended)[::-1]

    # Diversify by genre: take top-2 per genre, fill remainder with best overall.
    seen_genres: set[str] = set()
    genre_counts: dict[str, int] = {}
    diverse_order = []

    for i in order:
        candidate = candidates[i]
        genres = candidate.get("genres") or []
        genre_list = genres if isinstance(genres, list) else [g.strip() for g in genres.split(",") if g.strip()]

        # Prioritize items with genres we haven't seen much of yet.
        added = False
        for genre in genre_list:
            if genre_counts.get(genre, 0) < 2 and len(diverse_order) < _ROW_SIZE:
                diverse_order.append(i)
                genre_counts[genre] = genre_counts.get(genre, 0) + 1
                seen_genres.update(genre_list)
                added = True
                break

        # If all genres have 2+, add anyway (fill up to _ROW_SIZE).
        if not added and len(diverse_order) < _ROW_SIZE:
            diverse_order.append(i)

    items = []
    for i in diverse_order:
        why = explain(taste.vector, cand_matrix[i], vocab)
        reason = f"Because you like {', '.join(why)}" if why else "Recommended for you"
        items.append(_to_item(candidates[i], reason, blended[i]))
    return {"key": "top_picks", "title": "Top Picks for You", "items": items}


def _because_you_watched_rows(
    entries, candidates, cand_matrix, vocab, *, max_rows: int = 2
) -> list[dict]:
    """For the most recent finished titles, a row of their nearest content neighbors."""
    rows: list[dict] = []
    seed_titles = [
        e["title"] for e in entries if e["completed"] and e["title"]["genres"]
    ][:max_rows]
    for seed in seed_titles:
        seed_vec = feature_vector(seed, vocab)
        sims = content_scores(seed_vec, cand_matrix)
        order = [
            i
            for i in np.argsort(sims)[::-1]
            if candidates[i]["id"] != seed["id"]
            or candidates[i]["kind"] != seed["kind"]
        ][:_ROW_SIZE]
        items = [
            _to_item(candidates[i], f"Because you watched {seed['title']}", sims[i])
            for i in order
            if sims[i] > 0
        ]
        if items:
            rows.append(
                {
                    "key": f"because:{seed['kind']}:{seed['id']}",
                    "title": f"Because You Watched {seed['title']}",
                    "items": items,
                }
            )
    return rows


def _genre_rows(candidates, blended, taste, *, max_rows: int = 3) -> list[dict]:
    """Re-ranked rows for the profile's favorite genres (from the taste vector)."""
    fav_genres = [
        g for g in taste.dominant_features if not g.startswith(("Keyword:", "Stars"))
    ]
    rows: list[dict] = []
    for genre in fav_genres:
        if len(rows) >= max_rows:
            break
        idx = [i for i, c in enumerate(candidates) if genre in c["genres"]]
        if len(idx) < _MIN_GENRE_ROW:
            continue
        idx.sort(key=lambda i: blended[i], reverse=True)
        items = [_to_item(candidates[i], genre, blended[i]) for i in idx[:_ROW_SIZE]]
        rows.append(
            {"key": f"genre:{genre}", "title": f"{genre} You'll Like", "items": items}
        )
    return rows


def _cold_start_rows(candidates, vocab) -> list[dict]:
    """No history yet: surface highly-rated titles and the library's biggest genres."""
    rows: list[dict] = []

    rated = sorted(candidates, key=lambda t: (t["rating"] or 0.0), reverse=True)[
        :_ROW_SIZE
    ]
    popular = [
        _to_item(t, "Highly rated", t["rating"] or 0.0)
        for t in rated
        if (t["rating"] or 0.0) >= 6.0
    ]
    if popular:
        rows.append(
            {"key": "popular", "title": "Popular in Your Library", "items": popular}
        )

    # Biggest genres in the (vocabulary already orders genres by frequency).
    for genre in vocab.genres[:3]:
        idx = [t for t in candidates if genre in t["genres"]]
        if len(idx) < _MIN_GENRE_ROW:
            continue
        idx.sort(key=lambda t: (t["rating"] or 0.0), reverse=True)
        items = [_to_item(t, genre, t["rating"] or 0.0) for t in idx[:_ROW_SIZE]]
        rows.append({"key": f"genre:{genre}", "title": genre, "items": items})

    return [r for r in rows if r["items"]]


def similar_titles(kind: str, title_id: int, *, limit: int = 12) -> list[dict]:
    """Content-similarity neighbors of one title — the detail page's "More Like This".

    Profile-independent: works with zero history. Returns ``[]`` if the title is unknown.
    """
    conn = db.get_db()
    try:
        titles = db.get_titles_for_features(conn)
    finally:
        conn.close()
    if not titles:
        return []

    vocab = build_vocabulary(titles)
    target = next(
        (t for t in titles if t["kind"] == kind and t["id"] == title_id), None
    )
    if target is None:
        return []

    others = [t for t in titles if not (t["kind"] == kind and t["id"] == title_id)]
    if not others:
        return []
    matrix = feature_matrix(others, vocab)
    target_vec = feature_vector(target, vocab)
    sims = content_scores(target_vec, matrix)
    order = np.argsort(sims)[::-1][:limit]
    return [
        _to_item(others[i], "More like this", sims[i]) for i in order if sims[i] > 0
    ]
