"""Adobe VIP Marketplace Docs MCP Server."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vipmp-docs-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0"
