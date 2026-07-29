"""
Tests that keep manifest.json honest about what the server exposes.

The manifest's `tools` array is what MCP clients that read the bundle
metadata — Claude Desktop among them — display as the extension's tool
set. It is hand-maintained, so it silently drifts whenever a tool is
added to server.py and the manifest is forgotten. That happened with
`list_vipmp_status_codes` (added in 0.12.0, absent from the manifest
until 0.13.1): the server advertised it over `tools/list`, but Desktop
never showed it.
"""

from __future__ import annotations

import asyncio
import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "manifest.json"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _registered_tool_names() -> set[str]:
    """Names of every tool the MCP server actually registers."""
    from vipmp_docs_mcp.server import mcp

    return {tool.name for tool in asyncio.run(mcp.list_tools())}


class TestManifestToolParity:
    """
    The manifest must list exactly the tools the server registers —
    no missing entries (invisible in clients that read the manifest)
    and no stale ones (advertised but uncallable).
    """

    def test_manifest_lists_every_registered_tool(self):
        declared = {t["name"] for t in _manifest()["tools"]}
        missing = _registered_tool_names() - declared
        assert not missing, (
            f"tools registered in server.py but absent from manifest.json: {sorted(missing)}"
        )

    def test_manifest_declares_no_unknown_tools(self):
        declared = {t["name"] for t in _manifest()["tools"]}
        stale = declared - _registered_tool_names()
        assert not stale, (
            f"tools declared in manifest.json but not registered in server.py: {sorted(stale)}"
        )

    def test_every_declared_tool_has_a_description(self):
        for tool in _manifest()["tools"]:
            description = tool.get("description", "")
            assert description.strip(), f"{tool['name']} has no description in manifest.json"


class TestManifestVersion:
    """
    manifest.json and pyproject.toml are bumped together by
    auto-version-bump.yml. A mismatch means a release published a
    bundle whose advertised version disagrees with the wheel.
    """

    def test_manifest_version_matches_pyproject(self):
        pyproject = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
        assert _manifest()["version"] == pyproject["project"]["version"]

    def test_server_handshake_reports_the_installed_version(self):
        """
        The version the server advertises in the initialize handshake is the
        one users quote in bug reports, so it must be wired to the package
        metadata rather than left at the empty string FastMCP 1.x always
        sent (nothing noticed for the whole 1.x era).

        Asserted against installed metadata, not `pyproject.toml`: hatchling
        derives one from the other at build time, and comparing to the file
        would instead fail on a stale editable install — right after a
        maintainer bumps the version, which is the worst moment for it.
        """
        from vipmp_docs_mcp import __version__
        from vipmp_docs_mcp.server import mcp

        assert mcp.version == __version__
        assert mcp.version not in ("", "0.0.0"), (
            "server is advertising no usable version — is `version=` still "
            "passed to MCPServer, and is the package installed?"
        )
