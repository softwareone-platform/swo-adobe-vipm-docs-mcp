"""
Tests that keep README.md honest about what the server exposes.

The README's tool tables are what a human reads before installing, and
nothing kept them in sync with `server.py`. Both directions had drifted:
`vipmp_server_info` shipped and was never documented, and the tables still
cited `get_vipmp_releases`, removed in 0.12.0 in favour of
`list_vipmp_releases`. `tests/test_manifest.py` catches the equivalent drift
in `manifest.json`; this catches it in the prose.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"

# Backticked lowercase snake_case identifiers. Filtered below to those that
# look like MCP entry points; matches with or without a trailing "(", since
# the README cites tools both ways.
BACKTICKED = re.compile(r"`([a-z][a-z0-9_]*)\(?")

# Same shape as a tool name but not one: the package directory, which appears
# inside backticked file paths.
NOT_TOOLS = frozenset({"vipmp_docs_mcp"})


def _registered(kind: str) -> set[str]:
    from vipmp_docs_mcp.server import mcp

    lister = mcp.list_tools if kind == "tools" else mcp.list_prompts
    return {item.name for item in asyncio.run(lister())}


def _tool_shaped_mentions() -> set[str]:
    """
    Backticked identifiers in the README that are shaped like a tool name:
    snake_case and containing "vipmp". The underscore requirement drops the
    bare `vipmp` that falls out of backticked `vipmp-docs-mcp`, since the
    pattern stops at the hyphen.
    """
    tokens = set(BACKTICKED.findall(README_PATH.read_text(encoding="utf-8")))
    return {t for t in tokens if "vipmp" in t and "_" in t} - NOT_TOOLS


class TestReadmeToolParity:
    """
    The README must document exactly the tools the server registers — an
    undocumented tool goes unused, and a documented-but-removed one sends
    readers looking for something that will never answer.
    """

    def test_readme_documents_every_registered_tool(self):
        missing = _registered("tools") - _tool_shaped_mentions()
        assert not missing, (
            f"tools registered in server.py but absent from README.md: {sorted(missing)}"
        )

    def test_readme_cites_no_unknown_tools(self):
        # Prompts share the naming shape and are documented in their own
        # table, so they are legitimate mentions rather than stale tools.
        stale = _tool_shaped_mentions() - _registered("tools") - _registered("prompts")
        assert not stale, (
            f"tools cited in README.md but not registered in server.py: {sorted(stale)}"
        )
