"""Tests for research_why — per-turn Why overlay analysis."""

from __future__ import annotations

from governor.research_why import (
    WhyOverlay,
    build_why_overlay,
    canonical_form,
    canonicalize_ref,
    extract_candidate_sources,
    extract_source_refs,
)


# ============================================================================
# canonicalize_ref / canonical_form
# ============================================================================


class TestCanonicalization:
    """Tests for arXiv/DOI alias canonicalization."""

    def test_arxiv_doi_to_arxiv(self) -> None:
        """doi:10.48550/arXiv.2001.08361 → arxiv:2001.08361."""
        ref_type, identifier = canonicalize_ref("doi", "10.48550/arXiv.2001.08361")
        assert ref_type == "arxiv"
        assert identifier == "2001.08361"

    def test_arxiv_doi_case_insensitive(self) -> None:
        """DOI prefix match is case-insensitive."""
        ref_type, identifier = canonicalize_ref("doi", "10.48550/ARXIV.2203.15556")
        assert ref_type == "arxiv"
        assert identifier == "2203.15556"

    def test_non_arxiv_doi_unchanged(self) -> None:
        """Regular DOIs are not touched."""
        ref_type, identifier = canonicalize_ref("doi", "10.1038/nature12373")
        assert ref_type == "doi"
        assert identifier == "10.1038/nature12373"

    def test_arxiv_ref_unchanged(self) -> None:
        """Already-arxiv refs pass through."""
        ref_type, identifier = canonicalize_ref("arxiv", "2001.08361")
        assert ref_type == "arxiv"
        assert identifier == "2001.08361"

    def test_canonical_form_arxiv_doi(self) -> None:
        """canonical_form handles the full string form."""
        assert canonical_form("doi:10.48550/arXiv.2001.08361") == "arxiv:2001.08361"

    def test_canonical_form_regular_doi(self) -> None:
        assert canonical_form("doi:10.1234/foo") == "doi:10.1234/foo"

    def test_canonical_form_no_colon(self) -> None:
        """Strings without colon are lowercased."""
        assert canonical_form("SOMETHING") == "something"

    def test_canonical_form_preserves_version(self) -> None:
        """arXiv DOI with version suffix."""
        assert canonical_form("doi:10.48550/arXiv.2301.07041v2") == "arxiv:2301.07041v2"

    def test_source_ref_normalized_property(self) -> None:
        """SourceRef.normalized uses canonicalization."""
        from governor.research_why import SourceRef
        ref = SourceRef(ref_type="doi", identifier="10.48550/arXiv.2001.08361", raw="doi:10.48550/arXiv.2001.08361")
        assert ref.normalized == "arxiv:2001.08361"


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

    # -- Edge cases (Chatty review) --

    def test_trailing_punctuation_stripped(self) -> None:
        """DOI at end of sentence: trailing period stripped."""
        refs = extract_source_refs("See doi:10.1234/abc.")
        assert len(refs) == 1
        assert refs[0].identifier == "10.1234/abc"

    def test_trailing_paren_not_captured(self) -> None:
        """DOI in parentheses: closing paren not captured."""
        refs = extract_source_refs("(doi:10.1234/abc)")
        assert len(refs) == 1
        # The regex stops at ')' because [^\s,;)\]] excludes it
        assert ")" not in refs[0].identifier

    def test_case_insensitive_cve(self) -> None:
        """CVE matching is case-insensitive."""
        refs = extract_source_refs("cve-2024-12345")
        assert len(refs) == 1
        assert refs[0].ref_type == "cve"

    def test_doi_in_url_extracted(self) -> None:
        """DOI URL form is extracted correctly."""
        refs = extract_source_refs("https://doi.org/10.1038/s41586-023-06747-5")
        assert len(refs) == 1
        assert refs[0].identifier.startswith("10.1038/")

    def test_code_block_still_matches(self) -> None:
        """Source refs inside code blocks are still extracted.

        This is intentional: we want to catch citations wherever they appear.
        The model might format them as code.
        """
        refs = extract_source_refs("```\ndoi:10.1234/foo\n```")
        assert len(refs) == 1

    def test_not_a_doi_false_positive(self) -> None:
        """Random '10.' followed by digits is not a DOI without prefix."""
        refs = extract_source_refs("The score was 10.5432 out of 20.")
        # No doi: prefix → should not match
        assert not any(r.ref_type == "doi" for r in refs)

    def test_pip_install_in_prose(self) -> None:
        """'pip install' in prose extracts the package name."""
        refs = extract_source_refs("You can pip install flask-cors for CORS support.")
        assert len(refs) == 1
        assert refs[0].identifier == "flask-cors"

    # -- arXiv/DOI canonicalization --

    def test_arxiv_doi_dedup_with_arxiv_id(self) -> None:
        """doi:10.48550/arXiv.X and arxiv:X in same text dedup to one ref."""
        text = (
            "Kaplan et al. (doi:10.48550/arXiv.2001.08361) showed scaling laws. "
            "See also arxiv:2001.08361 for the full paper."
        )
        refs = extract_source_refs(text)
        assert len(refs) == 1  # deduped via canonical form

    def test_arxiv_doi_first_occurrence_wins(self) -> None:
        """When deduping, the first occurrence in text wins."""
        text = "doi:10.48550/arXiv.2001.08361 and arxiv:2001.08361"
        refs = extract_source_refs(text)
        assert len(refs) == 1
        # DOI pattern comes first in _SOURCE_REF_PATTERNS
        assert refs[0].ref_type == "doi"
        assert refs[0].identifier == "10.48550/arXiv.2001.08361"

    def test_two_different_arxiv_dois_not_deduped(self) -> None:
        """Different arXiv DOIs are not deduped."""
        text = "doi:10.48550/arXiv.2001.08361 and doi:10.48550/arXiv.2203.15556"
        refs = extract_source_refs(text)
        assert len(refs) == 2


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

    # -- arXiv/DOI alias matching --

    def test_arxiv_doi_accepted_matches_arxiv_ref(self) -> None:
        """Accepted as doi:10.48550/arXiv.X matches assistant's arxiv:X."""
        overlay = build_why_overlay(
            "See arxiv:2001.08361 for details.",
            accepted_sources=["doi:10.48550/arXiv.2001.08361"],
            accepted_claim_ids=[],
        )
        assert len(overlay.matched_refs) == 1
        assert len(overlay.floating_refs) == 0

    def test_arxiv_accepted_matches_doi_ref(self) -> None:
        """Accepted as arxiv:X matches assistant's doi:10.48550/arXiv.X."""
        overlay = build_why_overlay(
            "Kaplan et al. (doi:10.48550/arXiv.2001.08361) showed...",
            accepted_sources=["arxiv:2001.08361"],
            accepted_claim_ids=[],
        )
        assert len(overlay.matched_refs) == 1
        assert len(overlay.floating_refs) == 0

    def test_arxiv_doi_alias_not_floating(self) -> None:
        """The exact scenario from the screenshots: arXiv DOI accepted, same paper not flagged floating."""
        overlay = build_why_overlay(
            "The foundational work is Kaplan et al. (doi:10.48550/arXiv.2001.08361). "
            "Hoffmann et al. (doi:10.48550/arXiv.2203.15556) revised the allocation.",
            accepted_sources=[
                "doi:10.48550/arXiv.2001.08361",
                "doi:10.48550/arXiv.2203.15556",
            ],
            accepted_claim_ids=["C-DEMO01", "C-DEMO02"],
        )
        assert len(overlay.matched_refs) == 2
        assert len(overlay.floating_refs) == 0

    def test_mixed_arxiv_alias_and_regular_doi(self) -> None:
        """arXiv DOI and regular DOI in same overlay."""
        overlay = build_why_overlay(
            "See doi:10.48550/arXiv.2001.08361 and doi:10.1038/nature12373.",
            accepted_sources=["arxiv:2001.08361"],  # only arXiv accepted
            accepted_claim_ids=[],
        )
        assert len(overlay.matched_refs) == 1  # arXiv alias matches
        assert len(overlay.floating_refs) == 1  # nature DOI is floating
        assert overlay.floating_refs[0].identifier == "10.1038/nature12373"
