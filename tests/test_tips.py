"""
Tests for the VIPMP tips loader.

The tips file ships with the package (``content/tips.md``). Every test
that exercises file I/O redirects ``TIPS_PATH`` via monkeypatch to keep
the real shipped file out of the test's way — the stub content changes
over time and we don't want tests to regress when a human edits it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vipmp_docs_mcp import tips

SAMPLE = """# VIPMP Tips

Intro blurb that should never be returned as a section.

## Customer lifecycle

This is the customer lifecycle body.

- A bullet
- Another

## Ordering flow

Ordering content here.

## 3YC (3-Year Commit)

3YC content with (parens) and punctuation.

---

## Auth and sandbox

Auth body after a horizontal rule — make sure rules don't break parsing.
"""


@pytest.fixture(autouse=True)
def isolate_tips(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point TIPS_PATH at a temp file for every test."""
    path = tmp_path / "tips.md"
    monkeypatch.setattr(tips, "TIPS_PATH", path)
    return path


class TestLoadTips:
    def test_missing_file_returns_none(self, isolate_tips: Path):
        assert tips.load_tips() is None

    def test_present_file_returns_full_text(self, isolate_tips: Path):
        isolate_tips.write_text(SAMPLE, encoding="utf-8")
        out = tips.load_tips()
        assert out is not None
        assert "Ordering content here." in out


class TestGetTipSection:
    def test_missing_file_returns_none(self):
        # TIPS_PATH was patched to a non-existent temp path.
        assert tips.get_tip_section("Customer lifecycle") is None

    def test_exact_heading_match(self, isolate_tips: Path):
        isolate_tips.write_text(SAMPLE, encoding="utf-8")
        body = tips.get_tip_section("Customer lifecycle")
        assert body is not None
        assert body.startswith("This is the customer lifecycle body.")
        assert "A bullet" in body
        # Must NOT bleed into the next section.
        assert "Ordering content here." not in body

    def test_case_insensitive_match(self, isolate_tips: Path):
        isolate_tips.write_text(SAMPLE, encoding="utf-8")
        assert tips.get_tip_section("customer lifecycle") is not None
        assert tips.get_tip_section("CUSTOMER LIFECYCLE") is not None

    def test_punctuation_tolerant(self, isolate_tips: Path):
        """Parens and ampersands in headings shouldn't break lookup."""
        isolate_tips.write_text(SAMPLE, encoding="utf-8")
        # Heading in file: "3YC (3-Year Commit)"; callers might pass
        # "3YC", "3yc-3-year-commit", or the full string.
        body = tips.get_tip_section("3YC (3-Year Commit)")
        assert body is not None
        assert "3YC content" in body

    def test_unknown_heading_returns_none(self, isolate_tips: Path):
        isolate_tips.write_text(SAMPLE, encoding="utf-8")
        assert tips.get_tip_section("Nonexistent topic") is None

    def test_empty_section_returns_none(self, isolate_tips: Path):
        """A section header with no body below it returns None, not ''."""
        isolate_tips.write_text(
            "# root\n\n## Empty section\n\n## Next\n\nbody",
            encoding="utf-8",
        )
        assert tips.get_tip_section("Empty section") is None
        assert tips.get_tip_section("Next") is not None

    def test_horizontal_rule_does_not_terminate_section(
        self, isolate_tips: Path
    ):
        """`---` inside a section body should be kept verbatim."""
        isolate_tips.write_text(SAMPLE, encoding="utf-8")
        body = tips.get_tip_section("Auth and sandbox")
        assert body is not None
        assert "Auth body after a horizontal rule" in body

    def test_section_at_end_of_file(self, isolate_tips: Path):
        """The last H2 in the file has no following H2 to bound it."""
        isolate_tips.write_text(SAMPLE, encoding="utf-8")
        body = tips.get_tip_section("Auth and sandbox")
        assert body is not None
        assert body.endswith("don't break parsing.")


class TestListTipTopics:
    def test_missing_file_returns_empty(self):
        assert tips.list_tip_topics() == []

    def test_returns_h2_headings_in_order(self, isolate_tips: Path):
        isolate_tips.write_text(SAMPLE, encoding="utf-8")
        topics = tips.list_tip_topics()
        assert topics == [
            "Customer lifecycle",
            "Ordering flow",
            "3YC (3-Year Commit)",
            "Auth and sandbox",
        ]

    def test_ignores_h1_and_h3(self, isolate_tips: Path):
        isolate_tips.write_text(
            "# H1 should be ignored\n\n"
            "## Topic A\n\n### H3 should be ignored\n\n"
            "## Topic B\n",
            encoding="utf-8",
        )
        assert tips.list_tip_topics() == ["Topic A", "Topic B"]
