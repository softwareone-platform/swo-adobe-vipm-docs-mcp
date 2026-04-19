# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.7.0] — 2026-04-19

### Added
- **Claude Desktop extension packaging.** The repo now ships as a
  `.mcpb` bundle via a new `.github/workflows/publish-mcpb.yml` workflow
  that runs on every `v*` tag push. Uses `server.type: "uv"` so the
  bundle itself is tiny (~85 kB) — dependencies resolve from
  `pyproject.toml` via `uv` on the user's machine. Manifest enumerates
  all 17 tools for the extension UI. Sideloaded `.mcpb` files do not
  auto-update (that's Anthropic-directory-only), so the workflow
  enforces tag ↔ pyproject ↔ manifest version parity to keep the
  artefact and the PyPI release aligned.
- **GitHub-refreshed remote-index tier.** New
  `src/vipmp_docs_mcp/remote_index.py` fetches the current
  `data/index.json` from `main` on raw.githubusercontent.com and uses
  it when it's fresher than the baseline shipped in the installed
  wheel. 12-hour TTL, ETag revalidation (304 costs no bandwidth),
  atomic writes. `resolve_active_index()` in `index.py` now walks four
  tiers: user-local rebuild → github-remote → package baseline →
  live-extraction fallback. Merging the daily `refresh-index` PR is now
  enough to put fresh data on users' machines within 12 h — no PyPI
  release or `uvx` cache dance required.
- **`VIPMP_DISABLE_REMOTE_INDEX`** environment variable for
  deterministic runs (tests, air-gapped environments, forensic
  debugging). When set to a truthy value, the remote tier is skipped
  and the package baseline is used directly.
- **`vipmp_server_info` now reports the active index tier** and the
  remote-index cache state (fetched-at, TTL, URL, opt-out status) so
  users can see which source their tool results are coming from.

### Internal
- `index.py` gains `ActiveIndex` (snapshot + source label + path) and
  `resolve_active_index()`. `get_active_index()` is retained as a
  backwards-compatible wrapper — all seven existing callers in
  `server.py` keep working without changes.
- Remote-index tier is always stale-OK: any transport error, non-JSON
  response, or unexpected exception falls back to whatever is on disk
  and, failing that, to the package baseline. Never raises.
- Added 21 new tests (17 in `tests/test_remote_index.py` covering
  opt-out, fresh fetch, 304 revalidation, TTL short-circuit, network
  failure fallback, and status reporting; 4 in `tests/test_index.py`
  covering tier priority).

## [0.6.1] — 2026-04-18

### Added
- **PyPI publishing.** New `.github/workflows/publish-pypi.yml` workflow
  publishes to PyPI on every `v*` tag push using **Trusted Publishing**
  (OIDC) — no API tokens to rotate. Verifies the wheel includes
  `data/index.json` and that the git tag matches the package version
  before publishing.
- **README install snippet** simplified to `uvx vipmp-docs-mcp`
  (PyPI-backed). The git-source snippet is still documented for
  bleeding-edge installs but flagged with a Windows-PATH caveat — Claude
  Desktop's subprocess often can't find git, which broke the install
  for at least one user who tried the v0.6.0 snippet.

### Changed
- **Removed redundant `force-include` block** from `pyproject.toml`'s
  hatchling config. It was duplicating `data/index.json` into the
  wheel, triggering a build warning. The default `packages` directive
  already ships everything under the package directory.

### Internal
- Bumped to v0.6.1 to mark the first PyPI-published release. No code
  changes.

## [0.6.0] — 2026-04-18

### Added
- **Parallel async fetcher** — new `async_fetch_many` in `fetcher.py`
  uses `httpx.AsyncClient` with a 5-way semaphore. `warm_vipmp_cache`
  and `build_index` use it. Cold rebuild dropped from **38s to 6.6s
  (5.7x faster)**. Includes the same trailing-slash fallback and content
  sanity check as the sync fetcher; per-path failures are isolated so
  one bad page doesn't abort a batch.
- **Adobe-published validation regex enforcement** — extracts the
  `Field Name | Resource | Regular Expression` table from
  `/vipmp/docs/references/validations` and checks every string field in
  a body against the matching rule. Cross-cutting: a rule for
  `firstName` (defined on the Contact resource) fires even when
  validating a Customer body. Works for `companyName`, `firstName`,
  `lastName`, and `postalCode` today; auto-extends as Adobe documents
  more.
- **Java → Python regex translator** — Adobe ships regexes as Java
  source string literals (doubled backslashes); we now un-escape them
  correctly. Uses the third-party `regex` package (added as a runtime
  dependency) for full Unicode property support (`\\p{L}`, `\\p{N}`),
  with a graceful ASCII fallback if `regex` isn't available.

### Changed
- **Index schema bumped to v4** — adds `validations: list[ValidationRule]`
  to `IndexSnapshot`. v0.5.x indexes are transparently discarded and
  rebuilt.
- **Baseline index rebuilt** — 21 endpoints, 65 error codes, 18 schemas,
  17 releases, **4 validation rules**.
- **Build performance:** `build_index` uses parallel fetching (was
  serial). `warm_vipmp_cache` likewise.

### Tests
- 24 new tests across `test_async_fetcher.py` and `test_validations.py`.
- Full suite now **138 tests** passing in ~4 seconds.

## [0.5.0] — 2026-04-18

### Added
- **`vipmp_server_info`** tool — diagnostic dump: package version,
  Python version, index age + counts (endpoints / errors / schemas /
  releases / deprecations), sitemap size, cache stats, log file path,
  and a "Tips" section pointing at the right tool when something looks
  off. First call when debugging.
- **`Literal` types for closed-set arguments** — `section` on
  `list_vipmp_releases`, `method` on `describe_vipmp_endpoint`, and
  `language` on `generate_vipmp_request` are now declared as `Literal[...]`.
  Surfaces in the tool's JSON schema as `enum: [...]`, so MCP clients
  can render them as dropdowns (and reject invalid values before they
  reach the server).

### Changed
- **Sharper error messages** across `server.py` and `validator.py` —
  empty-result paths and fetch failures now tell the caller exactly
  what to do next. Examples:
  - `get_vipmp_page` fetch failure → suggests `refresh_vipmp_sitemap` /
    `list_vipmp_docs` and explains the retry behaviour.
  - "No error codes matched query" → suggests dropping the filter,
    using a substring, or rebuilding the index.
  - "No request schema extracted" → suggests `get_vipmp_page` and
    `get_vipmp_code_examples` for the same path.
- **CONTRIBUTING.md release checklist** — added a "refresh dev
  dependencies" step (`pip install -e ".[dev]" --upgrade`) before
  pre-tag lint, so future hotfixes like v0.4.1 don't recur from local
  / CI ruff drift.

### Considered, deferred
- **Structured output** for `validate_vipmp_request` — FastMCP supports
  it via TypedDict return types, but adopting it would replace the
  current Markdown output with auto-generated text (less readable for
  humans). Will revisit if any agent integration explicitly needs
  programmatic issue lists.
- **Prompt argument completion** — MCP spec scopes
  `completion/complete` to prompts and resource templates, not tool
  args. Our prompts currently don't have closed-set arguments worth
  completing.

## [0.4.1] — 2026-04-18

### Fixed
- CI lint failures on ruff 0.15 that didn't fire on the older ruff
  version pinned locally. Addressed by:
  - Replacing a trivial `if`/`else`-block with a `value or fallback`
    expression in `codegen.py` (SIM108).
  - Combining nested `with patch(...):` statements in
    `tests/test_codegen.py` (SIM117).
  - Prefixing an unused unpacked variable with `_` in
    `tests/test_validator.py` (RUF059).
  - Re-sorting import blocks in both new test files (I001).

### Changed
- **Pinned `ruff>=0.15.0,<0.16`** in the dev extras so local and CI see
  the same rule set. Avoids the kind of surprise where a working local
  pre-commit run passes but CI fails on newly-enabled rules.

## [0.4.0] — 2026-04-18

### Added
- **`describe_vipmp_endpoint(method, path)`** — one-shot endpoint profile:
  returns the request schema, documented error codes, release-note
  mentions, and cross-references to code examples + validation in a
  single call. Replaces 4 chained tool invocations with one coherent
  view. Index-backed; closed-world.
- **`validate_vipmp_request(endpoint, body_json)`** — programmatic
  validator that cross-checks a JSON body against the documented schema.
  Detects unknown fields (warning), missing required fields (error),
  type mismatches (error), constraint violations like "Max: 35 characters"
  or numeric maxes (error), nested objects not recursively validated
  (info), and usage of deprecated fields (warning). Turns the
  `review_request_body` prompt workflow into a real programmatic tool.
- **`generate_vipmp_request(endpoint, body?, language?)`** — emits a
  runnable code snippet for an endpoint in one of four languages:
  `curl` (default), `powershell` (Invoke-RestMethod), `python` (httpx),
  `csharp` (HttpClient). When no body is supplied, builds a placeholder
  body from the schema so the snippet shows the full shape the developer
  needs to fill in. Skips read-only fields automatically.
- **Deprecation tracking** — extractors now scan for deprecation markers
  ("deprecated", "will be removed", "no longer supported", "sunset",
  "end of life") and tag endpoints and schema fields with a
  `deprecated: bool` + `deprecation_note: str | None`. Used by
  `describe_vipmp_endpoint` (flags deprecated endpoints with a banner)
  and `validate_vipmp_request` (warns when a deprecated field is used).

### Changed
- **Index schema bumped to v3.** Adds `deprecated` + `deprecation_note`
  to `Endpoint`; adds `deprecated` to `SchemaField`. Any on-disk index
  from v0.3.x is transparently discarded and rebuilt.
- **Server instructions** rewritten to guide Claude toward the new
  endpoint-centric tools before falling back to generic doc search.
- **Code snippet placeholder body** now includes all non-read-only
  fields when no field is explicitly required (Adobe's docs don't always
  mark required fields), so developers see the full shape instead of
  an empty body.

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

[Unreleased]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.6.1...HEAD
[0.6.1]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.3.2...v0.4.0
[0.3.2]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/releases/tag/v0.3.0
