# Adobe VIP Marketplace Docs MCP Server

[![CI](https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12%20%7C%203.13-blue)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-compatible-6E56CF)](https://modelcontextprotocol.io/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-green)](LICENSE)
[![Latest Release](https://img.shields.io/github/v/release/softwareone-platform/swo-adobe-vipm-docs-mcp?label=release)](https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp/releases)

A local [Model Context Protocol](https://modelcontextprotocol.io/) server that turns the [Adobe VIP Marketplace Partner API documentation](https://developer.adobe.com/vipmp/docs/) into searchable, structured tools for Claude Desktop (or any other MCP-aware client).

Built to save SoftwareOne developers from scrolling through Adobe's docs to find the right endpoint, error code, or field definition. Ask Claude instead — it uses this server to look it up.

## What you can ask

Once installed, ask Claude things like:

> "How do I create a reseller account?"
> "What are the error codes for LGA enrollment?"
> "What fields does the Customer resource have, and which are required?"
> "Show me the JSON request body for `POST /v3/customers`."
> "Is 3YC available for LGA customers?"
> "What changed in the last VIPMP release?"

Claude calls one of the tools below, the server fetches and parses the relevant Adobe docs, and the answer flows into your conversation — with links back to the canonical pages.

## Tools exposed

### Search & fetch
| Tool | What it does |
|---|---|
| `search_vipmp_docs(query, max_results?)` | Ranks pages by title/tag matches plus content matches (for any page already in the local cache). Returns relevance-ranked sections, not blunt character cutoffs. |
| `list_vipmp_docs()` | Full sitemap of every documented page, grouped by topic. |
| `get_vipmp_page(path)` | Fetch the full content of a specific page. |

### Endpoint-centric tools (the highest-leverage workflows)
| Tool | What it does |
|---|---|
| `describe_vipmp_endpoint(method, path)` | **One-shot profile**: schema + error codes + release-note mentions + cross-references in a single call. The fastest way to understand an endpoint end-to-end. |
| `validate_vipmp_request(endpoint, body_json)` | Programmatically checks a JSON body against the documented schema. Catches unknown fields, missing required fields, type mismatches, constraint violations (e.g. "Max: 35 characters"), and deprecated-field usage. |
| `generate_vipmp_request(endpoint, body?, language?)` | Emits a runnable snippet in `curl` / `powershell` / `python` (httpx) / `csharp` (HttpClient). Builds a placeholder body from the schema when you don't supply one. |

### Structured extractors
| Tool | What it does |
|---|---|
| `list_vipmp_endpoints()` | Every REST endpoint across the docs — method + path + source page. |
| `list_vipmp_error_codes(query?)` | Every documented error code (numeric + symbolic) with triggering endpoint and reason. |
| `get_vipmp_schema(resource_name?)` | Structured field schemas (name, type, required, description, constraints) for VIPMP resources. |
| `get_vipmp_code_examples(docs_path, language?)` | Pull JSON / curl / Python / etc. code blocks off a specific page. |
| `list_vipmp_releases(since?, section?, limit?)` | **Dated release entries** — API changes, Sandbox changes, and upcoming. Filter by date or section. Refreshed daily. See [Tracking releases](#tracking-releases) below. |

### Cache, sitemap & index management
| Tool | What it does |
|---|---|
| `warm_vipmp_cache()` | Pre-fetch every page (~30s one-time) so content-level search works on all pages immediately. |
| `vipmp_cache_stats()` | Cache size, freshness, TTL, file path. |
| `vipmp_cache_clear(path?)` | Drop one entry or the whole cache. |
| `refresh_vipmp_sitemap()` | Rebuild the sitemap from Adobe's published `/sitemap.xml`. Run when you're seeing 404s or think the sitemap has drifted. |
| `rebuild_vipmp_index()` | Rebuild the pre-extracted index of endpoints/error codes/schemas (~60s). Run to refresh the data behind the structured tools between package updates. |

## Prompts

Pre-baked prompt templates your MCP client can offer directly (no need to remember which tools to chain):

| Prompt | Arguments |
|---|---|
| `review_request_body` | `endpoint`, `body_json` — cross-checks your JSON body against the documented schema |
| `debug_error_code` | `code`, `endpoint?` — diagnoses a specific VIPMP error code and suggests fixes |
| `draft_order` | `customer_id`, `offers`, `market_segment?` — walks through creating a `POST /v3/orders` request |
| `summarize_recent_changes` | `since?`, `area?` — release digest grouped by theme, flags breaking/deprecations |
| `check_feature_status` | `feature` — is it live / in Sandbox / upcoming / not documented? |
| `check_3yc_eligibility` | `customer_id`, `desired_commit_quantity?` — evaluates 3-Year Commit eligibility |

### Training curriculum

Seven prompts for learning how VIPMP works — intended for new developers and technical product managers alike. Each walkthrough blends business context (why the rule exists, what it means commercially) with the API surface (which endpoints, which schemas, which errors). Prompts draw from Adobe's published docs *and* [`src/vipmp_docs_mcp/content/training-supplement.md`](src/vipmp_docs_mcp/content/training-supplement.md) — a human-authored file where SoftwareOne operational knowledge gets captured. Contributing to the supplement is how you make the whole curriculum smarter for everyone.

| Prompt | Arguments |
|---|---|
| `start_vipmp_learning` | `role?`, `goal?` — friendly router that asks what you're trying to learn and points you at the right walkthrough |
| `learn_customer_lifecycle` | — states, transitions, API surface, common traps |
| `learn_ordering_flow` | — ordering end-to-end: commercial states + API sequence + error handling |
| `learn_3yc` | — 3-Year Commit eligibility, commit math, enrollment flow |
| `learn_subscriptions_and_renewals` | — coterm, auto-renew, proration, mid-term changes |
| `learn_returns_and_refunds` | — return windows, what qualifies, refund mechanics |
| `learn_auth_and_sandbox` | — IMS auth, credentials, safe sandbox experimentation |

## Install

### With `uvx` (recommended — zero setup, no clone, no git required)

If you have [uv](https://docs.astral.sh/uv/) installed, drop this into `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "vipmp-docs": {
      "command": "uvx",
      "args": ["vipmp-docs-mcp"]
    }
  }
}
```

`uvx` fetches `vipmp-docs-mcp` from PyPI on first run and caches it. Updates: `uvx cache clean vipmp-docs-mcp` then restart Claude Desktop.

**Pin to a specific version** if you want stability:

```json
{
  "mcpServers": {
    "vipmp-docs": {
      "command": "uvx",
      "args": ["vipmp-docs-mcp==0.6.1"]
    }
  }
}
```

**Install bleeding-edge from source** (requires git on PATH):

```json
{
  "mcpServers": {
    "vipmp-docs": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp.git",
        "vipmp-docs-mcp"
      ]
    }
  }
}
```

> **Note:** the git-source variant requires `git` to be on the PATH that Claude Desktop's subprocess sees. On Windows this is sometimes only on the User PATH and not the System PATH; if you see "Git executable not found" in Claude Desktop's MCP logs, either move git into System PATH or use the PyPI snippet above (which doesn't need git).

### From a clone (for development)

```bash
git clone https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp.git
cd swo-adobe-vipm-docs-mcp
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -e ".[dev]"
```

Then point Claude Desktop at the installed console script:

```json
{
  "mcpServers": {
    "vipmp-docs": {
      "command": "<path-to-clone>/.venv/Scripts/vipmp-docs-mcp.exe",
      "args": []
    }
  }
}
```

Restart Claude Desktop after saving. Requires **Python 3.12+**.

### Verify

In a new Claude Desktop conversation, ask:

> "List all Adobe VIP Marketplace doc pages."

Claude should call `list_vipmp_docs` and return ~86 entries grouped by section.

## Recipes

Concrete examples of what to ask, and which tools/prompts Claude will call.

### "What endpoints exist for customer accounts?"
Triggers `list_vipmp_endpoints`, filters output to the `customer-account` group.

### "What fields does a Customer have, and which are required?"
Triggers `get_vipmp_schema` with `resource_name="customer"`. Returns a table of field name / type / required / description / constraints.

### "I'm getting error 1117 on POST /v3/customers — what's wrong?"
Use the `debug_error_code` prompt:
- Args: `code=1117`, `endpoint="POST /v3/customers"`
- Claude calls `list_vipmp_error_codes` → finds docs → calls `get_vipmp_page` for context → calls `get_vipmp_schema` if the fix involves a specific field → summarises.

### "Draft a request to create a new customer for reseller 5556667778 in commercial segment."
Use the `draft_order` prompt variants or ask Claude directly. It will:
1. `search_vipmp_docs("create customer")`
2. `get_vipmp_schema("customer")`
3. `get_vipmp_code_examples("/vipmp/docs/customer-account/create-customer-account", language="json")`
4. Produce a valid JSON body, flag anything it's guessing.

### "Is the new LGA convert endpoint live yet?"
Triggers `list_vipmp_releases(since="2026-01-01")` to see what's shipped, then `get_vipmp_page` on the LGA docs for context. Claude cross-references to tell you the release date or that it's still upcoming.

### "What changed in the VIPMP API since 2026-01-01?"
Triggers `list_vipmp_releases(since="2026-01-01", section="api_changes")`. Returns a dated, sectioned list of every release — in milliseconds because it's served from the pre-built index.

### "Catch me up on LGA changes in the last month."
Use the `summarize_recent_changes` prompt with `area="LGA"`. Claude fetches recent API changes, Sandbox changes, and upcoming entries, filters to LGA mentions, groups the result by theme, and flags anything breaking.

### "Is Mid-Term Upgrades live in production yet?"
Use the `check_feature_status` prompt with `feature="Mid-term upgrades"`. Returns one of {Live / In Sandbox / Upcoming / Not documented}, with the release date and evidence quoted from the docs.

### "Tell me everything about `POST /v3/customers`."
One call: `describe_vipmp_endpoint(method="POST", path="/v3/customers")`. Returns the request schema, documented error codes, release-note mentions, and cross-references to `get_vipmp_code_examples` / `generate_vipmp_request` / `validate_vipmp_request`. Replaces what used to be four separate tool calls.

### "Check this JSON body before I send it."
`validate_vipmp_request(endpoint="POST /v3/customers", body_json='{"resellerId":"R1","externalReferenceId":"..."}')`. Returns a structured issue list: errors (missing required, type mismatch, constraint violation, deprecated field), warnings (unknown fields), and info (nested objects not recursively validated). Catches most real-world mistakes in milliseconds.

### "Give me a Python / PowerShell / C# starting point for this endpoint."
`generate_vipmp_request(endpoint="POST /v3/customers", language="python")`. Emits a runnable snippet with the auth-header scaffolding and a schema-derived placeholder body. Swap `${VIPMP_BASE_URL}` and `${VIPMP_ACCESS_TOKEN}` for your own values and you have a working request shell.

### "Pre-warm the cache so search works faster."
Call the `warm_vipmp_cache` tool directly. One-time ~30s fetch of every page. Subsequent searches get content-level relevance matching across all 86 pages.

## Tracking releases

Release notes are the highest-signal information for developers working against an evolving API — you need to know "has X shipped?", "what changed this month?", "is Y still upcoming?". This server treats them as a first-class data type.

The `list_vipmp_releases` tool serves structured, dated entries pulled from Adobe's two release-notes pages:

- [/vipmp/docs/release-notes](https://developer.adobe.com/vipmp/docs/release-notes) → `section="api_changes"` and (from the bottom of the same page) `section="sandbox"`
- [/vipmp/docs/release-notes/upcoming-releases](https://developer.adobe.com/vipmp/docs/release-notes/upcoming-releases) → `section="upcoming"`

Each entry has an ISO date (where available), a section, and one or more changes with titles and Markdown bodies — so filtering by "what changed since February" is a one-line call.

**Daily refresh.** The [`refresh-index.yml`](.github/workflows/refresh-index.yml) GitHub Action runs daily (04:23 UTC), rebuilds the index including releases, and opens a PR if anything changed. Published installs (`pip install -e .`, `uvx --from git+...`) pick up updates automatically once the PR merges. For bleeding-edge, call `rebuild_vipmp_index` locally.

**Prompting patterns:**

```
"What are the latest VIPMP updates since 2026-01-01?"
  → list_vipmp_releases(since="2026-01-01")

"What shipped in the Sandbox environment recently?"
  → list_vipmp_releases(section="sandbox", limit=5)

"What's coming in upcoming releases?"
  → list_vipmp_releases(section="upcoming")

"Has the Early Renewals feature shipped yet?"
  → list_vipmp_releases(since="2026-01-01") + grep
```

Sections are kept separate because they mean different things: `api_changes` is production-live, `sandbox` only applies to the test environment, `upcoming` isn't live yet, and `earlier` is the catch-all bucket for pre-2025 changes that Adobe hasn't dated.

## The structured index

The `list_vipmp_endpoints`, `list_vipmp_error_codes`, `get_vipmp_schema`, and `get_vipmp_releases` tools are all served from a **pre-built index** — a single JSON file that captures every endpoint, error code, and field schema extracted from Adobe's docs. With the index in place these tools answer in **single-digit milliseconds**. Without it, they fall back to live extraction across ~86 pages (~30s cold, ~5s warm).

**Three-tier resolution for the active index:**

1. **User-local rebuild** (`~/.cache/swo-adobe-vipm-docs-mcp/index.json`) — freshest. Written by the `rebuild_vipmp_index` MCP tool when you run it.
2. **Package-shipped baseline** (`src/vipmp_docs_mcp/data/index.json`) — what you get out of the box. Refreshed weekly by the `refresh-index.yml` GitHub Action and included in each release.
3. **None** — tools fall back to live extraction. The output annotates this so you know.

**Keeping the baseline fresh:** a GitHub Action ([`refresh-index.yml`](.github/workflows/refresh-index.yml)) runs **daily** (release notes change frequently) and also on demand via `workflow_dispatch`. It rebuilds the index against live Adobe docs and, if anything changed (new endpoint, removed error code, schema drift, fresh release entry, etc.), opens a PR for human review. Merging that PR publishes the new baseline to `pip install -e .` / `uvx --from git+...` installs automatically. Days where nothing changes produce no PR.

**Running on demand:**
```bash
# Via the Actions UI:
#   Actions → Refresh structured index → Run workflow (add a reason)

# Or via the gh CLI:
gh workflow run refresh-index.yml -f reason="Adobe released new error codes"
```

Downstream users who want bleeding-edge can call `rebuild_vipmp_index` from their MCP client at any time — takes ~60 seconds and writes to their local cache dir, overriding the shipped baseline until the next run.

## How it works

- **Fetches on demand, caches on disk.** Pages are pulled from `developer.adobe.com` when first requested and stored in `~/.cache/swo-adobe-vipm-docs-mcp/cache.json` with a 24-hour TTL. Stale entries are revalidated cheaply via HTTP `If-None-Match` — a 304 just bumps the timestamp without re-downloading.
- **Resilient fetching.** Retries on transient 5xx / timeouts / rate-limits with exponential backoff. Adobe's docs are inconsistent about trailing slashes; the fetcher transparently tries both forms on 404.
- **Content sanity check.** If Adobe ever serves a login wall or CDN error page, the server detects missing content markers and fails loud instead of returning garbage.
- **Auto-refreshing sitemap.** The sitemap is built from Adobe's own `/sitemap.xml` and persisted to `sitemap.json` with hand-curated search tags merged on top. Call `refresh_vipmp_sitemap` when you suspect drift; the weekly GitHub Actions link-check opens an issue if it detects 404s on known paths.
- **Section- and paragraph-level truncation.** `search_vipmp_docs` returns the most relevant sections of each matched page — on flat pages (Adobe docs are often flat) it falls back to paragraph-level ranking.
- **Structured parsers** for Adobe's `div.table` pseudo-tables extract endpoints, error codes, and field schemas into real data structures — no more eyeballing HTML.

## Logs

The server logs to a rotating file so transient failures are debuggable:

- Windows: `%LOCALAPPDATA%\swo-adobe-vipm-docs-mcp\server.log`
- macOS: `~/Library/Caches/swo-adobe-vipm-docs-mcp/server.log`
- Linux: `~/.cache/swo-adobe-vipm-docs-mcp/server.log`

## Development

```bash
pip install -e ".[dev]"
ruff check src/ tests/
pytest -v
```

The test suite is 56 pytest-mocked tests (no network required) covering parsers, cache, search, and fetcher retry logic.

## Requirements

- Python 3.12+
- Internet access to `https://developer.adobe.com`
- MCP client (Claude Desktop, [Cline](https://github.com/cline/cline), [Cursor](https://cursor.sh/), etc.)

## License

Licensed under the [Apache License, Version 2.0](LICENSE). See the [NOTICE](NOTICE) file for attribution.

Copyright © 2026 SoftwareOne AG.

---

_Adobe, Adobe VIP Marketplace, and related marks are trademarks of Adobe Inc. This project is not affiliated with, endorsed by, or sponsored by Adobe Inc._
