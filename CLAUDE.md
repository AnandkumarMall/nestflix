# CLAUDE.md

## Project overview

Nestflix is a self-hosted, Netflix-style web app for a user's **local** movie & TV
library. It scans folders, enriches titles with TMDB metadata, streams video in the
browser with resume support, and recommends what to watch next using a taste model that
learns from viewing behavior.

---

## Architecture
```
nestflix/
├── backend/                  # Python + FastAPI
│   ├── main.py               # app entry; mounts routers + serves built frontend
│   ├── config.py             # loads .env (TMDB key, library paths, port)
│   ├── db.py                 # SQLite helpers: get_db(), init_db()
│   ├── schema.sql            # canonical schema (single source of truth)
│   ├── scanner.py            # walk LIBRARY_PATHS, find video files
│   ├── titleparser.py        # filename -> {title, year, season, episode} via guessit
│   ├── tmdb.py               # async TMDB client (search/details/recommendations/trending)
│   ├── enrich.py             # match scanned items to TMDB + cache metadata/images
│   ├── streaming.py          # HTTP range-request video streaming + subtitles
│   ├── recommender/
│   │   ├── features.py       # feature vectors from TMDB metadata
│   │   ├── taste_profile.py  # weighted taste vector from watch history
│   │   ├── model.py          # scikit-learn "will I finish this?" re-ranker (auto-retrain)
│   │   └── rows.py           # assemble home-screen rows
│   └── routes/               # one router per concern
│       ├── library.py        # browse/search the local library
│       ├── playback.py       # stream files, save/read watch progress
│       ├── recommendations.py# personalized rows
│       ├── discovery.py      # TMDB trending / new releases
│       └── profiles.py       # multi-profile CRUD + switching
├── frontend/                 # React + Vite + TypeScript
│   └── src/
│       ├── pages/            # Home, Detail, Player, Search, Stats
│       ├── components/       # PosterRow, PosterCard, VideoPlayer, NavBar, ProfileGate
│       └── api/              # typed fetch wrappers for the backend
├── data/                     # SQLite db, cached images, trained model (gitignored)
├── requirements.txt
└── .env                      # secrets (gitignored)
```

**Where things belong:**
- New API routes → a router in `backend/routes/`, registered in `main.py`. No business
  logic in route handlers — they parse input, call a helper, return a response.
- DB logic → `backend/db.py` and the `recommender/` modules. Never inline SQL in routes.
- TMDB calls → `backend/tmdb.py` only. Nothing else talks to the TMDB API directly.
- New pages → `frontend/src/pages/`; shared UI → `frontend/src/components/`.
- All backend↔frontend calls go through `frontend/src/api/`. No raw `fetch` in components.

---

## Code style

- **Python:** PEP 8, snake_case, type hints on public functions, formatted with `black`.
- **TypeScript/React:** function components + hooks, no class components. `camelCase`
  for variables, `PascalCase` for components. Prettier-formatted.
- **SQL:** always parameterized (`?` placeholders) — never f-strings/interpolation.
- **Async:** backend I/O (TMDB, file streaming) is `async`. Don't block the event loop.
- **Errors:** raise `HTTPException` for API errors — never return bare error strings.

---

## Tech constraints

- **Backend: FastAPI only** — no Flask/Django.
- **DB: SQLite only** — raw `sqlite3` via `get_db()`. No ORM, no external DB.
- **TMDB access is centralized** in `tmdb.py`; responses are cached in SQLite.
- **Frontend: React + Vite + TypeScript.** No other UI framework.
- **Secrets** come from `.env` via `config.py` — never hardcode the TMDB key.
- Adding a pip/npm package requires updating `requirements.txt` / `package.json` and
  flagging it in the spec's "New dependencies" section.

---

## Recommendation engine notes

- Single-user data is small — the learned model is intentionally lightweight (logistic
  regression / gradient boosting) to avoid overfitting.
- The **content-based** path must always work from day one (cold start); the learned
  re-ranker only kicks in past a watch-count threshold and **auto-retrains** every N
  completed watches.
- Recommendations must be explainable (surface the top contributing features).

---

## Subagent policy

- Use a builtin **Explore** subagent for codebase exploration before implementing a feature.
- Use a subagent to **verify test results** after any implementation.
- When asked to plan, delegate codebase research to a subagent before presenting the plan.
- Use a builtin **Plan** subagent in plan mode.

---

## Commands
```bash
# Backend setup
python -m venv .venv
source .venv/Scripts/activate            # PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Initialize the database (run once)
python -c "from backend.db import init_db; init_db()"

# Run the API (serves built frontend too)
uvicorn backend.main:app --reload --port 8000

# Frontend dev (hot reload)
cd frontend && npm install && npm run dev

# Build the frontend for production (served by FastAPI)
cd frontend && npm run build

# Tests
pytest                                   # backend
cd frontend && npm test                  # frontend
```

---

## Git & feature workflow

- **Spec-first, one feature per branch.** Never commit directly to `main`.
- `/create-spec <n> <feature>` → `feature/<slug>` branch + `.claude/specs/<nn>-<slug>.md`.
- Implement against the spec's Definition of Done.
- `/ship-feature` → commit (Conventional Commits), push, open PR, **squash-merge**,
  delete remote + local branch, return to `main`.
- Branch names: `feature/<kebab-slug>`. Commits: `feat:`, `fix:`, `chore:`, `docs:`.

---

## Warnings & things to avoid

- **Never** put SQL in route handlers — DB logic lives in `db.py` / `recommender/`.
- **Never** call the TMDB API outside `tmdb.py`.
- **Never** commit `.env`, the SQLite db, cached images, or the trained model (`data/`).
- **Never** hardcode the backend URL in frontend components — use `src/api/`.
- **`.mkv` does not play reliably in browsers** — detect and fall back to ffmpeg remux
  (optional dependency) or flag the file as "needs conversion." Don't assume it just works.
- **TMDB matching is imperfect** for obscure/foreign titles — always keep a manual "fix
  match" path and degrade gracefully when there's no match.
- **Rate-limit** TMDB calls and cache aggressively — don't re-fetch on every launch.
