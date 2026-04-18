"""
Content-aware search and section-based truncation.

Search ranks sitemap entries by (title/tag matches) + (content matches when
content is already cached — opportunistic content scoring). Truncation splits
content on Markdown headings and returns the most query-relevant sections
instead of a blunt character-count cutoff.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .cache import DocsCache
from .logging_config import get_logger
from .sitemap import SitemapEntry

log = get_logger("search")

# Weights for the composite score. Title hits are worth more than tag hits
# because titles are curated. Content hits matter most when multiple query
# terms appear in the same page.
_WEIGHT_TITLE = 4
_WEIGHT_TAG = 2
_WEIGHT_CONTENT = 1

# Per-result section budget in characters — keeps responses readable even
# when many results are requested.
DEFAULT_SECTION_BUDGET = 2500


@dataclass
class ScoredEntry:
    entry: SitemapEntry
    title_score: int = 0
    tag_score: int = 0
    content_score: int = 0
    content: str | None = None  # None if not cached

    @property
    def total(self) -> int:
        return (
            self.title_score * _WEIGHT_TITLE
            + self.tag_score * _WEIGHT_TAG
            + self.content_score * _WEIGHT_CONTENT
        )


@dataclass
class Section:
    """One chunk of a docs page — typically a `## Heading` and its body."""
    heading: str
    level: int  # 1 for #, 2 for ##, etc.
    body: str
    score: int = 0

    def render(self) -> str:
        if self.heading:
            return f"{'#' * self.level} {self.heading}\n\n{self.body}".rstrip()
        return self.body.rstrip()

    @property
    def char_count(self) -> int:
        return len(self.render())


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    """Cheap tokenizer: word characters, lowercased."""
    return re.findall(r"\w+", text.lower())


def score_entry(entry: SitemapEntry, query_tokens: list[str], content: str | None = None) -> ScoredEntry:
    """Compute a composite score for a sitemap entry."""
    title_text = entry["title"].lower()
    tags_text = " ".join(entry["tags"]).lower()

    title_score = sum(1 for t in query_tokens if t in title_text)
    tag_score = sum(1 for t in query_tokens if t in tags_text)

    content_score = 0
    if content:
        content_lower = content.lower()
        # Count term occurrences (not just presence) — pages that repeat a
        # term rank higher.
        for t in query_tokens:
            content_score += content_lower.count(t)

    return ScoredEntry(
        entry=entry,
        title_score=title_score,
        tag_score=tag_score,
        content_score=content_score,
        content=content,
    )


def search(
    sitemap: list[SitemapEntry],
    cache: DocsCache,
    query: str,
    max_results: int = 5,
) -> list[ScoredEntry]:
    """
    Rank sitemap entries by relevance to query.

    Content scoring is opportunistic: pages already in the disk cache
    contribute to the score. Pages not cached still get scored on title/tags
    only, so the search is always fast (zero network on the search itself).
    """
    query_tokens = _tokens(query)
    if not query_tokens:
        return []

    scored: list[ScoredEntry] = []
    for entry in sitemap:
        cached = cache.get(entry["path"])
        content = cached.content if cached else None
        s = score_entry(entry, query_tokens, content)
        if s.total > 0:
            scored.append(s)

    scored.sort(key=lambda s: s.total, reverse=True)
    log.debug(
        "search query=%r matched=%d top_score=%d",
        query,
        len(scored),
        scored[0].total if scored else 0,
    )
    return scored[:max_results]


# ---------------------------------------------------------------------------
# Section splitting + relevance-based truncation
# ---------------------------------------------------------------------------


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


def split_sections(content: str) -> list[Section]:
    """
    Split a cleaned docs page into sections keyed by headings.

    Content above the first heading becomes an "intro" section (heading="",
    level=0). Each subsequent heading starts a new section whose body runs
    until the next heading of equal or higher level.
    """
    sections: list[Section] = []

    # Find all heading positions.
    matches = list(_HEADING_RE.finditer(content))
    if not matches:
        return [Section(heading="", level=0, body=content.strip())]

    # Everything before the first heading.
    preamble = content[: matches[0].start()].strip()
    if preamble:
        sections.append(Section(heading="", level=0, body=preamble))

    for i, match in enumerate(matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        body_start = match.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()
        sections.append(Section(heading=heading, level=level, body=body))

    return sections


def score_sections(sections: list[Section], query_tokens: list[str]) -> list[Section]:
    """Score sections by query term occurrences in heading + body."""
    for section in sections:
        haystack = (section.heading + " " + section.body).lower()
        section.score = sum(haystack.count(t) for t in query_tokens)
    return sections


def _split_paragraphs(body: str) -> list[str]:
    """Split a body of text on blank lines, returning non-empty paragraphs."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", body)]
    return [p for p in paras if p]


def _paragraph_fallback(content: str, query: str | None, max_chars: int) -> str:
    """
    When a page has no meaningful heading structure (Adobe's docs are often
    flat — one h1 and a big body), fall back to paragraph-level relevance.
    """
    paragraphs = _split_paragraphs(content)
    if not paragraphs:
        return content[:max_chars]

    if query:
        query_tokens = _tokens(query)
        scored = [
            (i, para, sum(para.lower().count(t) for t in query_tokens))
            for i, para in enumerate(paragraphs)
        ]
        scored.sort(key=lambda x: (-x[2], x[0]))
    else:
        scored = [(i, para, 0) for i, para in enumerate(paragraphs)]

    chosen: list[tuple[int, str]] = []
    budget = max_chars
    for idx, para, score in scored:
        if query and score == 0 and chosen:
            break
        size = len(para) + 2  # +2 for the "\n\n" separator
        if size > budget and chosen:
            break
        chosen.append((idx, para))
        budget -= size

    chosen.sort(key=lambda x: x[0])
    rendered = "\n\n".join(p for _, p in chosen).strip()
    if len(chosen) < len(paragraphs):
        rendered += (
            f"\n\n[...{len(paragraphs) - len(chosen)} paragraph(s) omitted — "
            f"call get_vipmp_page for the full page...]"
        )
    return rendered


def relevant_sections(
    content: str,
    query: str | None = None,
    max_chars: int = DEFAULT_SECTION_BUDGET,
) -> str:
    """
    Return the most query-relevant parts of a page, stopping once the
    character budget is reached. With no query, returns the opening parts
    in order. Boundaries (section or paragraph) are preserved — we never
    truncate mid-chunk.

    Strategy:
      - If the page has multiple headings, rank and select by section.
      - If the page is flat (0-1 headings, common on Adobe docs), fall
        back to paragraph-level ranking.
    """
    sections = split_sections(content)

    # Flat page → paragraph fallback. One section with a single heading
    # counts as flat for this purpose because section scoring degenerates.
    non_preamble = [s for s in sections if s.heading]
    if len(non_preamble) <= 1:
        return _paragraph_fallback(content, query, max_chars)

    if query:
        query_tokens = _tokens(query)
        sections = score_sections(sections, query_tokens)
        sections_with_idx = list(enumerate(sections))
        sections_with_idx.sort(key=lambda x: (-x[1].score, x[0]))
    else:
        sections_with_idx = list(enumerate(sections))

    chosen: list[tuple[int, Section]] = []
    budget = max_chars
    for idx, section in sections_with_idx:
        if query and section.score == 0 and chosen:
            break
        size = section.char_count + 2
        if size > budget and chosen:
            break
        chosen.append((idx, section))
        budget -= size

    chosen.sort(key=lambda x: x[0])
    rendered = "\n\n".join(s.render() for _, s in chosen).strip()

    if len(chosen) < len(sections):
        rendered += (
            f"\n\n[...{len(sections) - len(chosen)} section(s) omitted — "
            f"call get_vipmp_page for the full page...]"
        )
    return rendered
