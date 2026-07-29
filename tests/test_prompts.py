"""
Tests for the prompt module.

Scope kept narrow: prompt bodies are essentially copy, and full-text
assertions would just echo the fixtures. What's worth locking in is
that each walkthrough prompt actually renders (no unresolved refs
after the supplement→tips refactor) and that the Adobe-sole-source
promise and the tips signpost — the two invariants that justify
keeping walkthroughs separate from tips — are present.
"""

from __future__ import annotations

from typing import ClassVar

from mcp.server.mcpserver import MCPServer

from vipmp_docs_mcp.prompts import register_prompts

# Marker used in place of a body when a prompt raises while rendering, so the
# failure surfaces with its cause instead of the prompt simply going missing.
RENDER_FAILED = "<render failed:"


def _rendered_prompts() -> dict[str, str]:
    """Register all prompts on a throwaway MCPServer instance and return
    {prompt_name: rendered_body} for every walkthrough (no-arg prompts
    only — the parameterised ones are exercised by their callers).

    A prompt that raises while rendering is recorded with its traceback as
    the body rather than dropped, so the assertions below fail with the
    underlying error instead of a bare "didn't render"."""
    mcp = MCPServer("test")
    register_prompts(mcp)

    # MCPServer exposes prompts via a private registry; we pull the
    # callables out, call each no-arg prompt, and collect the string.
    # The no-arg prompts are the six walkthroughs; the router takes
    # optional args which we can pass defaults to.
    import asyncio

    out: dict[str, str] = {}
    prompts_list = asyncio.run(mcp.list_prompts())
    for p in prompts_list:
        # Skip parameterised prompts (they need inputs we'd have to invent).
        if p.arguments and any(a.required for a in p.arguments):
            continue
        try:
            result = asyncio.run(mcp.get_prompt(p.name, arguments={}))
        except Exception as exc:
            out[p.name] = f"{RENDER_FAILED} {type(exc).__name__}: {exc}>"
            continue
        out[p.name] = "\n".join(
            m.content.text for m in result.messages if hasattr(m.content, "text")
        )
    return out


class TestWalkthroughInvariants:
    """
    The six learn_* walkthroughs all promise:
      1. Ground claims in Adobe's live docs only (sole-source).
      2. Point at the tips tool at the end (signpost).

    If either invariant drops off any walkthrough, learners either
    lose the citability guarantee (claim 1) or fail to discover the
    tips surface (claim 2).
    """

    WALKTHROUGH_NAMES: ClassVar[set[str]] = {
        "learn_customer_lifecycle",
        "learn_ordering_flow",
        "learn_3yc",
        "learn_subscriptions_and_renewals",
        "learn_returns_and_refunds",
        "learn_auth_and_sandbox",
    }

    def test_all_walkthroughs_render(self):
        rendered = _rendered_prompts()
        missing = self.WALKTHROUGH_NAMES - rendered.keys()
        assert not missing, f"these walkthroughs didn't render: {missing}"
        failed = {
            name: rendered[name]
            for name in self.WALKTHROUGH_NAMES
            if rendered[name].startswith(RENDER_FAILED)
        }
        assert not failed, f"these walkthroughs raised while rendering: {failed}"

    def test_every_walkthrough_promises_adobe_sole_source(self):
        rendered = _rendered_prompts()
        for name in self.WALKTHROUGH_NAMES:
            body = rendered[name]
            assert "Ground every claim" in body, (
                f"{name} is missing the Adobe-sole-source directive"
            )

    def test_every_walkthrough_signposts_get_vipmp_tips(self):
        rendered = _rendered_prompts()
        for name in self.WALKTHROUGH_NAMES:
            body = rendered[name]
            assert "tips" in body.lower(), f"{name} is missing any mention of tips"
            # Each signpost uses the phrase "ask me for '<topic> tips'"
            # — locks in the specific framing so a refactor can't
            # silently drop it.
            assert "ask me for" in body.lower(), (
                f"{name} is missing the 'ask me for <topic> tips' signpost"
            )

    def test_router_mentions_tips_surface(self):
        """The onboarding router should hint that the tips surface exists,
        so new learners know about it before they pick a walkthrough."""
        rendered = _rendered_prompts()
        body = rendered.get("start_vipmp_learning", "")
        assert body, "start_vipmp_learning didn't render"
        assert "get_vipmp_tips" in body
