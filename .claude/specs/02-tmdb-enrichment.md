# Spec: TMDB Enrichment & Caching

## Overview

The scanner (feature 01) fills the library with rows parsed from filenames —
`parsed_title`, `year`, `season/episode` — but no posters, overviews, ratings, or
genres. This feature matches each scanned movie/show to a TMDB record, pulls real
metadata, caches everything in SQLite, and downloads poster/backdrop images to disk so
the UI loads instantly and works offline after the first fetch.

It also lights up the **discovery** rows (Trending, New Releases) that pull straight from
TMDB for titles the user doesn't own yet.

All TMDB access is centralized in `backend/tmdb.py` (per CLAUDE.md) and cached
aggressively in the `tmdb_cache` table.

## Network constraint (important)

The target user's ISP **DNS-poisons `api.themoviedb.org` / `image.tmdb.org`** — direct
requests time out (verified: `nslookup` returns an Indian-ISP blackhole IP). The fix,
verified working in-session, is to resolve TMDB hostnames via **Cloudflare DNS-over-HTTPS
(1.1.1.1)** and connect to the real IP, leaving TLS SNI + certificate verification against
the original hostname (exactly like `curl --resolve`). This is implemented as a scoped
`socket.getaddrinfo` override that only rewrites the two TMDB hostnames and falls through
for everything else. Toggle with `TMDB_USE_DOH` (default `true`).

## Definition of Done

- `backend/tmdb.py` — async `httpx` client with:
  - `search_movie(title, year)`, `search_tv(title, year)`, `movie_details(id)`,
    `tv_details(id)`, `movie_recommendations(id)`, `trending(media_type, window)`,
    `get_image(path, size)`.
  - SQLite response cache (`tmdb_cache`) keyed by path+params, with an optional max-age.
  - DoH resolver (scoped, toggleable), retry/backoff on timeouts + HTTP 429.
  - Raises `HTTPException`-friendly errors; never leaks the API key into logs/responses.
- `backend/enrich.py` — match pending movies/shows to TMDB, write metadata back, set
  `match_status` (`matched` / `unmatched`), and cache poster/backdrop images to
  `data/images/`. Idempotent and rate-limited.
- DB helpers in `backend/db.py` for cache get/put, listing pending items, and writing
  enriched metadata (no SQL in routes).
- Routes:
  - `POST /api/library/enrich` — enrich pending items, returns counts.
  - `GET  /api/library/movies/{id}/matches?q=` + `POST /api/library/movies/{id}/match`
    — manual "fix match" path for imperfect/foreign titles.
  - `GET  /api/discovery/trending`, `GET /api/discovery/new-releases` — real data.
  - `GET  /api/images/{size}/{tmdb_path}` — serve a cached image, fetching through DoH on
    first request (so the frontend never hits the poisoned hostname directly).
- Graceful degradation: no TMDB key → endpoints return empty/clear errors, scan + browse
  still work. No network → enrichment marks items `unmatched`, doesn't crash.
- Tests (mocked TMDB, offline): cache key/get/put, DoH resolver fallthrough, match
  selection (year tiebreak), enrich writes metadata + sets status, unmatched path.

## Out of scope (later phases)

- Streaming/playback and the player UI (feature 03).
- The recommendation engine using these features (feature 04).
- The Netflix-style frontend rows/detail UI (feature 05) — this feature only exposes the
  API; the React side consumes it later.

## New dependencies

None — `httpx` is already in `requirements.txt`. DoH uses `httpx` + stdlib `socket`.

## Verification

1. `POST /api/library/scan` then `POST /api/library/enrich` → known titles get posters,
   overviews, genres; `GET /api/library` shows `match_status: matched`.
2. Obscure/foreign title that mis-matches → `GET .../matches` lists candidates,
   `POST .../match` corrects it.
3. `GET /api/discovery/trending` returns TMDB trending items.
4. `GET /api/images/w342/<path>` returns image bytes (cached on disk after first call).
5. `pytest` green (all mocked — no live network needed).
