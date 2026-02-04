"""
Tests for chrono check (temporal grounding).
"""

import pytest
from governor.chrono import (
    ChronoFinding,
    ChronoSeverity,
    check_chrono,
    check_chrono_strict,
    chrono_invariant_check,
    get_current_year,
)


class TestChronoFinding:
    def test_to_dict(self):
        f = ChronoFinding(
            year=2025,
            context="Copyright 2025",
            reason="off-by-one",
            severity=ChronoSeverity.WARN,
            position=10,
        )
        d = f.to_dict()
        assert d["year"] == 2025
        assert d["severity"] == "warn"
        assert "position" in d


class TestGetCurrentYear:
    def test_returns_integer(self):
        year = get_current_year()
        assert isinstance(year, int)
        assert 2020 <= year <= 2100


class TestCheckChrono:
    def test_no_years_returns_empty(self):
        findings = check_chrono("No dates here", current_year=2026)
        assert findings == []

    def test_current_year_no_finding(self):
        findings = check_chrono("Copyright 2026", current_year=2026)
        assert findings == []

    def test_off_by_one_in_copyright(self):
        findings = check_chrono("Copyright 2025 James Beck", current_year=2026)
        assert len(findings) == 1
        assert findings[0].year == 2025
        assert findings[0].severity == ChronoSeverity.WARN
        assert "off-by-one" in findings[0].reason.lower() or "2025" in findings[0].reason

    def test_stale_year_in_copyright(self):
        findings = check_chrono("Copyright 2023 James Beck", current_year=2026)
        assert len(findings) == 1
        assert findings[0].year == 2023
        assert findings[0].severity == ChronoSeverity.WARN
        assert "stale" in findings[0].reason.lower()

    def test_far_future_is_error(self):
        findings = check_chrono("Published in 2030", current_year=2026)
        assert len(findings) == 1
        assert findings[0].year == 2030
        assert findings[0].severity == ChronoSeverity.ERROR

    def test_near_future_ok(self):
        # 1-2 years in future is plausible (upcoming publications, etc.)
        findings = check_chrono("Conference 2027", current_year=2026)
        assert findings == []

    def test_copyright_symbol(self):
        findings = check_chrono("© 2025 All rights reserved", current_year=2026)
        assert len(findings) == 1
        assert findings[0].year == 2025

    def test_iso_date_format(self):
        findings = check_chrono("Created: 2025-01-15", current_year=2026)
        assert len(findings) == 1
        assert findings[0].year == 2025

    def test_as_of_context(self):
        findings = check_chrono("As of 2025, the system...", current_year=2026)
        assert len(findings) == 1

    def test_year_without_context_not_flagged(self):
        # A year mentioned without current-context indicators shouldn't flag
        findings = check_chrono("The algorithm was invented in 2015", current_year=2026)
        assert findings == []

    def test_historical_year_ok(self):
        findings = check_chrono("Founded in 1995", current_year=2026)
        assert findings == []

    def test_multiple_findings(self):
        text = "Copyright 2024. Updated 2025. Valid until 2099."
        findings = check_chrono(text, current_year=2026)
        # 2024 and 2025 in copyright context, 2099 is far future
        assert len(findings) >= 2

    def test_context_extraction(self):
        text = "Some prefix text here. Copyright 2025 James Beck. Some suffix."
        findings = check_chrono(text, current_year=2026)
        assert len(findings) == 1
        assert "Copyright" in findings[0].context
        assert "2025" in findings[0].context

    def test_position_tracking(self):
        text = "Copyright 2025"
        findings = check_chrono(text, current_year=2026)
        assert findings[0].position == 10  # "Copyright " is 10 chars

    def test_check_context_disabled(self):
        # With context checking disabled, old years aren't flagged
        findings = check_chrono("Copyright 2025", current_year=2026, check_context=False)
        assert findings == []

    def test_max_future_years_customizable(self):
        # Default allows up to 2 years in future (inclusive)
        findings = check_chrono("Event 2029", current_year=2026, max_future_years=2)
        assert len(findings) == 1  # 2029 is 3 years out, beyond the 2-year window

        findings = check_chrono("Event 2028", current_year=2026, max_future_years=2)
        assert findings == []  # 2028 is exactly 2 years, within range


class TestCheckChronoStrict:
    def test_passes_with_no_issues(self):
        passed, findings = check_chrono_strict("Copyright 2026", current_year=2026)
        assert passed is True

    def test_fails_with_warn(self):
        passed, findings = check_chrono_strict("Copyright 2025", current_year=2026)
        assert passed is False
        assert len(findings) >= 1

    def test_fails_with_error(self):
        passed, findings = check_chrono_strict("Date: 2050", current_year=2026)
        assert passed is False


class TestChronoInvariantCheck:
    def test_passes_clean_text(self):
        passed, msg = chrono_invariant_check("No dates here")
        assert passed is True
        assert "No temporal anomalies" in msg

    def test_fails_stale_year(self):
        # Use a year that's definitely in the past relative to system time
        import datetime
        current = datetime.datetime.now().year
        stale_year = current - 2
        passed, msg = chrono_invariant_check(f"Copyright {stale_year}")
        assert passed is False
        assert str(stale_year) in msg


class TestRealWorldExamples:
    """Test with realistic content that might come from an AI."""

    def test_license_file(self):
        text = """
        Apache License 2.0

        Copyright 2025 James Beck

        Licensed under the Apache License...
        """
        findings = check_chrono(text, current_year=2026)
        # Should catch the stale copyright year
        assert any(f.year == 2025 for f in findings)

    def test_commit_message(self):
        text = "Fix bug in date handling (January 15, 2025)"
        findings = check_chrono(text, current_year=2026)
        assert len(findings) >= 1

    def test_research_citation(self):
        # Historical citations should be fine
        text = "Smith et al. (2020) demonstrated that..."
        findings = check_chrono(text, current_year=2026)
        assert findings == []

    def test_readme_badges(self):
        text = "![Build Status](https://img.shields.io/badge/updated-2025-blue)"
        findings = check_chrono(text, current_year=2026)
        # This might or might not flag depending on context detection
        # The key is it shouldn't crash
        assert isinstance(findings, list)

    def test_mixed_valid_invalid(self):
        text = """
        # Project History

        - Founded in 2020
        - Major rewrite in 2023
        - Current version © 2025
        """
        findings = check_chrono(text, current_year=2026)
        # Should flag the copyright line (has © context) and "Current version" context
        # Historical "Founded in" and "rewrite in" don't have current-context markers
        stale = [f for f in findings if f.severity == ChronoSeverity.WARN]
        # At minimum, the © 2025 should be caught
        assert any(f.year == 2025 for f in stale)
