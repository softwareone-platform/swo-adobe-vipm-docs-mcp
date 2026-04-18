"""Tests for path normalization and sitemap lookup helpers."""

from __future__ import annotations

from vipmp_docs_mcp.sitemap import find_by_path, known_paths, normalize_path


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


class TestKnownPaths:
    def test_all_paths_normalized(self):
        # Every returned path should be in normalized form (leading slash, no trailing).
        for p in known_paths():
            assert p.startswith("/")
            assert p == "/" or not p.endswith("/")


class TestFindByPath:
    def test_finds_existing(self):
        entry = find_by_path("/vipmp/docs/lga/")
        assert entry is not None
        assert "LGA" in entry["title"] or "Large Government" in entry["title"]

    def test_works_regardless_of_slash(self):
        with_slash = find_by_path("/vipmp/docs/lga/")
        without_slash = find_by_path("/vipmp/docs/lga")
        assert with_slash is not None
        assert without_slash is not None
        assert with_slash["path"] == without_slash["path"]

    def test_returns_none_for_unknown(self):
        assert find_by_path("/vipmp/docs/definitely-not-a-page/") is None
