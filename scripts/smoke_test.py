"""
End-to-end smoke test for the MCP server.

Starts `vipmp-docs-mcp` as a subprocess, connects over stdio using the
MCP client SDK, and exercises the main tools + prompts. Catches regressions
that unit tests can't — missing imports, broken FastMCP registration,
transport failures, etc.

Run from the repo root with the venv active:

    python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent
# Use the venv's console script so we pick up the editable install.
if sys.platform == "win32":
    CONSOLE_SCRIPT = REPO_ROOT / ".venv" / "Scripts" / "vipmp-docs-mcp.exe"
else:
    CONSOLE_SCRIPT = REPO_ROOT / ".venv" / "bin" / "vipmp-docs-mcp"


OK = "\x1b[32m✓\x1b[0m"
FAIL = "\x1b[31m✗\x1b[0m"


def ok(msg: str) -> None:
    print(f"  {OK} {msg}")


def fail(msg: str) -> None:
    print(f"  {FAIL} {msg}")


async def main() -> int:
    if not CONSOLE_SCRIPT.exists():
        print(f"{FAIL} Console script not found at {CONSOLE_SCRIPT}")
        print("    Run `pip install -e .` in the venv first.")
        return 1

    print(f"Smoke-testing server at {CONSOLE_SCRIPT}")
    print()

    params = StdioServerParameters(command=str(CONSOLE_SCRIPT), args=[])

    failures = 0

    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
            # --- Handshake --------------------------------------------------
            print("Handshake")
            init = await session.initialize()
            ok(f"server={init.serverInfo.name!r} version={init.serverInfo.version}")

            # --- Discovery --------------------------------------------------
            print("\nDiscovery")
            tools = await session.list_tools()
            prompts = await session.list_prompts()
            ok(f"{len(tools.tools)} tools")
            ok(f"{len(prompts.prompts)} prompts")

            expected_tools = {
                "list_vipmp_docs",
                "search_vipmp_docs",
                "get_vipmp_page",
                "warm_vipmp_cache",
                "refresh_vipmp_sitemap",
                "rebuild_vipmp_index",
                "vipmp_cache_stats",
                "vipmp_cache_clear",
                "list_vipmp_endpoints",
                "list_vipmp_error_codes",
                "get_vipmp_schema",
                "get_vipmp_code_examples",
                "list_vipmp_releases",
                "describe_vipmp_endpoint",
                "validate_vipmp_request",
                "generate_vipmp_request",
                "vipmp_server_info",
            }
            got_tools = {t.name for t in tools.tools}
            missing = expected_tools - got_tools
            extra = got_tools - expected_tools
            if missing:
                fail(f"missing tools: {sorted(missing)}")
                failures += 1
            if extra:
                ok(f"extra tools (new?): {sorted(extra)}")

            expected_prompts = {
                "review_request_body",
                "debug_error_code",
                "draft_order",
                "summarize_recent_changes",
                "check_feature_status",
                "check_3yc_eligibility",
            }
            got_prompts = {p.name for p in prompts.prompts}
            missing_p = expected_prompts - got_prompts
            if missing_p:
                fail(f"missing prompts: {sorted(missing_p)}")
                failures += 1

            # --- Tool: list_vipmp_docs (no network) ------------------------
            print("\nlist_vipmp_docs (no network)")
            r = await session.call_tool("list_vipmp_docs", {})
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "Sitemap" in text and "`/vipmp/docs" in text:
                ok(f"returned sitemap ({len(text)} chars)")
            else:
                fail("sitemap output doesn't contain expected markers")
                failures += 1

            # --- Tool: vipmp_server_info (fast diagnostic) ----------------
            print("\nvipmp_server_info")
            r = await session.call_tool("vipmp_server_info", {})
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            lower = text.lower()
            if "package" in lower and "index" in lower and "cache" in lower:
                ok(f"diagnostic dumped ({len(text)} chars)")
            else:
                fail(f"server_info output unexpected: {text[:300]}")
                failures += 1

            # --- Tool: vipmp_cache_stats ----------------------------------
            print("\nvipmp_cache_stats")
            r = await session.call_tool("vipmp_cache_stats", {})
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "Total entries" in text:
                ok(f"cache stats returned ({len(text)} chars)")
            else:
                fail("cache stats missing expected header")
                failures += 1

            # --- Tool: search_vipmp_docs (no-match path, no network) ------
            print("\nsearch_vipmp_docs (no-match)")
            r = await session.call_tool(
                "search_vipmp_docs",
                {"query": "xyzneverexistskeyword", "max_results": 3},
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "No pages matched" in text:
                ok("no-match path returns helpful message")
            else:
                fail(f"no-match path unexpected output: {text[:200]}")
                failures += 1

            # --- Tool: search_vipmp_docs (real query, network) ------------
            print("\nsearch_vipmp_docs ('oauth token')")
            r = await session.call_tool(
                "search_vipmp_docs",
                {"query": "oauth token", "max_results": 2},
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "Search results for" in text and "**Path:**" in text:
                ok(f"search returned results ({len(text)} chars)")
            else:
                fail(f"search output malformed: {text[:300]}")
                failures += 1

            # --- Tool: get_vipmp_page (network) ---------------------------
            print("\nget_vipmp_page('/vipmp/docs/authentication')")
            r = await session.call_tool(
                "get_vipmp_page", {"path": "/vipmp/docs/authentication"}
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "Source" in text and "authentication" in text.lower():
                ok(f"page fetched ({len(text)} chars)")
            else:
                fail(f"page fetch unexpected output: {text[:300]}")
                failures += 1

            # --- Tool: list_vipmp_endpoints (should use index, be fast) ---
            print("\nlist_vipmp_endpoints (index-backed)")
            import time as _time

            t0 = _time.perf_counter()
            r = await session.call_tool("list_vipmp_endpoints", {})
            elapsed_ms = (_time.perf_counter() - t0) * 1000
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "Endpoints" in text and "pre-built index" in text:
                ok(f"returned endpoints in {elapsed_ms:.0f}ms ({len(text)} chars, index-backed)")
            elif "Endpoints" in text:
                fail(f"endpoints returned but NOT index-backed ({elapsed_ms:.0f}ms — live extraction)")
                failures += 1
            else:
                fail(f"unexpected output: {text[:300]}")
                failures += 1

            # --- Tool: get_vipmp_schema (network) -------------------------
            print("\nget_vipmp_schema('customer')")
            r = await session.call_tool(
                "get_vipmp_schema", {"resource_name": "customer"}
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "Customer" in text and "| Field |" in text:
                ok(f"customer schema returned ({len(text)} chars)")
            else:
                fail(f"schema output unexpected: {text[:300]}")
                failures += 1

            # --- Tool: get_vipmp_code_examples (network) ------------------
            print("\nget_vipmp_code_examples('/vipmp/docs/customer-account/create-customer-account', language='json')")
            r = await session.call_tool(
                "get_vipmp_code_examples",
                {
                    "docs_path": "/vipmp/docs/customer-account/create-customer-account",
                    "language": "json",
                },
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "```json" in text and ("Request" in text or "Response" in text):
                ok(f"code examples returned ({len(text)} chars)")
            else:
                fail(f"code examples output unexpected: {text[:300]}")
                failures += 1

            # --- Tool: list_vipmp_releases (the headline feature) ---------
            print("\nlist_vipmp_releases(since='2026-01-01')")
            t0 = _time.perf_counter()
            r = await session.call_tool(
                "list_vipmp_releases",
                {"since": "2026-01-01"},
            )
            elapsed_ms = (_time.perf_counter() - t0) * 1000
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "VIPMP releases" in text and "2026-" in text and "API changes" in text:
                ok(f"returned releases in {elapsed_ms:.0f}ms ({len(text)} chars)")
            else:
                fail(f"releases output unexpected: {text[:300]}")
                failures += 1

            print("\nlist_vipmp_releases(section='sandbox')")
            r = await session.call_tool(
                "list_vipmp_releases",
                {"section": "sandbox"},
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "Sandbox" in text or "sandbox" in text.lower():
                ok(f"sandbox filter returns sandbox entries ({len(text)} chars)")
            else:
                fail(f"sandbox filter didn't return sandbox content: {text[:300]}")
                failures += 1

            # --- Tool: describe_vipmp_endpoint ----------------------------
            print("\ndescribe_vipmp_endpoint(method='POST', path='/v3/customers')")
            r = await session.call_tool(
                "describe_vipmp_endpoint",
                {"method": "POST", "path": "/v3/customers"},
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "POST" in text and "Request schema" in text and "/v3/customers" in text:
                ok(f"endpoint described ({len(text)} chars)")
            else:
                fail(f"describe_vipmp_endpoint output unexpected: {text[:300]}")
                failures += 1

            # --- Tool: validate_vipmp_request -----------------------------
            print("\nvalidate_vipmp_request(endpoint='POST /v3/customers', body=bad)")
            bad_body = '{"externalReferenceId": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}'
            r = await session.call_tool(
                "validate_vipmp_request",
                {"endpoint": "POST /v3/customers", "body_json": bad_body},
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "Invalid" in text and "too long" in text:
                ok(f"validator correctly flagged over-long field ({len(text)} chars)")
            else:
                fail(f"validator output unexpected: {text[:300]}")
                failures += 1

            # --- Tool: generate_vipmp_request -----------------------------
            print("\ngenerate_vipmp_request(endpoint='POST /v3/customers', language='python')")
            r = await session.call_tool(
                "generate_vipmp_request",
                {"endpoint": "POST /v3/customers", "language": "python"},
            )
            text = "".join(c.text for c in r.content if hasattr(c, "text"))
            if "import httpx" in text and "python" in text.lower():
                ok(f"python snippet generated ({len(text)} chars)")
            else:
                fail(f"codegen output unexpected: {text[:300]}")
                failures += 1

            # --- Prompt: debug_error_code ---------------------------------
            print("\nprompt debug_error_code(code='1117')")
            p = await session.get_prompt("debug_error_code", {"code": "1117"})
            msg = "".join(
                m.content.text for m in p.messages if hasattr(m.content, "text")
            )
            if "1117" in msg and "list_vipmp_error_codes" in msg:
                ok(f"prompt renders ({len(msg)} chars, references the right tool)")
            else:
                fail(f"prompt output unexpected: {msg[:300]}")
                failures += 1

            # --- Prompt: summarize_recent_changes (default + with area) ---
            print("\nprompt summarize_recent_changes() — default since")
            p = await session.get_prompt("summarize_recent_changes", {})
            msg = "".join(
                m.content.text for m in p.messages if hasattr(m.content, "text")
            )
            # Check no step-number gap (regression we just fixed) and references
            # the right tool.
            has_gap = "3." in msg and "4." in msg and "5." in msg and "6." in msg
            if "list_vipmp_releases" in msg and has_gap:
                ok(f"prompt renders with sequential steps ({len(msg)} chars)")
            else:
                fail(f"prompt missing steps or wrong tool: {msg[:300]}")
                failures += 1

            print("\nprompt check_feature_status(feature='Early Renewals')")
            p = await session.get_prompt(
                "check_feature_status", {"feature": "Early Renewals"}
            )
            msg = "".join(
                m.content.text for m in p.messages if hasattr(m.content, "text")
            )
            if "Early Renewals" in msg and "list_vipmp_releases" in msg:
                ok(f"prompt renders ({len(msg)} chars)")
            else:
                fail(f"prompt output unexpected: {msg[:300]}")
                failures += 1

    print()
    if failures:
        print(f"{FAIL} {failures} check(s) failed")
        return 1
    print(f"{OK} All smoke checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
