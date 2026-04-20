"""
Reader for the human-authored training supplement.

The supplement lives at ``content/training-supplement.md`` next to the
package. Each H2 heading corresponds to one ``learn_*`` prompt; this
module extracts the section matching a given heading and hands it back
for interpolation into the prompt template.

Design notes:

- Matching is case-insensitive and whitespace-tolerant so prompt
  authors can pass "Customer lifecycle" / "customer_lifecycle" /
  "Customer Lifecycle" interchangeably.
- Missing sections return ``None`` rather than raising — prompts
  handle "no supplement yet" gracefully (fall back to Adobe's docs).
- TODO-only sections (the initial stubs) are returned verbatim.
  We deliberately don't try to detect "this is just a stub" and
  suppress it; the stub text itself is shaped so the assistant can
  recognise and communicate that more content is coming.
"""

from __future__ import annotations

import re
from pathlib import Path

from .logging_config import get_logger

log = get_logger("supplement")

SUPPLEMENT_PATH = Path(__file__).parent / "content" / "training-supplement.md"


def _normalise(heading: str) -> str:
    """Collapse variants of a heading to a comparable key."""
    return re.sub(r"[^a-z0-9]+", "", heading.lower())


def load_supplement() -> str | None:
    """Return the full supplement text, or None if the file is missing."""
    if not SUPPLEMENT_PATH.exists():
        log.warning("supplement file not found at %s", SUPPLEMENT_PATH)
        return None
    try:
        return SUPPLEMENT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        log.warning("supplement file unreadable (%s): %s", SUPPLEMENT_PATH, exc)
        return None


def get_section(heading: str) -> str | None:
    """
    Return the body of the H2 section whose heading matches ``heading``
    (case-insensitive, punctuation-tolerant), or None if the supplement
    file is missing or no such section exists.

    The returned body excludes the heading line itself and stops at the
    next H2 (or EOF). Horizontal rules (---) between sections are
    treated as content and included verbatim; downstream prompts strip
    them if needed.
    """
    text = load_supplement()
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
        log.debug("no supplement section matched %r", heading)
        return None

    # Trim leading/trailing blank lines so callers can slot the body
    # into prompts without extra whitespace.
    body = "\n".join(captured).strip("\n")
    return body if body else None
