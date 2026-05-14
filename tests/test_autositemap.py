"""
Tests for the sitemap tier resolution introduced in 0.7.2 (GitHub #6).

Covers ``get_active_sitemap``'s priority chain (user cache → package-shipped
→ empty) and ``merge_curated_tags``'s interaction with ``CURATED_TAGS``.
The network-heavy ``build_sitemap`` path stays out of scope here — it's
exercised end-to-end by the CI refresh workflow.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from vipmp_docs_mcp import autositemap
from vipmp_docs_mcp.autositemap import (
    MIN_VIPMP_SITEMAP_PATHS,
    SITEMAP_SCHEMA_VERSION,
    _fetch_sitemap_paths,
    get_active_sitemap,
    merge_curated_tags,
    save_sitemap,
)
from vipmp_docs_mcp.fetcher import FetchError


def _payload(entries: list[dict]) -> str:
    return json.dumps(
        {
            "schema_version": SITEMAP_SCHEMA_VERSION,
            "generated_at": time.time(),
            "entries": entries,
        }
    )


class TestGetActiveSitemapTierOrder:
    @pytest.fixture(autouse=True)
    def isolate_paths(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """Redirect both tier paths to tmp_path so tests never touch
        the real user cache or the shipped package fallback."""
        self.user_path = tmp_path / "user-sitemap.json"
        self.pkg_path = tmp_path / "pkg-sitemap.json"
        monkeypatch.setattr(autositemap, "SITEMAP_JSON_PATH", self.user_path)
        monkeypatch.setattr(autositemap, "PACKAGE_SITEMAP_PATH", self.pkg_path)

    def test_user_cache_wins_over_package(self):
        self.user_path.write_text(
            _payload([{"path": "/vipmp/docs/u", "title": "User", "tags": []}])
        )
        self.pkg_path.write_text(
            _payload([{"path": "/vipmp/docs/p", "title": "Package", "tags": []}])
        )
        active = get_active_sitemap()
        assert len(active) == 1
        assert active[0]["title"] == "User"

    def test_package_fallback_when_user_missing(self):
        self.pkg_path.write_text(
            _payload([{"path": "/vipmp/docs/p", "title": "Package", "tags": []}])
        )
        active = get_active_sitemap()
        assert len(active) == 1
        assert active[0]["title"] == "Package"

    def test_empty_when_both_missing(self):
        """Last resort — no hand-curated list to fall back to anymore
        (retired in 0.7.2). Callers must handle empty gracefully."""
        active = get_active_sitemap()
        assert active == []

    def test_package_fallback_when_user_is_corrupt(self):
        """A broken user cache shouldn't mask the package fallback."""
        self.user_path.write_text("not json {{{")
        self.pkg_path.write_text(
            _payload([{"path": "/vipmp/docs/p", "title": "Package", "tags": []}])
        )
        active = get_active_sitemap()
        assert len(active) == 1
        assert active[0]["title"] == "Package"

    def test_schema_mismatch_falls_through(self):
        """A user cache written under an old schema version is ignored."""
        self.user_path.write_text(
            json.dumps(
                {
                    "schema_version": SITEMAP_SCHEMA_VERSION + 99,
                    "generated_at": time.time(),
                    "entries": [{"path": "/vipmp/docs/u", "title": "Old", "tags": []}],
                }
            )
        )
        self.pkg_path.write_text(
            _payload([{"path": "/vipmp/docs/p", "title": "Package", "tags": []}])
        )
        active = get_active_sitemap()
        assert active[0]["title"] == "Package"


class TestMergeCuratedTags:
    def test_attaches_tags_for_known_last_segment(self):
        entries = [
            {
                "path": "/vipmp/docs/authentication",
                "title": "Authentication",
                "tags": ["existing"],
            }
        ]
        out = merge_curated_tags(entries)
        # `authentication` is a known key in CURATED_TAGS.
        assert "existing" in out[0]["tags"]
        assert "oauth" in out[0]["tags"]

    def test_unknown_segment_leaves_tags_alone(self):
        entries = [
            {
                "path": "/vipmp/docs/some-never-heard-of-thing",
                "title": "Whatever",
                "tags": ["only-this"],
            }
        ]
        out = merge_curated_tags(entries)
        assert out[0]["tags"] == ["only-this"]

    def test_preserves_uniqueness_and_sorts(self):
        """Merge must dedup tags (entry + curated can overlap) and return
        them in a stable sorted order."""
        entries = [
            {
                "path": "/vipmp/docs/authentication",
                "title": "Authentication",
                "tags": ["oauth", "zzz-last"],  # "oauth" is also in CURATED_TAGS
            }
        ]
        out = merge_curated_tags(entries)
        tags = out[0]["tags"]
        assert tags == sorted(tags)
        assert tags.count("oauth") == 1  # no duplicates
        assert "zzz-last" in tags


class TestFetchSitemapPathsFailLoud:
    """Guard added after the 2026-05-13/14 incident where Adobe's CDN
    returned a sitemap.xml with zero vipmp paths and the build silently
    produced an empty index."""

    def _xml(self, vipmp_count: int = 0, extra_urls: int = 5) -> str:
        urls = [
            f"<url><loc>https://developer.adobe.com/other/{i}/</loc></url>"
            for i in range(extra_urls)
        ] + [
            f"<url><loc>https://developer.adobe.com/vipmp/docs/page-{i}</loc></url>"
            for i in range(vipmp_count)
        ]
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(urls)
            + "</urlset>"
        )

    def test_raises_when_no_vipmp_paths(self, monkeypatch: pytest.MonkeyPatch):
        body = self._xml(vipmp_count=0, extra_urls=12)
        monkeypatch.setattr(autositemap, "fetch_page_html", lambda *a, **k: body)
        with pytest.raises(FetchError) as exc_info:
            _fetch_sitemap_paths()
        msg = str(exc_info.value)
        assert "0 vipmp paths" in msg
        assert str(len(body)) in msg  # response byte count for diagnosis
        assert "12 total URLs" in msg

    def test_raises_when_below_floor(self, monkeypatch: pytest.MonkeyPatch):
        body = self._xml(vipmp_count=MIN_VIPMP_SITEMAP_PATHS - 1, extra_urls=0)
        monkeypatch.setattr(autositemap, "fetch_page_html", lambda *a, **k: body)
        with pytest.raises(FetchError, match=r"minimum 50"):
            _fetch_sitemap_paths()

    def test_passes_at_floor(self, monkeypatch: pytest.MonkeyPatch):
        body = self._xml(vipmp_count=MIN_VIPMP_SITEMAP_PATHS, extra_urls=0)
        monkeypatch.setattr(autositemap, "fetch_page_html", lambda *a, **k: body)
        paths = _fetch_sitemap_paths()
        assert len(paths) == MIN_VIPMP_SITEMAP_PATHS


class TestSaveSitemapOverwriteGuard:
    def test_refuses_to_overwrite_healthy_file_with_empty(self, tmp_path: Path):
        path = tmp_path / "sitemap.json"
        path.write_text(_payload([{"path": "/vipmp/docs/x", "title": "Existing", "tags": []}]))
        with pytest.raises(ValueError, match=r"refusing to overwrite"):
            save_sitemap([], path)
        # File untouched.
        assert json.loads(path.read_text())["entries"][0]["title"] == "Existing"

    def test_overwrites_empty_file_with_empty(self, tmp_path: Path):
        """An existing-but-empty file is fine to overwrite — there's nothing to lose."""
        path = tmp_path / "sitemap.json"
        path.write_text(_payload([]))
        save_sitemap([], path)  # no exception
        assert json.loads(path.read_text())["entries"] == []

    def test_writes_normally_when_file_missing(self, tmp_path: Path):
        path = tmp_path / "sitemap.json"
        save_sitemap([], path)  # no exception, creates the file
        assert path.exists()
        assert json.loads(path.read_text())["entries"] == []

    def test_writes_normally_with_non_empty_entries(self, tmp_path: Path):
        """Non-empty payload always writes, even over an existing healthy file."""
        path = tmp_path / "sitemap.json"
        path.write_text(_payload([{"path": "/vipmp/docs/old", "title": "Old", "tags": []}]))
        save_sitemap([{"path": "/vipmp/docs/new", "title": "New", "tags": []}], path)
        assert json.loads(path.read_text())["entries"][0]["title"] == "New"
