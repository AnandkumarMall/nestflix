"""Tests for the image cache helper and route validation (path-traversal defense)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import enrich
from backend.main import app


def test_image_filename_never_contains_separators():
    # Even traversal-shaped input collapses to a single flat filename.
    for evil in ["../../../etc/passwd", "..\\..\\.env", "/a/b/c.jpg"]:
        name = enrich._image_filename(evil, "w342")
        assert "/" not in name and "\\" not in name


def test_image_route_rejects_bad_size(temp_db):
    with TestClient(app) as client:
        r = client.get("/api/images/w999/poster.jpg")
    assert r.status_code == 400


def test_image_route_rejects_traversal_path(temp_db):
    with TestClient(app) as client:
        # Backslashes survive as a single path segment; the name regex must reject them.
        r = client.get("/api/images/w342/..%5C..%5C.env")
    assert r.status_code == 400
