"""Tests for research_why — per-turn Why overlay analysis."""

from __future__ import annotations

from governor.research_why import (
    WhyOverlay,
    build_why_overlay,
    extract_candidate_sources,
    extract_source_refs,
)


# ============================================================================
# extract_source_refs
# ============================================================================


class TestExtractSourceRefs:
    """Tests for source reference extraction from text."""

    def test_doi(self) -> None:
        refs = extract_source_refs("See doi:10.1038/nature12373 for details.")
        assert len(refs) == 1
        assert refs[0].ref_type == "doi"
        assert refs[0].identifier == "10.1038/nature12373"

    def test_doi_url(self) -> None:
        refs = extract_source_refs("From https://doi.org/10.1234/foo.bar")
        assert len(refs) == 1
        assert refs[0].normalized == "doi:10.1234/foo.bar"

    def test_arxiv(self) -> None:
        refs = extract_source_refs("arxiv:2301.07041v2")
        assert len(refs) == 1
        assert refs[0].ref_type == "arxiv"
        assert refs[0].identifier == "2301.07041v2"

    def test_cve(self) -> None:
        refs = extract_source_refs("Patched in CVE-2021-44228")
        assert len(refs) == 1
        assert refs[0].ref_type == "cve"
        assert refs[0].normalized == "cve:CVE-2021-44228"

    def test_rfc(self) -> None:
        refs = extract_source_refs("Per RFC 6749")
        assert len(refs) == 1
        assert refs[0].ref_type == "rfc"
        assert refs[0].identifier == "6749"

    def test_pypi(self) -> None:
        refs = extract_source_refs("Install via pypi:numpy")
        assert len(refs) == 1
        assert refs[0].ref_type == "pypi"
        assert refs[0].identifier == "numpy"

    def test_pip_install(self) -> None:
        refs = extract_source_refs("Run pip install requests")
        assert len(refs) == 1
        assert refs[0].ref_type == "pypi"
        assert refs[0].identifier == "requests"

    def test_multiple_refs(self) -> None:
        text = "Based on doi:10.1234/foo and CVE-2023-12345 per RFC 8446"
        refs = extract_source_refs(text)
        assert len(refs) == 3
        types = {r.ref_type for r in refs}
        assert types == {"doi", "cve", "rfc"}

    def test_dedup(self) -> None:
        text = "See doi:10.1234/foo and also doi:10.1234/foo again"
        refs = extract_source_refs(text)
        assert len(refs) == 1

    def test_no_refs(self) -> None:
        refs = extract_source_refs("This text has no source references.")
        assert len(refs) == 0


# ============================================================================
# extract_candidate_sources
# ============================================================================


class TestExtractCandidateSources:
    """Tests for CANDIDATE_SOURCE line extraction."""

    def test_basic(self) -> None:
        text = "CANDIDATE_SOURCE: doi:10.1234/new"
        candidates = extract_candidate_sources(text)
        assert candidates == ["doi:10.1234/new"]

    def test_multiple(self) -> None:
        text = (
            "Some text\n"
            "CANDIDATE_SOURCE: doi:10.1234/a\n"
            "More text\n"
            "CANDIDATE_SOURCE: pypi:pandas\n"
        )
        candidates = extract_candidate_sources(text)
        assert len(candidates) == 2
        assert "doi:10.1234/a" in candidates
        assert "pypi:pandas" in candidates

    def test_dedup(self) -> None:
        text = (
            "CANDIDATE_SOURCE: doi:10.1234/a\n"
            "CANDIDATE_SOURCE: doi:10.1234/a\n"
        )
        candidates = extract_candidate_sources(text)
        assert len(candidates) == 1

    def test_case_insensitive(self) -> None:
        text = "candidate_source: doi:10.1234/foo"
        candidates = extract_candidate_sources(text)
        assert len(candidates) == 1

    def test_no_candidates(self) -> None:
        text = "This text has no candidate source lines."
        candidates = extract_candidate_sources(text)
        assert len(candidates) == 0


# ============================================================================
# build_why_overlay
# ============================================================================


class TestBuildWhyOverlay:
    """Tests for the full Why overlay builder."""

    def test_empty_everything(self) -> None:
        """No accepted sources, no refs in text → minimal overlay."""
        overlay = build_why_overlay("Hello world", [], [])
        assert overlay.injected_source_count == 0
        assert overlay.injected_claim_count == 0
        assert overlay.referenced_sources == []
        assert overlay.floating_refs == []
        assert overlay.matched_refs == []

    def test_injected_counts(self) -> None:
        """Overlay reflects what was injected."""
        overlay = build_why_overlay(
            "text",
            accepted_sources=["doi:10.1234/a", "pypi:numpy"],
            accepted_claim_ids=["C-ABC123", "C-DEF456"],
        )
        assert overlay.injected_source_count == 2
        assert overlay.injected_claim_count == 2
        assert overlay.injected_sources == ["doi:10.1234/a", "pypi:numpy"]
        assert overlay.injected_claim_ids == ["C-ABC123", "C-DEF456"]

    def test_matched_ref(self) -> None:
        """Referenced source that's in accepted → matched."""
        overlay = build_why_overlay(
            "According to doi:10.1234/foo, the result is...",
            accepted_sources=["doi:10.1234/foo"],
            accepted_claim_ids=[],
        )
        assert len(overlay.matched_refs) == 1
        assert overlay.matched_refs[0].normalized == "doi:10.1234/foo"
        assert len(overlay.floating_refs) == 0

    def test_floating_ref(self) -> None:
        """Referenced source NOT in accepted and NOT a candidate → floating."""
        overlay = build_why_overlay(
            "According to doi:10.9999/ghost, the result is...",
            accepted_sources=["doi:10.1234/foo"],
            accepted_claim_ids=[],
        )
        assert len(overlay.floating_refs) == 1
        assert overlay.floating_refs[0].normalized == "doi:10.9999/ghost"
        assert len(overlay.matched_refs) == 0

    def test_candidate_not_floating(self) -> None:
        """Source under CANDIDATE_SOURCE is NOT treated as floating."""
        text = (
            "I found doi:10.5678/new which is relevant.\n"
            "CANDIDATE_SOURCE: doi:10.5678/new"
        )
        overlay = build_why_overlay(
            text,
            accepted_sources=[],
            accepted_claim_ids=[],
        )
        assert len(overlay.candidate_sources) == 1
        assert len(overlay.floating_refs) == 0

    def test_mixed_matched_and_floating(self) -> None:
        """Mix of matched, floating, and candidate refs."""
        text = (
            "Based on doi:10.1234/accepted and doi:10.9999/ghost.\n"
            "Also see doi:10.5678/candidate.\n"
            "CANDIDATE_SOURCE: doi:10.5678/candidate"
        )
        overlay = build_why_overlay(
            text,
            accepted_sources=["doi:10.1234/accepted"],
            accepted_claim_ids=["C-001"],
        )
        assert len(overlay.matched_refs) == 1
        assert overlay.matched_refs[0].identifier == "10.1234/accepted"
        assert len(overlay.floating_refs) == 1
        assert overlay.floating_refs[0].identifier == "10.9999/ghost"
        assert len(overlay.candidate_sources) == 1

    def test_case_insensitive_matching(self) -> None:
        """Accepted source matching is case-insensitive."""
        overlay = build_why_overlay(
            "See DOI:10.1234/FOO for details.",
            accepted_sources=["doi:10.1234/FOO"],
            accepted_claim_ids=[],
        )
        assert len(overlay.matched_refs) == 1
        assert len(overlay.floating_refs) == 0

    def test_to_dict(self) -> None:
        """WhyOverlay.to_dict() produces expected JSON structure."""
        overlay = build_why_overlay(
            "See doi:10.1234/foo and doi:10.9999/ghost.\nCANDIDATE_SOURCE: pypi:pandas",
            accepted_sources=["doi:10.1234/foo"],
            accepted_claim_ids=["C-001"],
        )
        d = overlay.to_dict()
        assert d["injected"]["source_count"] == 1
        assert d["injected"]["claim_count"] == 1
        assert d["injected"]["claim_ids"] == ["C-001"]
        # 3 refs: doi:10.1234/foo, doi:10.9999/ghost, pypi:pandas (from CANDIDATE line)
        assert len(d["referenced"]["sources"]) == 3
        assert len(d["referenced"]["candidates"]) == 1
        assert len(d["matched"]) == 1
        assert len(d["floating"]) == 1  # doi:10.9999/ghost (pypi:pandas is a candidate)

    def test_no_accepted_all_floating(self) -> None:
        """With no accepted sources, all refs are floating."""
        overlay = build_why_overlay(
            "doi:10.1234/a and CVE-2023-12345",
            accepted_sources=[],
            accepted_claim_ids=[],
        )
        assert len(overlay.floating_refs) == 2
        assert len(overlay.matched_refs) == 0

    def test_all_accepted_none_floating(self) -> None:
        """All refs match accepted sources — none floating."""
        overlay = build_why_overlay(
            "doi:10.1234/a and pypi:numpy",
            accepted_sources=["doi:10.1234/a", "pypi:numpy"],
            accepted_claim_ids=[],
        )
        assert len(overlay.matched_refs) == 2
        assert len(overlay.floating_refs) == 0
