# Nestflix 🎬

A Netflix-style web app for your **local** movie & TV library. Point it at a folder
and get poster walls, genre rows, search, an in-browser player that **resumes where you
left off**, and a recommendation engine that **learns your taste** — enriched with
metadata and discovery from [TMDB](https://www.themoviedb.org/).

## Features

- 📂 **Library scanner** — walks your folders, finds video files, parses clean titles
- 🖼️ **TMDB enrichment** — posters, backdrops, synopses, cast, genres, ratings (cached)
- ▶️ **Streaming player** — HTTP range requests for instant seeking + subtitles
- ⏯️ **Resume & Continue Watching** — picks up exactly where you stopped
- 📺 **Movies + TV series** — seasons/episodes with next-episode autoplay
- 🤖 **Recommendations** — content-based + an auto-retraining model that learns what you finish
- 🔎 **Discovery** — Trending / New Releases / "Because you watched…" from TMDB
- 👥 **Multi-profile** — separate tastes per viewer
- 📊 **Stats / Wrapped** — hours watched, top genres, most rewatched

## Tech stack

- **Backend:** Python + FastAPI, SQLite, scikit-learn
- **Frontend:** React + Vite + TypeScript
- **Metadata:** TMDB API

## Quick start

```bash
# 1. Backend
python -m venv .venv
source .venv/Scripts/activate          # Windows (Git Bash). PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                    # then fill in TMDB_API_KEY and LIBRARY_PATHS

# 2. Frontend
cd frontend && npm install && cd ..

# 3. Run (dev)
uvicorn backend.main:app --reload --port 8000   # API + serves built frontend
cd frontend && npm run dev                       # Vite dev server (hot reload)
```

Open http://localhost:8000 (or the Vite dev URL during frontend development).

## Project workflow

Nestflix is built **spec-first, one feature per branch**:

1. `/create-spec <n> <feature>` — creates `feature/<slug>` + a spec in `.claude/specs/`
2. Review the spec, then implement in plan mode
3. `/ship-feature` — commit, push, open PR, squash-merge, clean up branches

See [CLAUDE.md](./CLAUDE.md) for architecture and conventions.

## License

MIT
