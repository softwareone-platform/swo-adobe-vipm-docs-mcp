# Contributing

Thanks for your interest in contributing. This project is a small, focused MCP server for Adobe VIPMP docs — PRs for bug fixes, parser improvements, new tools/prompts, and docs are welcome.

## Before you open a PR

**Please open an issue first** for anything non-trivial — a new tool, a parser rewrite, a dependency swap. A 10-line issue conversation saves everyone from a rejected PR. Small fixes (typos, obvious bugs, a missing trailing slash in a URL) can go straight to a PR.

## Dev setup

```bash
git clone https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp.git
cd swo-adobe-vipm-docs-mcp

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -e ".[dev]"
```

Requires **Python 3.12+**.

## The feedback loop

```bash
# Lint + format
ruff check src/ tests/ scripts/
ruff format src/ tests/ scripts/      # optional; project follows ruff defaults

# Fast unit tests (mocked httpx, no network)
pytest -v

# Coverage
pytest --cov=vipmp_docs_mcp --cov-report=term-missing

# End-to-end smoke test (spawns the server, talks over real MCP stdio)
python scripts/smoke_test.py
```

All of these run in CI on every PR. Keep them green.

## What the code is organized around

```
src/vipmp_docs_mcp/
├── server.py             # FastMCP entry point — tool/prompt registration
├── fetcher.py            # HTTP client (retries + trailing-slash fallback)
├── cache.py              # Disk cache with TTL + ETag
├── sitemap.py            # Hand-curated fallback sitemap
├── autositemap.py        # Fetches Adobe's /sitemap.xml, builds entries
├── html_cleaner.py       # HTML → Markdown-ish text
├── search.py             # Scoring, section/paragraph truncation
├── extractors.py         # div.table parsers: endpoints, errors, schemas, code
├── releases.py           # Release-notes parser (dated + section-aware)
├── index.py              # IndexSnapshot: ties extractors + releases together
├── prompts.py            # MCP prompts
├── logging_config.py     # Rotating file logger
└── data/index.json       # Shipped baseline index, refreshed daily by GHA
```

Tests live in `tests/` with synthetic HTML fixtures in `tests/conftest.py`.

## Adding a new tool

1. Add the function to `src/vipmp_docs_mcp/server.py` with the `@mcp.tool(...)` decorator.
2. Always set `title` and `annotations=ToolAnnotations(...)` — see existing tools for the pattern.
3. Add the tool name to the `expected_tools` set in `scripts/smoke_test.py` and add an assertion that exercises it.
4. Add at least one unit test in `tests/`.
5. Update `README.md`'s tools table.

## Adding a new extractor

1. Put the parser in `src/vipmp_docs_mcp/extractors.py` (or `releases.py` for date-structured content).
2. Add it to `IndexSnapshot` in `index.py` and populate it in `build_index()`.
3. Bump `INDEX_SCHEMA_VERSION` if the on-disk shape changes.
4. Add a synthetic HTML fixture to `tests/conftest.py` and cover the happy path + at least one edge case.
5. Test locally: `python -m vipmp_docs_mcp.index.build_index` (or use the MCP tool `rebuild_vipmp_index` via a client).

## Adding a new prompt

1. Add a function with `@mcp.prompt()` in `src/vipmp_docs_mcp/prompts.py`.
2. Be explicit about which tools Claude should chain — prompts are only as good as their tool hints.
3. Avoid gaps in numbered steps (the smoke test checks for this).
4. Add a smoke-test assertion that the prompt renders correctly.

## Commit style

- Keep messages short and descriptive. Imperative mood ("Add X" not "Added X").
- For anything user-visible, update `CHANGELOG.md` under the `## [Unreleased]` heading.
- We don't require Conventional Commits but short-prefix tags (`fix:`, `feat:`, `docs:`) are welcome.

## Releases

Maintainers:

1. Bump `version` in `pyproject.toml` and `__version__` in `src/vipmp_docs_mcp/__init__.py`.
2. Move the `## [Unreleased]` entries in `CHANGELOG.md` under a new `## [X.Y.Z] — YYYY-MM-DD` heading.
3. Commit, tag (`git tag -a vX.Y.Z -m "..."`), push `main` + tag.
4. `gh release create vX.Y.Z --title "..." --notes "..."` referencing the changelog entry.

## Reporting security issues

Please don't open a public issue for security-sensitive bugs. Email the maintainers directly (see repo settings → Security).

## Code of Conduct

By participating you agree to the terms of the [Code of Conduct](CODE_OF_CONDUCT.md).
