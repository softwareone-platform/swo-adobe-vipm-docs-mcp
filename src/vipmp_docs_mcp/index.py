"""
Pre-built index of structured data extracted from every VIPMP docs page.

Lets `list_vipmp_endpoints`, `list_vipmp_error_codes`, `get_vipmp_schema`,
and `get_vipmp_releases` answer in milliseconds instead of re-extracting
from HTML on every call.

Three-tier resolution for the active index:
    1. User-local rebuild (~/.cache/.../index.json) — freshest, if present
    2. Package-shipped baseline (src/vipmp_docs_mcp/data/index.json) —
       refreshed weekly by GitHub Actions and published with releases
    3. None — tools fall back to on-the-fly extraction
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from .autositemap import get_active_sitemap
from .extractors import (
    Endpoint,
    ErrorCode,
    SchemaResource,
    extract_endpoints,
    extract_error_codes,
    extract_schemas,
)
from .fetcher import FetchError, fetch_page_html
from .logging_config import CACHE_DIR, get_logger
from .releases import (
    RELEASE_NOTES_PATH,
    UPCOMING_RELEASES_PATH,
    ReleaseEntry,
    parse_recent_releases,
    parse_upcoming_releases,
)

log = get_logger("index")

INDEX_SCHEMA_VERSION = 2  # Bumped when `releases` was added to the snapshot.

# Per-user refresh: written by rebuild_vipmp_index tool / GHA artifact drop.
USER_INDEX_PATH = CACHE_DIR / "index.json"

# Baseline shipped with the package. Lives in src/vipmp_docs_mcp/data/
# so it's included in the wheel via pyproject.toml's package-data entry.
PACKAGE_INDEX_PATH = Path(__file__).parent / "data" / "index.json"


@dataclass
class IndexSnapshot:
    """A point-in-time snapshot of structured data extracted from the docs."""

    schema_version: int = INDEX_SCHEMA_VERSION
    built_at: float = field(default_factory=time.time)
    source_sitemap_size: int = 0
    pages_parsed: int = 0
    parse_errors: list[tuple[str, str]] = field(default_factory=list)
    endpoints: list[Endpoint] = field(default_factory=list)
    error_codes: list[ErrorCode] = field(default_factory=list)
    schemas: list[SchemaResource] = field(default_factory=list)
    releases: list[ReleaseEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "built_at": self.built_at,
            "source_sitemap_size": self.source_sitemap_size,
            "pages_parsed": self.pages_parsed,
            "parse_errors": [
                {"path": p, "error": e} for p, e in self.parse_errors
            ],
            "endpoints": [e.to_dict() for e in self.endpoints],
            "error_codes": [e.to_dict() for e in self.error_codes],
            "schemas": [s.to_dict() for s in self.schemas],
            "releases": [r.to_dict() for r in self.releases],
        }

    @classmethod
    def from_dict(cls, data: dict) -> IndexSnapshot:
        return cls(
            schema_version=data.get("schema_version", 0),
            built_at=float(data.get("built_at", 0.0)),
            source_sitemap_size=int(data.get("source_sitemap_size", 0)),
            pages_parsed=int(data.get("pages_parsed", 0)),
            parse_errors=[
                (e["path"], e["error"]) for e in data.get("parse_errors", [])
            ],
            endpoints=[Endpoint(**e) for e in data.get("endpoints", [])],
            error_codes=[ErrorCode(**e) for e in data.get("error_codes", [])],
            schemas=[
                SchemaResource(
                    name=s["name"],
                    level=s["level"],
                    docs_path=s.get("docs_path"),
                    fields=[
                        __import__("vipmp_docs_mcp.extractors", fromlist=["SchemaField"]).SchemaField(**f)
                        for f in s.get("fields", [])
                    ],
                )
                for s in data.get("schemas", [])
            ],
            releases=[ReleaseEntry.from_dict(r) for r in data.get("releases", [])],
        )

    @property
    def age_seconds(self) -> float:
        return time.time() - self.built_at


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_index() -> IndexSnapshot:
    """
    Walk the active sitemap, fetch every page, and extract endpoints,
    error codes, and schemas into one snapshot. Parse errors are captured
    (not raised) so a single broken page doesn't abort the whole build.

    Takes ~30s end-to-end against a warm cache, ~60s cold.
    """
    sitemap = get_active_sitemap()
    snap = IndexSnapshot(source_sitemap_size=len(sitemap))

    for i, entry in enumerate(sitemap, 1):
        path = entry["path"]
        title = entry["title"]
        try:
            html = fetch_page_html(path)
        except FetchError as exc:
            log.warning("(%d/%d) fetch failed %s: %s", i, len(sitemap), path, exc)
            snap.parse_errors.append((path, str(exc)))
            continue

        try:
            snap.endpoints.extend(extract_endpoints(html, path, title))
            snap.error_codes.extend(extract_error_codes(html, docs_path=path))
            snap.schemas.extend(extract_schemas(html, docs_path=path))
            snap.pages_parsed += 1
        except Exception as exc:
            log.exception("(%d/%d) parse failed %s", i, len(sitemap), path)
            snap.parse_errors.append((path, f"parse error: {exc}"))

    # Release notes — parsed from two dedicated pages (structure is different
    # from the rest of the docs, so we use dedicated parsers).
    for label, path, parser in (
        ("recent", RELEASE_NOTES_PATH, parse_recent_releases),
        ("upcoming", UPCOMING_RELEASES_PATH, parse_upcoming_releases),
    ):
        try:
            html = fetch_page_html(path)
            entries = parser(html, docs_path=path)
            snap.releases.extend(entries)
            log.info("parsed %d %s release entries from %s", len(entries), label, path)
        except FetchError as exc:
            log.warning("failed to fetch %s release notes: %s", label, exc)
            snap.parse_errors.append((path, str(exc)))

    log.info(
        "built index: %d pages parsed, %d errors, %d endpoints, %d error codes, %d schemas, %d releases",
        snap.pages_parsed,
        len(snap.parse_errors),
        len(snap.endpoints),
        len(snap.error_codes),
        len(snap.schemas),
        len(snap.releases),
    )
    return snap


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def save_index(snapshot: IndexSnapshot, path: Path = USER_INDEX_PATH) -> None:
    """Atomic write the snapshot to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshot.to_dict(), f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    log.info("saved index to %s", path)


def load_index(path: Path) -> IndexSnapshot | None:
    """Load an index from disk, or None if missing/invalid."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("index file unreadable (%s); ignoring: %s", path, exc)
        return None
    if data.get("schema_version") != INDEX_SCHEMA_VERSION:
        log.warning("index schema mismatch at %s; ignoring", path)
        return None
    return IndexSnapshot.from_dict(data)


def get_active_index() -> IndexSnapshot | None:
    """
    Return the freshest index available: user-local rebuild first, then
    the package-shipped baseline, then None.
    """
    user = load_index(USER_INDEX_PATH)
    if user is not None:
        log.debug("using user-local index (age=%.0fs)", user.age_seconds)
        return user
    pkg = load_index(PACKAGE_INDEX_PATH)
    if pkg is not None:
        log.debug("using package-shipped index (age=%.0fs)", pkg.age_seconds)
        return pkg
    log.debug("no index available; callers will fall back to live extraction")
    return None
