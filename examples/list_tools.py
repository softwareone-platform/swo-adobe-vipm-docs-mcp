"""
Minimal example: connect to the server and list every registered tool + prompt.

The shortest thing that proves you can talk to the server from Python.
Useful as a starting skeleton for your own scripts.

Run:
    python examples/list_tools.py
"""

from __future__ import annotations

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


async def main() -> None:
    params = StdioServerParameters(command=str(CONSOLE_SCRIPT), args=[])

    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        init = await session.initialize()
        print(f"Connected to {init.serverInfo.name} v{init.serverInfo.version}")
        print()

        tools = await session.list_tools()
        print(f"Tools ({len(tools.tools)}):")
        for t in sorted(tools.tools, key=lambda x: x.name):
            print(f"  - {t.name:30s}  {t.title or ''}")

        prompts = await session.list_prompts()
        print()
        print(f"Prompts ({len(prompts.prompts)}):")
        for p in sorted(prompts.prompts, key=lambda x: x.name):
            args = ", ".join(a.name for a in (p.arguments or []))
            print(f"  - {p.name}({args})")


if __name__ == "__main__":
    asyncio.run(main())
