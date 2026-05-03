"""
Pre-built index of structured data extracted from every VIPMP docs page.

Lets `list_vipmp_endpoints`, `list_vipmp_error_codes`, `get_vipmp_schema`,
and `get_vipmp_releases` answer in milliseconds instead of re-extracting
from HTML on every call.

Resolution chain for the active index:
    1. User-local rebuild (~/.cache/.../index.json) — freshest, if present
    2. GitHub-refreshed remote (~/.cache/.../remote-index.json) — pulled
       on demand from `main`, TTL 12h. See remote_index.py.
    3. Package-shipped baseline (src/vipmp_docs_mcp/data/index.json) —
       refreshed daily by GitHub Actions and published with releases.
    4. None — tools fall back to on-the-fly extraction.
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
    ValidationRule,
    extract_endpoints,
    extract_error_codes,
    extract_schemas,
    extract_validations,
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

INDEX_SCHEMA_VERSION = 4  # v4 added `validations` (Adobe-published regex rules per field).

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
    validations: list[ValidationRule] = field(default_factory=list)

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
            "validations": [v.to_dict() for v in self.validations],
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
            validations=[ValidationRule(**v) for v in data.get("validations", [])],
        )

    @property
    def age_seconds(self) -> float:
        return time.time() - self.built_at


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def build_index() -> IndexSnapshot:
    """
    Walk the active sitemap, fetch every page in parallel, and extract
    endpoints, error codes, schemas, and validation regexes into one
    snapshot. Parse errors are captured (not raised) so a single broken
    page doesn't abort the whole build.

    Takes ~10s with a warm cache and parallel fetcher (was ~30s serial),
    ~20s cold (was ~60s serial).

    Callable from both synchronous contexts (CI scripts, REPL) and from
    inside a running event loop (MCP tool handlers); the parallel fetch
    is dispatched via `fetcher.run_async`, which handles either shape.
    """
    from .autositemap import build_sitemap, save_sitemap
    from .fetcher import async_fetch_many, run_async

    # Refresh the sitemap from Adobe before doing anything else. The
    # hand-curated fallback in sitemap.py still uses underscore-separated
    # paths that Adobe has migrated off (see GitHub issue #4) — rebuilding
    # against it produces mostly-404 fetches and a near-empty index, which
    # is exactly how CI-built indexes have been regressing for users on
    # the github-remote tier. If Adobe's sitemap.xml is unreachable the
    # refresh is skipped and we fall back to whatever `get_active_sitemap`
    # finds (persisted JSON first, hand-curated last resort).
    try:
        log.info("build_index: refreshing sitemap from Adobe before build")
        entries = build_sitemap()
        save_sitemap(entries)
    except Exception as exc:
        log.warning(
            "build_index: sitemap refresh failed (%s); "
            "proceeding with currently-active sitemap",
            exc,
        )

    sitemap = get_active_sitemap()
    snap = IndexSnapshot(source_sitemap_size=len(sitemap))
    paths = [entry["path"] for entry in sitemap]
    title_for = {entry["path"]: entry["title"] for entry in sitemap}

    log.info("build_index: fetching %d pages in parallel", len(paths))
    fetch_results = run_async(lambda: async_fetch_many(paths, concurrency=5))

    for path in paths:
        result = fetch_results.get(path)
        if isinstance(result, FetchError) or result is None:
            err_msg = str(result) if result else "missing from fetch results"
            log.warning("fetch failed %s: %s", path, err_msg)
            snap.parse_errors.append((path, err_msg))
            continue

        html = result
        title = title_for[path]
        try:
            snap.endpoints.extend(extract_endpoints(html, path, title))
            snap.error_codes.extend(extract_error_codes(html, docs_path=path))
            snap.schemas.extend(extract_schemas(html, docs_path=path))
            # Validations live exclusively on the references/validations page,
            # but extracting unconditionally is cheap (no-op if not the right
            # page) and future-proofs against Adobe moving them.
            snap.validations.extend(extract_validations(html, docs_path=path))
            snap.pages_parsed += 1
        except Exception as exc:
            log.exception("parse failed %s", path)
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


@dataclass
class ActiveIndex:
    """The loaded index plus metadata about which tier it came from."""

    snapshot: IndexSnapshot
    source: str  # "user-local" | "github-remote" | "package-baseline"
    path: Path


def resolve_active_index() -> ActiveIndex | None:
    """
    Walk the tier chain and return the first usable index along with its
    source label. See the module docstring for the tier order.

    The github-remote tier may trigger a network fetch (conditional GET,
    subject to a 12h TTL). It degrades silently on any failure — the
    caller always ends up with the package baseline if no fresher source
    works.
    """
    user = load_index(USER_INDEX_PATH)
    if user is not None:
        log.debug("using user-local index (age=%.0fs)", user.age_seconds)
        return ActiveIndex(user, "user-local", USER_INDEX_PATH)

    # Local import to avoid a circular dependency at module load time —
    # remote_index doesn't import index, but this keeps the coupling
    # one-way at runtime as well.
    from .remote_index import ensure_fresh

    remote_path = ensure_fresh()
    if remote_path is not None:
        remote = load_index(remote_path)
        if remote is not None:
            log.debug("using github-remote index (age=%.0fs)", remote.age_seconds)
            return ActiveIndex(remote, "github-remote", remote_path)

    pkg = load_index(PACKAGE_INDEX_PATH)
    if pkg is not None:
        log.debug("using package-shipped index (age=%.0fs)", pkg.age_seconds)
        return ActiveIndex(pkg, "package-baseline", PACKAGE_INDEX_PATH)

    log.debug("no index available; callers will fall back to live extraction")
    return None


def get_active_index() -> IndexSnapshot | None:
    """
    Return the freshest index snapshot available, or None if no tier
    yielded a usable index. Thin wrapper over ``resolve_active_index``
    kept for backwards compatibility with callers that don't need the
    source label.
    """
    active = resolve_active_index()
    return active.snapshot if active is not None else None
