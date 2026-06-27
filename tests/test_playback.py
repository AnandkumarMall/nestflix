"""Playback routes: info, range streaming, resume progress + Continue Watching."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from backend import db, media_probe
from backend.config import settings
from backend.main import app
from backend.media_probe import MediaInfo


def _seed_movie(tmp_path: Path, monkeypatch, container: str = "mp4") -> int:
    """Create a library file + media/movie rows; return the media_file_id."""
    root = tmp_path / "lib"
    root.mkdir(exist_ok=True)
    monkeypatch.setattr(settings, "library_paths", [root])
    video = root / f"The.Matrix.1999.{container}"
    video.write_bytes(bytes(i % 256 for i in range(1000)))
    conn = db.get_db()
    try:
        media_file_id = db.upsert_media_file(
            conn, str(video), 1000, 0.0, container, "movie"
        )
        db.upsert_movie(conn, media_file_id, "The Matrix", 1999)
        conn.commit()
    finally:
        conn.close()
    return media_file_id


def test_info_returns_play_mode_and_title(temp_db, tmp_path, monkeypatch):
    media_file_id = _seed_movie(tmp_path, monkeypatch)
    monkeypatch.setattr(
        media_probe,
        "probe",
        lambda p: MediaInfo("mp4", "h264", "aac", 120.0, 1920, 1080),
    )
    with TestClient(app) as client:
        r = client.get(f"/api/playback/{media_file_id}/info")
    assert r.status_code == 200
    body = r.json()
    assert body["play_mode"] == "direct"
    assert body["title"] == "The Matrix"
    assert body["kind"] == "movie"


def test_info_missing_file_is_404(temp_db):
    with TestClient(app) as client:
        r = client.get("/api/playback/999999/info")
    assert r.status_code == 404


def test_stream_honors_range(temp_db, tmp_path, monkeypatch):
    media_file_id = _seed_movie(tmp_path, monkeypatch)
    monkeypatch.setattr(
        media_probe,
        "probe",
        lambda p: MediaInfo("mp4", "h264", "aac", 120.0, 1920, 1080),
    )
    with TestClient(app) as client:
        r = client.get(
            f"/api/playback/{media_file_id}/stream", headers={"Range": "bytes=0-99"}
        )
    assert r.status_code == 206
    assert r.headers["Content-Range"] == "bytes 0-99/1000"
    assert len(r.content) == 100


def test_stream_unavailable_without_ffmpeg_is_409(temp_db, tmp_path, monkeypatch):
    media_file_id = _seed_movie(tmp_path, monkeypatch, container="mkv")
    monkeypatch.setattr(settings, "ffmpeg_path", "")
    monkeypatch.setattr(settings, "ffprobe_path", "")
    monkeypatch.setattr(
        media_probe,
        "probe",
        lambda p: MediaInfo("mkv", "hevc", "ac3", 120.0, 3840, 2160),
    )
    with TestClient(app) as client:
        r = client.get(f"/api/playback/{media_file_id}/stream")
    assert r.status_code == 409


def test_progress_roundtrip_and_continue_watching(temp_db, tmp_path, monkeypatch):
    media_file_id = _seed_movie(tmp_path, monkeypatch)
    with TestClient(app) as client:
        # Save a mid-watch position (default seeded profile id == 1).
        saved = client.post(
            "/api/playback/progress",
            json={
                "profile_id": 1,
                "media_file_id": media_file_id,
                "position_seconds": 30.0,
                "duration_seconds": 120.0,
            },
        )
        assert saved.status_code == 200
        assert saved.json()["completed"] is False

        got = client.get(
            f"/api/playback/progress?profile_id=1&media_file_id={media_file_id}"
        ).json()
        assert got["position_seconds"] == 30.0

        cont = client.get("/api/playback/continue?profile_id=1").json()
        assert any(i["media_file_id"] == media_file_id for i in cont["items"])

        # Finishing the title marks it complete and drops it from Continue Watching.
        done = client.post(
            "/api/playback/progress",
            json={
                "profile_id": 1,
                "media_file_id": media_file_id,
                "position_seconds": 118.0,
                "duration_seconds": 120.0,
            },
        )
        assert done.json()["completed"] is True
        cont2 = client.get("/api/playback/continue?profile_id=1").json()
        assert all(i["media_file_id"] != media_file_id for i in cont2["items"])


def test_progress_rejects_unknown_ids(temp_db):
    with TestClient(app) as client:
        r = client.post(
            "/api/playback/progress",
            json={
                "profile_id": 999,
                "media_file_id": 999,
                "position_seconds": 1.0,
                "duration_seconds": 10.0,
            },
        )
    assert r.status_code == 400
