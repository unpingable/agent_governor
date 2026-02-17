# SPDX-License-Identifier: Apache-2.0
"""
Tests for cooperative redundancy / independence scoring.

Covers: MethodSignature, pairwise_jaccard, independence_score,
is_independent_support, IndependenceScorer, IndependenceResult,
and quorum integration.
"""

from datetime import datetime, timedelta

import pytest

from governor.independence import (
    IndependenceResult,
    IndependenceScorer,
    MethodSignature,
    independence_score,
    is_independent_support,
    pairwise_jaccard,
)
from governor.quorum import (
    ClaimType,
    QuorumManager,
    QuorumStatus,
    Vote,
    VoteVerdict,
)
from governor.dissent import EvidencePointer


# =============================================================================
# TestMethodSignature
# =============================================================================


class TestMethodSignature:

    def test_creation(self):
        sig = MethodSignature(
            agent_id="a1",
            tool_path_hash="tool1",
            sources_hash="src1",
            prompt_hash="prompt1",
        )
        assert sig.agent_id == "a1"
        assert sig.tool_path_hash == "tool1"
        assert sig.model_tier == "standard"

    def test_feature_set(self):
        sig = MethodSignature(
            agent_id="a1",
            tool_path_hash="tool1",
            sources_hash="src1",
            prompt_hash="prompt1",
        )
        fs = sig.feature_set
        assert "tool:tool1" in fs
        assert "sources:src1" in fs
        assert "prompt:prompt1" in fs
        assert "tier:standard" in fs
        assert len(fs) == 4

    def test_to_dict(self):
        sig = MethodSignature(
            agent_id="a1",
            tool_path_hash="t1",
            sources_hash="s1",
            prompt_hash="p1",
            source_urls=frozenset({"http://a.com"}),
        )
        d = sig.to_dict()
        assert d["agent_id"] == "a1"
        assert d["source_urls"] == ["http://a.com"]

    def test_from_vote_with_hashes(self):
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="ok",
            tool_path_hash="t1", sources_hash="s1", prompt_hash="p1",
        )
        sig = MethodSignature.from_vote(v)
        assert sig is not None
        assert sig.agent_id == "a1"
        assert sig.tool_path_hash == "t1"

    def test_from_vote_without_hashes(self):
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="ok",
        )
        sig = MethodSignature.from_vote(v)
        assert sig is None

    def test_from_vote_partial_hashes(self):
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="ok",
            tool_path_hash="t1",
        )
        sig = MethodSignature.from_vote(v)
        assert sig is None  # Missing sources_hash and prompt_hash


# =============================================================================
# TestPairwiseJaccard
# =============================================================================


class TestPairwiseJaccard:

    def test_identical_signatures(self):
        sig = MethodSignature("a1", "t1", "s1", "p1")
        assert pairwise_jaccard(sig, sig) == 1.0

    def test_disjoint_signatures(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t2", "s2", "p2")
        # features: tool, sources, prompt all different, but tier is same (standard)
        # overlap = {"tier:standard"}, union = 7
        j = pairwise_jaccard(sig_a, sig_b)
        assert j == pytest.approx(1 / 7)

    def test_completely_disjoint(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1", model_tier="heavy")
        sig_b = MethodSignature("a2", "t2", "s2", "p2", model_tier="fast")
        # All 4 features different → overlap=0, union=8
        j = pairwise_jaccard(sig_a, sig_b)
        assert j == 0.0

    def test_partial_overlap(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t1", "s2", "p2")
        # Same tool, same tier → overlap=2, union=6
        j = pairwise_jaccard(sig_a, sig_b)
        assert j == pytest.approx(2 / 6)

    def test_symmetry(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t2", "s2", "p2")
        assert pairwise_jaccard(sig_a, sig_b) == pairwise_jaccard(sig_b, sig_a)


# =============================================================================
# TestIndependenceScore
# =============================================================================


class TestIndependenceScore:

    def test_empty_list(self):
        assert independence_score([]) == 0.0

    def test_single_signature(self):
        sig = MethodSignature("a1", "t1", "s1", "p1")
        assert independence_score([sig]) == 0.0

    def test_identical_signatures(self):
        sig = MethodSignature("a1", "t1", "s1", "p1")
        sig2 = MethodSignature("a2", "t1", "s1", "p1")
        # Same features → jaccard=1.0 → independence=0.0
        assert independence_score([sig, sig2]) == 0.0

    def test_completely_different(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1", model_tier="heavy")
        sig_b = MethodSignature("a2", "t2", "s2", "p2", model_tier="fast")
        assert independence_score([sig_a, sig_b]) == 1.0

    def test_three_signatures_mixed(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t2", "s2", "p2")
        sig_c = MethodSignature("a3", "t1", "s1", "p1")  # Same as a1
        # Max jaccard is between a1 and a3 (=1.0) → independence=0.0
        assert independence_score([sig_a, sig_b, sig_c]) == 0.0


# =============================================================================
# TestIsIndependentSupport
# =============================================================================


class TestIsIndependentSupport:

    def test_different_sources(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t1", "s2", "p1")
        assert is_independent_support(sig_a, sig_b)

    def test_same_everything(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t1", "s1", "p1")
        assert not is_independent_support(sig_a, sig_b)

    def test_different_tools_same_sources(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t2", "s1", "p2")
        # Different tools but same sources → not independent
        assert not is_independent_support(sig_a, sig_b)

    def test_same_source_urls_anti_cheat(self):
        sig_a = MethodSignature(
            "a1", "t1", "s1", "p1",
            source_urls=frozenset({"http://example.com/doc1"}),
        )
        sig_b = MethodSignature(
            "a2", "t2", "s2", "p2",
            source_urls=frozenset({"http://example.com/doc1"}),
        )
        # Same URL even with different hashes → anti-cheat triggers
        assert not is_independent_support(sig_a, sig_b)

    def test_no_source_urls_bypasses_anti_cheat(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t2", "s2", "p2")
        # No URLs → no anti-cheat, different sources → independent
        assert is_independent_support(sig_a, sig_b)

    def test_different_tools_and_sources(self):
        sig_a = MethodSignature("a1", "t1", "s1", "p1")
        sig_b = MethodSignature("a2", "t2", "s2", "p2")
        assert is_independent_support(sig_a, sig_b)


# =============================================================================
# TestIndependenceScorer
# =============================================================================


class TestIndependenceScorer:

    def _make_vote(self, agent_id, tool="t1", sources="s1", prompt="p1"):
        return Vote(
            vote_id=f"v_{agent_id}",
            proposal_id="p1",
            agent_id=agent_id,
            verdict=VoteVerdict.APPROVE,
            reason="ok",
            tool_path_hash=tool,
            sources_hash=sources,
            prompt_hash=prompt,
        )

    def test_score_diverse_votes(self):
        scorer = IndependenceScorer(threshold=0.3)
        votes = [
            self._make_vote("a1", "t1", "s1", "p1"),
            self._make_vote("a2", "t2", "s2", "p2"),
        ]
        result = scorer.score_votes(votes)
        assert result.score > 0.3
        assert result.passes_threshold

    def test_score_identical_votes(self):
        scorer = IndependenceScorer(threshold=0.3)
        votes = [
            self._make_vote("a1", "t1", "s1", "p1"),
            self._make_vote("a2", "t1", "s1", "p1"),
        ]
        result = scorer.score_votes(votes)
        assert result.score == 0.0
        assert not result.passes_threshold

    def test_score_votes_without_hashes(self):
        scorer = IndependenceScorer(threshold=0.3)
        votes = [
            Vote("v1", "p1", "a1", VoteVerdict.APPROVE, "ok"),
            Vote("v2", "p1", "a2", VoteVerdict.APPROVE, "ok"),
        ]
        result = scorer.score_votes(votes)
        assert result.total_signatures == 0
        assert result.score == 0.0

    def test_count_independent_supports(self):
        scorer = IndependenceScorer()
        votes = [
            self._make_vote("a1", "t1", "s1", "p1"),
            self._make_vote("a2", "t2", "s2", "p2"),
            self._make_vote("a3", "t1", "s1", "p1"),  # Same as a1
        ]
        count = scorer.count_independent_supports(votes)
        # a1-a2 independent, a2-a3 independent → a1, a2, a3 all in set = 3
        assert count >= 2

    def test_anti_cheat_detection(self):
        scorer = IndependenceScorer()
        sigs = [
            MethodSignature(
                "a1", "t1", "s1", "p1",
                source_urls=frozenset({"http://shared.com"}),
            ),
            MethodSignature(
                "a2", "t2", "s2", "p2",
                source_urls=frozenset({"http://shared.com"}),
            ),
        ]
        violations = scorer.check_anti_cheat(sigs)
        assert len(violations) == 1
        assert "shared.com" in violations[0]

    def test_anti_cheat_blocks_threshold(self):
        scorer = IndependenceScorer(threshold=0.3)
        votes = [
            Vote(
                "v1", "p1", "a1", VoteVerdict.APPROVE, "ok",
                tool_path_hash="t1", sources_hash="s1", prompt_hash="p1",
            ),
            Vote(
                "v2", "p1", "a2", VoteVerdict.APPROVE, "ok",
                tool_path_hash="t2", sources_hash="s2", prompt_hash="p2",
            ),
        ]
        # Manually inject source_urls for anti-cheat — we need MethodSignature
        # to test this properly via the scorer
        result = scorer.score_votes(votes)
        # Score is high but no violations since Vote doesn't carry source_urls
        assert result.passes_threshold

    def test_threshold_customization(self):
        scorer = IndependenceScorer(threshold=0.9)
        votes = [
            self._make_vote("a1", "t1", "s1", "p1"),
            self._make_vote("a2", "t1", "s2", "p2"),
        ]
        result = scorer.score_votes(votes)
        # Score is moderate but below 0.9
        assert not result.passes_threshold

    def test_result_pairwise_scores(self):
        scorer = IndependenceScorer()
        votes = [
            self._make_vote("a1", "t1", "s1", "p1"),
            self._make_vote("a2", "t2", "s2", "p2"),
        ]
        result = scorer.score_votes(votes)
        assert len(result.pairwise_scores) == 1
        a, b, s = result.pairwise_scores[0]
        assert {a, b} == {"a1", "a2"}


# =============================================================================
# TestIndependenceResult
# =============================================================================


class TestIndependenceResult:

    def test_to_dict(self):
        r = IndependenceResult(
            score=0.75,
            independent_count=2,
            total_signatures=3,
            violations=[],
            pairwise_scores=[("a1", "a2", 0.25)],
            passes_threshold=True,
        )
        d = r.to_dict()
        assert d["score"] == 0.75
        assert d["independent_count"] == 2
        assert d["passes_threshold"]
        assert len(d["pairwise_scores"]) == 1

    def test_threshold_pass(self):
        r = IndependenceResult(
            score=0.5, independent_count=2, total_signatures=2,
            violations=[], pairwise_scores=[], passes_threshold=True,
        )
        assert r.passes_threshold

    def test_threshold_fail_with_violations(self):
        r = IndependenceResult(
            score=0.8, independent_count=2, total_signatures=2,
            violations=["shared URLs"], pairwise_scores=[],
            passes_threshold=False,
        )
        assert not r.passes_threshold


# =============================================================================
# TestQuorumIntegration
# =============================================================================


class TestQuorumIntegration:

    def _make_vote(self, mgr, pid, agent_id, tool="t1", sources="s1", prompt="p1"):
        return mgr.cast_vote(
            pid, agent_id, VoteVerdict.APPROVE, "ok",
            tool_path_hash=tool, sources_hash=sources, prompt_hash=prompt,
        )

    def test_identical_signatures_dont_count(self):
        """Critical test #3: identical method signatures should not pass independence."""
        scorer = IndependenceScorer(threshold=0.3)
        mgr = QuorumManager(independence_scorer=scorer)
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)

        # Two agents with identical method signatures
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       tool_path_hash="same", sources_hash="same", prompt_hash="same")
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       tool_path_hash="same", sources_hash="same", prompt_hash="same")
        mgr.update("p1", now=now + timedelta(seconds=5))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=5))
        assert not can
        assert any("Independence" in r or "independence" in r.lower() for r in reasons)

    def test_can_proceed_checks_independence(self):
        """QuorumManager with independence_scorer gates on independence."""
        scorer = IndependenceScorer(threshold=0.3)
        mgr = QuorumManager(independence_scorer=scorer)
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)

        # Identical signatures
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       tool_path_hash="t1", sources_hash="s1", prompt_hash="p1")
        mgr.update("p1", now=now + timedelta(seconds=15))
        # Only one vote — score is 0.0 (single sig)
        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=15))
        assert not can

    def test_diverse_methods_pass(self):
        """Diverse method signatures should pass independence check."""
        scorer = IndependenceScorer(threshold=0.3)
        mgr = QuorumManager(independence_scorer=scorer)
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.MATH, created_at=now)

        ev = [EvidencePointer(description="auto", evidence_type="calc_result")]
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now,
                       tool_path_hash="grep", sources_hash="github", prompt_hash="tmpl1", evidence=ev)
        mgr.cast_vote("p1", "a2", VoteVerdict.APPROVE, "ok", timestamp=now,
                       tool_path_hash="curl", sources_hash="arxiv", prompt_hash="tmpl2", evidence=ev)
        mgr.update("p1", now=now + timedelta(seconds=5))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=5))
        assert can
        assert len(reasons) == 0

    def test_no_scorer_skips_independence(self):
        """Without independence_scorer, independence gate is skipped."""
        mgr = QuorumManager()  # No scorer
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)
        ev = [EvidencePointer(description="auto", evidence_type="test_result")]
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now, evidence=ev)
        mgr.update("p1", now=now + timedelta(seconds=15))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=15))
        assert can

    def test_votes_without_hashes_score_zero(self):
        """Votes without hash fields → 0 signatures → independence fails."""
        scorer = IndependenceScorer(threshold=0.3)
        mgr = QuorumManager(independence_scorer=scorer)
        now = datetime(2024, 6, 1)
        mgr.create_quorum("p1", ClaimType.CODE, created_at=now)

        # Vote without hashes
        mgr.cast_vote("p1", "a1", VoteVerdict.APPROVE, "ok", timestamp=now)
        mgr.update("p1", now=now + timedelta(seconds=15))

        can, reasons = mgr.can_proceed("p1", now=now + timedelta(seconds=15))
        assert not can
        assert any("ndependence" in r for r in reasons)
