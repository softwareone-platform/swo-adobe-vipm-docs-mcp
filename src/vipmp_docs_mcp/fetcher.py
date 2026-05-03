"""
HTTP client with retries, backoff, and content sanity checks.

Wraps httpx with tenacity for resilience. Everything that fetches a page
from developer.adobe.com goes through this module.

The synchronous API (fetch_page_html, fetch_page_with_etag) is the main
interface used by tools and cache code. async_fetch_many is a parallel
fetch helper used by warm_vipmp_cache and build_index for situations
where serial fetching would be unacceptably slow.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

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


# ---------------------------------------------------------------------------
# Parallel async fetcher (used by warm_vipmp_cache and build_index for
# situations where serial fetching would be unacceptably slow).
# ---------------------------------------------------------------------------


DEFAULT_CONCURRENCY = 5
"""Be polite to Adobe's CDN — 5 concurrent requests is plenty for our use case."""


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=4.0),
    retry=retry_if_exception(_is_retryable),
    reraise=True,
)
async def _async_fetch_with_retries(
    client: httpx.AsyncClient, url: str, headers: dict[str, str]
) -> httpx.Response:
    """Async retry-wrapped fetch. Mirrors `_fetch_with_retries` policy."""
    log.debug("async-fetching %s", url)
    response = await client.get(url, headers=headers)
    if response.status_code in _RETRYABLE_STATUS:
        # Trigger tenacity retry. raise_for_status raises HTTPStatusError,
        # which `_is_retryable` catches for the retryable status set.
        response.raise_for_status()
    return response


async def _async_fetch_one(
    client: httpx.AsyncClient,
    path: str,
    *,
    validate: bool = True,
) -> str:
    """
    Async equivalent of fetch_page_html for one path. Includes the same
    trailing-slash fallback semantics and the same retry/backoff policy
    as the sync fetcher. Raises FetchError on failure.
    """
    last_err: Exception | None = None
    for candidate in _trailing_slash_variants(path):
        url = BASE_URL + candidate
        try:
            response = await _async_fetch_with_retries(
                client, url, _default_headers()
            )
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
                f"response for {path} did not look like an Adobe docs page"
            )

        log.debug("async-fetched %s (%d bytes)", candidate, len(html))
        return html

    assert last_err is not None
    raise last_err


async def async_fetch_many(
    paths: list[str],
    *,
    concurrency: int = DEFAULT_CONCURRENCY,
    validate: bool = True,
    on_progress: Callable[[int, int, str, FetchError | None], Awaitable[None] | None] | None = None,
) -> dict[str, str | FetchError]:
    """
    Fetch many paths in parallel, returning a dict of {path: html | FetchError}.

    Failures are captured per-path rather than aborting the batch — callers
    decide what to do with partial successes (warm_cache logs and skips,
    build_index appends to parse_errors).

    Args:
        paths: Doc paths to fetch.
        concurrency: Maximum concurrent requests. Default 5 — we're polite.
        validate: Same as fetch_page_html.
        on_progress: Optional callback(done, total, path, error_or_none).
            Useful for emitting progress to logs while a long fetch runs.

    Returns:
        {path: html_string} for successes, {path: FetchError} for failures.
    """
    semaphore = asyncio.Semaphore(concurrency)
    results: dict[str, str | FetchError] = {}
    done = 0
    total = len(paths)

    timeout = httpx.Timeout(15.0, connect=10.0)
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)

    async with httpx.AsyncClient(
        timeout=timeout, limits=limits, follow_redirects=True
    ) as client:

        async def fetch_one(path: str) -> None:
            nonlocal done
            async with semaphore:
                err: FetchError | None = None
                try:
                    html = await _async_fetch_one(client, path, validate=validate)
                    results[path] = html
                except FetchError as exc:
                    results[path] = exc
                    err = exc
                done += 1
                if on_progress is not None:
                    maybe_aw = on_progress(done, total, path, err)
                    if asyncio.iscoroutine(maybe_aw):
                        await maybe_aw

        await asyncio.gather(*(fetch_one(p) for p in paths))

    succeeded = sum(1 for v in results.values() if isinstance(v, str))
    log.info("async_fetch_many: %d/%d succeeded", succeeded, total)
    return results


def run_async(coro_factory):
    """
    Run an async coroutine from a sync context, even if a loop is active.

    `asyncio.run()` raises "cannot be called from a running event loop"
    when invoked under one — which can happen if a future MCP runtime
    drives sync tool bodies inside the loop thread. To stay safe in
    both shapes:

      - if no loop is running, dispatch directly via `asyncio.run`;
      - if a loop is running, isolate the work in a short-lived worker
        thread with its own fresh loop.

    `coro_factory` is a zero-arg callable that returns the coroutine.
    The deferred construction matters: building the coroutine under one
    loop and awaiting it under another raises "attached to a different
    loop". The factory pattern defers construction to the worker.
    """
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro_factory())).result()
