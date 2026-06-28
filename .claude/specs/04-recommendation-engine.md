# Spec: Recommendation Engine

## Overview

Phases 01–03 gave Nestflix a browsable, enriched, streamable library with per-profile
watch history (`watch_progress`, `watch_events`) and explicit `ratings` (thumbs up/down).
This feature turns that data into **personalized home-screen rows** and a **"More Like
This"** rail on the detail page.

Per CLAUDE.md, the engine is two-tiered:

1. **Content-based (always on, cold-start safe).** Build a feature vector for every title
   from its TMDB metadata (genres, keywords, top cast, rating, decade, runtime). Aggregate
   the profile's watched titles into a weighted **taste vector** and rank unwatched titles
   by cosine similarity. This path works from the very first watch.
2. **Learned re-ranker (kicks in past a threshold, auto-retrains).** A lightweight
   scikit-learn logistic-regression model predicts *"will I finish this?"* from the same
   features, trained on `watch_events` (finish = 1, abandon = 0). It only activates once a
   profile has ≥ `MODEL_MIN_SAMPLES` completed watches and **auto-retrains every
   `RETRAIN_EVERY` completed watches**. Below threshold (or if training fails), ranking
   falls back to the content score alone.

Recommendations are **explainable**: every recommended title carries the top contributing
features (e.g. "Sci-Fi · because you watched The Matrix").

## Where things live (per CLAUDE.md)

- `backend/recommender/features.py` — vocabulary + dense feature vectors from metadata.
- `backend/recommender/taste_profile.py` — weighted taste vector from watch history.
- `backend/recommender/model.py` — sklearn re-ranker, persistence, auto-retrain.
- `backend/recommender/rows.py` — assemble ordered, explainable home rows.
- DB reads for the recommender → `backend/db.py` (no SQL in routes).
- Routes → `backend/routes/recommendations.py` (replaces the stub). Thin handlers only.
- Frontend → personalized rows on `Home`, "More Like This" + thumbs on `Detail`, all via
  `src/api/client.ts`.

## Definition of Done

### Backend
- `recommender/features.py`:
  - `build_vocabulary(titles)` → stable index maps for genres / keywords / cast.
  - `feature_vector(title, vocab)` → dense `numpy` vector (multi-hot genres/keywords/cast +
    normalized rating, decade-recency, runtime). Handles missing/`NULL` metadata.
  - `FEATURE_NAMES` / a way to map vector indices back to human labels (for explanations).
- `recommender/taste_profile.py`:
  - `build_taste_profile(watched, vocab)` → weighted mean of watched feature vectors.
    Weight = completion fraction × recency, **plus** explicit rating (thumbs up boosts,
    thumbs down subtracts). Returns the vector + the dominant features (for "because you
    like …").
  - `content_scores(taste, candidates)` → cosine similarity per candidate.
- `recommender/model.py`:
  - `training_data(watched)` → `(X, y)` from watch events (finish=1 / abandon=0).
  - `train(profile_id, …)` → fit `LogisticRegression`, persist to
    `data/models/profile_<id>.pkl` (gitignored); returns metrics or `None` if too few
    samples / single-class.
  - `predict(model, candidates)` → finish-probabilities, and `top_features(model)` for
    explanations.
  - `maybe_retrain(profile_id, completed_count)` → retrain on the `RETRAIN_EVERY` cadence.
  - Loads gracefully: a missing/corrupt pickle → `None`, never crashes a request.
- `recommender/rows.py`:
  - `home_rows(profile_id)` → ordered rows: **Top Picks for You**, **Because You Watched
    \<title\>**, per-genre rows ("Sci-Fi Movies You'll Like"), excluding already-finished
    titles. Each item carries `reason` (explanation). Blends content score + model
    probability when the model is available; pure content score otherwise.
  - `similar_titles(kind, id)` → content-similarity neighbors for the detail rail
    (profile-independent, works with zero history).
- `db.py` helpers (parameterized, no SQL in routes):
  - `get_titles_for_features(conn)` — every movie/show with genres/keywords/cast/rating/
    year/runtime + its `media_file_id`(s).
  - `get_watch_history(conn, profile_id)` — finished/abandoned events joined to title
    features, with completion pct, recency, and any thumbs rating.
  - `get_completed_count(conn, profile_id)`, `get_finished_media_ids(conn, profile_id)`.
  - `upsert_rating(conn, profile_id, movie_id|show_id, value)` and `get_ratings(…)`.
- Routes (`/api/recommendations`):
  - `GET /rows?profile_id=` — the personalized rows (replaces the stub `[]`).
  - `GET /similar?kind=&id=` — "More Like This" for a title.
  - `POST /rate` `{profile_id, movie_id?|show_id?, value:±1}` — record a thumbs signal.
  - `POST /retrain?profile_id=` — force a retrain (dev/debug); returns metrics.
  - All raise `HTTPException` on bad input; degrade to empty rows (never 500) when there's
    no library or no history.

### Frontend
- `src/api/client.ts` — types (`RecRow`, `RecItem` with `reason`, `Similar`) + methods
  `recommendationRows`, `similar`, `rate`.
- `Home.tsx` — render the personalized rows above the raw library rows when a profile has
  history; keep the existing library/discovery rows as the cold-start fallback.
- `Detail.tsx` — a **More Like This** `PosterRow` and **thumbs up/down** buttons that call
  `rate` and reflect the saved value.

### Tests (offline, no TMDB/network)
- `features`: vector shape, multi-hot correctness, missing-metadata safety, decade norm.
- `taste_profile`: finished+thumbs-up dominates; thumbs-down repels; recency weighting;
  cosine ranking order.
- `model`: trains past threshold, returns `None` below it / single-class, persist+reload,
  corrupt pickle → `None`, `maybe_retrain` cadence.
- `rows`: excludes finished titles, cold-start (no history) still returns content rows,
  every item has a non-empty `reason`, blended score ordering.
- routes: `/rows`, `/similar`, `/rate` happy paths + validation; empty-library degradation.

## Out of scope (later)
- Collaborative filtering / multi-user signals (single-user app by design).
- Embeddings / deep models — intentionally lightweight to avoid overfitting tiny data.
- A dedicated Stats page (separate feature).

## New dependencies
None — `scikit-learn==1.6.1` and `numpy==2.2.1` are already in `requirements.txt`. Model
pickles live under `data/models/` (already covered by the `data/` gitignore).

## Verification
1. Fresh profile (no history): `GET /rows` returns content-based rows (no crash); `Home`
   shows library + discovery.
2. Finish a couple of titles, thumbs-up one → `GET /rows` surfaces **Top Picks** and
   **Because You Watched …** with sensible neighbors and a `reason` on each card.
3. After ≥ `MODEL_MIN_SAMPLES` completed watches, `POST /retrain` returns metrics and a
   model pickle appears under `data/models/`; ordering reflects the re-ranker.
4. Detail page shows **More Like This**; thumbs up/down persists and re-ranks future rows.
5. `pytest` green (all offline).
