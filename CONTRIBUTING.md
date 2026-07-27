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
# Lint + format — CI gates all four paths
ruff check src/ tests/ scripts/ examples/
ruff format src/ tests/ scripts/ examples/

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
3. **Declare the tool in `manifest.json`'s `tools` array** (name + one-line description). This is what MCP clients that read the bundle metadata — Claude Desktop among them — display, so a tool missing here is invisible to those users even though the server serves it. `tests/test_manifest.py` fails if you skip this.
4. Add an assertion to `scripts/smoke_test.py` that exercises the tool. You do **not** need to register the name there — the expected set is derived from `manifest.json`.
5. Add at least one unit test in `tests/`.
6. Update `README.md`'s tools table.

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
4. Add the prompt name to `EXPECTED_PROMPTS` in `scripts/smoke_test.py`. Prompts are registered dynamically, so unlike tools there's no manifest declaration to derive the set from.
5. Add a smoke-test assertion that the prompt renders correctly.

## Commit style

- Keep messages short and descriptive. Imperative mood ("Add X" not "Added X").
- For anything user-visible, update `CHANGELOG.md` under the `## [Unreleased]` heading.
- We don't require Conventional Commits but short-prefix tags (`fix:`, `feat:`, `docs:`) are welcome.

## Releases

**Pushing a `v*` tag is what releases.** Everything after the tag is automated —
you never build, upload, or create a release by hand.

There are two ways a tag gets created.

### Automated: minor releases from bot PRs

When a PR whose branch is prefixed `bot/` merges into `main` (today that's only
`bot/refresh-index`, from [`refresh-index.yml`](.github/workflows/refresh-index.yml)),
[`auto-version-bump.yml`](.github/workflows/auto-version-bump.yml) takes over:

1. Bumps the **minor** version in `pyproject.toml` + `manifest.json`.
2. Commits straight to `main` (admin PAT, bypassing the PR ruleset).
3. Waits for CI to pass on that commit.
4. Tags `vX.(Y+1).0` — **only** if CI passed.

No human action needed. If CI fails, the version bump still lands on `main` but
nothing is tagged or published; a maintainer investigates and tags manually.

### Manual: patch releases and everything else

The automation only ever produces **minor** bumps, so a patch release — like
0.13.1 — needs a hand-pushed tag.

1. **Refresh dev dependencies** so local matches CI:
   ```bash
   pip install -e ".[dev]" --upgrade
   ```
   Lint rules evolve with ruff versions. Without this step, your local
   pre-tag check can pass under an older rule set while CI fails under
   the latest — which is how we ended up hotfixing v0.4.1.

2. **Full pre-tag check:**
   ```bash
   ruff check src/ tests/ scripts/ examples/
   ruff format --check src/ tests/ scripts/ examples/
   pytest --cov=vipmp_docs_mcp --cov-report=term
   python scripts/smoke_test.py
   ```
   All must pass. If smoke fails, it usually means a tool broke or a prompt
   rendered malformed — CI won't catch those because it doesn't run the smoke
   test (it requires network).

3. Bump `version` in **both** `pyproject.toml` and `manifest.json` — they must
   match, and `tests/test_manifest.py` fails if they drift. Do **not** touch
   `__version__` in `src/vipmp_docs_mcp/__init__.py`; it is derived from the
   installed package metadata and needs no manual edit.

4. Move the `## [Unreleased]` entries in `CHANGELOG.md` under a new
   `## [X.Y.Z] — YYYY-MM-DD` heading. Add the comparison link at the bottom.

5. **Open a PR and merge it.** `main` requires changes to go through a PR, so
   the version bump can't be pushed directly.

6. Tag the merge commit on `main` and push the tag:
   ```bash
   git checkout main && git pull
   git tag -a vX.Y.Z -m "vX.Y.Z — short summary"
   git push origin vX.Y.Z
   ```

### What the tag triggers

Both publish workflows re-verify CI succeeded on the tagged commit before doing
anything, so a hand-pushed tag gets the same protection as an automated one.

| Workflow | Does |
|---|---|
| [`publish-pypi.yml`](.github/workflows/publish-pypi.yml) | Checks the tag matches `pyproject.toml`'s version, builds sdist + wheel, asserts the wheel contains `data/index.json`, publishes to PyPI via OIDC Trusted Publishing (no token or password anywhere) |
| [`publish-mcpb.yml`](.github/workflows/publish-mcpb.yml) | Packs `vipmp-docs-mcp-X.Y.Z.mcpb`, uploads it as a run artifact, then **creates the GitHub Release** (if the tag doesn't have one) and attaches the bundle |

A version/tag mismatch fails the PyPI job rather than publishing something
mislabelled.

### Release notes

The Release is created with an **empty body** — nothing generates notes. Add them
afterwards if the release warrants it:

```bash
gh release edit vX.Y.Z --notes "..."
```

Reference the changelog entry and include the `uvx` install snippet pinned to
`@vX.Y.Z`.

## Dependency updates

[Dependabot](.github/dependabot.yml) opens grouped PRs every Monday for two
ecosystems:

| Group | Covers |
|---|---|
| `runtime-dependencies` | `pyproject.toml` runtime deps + `uv.lock` — changes what users resolve on install |
| `dev-dependencies` | test tooling only — affects CI, not the shipped package |
| `github-actions` | everything under `.github/workflows/` |

Runtime and dev are deliberately separate: a runtime bump changes what
`pip install vipmp-docs-mcp` gives users and deserves closer review than a
pytest bump.

Two things to know when reviewing them:

- **A Dependabot merge does not cut a release.** `auto-version-bump.yml` only
  fires for branches prefixed `bot/`, and Dependabot uses `dependabot/…`. If a
  dependency bump should ship, tag it manually (see Releases above).
- **`ruff` is pinned below the next minor** (`>=0.15.0,<0.16`) because lint
  rules change between minors. Dependabot cannot cross that ceiling on its own;
  widening it is a deliberate call, and expect new lint findings when you do.

## Reporting security issues

Please don't open a public issue for security-sensitive bugs. Email the maintainers directly (see repo settings → Security).

## Code of Conduct

By participating you agree to the terms of the [Code of Conduct](CODE_OF_CONDUCT.md).
