"""Tests for the library scanner: discovery, persistence, and idempotency."""

from __future__ import annotations

from backend import db
from backend.scanner import iter_video_files, scan_library

from .conftest import make_files


def test_scan_discovers_movies_and_episodes(temp_db, tmp_path):
    root = tmp_path / "library"
    make_files(
        root,
        [
            "Movies/The.Matrix.1999.1080p.BluRay.mkv",
            "Movies/Inception.2010.720p.mp4",
            "TV/The.Office/The.Office.S02E05.720p.mkv",
            "TV/The.Office/The.Office.S02E06.720p.mkv",
            "Movies/poster.jpg",  # not a video
            "Movies/sample/The.Matrix.sample.mkv",  # sample dir, skipped
        ],
    )

    result = scan_library([root])

    assert result.movies_added == 2
    assert result.episodes_added == 2
    # poster.jpg + sample file are not counted as seen video files at all.
    assert result.files_seen == 4

    lib = db.get_library()
    titles = {m["parsed_title"] for m in lib["movies"]}
    assert "The Matrix" in titles and "Inception" in titles

    assert len(lib["shows"]) == 1
    office = lib["shows"][0]
    assert office["parsed_title"] == "The Office"
    assert len(office["episodes"]) == 2
    assert office["episodes"][0]["season"] == 2


def test_scan_is_idempotent(temp_db, tmp_path):
    root = tmp_path / "library"
    make_files(
        root,
        [
            "The.Matrix.1999.1080p.mkv",
            "The.Office.S01E01.mkv",
        ],
    )

    scan_library([root])
    scan_library([root])  # second run must not duplicate anything

    conn = db.get_db()
    try:
        n_files = conn.execute("SELECT COUNT(*) AS n FROM media_files").fetchone()["n"]
        n_movies = conn.execute("SELECT COUNT(*) AS n FROM movies").fetchone()["n"]
        n_shows = conn.execute("SELECT COUNT(*) AS n FROM shows").fetchone()["n"]
        n_eps = conn.execute("SELECT COUNT(*) AS n FROM episodes").fetchone()["n"]
    finally:
        conn.close()

    assert n_files == 2
    assert n_movies == 1
    assert n_shows == 1
    assert n_eps == 1


def test_iter_skips_hidden_and_non_video(temp_db, tmp_path):
    root = tmp_path / "library"
    make_files(
        root,
        [
            "good.mkv",
            ".hidden.mkv",
            "notes.txt",
        ],
    )
    found = {p.name for p in iter_video_files([root])}
    assert found == {"good.mkv"}
