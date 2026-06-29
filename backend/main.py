"""Nestflix application entry point.

Boots FastAPI, initializes the database, registers routers, and serves the built
frontend (frontend/dist) when present. Run with:

    uvicorn backend.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import tmdb
from .config import settings
from .db import init_db
from .routes import (
    discovery,
    images,
    library,
    playback,
    profiles,
    recommendations,
    stats,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure the database exists and is migrated before serving requests.
    init_db()
    yield
    # Release the shared TMDB HTTP client on shutdown.
    await tmdb.aclose()


app = FastAPI(title="Nestflix", version="0.1.0", lifespan=lifespan)

# During development the Vite dev server runs on a different origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers.
app.include_router(profiles.router)
app.include_router(library.router)
app.include_router(playback.router)
app.include_router(recommendations.router)
app.include_router(discovery.router)
app.include_router(images.router)
app.include_router(stats.router)


@app.get("/api/health")
async def health() -> dict:
    """Liveness probe + quick view of configuration state."""
    return {
        "status": "ok",
        "tmdb_configured": settings.tmdb_configured,
        "library_paths": [str(p) for p in settings.library_paths],
    }


# Serve the built frontend if it has been built; otherwise return a hint at root.
if settings.frontend_dist.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=settings.frontend_dist / "assets"),
        name="assets",
    )

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        """Serve the SPA index for any non-API path (client-side routing)."""
        index = settings.frontend_dist / "index.html"
        return FileResponse(index)

else:

    @app.get("/")
    async def root() -> JSONResponse:
        return JSONResponse(
            {
                "message": "Nestflix API is running. Build the frontend "
                "(cd frontend && npm run build) or start the Vite dev server "
                "(npm run dev) for the UI.",
                "docs": "/docs",
            }
        )
