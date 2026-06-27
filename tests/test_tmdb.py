"""Tests for the TMDB client: caching, result selection, and the DoH resolver.

No network: the cache is exercised directly and the resolver is tested via monkeypatch.
"""

from __future__ import annotations

from backend import db, tmdb


def test_cache_put_then_get_roundtrips(temp_db):
    key = 'search/movie?{"query":"matrix"}'
    db.tmdb_cache_put(key, {"results": [{"id": 603}]})
    assert db.tmdb_cache_get(key) == {"results": [{"id": 603}]}


def test_cache_miss_returns_none(temp_db):
    assert db.tmdb_cache_get("nope") is None


def test_cache_key_excludes_api_key():
    a = tmdb._cache_key("search/movie", {"query": "matrix", "api_key": "secret"})
    b = tmdb._cache_key("search/movie", {"query": "matrix"})
    assert a == b
    assert "secret" not in a


def test_best_result_prefers_year_match():
    results = [
        {"id": 1, "release_date": "2021-01-01"},
        {"id": 2, "release_date": "1999-03-30"},
    ]
    picked = tmdb._best_result(results, 1999, year_key="release_date")
    assert picked["id"] == 2


def test_best_result_falls_back_to_first():
    results = [{"id": 1, "release_date": "2021-01-01"}]
    picked = tmdb._best_result(results, None, year_key="release_date")
    assert picked["id"] == 1


def test_best_result_empty_is_none():
    assert tmdb._best_result([], 1999, year_key="release_date") is None


def test_doh_resolver_falls_through_for_non_tmdb_hosts(monkeypatch):
    seen = {}
    monkeypatch.setattr(
        tmdb, "_orig_getaddrinfo", lambda host, *a, **k: seen.setdefault("host", host)
    )
    tmdb._patched_getaddrinfo("example.com", 80)
    assert seen["host"] == "example.com"


def test_doh_resolver_rewrites_tmdb_host(monkeypatch):
    monkeypatch.setattr(tmdb, "_doh_resolve_sync", lambda host: "1.2.3.4")
    seen = {}
    monkeypatch.setattr(
        tmdb, "_orig_getaddrinfo", lambda host, *a, **k: seen.setdefault("host", host)
    )
    tmdb._patched_getaddrinfo("api.themoviedb.org", 443)
    assert seen["host"] == "1.2.3.4"


def test_doh_resolver_falls_back_when_doh_fails(monkeypatch):
    def boom(host):
        raise RuntimeError("doh down")

    monkeypatch.setattr(tmdb, "_doh_resolve_sync", boom)
    seen = {}
    monkeypatch.setattr(
        tmdb, "_orig_getaddrinfo", lambda host, *a, **k: seen.setdefault("host", host)
    )
    tmdb._patched_getaddrinfo("api.themoviedb.org", 443)
    assert seen["host"] == "api.themoviedb.org"
