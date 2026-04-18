"""Tests for the release-notes parser — dates, sections, sandbox split."""

from __future__ import annotations

import pytest

from vipmp_docs_mcp.releases import (
    SECTION_API_CHANGES,
    SECTION_EARLIER,
    SECTION_SANDBOX,
    SECTION_UPCOMING,
    ReleaseChange,
    ReleaseEntry,
    filter_section,
    filter_since,
    parse_recent_releases,
    parse_upcoming_releases,
)

# ---------------------------------------------------------------------------
# Synthetic HTML fixtures
# ---------------------------------------------------------------------------


RECENT_HTML = """
<html><body><main>
<h1>Release notes</h1>
<h2>API changes</h2>

<h3>April 09, 2026</h3>
<h4>Support for automatic discount continuity across renewals</h4>
<p>Discounts now continue across renewals automatically.</p>
<ul>
  <li>Applies to all Flexible Discount offers.</li>
  <li>Respects the discount lock end date.</li>
</ul>

<h3>March 30, 2026</h3>
<h4>Early Renewals</h4>
<p>Renew subscriptions ahead of the anniversary date.</p>
<h4>Second change on same date</h4>
<p>Extra body text for the second feature.</p>

<h3>Earlier releases from 2024</h3>
<p>Historical changes preserved below.</p>

<h2>Sandbox changes</h2>

<h3>January 08, 2026</h3>
<h4>Sandbox environment reset</h4>
<p>Sandbox accounts now reset monthly.</p>

<h3>Earlier releases</h3>
<p>Historical sandbox notes.</p>

<p>vipmp marker</p>
</main></body></html>
"""


UPCOMING_STUB_HTML = """
<html><body><main>
<h1>Upcoming releases</h1>
<p>This topic will be updated soon.</p>
<p>vipmp marker</p>
</main></body></html>
"""


UPCOMING_EMPTY_HTML = """
<html><body><main>
<h1>Upcoming releases</h1>
</main></body></html>
"""


# ---------------------------------------------------------------------------
# Tests: parser
# ---------------------------------------------------------------------------


class TestParseRecent:
    def test_extracts_all_releases(self):
        entries = parse_recent_releases(RECENT_HTML, docs_path="/vipmp/docs/release-notes")
        # Two dated API changes + earlier-api + one dated Sandbox + earlier-sandbox.
        assert len(entries) == 5

    def test_dated_api_entries_parse_iso(self):
        entries = parse_recent_releases(RECENT_HTML)
        dates = {e.date for e in entries if e.date}
        assert "2026-04-09" in dates
        assert "2026-03-30" in dates
        assert "2026-01-08" in dates

    def test_undated_entries_land_in_earlier_section(self):
        entries = parse_recent_releases(RECENT_HTML)
        earlier = [e for e in entries if e.section == SECTION_EARLIER]
        assert len(earlier) == 2  # "Earlier releases from 2024" + "Earlier releases"
        for e in earlier:
            assert e.date is None

    def test_sandbox_section_labeled(self):
        entries = parse_recent_releases(RECENT_HTML)
        sandbox_dated = [
            e for e in entries if e.section == SECTION_SANDBOX and e.date
        ]
        assert len(sandbox_dated) == 1
        assert sandbox_dated[0].date == "2026-01-08"
        assert any("Sandbox" in c.title for c in sandbox_dated[0].changes)

    def test_multiple_h4s_under_one_date(self):
        entries = parse_recent_releases(RECENT_HTML)
        march_30 = next(e for e in entries if e.date == "2026-03-30")
        assert len(march_30.changes) == 2
        assert march_30.changes[0].title == "Early Renewals"
        assert "anniversary date" in march_30.changes[0].body
        assert march_30.changes[1].title == "Second change on same date"

    def test_body_preserves_lists(self):
        entries = parse_recent_releases(RECENT_HTML)
        april_9 = next(e for e in entries if e.date == "2026-04-09")
        body = april_9.changes[0].body
        assert "- Applies to all Flexible Discount offers." in body
        assert "- Respects the discount lock end date." in body

    def test_docs_path_propagated(self):
        entries = parse_recent_releases(
            RECENT_HTML, docs_path="/vipmp/docs/release-notes"
        )
        for e in entries:
            assert e.docs_path == "/vipmp/docs/release-notes"


class TestParseUpcoming:
    def test_stub_captured_as_single_entry(self):
        entries = parse_upcoming_releases(UPCOMING_STUB_HTML)
        assert len(entries) == 1
        assert entries[0].section == SECTION_UPCOMING
        assert entries[0].date is None
        assert "This topic will be updated soon" in entries[0].changes[0].body

    def test_empty_page_returns_empty(self):
        assert parse_upcoming_releases(UPCOMING_EMPTY_HTML) == []


# ---------------------------------------------------------------------------
# Tests: filtering
# ---------------------------------------------------------------------------


class TestFilterSince:
    def _sample(self):
        return [
            ReleaseEntry(date="2026-04-09", raw_date="April 9, 2026", section=SECTION_API_CHANGES),
            ReleaseEntry(date="2026-03-30", raw_date="March 30, 2026", section=SECTION_API_CHANGES),
            ReleaseEntry(date="2025-01-23", raw_date="Jan 23, 2025", section=SECTION_API_CHANGES),
            ReleaseEntry(date=None, raw_date="Earlier releases", section=SECTION_EARLIER),
        ]

    def test_keeps_on_or_after(self):
        out = filter_since(self._sample(), "2026-01-01")
        dates = {e.date for e in out}
        assert dates == {"2026-04-09", "2026-03-30"}

    def test_drops_undated_entries(self):
        out = filter_since(self._sample(), "2020-01-01")
        assert all(e.date is not None for e in out)

    def test_boundary_inclusive(self):
        out = filter_since(self._sample(), "2026-03-30")
        assert "2026-03-30" in {e.date for e in out}

    def test_invalid_date_raises(self):
        with pytest.raises(ValueError, match="ISO date"):
            filter_since(self._sample(), "last week")


class TestFilterSection:
    def test_filters_to_section(self):
        entries = [
            ReleaseEntry(date=None, raw_date="a", section=SECTION_API_CHANGES),
            ReleaseEntry(date=None, raw_date="b", section=SECTION_SANDBOX),
            ReleaseEntry(date=None, raw_date="c", section=SECTION_UPCOMING),
        ]
        assert len(filter_section(entries, SECTION_SANDBOX)) == 1
        assert filter_section(entries, SECTION_SANDBOX)[0].raw_date == "b"


# ---------------------------------------------------------------------------
# Tests: roundtrip
# ---------------------------------------------------------------------------


class TestReleaseEntryDict:
    def test_roundtrip(self):
        e = ReleaseEntry(
            date="2026-04-09",
            raw_date="April 09, 2026",
            section=SECTION_API_CHANGES,
            changes=[ReleaseChange(title="Foo", body="Bar")],
            docs_path="/vipmp/docs/release-notes",
        )
        loaded = ReleaseEntry.from_dict(e.to_dict())
        assert loaded.date == e.date
        assert loaded.raw_date == e.raw_date
        assert loaded.section == e.section
        assert len(loaded.changes) == 1
        assert loaded.changes[0].title == "Foo"
        assert loaded.docs_path == "/vipmp/docs/release-notes"
