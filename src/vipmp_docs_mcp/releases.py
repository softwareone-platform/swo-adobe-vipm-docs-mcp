"""
Structured parser for Adobe VIPMP release notes.

Release notes matter more to developers than anything else on the docs
site — they answer "has X shipped?", "what changed this month?", "is Y
still upcoming?". We parse them into dated entries keyed by section
(API changes / Sandbox / Upcoming) so tools can filter by "since <date>"
or by section, and so Claude can reason about timing without re-reading
the whole page.

Structure of Adobe's `/vipmp/docs/release-notes` page:

    <h1>Release notes</h1>
    <h2>API changes</h2>
      <h3>April 09, 2026</h3>
        <h4>Feature title</h4>
          <p>body</p>
          <ul>...</ul>
        <h4>Another feature under same release</h4>
          ...
      <h3>March 30, 2026</h3>
        ...
      <h3>Earlier releases from 2024</h3>  ← catch-all, no date
    <h2>Sandbox changes</h2>
      <h3>January 08, 2026</h3>
      <h3>Earlier releases</h3>  ← catch-all

The `/vipmp/docs/release-notes/upcoming-releases` page is currently a
stub ("This topic will be updated soon.") — we capture it as a single
entry with section="upcoming" so callers still get an answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from .logging_config import get_logger

log = get_logger("releases")


RELEASE_NOTES_PATH = "/vipmp/docs/release-notes"
UPCOMING_RELEASES_PATH = "/vipmp/docs/release-notes/upcoming-releases"

# Adobe uses "Month DD, YYYY" (e.g. "April 09, 2026") consistently.
_DATE_FORMATS = ("%B %d, %Y", "%b %d, %Y")


SECTION_API_CHANGES = "api_changes"
SECTION_SANDBOX = "sandbox"
SECTION_UPCOMING = "upcoming"
SECTION_EARLIER = "earlier"


@dataclass
class ReleaseChange:
    """One feature or change within a release (one h4 + its body)."""

    title: str
    body: str  # Paragraphs + lists as Markdown-ish text.

    def to_dict(self) -> dict:
        return {"title": self.title, "body": self.body}


@dataclass
class ReleaseEntry:
    """One dated release with its list of changes."""

    date: str | None  # ISO date "YYYY-MM-DD", or None for catch-all buckets
    raw_date: str  # Original heading text, e.g. "April 09, 2026"
    section: str  # One of SECTION_* constants
    changes: list[ReleaseChange] = field(default_factory=list)
    docs_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "raw_date": self.raw_date,
            "section": self.section,
            "changes": [c.to_dict() for c in self.changes],
            "docs_path": self.docs_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ReleaseEntry:
        return cls(
            date=data.get("date"),
            raw_date=data.get("raw_date", ""),
            section=data.get("section", SECTION_API_CHANGES),
            changes=[ReleaseChange(**c) for c in data.get("changes", [])],
            docs_path=data.get("docs_path"),
        )


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_date(text: str) -> str | None:
    """Try to parse "Month DD, YYYY" into ISO format. Returns None on failure."""
    stripped = text.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(stripped, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _render_body(elements: list[Tag]) -> str:
    """Render a sequence of block elements as Markdown-ish text."""
    lines: list[str] = []
    for el in elements:
        name = el.name
        text = el.get_text(separator=" ", strip=True)
        if not text:
            continue
        if name == "p":
            lines.append(text)
        elif name in ("ul", "ol"):
            for li in el.find_all("li", recursive=False):
                li_text = li.get_text(separator=" ", strip=True)
                if li_text:
                    lines.append(f"- {li_text}")
        elif name == "li":
            lines.append(f"- {text}")
        elif re.fullmatch(r"h[5-6]", name or ""):
            lines.append(f"**{text}**")
        elif name == "pre":
            lines.append(f"```\n{text}\n```")
        else:
            lines.append(text)
    return "\n\n".join(lines).strip()


def _siblings_until(start: Tag, stop_names: set[str]) -> list[Tag]:
    """Collect siblings after `start` until an element with a name in stop_names."""
    out: list[Tag] = []
    for sib in start.find_next_siblings():
        if isinstance(sib, Tag) and sib.name in stop_names:
            break
        if isinstance(sib, Tag):
            out.append(sib)
    return out


def _parse_section(h2: Tag, section: str, docs_path: str) -> list[ReleaseEntry]:
    """
    Walk h3 → h4 within one section (bounded by the next h2 or document end).

    Each h3 is a release date (or catch-all). Within each h3, each h4 is
    a change; the body of a change is everything between its h4 and the
    next h4/h3/h2.
    """
    entries: list[ReleaseEntry] = []

    # Find all h3s that belong to this h2 (before the next h2).
    h3s: list[Tag] = []
    for sib in h2.find_next_siblings():
        if isinstance(sib, Tag) and sib.name == "h2":
            break
        if isinstance(sib, Tag) and sib.name == "h3":
            h3s.append(sib)

    for h3 in h3s:
        raw = h3.get_text(strip=True)
        iso = _parse_date(raw)
        resolved_section = section if iso else SECTION_EARLIER

        entry = ReleaseEntry(
            date=iso,
            raw_date=raw,
            section=resolved_section,
            docs_path=docs_path,
        )

        # Collect h4s belonging to this h3 (until next h3/h2).
        for sib in h3.find_next_siblings():
            if isinstance(sib, Tag) and sib.name in {"h2", "h3"}:
                break
            if isinstance(sib, Tag) and sib.name == "h4":
                title = sib.get_text(strip=True)
                body_elements = _siblings_until(
                    sib, stop_names={"h2", "h3", "h4"}
                )
                body = _render_body(body_elements)
                entry.changes.append(ReleaseChange(title=title, body=body))

        # If no h4s found (e.g. "Earlier releases from 2024"), fall back
        # to whatever paragraphs sit under the h3 directly.
        if not entry.changes:
            body_elements = _siblings_until(
                h3, stop_names={"h2", "h3"}
            )
            body = _render_body(body_elements)
            if body:
                entry.changes.append(ReleaseChange(title=raw, body=body))

        entries.append(entry)

    return entries


def parse_recent_releases(html: str, docs_path: str = RELEASE_NOTES_PATH) -> list[ReleaseEntry]:
    """Parse the /vipmp/docs/release-notes page into structured entries."""
    soup = BeautifulSoup(html, "html.parser")
    for sel in ("nav", "footer", "script", "style", "header"):
        for t in soup.select(sel):
            t.decompose()
    main = soup.find("main") or soup.find("article") or soup

    entries: list[ReleaseEntry] = []
    for h2 in main.find_all("h2"):
        heading = h2.get_text(strip=True).lower()
        if "api changes" in heading or "api change" in heading:
            section = SECTION_API_CHANGES
        elif "sandbox" in heading:
            section = SECTION_SANDBOX
        else:
            # Unknown h2 — skip rather than misclassify.
            log.debug("skipping unknown h2 on release notes: %r", heading)
            continue
        entries.extend(_parse_section(h2, section, docs_path))

    log.info("parsed %d release entries from %s", len(entries), docs_path)
    return entries


def parse_upcoming_releases(
    html: str, docs_path: str = UPCOMING_RELEASES_PATH
) -> list[ReleaseEntry]:
    """
    Parse the upcoming-releases page. Currently a stub on Adobe's side;
    we return a single entry containing whatever body text is present
    so callers still get a useful answer.
    """
    soup = BeautifulSoup(html, "html.parser")
    for sel in ("nav", "footer", "script", "style", "header"):
        for t in soup.select(sel):
            t.decompose()
    main = soup.find("main") or soup.find("article") or soup

    # Collect all paragraphs + lists under the page.
    elements = list(main.find_all(["p", "ul", "ol", "h2", "h3", "h4"]))
    body = _render_body(elements)

    if not body:
        return []

    # Upcoming entries don't have dates — we synthesise one bucket.
    return [
        ReleaseEntry(
            date=None,
            raw_date="Upcoming",
            section=SECTION_UPCOMING,
            changes=[ReleaseChange(title="Upcoming changes", body=body)],
            docs_path=docs_path,
        )
    ]


# ---------------------------------------------------------------------------
# Filtering / rendering helpers
# ---------------------------------------------------------------------------


def filter_since(
    entries: list[ReleaseEntry], since: str
) -> list[ReleaseEntry]:
    """
    Keep only entries whose date is >= `since` (ISO "YYYY-MM-DD").

    Entries without a date (catch-all "Earlier releases" buckets) are
    dropped when a `since` filter is applied — callers looking for "what
    changed since X" don't want the undated catch-all.
    """
    try:
        since_dt = datetime.strptime(since, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(
            f"`since` must be ISO date 'YYYY-MM-DD', got {since!r}"
        ) from exc

    out: list[ReleaseEntry] = []
    for e in entries:
        if not e.date:
            continue
        try:
            entry_dt = datetime.strptime(e.date, "%Y-%m-%d").date()
        except ValueError:
            continue
        if entry_dt >= since_dt:
            out.append(e)
    return out


def filter_section(
    entries: list[ReleaseEntry], section: str
) -> list[ReleaseEntry]:
    """Keep entries whose section matches."""
    return [e for e in entries if e.section == section]
