"""Tests for normalize_path and the CURATED_TAGS metadata."""

from __future__ import annotations

from vipmp_docs_mcp.sitemap import CURATED_TAGS, normalize_path


class TestNormalizePath:
    def test_adds_leading_slash(self):
        assert normalize_path("vipmp/docs/lga") == "/vipmp/docs/lga"

    def test_strips_trailing_slash(self):
        assert normalize_path("/vipmp/docs/lga/") == "/vipmp/docs/lga"

    def test_preserves_root_slash(self):
        assert normalize_path("/") == "/"

    def test_idempotent(self):
        p = normalize_path("/vipmp/docs/lga")
        assert normalize_path(p) == p

    def test_handles_bare_path(self):
        assert normalize_path("x") == "/x"


class TestCuratedTags:
    def test_has_entries(self):
        """Regression guard — the dict shouldn't silently empty out."""
        assert len(CURATED_TAGS) > 50

    def test_keys_are_hyphenated_slug_form(self):
        """Every key is a bare lowercase slug (hyphens, no underscores,
        no slashes, no whitespace). ``autositemap.merge_curated_tags``
        looks up by the last path segment of a live Adobe entry, so any
        key that doesn't match that shape is dead weight."""
        for key in CURATED_TAGS:
            assert key == key.lower()
            assert "_" not in key
            assert "/" not in key
            assert " " not in key

    def test_values_are_non_empty_lists(self):
        for key, tags in CURATED_TAGS.items():
            assert isinstance(tags, list), f"{key!r} tags isn't a list"
            assert tags, f"{key!r} has no tags — delete the entry instead"
            for tag in tags:
                assert isinstance(tag, str) and tag
