"""HTTP range serving, path-containment, and subtitle helpers (no ffmpeg needed)."""

from __future__ import annotations

from pathlib import Path

from backend import streaming
from backend.config import settings
from backend.media_probe import MediaInfo, SubtitleStream


def _library(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "lib"
    root.mkdir()
    monkeypatch.setattr(settings, "library_paths", [root])
    return root


def _make_video(root: Path, size: int = 1000) -> Path:
    f = root / "movie.mp4"
    f.write_bytes(bytes(i % 256 for i in range(size)))
    return f


def test_full_request_is_200_with_length(tmp_path, monkeypatch):
    f = _make_video(_library(tmp_path, monkeypatch))
    resp = streaming.range_response(f, None, "mp4")
    assert resp.status_code == 200
    assert resp.headers["Accept-Ranges"] == "bytes"
    assert resp.headers["Content-Length"] == "1000"
    assert resp.headers["Content-Type"] == "video/mp4"


def test_partial_request_is_206(tmp_path, monkeypatch):
    f = _make_video(_library(tmp_path, monkeypatch))
    resp = streaming.range_response(f, "bytes=0-99", "mp4")
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == "bytes 0-99/1000"
    assert resp.headers["Content-Length"] == "100"


def test_suffix_range(tmp_path, monkeypatch):
    f = _make_video(_library(tmp_path, monkeypatch))
    resp = streaming.range_response(f, "bytes=-50", "mp4")
    assert resp.status_code == 206
    assert resp.headers["Content-Range"] == "bytes 950-999/1000"


def test_unsatisfiable_range_is_416(tmp_path, monkeypatch):
    f = _make_video(_library(tmp_path, monkeypatch))
    resp = streaming.range_response(f, "bytes=5000-6000", "mp4")
    assert resp.status_code == 416


def test_is_within_library(tmp_path, monkeypatch):
    root = _library(tmp_path, monkeypatch)
    inside = root / "a.mkv"
    inside.write_bytes(b"x")
    outside = tmp_path / "evil.mkv"
    outside.write_bytes(b"x")
    assert streaming.is_within_library(inside)
    assert not streaming.is_within_library(outside)


def test_srt_to_vtt_converts_timestamps():
    srt = "1\n00:00:01,000 --> 00:00:02,500\nHello\n"
    vtt = streaming.srt_to_vtt(srt)
    assert vtt.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:02.500" in vtt


def test_subtitle_tracks_lists_text_embedded_and_sidecar(tmp_path, monkeypatch):
    root = _library(tmp_path, monkeypatch)
    video = root / "film.mkv"
    video.write_bytes(b"x")
    (root / "film.en.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8"
    )
    info = MediaInfo(
        container="mkv",
        video_codec="h264",
        audio_codec="aac",
        duration_seconds=10.0,
        width=1920,
        height=1080,
        subtitles=[
            SubtitleStream(2, "subrip", "eng", "English", True),
            SubtitleStream(3, "hdmv_pgs_subtitle", "eng", None, False),  # image: skip
        ],
    )
    tracks = streaming.subtitle_tracks(video, info)
    embedded = [t for t in tracks if t["kind"] == "embedded"]
    sidecar = [t for t in tracks if t["kind"] == "sidecar"]
    assert [t["track"] for t in embedded] == ["e2"]  # PGS (e3) excluded
    assert len(sidecar) == 1


def test_subtitle_to_vtt_from_sidecar(tmp_path, monkeypatch):
    root = _library(tmp_path, monkeypatch)
    video = root / "film.mkv"
    video.write_bytes(b"x")
    (root / "film.srt").write_text(
        "1\n00:00:01,000 --> 00:00:02,000\nHi\n", encoding="utf-8"
    )
    vtt = streaming.subtitle_to_vtt(video, "s0")
    assert vtt is not None and vtt.startswith("WEBVTT")
    assert "00:00:01.000 --> 00:00:02.000" in vtt
