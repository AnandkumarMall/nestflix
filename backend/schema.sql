-- Nestflix schema — canonical source of truth for the SQLite database.
-- Applied by backend.db.init_db(). Uses IF NOT EXISTS so it is safe to re-run.

PRAGMA foreign_keys = ON;

-- Viewers. Recommendations and watch history are per-profile so tastes don't blend.
CREATE TABLE IF NOT EXISTS profiles (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    avatar_color TEXT NOT NULL DEFAULT '#e50914',
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every video file discovered on disk. One row per physical file.
CREATE TABLE IF NOT EXISTS media_files (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    path      TEXT NOT NULL UNIQUE,
    size      INTEGER NOT NULL,
    mtime     REAL NOT NULL,
    container TEXT NOT NULL,                 -- file extension, e.g. mkv / mp4
    kind      TEXT NOT NULL,                 -- 'movie' | 'episode'
    added_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- A movie, backed by exactly one media file, enriched from TMDB.
CREATE TABLE IF NOT EXISTS movies (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    media_file_id INTEGER NOT NULL UNIQUE REFERENCES media_files(id) ON DELETE CASCADE,
    tmdb_id       INTEGER,
    parsed_title  TEXT NOT NULL,             -- title parsed from the filename
    title         TEXT,                      -- canonical TMDB title
    year          INTEGER,
    overview      TEXT,
    poster_path   TEXT,
    backdrop_path TEXT,
    rating        REAL,                      -- TMDB vote_average
    runtime       INTEGER,                   -- minutes
    genres        TEXT,                      -- JSON array of genre names
    cast          TEXT,                      -- JSON array of top-billed names
    keywords      TEXT,                      -- JSON array of TMDB keyword names
    match_status  TEXT NOT NULL DEFAULT 'pending'  -- pending | matched | unmatched
);

-- A TV show (grouping of episodes), enriched from TMDB.
CREATE TABLE IF NOT EXISTS shows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    tmdb_id       INTEGER,
    parsed_title  TEXT NOT NULL,
    title         TEXT,
    year          INTEGER,
    overview      TEXT,
    poster_path   TEXT,
    backdrop_path TEXT,
    rating        REAL,
    genres        TEXT,
    keywords      TEXT,
    match_status  TEXT NOT NULL DEFAULT 'pending',
    UNIQUE (parsed_title)
);

-- An episode, backed by one media file, belonging to a show.
CREATE TABLE IF NOT EXISTS episodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    show_id       INTEGER NOT NULL REFERENCES shows(id) ON DELETE CASCADE,
    media_file_id INTEGER NOT NULL UNIQUE REFERENCES media_files(id) ON DELETE CASCADE,
    season        INTEGER NOT NULL,
    episode       INTEGER NOT NULL,
    title         TEXT,
    overview      TEXT,
    still_path    TEXT,
    UNIQUE (show_id, season, episode)
);

-- Cache of raw TMDB responses, keyed by request, to avoid refetching.
CREATE TABLE IF NOT EXISTS tmdb_cache (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key  TEXT NOT NULL UNIQUE,         -- e.g. 'search/movie?q=matrix&y=1999'
    response   TEXT NOT NULL,                -- raw JSON
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Resume support + Continue Watching. One row per (profile, media file).
CREATE TABLE IF NOT EXISTS watch_progress (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id       INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    media_file_id    INTEGER NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    position_seconds REAL NOT NULL DEFAULT 0,
    duration_seconds REAL NOT NULL DEFAULT 0,
    completed        INTEGER NOT NULL DEFAULT 0,
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (profile_id, media_file_id)
);

-- Explicit signals (thumbs up/down) feeding the taste model.
CREATE TABLE IF NOT EXISTS ratings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    movie_id   INTEGER REFERENCES movies(id) ON DELETE CASCADE,
    show_id    INTEGER REFERENCES shows(id) ON DELETE CASCADE,
    value      INTEGER NOT NULL,             -- +1 (up) or -1 (down)
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Behavioral log used as training data for the "will I finish this?" model.
CREATE TABLE IF NOT EXISTS watch_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id    INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    media_file_id INTEGER NOT NULL REFERENCES media_files(id) ON DELETE CASCADE,
    event         TEXT NOT NULL,             -- 'start' | 'progress' | 'finish' | 'abandon'
    pct           REAL NOT NULL DEFAULT 0,   -- fraction watched at event time
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_progress_profile ON watch_progress(profile_id);
CREATE INDEX IF NOT EXISTS idx_events_profile ON watch_events(profile_id);
CREATE INDEX IF NOT EXISTS idx_episodes_show ON episodes(show_id);
