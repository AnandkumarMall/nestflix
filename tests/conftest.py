"""Shared pytest fixtures: an isolated temp database for each test."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend import db
from backend.config import settings


@pytest.fixture()
def temp_db(tmp_path: Path, monkeypatch):
    """Point the app at a throwaway SQLite file and initialize the schema."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(settings, "db_path", db_file)
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "images_dir", tmp_path / "images")
    db.init_db()
    yield db_file


def make_files(root: Path, names: list[str]) -> None:
    """Create empty files (with parent dirs) for the given relative names."""
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\x00")  # non-empty so .stat().st_size > 0
