"""
Disk-backed cache for cleaned Adobe docs pages.

Design:
    - Single JSON file at ~/.cache/swo-adobe-vipm-docs-mcp/cache.json
    - Stores cleaned text (not raw HTML) — ~10x smaller, cleaning is
      deterministic so re-cleaning adds no information.
    - Each entry tracks the response ETag so stale entries can be revalidated
      cheaply via If-None-Match.
    - Atomic writes (temp file + os.replace).

Concurrency:
    Not process-safe for concurrent writers. MCP servers run as a
    subprocess of a single client session, so this is fine in practice.
    If that assumption ever changes, swap to SQLite (stdlib, small) —
    the public API here shouldn't need to change.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .fetcher import FetchError, fetch_page_with_etag
from .html_cleaner import extract_text
from .logging_config import CACHE_DIR, get_logger
from .sitemap import normalize_path

log = get_logger("cache")

CACHE_FILE = CACHE_DIR / "cache.json"

# Pages stay fresh for 24h without revalidation. After that, we If-None-Match
# against the stored ETag; 304 = bump timestamp without re-downloading content.
DEFAULT_TTL_SECONDS = 24 * 3600

# Cache file format version — bump if the on-disk schema changes.
SCHEMA_VERSION = 1


@dataclass
class CacheEntry:
    content: str
    etag: str | None = None
    fetched_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"content": self.content, "etag": self.etag, "fetched_at": self.fetched_at}

    @classmethod
    def from_dict(cls, data: dict) -> CacheEntry:
        return cls(
            content=data["content"],
            etag=data.get("etag"),
            fetched_at=float(data.get("fetched_at", 0.0)),
        )

    def is_fresh(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> bool:
        return (time.time() - self.fetched_at) < ttl_seconds


class DocsCache:
    """JSON-file-backed cache of cleaned docs pages."""

    def __init__(self, path: Path = CACHE_FILE, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self.path = path
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, CacheEntry] = {}
        self._loaded = False

    # ------------------------------------------------------------------ I/O

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True

        if not self.path.exists():
            log.info("cache file not present, starting fresh at %s", self.path)
            return

        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("cache file unreadable (%s); starting fresh", exc)
            return

        if data.get("schema_version") != SCHEMA_VERSION:
            log.warning(
                "cache schema mismatch (got %s, want %s); discarding",
                data.get("schema_version"),
                SCHEMA_VERSION,
            )
            return

        entries_raw = data.get("entries", {})
        for path, entry_dict in entries_raw.items():
            try:
                self._entries[path] = CacheEntry.from_dict(entry_dict)
            except (KeyError, TypeError, ValueError):
                log.warning("skipping malformed cache entry for %s", path)

        log.info("loaded %d cache entries from %s", len(self._entries), self.path)

    def _save(self) -> None:
        """Atomic write: dump to <path>.tmp then os.replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "saved_at": time.time(),
            "entries": {path: entry.to_dict() for path, entry in self._entries.items()},
        }
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, self.path)

    # -------------------------------------------------------------- Public

    def get(self, path: str) -> CacheEntry | None:
        """Return the cached entry for a path, or None. Does not refresh."""
        self._load()
        return self._entries.get(normalize_path(path))

    def put(self, path: str, content: str, *, etag: str | None = None) -> None:
        """
        Store cleaned content for a path and atomically persist to disk.

        Public counterpart to `get_or_fetch`'s internal write — used by
        callers that already have the cleaned content in hand and want
        to seed the cache without reaching into private state.
        """
        self._load()
        self._entries[normalize_path(path)] = CacheEntry(
            content=content, etag=etag, fetched_at=time.time()
        )
        self._save()

    def put_many(self, entries: dict[str, str]) -> None:
        """
        Store many `{path: cleaned_content}` pairs and persist with one
        atomic write at the end. Used by the parallel warmup so we
        don't fsync once per page.
        """
        self._load()
        now = time.time()
        for path, content in entries.items():
            self._entries[normalize_path(path)] = CacheEntry(
                content=content, etag=None, fetched_at=now
            )
        self._save()

    def get_or_fetch(self, path: str) -> str:
        """
        Return cleaned content for a path. If cached and fresh, serve from cache.
        If stale, conditionally re-fetch (If-None-Match); 304 bumps timestamp,
        200 replaces content. If not cached at all, fetch unconditionally.

        Raises FetchError on network failure when we don't already have a
        usable cached entry to fall back to.
        """
        self._load()
        path = normalize_path(path)
        entry = self._entries.get(path)

        # Fresh cache hit: serve directly.
        if entry is not None and entry.is_fresh(self.ttl_seconds):
            log.debug("cache hit (fresh) %s", path)
            return entry.content

        # Stale or missing: fetch (conditionally if we have an etag).
        try:
            html, new_etag = fetch_page_with_etag(
                path, etag=entry.etag if entry else None
            )
        except FetchError as exc:
            # If we have a stale entry, serving it is strictly better than raising.
            if entry is not None:
                log.warning("fetch failed for %s (%s); serving stale cache", path, exc)
                return entry.content
            raise

        if html is None:
            # 304 Not Modified — refresh timestamp on existing entry.
            assert entry is not None, "304 without prior entry is a bug"
            entry.fetched_at = time.time()
            self._entries[path] = entry
            self._save()
            log.debug("cache revalidated (304) %s", path)
            return entry.content

        # 200 with fresh content — clean and store.
        content = extract_text(html)
        self._entries[path] = CacheEntry(
            content=content, etag=new_etag, fetched_at=time.time()
        )
        self._save()
        log.info("cache refreshed %s (%d chars)", path, len(content))
        return content

    def invalidate(self, path: str | None = None) -> None:
        """Drop one entry, or the whole cache if path is None."""
        self._load()
        if path is None:
            self._entries.clear()
            if self.path.exists():
                self.path.unlink()
            log.info("cache cleared")
        else:
            self._entries.pop(normalize_path(path), None)
            self._save()
            log.info("cache entry invalidated %s", path)

    def stats(self) -> dict:
        """Return a snapshot of cache state for introspection."""
        self._load()
        now = time.time()
        total = len(self._entries)
        fresh = sum(1 for e in self._entries.values() if e.is_fresh(self.ttl_seconds))
        return {
            "total": total,
            "fresh": fresh,
            "stale": total - fresh,
            "ttl_seconds": self.ttl_seconds,
            "cache_file": str(self.path),
            "oldest_age_seconds": (
                now - min((e.fetched_at for e in self._entries.values()), default=now)
            ),
        }


# Module-level default instance; server.py uses this.
_default_cache: DocsCache | None = None


def get_cache() -> DocsCache:
    """Singleton-ish accessor for the default disk cache."""
    global _default_cache
    if _default_cache is None:
        _default_cache = DocsCache()
    return _default_cache
