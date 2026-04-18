"""
FastMCP server — registers tools and runs the MCP transport.

Tool implementations live here but delegate real work to the supporting
modules (fetcher, sitemap, html_cleaner). Disk cache, content search,
structured extractors, and MCP prompts land in later phases.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .autositemap import build_sitemap, get_active_sitemap, save_sitemap
from .cache import get_cache
from .extractors import (
    extract_code_examples,
    extract_endpoints,
    extract_error_codes,
    extract_schemas,
)
from .fetcher import FetchError
from .index import (
    USER_INDEX_PATH,
    build_index,
    get_active_index,
    save_index,
)
from .logging_config import configure_logging, get_logger
from .prompts import register_prompts
from .search import relevant_sections, search
from .sitemap import find_by_path as _find_in_hand_curated
from .sitemap import normalize_path

log = get_logger("server")


# Active sitemap: auto-generated (from Adobe's sitemap.xml, persisted to
# ~/.cache/.../sitemap.json) if available, else hand-curated fallback.
# Mutable so `refresh_vipmp_sitemap` can swap in a fresh copy at runtime
# without a server restart.
_active_sitemap = get_active_sitemap()


def _get_sitemap():
    """Indirection so tools always read the current sitemap, not a snapshot."""
    return _active_sitemap


def _find_by_path(path: str):
    """Find an entry in the active sitemap (may be auto or hand-curated)."""
    normalized = normalize_path(path)
    for entry in _active_sitemap:
        if normalize_path(entry["path"]) == normalized:
            return entry
    # Fallback: legacy hand-curated list in case the active one is empty.
    return _find_in_hand_curated(path)


def _known_paths() -> set[str]:
    return {normalize_path(e["path"]) for e in _active_sitemap}


mcp = FastMCP(
    "vipmp-docs",
    instructions=(
        "Use this server to look up Adobe VIP Marketplace Partner API documentation. "
        "Call search_vipmp_docs first to find relevant pages, then get_vipmp_page to read full content. "
        "Structured tools: list_vipmp_endpoints, list_vipmp_error_codes, get_vipmp_schema, "
        "get_vipmp_code_examples. Prompts: review_request_body, debug_error_code, draft_order, "
        "check_3yc_eligibility."
    ),
)

# Register the MCP Prompts (imported from prompts.py).
register_prompts(mcp)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_cleaned_content(path: str) -> str:
    """
    Return cleaned Markdown-ish text for a docs page. Uses the disk-backed
    cache with 24h TTL + ETag revalidation; falls back to stale cache on
    transient network failures.
    """
    return get_cache().get_or_fetch(path)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def list_vipmp_docs() -> str:
    """
    Return the full sitemap of Adobe VIP Marketplace API documentation.
    Use this to browse all available topics or to find exact page paths.
    """
    sitemap = _get_sitemap()
    lines = [f"# Adobe VIP Marketplace Docs — Sitemap ({len(sitemap)} pages)\n"]
    current_section = ""
    for entry in sorted(sitemap, key=lambda e: e["path"]):
        parts = [p for p in entry["path"].strip("/").split("/") if p]
        section = parts[1] if len(parts) > 1 else "root"
        if section != current_section:
            lines.append(f"\n## {section.replace('-', ' ').replace('_', ' ').title()}")
            current_section = section
        lines.append(f"- **{entry['title']}** → `{entry['path']}`")
    return "\n".join(lines)


@mcp.tool()
def search_vipmp_docs(query: str, max_results: int = 5) -> str:
    """
    Search the Adobe VIP Marketplace API documentation by keyword or topic.
    Ranks pages by title/tag matches plus content matches (for any page
    already in the local cache — call warm_vipmp_cache once to pre-fetch
    every page for the strongest results).

    Returns matching page titles, paths, and the most query-relevant
    sections from each page (not a blunt character cutoff).

    Args:
        query: Search terms, e.g. "create order", "oauth token", "3YC eligibility"
        max_results: Maximum number of pages to return (default 5, max 10)
    """
    max_results = min(max_results, 10)
    cache = get_cache()
    top = search(_get_sitemap(), cache, query, max_results=max_results)

    if not top:
        log.info("no matches for query=%r", query)
        return (
            f"No pages matched '{query}'.\n\n"
            "Try:\n"
            "  - `list_vipmp_docs()` to browse all topics\n"
            "  - `warm_vipmp_cache()` to pre-fetch every page, then search again "
            "(enables content-level matching)"
        )

    log.info("search query=%r matched %d entries", query, len(top))
    out = [f"# Search results for: '{query}'\n"]
    for scored in top:
        entry = scored.entry
        out.append(
            f"---\n## {entry['title']}\n"
            f"**Path:** `{entry['path']}` · "
            f"**Score:** {scored.total} "
            f"(title={scored.title_score}, tags={scored.tag_score}, "
            f"content={scored.content_score})\n"
        )
        try:
            content = _get_cleaned_content(entry["path"])
            out.append(relevant_sections(content, query=query))
        except FetchError as exc:
            out.append(f"_(Could not fetch page: {exc})_")

    return "\n\n".join(out)


@mcp.tool()
def get_vipmp_page(path: str) -> str:
    """
    Fetch the full content of a specific Adobe VIP Marketplace documentation page.

    Args:
        path: The doc path, e.g. "/vipmp/docs/order_management/create_order/"
              Use list_vipmp_docs() or search_vipmp_docs() to find valid paths.
    """
    path = normalize_path(path)

    warning = ""
    if path not in _known_paths():
        warning = f"⚠️  '{path}' is not in the known sitemap. Attempting fetch anyway.\n\n"

    try:
        content = _get_cleaned_content(path)
    except FetchError as exc:
        return f"{warning}Error fetching '{path}': {exc}"

    entry = _find_by_path(path)
    title = entry["title"] if entry else path
    from .fetcher import BASE_URL

    return f"{warning}# {title}\n**Source:** {BASE_URL}{path}\n**Path:** `{path}`\n\n{content}"


@mcp.tool()
def warm_vipmp_cache() -> str:
    """
    Pre-fetch every page in the sitemap so subsequent searches can do
    content-level matching (not just title/tag matching).

    First run takes ~30 seconds over ~70 pages. Subsequent runs are
    near-instant because the disk cache + ETag revalidation handle
    unchanged pages with 304 responses.

    Returns a summary of fetches, cache hits, and any errors.
    """
    cache = get_cache()
    fetched = 0
    revalidated = 0
    errors: list[tuple[str, str]] = []

    for entry in _get_sitemap():
        path = entry["path"]
        before = cache.get(path)
        try:
            cache.get_or_fetch(path)
            after = cache.get(path)
            # Heuristic: if fetched_at advanced and content length changed OR no
            # prior entry existed, treat as a fresh fetch; otherwise revalidated.
            if before is None or (after and before.content != after.content):
                fetched += 1
            else:
                revalidated += 1
        except FetchError as exc:
            errors.append((path, str(exc)))
            log.warning("warm_cache failed for %s: %s", path, exc)

    lines = [
        "# Cache warmup complete",
        "",
        f"- **Fetched (new or changed):** {fetched}",
        f"- **Revalidated (unchanged):** {revalidated}",
        f"- **Errors:** {len(errors)}",
    ]
    if errors:
        lines.append("\n## Errors")
        for path, msg in errors:
            lines.append(f"- `{path}` — {msg}")
    return "\n".join(lines)


@mcp.tool()
def refresh_vipmp_sitemap() -> str:
    """
    Rebuild the sitemap from Adobe's published /sitemap.xml. Fetches every
    current /vipmp/docs/ page for its title, merges hand-curated search tags
    where paths still line up, and persists the result to sitemap.json so
    future server startups use the refreshed list.

    Run this if:
      - You're seeing 404s on known pages (Adobe renamed or removed them)
      - You want to pick up newly-added pages Adobe's published since install
      - The default hand-curated sitemap looks stale

    Takes about 30 seconds over ~80 pages. Safe to run repeatedly.
    """
    global _active_sitemap
    try:
        entries = build_sitemap()
    except FetchError as exc:
        return f"Refresh failed: {exc}"

    save_sitemap(entries)
    _active_sitemap = entries

    # Also invalidate the content cache — old cached entries may correspond
    # to paths that no longer exist in the new sitemap.
    get_cache().invalidate()

    return (
        f"# Sitemap refreshed\n\n"
        f"- **Total pages:** {len(entries)}\n"
        f"- **Saved to:** `~/.cache/swo-adobe-vipm-docs-mcp/sitemap.json`\n"
        f"- **Content cache cleared** — first search will refetch pages as needed "
        f"(or call `warm_vipmp_cache` to pre-fetch all).\n"
    )


@mcp.tool()
def vipmp_cache_stats() -> str:
    """
    Return statistics about the on-disk docs cache — total entries,
    fresh/stale split, TTL, and the cache file path. Useful when debugging
    "why did it return stale content" or "is the cache being used at all".
    """
    stats = get_cache().stats()
    return (
        f"# VIPMP docs cache\n\n"
        f"- **Total entries:** {stats['total']}\n"
        f"- **Fresh:** {stats['fresh']}\n"
        f"- **Stale (will revalidate on next fetch):** {stats['stale']}\n"
        f"- **TTL:** {stats['ttl_seconds']} seconds "
        f"({stats['ttl_seconds'] // 3600} hours)\n"
        f"- **Oldest entry age:** {stats['oldest_age_seconds']:.0f} seconds\n"
        f"- **Cache file:** `{stats['cache_file']}`"
    )


@mcp.tool()
def vipmp_cache_clear(path: str | None = None) -> str:
    """
    Clear the docs cache. Pass a specific doc path to invalidate one entry,
    or omit to wipe the entire cache.

    Args:
        path: Optional docs path to invalidate (e.g. "/vipmp/docs/lga/create/").
              If None, clears everything.
    """
    get_cache().invalidate(path)
    return f"Cleared cache entry for {path}" if path else "Cleared entire docs cache"


# ---------------------------------------------------------------------------
# Structured extractors
# ---------------------------------------------------------------------------


def _iter_pages():
    """
    Yield (docs_path, title, html) for every page in the sitemap.

    Extractors need raw HTML (not cleaned text), so this bypasses the
    cleaned-text cache and fetches HTML directly. The fetcher's own retry
    + trailing-slash fallback handles transient issues.
    """
    from .fetcher import fetch_page_html

    for entry in _get_sitemap():
        try:
            html = fetch_page_html(entry["path"])
        except FetchError as exc:
            log.warning("iter_pages: skipping %s: %s", entry["path"], exc)
            continue
        yield entry["path"], entry["title"], html


def _index_source_note() -> str:
    """Human-readable source annotation for index-backed tool output."""
    idx = get_active_index()
    if idx is None:
        return "_(Extracted live — consider calling `rebuild_vipmp_index` for faster future calls.)_"
    age_h = idx.age_seconds / 3600
    freshness = f"{age_h:.0f}h old" if age_h < 48 else f"{age_h / 24:.0f}d old"
    return f"_Served from pre-built index ({freshness}, {idx.pages_parsed} pages parsed)._"


@mcp.tool()
def list_vipmp_endpoints() -> str:
    """
    Extract every HTTP endpoint (method + path) documented across the whole
    VIPMP docs. Returns a Markdown table grouped by resource area.

    Served from the pre-built index (milliseconds) when available. Falls
    back to live extraction across the sitemap (~30s cold, ~5s warm) if
    no index is present. Call `rebuild_vipmp_index` to refresh locally.
    """
    idx = get_active_index()
    if idx is not None:
        endpoints = list(idx.endpoints)
    else:
        endpoints = []
        for docs_path, title, html in _iter_pages():
            endpoints.extend(extract_endpoints(html, docs_path, title))

    if not endpoints:
        return "_(No endpoints found in the current sitemap.)_"

    # Group by first path segment after /v3/ for readability.
    def group_key(ep) -> str:
        parts = [p for p in ep.path.strip("/").split("/") if p]
        return parts[1] if len(parts) > 1 else (parts[0] if parts else "misc")

    endpoints.sort(key=lambda e: (group_key(e), e.path, e.method))
    current_group = ""
    out = [
        f"# VIPMP Endpoints ({len(endpoints)} documented)\n",
        _index_source_note(),
        "",
    ]
    for ep in endpoints:
        group = group_key(ep)
        if group != current_group:
            out.append(f"\n## {group.replace('_', ' ').title()}\n")
            current_group = group
        out.append(
            f"- `{ep.method:6s}` `{ep.path}` — [{ep.title}](`{ep.docs_path}`)"
        )
    return "\n".join(out)


@mcp.tool()
def list_vipmp_error_codes(query: str | None = None) -> str:
    """
    Extract every error code documented across VIPMP docs — both numeric
    codes (e.g. 1117, 5117) and symbolic reason codes (e.g.
    INVALID_LM_MIGRATION_LEVEL).

    Args:
        query: Optional substring filter. Matches against code, reason, or
            endpoint. Case-insensitive.

    Served from the pre-built index when available, falling back to live
    extraction if not. Call `rebuild_vipmp_index` to refresh locally.
    """
    idx = get_active_index()
    if idx is not None:
        codes = list(idx.error_codes)
    else:
        codes = []
        for docs_path, _title, html in _iter_pages():
            codes.extend(extract_error_codes(html, docs_path=docs_path))

    if query:
        needle = query.lower()
        codes = [
            c
            for c in codes
            if needle in c.code.lower()
            or needle in c.reason.lower()
            or (c.endpoint and needle in c.endpoint.lower())
        ]

    if not codes:
        return f"_(No error codes matched{' query=' + repr(query) if query else ''}.)_"

    codes.sort(key=lambda c: (c.code, c.endpoint or "", c.docs_path or ""))
    out = [
        f"# VIPMP Error Codes ({len(codes)} shown"
        + (f", query={query!r}" if query else "")
        + ")\n",
        _index_source_note(),
        "",
    ]
    for c in codes:
        ep = f" — `{c.endpoint}`" if c.endpoint else ""
        out.append(f"- **{c.code}**{ep}\n  {c.reason}\n  _source:_ `{c.docs_path}`")
    return "\n".join(out)


@mcp.tool()
def get_vipmp_schema(resource_name: str | None = None) -> str:
    """
    Return structured field schemas (name, type, required, description)
    for VIPMP resources. Source: the Resources & Fields reference page.

    Args:
        resource_name: Optional case-insensitive substring to filter by
            resource name (e.g. "customer", "linkedMembership"). Omit to
            get every documented resource.
    """
    idx = get_active_index()
    if idx is not None:
        schemas = list(idx.schemas)
    else:
        try:
            from .fetcher import fetch_page_html

            html = fetch_page_html("/vipmp/docs/references/resources")
        except FetchError as exc:
            return f"Error fetching Resources page: {exc}"
        schemas = extract_schemas(html, docs_path="/vipmp/docs/references/resources")

    if resource_name:
        needle = resource_name.lower()
        schemas = [s for s in schemas if needle in s.name.lower()]

    if not schemas:
        return f"_(No schemas matched resource_name={resource_name!r}.)_"

    out = [
        f"# VIPMP Resource Schemas ({len(schemas)} resource(s))\n",
        _index_source_note(),
        "",
    ]
    for s in schemas:
        out.append(f"\n## {s.name}\n")
        out.append("| Field | Type | Required | Description | Constraints |")
        out.append("|---|---|---|---|---|")
        for f in s.fields:
            req = (
                "✅"
                if f.required is True
                else "optional"
                if f.required is False
                else "—"
            )
            desc = f.description.replace("\n", " ").replace("|", "\\|")
            cons = (f.constraints or "").replace("\n", " ").replace("|", "\\|")
            out.append(f"| `{f.name}` | {f.type} | {req} | {desc} | {cons} |")
    return "\n".join(out)


@mcp.tool()
def get_vipmp_code_examples(docs_path: str, language: str | None = None) -> str:
    """
    Extract code examples (JSON / curl / bash / python / etc.) from a
    specific docs page. Optionally filter by language.

    Args:
        docs_path: Docs path (e.g. "/vipmp/docs/customer-account/create-customer-account").
        language: Optional filter — "json", "python", "bash", etc. Matches
            the `language-<x>` class on `<code>` elements.
    """
    path = normalize_path(docs_path)
    try:
        from .fetcher import fetch_page_html

        html = fetch_page_html(path)
    except FetchError as exc:
        return f"Error fetching `{path}`: {exc}"

    examples = extract_code_examples(html, language=language)
    if not examples:
        filter_note = f" (language={language!r})" if language else ""
        return f"_(No code examples found on `{path}`{filter_note}.)_"

    out = [f"# Code examples from `{path}`\n"]
    if language:
        out.append(f"_Filtered to language: {language}_\n")
    for i, ex in enumerate(examples, 1):
        heading = ex.nearby_heading or "(no nearby heading)"
        lang_tag = ex.language or ""
        out.append(f"\n## Example {i} — {heading}\n")
        out.append(f"```{lang_tag}\n{ex.code.rstrip()}\n```")
    return "\n".join(out)


@mcp.tool()
def rebuild_vipmp_index() -> str:
    """
    Rebuild the pre-extracted index of endpoints, error codes, and schemas
    by walking every page in the current sitemap. Saves to
    `~/.cache/swo-adobe-vipm-docs-mcp/index.json`.

    Run this if:
      - The structured tools (`list_vipmp_endpoints`, `list_vipmp_error_codes`,
        `get_vipmp_schema`) are returning stale data
      - You just ran `refresh_vipmp_sitemap` and want the structured
        tools to pick up new pages
      - The package-shipped baseline index is older than you'd like

    Takes ~60 seconds from cold cache, ~15-20 seconds from warm cache.
    """
    snap = build_index()
    save_index(snap, USER_INDEX_PATH)

    parts = [
        "# Index rebuilt\n",
        f"- **Pages parsed:** {snap.pages_parsed} / {snap.source_sitemap_size}",
        f"- **Endpoints extracted:** {len(snap.endpoints)}",
        f"- **Error codes extracted:** {len(snap.error_codes)}",
        f"- **Schemas extracted:** {len(snap.schemas)}",
        f"- **Parse errors:** {len(snap.parse_errors)}",
        f"- **Saved to:** `{USER_INDEX_PATH}`",
    ]
    if snap.parse_errors:
        parts.append("\n## Errors")
        for path, msg in snap.parse_errors[:20]:
            parts.append(f"- `{path}` — {msg}")
        if len(snap.parse_errors) > 20:
            parts.append(f"- _(+{len(snap.parse_errors) - 20} more)_")
    return "\n".join(parts)


@mcp.tool()
def list_vipmp_releases(
    since: str | None = None,
    section: str | None = None,
    limit: int = 20,
) -> str:
    """
    Return structured VIPMP release notes — the highest-signal information
    for developers tracking API changes. Served from the pre-built index
    (refreshed daily), so calls return in milliseconds.

    Each entry has a date, a section ("api_changes", "sandbox", "upcoming",
    or "earlier"), and one or more changes with titles and bodies. Covers
    both the main API changes and the Sandbox-specific changes at the
    bottom of the release-notes page — they're tracked separately.

    Args:
        since: ISO date ("YYYY-MM-DD"). If provided, returns only releases
            on or after this date. Example: "2026-01-01" for everything
            since New Year. Entries without a date (catch-all "earlier
            releases" buckets) are excluded when `since` is set.
        section: Optional filter. One of:
          - "api_changes" — the main API release stream
          - "sandbox" — Sandbox-environment-specific changes
          - "upcoming" — announced but not yet shipped
          - "earlier" — catch-all entries without a specific date
        limit: Maximum number of release entries to return (default 20).

    Examples:
        # What shipped in 2026?
        list_vipmp_releases(since="2026-01-01", section="api_changes")

        # Recent sandbox-only changes
        list_vipmp_releases(section="sandbox", limit=5)

        # What's coming
        list_vipmp_releases(section="upcoming")
    """
    from .releases import SECTION_API_CHANGES, filter_section, filter_since

    idx = get_active_index()
    if idx is None:
        return (
            "_(No index available — call `rebuild_vipmp_index` to build one "
            "(~60s), then try again. Until then I can't serve release data fast.)_"
        )

    entries = list(idx.releases)
    if not entries:
        return (
            "_(Index has no release entries. This usually means the release-notes "
            "pages failed to parse on the last build. Try `rebuild_vipmp_index`; "
            "if the problem persists, Adobe may have restructured the release-notes "
            "page and the parser needs an update.)_"
        )

    # Filter
    if section:
        entries = filter_section(entries, section)
    if since:
        try:
            entries = filter_since(entries, since)
        except ValueError as exc:
            return f"_(Invalid `since`: {exc})_"

    if not entries:
        filters = []
        if since:
            filters.append(f"since={since}")
        if section:
            filters.append(f"section={section}")
        filter_str = f" ({', '.join(filters)})" if filters else ""
        return f"_(No release entries matched{filter_str}.)_"

    # Sort: dated entries newest-first, undated last.
    entries.sort(
        key=lambda e: (e.date is None, e.date or "", e.section),
        reverse=False,
    )
    # Reverse dated portion so newest first; undated stay at bottom.
    dated = [e for e in entries if e.date]
    undated = [e for e in entries if not e.date]
    dated.sort(key=lambda e: e.date or "", reverse=True)
    entries = dated + undated

    total = len(entries)
    entries = entries[:limit]

    out = [
        f"# VIPMP releases ({len(entries)} of {total} shown)\n",
        _index_source_note(),
        "",
    ]
    if since:
        out.append(f"_Filter: since {since}_")
    if section:
        out.append(f"_Filter: section={section}_")
    out.append("")

    # Group by section for readability when mixed.
    sections_seen: dict[str, list] = {}
    for e in entries:
        sections_seen.setdefault(e.section, []).append(e)

    section_labels = {
        SECTION_API_CHANGES: "API changes",
        "sandbox": "Sandbox changes",
        "upcoming": "Upcoming",
        "earlier": "Earlier releases (undated)",
    }

    for section_key in (SECTION_API_CHANGES, "sandbox", "upcoming", "earlier"):
        if section_key not in sections_seen:
            continue
        section_entries = sections_seen[section_key]
        out.append(f"\n## {section_labels[section_key]}\n")
        for e in section_entries:
            out.append(f"\n### {e.raw_date}\n")
            if e.docs_path:
                out.append(f"_Source:_ `{e.docs_path}`\n")
            for change in e.changes:
                out.append(f"\n**{change.title}**\n")
                if change.body:
                    out.append(change.body)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Console-script entry point."""
    configure_logging()
    log.info("starting vipmp-docs MCP server")
    mcp.run()


if __name__ == "__main__":
    main()
