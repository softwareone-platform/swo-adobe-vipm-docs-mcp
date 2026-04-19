"""Tests for the structured index — roundtrip, schema mismatch, age tracking."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from vipmp_docs_mcp import index as index_module
from vipmp_docs_mcp import remote_index
from vipmp_docs_mcp.extractors import Endpoint, ErrorCode, SchemaField, SchemaResource
from vipmp_docs_mcp.index import (
    INDEX_SCHEMA_VERSION,
    IndexSnapshot,
    load_index,
    resolve_active_index,
    save_index,
)


def _sample_snap() -> IndexSnapshot:
    return IndexSnapshot(
        built_at=1_700_000_000.0,
        source_sitemap_size=3,
        pages_parsed=3,
        parse_errors=[("/broken", "HTTP 404")],
        endpoints=[
            Endpoint(method="POST", path="/v3/customers", docs_path="/a", title="Create"),
            Endpoint(method="GET", path="/v3/customers", docs_path="/b", title="List"),
        ],
        error_codes=[
            ErrorCode(code="1117", reason="bad date", endpoint="POST /v3/customers"),
        ],
        schemas=[
            SchemaResource(
                name="Customer",
                level=2,
                fields=[
                    SchemaField(
                        name="id",
                        type="String",
                        required=True,
                        description="Customer id",
                        constraints="Max 35",
                    ),
                ],
            )
        ],
    )


class TestRoundtrip:
    def test_roundtrip_preserves_all_fields(self, tmp_path: Path):
        snap = _sample_snap()
        path = tmp_path / "index.json"
        save_index(snap, path)

        loaded = load_index(path)
        assert loaded is not None
        assert loaded.source_sitemap_size == 3
        assert loaded.pages_parsed == 3
        assert len(loaded.parse_errors) == 1
        assert loaded.parse_errors[0] == ("/broken", "HTTP 404")
        assert len(loaded.endpoints) == 2
        assert loaded.endpoints[0].method == "POST"
        assert loaded.endpoints[0].path == "/v3/customers"
        assert len(loaded.error_codes) == 1
        assert loaded.error_codes[0].code == "1117"
        assert len(loaded.schemas) == 1
        assert loaded.schemas[0].name == "Customer"
        assert loaded.schemas[0].fields[0].name == "id"
        assert loaded.schemas[0].fields[0].required is True

    def test_saved_json_is_pretty(self, tmp_path: Path):
        snap = _sample_snap()
        path = tmp_path / "index.json"
        save_index(snap, path)
        # Indented JSON is easier for humans (and CI diffs).
        assert "\n" in path.read_text()
        data = json.loads(path.read_text())
        assert data["schema_version"] == INDEX_SCHEMA_VERSION


class TestLoadIndex:
    def test_missing_file_returns_none(self, tmp_path: Path):
        assert load_index(tmp_path / "nope.json") is None

    def test_schema_mismatch_returns_none(self, tmp_path: Path):
        path = tmp_path / "old.json"
        path.write_text(json.dumps({"schema_version": 999, "endpoints": []}))
        assert load_index(path) is None

    def test_corrupt_json_returns_none(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json {{{")
        assert load_index(path) is None


class TestResolveActiveIndex:
    """
    Integration-level tests for the tier chain. Each test redirects every
    tier's path to a tmp location and asserts which one wins.
    """

    @pytest.fixture(autouse=True)
    def isolate_paths(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        self.user_path = tmp_path / "user-index.json"
        self.remote_path = tmp_path / "remote-index.json"
        self.remote_meta = tmp_path / "remote-index.meta.json"
        self.pkg_path = tmp_path / "pkg-index.json"
        monkeypatch.setattr(index_module, "USER_INDEX_PATH", self.user_path)
        monkeypatch.setattr(index_module, "PACKAGE_INDEX_PATH", self.pkg_path)
        monkeypatch.setattr(remote_index, "REMOTE_INDEX_PATH", self.remote_path)
        monkeypatch.setattr(remote_index, "REMOTE_INDEX_META_PATH", self.remote_meta)
        # Disable network — tier resolution should never hit the wire here.
        monkeypatch.setenv(remote_index.DISABLE_ENV, "1")

    def _write(self, path: Path, snap: IndexSnapshot) -> None:
        save_index(snap, path)

    def test_user_local_wins_over_remote_and_baseline(self):
        self._write(self.user_path, _sample_snap())
        self._write(self.remote_path, _sample_snap())
        self._write(self.pkg_path, _sample_snap())

        active = resolve_active_index()
        assert active is not None
        assert active.source == "user-local"
        assert active.path == self.user_path

    def test_baseline_used_when_user_and_remote_absent(self):
        self._write(self.pkg_path, _sample_snap())

        active = resolve_active_index()
        assert active is not None
        assert active.source == "package-baseline"
        assert active.path == self.pkg_path

    def test_remote_wins_over_baseline(self, monkeypatch: pytest.MonkeyPatch):
        # Re-enable the remote tier and pre-populate its cache file so
        # ensure_fresh() short-circuits on TTL.
        monkeypatch.delenv(remote_index.DISABLE_ENV, raising=False)
        self._write(self.remote_path, _sample_snap())
        self.remote_meta.write_text(json.dumps({"fetched_at": time.time(), "etag": "x"}))
        self._write(self.pkg_path, _sample_snap())

        active = resolve_active_index()
        assert active is not None
        assert active.source == "github-remote"
        assert active.path == self.remote_path

    def test_none_when_nothing_available(self):
        active = resolve_active_index()
        assert active is None


class TestAgeSeconds:
    def test_recent_index_has_low_age(self):
        snap = IndexSnapshot(built_at=time.time() - 10)
        assert 5 < snap.age_seconds < 20

    def test_old_index_has_high_age(self):
        snap = IndexSnapshot(built_at=time.time() - 86400 * 30)  # 30 days
        assert snap.age_seconds > 86400 * 29
