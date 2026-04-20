"""
Tests for the training-supplement section loader.

The supplement file ships with the package (``content/training-supplement.md``).
Every test that exercises file I/O redirects ``SUPPLEMENT_PATH`` via
monkeypatch to keep the real shipped file out of the test's way — the
stub content changes over time and we don't want tests to regress when
a human edits it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vipmp_docs_mcp import supplement

SAMPLE = """# Training Supplement

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
def isolate_supplement(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point SUPPLEMENT_PATH at a temp file for every test."""
    path = tmp_path / "training-supplement.md"
    monkeypatch.setattr(supplement, "SUPPLEMENT_PATH", path)
    return path


class TestLoadSupplement:
    def test_missing_file_returns_none(self, isolate_supplement: Path):
        assert supplement.load_supplement() is None

    def test_present_file_returns_full_text(self, isolate_supplement: Path):
        isolate_supplement.write_text(SAMPLE, encoding="utf-8")
        out = supplement.load_supplement()
        assert out is not None
        assert "Ordering content here." in out


class TestGetSection:
    def test_missing_file_returns_none(self):
        # SUPPLEMENT_PATH was patched to a non-existent temp path.
        assert supplement.get_section("Customer lifecycle") is None

    def test_exact_heading_match(self, isolate_supplement: Path):
        isolate_supplement.write_text(SAMPLE, encoding="utf-8")
        body = supplement.get_section("Customer lifecycle")
        assert body is not None
        assert body.startswith("This is the customer lifecycle body.")
        assert "A bullet" in body
        # Must NOT bleed into the next section.
        assert "Ordering content here." not in body

    def test_case_insensitive_match(self, isolate_supplement: Path):
        isolate_supplement.write_text(SAMPLE, encoding="utf-8")
        assert supplement.get_section("customer lifecycle") is not None
        assert supplement.get_section("CUSTOMER LIFECYCLE") is not None

    def test_punctuation_tolerant(self, isolate_supplement: Path):
        """Parens and ampersands in headings shouldn't break lookup."""
        isolate_supplement.write_text(SAMPLE, encoding="utf-8")
        # Heading in file: "3YC (3-Year Commit)"; callers might pass
        # "3YC", "3yc-3-year-commit", or the full string.
        body = supplement.get_section("3YC (3-Year Commit)")
        assert body is not None
        assert "3YC content" in body

    def test_unknown_heading_returns_none(self, isolate_supplement: Path):
        isolate_supplement.write_text(SAMPLE, encoding="utf-8")
        assert supplement.get_section("Nonexistent topic") is None

    def test_empty_section_returns_none(self, isolate_supplement: Path):
        """A section header with no body below it returns None, not ''."""
        isolate_supplement.write_text(
            "# root\n\n## Empty section\n\n## Next\n\nbody",
            encoding="utf-8",
        )
        assert supplement.get_section("Empty section") is None
        assert supplement.get_section("Next") is not None

    def test_horizontal_rule_does_not_terminate_section(
        self, isolate_supplement: Path
    ):
        """`---` inside a section body should be kept verbatim."""
        isolate_supplement.write_text(SAMPLE, encoding="utf-8")
        body = supplement.get_section("Auth and sandbox")
        assert body is not None
        assert "Auth body after a horizontal rule" in body

    def test_section_at_end_of_file(self, isolate_supplement: Path):
        """The last H2 in the file has no following H2 to bound it."""
        isolate_supplement.write_text(SAMPLE, encoding="utf-8")
        body = supplement.get_section("Auth and sandbox")
        assert body is not None
        assert body.endswith("don't break parsing.")
