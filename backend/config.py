"""Application configuration, loaded from environment / .env.

This is the ONLY place secrets and paths are read. Import `settings` everywhere else.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

# Project root is the parent of the backend/ package.
ROOT_DIR = Path(__file__).resolve().parent.parent

# Load .env from the project root if present (no-op if missing).
load_dotenv(ROOT_DIR / ".env")


def _find_binary(name: str) -> str:
    """Resolve an executable from PATH, falling back to known winget install dirs.

    winget updates PATH only for *new* processes, so a server started in an old shell
    may not see ffmpeg on PATH yet — scan the package dir as a backstop.
    """
    found = shutil.which(name)
    if found:
        return found
    local = os.getenv("LOCALAPPDATA")
    if local:
        pattern = f"Microsoft/WinGet/Packages/*FFmpeg*/**/bin/{name}.exe"
        for candidate in Path(local).glob(pattern):
            if candidate.is_file():
                return str(candidate)
    return ""


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
        self.tmdb_use_doh: bool = os.getenv("TMDB_USE_DOH", "true").strip().lower() not in (
            "0",
            "false",
            "no",
        )

        # Local data lives under data/ (gitignored): db, cached images, models.
        self.data_dir: Path = ROOT_DIR / "data"
        self.images_dir: Path = self.data_dir / "images"
        self.db_path: Path = self.data_dir / "nestflix.db"
        # One persisted "will I finish this?" model per profile.
        self.models_dir: Path = self.data_dir / "models"

        # Recommendation engine knobs. The content-based path always runs; the learned
        # re-ranker only activates past MODEL_MIN_SAMPLES completed watches and retrains
        # every RETRAIN_EVERY completed watches (keeps the tiny single-user model fresh
        # without overfitting).
        self.model_min_samples: int = int(os.getenv("MODEL_MIN_SAMPLES", "12"))
        self.retrain_every: int = int(os.getenv("RETRAIN_EVERY", "5"))

        # Where the built frontend ends up (served by FastAPI in production).
        self.frontend_dist: Path = ROOT_DIR / "frontend" / "dist"

        # ffmpeg/ffprobe are an OPTIONAL system dependency used to remux/transcode
        # containers and codecs browsers can't play natively (mkv, HEVC, AC3, ...) and to
        # extract embedded subtitles. Absent → the app still streams natively-playable
        # files and surfaces a clear "needs ffmpeg" state for the rest. Paths may be
        # overridden via .env; otherwise we look them up on PATH.
        self.ffmpeg_path: str = os.getenv("FFMPEG_PATH", "").strip() or _find_binary("ffmpeg")
        self.ffprobe_path: str = os.getenv("FFPROBE_PATH", "").strip() or _find_binary("ffprobe")
        # x264 transcode quality/speed knobs (sane defaults; rarely changed).
        self.transcode_preset: str = os.getenv("TRANSCODE_PRESET", "veryfast").strip()
        self.transcode_crf: int = int(os.getenv("TRANSCODE_CRF", "23"))

    @property
    def tmdb_configured(self) -> bool:
        return bool(self.tmdb_api_key)

    @property
    def ffmpeg_available(self) -> bool:
        """True when both ffmpeg and ffprobe are resolvable (enables remux/transcode)."""
        return bool(self.ffmpeg_path and self.ffprobe_path)

    def ensure_dirs(self) -> None:
        """Create local data directories if they don't exist yet."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.models_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
