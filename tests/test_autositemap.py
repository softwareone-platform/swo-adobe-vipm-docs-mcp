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
    SITEMAP_SCHEMA_VERSION,
    get_active_sitemap,
    merge_curated_tags,
)


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
