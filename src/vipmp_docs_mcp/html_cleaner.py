"""
Shared HTML → plain-text extraction.

Adobe's docs pages are Gatsby-generated; stripping nav/footer/script and
walking headings + paragraphs + code blocks is enough to yield readable
Markdown-ish output that Claude can consume efficiently.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup, Tag


def extract_text(html: str) -> str:
    """Convert a fetched HTML page into clean Markdown-ish plain text."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove chrome.
    for selector in ("nav", "footer", "script", "style", ".gatsby-highlight", "header"):
        for tag in soup.select(selector):
            tag.decompose()

    # Pick the main content container, falling back to the whole document.
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"content|main|body", re.I))
    )
    target: Tag = main if isinstance(main, Tag) else soup

    lines: list[str] = []
    for element in target.find_all(["h1", "h2", "h3", "h4", "h5", "p", "li", "pre", "code", "th", "td"]):
        text = element.get_text(separator=" ", strip=True)
        if not text:
            continue
        tag = element.name
        if tag == "h1":
            lines.append(f"\n# {text}\n")
        elif tag == "h2":
            lines.append(f"\n## {text}\n")
        elif tag == "h3":
            lines.append(f"\n### {text}\n")
        elif tag in ("h4", "h5"):
            lines.append(f"\n#### {text}\n")
        elif tag == "pre":
            lines.append(f"\n```\n{text}\n```\n")
        elif tag == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)

    content = "\n".join(lines).strip()
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content


# Markers that strongly suggest the fetched HTML is a real docs page
# (vs a login wall, maintenance page, or CDN error page). Used by the
# fetcher's content sanity check.
EXPECTED_CONTENT_MARKERS = (
    "vipmp",
    "VIP Marketplace",
    "adobe",
)


def looks_like_docs_page(html: str) -> bool:
    """Rough check that the fetched HTML is a real Adobe docs page."""
    lower = html.lower()
    return any(marker.lower() in lower for marker in EXPECTED_CONTENT_MARKERS)
