"""Tests for the disk cache — round-trip, TTL, invalidation."""

from __future__ import annotations

import time
from pathlib import Path

from vipmp_docs_mcp.cache import CacheEntry, DocsCache


class TestCacheEntry:
    def test_fresh_when_new(self):
        e = CacheEntry(content="x")
        assert e.is_fresh(ttl_seconds=3600)

    def test_stale_after_ttl(self):
        e = CacheEntry(content="x", fetched_at=time.time() - 7200)
        assert not e.is_fresh(ttl_seconds=3600)

    def test_roundtrip(self):
        e = CacheEntry(content="hello", etag='W/"abc"', fetched_at=1234567890.0)
        e2 = CacheEntry.from_dict(e.to_dict())
        assert e2.content == "hello"
        assert e2.etag == 'W/"abc"'
        assert e2.fetched_at == 1234567890.0


class TestDocsCache:
    def test_persists_across_instances(self, tmp_cache_path: Path):
        cache = DocsCache(path=tmp_cache_path)
        cache._entries["/x"] = CacheEntry(content="body")
        cache._save()

        cache2 = DocsCache(path=tmp_cache_path)
        entry = cache2.get("/x")
        assert entry is not None
        assert entry.content == "body"

    def test_missing_file_starts_empty(self, tmp_cache_path: Path):
        cache = DocsCache(path=tmp_cache_path)
        assert cache.get("/anything") is None

    def test_invalidate_single(self, tmp_cache_path: Path):
        cache = DocsCache(path=tmp_cache_path)
        cache._entries["/a"] = CacheEntry(content="A")
        cache._entries["/b"] = CacheEntry(content="B")
        cache._save()

        cache.invalidate("/a")
        assert cache.get("/a") is None
        assert cache.get("/b") is not None

    def test_invalidate_all(self, tmp_cache_path: Path):
        cache = DocsCache(path=tmp_cache_path)
        cache._entries["/a"] = CacheEntry(content="A")
        cache._save()

        cache.invalidate()
        assert cache.get("/a") is None
        assert not tmp_cache_path.exists()

    def test_stats(self, tmp_cache_path: Path):
        cache = DocsCache(path=tmp_cache_path, ttl_seconds=3600)
        cache._entries["/fresh"] = CacheEntry(content="F", fetched_at=time.time())
        cache._entries["/stale"] = CacheEntry(content="S", fetched_at=time.time() - 10000)
        stats = cache.stats()
        assert stats["total"] == 2
        assert stats["fresh"] == 1
        assert stats["stale"] == 1

    def test_schema_mismatch_discarded(self, tmp_cache_path: Path):
        import json

        tmp_cache_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_cache_path.write_text(
            json.dumps({"schema_version": 999, "entries": {"/x": {"content": "y"}}})
        )
        cache = DocsCache(path=tmp_cache_path)
        assert cache.get("/x") is None

    def test_put_persists_single(self, tmp_cache_path: Path):
        cache = DocsCache(path=tmp_cache_path)
        cache.put("/a", "body-a", etag='W/"1"')

        cache2 = DocsCache(path=tmp_cache_path)
        entry = cache2.get("/a")
        assert entry is not None
        assert entry.content == "body-a"
        assert entry.etag == 'W/"1"'

    def test_put_many_persists_with_one_save(self, tmp_cache_path: Path):
        cache = DocsCache(path=tmp_cache_path)
        cache.put_many({"/a": "A", "/b": "B", "/c": "C"})

        cache2 = DocsCache(path=tmp_cache_path)
        for path, expected in [("/a", "A"), ("/b", "B"), ("/c", "C")]:
            entry = cache2.get(path)
            assert entry is not None
            assert entry.content == expected
