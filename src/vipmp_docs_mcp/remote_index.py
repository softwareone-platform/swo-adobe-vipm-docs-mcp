"""
GitHub-refreshed index tier — keeps `data/index.json` fresh between PyPI releases.

The package ships with a baseline ``data/index.json``, but that file ages as
soon as the wheel is built. A daily GitHub Actions workflow rebuilds the index
on ``main``, yet users don't see that refresh until a new PyPI version is
tagged and their ``uvx`` cache turns over. This module closes that gap.

On demand (first index-requiring tool call per session, subject to the TTL):

  1. If a cached copy is within the TTL window, use it — no network.
  2. Otherwise do a conditional GET against raw.githubusercontent.com with
     the stored ETag. 304 is free; 200 overwrites the cache atomically.
  3. If the fetch fails for any reason (offline, rate limit, DNS, timeout,
     non-JSON response, GitHub 5xx) we fall back to whatever is on disk,
     logging a warning. This tier is always stale-OK: it only ever *adds*
     freshness, it never blocks the server.

Opt-out: set ``VIPMP_DISABLE_REMOTE_INDEX=1`` for deterministic runs (tests,
air-gapped environments, forensic debugging). Users on the opt-out path get
the package baseline as before.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .logging_config import CACHE_DIR, get_logger

log = get_logger("remote_index")

REMOTE_INDEX_URL = (
    "https://raw.githubusercontent.com/softwareone-platform/"
    "swo-adobe-vipm-docs-mcp/main/src/vipmp_docs_mcp/data/index.json"
)

REMOTE_INDEX_PATH = CACHE_DIR / "remote-index.json"
REMOTE_INDEX_META_PATH = CACHE_DIR / "remote-index.meta.json"

TTL_SECONDS = 12 * 3600

DISABLE_ENV = "VIPMP_DISABLE_REMOTE_INDEX"

_FETCH_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def _is_disabled() -> bool:
    return os.environ.get(DISABLE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _load_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        log.debug("meta file unreadable at %s; treating as empty", path)
        return {}


def _save_meta(meta: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f)
    os.replace(tmp, path)


def _within_ttl(meta: dict) -> bool:
    try:
        fetched_at = float(meta.get("fetched_at", 0.0))
    except (TypeError, ValueError):
        return False
    return (time.time() - fetched_at) < TTL_SECONDS


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    retry=retry_if_exception(
        lambda e: isinstance(e, (httpx.TransportError, httpx.TimeoutException))
    ),
    reraise=True,
)
def _conditional_get(etag: str | None) -> httpx.Response:
    """Conditional GET against REMOTE_INDEX_URL. Transient transport/timeout errors retry."""
    headers: dict[str, str] = {
        "User-Agent": "SWOVIPMPDocsMCP-remote-index (+https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp)",
        "Accept": "application/json",
    }
    if etag:
        headers["If-None-Match"] = etag
    with httpx.Client(timeout=_FETCH_TIMEOUT, follow_redirects=True) as client:
        return client.get(REMOTE_INDEX_URL, headers=headers)


def _write_atomic(body: bytes, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(body)
    os.replace(tmp, path)


def ensure_fresh() -> Path | None:
    """
    Return the on-disk path to a usable remote index, refreshing it if the
    TTL has expired. Returns None only if the tier is disabled and there is
    nothing cached (the caller should then fall through to the package
    baseline).

    Never raises. Every failure mode degrades to "use what's on disk, if
    anything." The baseline tier in index.py is the true safety net.
    """
    if _is_disabled():
        log.debug("remote index disabled via %s", DISABLE_ENV)
        return None

    # Look these up per-call so tests (and any future caller) can
    # monkeypatch the module-level constants — function-default-arg
    # bindings would be captured at def-time and miss the patch.
    index_path = REMOTE_INDEX_PATH
    meta_path = REMOTE_INDEX_META_PATH

    have_cached = index_path.exists()
    meta = _load_meta(meta_path)

    # Short-circuit: inside the TTL window we trust what's on disk and
    # don't make a network call. This is the common case — typical
    # sessions hit disk for free and never touch GitHub.
    if have_cached and _within_ttl(meta):
        log.debug("remote index within TTL (fetched %.1fh ago); using cache",
                  (time.time() - float(meta.get("fetched_at", 0))) / 3600)
        return index_path

    etag = meta.get("etag") if have_cached else None

    try:
        response = _conditional_get(etag)
    except (httpx.TransportError, httpx.TimeoutException, RetryError) as exc:
        log.warning("remote index unreachable (%s); using cached copy if any", exc)
        return index_path if have_cached else None
    except Exception as exc:  # defensive: never propagate from this tier
        log.warning("remote index fetch raised unexpected %s: %s", type(exc).__name__, exc)
        return index_path if have_cached else None

    if response.status_code == 304:
        log.debug("remote index 304 Not Modified — bumping fetched_at")
        meta["fetched_at"] = time.time()
        _save_meta(meta, meta_path)
        return index_path

    if response.status_code != 200:
        log.warning(
            "remote index fetch got HTTP %s; using cached copy if any",
            response.status_code,
        )
        return index_path if have_cached else None

    body = response.content
    try:
        # Sanity-parse: don't write garbage to disk. Schema validation
        # happens when index.py tries to load the file — rejecting it
        # there falls through to the baseline tier, which is correct.
        json.loads(body)
    except json.JSONDecodeError as exc:
        log.warning("remote index response is not valid JSON (%s); ignoring", exc)
        return index_path if have_cached else None

    _write_atomic(body, index_path)
    _save_meta(
        {
            "fetched_at": time.time(),
            "etag": response.headers.get("ETag"),
            "content_length": len(body),
            "source_url": REMOTE_INDEX_URL,
        },
        meta_path,
    )
    log.info(
        "refreshed remote index from GitHub (%d bytes, etag=%s)",
        len(body),
        response.headers.get("ETag"),
    )
    return index_path


def get_status() -> dict:
    """
    Describe the remote-index tier state without triggering a fetch.
    Used by ``vipmp_server_info`` to show what users actually have.
    """
    if _is_disabled():
        return {"enabled": False, "reason": f"{DISABLE_ENV} is set"}
    meta = _load_meta(REMOTE_INDEX_META_PATH)
    return {
        "enabled": True,
        "cached": REMOTE_INDEX_PATH.exists(),
        "fetched_at": meta.get("fetched_at"),
        "etag": meta.get("etag"),
        "ttl_seconds": TTL_SECONDS,
        "url": REMOTE_INDEX_URL,
        "path": str(REMOTE_INDEX_PATH),
    }
