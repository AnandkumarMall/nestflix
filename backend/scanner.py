"""Walk the configured library folders, parse titles, and persist them to SQLite.

The scanner is idempotent: re-running it updates existing rows rather than duplicating
them (the DB upsert helpers rely on the schema's UNIQUE constraints). It performs no TMDB
calls — matching/enrichment is a separate feature; new rows start as match_status
'pending'.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from . import db, titleparser
from .config import settings

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".m4v", ".webm"}

# Directory names we never descend into.
_SKIP_DIRS = {"sample", "samples", "extras", "featurettes", "subs", "subtitles"}


@dataclass
class ScanResult:
    files_seen: int = 0
    movies_added: int = 0
    episodes_added: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


def iter_video_files(roots: Iterable[Path]) -> Iterator[Path]:
    """Yield video files under the given roots, skipping hidden and sample directories."""
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_dir():
                continue
            parts_lower = {p.lower() for p in path.parts}
            if any(p.startswith(".") for p in path.parts):
                continue  # hidden file or hidden directory anywhere in the path
            if parts_lower & _SKIP_DIRS:
                continue
            if path.suffix.lower() in VIDEO_EXTENSIONS:
                yield path


def scan_library(roots: Iterable[Path] | None = None) -> ScanResult:
    """Scan the library and upsert movies/shows/episodes. Returns counts."""
    roots = list(roots) if roots is not None else settings.library_paths
    result = ScanResult()

    conn = db.get_db()
    try:
        for path in iter_video_files(roots):
            result.files_seen += 1
            try:
                stat = path.stat()
                parsed = titleparser.parse(path.name)
                container = path.suffix.lower().lstrip(".")

                media_file_id = db.upsert_media_file(
                    conn,
                    path=str(path),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    container=container,
                    kind=parsed.kind,
                )

                if parsed.kind == "episode":
                    show_id = db.upsert_show(conn, parsed.title)
                    db.upsert_episode(
                        conn,
                        show_id=show_id,
                        media_file_id=media_file_id,
                        season=parsed.season,
                        episode=parsed.episode,
                    )
                    result.episodes_added += 1
                else:
                    db.upsert_movie(conn, media_file_id, parsed.title, parsed.year)
                    result.movies_added += 1
            except Exception as exc:  # never let one bad file abort the whole scan
                result.skipped += 1
                result.errors.append(f"{path}: {exc}")
        conn.commit()
    finally:
        conn.close()

    return result
