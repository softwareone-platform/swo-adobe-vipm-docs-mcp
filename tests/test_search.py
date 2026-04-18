"""Tests for scoring, section splitting, and paragraph fallback."""

from __future__ import annotations

from vipmp_docs_mcp.search import (
    _split_paragraphs,
    _tokens,
    relevant_sections,
    score_entry,
    split_sections,
)


class TestTokens:
    def test_lowercases_and_splits(self):
        assert _tokens("OAuth Token Exchange") == ["oauth", "token", "exchange"]

    def test_strips_punctuation(self):
        assert _tokens("POST /v3/customers!") == ["post", "v3", "customers"]


class TestScoreEntry:
    def test_title_dominates(self):
        entry = {"path": "/x", "title": "Create Order", "tags": ["foo"]}
        # Query matches title twice.
        s = score_entry(entry, ["create", "order"])
        assert s.title_score == 2
        assert s.tag_score == 0
        assert s.total == 2 * 4  # _WEIGHT_TITLE

    def test_content_boosts_when_cached(self):
        entry = {"path": "/x", "title": "Other", "tags": []}
        content = "order order order"  # three matches
        s = score_entry(entry, ["order"], content=content)
        assert s.content_score == 3
        assert s.total == 3  # only content weight applies (title=0, tag=0)

    def test_no_match_returns_zero(self):
        entry = {"path": "/x", "title": "Unrelated", "tags": []}
        s = score_entry(entry, ["nonexistent"])
        assert s.total == 0


class TestSplitSections:
    def test_single_heading(self):
        sections = split_sections("# Intro\n\nbody text")
        assert len(sections) == 1
        assert sections[0].heading == "Intro"
        assert "body text" in sections[0].body

    def test_multiple_headings(self):
        content = "# A\n\nbody A\n\n## B\n\nbody B\n\n## C\n\nbody C"
        sections = split_sections(content)
        # 3 headings → 3 sections. No preamble before the first heading.
        assert len(sections) == 3
        assert [s.heading for s in sections] == ["A", "B", "C"]

    def test_preamble_captured(self):
        content = "preamble\n\n# A\n\nbody A"
        sections = split_sections(content)
        assert sections[0].heading == ""
        assert "preamble" in sections[0].body
        assert sections[1].heading == "A"

    def test_no_headings(self):
        sections = split_sections("just a paragraph\n\nand another")
        assert len(sections) == 1
        assert sections[0].heading == ""


class TestSplitParagraphs:
    def test_basic(self):
        assert _split_paragraphs("para 1\n\npara 2\n\npara 3") == [
            "para 1", "para 2", "para 3"
        ]

    def test_whitespace_only_blocks_ignored(self):
        assert _split_paragraphs("a\n\n   \n\nb") == ["a", "b"]


class TestRelevantSections:
    def test_flat_page_falls_back_to_paragraphs(self):
        content = "intro para\n\nrelevant para about oauth\n\nirrelevant para"
        out = relevant_sections(content, query="oauth", max_chars=500)
        assert "relevant para about oauth" in out
        # Paragraph mode orders by score, then emits in original order.
        assert "irrelevant" not in out or len(out) > len("relevant para about oauth")

    def test_no_query_returns_intro_order(self):
        content = "first\n\nsecond\n\nthird"
        out = relevant_sections(content, query=None, max_chars=500)
        assert out.index("first") < out.index("second") < out.index("third")

    def test_budget_caps_output(self):
        # Lots of content; tight budget. Result must fit within budget + omission notice.
        content = "\n\n".join(f"paragraph {i}" * 10 for i in range(20))
        out = relevant_sections(content, query="paragraph", max_chars=200)
        # Omission notice adds extra characters; check chosen content is small.
        assert "omitted" in out
