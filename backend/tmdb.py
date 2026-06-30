"""Async TMDB client — the ONLY module that talks to the TMDB API.

Responsibilities:
  * Centralized, rate-limited, retrying access to TMDB v3 endpoints.
  * Aggressive caching of JSON responses in the `tmdb_cache` table.
  * A scoped DNS-over-HTTPS resolver so the app works on networks that DNS-poison
    TMDB (see `_install_doh_resolver`).

Nothing outside this module imports `httpx` for TMDB or hardcodes the API key — callers
use the typed coroutines below. Errors surface as `TMDBError`; route handlers translate
them into `HTTPException`.
"""

from __future__ import annotations

import asyncio
import json
import socket
import ssl
import time
from typing import Any

import httpx

from . import db
from .config import settings

API_BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p"

# Hostnames whose DNS we resolve via DoH when TMDB_USE_DOH is on.
_TMDB_HOSTS = {"api.themoviedb.org", "image.tmdb.org"}

# Multiple DoH resolvers — they return different CloudFront/CDN edge pools, which
# matters because the target ISP blocks *some* edge IPs at the TCP/TLS level. Each
# entry is (url, extra_headers); both accept ?name=&type=A.
_DOH_RESOLVERS = (
    ("https://1.1.1.1/dns-query", {"accept": "application/dns-json"}),
    ("https://8.8.8.8/resolve", {}),
)

# Be a good API citizen: cap concurrency and retry transient failures.
_MAX_CONCURRENCY = 8
_MAX_RETRIES = 3
_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


class TMDBError(Exception):
    """Any failure talking to TMDB (not configured, network, or bad response)."""


class TMDBNotConfigured(TMDBError):
    """Raised when no TMDB API key is set."""


# ---------------------------------------------------------------------------
# DNS-over-HTTPS resolver (scoped to TMDB hostnames only).
# ---------------------------------------------------------------------------
# The target ISP both DNS-poisons TMDB *and* resets connections to some of its
# CloudFront edge IPs at the TCP/TLS layer. So we (1) gather candidate IPs from
# several DoH resolvers (they return different edge pools) and (2) probe them with
# a real TLS handshake, pinning the first that actually answers. The pinned IP is
# handed to the original getaddrinfo; TLS SNI + cert verification still use the
# real hostname from the URL (like `curl --resolve`), so connections stay verified.

_orig_getaddrinfo = socket.getaddrinfo
_doh_installed = False
_doh_cache: dict[str, tuple[str, float]] = {}  # host -> (ip, expires_at)
_DOH_TTL = 3600.0
_PROBE_TIMEOUT = 4.0


def _doh_candidates(host: str) -> list[str]:
    """Collect candidate A-record IPs for `host` across all DoH resolvers."""
    ips: list[str] = []
    for url, headers in _DOH_RESOLVERS:
        try:
            resp = httpx.get(url, params={"name": host, "type": "A"}, headers=headers, timeout=8.0)
            resp.raise_for_status()
            answers = resp.json().get("Answer", [])
            ips += [a["data"] for a in answers if a.get("type") == 1]  # type 1 == A
        except Exception:
            continue
    # De-duplicate while preserving order.
    seen: set[str] = set()
    return [ip for ip in ips if not (ip in seen or seen.add(ip))]


def _probe_ip(host: str, ip: str) -> bool:
    """True if a real TLS handshake to `ip` (with `host`'s SNI) gets an HTTP reply.

    Blocked edges are reset during the handshake, so they fail here and are skipped.
    """
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((ip, 443), timeout=_PROBE_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                tls.sendall(f"GET / HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n".encode())
                return tls.recv(16).startswith(b"HTTP/")
    except Exception:
        return False


def _doh_resolve_sync(host: str) -> str:
    """Resolve `host` to a reachable IPv4 address, pinning a working edge for an hour."""
    cached = _doh_cache.get(host)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    candidates = _doh_candidates(host)
    if not candidates:
        raise TMDBError(f"DoH returned no A record for {host}")

    chosen = next((ip for ip in candidates if _probe_ip(host, ip)), candidates[0])
    _doh_cache[host] = (chosen, time.monotonic() + _DOH_TTL)
    return chosen


def _patched_getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
    """getaddrinfo that swaps TMDB hostnames for their DoH-resolved IP.

    `host` may arrive as bytes (anyio/httpx do this), so normalize before matching.
    """
    name = host.decode() if isinstance(host, bytes | bytearray) else host
    if name in _TMDB_HOSTS:
        try:
            ip = _doh_resolve_sync(name)
            return _orig_getaddrinfo(ip, *args, **kwargs)
        except Exception:
            # Fall back to the system resolver rather than hard-failing.
            pass
    return _orig_getaddrinfo(host, *args, **kwargs)


def _install_doh_resolver() -> None:
    """Install the scoped resolver once, if DoH is enabled in config."""
    global _doh_installed
    if _doh_installed or not settings.tmdb_use_doh:
        return
    socket.getaddrinfo = _patched_getaddrinfo  # type: ignore[assignment]
    _doh_installed = True


def is_online() -> bool:
    """Quick check if internet is available (ping 8.8.8.8 or 1.1.1.1)."""
    for host in ("8.8.8.8", "1.1.1.1"):
        try:
            socket.create_connection((host, 53), timeout=2.0).close()
            return True
        except (TimeoutError, OSError):
            continue
    return False


# ---------------------------------------------------------------------------
# HTTP client + cached GET
# ---------------------------------------------------------------------------

_client: httpx.AsyncClient | None = None
_semaphore: asyncio.Semaphore | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _install_doh_resolver()
        _client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _client


def _get_semaphore() -> asyncio.Semaphore:
    """Lazily create the concurrency limiter on the active event loop."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
    return _semaphore


async def aclose() -> None:
    """Close the shared client (called on app shutdown)."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _require_key() -> str:
    if not settings.tmdb_api_key:
        raise TMDBNotConfigured("TMDB_API_KEY is not set")
    return settings.tmdb_api_key


def _cache_key(path: str, params: dict[str, Any]) -> str:
    """Stable cache key from path + params, excluding the secret api_key."""
    safe = {k: v for k, v in sorted(params.items()) if k != "api_key" and v is not None}
    return f"{path}?{json.dumps(safe, sort_keys=True, separators=(',', ':'))}"


async def _get(
    path: str,
    params: dict[str, Any] | None = None,
    *,
    max_age_hours: float | None = None,
) -> dict[str, Any]:
    """GET `path` from TMDB with caching, retry, and rate limiting.

    `max_age_hours` controls cache freshness: None means cache forever (good for
    immutable details); a number re-fetches data older than that (good for trending).
    """
    api_key = _require_key()
    params = dict(params or {})
    key = _cache_key(path, params)

    cached = db.tmdb_cache_get(key, max_age_hours=max_age_hours)
    if cached is not None:
        return cached

    # Check internet before attempting fresh API call. If offline, raise error with cached fallback instruction.
    if not is_online():
        raise TMDBError(
            f"No internet connection. {path} data unavailable. "
            "(Local library and watch history still work offline.)"
        )

    params["api_key"] = api_key
    url = f"{API_BASE}/{path.lstrip('/')}"

    # Keep only a sanitized reason — the request URL carries the api_key, so the raw
    # httpx exception (which embeds the URL) must never reach logs or responses.
    last_err = "no response"
    for attempt in range(_MAX_RETRIES):
        try:
            async with _get_semaphore():
                resp = await _get_client().get(url, params=params)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                await asyncio.sleep(min(retry_after, 10.0))
                last_err = "rate limited"
                continue
            resp.raise_for_status()
            data = resp.json()
            db.tmdb_cache_put(key, data)
            return data
        except httpx.HTTPStatusError as exc:
            last_err = f"HTTP {exc.response.status_code}"
            await asyncio.sleep(0.5 * (attempt + 1))
        except httpx.TransportError as exc:
            last_err = type(exc).__name__
            await asyncio.sleep(0.5 * (attempt + 1))

    raise TMDBError(f"TMDB request failed for {path}: {last_err}")


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


async def search_movie(title: str, year: int | None = None) -> dict[str, Any] | None:
    """Return the best movie match for `title` (+optional year), or None."""
    params: dict[str, Any] = {"query": title}
    if year:
        params["year"] = year
    data = await _get("search/movie", params)
    return _best_result(data.get("results", []), year, year_key="release_date")


async def search_tv(title: str, year: int | None = None) -> dict[str, Any] | None:
    """Return the best TV match for `title` (+optional first-air year), or None."""
    params: dict[str, Any] = {"query": title}
    if year:
        params["first_air_date_year"] = year
    data = await _get("search/tv", params)
    return _best_result(data.get("results", []), year, year_key="first_air_date")


async def search_movies(query: str, year: int | None = None) -> list[dict[str, Any]]:
    """Return all movie search results (used by the manual fix-match picker)."""
    params: dict[str, Any] = {"query": query}
    if year:
        params["year"] = year
    data = await _get("search/movie", params)
    return data.get("results", [])


async def movie_details(tmdb_id: int) -> dict[str, Any]:
    """Full movie record incl. credits + keywords (append_to_response)."""
    return await _get(f"movie/{tmdb_id}", {"append_to_response": "credits,keywords"})


async def tv_details(tmdb_id: int) -> dict[str, Any]:
    """Full TV record incl. credits + keywords."""
    return await _get(f"tv/{tmdb_id}", {"append_to_response": "credits,keywords"})


async def trending(media_type: str = "all", window: str = "week") -> list[dict[str, Any]]:
    """Trending titles. Cached for 6h since the list changes slowly."""
    data = await _get(f"trending/{media_type}/{window}", max_age_hours=6.0)
    return data.get("results", [])


async def now_playing() -> list[dict[str, Any]]:
    """Movies currently in theaters / newly released. Cached for 12h."""
    data = await _get("movie/now_playing", max_age_hours=12.0)
    return data.get("results", [])


async def recommendations(media_type: str, tmdb_id: int) -> list[dict[str, Any]]:
    """Similar titles to a TMDB ID (movie or tv). Cached for 24h."""
    data = await _get(f"{media_type}/{tmdb_id}/recommendations", max_age_hours=24.0)
    return data.get("results", [])


async def get_image(path: str, size: str = "w342") -> bytes:
    """Download a poster/backdrop/still by its TMDB path, returning raw bytes."""
    _install_doh_resolver()
    url = f"{IMAGE_BASE}/{size}/{path.lstrip('/')}"
    async with _get_semaphore():
        resp = await _get_client().get(url)
    resp.raise_for_status()
    return resp.content


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _best_result(
    results: list[dict[str, Any]], year: int | None, *, year_key: str
) -> dict[str, Any] | None:
    """Pick the best search hit: prefer an exact year match, else most popular."""
    if not results:
        return None
    if year:
        for r in results:
            date = r.get(year_key) or ""
            if date[:4] == str(year):
                return r
    # TMDB already sorts by relevance/popularity; take the first.
    return results[0]
