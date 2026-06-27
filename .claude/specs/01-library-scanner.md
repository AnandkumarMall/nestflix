# Spec: Library Scanner

## Overview
Walk the folders in `LIBRARY_PATHS`, discover video files, parse a clean title (and
season/episode for TV) from each messy filename, and persist the results to SQLite so the
rest of Nestflix has a real library to work with. This is the foundation every later
feature builds on: TMDB enrichment matches these parsed titles, the player streams these
files, and the recommender ranks these movies/shows. Before this feature the library is
empty stubs; after it, `GET /api/library` returns the user's actual movies and shows.

## Depends on
- Base scaffold — `media_files`, `movies`, `shows`, `episodes` tables and `get_db()`.

## API routes
- `POST /api/library/scan` — trigger a (re)scan of `LIBRARY_PATHS`; returns counts
  `{movies_added, episodes_added, files_seen, skipped}` — local/admin action.
- `GET /api/library` — replace the stub; return `{movies: [...], shows: [...]}` from the
  database (shows include their episodes grouped by season).

## Database changes
No schema changes — the base `schema.sql` already has every needed table and column.
(`movies.match_status` defaults to `'pending'`, which is correct until TMDB enrichment.)

## Backend modules
- **Create** `backend/titleparser.py`:
  - `parse(filename: str) -> ParsedTitle` using `guessit`, with a light regex fallback.
  - `ParsedTitle` dataclass: `kind` ('movie'|'episode'), `title`, `year`, `season`,
    `episode`. TV detected when guessit yields a season/episode.
- **Create** `backend/scanner.py`:
  - `VIDEO_EXTENSIONS` constant (`.mp4 .mkv .avi .mov .m4v .webm`).
  - `iter_video_files(roots) -> Iterator[Path]` — recursive walk, skips hidden/sample dirs.
  - `scan_library() -> ScanResult` — for each file: upsert `media_files` by unique `path`;
    if movie, upsert `movies` (parsed_title, year, kind='movie'); if episode, upsert the
    `shows` row by parsed show title then upsert the `episodes` row keyed by
    (show, season, episode). Idempotent: re-scanning does not duplicate rows.
- **Modify** `backend/db.py`: add helpers used by the scanner and the library route:
  - `upsert_media_file(path, size, mtime, container, kind) -> int`
  - `upsert_movie(media_file_id, parsed_title, year) -> int`
  - `upsert_show(parsed_title) -> int`
  - `upsert_episode(show_id, media_file_id, season, episode) -> int`
  - `get_library() -> dict` — movies + shows (with grouped episodes) as plain dicts.
- **Modify** `backend/routes/library.py`: wire `GET /api/library` to `get_library()` and
  add `POST /api/library/scan` calling `scan_library()`.

## Frontend
No frontend changes in this feature (the Home UI consuming this lands in the frontend
feature). Verification is via the API and tests.

## Files to change / create
- Create: `backend/titleparser.py`, `backend/scanner.py`, `tests/test_titleparser.py`,
  `tests/test_scanner.py`, `tests/conftest.py`
- Change: `backend/db.py`, `backend/routes/library.py`, `requirements.txt` (add pytest)

## New dependencies
- `pytest` (dev) for the test suite. `guessit` is already in `requirements.txt`.

## Rules for implementation
- DB logic stays in `backend/db.py` — the scanner calls helpers, never inlines SQL in the
  route handler.
- Parameterized SQL only.
- The scanner must be **idempotent** — re-running produces no duplicate rows (rely on the
  `UNIQUE` constraints + `INSERT ... ON CONFLICT` upserts).
- Title parsing must not crash on weird filenames — always fall back to a cleaned stem.
- No TMDB calls here — enrichment is a separate feature. `match_status` stays `'pending'`.

## Definition of done
- [ ] `POST /api/library/scan` walks every path in `LIBRARY_PATHS` and returns accurate
      counts.
- [ ] A movie file like `The.Matrix.1999.1080p.BluRay.mkv` parses to title "The Matrix",
      year 1999, kind movie, and creates one `movies` row.
- [ ] A TV file like `The.Office.S02E05.720p.mkv` parses to show "The Office", season 2,
      episode 5, and creates one `shows` row + one `episodes` row.
- [ ] Non-video files and hidden/`sample` directories are skipped.
- [ ] Re-running the scan does not create duplicate `media_files`, `movies`, `shows`, or
      `episodes` rows (idempotent).
- [ ] `GET /api/library` returns the scanned movies and shows (shows include episodes
      grouped by season).
- [ ] `pytest` passes, including new `test_titleparser.py` and `test_scanner.py` that use
      a temp dir of fake files and a temp database.
- [ ] No SQL in `backend/routes/library.py`; all queries go through `backend/db.py`.
