"""Tests for the fetcher — retry, trailing-slash fallback, content validation."""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from vipmp_docs_mcp.fetcher import (
    BASE_URL,
    FetchError,
    SuspiciousContentError,
    fetch_page_html,
    fetch_page_with_etag,
)

# A minimal HTML body that passes looks_like_docs_page().
REAL_PAGE_HTML = "<html><body><main>vipmp content here</main></body></html>"


class TestFetchPageHtml:
    def test_happy_path(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/x", html=REAL_PAGE_HTML)
        assert fetch_page_html("/vipmp/docs/x") == REAL_PAGE_HTML

    def test_trailing_slash_fallback_on_404(self, httpx_mock: HTTPXMock):
        # First form 404s, second form (with trailing slash) returns 200.
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/x", status_code=404)
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/x/", html=REAL_PAGE_HTML)
        assert fetch_page_html("/vipmp/docs/x") == REAL_PAGE_HTML

    def test_both_variants_404_raises(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/nope", status_code=404)
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/nope/", status_code=404)
        with pytest.raises(FetchError, match="404"):
            fetch_page_html("/vipmp/docs/nope")

    def test_suspicious_content_raises(self, httpx_mock: HTTPXMock):
        # Response body is missing every expected marker.
        httpx_mock.add_response(
            url=f"{BASE_URL}/vipmp/docs/login",
            html="<html><body>please log in</body></html>",
        )
        with pytest.raises(SuspiciousContentError):
            fetch_page_html("/vipmp/docs/login")

    def test_validate_false_skips_content_check(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/sitemap.xml",
            html="<?xml version='1.0'?><urlset></urlset>",
        )
        # No SuspiciousContentError even though body has no "vipmp" marker.
        out = fetch_page_html("/sitemap.xml", validate=False)
        assert "urlset" in out

    def test_retries_on_502(self, httpx_mock: HTTPXMock):
        # First attempt 502, second 200.
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/x", status_code=502)
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/x", html=REAL_PAGE_HTML)
        assert fetch_page_html("/vipmp/docs/x") == REAL_PAGE_HTML


class TestFetchPageWithEtag:
    def test_304_returns_none_html(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/x", status_code=304)
        html, etag = fetch_page_with_etag("/vipmp/docs/x", etag='W/"old"')
        assert html is None
        assert etag == 'W/"old"'  # unchanged

    def test_200_returns_new_etag(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url=f"{BASE_URL}/vipmp/docs/x",
            html=REAL_PAGE_HTML,
            headers={"ETag": 'W/"new"'},
        )
        html, etag = fetch_page_with_etag("/vipmp/docs/x")
        assert html == REAL_PAGE_HTML
        assert etag == 'W/"new"'

    def test_trailing_slash_fallback_on_404(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(url=f"{BASE_URL}/vipmp/docs/x", status_code=404)
        httpx_mock.add_response(
            url=f"{BASE_URL}/vipmp/docs/x/",
            html=REAL_PAGE_HTML,
            headers={"ETag": 'W/"v1"'},
        )
        html, etag = fetch_page_with_etag("/vipmp/docs/x")
        assert html == REAL_PAGE_HTML
        assert etag == 'W/"v1"'
