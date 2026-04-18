# Adobe VIP Marketplace Docs MCP Server

A local [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes the [Adobe VIP Marketplace Partner API documentation](https://developer.adobe.com/vipmp/docs/) as searchable tools for Claude Desktop (or any other MCP-aware client).

## What it does

Instead of scrolling through Adobe's docs site to find the right endpoint, you can ask Claude to look it up:

> "How do I create a reseller account?"
> "What are the error codes for Mid-Term Upgrades?"
> "Show me the request headers required for an LGA create call."

Claude calls one of the tools below, the MCP server fetches the relevant page(s) from `developer.adobe.com`, and the content flows into the conversation.

## Tools exposed

| Tool | Description |
|---|---|
| `list_vipmp_docs()` | Returns the full sitemap — all 70+ pages with titles and paths |
| `search_vipmp_docs(query, max_results?)` | Keyword search across titles/tags; fetches and returns content from matching pages (truncated to ~6,000 chars each) |
| `get_vipmp_page(path)` | Fetch full content of a specific page by its path |

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/softwareone-platform/swo-adobe-vipm-docs-mcp.git
cd swo-adobe-vipm-docs-mcp
```

**Recommended — virtual environment:**

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Or install into your system Python:

```bash
pip install -r requirements.txt
```

Requires **Python 3.12+**.

### 2. Register with Claude Desktop

Open `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) and add the server entry inside the `"mcpServers"` object. Replace `<path-to-clone>` with the absolute path to your clone.

```json
{
  "mcpServers": {
    "vipmp-docs": {
      "command": "python",
      "args": ["<path-to-clone>/server.py"],
      "env": {}
    }
  }
}
```

If using a virtual environment, point `command` at the venv's Python so MCP dependencies resolve correctly:

```json
{
  "mcpServers": {
    "vipmp-docs": {
      "command": "<path-to-clone>/.venv/Scripts/python.exe",
      "args": ["<path-to-clone>/server.py"],
      "env": {}
    }
  }
}
```

Restart Claude Desktop after saving the config.

### 3. Verify

In a new Claude Desktop conversation, ask:

> "List all Adobe VIP Marketplace doc pages"

Claude should call `list_vipmp_docs` and return the full sitemap.

## How it works

- **Fetches on demand.** Pages are pulled from `developer.adobe.com` only when a tool is invoked.
- **In-memory cache with 1-hour TTL.** Repeated calls for the same page within an hour are served from memory. Cache is cleared when Claude Desktop restarts — no disk persistence.
- **Text extraction.** HTML is parsed with BeautifulSoup; nav/footer/script elements are stripped; headings, paragraphs, lists, and code blocks are preserved as Markdown-ish plain text.
- **Truncation.** `search_vipmp_docs` truncates each page at ~6,000 characters; use `get_vipmp_page` for the full content of any specific page.

## Maintaining the sitemap

The sitemap is hand-curated inside `server.py` (the `SITEMAP` list) and covers every page listed in the official docs navigation as of March 2026. If Adobe adds new pages, append entries to `SITEMAP` with `path`, `title`, and search `tags`.

## Requirements

- Python 3.12+
- Internet access to `https://developer.adobe.com`

## License

Licensed under the [Apache License, Version 2.0](LICENSE). See the [NOTICE](NOTICE) file for attribution.

Copyright © 2026 SoftwareOne AG.

---

_Adobe, Adobe VIP Marketplace, and related marks are trademarks of Adobe Inc. This project is not affiliated with, endorsed by, or sponsored by Adobe Inc._
