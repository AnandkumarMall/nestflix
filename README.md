# Nestflix 🎬

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue)](https://www.python.org/)
[![Node 16+](https://img.shields.io/badge/Node-16%2B-green)](https://nodejs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Netflix-style web app for your **local** movie & TV library. Scan folders, browse with beautiful posters,
stream with instant resume, and get personalized recommendations that learn from what you actually watch.
No cloud uploads, no subscriptions, no tracking — just you, your videos, and [TMDB](https://www.themoviedb.org/) metadata.

## What you get

- **📂 Auto-scan folders** — point at a directory, Nestflix finds video files and parses titles (no manual tagging)
- **🖼️ Rich metadata** — TMDB posters, backdrops, synopses, cast, genres, ratings (cached locally, zero internet after first sync)
- **⏳ Resume anywhere** — close mid-episode, return days later, player resumes exactly where you left off
- **📺 Movies + TV series** — full season/episode support with next-episode autoplay
- **🤖 Learn your taste** — system learns what you *finish* (not just click), auto-ranks home rows by what you'll actually watch
- **🔎 Search & filter** — find titles, browse by genre, sort by rating
- **🎬 Discovery rows** — trending on TMDB, new releases, "because you watched X" recommendations
- **👥 Multi-profile** — separate profiles per family member with independent watch history and taste models
- **📊 Stats & wrapped** — hours watched, top genres, most rewatched, year-in-review breakdown
- **▶️ Snappy playback** — HTTP range requests for instant seeking, subtitle support, no buffering
- **📡 Offline mode** — browse & watch your local library without internet; cached metadata still works

## Requirements

| Item | Details |
|------|---------|
| **OS** | Windows, macOS, Linux |
| **Python** | 3.9 or later |
| **Node.js** | 16 or later |
| **TMDB API Key** | Free at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api) |
| **Video library** | Local folder(s) with video files |

**Supported video formats:** `.mp4`, `.mkv`, `.avi`, `.mov`, `.flv`, `.m4v`, `.webm`

> **Note:** `.mkv` playback in browsers is inconsistent. If you have `.mkv` files and encounter issues, consider transcoding to `.mp4` or using ffmpeg remux (see [Troubleshooting](#troubleshooting)).

## Setup

### 1. Clone & create virtual environment

```bash
git clone <repo-url>
cd nestflix

# Create virtual environment
python -m venv .venv

# Activate it
# On Windows (Git Bash or PowerShell)
.venv\Scripts\activate
# On macOS/Linux
source .venv/bin/activate
```

### 2. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your details:

```env
# Get your free key from https://www.themoviedb.org/settings/api
TMDB_API_KEY=your_api_key_here

# Paths to your video folders (use semicolon on Windows, colon on Unix)
LIBRARY_PATHS=/path/to/movies:/path/to/shows

# Server port
PORT=8000
```

### 4. Initialize database

```bash
python -c "from backend.db import init_db; init_db()"
```

### 5. Install frontend dependencies

```bash
cd frontend && npm install && cd ..
```

### 6. Build frontend (production) or start dev server

**Production (build once, run with FastAPI):**
```bash
cd frontend && npm run build && cd ..
```

**Development (hot reload):**
```bash
cd frontend && npm run dev
```

### 7. Start the app

**Option A: Backend only (frontend already built)**
```bash
uvicorn backend.main:app --reload --port 8000
```
Visit `http://localhost:8000`

**Option B: Backend + frontend dev server (for frontend development)**
```bash
# Terminal 1: backend
uvicorn backend.main:app --reload --port 8000

# Terminal 2: frontend hot reload
cd frontend && npm run dev
```
Visit the URL shown by Vite (usually `http://localhost:5173`)

## Configuration

All settings live in `.env`. Here's what each does:

| Variable | Purpose | Example |
|----------|---------|---------|
| `TMDB_API_KEY` | TMDB metadata (posters, synopses, ratings) | `abc123xyz...` |
| `LIBRARY_PATHS` | Folders to scan for videos | `/mnt/videos:/home/user/shows` |
| `PORT` | Server port | `8000` |
| `DB_PATH` | SQLite database location | `data/nestflix.db` |

**Multiple library paths:**
- **Windows:** Use semicolons: `C:\Videos;E:\Movies`
- **macOS/Linux:** Use colons: `/mnt/videos:/home/user/shows`

**First run:** The scanner indexes your entire library on startup — this can take several minutes for large collections. Subsequent runs only check for new/modified files.

## Usage

### First time: Add your library

1. **Start the app** (see Setup above)
2. **Open the browser** to `http://localhost:8000`
3. **Scan your library** — the app auto-scans on startup; check the backend logs for progress
4. **Wait for TMDB enrichment** — titles are matched to TMDB and posters are cached (may take a few minutes for large libraries)
5. **Browse** — home page shows trending, recommendations, and your library by genre

### Ongoing

- **Resume playback:** Click a title, player remembers where you stopped
- **Next episode:** TV series auto-play the next episode when you finish
- **Recommendations:** Home page shows rows tailored to your watch history (learns after ~10 watched items)
- **Search:** Find titles by name, filter by genre
- **Profiles:** Switch profiles to keep family members' tastes separate
- **Stats:** See your wrapped stats (hours watched, top genres)

## How recommendations work

Nestflix learns your taste in two stages:

1. **Content-based** (day one) — similar titles by genre, director, cast from your local library (works immediately)
2. **Personalized** (after ~10 watched items) — trains a lightweight model on what you *finish* vs. what you abandon, re-ranks home rows with your taste

**Note:** Recommendations show titles *already in your local library* sorted by similarity to what you've watched. To discover new titles not on your computer, check the **Trending** and **New Releases** sections (powered by TMDB).

Tip: Mark titles with 👍/👎 to influence recommendations — thumbs up pulls recommendations toward that title, thumbs down repels.

Each profile learns independently, so household members don't influence each other's recommendations.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **No titles found after scanning** | Check `LIBRARY_PATHS` in `.env` exists and is readable. Verify file extensions are supported (`.mp4`, `.mkv`, etc.). Check backend logs for `[ERROR]` lines. |
| **TMDB API errors / rate limiting** | Verify your API key at [themoviedb.org/settings/api](https://www.themoviedb.org/settings/api). If rate-limited (40 req/10s), wait 10 min. Check `data/tmdb_cache.db` exists. |
| **`.mkv` files won't play or audio is out of sync** | Browser support for MKV is inconsistent (Firefox > Chrome). If audio/video is misaligned or won't load:<br>- Try Firefox or a different browser<br>- Transcode to `.mp4`: `ffmpeg -i file.mkv -c copy file.mp4` (fast, lossless)<br>- Use a media server with native MKV support (Jellyfin, Plex) |
| **Slow initial scan** | First run indexes entire library — expect **several minutes** for 500+ titles. Subsequent scans only re-check modified files. Check logs: `[INFO] Scanned: X/Y` |
| **Port already in use** | Change `PORT` in `.env` to unused port (e.g., `8001`). Or kill process: `lsof -i :8000 \| grep LISTEN \| awk '{print $2}' \| xargs kill -9` |
| **Database locked / can't start** | Ensure only one instance runs. If `data/nestflix.db` corrupted, delete it and re-run: `python -c "from backend.db import init_db; init_db()"` |
| **Subtitle files not showing** | Place subtitle files in the **same folder** as the video with matching filename stem. E.g.:<br>- Video: `movie.mkv`<br>- Subtitle: `movie.srt` (not `movie_en.srt` or `subs/movie.srt`)<br>Supported formats: SRT, VTT, ASS<br>Tip: Check backend logs to confirm subtitles were detected. |

---

## Architecture

**Backend** (Python + FastAPI):
- `main.py` — entry point, mounts routers, serves built frontend
- `scanner.py` — walks `LIBRARY_PATHS`, finds video files
- `titleparser.py` — parses `movie.mkv` → `{title, year, season, episode}` via guessit
- `tmdb.py` — TMDB API client with caching + DoH fallback
- `enrich.py` — matches scanned titles to TMDB, caches posters/metadata
- `streaming.py` — HTTP range-request video streaming + subtitle support
- `recommender/` — taste model (gradient boosting), feature vectors, home-page row assembly
- `routes/` — API endpoints (library, playback, recommendations, profiles, stats)

**Frontend** (React + Vite + TypeScript):
- `pages/` — Home, Detail, Player, Search, Stats
- `components/` — PosterRow, PosterCard, VideoPlayer, NavBar, ProfileGate
- `api/` — typed fetch wrappers for backend endpoints

**Database** (SQLite):
- Stores library metadata, watch history, profiles, taste models, cached TMDB data

**Workflow:**
1. Scanner finds video files, parses titles
2. Enrich module matches titles to TMDB, caches metadata + images
3. Frontend fetches library, plays videos, tracks watch position
4. Recommender learns from watch history, ranks home-page rows
5. Multi-profile isolation keeps family members' tastes separate

See [CLAUDE.md](./CLAUDE.md) for full architecture, code conventions, and how to contribute.

## License

MIT

---

## Contributing

Nestflix follows a spec-first, feature-branch workflow. See [CLAUDE.md](./CLAUDE.md) for architecture and conventions.
