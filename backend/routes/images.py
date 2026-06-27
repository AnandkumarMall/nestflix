"""Serve cached TMDB images from disk, fetching them through DoH on first request.

The frontend points <img> tags at this router instead of image.tmdb.org so it never hits
the (possibly DNS-poisoned) TMDB host directly — the backend fetches and caches once.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .. import enrich
from ..config import settings
from ..tmdb import TMDBError

router = APIRouter(prefix="/api/images", tags=["images"])

# Sizes we allow proxying (matches TMDB's poster/backdrop/still buckets).
_ALLOWED_SIZES = {"w92", "w154", "w185", "w342", "w500", "w780", "original"}

# TMDB image paths are a single opaque filename, e.g. "abc123XYZ.jpg". Reject anything
# else so a crafted path can never escape data/images/ (path traversal).
_IMAGE_NAME = re.compile(r"^[A-Za-z0-9]+\.(jpg|jpeg|png|webp)$")


@router.get("/{size}/{tmdb_path}")
async def get_image(size: str, tmdb_path: str) -> FileResponse:
    """Return a cached image by TMDB path, downloading it once if needed."""
    if size not in _ALLOWED_SIZES:
        raise HTTPException(status_code=400, detail="unsupported image size")
    if not _IMAGE_NAME.match(tmdb_path):
        raise HTTPException(status_code=400, detail="invalid image path")
    if not settings.tmdb_configured:
        raise HTTPException(status_code=400, detail="TMDB_API_KEY is not configured")
    try:
        dest = await enrich.ensure_image_cached(tmdb_path, size)
    except TMDBError as exc:
        raise HTTPException(status_code=502, detail=f"TMDB error: {exc}") from exc
    if dest is None or not dest.exists():
        raise HTTPException(status_code=404, detail="image not available")
    return FileResponse(dest)
