"""Tests for the parallel async fetcher."""

from __future__ import annotations

import asyncio

from pytest_httpx import HTTPXMock

from vipmp_docs_mcp.fetcher import (
    BASE_URL,
    FetchError,
    async_fetch_many,
)

REAL_PAGE_HTML = "<html><body><main>vipmp content</main></body></html>"


class TestAsyncFetchMany:
    def test_all_succeed(self, httpx_mock: HTTPXMock):
        for path in ["/a", "/b", "/c"]:
            httpx_mock.add_response(url=f"{BASE_URL}{path}", html=REAL_PAGE_HTML)

        results = asyncio.run(async_fetch_many(["/a", "/b", "/c"]))
        assert set(results.keys()) == {"/a", "/b", "/c"}
        assert all(isinstance(v, str) for v in results.values())

    def test_partial_failure_isolated(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=f"{BASE_URL}/ok", html=REAL_PAGE_HTML)
        # Both slash variants of /missing 404
        httpx_mock.add_response(url=f"{BASE_URL}/missing", status_code=404)
        httpx_mock.add_response(url=f"{BASE_URL}/missing/", status_code=404)

        results = asyncio.run(async_fetch_many(["/ok", "/missing"]))
        assert isinstance(results["/ok"], str)
        assert isinstance(results["/missing"], FetchError)
        assert "404" in str(results["/missing"])

    def test_empty_input_returns_empty(self):
        results = asyncio.run(async_fetch_many([]))
        assert results == {}

    def test_trailing_slash_fallback(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=f"{BASE_URL}/x", status_code=404)
        httpx_mock.add_response(url=f"{BASE_URL}/x/", html=REAL_PAGE_HTML)
        results = asyncio.run(async_fetch_many(["/x"]))
        assert isinstance(results["/x"], str)

    def test_progress_callback_invoked(self, httpx_mock: HTTPXMock):
        for path in ["/a", "/b"]:
            httpx_mock.add_response(url=f"{BASE_URL}{path}", html=REAL_PAGE_HTML)

        calls: list[tuple[int, int, str]] = []

        def cb(done: int, total: int, path: str, err: object) -> None:
            calls.append((done, total, path))

        asyncio.run(async_fetch_many(["/a", "/b"], on_progress=cb))
        assert len(calls) == 2
        assert {c[2] for c in calls} == {"/a", "/b"}
        assert all(c[1] == 2 for c in calls)

    def test_async_progress_callback_awaited(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=f"{BASE_URL}/x", html=REAL_PAGE_HTML)

        calls: list[str] = []

        async def cb(done: int, total: int, path: str, err: object) -> None:
            calls.append(path)

        asyncio.run(async_fetch_many(["/x"], on_progress=cb))
        assert calls == ["/x"]

    def test_concurrency_respected(self, httpx_mock: HTTPXMock):
        # Just check that with concurrency=1 we still get all results back —
        # functional correctness rather than timing.
        for path in ["/a", "/b", "/c"]:
            httpx_mock.add_response(url=f"{BASE_URL}{path}", html=REAL_PAGE_HTML)
        results = asyncio.run(async_fetch_many(["/a", "/b", "/c"], concurrency=1))
        assert set(results.keys()) == {"/a", "/b", "/c"}

    def test_suspicious_content_treated_as_failure(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/login",
            html="<html><body>please log in</body></html>",
        )
        results = asyncio.run(async_fetch_many(["/login"]))
        assert isinstance(results["/login"], FetchError)

    def test_transient_5xx_is_retried(self, httpx_mock: HTTPXMock):
        # First two responses 503, then 200 — the async path should retry
        # under the same policy as the sync path and end up succeeding.
        url = f"{BASE_URL}/flaky"
        httpx_mock.add_response(url=url, status_code=503)
        httpx_mock.add_response(url=url, status_code=503)
        httpx_mock.add_response(url=url, html=REAL_PAGE_HTML)

        results = asyncio.run(async_fetch_many(["/flaky"]))
        assert isinstance(results["/flaky"], str)
        assert "vipmp content" in results["/flaky"]
