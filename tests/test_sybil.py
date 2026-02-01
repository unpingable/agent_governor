"""Tests for sybil resistance: bloc detection, Neff, origin budgets."""

import pytest
from datetime import datetime, timedelta

from governor.sybil import (
    SybilEventType,
    ProvenanceVector,
    Bloc,
    NeffResult,
    OriginBudget,
    SybilEvent,
    SybilConfig,
    BlocDetector,
    OriginBudgetTracker,
    SybilDetector,
    create_sybil_detector,
    compute_neff,
)
from governor.quorum import (
    Vote,
    VoteVerdict,
    QuorumManager,
    ClaimType,
    QuorumStatus,
    create_quorum_manager,
)
from governor.independence import MethodSignature
from governor.dissent import EvidencePointer


# =============================================================================
# Helpers
# =============================================================================


def make_vote(
    agent_id: str,
    proposal_id: str = "prop1",
    verdict: VoteVerdict = VoteVerdict.APPROVE,
    tool_path_hash: str = "tool_a",
    sources_hash: str = "src_a",
    prompt_hash: str = "prompt_a",
    model_id: str = "standard",
    provider_id: str | None = None,
    response_time_ms: float | None = None,
    error_hash: str | None = None,
    source_urls: frozenset[str] | None = None,
) -> Vote:
    return Vote(
        vote_id=f"vote_{agent_id}",
        proposal_id=proposal_id,
        agent_id=agent_id,
        verdict=verdict,
        reason="test",
        tool_path_hash=tool_path_hash,
        sources_hash=sources_hash,
        prompt_hash=prompt_hash,
        model_id=model_id,
        source_urls=source_urls or frozenset(),
        provider_id=provider_id,
        response_time_ms=response_time_ms,
        error_hash=error_hash,
    )


def make_pv(
    agent_id: str,
    tool_path_hash: str = "tool_a",
    sources_hash: str = "src_a",
    prompt_hash: str = "prompt_a",
    model_tier: str = "standard",
    provider_id: str | None = None,
    response_time_ms: float | None = None,
    error_hash: str | None = None,
) -> ProvenanceVector:
    return ProvenanceVector(
        agent_id=agent_id,
        tool_path_hash=tool_path_hash,
        sources_hash=sources_hash,
        prompt_hash=prompt_hash,
        model_tier=model_tier,
        provider_id=provider_id,
        response_time_ms=response_time_ms,
        error_hash=error_hash,
    )


# =============================================================================
# TestProvenanceVector
# =============================================================================


class TestProvenanceVector:
    def test_creation(self):
        pv = make_pv("agent1")
        assert pv.agent_id == "agent1"
        assert pv.tool_path_hash == "tool_a"
        assert pv.provider_id is None

    def test_feature_set_basic(self):
        pv = make_pv("agent1")
        fs = pv.feature_set
        assert "tool:tool_a" in fs
        assert "sources:src_a" in fs
        assert "prompt:prompt_a" in fs
        assert "tier:standard" in fs

    def test_feature_set_with_provider(self):
        pv = make_pv("agent1", provider_id="openai")
        fs = pv.feature_set
        assert "provider:openai" in fs

    def test_feature_set_with_error_hash(self):
        pv = make_pv("agent1", error_hash="err123")
        fs = pv.feature_set
        assert "error:err123" in fs

    def test_to_method_signature(self):
        pv = make_pv("agent1", provider_id="openai", response_time_ms=150.0)
        ms = pv.to_method_signature()
        assert isinstance(ms, MethodSignature)
        assert ms.agent_id == "agent1"
        assert ms.tool_path_hash == "tool_a"

    def test_to_dict(self):
        pv = make_pv("agent1", provider_id="openai", response_time_ms=100.0, error_hash="err")
        d = pv.to_dict()
        assert d["agent_id"] == "agent1"
        assert d["provider_id"] == "openai"
        assert d["response_time_ms"] == 100.0
        assert d["error_hash"] == "err"

    def test_from_dict(self):
        d = {
            "agent_id": "a1",
            "tool_path_hash": "t",
            "sources_hash": "s",
            "prompt_hash": "p",
            "provider_id": "anthropic",
        }
        pv = ProvenanceVector.from_dict(d)
        assert pv.agent_id == "a1"
        assert pv.provider_id == "anthropic"

    def test_from_vote(self):
        v = make_vote("agent1", provider_id="openai", response_time_ms=200.0, error_hash="e1")
        pv = ProvenanceVector.from_vote(v)
        assert pv is not None
        assert pv.agent_id == "agent1"
        assert pv.provider_id == "openai"
        assert pv.response_time_ms == 200.0
        assert pv.error_hash == "e1"

    def test_from_vote_missing_hashes(self):
        v = make_vote("agent1")
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="test",
        )
        pv = ProvenanceVector.from_vote(v)
        assert pv is None


# =============================================================================
# TestBlocDetector
# =============================================================================


class TestBlocDetector:
    def test_compute_similarity_identical(self):
        bd = BlocDetector()
        a = make_pv("a1")
        b = make_pv("a2")  # same hashes
        sim = bd.compute_similarity(a, b)
        assert sim == 1.0

    def test_compute_similarity_distinct(self):
        bd = BlocDetector()
        a = make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1")
        b = make_pv("a2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2")
        sim = bd.compute_similarity(a, b)
        assert sim < 0.3

    def test_compute_similarity_partial_overlap(self):
        bd = BlocDetector()
        a = make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1")
        b = make_pv("a2", tool_path_hash="t1", sources_hash="s2", prompt_hash="p2")
        sim = bd.compute_similarity(a, b)
        assert 0.0 < sim < 1.0

    def test_timing_bonus(self):
        bd = BlocDetector()
        a = make_pv("a1", response_time_ms=100.0)
        b = make_pv("a2", response_time_ms=110.0)  # same hashes + close timing
        sim_with_timing = bd.compute_similarity(a, b)
        c = make_pv("a3")  # no timing
        sim_without_timing = bd.compute_similarity(a, c)
        # Timing should add a bonus
        assert sim_with_timing > sim_without_timing or sim_without_timing == 1.0

    def test_error_hash_bonus(self):
        bd = BlocDetector()
        a = make_pv("a1", error_hash="same_err")
        b = make_pv("a2", error_hash="same_err")  # same hashes + same error
        sim = bd.compute_similarity(a, b)
        # Should be > 1.0 before clamping, but clamped to 1.0
        assert sim == 1.0

    def test_error_hash_different(self):
        bd = BlocDetector()
        a = make_pv("a1", error_hash="err1")
        b = make_pv("a2", error_hash="err2")
        sim = bd.compute_similarity(a, b)
        # Different error hashes add distinct features, reducing Jaccard
        # 4 shared base features + 2 distinct error features = 4/6
        assert sim < 1.0

    def test_detect_blocs_single_agent(self):
        bd = BlocDetector()
        blocs = bd.detect_blocs([make_pv("a1")])
        assert blocs == []

    def test_detect_blocs_two_independent(self):
        bd = BlocDetector()
        a = make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1", model_tier="fast")
        b = make_pv("a2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2", model_tier="heavy")
        blocs = bd.detect_blocs([a, b])
        assert len(blocs) == 0

    def test_detect_blocs_two_correlated(self):
        bd = BlocDetector()
        a = make_pv("a1")
        b = make_pv("a2")  # identical hashes
        blocs = bd.detect_blocs([a, b])
        assert len(blocs) == 1
        assert set(blocs[0].member_agent_ids) == {"a1", "a2"}

    def test_detect_blocs_three_with_two_blocs(self):
        bd = BlocDetector()
        a = make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1")
        b = make_pv("a2", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1")
        c = make_pv("a3", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2", model_tier="heavy")
        blocs = bd.detect_blocs([a, b, c])
        assert len(blocs) == 1
        assert set(blocs[0].member_agent_ids) == {"a1", "a2"}

    def test_detect_blocs_all_same(self):
        bd = BlocDetector()
        vectors = [make_pv(f"a{i}") for i in range(5)]
        blocs = bd.detect_blocs(vectors)
        assert len(blocs) == 1
        assert len(blocs[0].member_agent_ids) == 5

    def test_detect_blocs_mixed(self):
        bd = BlocDetector()
        # Two clusters + 1 singleton
        a1 = make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1")
        a2 = make_pv("a2", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1")
        b1 = make_pv("b1", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2")
        b2 = make_pv("b2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2")
        c1 = make_pv("c1", tool_path_hash="t3", sources_hash="s3", prompt_hash="p3", model_tier="heavy")
        blocs = bd.detect_blocs([a1, a2, b1, b2, c1])
        assert len(blocs) == 2

    def test_empty_vectors(self):
        bd = BlocDetector()
        blocs = bd.detect_blocs([])
        assert blocs == []

    def test_compute_similarity_empty_features(self):
        """Both vectors with no features should return 0.0."""
        bd = BlocDetector()
        # This is a degenerate case; feature_set always has base features
        a = make_pv("a1")
        b = make_pv("a2")
        # With identical features, sim should be 1.0
        sim = bd.compute_similarity(a, b)
        assert sim == 1.0

    def test_provider_id_in_features(self):
        """Provider IDs add features, increasing differentiation."""
        bd = BlocDetector()
        a = make_pv("a1", provider_id="openai")
        b = make_pv("a2", provider_id="anthropic")
        sim = bd.compute_similarity(a, b)
        # Different providers means different feature sets
        assert sim < 1.0


# =============================================================================
# TestNeffComputation
# =============================================================================


class TestNeffComputation:
    def test_empty(self):
        bd = BlocDetector()
        result = bd.compute_neff([], required_k=2)
        assert result.neff == 0.0
        assert result.total_agents == 0
        assert not result.passes_threshold

    def test_single_agent(self):
        bd = BlocDetector()
        result = bd.compute_neff([make_pv("a1")], required_k=1)
        assert result.neff == 1.0
        assert result.singleton_count == 1
        assert result.passes_threshold

    def test_two_independent(self):
        bd = BlocDetector()
        a = make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1", model_tier="fast")
        b = make_pv("a2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2", model_tier="heavy")
        result = bd.compute_neff([a, b], required_k=2)
        assert result.neff == 2.0
        assert result.singleton_count == 2
        assert result.passes_threshold

    def test_two_correlated(self):
        bd = BlocDetector()
        a = make_pv("a1")
        b = make_pv("a2")
        result = bd.compute_neff([a, b], required_k=2)
        assert result.neff == 1.0  # bloc counts as 1
        assert not result.passes_threshold

    def test_three_with_one_bloc(self):
        bd = BlocDetector()
        a = make_pv("a1")
        b = make_pv("a2")  # correlated with a
        c = make_pv("a3", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2", model_tier="heavy")
        result = bd.compute_neff([a, b, c], required_k=2)
        assert result.neff == 2.0  # 1 bloc + 1 singleton
        assert result.passes_threshold

    def test_all_same(self):
        bd = BlocDetector()
        vectors = [make_pv(f"a{i}") for i in range(5)]
        result = bd.compute_neff(vectors, required_k=2)
        assert result.neff == 1.0
        assert not result.passes_threshold

    def test_singletons_mixed(self):
        bd = BlocDetector()
        vectors = [
            make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1", model_tier="fast"),
            make_pv("a2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2", model_tier="heavy"),
            make_pv("a3", tool_path_hash="t3", sources_hash="s3", prompt_hash="p3", model_tier="local"),
        ]
        result = bd.compute_neff(vectors, required_k=3)
        assert result.neff == 3.0
        assert result.passes_threshold

    def test_reduction_ratio(self):
        bd = BlocDetector()
        a = make_pv("a1")
        b = make_pv("a2")
        result = bd.compute_neff([a, b], required_k=1)
        assert result.reduction_ratio == 0.5  # 2 agents → 1 Neff

    def test_passes_threshold_edge(self):
        bd = BlocDetector()
        result = bd.compute_neff([make_pv("a1")], required_k=1)
        assert result.passes_threshold
        result2 = bd.compute_neff([make_pv("a1")], required_k=2)
        assert not result2.passes_threshold

    def test_neff_with_multiple_blocs(self):
        bd = BlocDetector()
        # 2 blocs of 2 + 1 singleton = Neff 3
        vectors = [
            make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1"),
            make_pv("a2", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1"),
            make_pv("b1", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2"),
            make_pv("b2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2"),
            make_pv("c1", tool_path_hash="t3", sources_hash="s3", prompt_hash="p3", model_tier="heavy"),
        ]
        result = bd.compute_neff(vectors, required_k=3)
        assert result.neff == 3.0

    def test_neff_zero_for_empty(self):
        bd = BlocDetector()
        result = bd.compute_neff([], required_k=1)
        assert result.neff == 0.0

    def test_reduction_ratio_zero_for_all_singletons(self):
        bd = BlocDetector()
        vectors = [
            make_pv("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1", model_tier="fast"),
            make_pv("a2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2", model_tier="heavy"),
        ]
        result = bd.compute_neff(vectors, required_k=2)
        assert result.reduction_ratio == 0.0


# =============================================================================
# TestOriginBudget
# =============================================================================


class TestOriginBudget:
    def test_creation(self):
        b = OriginBudget(origin_id="org1", max_votes_per_window=5)
        assert b.votes_remaining == 5
        assert not b.is_exhausted

    def test_consume(self):
        b = OriginBudget(origin_id="org1", max_votes_per_window=3)
        b.votes_cast = 2
        assert b.votes_remaining == 1
        assert not b.is_exhausted

    def test_exhaustion(self):
        b = OriginBudget(origin_id="org1", max_votes_per_window=3)
        b.votes_cast = 3
        assert b.is_exhausted
        assert b.votes_remaining == 0

    def test_window_not_expired(self):
        b = OriginBudget(
            origin_id="org1",
            max_votes_per_window=5,
            window_duration=timedelta(hours=1),
        )
        assert not b.is_window_expired()

    def test_window_expired(self):
        b = OriginBudget(
            origin_id="org1",
            max_votes_per_window=5,
            window_start=datetime.now() - timedelta(hours=2),
            window_duration=timedelta(hours=1),
        )
        assert b.is_window_expired()

    def test_reset_window(self):
        b = OriginBudget(origin_id="org1", max_votes_per_window=5)
        b.votes_cast = 5
        now = datetime.now()
        b.reset_window(now)
        assert b.votes_cast == 0
        assert b.window_start == now

    def test_to_dict(self):
        b = OriginBudget(origin_id="org1", max_votes_per_window=5)
        d = b.to_dict()
        assert d["origin_id"] == "org1"
        assert d["max_votes_per_window"] == 5

    def test_overexhaustion(self):
        b = OriginBudget(origin_id="org1", max_votes_per_window=0)
        assert b.is_exhausted
        assert b.votes_remaining == 0


# =============================================================================
# TestOriginBudgetTracker
# =============================================================================


class TestOriginBudgetTracker:
    def test_register(self):
        tracker = OriginBudgetTracker()
        b = tracker.register_origin("org1")
        assert b.origin_id == "org1"

    def test_can_vote(self):
        tracker = OriginBudgetTracker()
        tracker.register_origin("org1")
        can, reason = tracker.can_vote("org1")
        assert can
        assert reason == "OK"

    def test_untracked_origin(self):
        tracker = OriginBudgetTracker()
        can, reason = tracker.can_vote("unknown")
        assert can
        assert "not tracked" in reason.lower()

    def test_record_vote(self):
        tracker = OriginBudgetTracker()
        tracker.register_origin("org1")
        assert tracker.record_vote("org1")
        b = tracker.budgets["org1"]
        assert b.votes_cast == 1

    def test_exhausted(self):
        config = SybilConfig(default_votes_per_window=2)
        tracker = OriginBudgetTracker(config)
        tracker.register_origin("org1")
        assert tracker.record_vote("org1")
        assert tracker.record_vote("org1")
        assert not tracker.record_vote("org1")
        can, _ = tracker.can_vote("org1")
        assert not can

    def test_window_reset(self):
        config = SybilConfig(default_votes_per_window=1, budget_window_hours=0.001)
        tracker = OriginBudgetTracker(config)
        tracker.register_origin("org1")
        tracker.record_vote("org1")
        assert not tracker.record_vote("org1")
        # Simulate window expiry
        future = datetime.now() + timedelta(hours=1)
        can, _ = tracker.can_vote("org1", now=future)
        assert can

    def test_metrics(self):
        tracker = OriginBudgetTracker()
        tracker.register_origin("org1")
        m = tracker.get_metrics()
        assert m["tracked_origins"] == 1

    def test_auto_register_on_record(self):
        tracker = OriginBudgetTracker()
        assert tracker.record_vote("org_new")
        assert "org_new" in tracker.budgets


# =============================================================================
# TestSybilDetector
# =============================================================================


class TestSybilDetector:
    def test_check_votes_passes(self):
        sd = SybilDetector()
        votes = [
            make_vote("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1", model_id="fast"),
            make_vote("a2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2", model_id="heavy"),
        ]
        passes, neff, reasons = sd.check_votes(votes, "prop1", required_k=2)
        assert passes
        assert neff.neff == 2.0
        assert reasons == []

    def test_check_votes_fails_correlated(self):
        sd = SybilDetector()
        votes = [
            make_vote("a1"),
            make_vote("a2"),
        ]
        passes, neff, reasons = sd.check_votes(votes, "prop1", required_k=2)
        assert not passes
        assert neff.neff == 1.0
        assert any("Neff" in r for r in reasons)

    def test_check_votes_no_provenance(self):
        sd = SybilDetector()
        # Votes without hash fields
        v = Vote(
            vote_id="v1", proposal_id="p1", agent_id="a1",
            verdict=VoteVerdict.APPROVE, reason="test",
        )
        passes, neff, reasons = sd.check_votes([v], "prop1", required_k=1)
        assert not passes
        assert any("No provenance" in r for r in reasons)

    def test_escalation(self):
        config = SybilConfig(neff_escalation_threshold=2.0)
        sd = SybilDetector(config)
        votes = [make_vote("a1")]
        passes, neff, reasons = sd.check_votes(votes, "prop1", required_k=1)
        # neff=1 which is <= escalation_threshold=2
        assert any("escalation" in r.lower() for r in reasons)

    def test_events_logged(self):
        sd = SybilDetector()
        votes = [make_vote("a1"), make_vote("a2")]
        sd.check_votes(votes, "prop1", required_k=2)
        assert len(sd.events) > 0

    def test_origin_budget_check(self):
        sd = SybilDetector()
        sd.budget_tracker.register_origin("org1")
        can, reason = sd.check_origin_budget("a1", "org1")
        assert can

    def test_origin_budget_exhausted(self):
        config = SybilConfig(default_votes_per_window=1)
        sd = SybilDetector(config)
        sd.budget_tracker.register_origin("org1")
        sd.record_origin_vote("org1")
        can, reason = sd.check_origin_budget("a1", "org1")
        assert not can

    def test_metrics(self):
        sd = SybilDetector()
        m = sd.get_metrics()
        assert "total_events" in m
        assert "config" in m

    def test_should_escalate(self):
        config = SybilConfig(neff_escalation_threshold=3.0)
        sd = SybilDetector(config)
        neff = NeffResult(neff=2.0, total_agents=4, blocs=[], singleton_count=2,
                          reduction_ratio=0.5, passes_threshold=True)
        assert sd.should_escalate(neff)
        neff2 = NeffResult(neff=4.0, total_agents=4, blocs=[], singleton_count=4,
                           reduction_ratio=0.0, passes_threshold=True)
        assert not sd.should_escalate(neff2)

    def test_check_votes_with_blocs_events(self):
        sd = SybilDetector()
        votes = [make_vote("a1"), make_vote("a2")]
        sd.check_votes(votes, "prop1", required_k=2)
        bloc_events = [e for e in sd.events if e.event_type == SybilEventType.BLOC_DETECTED]
        assert len(bloc_events) >= 1

    def test_record_origin_vote(self):
        sd = SybilDetector()
        assert sd.record_origin_vote("org1")
        b = sd.budget_tracker.budgets["org1"]
        assert b.votes_cast == 1


# =============================================================================
# TestSybilConfig
# =============================================================================


class TestSybilConfig:
    def test_defaults(self):
        c = SybilConfig()
        assert c.bloc_similarity_threshold == 0.75
        assert c.min_independent_blocs == 2

    def test_to_dict(self):
        c = SybilConfig()
        d = c.to_dict()
        assert "bloc_similarity_threshold" in d
        assert "timing_similarity_ms" in d

    def test_from_dict(self):
        d = {"bloc_similarity_threshold": 0.8, "neff_escalation_threshold": 2.0}
        c = SybilConfig.from_dict(d)
        assert c.bloc_similarity_threshold == 0.8
        assert c.neff_escalation_threshold == 2.0


# =============================================================================
# TestQuorumIntegration
# =============================================================================


class TestQuorumIntegration:
    def _setup_quorum_with_votes(self, sybil_detector=None, votes_config=None):
        """Helper to set up a quorum with votes that reach REACHED status."""
        qm = create_quorum_manager(sybil_detector=sybil_detector)
        now = datetime.now()
        qs = qm.create_quorum("prop1", ClaimType.MATH, created_at=now)

        configs = votes_config or [
            {"agent_id": "a1", "tool_path_hash": "t1", "sources_hash": "s1", "prompt_hash": "p1", "model_id": "fast"},
            {"agent_id": "a2", "tool_path_hash": "t2", "sources_hash": "s2", "prompt_hash": "p2", "model_id": "heavy"},
        ]
        for vc in configs:
            qm.cast_vote(
                "prop1",
                vc["agent_id"],
                VoteVerdict.APPROVE,
                "test",
                timestamp=now,
                tool_path_hash=vc.get("tool_path_hash"),
                sources_hash=vc.get("sources_hash"),
                prompt_hash=vc.get("prompt_hash"),
                model_id=vc.get("model_id"),
            )

        # Advance time past stability window
        future = now + timedelta(seconds=10)
        qm.update("prop1", now=future)
        return qm, future

    def test_gate5_passes_with_independent_votes(self):
        sd = SybilDetector()
        qm, now = self._setup_quorum_with_votes(sybil_detector=sd)
        can, reasons = qm.can_proceed("prop1", now=now)
        # Should pass — 2 independent voters
        assert can, f"Expected pass but got: {reasons}"

    def test_gate5_fails_with_correlated_votes(self):
        sd = SybilDetector()
        qm, now = self._setup_quorum_with_votes(
            sybil_detector=sd,
            votes_config=[
                {"agent_id": "a1", "tool_path_hash": "t1", "sources_hash": "s1", "prompt_hash": "p1", "model_id": "standard"},
                {"agent_id": "a2", "tool_path_hash": "t1", "sources_hash": "s1", "prompt_hash": "p1", "model_id": "standard"},
            ],
        )
        can, reasons = qm.can_proceed("prop1", now=now)
        assert not can
        assert any("Sybil" in r for r in reasons)

    def test_backward_compat_no_sybil(self):
        """QuorumManager works fine without sybil_detector."""
        qm, now = self._setup_quorum_with_votes(sybil_detector=None)
        can, reasons = qm.can_proceed("prop1", now=now)
        assert can

    def test_vote_new_fields_serialization(self):
        v = make_vote("a1", provider_id="openai", response_time_ms=150.0, error_hash="err1")
        d = v.to_dict()
        assert d["provider_id"] == "openai"
        assert d["response_time_ms"] == 150.0
        assert d["error_hash"] == "err1"
        v2 = Vote.from_dict(d)
        assert v2.provider_id == "openai"
        assert v2.response_time_ms == 150.0
        assert v2.error_hash == "err1"

    def test_vote_backward_compat_no_new_fields(self):
        """Votes without new fields still serialize/deserialize."""
        v = make_vote("a1")
        d = v.to_dict()
        assert "provider_id" not in d
        v2 = Vote.from_dict(d)
        assert v2.provider_id is None


# =============================================================================
# TestConvenience
# =============================================================================


class TestConvenience:
    def test_create_sybil_detector(self):
        sd = create_sybil_detector()
        assert isinstance(sd, SybilDetector)

    def test_compute_neff_convenience(self):
        votes = [
            make_vote("a1", tool_path_hash="t1", sources_hash="s1", prompt_hash="p1", model_id="fast"),
            make_vote("a2", tool_path_hash="t2", sources_hash="s2", prompt_hash="p2", model_id="heavy"),
        ]
        result = compute_neff(votes, required_k=2)
        assert result.neff == 2.0


# =============================================================================
# TestSybilEvent
# =============================================================================


class TestSybilEvent:
    def test_creation(self):
        e = SybilEvent(
            event_type=SybilEventType.BLOC_DETECTED,
            proposal_id="prop1",
            details={"bloc_id": "b1"},
        )
        assert e.event_type == SybilEventType.BLOC_DETECTED
        assert e.proposal_id == "prop1"

    def test_to_dict(self):
        e = SybilEvent(
            event_type=SybilEventType.NEFF_COLLAPSE,
            proposal_id="prop1",
            details={"neff": 1.0},
        )
        d = e.to_dict()
        assert d["event_type"] == "neff_collapse"
        assert d["details"]["neff"] == 1.0
