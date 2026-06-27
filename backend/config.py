"""Application configuration, loaded from environment / .env.

This is the ONLY place secrets and paths are read. Import `settings` everywhere else.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Project root is the parent of the backend/ package.
ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root if present (no-op if missing).
load_dotenv(ROOT_DIR / ".env")


def _split_paths(raw: str) -> list[Path]:
    """Parse LIBRARY_PATHS (semicolon-separated) into existing directory Paths."""
    paths: list[Path] = []
    for chunk in raw.split(";"):
        chunk = chunk.strip().strip('"')
        if chunk:
            paths.append(Path(chunk).expanduser())
    return paths


class Settings:
    """Resolved runtime settings. Constructed once as the module-level `settings`."""

    def __init__(self) -> None:
        self.tmdb_api_key: str = os.getenv("TMDB_API_KEY", "").strip()
        self.library_paths: list[Path] = _split_paths(os.getenv("LIBRARY_PATHS", ""))
        self.port: int = int(os.getenv("PORT", "8000"))

        # Some ISPs DNS-poison TMDB; resolve its hostnames via Cloudflare DoH when set.
        self.tmdb_use_doh: bool = os.getenv(
            "TMDB_USE_DOH", "true"
        ).strip().lower() not in (
            "0",
            "false",
            "no",
        )

        # Local data lives under data/ (gitignored): db, cached images, model.
        self.data_dir: Path = ROOT_DIR / "data"
        self.images_dir: Path = self.data_dir / "images"
        self.db_path: Path = self.data_dir / "nestflix.db"
        self.model_path: Path = self.data_dir / "taste_model.pkl"

        # Where the built frontend ends up (served by FastAPI in production).
        self.frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

    @property
    def tmdb_configured(self) -> bool:
        return bool(self.tmdb_api_key)

    def ensure_dirs(self) -> None:
        """Create local data directories if they don't exist yet."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
