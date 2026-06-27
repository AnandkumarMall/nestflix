"""Tests for filename -> ParsedTitle parsing."""

from __future__ import annotations

from backend.titleparser import parse


def test_parses_movie_with_year():
    p = parse("The.Matrix.1999.1080p.BluRay.x264.mkv")
    assert p.kind == "movie"
    assert p.title == "The Matrix"
    assert p.year == 1999
    assert p.season is None and p.episode is None


def test_parses_tv_episode_sxxexx():
    p = parse("The.Office.S02E05.720p.HDTV.mkv")
    assert p.kind == "episode"
    assert p.title == "The Office"
    assert p.season == 2
    assert p.episode == 5


def test_parses_tv_episode_alt_format():
    p = parse("Breaking Bad - 1x07 - Negro y Azul.mp4")
    assert p.kind == "episode"
    assert p.season == 1
    assert p.episode == 7
    assert "Breaking Bad" in p.title


def test_garbage_filename_degrades_to_cleaned_stem():
    p = parse("____random_thing____.mp4")
    assert p.kind == "movie"
    assert p.title  # never empty


def test_no_crash_on_empty_name():
    p = parse(".mkv")
    assert p.kind == "movie"
    assert isinstance(p.title, str)
