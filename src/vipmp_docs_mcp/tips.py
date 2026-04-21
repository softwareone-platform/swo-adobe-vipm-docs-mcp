"""
Reader for the human-authored VIPMP tips file.

The tips file lives at ``content/tips.md`` next to the package. Each H2
heading is a topic (e.g. "Customer lifecycle", "Ordering flow"); each H3
inside a section is an individual tip. The ``get_vipmp_tips`` MCP tool
calls :func:`get_tip_section` to surface SoftwareOne-specific operational
knowledge that Adobe's reference docs don't cover — commercial rules,
gotchas, rules-of-thumb earned from production experience.

Earlier iterations tried to weave this content into walkthrough prompts
automatically; that approach didn't stick because LLMs treat in-prompt
text blocks as ambient context. Exposing the content via a dedicated
tool — which users reach by explicitly asking for "tips" — makes the
supplement content high-salience when it's wanted and invisible when
it's not, which matches the shape of real user intent.

Design notes:

- Matching is case-insensitive and punctuation-tolerant so callers can
  pass "Customer lifecycle" / "customer_lifecycle" / "Customer Lifecycle"
  interchangeably.
- Missing sections return ``None`` rather than raising — callers handle
  "no tips yet for that topic" gracefully.
- TODO-only sections are returned verbatim. We deliberately don't try
  to detect "this is just a stub"; the stub text itself signals to the
  assistant (and the user) that content is still being written.
"""

from __future__ import annotations

import re
from pathlib import Path

from .logging_config import get_logger

log = get_logger("tips")

TIPS_PATH = Path(__file__).parent / "content" / "tips.md"


def _normalise(heading: str) -> str:
    """Collapse variants of a heading to a comparable key."""
    return re.sub(r"[^a-z0-9]+", "", heading.lower())


def load_tips() -> str | None:
    """Return the full tips text, or None if the file is missing."""
    if not TIPS_PATH.exists():
        log.warning("tips file not found at %s", TIPS_PATH)
        return None
    try:
        return TIPS_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("tips file unreadable (%s): %s", TIPS_PATH, exc)
        return None


def get_tip_section(heading: str) -> str | None:
    """
    Return the body of the H2 section whose heading matches ``heading``
    (case-insensitive, punctuation-tolerant), or None if the tips file
    is missing or no such section exists.

    The returned body excludes the heading line itself and stops at the
    next H2 (or EOF). Horizontal rules (``---``) inside a section are
    treated as content and included verbatim.
    """
    text = load_tips()
    if text is None:
        return None

    target = _normalise(heading)
    lines = text.splitlines()

    capture = False
    captured: list[str] = []
    for line in lines:
        if line.startswith("## "):
            # Starting a new H2 — either the one we want, or we've
            # finished capturing the previous match.
            if capture:
                break
            current = _normalise(line[3:])
            if current == target:
                capture = True
            continue
        if capture:
            captured.append(line)

    if not capture and not captured:
        log.debug("no tips section matched %r", heading)
        return None

    # Trim leading/trailing blank lines so callers can slot the body
    # into responses without extra whitespace.
    body = "\n".join(captured).strip("\n")
    return body if body else None


def list_tip_topics() -> list[str]:
    """
    Return the H2 topic headings available in the tips file, in file
    order. Empty list if the file is missing.
    """
    text = load_tips()
    if text is None:
        return []
    topics: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            topics.append(line[3:].strip())
    return topics
