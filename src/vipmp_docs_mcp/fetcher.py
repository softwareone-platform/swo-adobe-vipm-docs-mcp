"""
HTTP client with retries, backoff, and content sanity checks.

Wraps httpx with tenacity for resilience. Everything that fetches a page
from developer.adobe.com goes through this module.
"""

from __future__ import annotations

import httpx
from tenacity import (
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .html_cleaner import looks_like_docs_page
from .logging_config import get_logger

log = get_logger("fetcher")

BASE_URL = "https://developer.adobe.com"
DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=10.0)

# Transient statuses worth retrying. Everything else is permanent.
_RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


class FetchError(Exception):
    """Raised when a fetch fails in a way the caller should surface."""


class SuspiciousContentError(FetchError):
    """Raised when the fetched HTML doesn't look like a real Adobe docs page."""


def _is_retryable(exc: BaseException) -> bool:
    """Predicate: retry transient network/timeout/5xx; don't retry permanent 4xx."""
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS
    return False


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
def _fetch_with_retries(client: httpx.Client, url: str, headers: dict[str, str]) -> httpx.Response:
    """Inner retry-wrapped fetch. Only transient errors retry."""
    log.debug("fetching %s", url)
    response = client.get(url, headers=headers)
    # Trigger retry for transient 5xx / 429 / etc.
    if response.status_code in _RETRYABLE_STATUS:
        response.raise_for_status()
    return response


def _default_headers(etag: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SWOVIPMPDocsMCP/0.2)",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Encoding": "gzip, deflate",
    }
    if etag:
        headers["If-None-Match"] = etag
    return headers


def _trailing_slash_variants(path: str) -> list[str]:
    """
    Return path + its trailing-slash sibling. Adobe's docs 404 on the
    "wrong" variant (and neither form is consistent), so on 404 we try
    the other form before giving up.
    """
    if path.endswith("/"):
        return [path, path.rstrip("/") or "/"]
    return [path, path + "/"]


def _fetch_one(client: httpx.Client, url: str, headers: dict[str, str]) -> httpx.Response:
    """Single fetch with tenacity retries, with the returned response unwrapped."""
    return _fetch_with_retries(client, url, headers)


def fetch_page_html(path: str, *, validate: bool = True) -> str:
    """
    Fetch a docs page by path and return its raw HTML.

    On 404, automatically retries the opposite trailing-slash variant —
    Adobe's docs site is inconsistent about which form resolves.

    Args:
        path: Absolute path on developer.adobe.com (e.g. "/vipmp/docs/").
        validate: If True, verify the response looks like a real docs page
            before returning. Raises SuspiciousContentError on mismatch.

    Raises:
        FetchError: On non-retryable 4xx (after trying both slash variants),
            post-retry 5xx, or network failure.
        SuspiciousContentError: If validate=True and the response body
            doesn't contain expected markers.
    """
    last_err: Exception | None = None
    for candidate in _trailing_slash_variants(path):
        url = BASE_URL + candidate
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
                response = _fetch_one(client, url, _default_headers())
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            log.warning("network error for %s: %s", candidate, exc)
            raise FetchError(f"network error fetching {path}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            log.warning("HTTP %s for %s after retries", exc.response.status_code, candidate)
            raise FetchError(
                f"HTTP {exc.response.status_code} {exc.response.reason_phrase} for {path}"
            ) from exc
        except RetryError as exc:
            log.warning("retries exhausted for %s", candidate)
            raise FetchError(f"retries exhausted fetching {path}") from exc

        # 404 → fall through and try the other slash variant.
        if response.status_code == 404:
            last_err = FetchError(f"HTTP 404 Not Found for {candidate}")
            log.debug("404 for %s; trying next variant", candidate)
            continue

        if response.status_code >= 400:
            log.warning("HTTP %s for %s (non-retryable)", response.status_code, candidate)
            raise FetchError(
                f"HTTP {response.status_code} {response.reason_phrase} for {path}"
            )

        html = response.text
        if validate and not looks_like_docs_page(html):
            log.warning("suspicious content for %s (len=%d)", candidate, len(html))
            raise SuspiciousContentError(
                f"response for {path} did not look like an Adobe docs page; "
                "this could be a login wall, maintenance page, or CDN error"
            )

        log.debug("fetched %s (%d bytes)", candidate, len(html))
        return html

    # All variants 404'd.
    assert last_err is not None
    raise last_err


def fetch_page_with_etag(
    path: str, *, etag: str | None = None, validate: bool = True
) -> tuple[str | None, str | None]:
    """
    Conditional fetch using If-None-Match. Returns (html, etag).

    Also tries the opposite trailing-slash variant on 404. If the server
    returns 304 Not Modified, html is None and etag is the unchanged tag.
    Otherwise html is the body and etag is the new value (or None).
    """
    last_err: Exception | None = None
    for candidate in _trailing_slash_variants(path):
        url = BASE_URL + candidate
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
                response = _fetch_one(client, url, _default_headers(etag))
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            log.warning("network error for %s: %s", candidate, exc)
            raise FetchError(f"network error fetching {path}: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            log.warning("HTTP %s for %s after retries", exc.response.status_code, candidate)
            raise FetchError(
                f"HTTP {exc.response.status_code} {exc.response.reason_phrase} for {path}"
            ) from exc
        except RetryError as exc:
            log.warning("retries exhausted for %s", candidate)
            raise FetchError(f"retries exhausted fetching {path}") from exc

        if response.status_code == 304:
            log.debug("304 not modified for %s", candidate)
            return None, etag

        if response.status_code == 404:
            last_err = FetchError(f"HTTP 404 Not Found for {candidate}")
            log.debug("404 for %s; trying next variant", candidate)
            continue

        if response.status_code >= 400:
            log.warning("HTTP %s for %s (non-retryable)", response.status_code, candidate)
            raise FetchError(
                f"HTTP {response.status_code} {response.reason_phrase} for {path}"
            )

        html = response.text
        new_etag = response.headers.get("ETag")

        if validate and not looks_like_docs_page(html):
            log.warning("suspicious content for %s (len=%d)", candidate, len(html))
            raise SuspiciousContentError(
                f"response for {path} did not look like an Adobe docs page"
            )

        log.debug("fetched %s (%d bytes, etag=%s)", candidate, len(html), new_etag)
        return html, new_etag

    assert last_err is not None
    raise last_err
