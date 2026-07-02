"""Video streaming engine: byte-range serving, ffmpeg remux/transcode, and subtitles.

Three play modes (chosen in ``media_probe.decide_play_mode``):

- **direct** — serve the file with HTTP Range support so the browser seeks natively.
- **remux** — ffmpeg copies the (compatible) video, fixes audio, repackages to fragmented
  MP4 streamed from stdout. Cheap.
- **transcode** — ffmpeg re-encodes to H.264/AAC. Costly but plays anything.

For the ffmpeg modes the output has no seekable index, so seeking is offset-based: the
client re-requests ``?t=<seconds>`` and ffmpeg restarts at that input position. The ffmpeg
process is always terminated when the client disconnects to avoid orphaned encoders.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import TypedDict

from fastapi import HTTPException
from fastapi.responses import Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

from .config import settings
from .media_probe import MediaInfo


class SubtitleTrackDict(TypedDict):
    track: str
    label: str
    language: str | None
    kind: str


logger = logging.getLogger(__name__)

_CHUNK = 256 * 1024  # 256 KiB read/stream chunk

# Map a container extension to a sensible Content-Type for direct play.
_CONTENT_TYPES = {
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
    "avi": "video/x-msvideo",
    "mov": "video/quicktime",
}

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


# ---------------------------------------------------------------------------
# Path safety — every filesystem access must stay inside a configured library.
# ---------------------------------------------------------------------------


def is_within_library(path: Path) -> bool:
    """True if ``path`` resolves to somewhere inside a configured library root."""
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in settings.library_paths:
        try:
            if resolved.is_relative_to(root.resolve()):
                return True
        except OSError:
            continue
    return False


# ---------------------------------------------------------------------------
# Direct play — HTTP Range / byte serving.
# ---------------------------------------------------------------------------


def range_response(path: Path, range_header: str | None, container: str) -> Response:
    """Serve a file honoring a Range header (206 partial) or in full (200)."""
    file_size = path.stat().st_size
    content_type = _CONTENT_TYPES.get(container.lower(), "application/octet-stream")
    start, end = 0, file_size - 1
    status = 200
    headers = {"Accept-Ranges": "bytes", "Content-Type": content_type}

    match = _RANGE_RE.fullmatch(range_header.strip()) if range_header else None
    if match:
        g_start, g_end = match.group(1), match.group(2)
        if g_start:
            start = int(g_start)
            end = int(g_end) if g_end else file_size - 1
        elif g_end:  # suffix range: bytes=-N → last N bytes
            start = max(0, file_size - int(g_end))
            end = file_size - 1
        end = min(end, file_size - 1)
        if start > end or start >= file_size:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"

    length = end - start + 1
    headers["Content-Length"] = str(length)

    def iter_file() -> Iterator[bytes]:
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    # Starlette iterates a sync generator in a threadpool, so file IO won't block the loop.
    return StreamingResponse(iter_file(), status_code=status, headers=headers)


# ---------------------------------------------------------------------------
# Remux / transcode — pipe fragmented MP4 from ffmpeg.
# ---------------------------------------------------------------------------


def _ffmpeg_cmd(path: Path, mode: str, start_seconds: float) -> list[str]:
    cmd = [settings.ffmpeg_path, "-loglevel", "error"]
    if start_seconds > 0:
        cmd += ["-ss", f"{start_seconds:.3f}"]  # input seek (fast, keyframe-accurate)
    cmd += ["-i", str(path), "-map", "0:v:0", "-map", "0:a:0?", "-sn"]
    if mode == "remux":
        # Keep the (already browser-safe) video; only the audio may need transcoding.
        cmd += ["-c:v", "copy", "-c:a", "aac", "-ac", "2"]
    else:  # transcode
        cmd += [
            "-c:v",
            "libx264",
            "-preset",
            settings.transcode_preset,
            "-crf",
            str(settings.transcode_crf),
            "-c:a",
            "aac",
            "-ac",
            "2",
        ]
    cmd += [
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "-f",
        "mp4",
        "pipe:1",
    ]
    return cmd


async def ffmpeg_stream(path: Path, mode: str, start_seconds: float) -> StreamingResponse:
    """Stream a fragmented MP4 produced by ffmpeg, killing it on client disconnect."""
    if not settings.ffmpeg_available:
        raise HTTPException(status_code=409, detail="ffmpeg is not installed")

    cmd = _ffmpeg_cmd(path, mode, start_seconds)
    # Use subprocess.Popen in a thread (works on Windows; asyncio subprocess doesn't).
    proc = await run_in_threadpool(
        subprocess.Popen,
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )

    def pump() -> Iterator[bytes]:
        try:
            assert proc.stdout is not None
            while True:
                chunk = proc.stdout.read(_CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            # Client closed the tab / seeked away — don't leave ffmpeg encoding forever.
            if proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    pass

    headers = {"Cache-Control": "no-store", "Accept-Ranges": "none"}
    return StreamingResponse(pump(), media_type="video/mp4", headers=headers)


# ---------------------------------------------------------------------------
# Subtitles — embedded (via ffmpeg) + sidecar files, served as WebVTT.
# ---------------------------------------------------------------------------

_SIDECAR_EXTS = {".srt", ".vtt", ".ass"}
_SRT_TIMESTAMP = re.compile(r"(\d{2}:\d{2}:\d{2}),(\d{3})")


def list_sidecars(path: Path) -> list[Path]:
    """Subtitle files sitting next to the video (same filename stem), sorted stably."""
    parent = path.parent
    stem = path.stem.lower()
    found: list[Path] = []
    try:
        for f in sorted(parent.iterdir()):
            if (
                f.suffix.lower() in _SIDECAR_EXTS
                and f.stem.lower().startswith(stem)
                and is_within_library(f)
            ):
                found.append(f)
    except OSError:
        pass
    return found


def _sidecar_language(path: Path, sidecar: Path) -> str | None:
    """Infer a language from the part of the sidecar name after the video stem."""
    extra = sidecar.stem[len(path.stem) :].strip(". _-")
    return extra or None


def subtitle_tracks(path: Path, info: MediaInfo | None) -> list[SubtitleTrackDict]:
    """List selectable subtitle tracks: text-based embedded streams + sidecar files."""
    tracks: list[SubtitleTrackDict] = []
    if info:
        for s in info.subtitles:
            if not s.text_based:
                continue  # image subs can't become WebVTT
            tracks.append(
                {
                    "track": f"e{s.index}",
                    "label": s.title or (s.language or f"Track {s.index}"),
                    "language": s.language,
                    "kind": "embedded",
                }
            )
    for i, sidecar in enumerate(list_sidecars(path)):
        lang = _sidecar_language(path, sidecar)
        tracks.append(
            {
                "track": f"s{i}",
                "label": lang or "External",
                "language": lang,
                "kind": "sidecar",
            }
        )
    return tracks


def srt_to_vtt(text: str) -> str:
    """Minimal SubRip → WebVTT conversion (comma decimals → periods, add header)."""
    body = _SRT_TIMESTAMP.sub(r"\1.\2", text)
    return "WEBVTT\n\n" + body


def subtitle_to_vtt(path: Path, track: str) -> str | None:
    """Return a subtitle track as WebVTT text, or None if it can't be produced.

    ``track`` is a token from :func:`subtitle_tracks`: ``e<index>`` for an embedded
    stream (extracted via ffmpeg) or ``s<n>`` for the nth sidecar file.
    """
    if track.startswith("e"):
        if not settings.ffmpeg_available:
            return None
        idx = _parse_int(track[1:])
        return _extract_embedded_vtt(path, idx) if idx is not None else None

    if track.startswith("s"):
        i = _parse_int(track[1:])
        sidecars = list_sidecars(path)
        if i is None or not 0 <= i < len(sidecars):
            return None
        sidecar = sidecars[i]
        try:
            text = sidecar.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return text if sidecar.suffix.lower() == ".vtt" else srt_to_vtt(text)

    return None


def _extract_embedded_vtt(path: Path, stream_index: int) -> str | None:
    cmd = [
        settings.ffmpeg_path,
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-map",
        f"0:{stream_index}",
        "-f",
        "webvtt",
        "pipe:1",
    ]
    import subprocess  # local import: only needed when extracting embedded subs

    try:
        result = subprocess.run(cmd, capture_output=True, timeout=60, check=True)
    except (subprocess.SubprocessError, OSError):
        logger.warning("subtitle extraction failed for %s #%s", path, stream_index)
        return None
    return result.stdout.decode("utf-8", errors="replace") or None


def _parse_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None
