"""
Tests for the GitHub-refreshed index tier.

Every test monkeypatches REMOTE_INDEX_PATH / REMOTE_INDEX_META_PATH onto a
fresh tmp_path so nothing escapes into the real user cache. The module-
level constants stay the product-facing defaults; tests treat them as
injection points.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from vipmp_docs_mcp import remote_index


@pytest.fixture(autouse=True)
def isolate_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Redirect all remote-index disk paths into tmp_path for every test."""
    idx = tmp_path / "remote-index.json"
    meta = tmp_path / "remote-index.meta.json"
    monkeypatch.setattr(remote_index, "REMOTE_INDEX_PATH", idx)
    monkeypatch.setattr(remote_index, "REMOTE_INDEX_META_PATH", meta)
    # Clear the env var so tests don't accidentally inherit a disable flag.
    monkeypatch.delenv(remote_index.DISABLE_ENV, raising=False)
    return idx, meta


def _valid_index_body() -> bytes:
    """Build a payload that satisfies the structural-invariant floors."""
    from vipmp_docs_mcp.index import INDEX_SCHEMA_VERSION
    from vipmp_docs_mcp.remote_index import (
        MIN_ENDPOINTS,
        MIN_ERROR_CODES,
        MIN_SCHEMAS,
    )

    return json.dumps(
        {
            "schema_version": INDEX_SCHEMA_VERSION,
            "endpoints": [{} for _ in range(MIN_ENDPOINTS)],
            "error_codes": [{} for _ in range(MIN_ERROR_CODES)],
            "schemas": [{} for _ in range(MIN_SCHEMAS)],
        }
    ).encode()


SAMPLE_BODY = _valid_index_body()


class TestDisabled:
    def test_env_var_disables(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ):
        monkeypatch.setenv(remote_index.DISABLE_ENV, "1")
        # If the tier runs, pytest-httpx will complain about the unmocked request.
        assert remote_index.ensure_fresh() is None

    @pytest.mark.parametrize("value", ["1", "true", "yes", "ON", " 1 "])
    def test_env_var_truthy_values(
        self, monkeypatch: pytest.MonkeyPatch, value: str
    ):
        monkeypatch.setenv(remote_index.DISABLE_ENV, value)
        assert remote_index.ensure_fresh() is None

    def test_env_var_empty_does_not_disable(
        self, monkeypatch: pytest.MonkeyPatch, httpx_mock: HTTPXMock
    ):
        monkeypatch.setenv(remote_index.DISABLE_ENV, "")
        httpx_mock.add_response(url=remote_index.REMOTE_INDEX_URL, content=SAMPLE_BODY)
        assert remote_index.ensure_fresh() == remote_index.REMOTE_INDEX_PATH


class TestFreshFetch:
    def test_first_fetch_writes_body_and_meta(
        self, httpx_mock: HTTPXMock, isolate_cache
    ):
        idx, meta = isolate_cache
        httpx_mock.add_response(
            url=remote_index.REMOTE_INDEX_URL,
            content=SAMPLE_BODY,
            headers={"ETag": 'W/"abc123"'},
        )

        path = remote_index.ensure_fresh()
        assert path == idx
        assert idx.read_bytes() == SAMPLE_BODY

        meta_data = json.loads(meta.read_text())
        assert meta_data["etag"] == 'W/"abc123"'
        assert meta_data["content_length"] == len(SAMPLE_BODY)
        assert abs(meta_data["fetched_at"] - time.time()) < 5

    def test_non_json_response_discarded(self, httpx_mock: HTTPXMock, isolate_cache):
        idx, _ = isolate_cache
        httpx_mock.add_response(
            url=remote_index.REMOTE_INDEX_URL,
            content=b"<html>rate limited</html>",
        )
        # No cached copy, so we return None rather than writing garbage.
        assert remote_index.ensure_fresh() is None
        assert not idx.exists()

    def test_invariant_failure_keeps_cached_copy(
        self, httpx_mock: HTTPXMock, isolate_cache
    ):
        idx, _ = isolate_cache
        idx.write_bytes(SAMPLE_BODY)

        # A poisoned index that's mostly empty must NOT overwrite the cache.
        bad_body = json.dumps(
            {
                "schema_version": 4,
                "endpoints": [],
                "error_codes": [],
                "schemas": [],
            }
        ).encode()
        httpx_mock.add_response(
            url=remote_index.REMOTE_INDEX_URL, content=bad_body
        )

        path = remote_index.ensure_fresh()
        assert path == idx
        # Cached copy preserved.
        assert idx.read_bytes() == SAMPLE_BODY

    def test_invariant_failure_returns_none_when_uncached(
        self, httpx_mock: HTTPXMock, isolate_cache
    ):
        idx, _ = isolate_cache
        bad_body = json.dumps(
            {
                "schema_version": 4,
                "endpoints": [],
                "error_codes": [],
                "schemas": [],
            }
        ).encode()
        httpx_mock.add_response(
            url=remote_index.REMOTE_INDEX_URL, content=bad_body
        )
        assert remote_index.ensure_fresh() is None
        assert not idx.exists()

    def test_invariant_failure_on_schema_version_mismatch(
        self, httpx_mock: HTTPXMock, isolate_cache
    ):
        idx, _ = isolate_cache
        bad_body = json.dumps(
            {
                "schema_version": 999,
                "endpoints": [{} for _ in range(20)],
                "error_codes": [{} for _ in range(40)],
                "schemas": [{} for _ in range(10)],
            }
        ).encode()
        httpx_mock.add_response(
            url=remote_index.REMOTE_INDEX_URL, content=bad_body
        )
        assert remote_index.ensure_fresh() is None
        assert not idx.exists()

    def test_non_200_response_returns_none_when_uncached(
        self, httpx_mock: HTTPXMock, isolate_cache
    ):
        idx, _ = isolate_cache
        httpx_mock.add_response(url=remote_index.REMOTE_INDEX_URL, status_code=500)
        assert remote_index.ensure_fresh() is None
        assert not idx.exists()


class TestTTLShortCircuit:
    def test_within_ttl_skips_network(self, isolate_cache):
        idx, meta = isolate_cache
        idx.write_bytes(SAMPLE_BODY)
        meta.write_text(json.dumps({"fetched_at": time.time() - 60, "etag": "x"}))

        # No httpx_mock responses registered — any network call would fail.
        assert remote_index.ensure_fresh() == idx

    def test_expired_ttl_triggers_conditional_get(
        self, httpx_mock: HTTPXMock, isolate_cache
    ):
        idx, meta = isolate_cache
        idx.write_bytes(SAMPLE_BODY)
        stale = time.time() - (remote_index.TTL_SECONDS + 100)
        meta.write_text(json.dumps({"fetched_at": stale, "etag": 'W/"old"'}))

        # Assert the request carries the stored ETag.
        httpx_mock.add_response(
            url=remote_index.REMOTE_INDEX_URL,
            match_headers={"If-None-Match": 'W/"old"'},
            status_code=304,
        )

        assert remote_index.ensure_fresh() == idx

        # 304 updates fetched_at but preserves the ETag and body.
        meta_data = json.loads(meta.read_text())
        assert meta_data["etag"] == 'W/"old"'
        assert abs(meta_data["fetched_at"] - time.time()) < 5


class TestNetworkFailureFallback:
    def test_transport_error_returns_cached_copy(
        self, httpx_mock: HTTPXMock, isolate_cache
    ):
        idx, meta = isolate_cache
        idx.write_bytes(SAMPLE_BODY)
        meta.write_text(
            json.dumps({"fetched_at": time.time() - remote_index.TTL_SECONDS - 1})
        )

        # Simulate GitHub unreachable for every retry attempt.
        for _ in range(3):
            httpx_mock.add_exception(httpx.ConnectError("boom"))

        path = remote_index.ensure_fresh()
        assert path == idx  # stale-OK: we keep what we had
        assert idx.read_bytes() == SAMPLE_BODY

    def test_transport_error_returns_none_when_uncached(
        self, httpx_mock: HTTPXMock, isolate_cache
    ):
        idx, _ = isolate_cache
        for _ in range(3):
            httpx_mock.add_exception(httpx.ConnectError("boom"))
        assert remote_index.ensure_fresh() is None
        assert not idx.exists()


class TestStatus:
    def test_reports_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(remote_index.DISABLE_ENV, "1")
        status = remote_index.get_status()
        assert status == {"enabled": False, "reason": f"{remote_index.DISABLE_ENV} is set"}

    def test_reports_cached_state(self, isolate_cache):
        idx, meta = isolate_cache
        idx.write_bytes(SAMPLE_BODY)
        meta.write_text(json.dumps({"fetched_at": 1234567890.0, "etag": "x"}))

        status = remote_index.get_status()
        assert status["enabled"] is True
        assert status["cached"] is True
        assert status["fetched_at"] == 1234567890.0
        assert status["etag"] == "x"
        assert status["ttl_seconds"] == remote_index.TTL_SECONDS

    def test_status_does_not_trigger_fetch(self, isolate_cache):
        idx, meta = isolate_cache
        # No httpx_mock fixture here — if get_status hit the network the
        # test would fail with an unmocked-request error.
        status = remote_index.get_status()
        assert status["cached"] is False
        assert not idx.exists()
        assert not meta.exists()
