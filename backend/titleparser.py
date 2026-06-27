"""Parse messy media filenames into clean titles and TV season/episode numbers.

Uses `guessit` (purpose-built for release-name parsing) with a light regex fallback so a
weird filename degrades to a cleaned stem instead of crashing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from guessit import guessit


@dataclass
class ParsedTitle:
    kind: str  # 'movie' | 'episode'
    title: str
    year: int | None = None
    season: int | None = None
    episode: int | None = None


# Tokens that commonly trail a title in release names; used only by the fallback.
_FALLBACK_NOISE = re.compile(
    r"\b(1080p|720p|2160p|4k|bluray|web[- ]?dl|webrip|hdrip|x264|x265|h264|h265|"
    r"hevc|aac|dts|bdrip|dvdrip|remux|proper|repack)\b.*$",
    re.IGNORECASE,
)
_SXXEYY = re.compile(r"[sS](\d{1,2})[eE](\d{1,3})")


def _clean_stem(stem: str) -> str:
    """Best-effort title cleanup when guessit gives us nothing usable."""
    text = stem.replace(".", " ").replace("_", " ").replace("-", " ")
    text = _FALLBACK_NOISE.sub("", text)
    text = re.sub(r"\(.*?\)|\[.*?\]", " ", text)  # drop bracketed groups
    return re.sub(r"\s+", " ", text).strip() or stem


def parse(filename: str) -> ParsedTitle:
    """Parse a filename (or full path) into a ParsedTitle.

    A title is treated as a TV episode when a season AND episode number are detected.
    """
    stem = Path(filename).stem

    try:
        info = guessit(filename)
    except Exception:
        info = {}

    title = (info.get("title") or "").strip()
    season = info.get("season")
    episode = info.get("episode")
    year = info.get("year")

    # guessit can return lists for multi-episode files; take the first.
    if isinstance(season, list):
        season = season[0] if season else None
    if isinstance(episode, list):
        episode = episode[0] if episode else None

    # Fallback title if guessit couldn't find one.
    if not title:
        title = _clean_stem(stem)
        if season is None and episode is None:
            m = _SXXEYY.search(stem)
            if m:
                season, episode = int(m.group(1)), int(m.group(2))
                # Title is whatever precedes the SxxExx marker.
                title = _clean_stem(stem[: m.start()]) or title

    is_episode = season is not None and episode is not None
    return ParsedTitle(
        kind="episode" if is_episode else "movie",
        title=title,
        year=int(year) if isinstance(year, int) else None,
        season=int(season) if is_episode else None,
        episode=int(episode) if is_episode else None,
    )
