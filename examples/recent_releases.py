"""
Print every VIPMP release that shipped in the last 30 days, grouped by section.

Demonstrates calling a tool with arguments and parsing its Markdown output.
Useful as a cron job to post weekly digests to Slack, a newsletter, etc.

Run:
    python examples/recent_releases.py
    python examples/recent_releases.py --since 2026-01-01
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent
CONSOLE_SCRIPT = (
    REPO_ROOT / ".venv" / "Scripts" / "vipmp-docs-mcp.exe"
    if sys.platform == "win32"
    else REPO_ROOT / ".venv" / "bin" / "vipmp-docs-mcp"
)


async def fetch_releases(since: str) -> str:
    params = StdioServerParameters(command=str(CONSOLE_SCRIPT), args=[])
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        r = await session.call_tool(
            "list_vipmp_releases", {"since": since, "limit": 50}
        )
        return "".join(c.text for c in r.content if hasattr(c, "text"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since",
        default=(date.today() - timedelta(days=30)).isoformat(),
        help="ISO date (YYYY-MM-DD). Defaults to 30 days ago.",
    )
    args = parser.parse_args()

    print(f"Releases since {args.since}:")
    print("=" * 60)
    print(asyncio.run(fetch_releases(args.since)))


if __name__ == "__main__":
    main()
