"""
Look up a VIPMP error code and print its documented cause.

Demonstrates calling a tool with a query filter. Handy for piping into
shell pipelines, embedding in CI failure messages, etc.

Run:
    python examples/find_error_code.py 1117
    python examples/find_error_code.py INVALID_LM_MIGRATION_LEVEL
    python examples/find_error_code.py "coterm"      # substring match
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSOLE_SCRIPT = (
    REPO_ROOT / ".venv" / "Scripts" / "vipmp-docs-mcp.exe"
    if sys.platform == "win32"
    else REPO_ROOT / ".venv" / "bin" / "vipmp-docs-mcp"
)


async def find(code: str) -> str:
    params = StdioServerParameters(command=str(CONSOLE_SCRIPT), args=[])
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        r = await session.call_tool("list_vipmp_error_codes", {"query": code})
        return "".join(c.text for c in r.content if hasattr(c, "text"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "code",
        help="Error code or substring to search for (case-insensitive). "
        'Examples: "1117", "INVALID_LM_MIGRATION_LEVEL", "coterm".',
    )
    args = parser.parse_args()

    result = asyncio.run(find(args.code))
    print(result)


if __name__ == "__main__":
    main()
