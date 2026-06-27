"""Probe media files with ffprobe and decide how to play them in a browser.

ffmpeg/ffprobe are an OPTIONAL system dependency (see `config.ffmpeg_available`). When
they are absent we fall back to a container-only guess so natively-playable files still
work and everything else is flagged ``unavailable`` instead of crashing.
"""

from __future__ import annotations

import json
import logging
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings

logger = logging.getLogger(__name__)

# Containers a browser <video> can demux directly.
_DIRECT_CONTAINERS = {"mp4", "m4v", "webm"}
# Video/audio codecs browsers decode natively.
_SAFE_VIDEO = {"h264", "avc1", "vp8", "vp9", "av1"}
_SAFE_AUDIO = {"aac", "mp3", "opus", "vorbis"}
# Embedded subtitle codecs we can turn into WebVTT (text-based only — image subs like
# PGS/VOBSUB can't be converted to text and are skipped).
_TEXT_SUBTITLE_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"}


@dataclass
class SubtitleStream:
    """One embedded subtitle stream from ffprobe."""

    index: int  # ffmpeg stream index, used with `-map 0:<index>`
    codec: str
    language: str | None
    title: str | None
    text_based: bool  # False for image subs we can't convert to WebVTT


@dataclass
class MediaInfo:
    """The streams/format facts we need to choose a play mode and show metadata."""

    container: str
    video_codec: str | None
    audio_codec: str | None
    duration_seconds: float
    width: int | None
    height: int | None
    subtitles: list[SubtitleStream] = field(default_factory=list)


def ffmpeg_available() -> bool:
    """True when ffmpeg + ffprobe are usable (remux/transcode/subtitle extraction)."""
    return settings.ffmpeg_available


# Probe results are cached in-process, keyed by (path, mtime) so an edited/replaced file
# is re-probed but repeat requests for the same file are free.
_probe_cache: dict[tuple[str, float], MediaInfo | None] = {}


def probe(path: Path) -> MediaInfo | None:
    """Probe a media file. Returns None if ffprobe is unavailable or the probe fails."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    key = (str(path), mtime)
    if key in _probe_cache:
        return _probe_cache[key]
    info = _run_ffprobe(path) if settings.ffprobe_path else None
    _probe_cache[key] = info
    return info


def _run_ffprobe(path: Path) -> MediaInfo | None:
    cmd = [
        settings.ffprobe_path,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30, check=True)
        data = json.loads(result.stdout)
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        logger.warning("ffprobe failed for %s", path, exc_info=True)
        return None

    streams = data.get("streams", [])
    fmt = data.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    subtitles: list[SubtitleStream] = []
    for s in streams:
        if s.get("codec_type") != "subtitle":
            continue
        codec = (s.get("codec_name") or "").lower()
        tags = s.get("tags") or {}
        subtitles.append(
            SubtitleStream(
                index=s.get("index", 0),
                codec=codec,
                language=tags.get("language"),
                title=tags.get("title"),
                text_based=codec in _TEXT_SUBTITLE_CODECS,
            )
        )

    try:
        duration = float(fmt.get("duration", 0.0))
    except (TypeError, ValueError):
        duration = 0.0

    return MediaInfo(
        container=path.suffix.lower().lstrip("."),
        video_codec=(video.get("codec_name") or "").lower() if video else None,
        audio_codec=(audio.get("codec_name") or "").lower() if audio else None,
        duration_seconds=duration,
        width=video.get("width") if video else None,
        height=video.get("height") if video else None,
        subtitles=subtitles,
    )


def decide_play_mode(container: str, info: MediaInfo | None) -> str:
    """Choose how to stream a file: 'direct' | 'remux' | 'transcode' | 'unavailable'.

    - **direct**: browser can demux + decode the file as-is (HTTP range, true seek).
    - **remux**: compatible video codec in an incompatible container — copy video, fix
      audio, repackage to fragmented MP4 (cheap, no re-encode).
    - **transcode**: incompatible video codec (e.g. HEVC) — re-encode to H.264 (costly).
    - **unavailable**: needs ffmpeg but it isn't installed.
    """
    container = container.lower()
    container_safe = container in _DIRECT_CONTAINERS

    if info is None:
        # No probe data (ffprobe absent or failed): guess from the container alone.
        if container_safe:
            return "direct"
        return "remux" if settings.ffmpeg_available else "unavailable"

    video_safe = (info.video_codec or "") in _SAFE_VIDEO
    audio_safe = (info.audio_codec or "") in _SAFE_AUDIO

    if container_safe and video_safe and audio_safe:
        return "direct"
    if not settings.ffmpeg_available:
        return "unavailable"
    if video_safe:
        return "remux"
    return "transcode"
