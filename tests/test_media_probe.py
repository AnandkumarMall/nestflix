"""Play-mode decision logic — pure, mocked (no ffmpeg needed)."""

from __future__ import annotations

from backend.config import settings
from backend.media_probe import MediaInfo, decide_play_mode


def _info(container: str, video: str | None, audio: str | None) -> MediaInfo:
    return MediaInfo(
        container=container,
        video_codec=video,
        audio_codec=audio,
        duration_seconds=10.0,
        width=1920,
        height=1080,
    )


def _set_ffmpeg(monkeypatch, available: bool) -> None:
    monkeypatch.setattr(settings, "ffmpeg_path", "ffmpeg" if available else "")
    monkeypatch.setattr(settings, "ffprobe_path", "ffprobe" if available else "")


def test_direct_for_browser_native(monkeypatch):
    _set_ffmpeg(monkeypatch, True)
    assert decide_play_mode("mp4", _info("mp4", "h264", "aac")) == "direct"


def test_remux_for_h264_in_mkv(monkeypatch):
    _set_ffmpeg(monkeypatch, True)
    # Compatible video codec, incompatible container/audio → remux.
    assert decide_play_mode("mkv", _info("mkv", "h264", "ac3")) == "remux"


def test_transcode_for_hevc(monkeypatch):
    _set_ffmpeg(monkeypatch, True)
    assert decide_play_mode("mkv", _info("mkv", "hevc", "aac")) == "transcode"


def test_unavailable_without_ffmpeg(monkeypatch):
    _set_ffmpeg(monkeypatch, False)
    assert decide_play_mode("mkv", _info("mkv", "h264", "ac3")) == "unavailable"


def test_native_still_direct_without_ffmpeg(monkeypatch):
    _set_ffmpeg(monkeypatch, False)
    assert decide_play_mode("mp4", _info("mp4", "h264", "aac")) == "direct"


def test_no_probe_guesses_from_container(monkeypatch):
    _set_ffmpeg(monkeypatch, True)
    assert decide_play_mode("mp4", None) == "direct"
    assert decide_play_mode("mkv", None) == "remux"
    _set_ffmpeg(monkeypatch, False)
    assert decide_play_mode("mkv", None) == "unavailable"
