"""
Tests for the prompt module.

Scope kept narrow: the prompt bodies themselves are essentially copy,
and unit-testing their full string output would just be testing the
test fixtures. We test the _supplement_block helper — the one piece
of real logic that sits in prompts.py — across its populated and
empty branches.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from vipmp_docs_mcp import prompts, supplement


@pytest.fixture
def supplement_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    path = tmp_path / "training-supplement.md"
    monkeypatch.setattr(supplement, "SUPPLEMENT_PATH", path)
    return path


class TestSupplementBlock:
    def test_populated_section_renders_content_and_separator(
        self, supplement_file: Path
    ):
        supplement_file.write_text(
            "## Customer lifecycle\n\nReal SWO content here.\n",
            encoding="utf-8",
        )
        out = prompts._supplement_block("Customer lifecycle")
        assert "SWO training supplement" in out
        assert "Customer lifecycle" in out
        assert "Real SWO content here." in out
        # Separator so the LLM can see where supplement ends.
        assert "---" in out

    def test_h3_subheadings_become_topic_checklist(self, supplement_file: Path):
        """H3 subsections in the supplement should surface as a named
        checklist below the content. The LLM ignores supplement prose
        above the teaching flow but covers named items from a
        bulleted list reliably — that's the whole reason this extraction
        exists. Lock it in so a refactor can't strip it silently."""
        supplement_file.write_text(
            "## Customer lifecycle\n\n"
            "### `globalSalesEnabled` — cross-region\n\nbullets\n\n"
            "### Deployment locations gotcha\n\nmore bullets\n",
            encoding="utf-8",
        )
        out = prompts._supplement_block("Customer lifecycle")
        assert "Topics from the supplement" in out
        assert "weave" in out.lower()
        # Both H3 names surface as checklist items.
        assert "`globalSalesEnabled` — cross-region" in out
        assert "Deployment locations gotcha" in out

    def test_no_h3_subheadings_skips_checklist(self, supplement_file: Path):
        """If the supplement section has no H3s (e.g. a short intro-only
        stub), we render the content plainly — no empty checklist
        header."""
        supplement_file.write_text(
            "## Customer lifecycle\n\nJust a sentence.\n",
            encoding="utf-8",
        )
        out = prompts._supplement_block("Customer lifecycle")
        assert "Topics from the supplement" not in out
        assert "Just a sentence." in out

    def test_empty_or_missing_section_produces_placeholder(
        self, supplement_file: Path
    ):
        # File exists but section doesn't.
        supplement_file.write_text(
            "## Some other topic\n\nunrelated\n",
            encoding="utf-8",
        )
        out = prompts._supplement_block("Customer lifecycle")
        assert "no notes yet" in out.lower()
        # Placeholder stays short — it's a hint to the LLM, not content.
        assert len(out) < 500

    def test_missing_file_produces_placeholder(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        monkeypatch.setattr(
            supplement, "SUPPLEMENT_PATH", tmp_path / "not-there.md"
        )
        out = prompts._supplement_block("Customer lifecycle")
        assert "no notes yet" in out.lower()
