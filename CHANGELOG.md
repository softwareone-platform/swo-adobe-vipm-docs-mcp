# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.2] — 2026-04-18

### Added
- **`CHANGELOG.md`** — you're reading it.
- **`CONTRIBUTING.md`** — dev-environment setup, test/lint workflow, PR guidelines.
- **`CODE_OF_CONDUCT.md`** — Contributor Covenant 2.1.
- **Test coverage reporting** via `pytest-cov`. Coverage runs in CI and an XML
  report is uploaded as a workflow artifact.
- **`examples/`** directory — runnable Python scripts demonstrating how to
  talk to the server programmatically via the MCP client SDK (useful for
  CI, automation, and non-Claude consumers).
- **README badges** — CI status, Python versions, license, MCP protocol.

## [0.3.1] — 2026-04-18

### Added
- **MCP tool annotations** on all 13 tools: `title`, `readOnlyHint`,
  `destructiveHint`, `idempotentHint`, `openWorldHint`. Lets well-behaved
  clients auto-approve read-only calls and confirm before destructive ones,
  and satisfies the Anthropic Connectors Directory submission requirements.

### Changed
- Each tool now carries a human-readable `title` distinct from its
  programmatic name.

## [0.3.0] — 2026-04-18

### Added
- **First-class release-notes tracking** — new `list_vipmp_releases(since, section, limit)`
  tool serving dated, structured entries from Adobe's release notes. Three
  sections tracked separately: `api_changes` (production API), `sandbox`
  (Sandbox environment-specific), `upcoming`.
- **Pre-built structured index** shipped with the package
  (`src/vipmp_docs_mcp/data/index.json`). Structured tools now answer in
  single-digit milliseconds instead of re-parsing HTML on every call.
- **`rebuild_vipmp_index` tool** — rebuild the index locally from live
  Adobe docs (~60s).
- **Two new MCP Prompts** — `summarize_recent_changes(since, area)` and
  `check_feature_status(feature)`, both release-aware.
- **Daily `refresh-index.yml` GitHub Action** — rebuilds the shipped
  baseline from live Adobe docs and opens a PR on structural change.
  Unchanged days produce nothing.
- **Weekly `link-check.yml` GitHub Action** — validates every sitemap
  path resolves and opens an issue on 404s.
- **Structured extractors**: `list_vipmp_endpoints`, `list_vipmp_error_codes`,
  `get_vipmp_schema`, `get_vipmp_code_examples` — all index-backed.
- **Content-aware search** — `search_vipmp_docs` now ranks on cached
  page content in addition to title/tag matches; search results use
  section- or paragraph-level truncation instead of blunt character cutoffs.
- **Disk-backed cache** with 24-hour TTL and `If-None-Match` / ETag
  revalidation. Stale entries are revalidated cheaply; 304 responses
  just bump the timestamp.
- **Auto-sitemap** from Adobe's published `/sitemap.xml`. Handles their
  path migration (underscores → hyphens) that was causing ~60 404s on
  the old hand-curated sitemap.
- **`refresh_vipmp_sitemap` tool** — rebuild the sitemap from Adobe's
  published sitemap.
- **Tenacity-based HTTP retries** with exponential backoff for transient
  5xx / 429 / timeouts.
- **Trailing-slash fallback** in the fetcher — Adobe's docs site is
  inconsistent (some paths 200 only without trailing slash, others only
  with). The fetcher transparently tries both.
- **Content sanity check** — requests that don't contain the expected
  markers (login walls, CDN errors) fail loud instead of returning garbage.
- **`warm_vipmp_cache` tool** — pre-fetch every sitemap page so content
  search has strong recall on all pages.
- **`vipmp_cache_stats` / `vipmp_cache_clear` tools** — operational
  introspection and invalidation.
- **78-test pytest suite** with mocked `httpx`. Runs in under 3 seconds.
- **End-to-end smoke test** (`scripts/smoke_test.py`) over real MCP
  stdio transport.
- **Structured file logging** to a rotating log file in the user's cache
  directory.
- **`pyproject.toml` + hatchling build** replacing `requirements.txt`.
  Adds `uvx`-installable console script entry point (`vipmp-docs-mcp`).
- **CI workflow** — lint + tests on Python 3.12 and 3.13 matrix.
- **Apache 2.0 license** + `NOTICE` file with Adobe trademark disclaimer.

### Changed
- **Restructured** from a single-file `server.py` into a proper Python
  package (`src/vipmp_docs_mcp/`). Every module is independently testable.
- Path normalization now canonicalizes to no-trailing-slash (was
  trailing-slash-required). Fetcher retries the opposite variant on 404
  so existing consumers aren't affected.
- `search_vipmp_docs` output — section-relevance-ranked instead of
  first-6000-chars.

### Removed
- `get_vipmp_releases()` — replaced by the richer `list_vipmp_releases`
  (date + section filterable, served from index).
- Hand-curated `SITEMAP` as primary source — now used only as a fallback
  when the persisted auto-generated sitemap is missing.

### Fixed
- ~60 404s caused by Adobe's underscore-to-hyphen path migration.
- `<br />` tags encoded as literal text (`&lt;br /&gt;`) in Adobe's
  table cells are now parsed into line breaks.

[Unreleased]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/releases/tag/v0.3.0
