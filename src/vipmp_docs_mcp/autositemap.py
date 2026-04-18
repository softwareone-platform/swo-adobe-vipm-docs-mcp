"""
Auto-refresh the docs sitemap from Adobe's published sitemap.xml.

Adobe publishes `/sitemap.xml` listing every URL under developer.adobe.com.
We filter for `/vipmp/docs/` paths, fetch each page for its title, and build
a fresh `SitemapEntry` list. Tags are derived from path segments + the
hand-curated tag dictionary in `sitemap_tags.py`.

The auto-generated sitemap is persisted to `sitemap.json` in the cache dir
so subsequent server startups don't need to refetch.
"""

from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

from .fetcher import BASE_URL, FetchError, fetch_page_html
from .logging_config import CACHE_DIR, get_logger
from .sitemap import SITEMAP as HAND_CURATED_SITEMAP
from .sitemap import SitemapEntry, normalize_path

log = get_logger("autositemap")

SITEMAP_XML_PATH = "/sitemap.xml"
SITEMAP_JSON_PATH = CACHE_DIR / "sitemap.json"

# Schema version — bump on breaking changes to the persisted JSON shape.
SITEMAP_SCHEMA_VERSION = 1


def _fetch_sitemap_paths() -> list[str]:
    """Fetch Adobe's sitemap.xml and return normalized vipmp doc paths."""
    xml = fetch_page_html(SITEMAP_XML_PATH, validate=False)
    root = ET.fromstring(xml)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [u.find("sm:loc", ns).text or "" for u in root.findall("sm:url", ns)]
    vipmp = [u.replace(BASE_URL, "") for u in urls if "/vipmp/docs/" in u]
    paths = sorted({normalize_path(p) for p in vipmp})
    log.info("fetched %d vipmp paths from %s", len(paths), SITEMAP_XML_PATH)
    return paths


def _extract_title(html: str, fallback: str) -> str:
    """Pull the page's <h1> (or <title>) as the entry title."""
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    title = soup.find("title")
    if title and title.get_text(strip=True):
        # Adobe titles are often "Page Name | Adobe Developer" — strip suffix.
        text = title.get_text(strip=True)
        return re.sub(r"\s*[|—]\s*Adobe.*$", "", text).strip()
    return fallback


def _derive_tags(path: str, title: str) -> list[str]:
    """
    Build search tags from the path segments plus title words. Light-touch:
    the goal is recall, not precision. Richer hand-curated tags (from the
    legacy SITEMAP) are merged on top by `merge_curated_tags` below.
    """
    tags: set[str] = set()

    # Path segments (minus leading/trailing slashes, minus the generic "vipmp"/"docs").
    segments = [s for s in path.strip("/").split("/") if s]
    for seg in segments:
        if seg in {"vipmp", "docs"}:
            continue
        # Split on hyphens/underscores to surface individual concept words.
        for word in re.split(r"[-_]", seg):
            if len(word) >= 3:
                tags.add(word.lower())
            tags.add(seg.replace("-", " ").replace("_", " ").lower())

    # Title words, lowercased (dropping short/stop words).
    stopwords = {"the", "a", "an", "and", "or", "of", "to", "for", "in", "on", "with", "by"}
    for word in re.findall(r"\w+", title.lower()):
        if len(word) >= 3 and word not in stopwords:
            tags.add(word)

    return sorted(tags)


def _build_curated_tag_index() -> dict[str, list[str]]:
    """
    Build a lookup from base path-suffix → curated tags, using the legacy
    hand-curated SITEMAP. This lets us reuse the richer tags (like "3YC",
    "HGO", "x-correlation-id") even though Adobe's URLs have changed.

    Key is the last non-empty path segment lowercased with hyphens → e.g.
    "/vipmp/docs/customer_account/three_year_commit/" keys as "three-year-commit".
    """
    index: dict[str, list[str]] = {}
    for entry in HAND_CURATED_SITEMAP:
        # Normalize the legacy path segment to hyphen convention.
        segments = [s for s in entry["path"].strip("/").split("/") if s]
        if not segments:
            continue
        last = segments[-1].replace("_", "-").lower()
        index[last] = list(entry["tags"])
    return index


def merge_curated_tags(entries: list[SitemapEntry]) -> list[SitemapEntry]:
    """Merge hand-curated tags onto auto-generated entries where paths line up."""
    curated = _build_curated_tag_index()
    merged = 0
    for entry in entries:
        segments = [s for s in entry["path"].strip("/").split("/") if s]
        if not segments:
            continue
        last = segments[-1].lower()
        if last in curated:
            existing = set(entry["tags"])
            for tag in curated[last]:
                existing.add(tag)
            entry["tags"] = sorted(existing)
            merged += 1
    log.info("merged curated tags onto %d/%d entries", merged, len(entries))
    return entries


def build_sitemap(throttle: float = 0.0) -> list[SitemapEntry]:
    """
    Build a fresh sitemap by fetching Adobe's sitemap.xml, then each page
    for its title. Returns entries sorted by path.

    Args:
        throttle: Seconds to sleep between page fetches. Default 0 (the
            retry/backoff in the fetcher already handles 429s). Set >0 if
            you want to be extra polite.
    """
    paths = _fetch_sitemap_paths()
    entries: list[SitemapEntry] = []
    errors: list[tuple[str, str]] = []

    for i, path in enumerate(paths, 1):
        try:
            html = fetch_page_html(path)
            title = _extract_title(html, fallback=path)
            tags = _derive_tags(path, title)
            entries.append({"path": path, "title": title, "tags": tags})
            log.debug("(%d/%d) %s → %s", i, len(paths), path, title)
        except FetchError as exc:
            errors.append((path, str(exc)))
            log.warning("(%d/%d) failed %s: %s", i, len(paths), path, exc)
        if throttle:
            time.sleep(throttle)

    entries = merge_curated_tags(entries)
    log.info(
        "built sitemap: %d entries (%d errors) from %d candidate paths",
        len(entries),
        len(errors),
        len(paths),
    )
    return entries


def save_sitemap(entries: list[SitemapEntry], path: Path = SITEMAP_JSON_PATH) -> None:
    """Persist the sitemap to JSON (atomic write)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SITEMAP_SCHEMA_VERSION,
        "generated_at": time.time(),
        "entries": entries,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    log.info("saved sitemap: %d entries to %s", len(entries), path)


def load_sitemap(path: Path = SITEMAP_JSON_PATH) -> list[SitemapEntry] | None:
    """Load the persisted sitemap, or None if missing/invalid."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("sitemap.json unreadable (%s); ignoring", exc)
        return None
    if data.get("schema_version") != SITEMAP_SCHEMA_VERSION:
        log.warning("sitemap.json schema mismatch; ignoring")
        return None
    entries = data.get("entries", [])
    log.info("loaded %d entries from %s", len(entries), path)
    return entries


def get_active_sitemap() -> list[SitemapEntry]:
    """
    Return the sitemap the server should use — persisted auto-generated one
    if available, hand-curated fallback otherwise.
    """
    auto = load_sitemap()
    if auto:
        return auto
    log.info("no persisted sitemap; falling back to hand-curated")
    return HAND_CURATED_SITEMAP
