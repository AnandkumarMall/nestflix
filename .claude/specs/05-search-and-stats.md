# Spec: Search and Stats Pages

## Overview

Phases 01–04 shipped scanner, TMDB enrichment, streaming player, and recommendations engine.
This spec closes the two remaining pages from CLAUDE.md's target architecture:

1. **Search page** — wires the existing `GET /api/library/search` backend endpoint. NavBar
   search box navigates to `/search?q=...`, rendering local library matches as PosterCards
   with quick links to Detail or direct playback.

2. **Stats page** — new per-profile dashboard aggregating viewing history into metrics:
   hours watched, titles finished, top genres (CSS bar chart), thumbs ratings, recently
   finished titles. Backend aggregates from existing tables; schema unchanged.

Once shipped, Nestflix has all 5 target pages (Home, Detail, Player, Search, Stats) per
CLAUDE.md.

---

## Where things live (per CLAUDE.md)

- `backend/db.py` — `get_profile_stats()` helper (no new tables, no migration).
- `backend/routes/stats.py` — `GET /api/stats?profile_id=` handler (new file).
- `backend/main.py` — register stats router.
- `frontend/src/pages/Search.tsx` — search results page (new file).
- `frontend/src/pages/Stats.tsx` — stats dashboard (new file).
- `frontend/src/pages/Home.tsx` — import `matchScore` from utils.
- `frontend/src/api/client.ts` — `SearchResult` type + `api.searchLibrary()` + `api.stats()`.
- `frontend/src/components/NavBar.tsx` — search input form + Stats link.
- `frontend/src/App.tsx` — routes `/search` and `/stats`.
- `frontend/src/utils.ts` — `matchScore()` shared helper.
- `frontend/src/styles.css` — search box, stats cards, genre bars (responsive).
- `tests/test_stats.py` — backend stats aggregation tests (new file).

---

## Definition of Done

### Backend
- `db.py:get_profile_stats(conn, profile_id, *, top_genres=8, recent=10)` → dict:
  - `titles_finished` — count of `watch_progress.completed=1` for profile.
  - `seconds_watched` — sum of all `watch_progress.position_seconds`.
  - `ratings` — `{up: #thumbs↑, down: #thumbs↓}` from ratings table.
  - `top_genres` — list of `{name, count}`, top N by frequency, excludes unmatched.
  - `recently_finished` — last N finished titles (kind, id, title, poster_path).
  - Empty profile → all zeros + empty lists (no crash).

- `routes/stats.py`:
  - `GET /api/stats?profile_id=<int>` handler.
  - Validates `profile_id >= 1` (400 if not).
  - Calls `db.get_profile_stats()`, returns it.
  - Documents unauthenticated access (trusted-network-only design).

- `main.py` — `include_router(stats.router)`.

### Frontend
- `pages/Search.tsx`:
  - Reads `?q=` from URL (via `useSearchParams`).
  - Calls `api.searchLibrary(q)`.
  - Renders results as PosterRow of PosterCards.
  - Links to `/title/:kind/:id` or direct playback `/watch/:mediaFileId`.
  - Empty query → prompt; no results → "No matches".
  - No debounce (search on navigate only).

- `pages/Stats.tsx`:
  - Uses `useProfile()` to get active profile id.
  - Calls `api.stats(profileId)`.
  - Renders stat cards (titles, hours, thumbs).
  - Renders genre bar chart (CSS, no charting lib).
  - Renders "Recently Finished" row via PosterRow + PosterCards.
  - Empty profile → shows prompt "Finish something to start building your stats."

- `api/client.ts`:
  - `SearchResult` type = `Movie | Show` union with `type: "movie" | "show"`.
  - `Stats` interface (profile_id, titles_finished, seconds_watched, ratings, top_genres,
    recently_finished).
  - `api.searchLibrary(q)` → `{query, results: SearchResult[]}`.
  - `api.stats(profileId)` → Stats.

- `components/NavBar.tsx`:
  - Search form: `<input>` + submit → navigate to `/search?q=...` (URL-encoded).
  - Stats link in nav-links.
  - No page-specific search state persistence.

- `App.tsx`:
  - Routes: `/search` → Search, `/stats` → Stats.
  - NavBar visible on both (not player route).

- `utils.ts`:
  - `matchScore(rating)` → shared helper, imported by Home + Search pages.

- `styles.css`:
  - `.nav-search*` — form + input, responsive width (180px → 120px on mobile).
  - `.stats*` — cards, headings, genre bars, labels (responsive: 120px → 80px on mobile).
  - `.stat-card` — min-width 140px, wraps on mobile.
  - `.genre-bar-label` — text-overflow ellipsis on small screens.

### Tests (offline, no TMDB/network)
- `test_stats.py`:
  - `test_stats_empty_profile()` — zeroed totals + empty lists.
  - `test_stats_with_watches()` — after seeding 3 titles (2 movies + 1 show episode) and
    ratings, stats aggregate correctly (count, seconds, genres, recently_finished).
  - `test_stats_route()` — `GET /api/stats?profile_id=N` happy path.
  - All 66 backend tests pass (including new test_stats.py).

---

## Quality & Security

### Quality
- `matchScore()` extracted to utils.ts (no duplication in Home + Search).
- All SQL parameterized (no injection).
- Router handlers thin (validation + call db helper + return).
- No dead code, no console.log.
- Frontend TypeScript builds clean.

### Security
- `/api/stats?profile_id=` unauthenticated; validates `profile_id >= 1`; documented as
  trusted-network-only (acceptable for local home setup).
- XSS safe (React escapes text nodes; no `dangerouslySetInnerHTML`).
- No secrets hardcoded.
- File paths in search results (not rendered in UI, low risk).

---

## Out of scope (later)
- Charting library (stats bars are CSS).
- Auth/multi-device profiles (current single-user trusted-network design).
- Search filters/advanced queries (current simple case-insensitive contain).
- Stats export (CSV, etc.).

---

## New dependencies
None. (Stats use existing SQLite + CSS; search uses existing backend.)

---

## Verification

1. Fresh profile → `/stats` renders zeroed cards + prompt.
2. Search box → type 'chainsaw' → `/search?q=chainsaw` shows matches as PosterCards.
3. Click search result → Detail page.
4. Finish a title + thumbs it → `/stats` now shows count in cards + genre.
5. Responsive: shrink browser → search box + genre labels resize correctly.
6. `pytest tests/test_stats.py` passes; `npm run build` clean; all 66 backend tests green.

---

## Implementation notes

- Build on `feature/search-and-stats` branch per spec-first workflow.
- Implement in ponytail mode: reuse existing components (PosterRow, PosterCard, matchScore),
  no speculative abstractions.
- Test locally before shipping via `/verify` skill.
- Review for quality + security before merge.
