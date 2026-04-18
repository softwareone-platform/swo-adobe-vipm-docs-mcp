# Examples

Runnable Python scripts that talk to the server via the MCP client SDK — useful for scripting, CI, or any non-Claude consumer.

Each example spawns the server as a subprocess (the same way Claude Desktop does) and speaks MCP over stdio. Install the package first:

```bash
pip install -e ".[dev]"
```

Then run any example:

```bash
python examples/list_tools.py
python examples/recent_releases.py
python examples/find_error_code.py 1117
```

## What's in here

| Script | What it does |
|---|---|
| [`list_tools.py`](list_tools.py) | Connects, prints every tool and prompt registered by the server. Minimal shape a client needs. |
| [`recent_releases.py`](recent_releases.py) | Calls `list_vipmp_releases` with a 30-day window, prints dated entries by section. |
| [`find_error_code.py`](find_error_code.py) | Takes a code number on the command line, queries `list_vipmp_error_codes`, prints the match. |

All three follow the same pattern: `stdio_client(...)` + `ClientSession(...)` + one or more `session.call_tool(...)` calls. Copy any of them as a starting point.

## Why these exist

- **Integration with CI/automation** — you can invoke the server from a script to generate release digests, validate request bodies, or export structured data as part of a build pipeline.
- **Learning** — if you're new to MCP, these show the minimal client shape without any Claude-specific complexity.
- **Debugging** — if you're writing a new tool, a quick example script is often faster than installing a fresh Claude Desktop config.
