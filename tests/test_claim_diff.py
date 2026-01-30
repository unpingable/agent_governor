"""
Tests for claim_diff module — epistemic state change detection.

Tests cover:
- ClaimSnapshot creation and immutability
- LedgerSnapshot capture and indexing
- MutationType enum completeness and severity ordering
- MutationEvent creation
- ClaimPair preserved/mutated classification, drift/laundering properties
- DiffResult buckets, summary, aggregates
- ClaimDiffer core diffing: all mutation types, hash pairing, thresholds
- Confidence drift detection with severity scaling
- Provenance laundering detection
- Evidence erosion detection
- Silent retraction detection
- DiffHistory tracking and trends
- Convenience functions
- Integration: full turn cycles, multi-turn trends
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from governor.claim_diff import (
    MutationType,
    ViolationType,
    MUTATION_SEVERITY,
    PROVENANCE_TRUST,
    ClaimSnapshot,
    LedgerSnapshot,
    MutationEvent,
    ClaimPair,
    Violation,
    DiffResult,
    DiffHistory,
    ClaimDiffer,
    snapshot_ledger,
    diff_snapshots,
    detect_laundering,
    detect_confidence_drift,
    _is_provenance_upgrade,
    _is_provenance_downgrade,
)
from governor.epistemic import (
    Provenance,
    EvidenceType,
    EvidenceRef,
    GroundedClaim,
    GroundedClaimStatus,
    EpistemicLedger,
)


# =============================================================================
# Helpers
# =============================================================================


def _make_claim_snapshot(
    claim_id: str = "gc_test001",
    content: str = "test claim",
    provenance: str = "assumed",
    confidence: float = 0.3,
    evidence_count: int = 0,
    evidence_ref_ids: tuple[str, ...] = (),
    status: str = "active",
    is_grounded: bool = False,
    is_dangerous: bool = False,
    source_agent_id: str | None = None,
) -> ClaimSnapshot:
    import hashlib
    content_hash = hashlib.sha256(content.lower().strip().encode()).hexdigest()[:16]
    return ClaimSnapshot(
        claim_id=claim_id,
        content=content,
        content_hash=content_hash,
        provenance=provenance,
        confidence=confidence,
        evidence_count=evidence_count,
        evidence_ref_ids=evidence_ref_ids,
        status=status,
        is_grounded=is_grounded,
        is_dangerous=is_dangerous,
        source_agent_id=source_agent_id,
    )


def _make_ledger_snapshot(
    step: int = 0,
    claims: dict[str, ClaimSnapshot] | None = None,
) -> LedgerSnapshot:
    if claims is None:
        claims = {}

    claims_by_hash: dict[str, list[str]] = {}
    for cid, snap in claims.items():
        if snap.content_hash not in claims_by_hash:
            claims_by_hash[snap.content_hash] = []
        claims_by_hash[snap.content_hash].append(cid)

    active = [c for c in claims.values() if c.status == "active"]
    dangerous = [c for c in active if c.is_dangerous]

    return LedgerSnapshot(
        step=step,
        timestamp=datetime.now(),
        claims=claims,
        claims_by_hash=claims_by_hash,
        total_claims=len(claims),
        active_count=len(active),
        dangerous_count=len(dangerous),
    )


def _make_evidence_ref(ref_id: str = "ev_test01") -> EvidenceRef:
    return EvidenceRef(
        ref_id=ref_id,
        ref_type=EvidenceType.TOOL_TRACE,
        locator="trace-123",
        scope="full",
        retrieved_at=datetime.now(),
    )


# =============================================================================
# TestClaimSnapshot
# =============================================================================


class TestClaimSnapshot:
    def test_create_basic(self):
        snap = _make_claim_snapshot()
        assert snap.claim_id == "gc_test001"
        assert snap.content == "test claim"
        assert snap.provenance == "assumed"
        assert snap.confidence == 0.3

    def test_frozen(self):
        snap = _make_claim_snapshot()
        with pytest.raises(AttributeError):
            snap.confidence = 0.5  # type: ignore

    def test_content_hash_consistent(self):
        s1 = _make_claim_snapshot(content="hello world")
        s2 = _make_claim_snapshot(content="hello world")
        assert s1.content_hash == s2.content_hash

    def test_content_hash_differs(self):
        s1 = _make_claim_snapshot(content="hello world")
        s2 = _make_claim_snapshot(content="different content")
        assert s1.content_hash != s2.content_hash

    def test_from_grounded_claim(self):
        ledger = EpistemicLedger()
        claim = ledger.new_claim("test assertion", Provenance.ASSUMED, 0.4)
        snap = ClaimSnapshot.from_grounded_claim(claim)
        assert snap.claim_id == claim.claim_id
        assert snap.content == "test assertion"
        assert snap.provenance == "assumed"
        assert snap.confidence == 0.4
        assert snap.evidence_count == 0
        assert snap.status == "active"

    def test_from_grounded_claim_with_evidence(self):
        ledger = EpistemicLedger()
        claim = ledger.new_claim("test", Provenance.RETRIEVED, 0.85)
        ev = _make_evidence_ref("ev_abc")
        ledger.attach_evidence(claim.claim_id, ev)
        snap = ClaimSnapshot.from_grounded_claim(claim)
        assert snap.evidence_count == 1
        assert "ev_abc" in snap.evidence_ref_ids
        assert snap.is_grounded is True

    def test_to_dict(self):
        snap = _make_claim_snapshot(source_agent_id="agent-1")
        d = snap.to_dict()
        assert d["claim_id"] == "gc_test001"
        assert d["provenance"] == "assumed"
        assert d["source_agent_id"] == "agent-1"

    def test_dangerous_flag(self):
        snap = _make_claim_snapshot(
            confidence=0.9, is_grounded=False, is_dangerous=True
        )
        assert snap.is_dangerous is True


# =============================================================================
# TestLedgerSnapshot
# =============================================================================


class TestLedgerSnapshot:
    def test_empty_snapshot(self):
        snap = _make_ledger_snapshot(step=5)
        assert snap.step == 5
        assert snap.total_claims == 0
        assert snap.active_count == 0
        assert snap.dangerous_count == 0

    def test_snapshot_with_claims(self):
        c1 = _make_claim_snapshot(claim_id="c1", content="claim one")
        c2 = _make_claim_snapshot(claim_id="c2", content="claim two")
        snap = _make_ledger_snapshot(step=3, claims={"c1": c1, "c2": c2})
        assert snap.total_claims == 2
        assert snap.active_count == 2

    def test_hash_index(self):
        c1 = _make_claim_snapshot(claim_id="c1", content="same content")
        c2 = _make_claim_snapshot(claim_id="c2", content="same content")
        snap = _make_ledger_snapshot(claims={"c1": c1, "c2": c2})
        # Both should map to the same hash
        assert len(snap.claims_by_hash) == 1
        hash_key = list(snap.claims_by_hash.keys())[0]
        assert len(snap.claims_by_hash[hash_key]) == 2

    def test_from_ledger(self):
        ledger = EpistemicLedger()
        ledger.step = 7
        ledger.new_claim("first claim", Provenance.ASSUMED)
        ledger.new_claim("second claim", Provenance.RETRIEVED)
        snap = LedgerSnapshot.from_ledger(ledger)
        assert snap.step == 7
        assert snap.total_claims == 2
        assert snap.active_count == 2

    def test_dangerous_count(self):
        # Create a claim that will be dangerous: high confidence + ungrounded
        c1 = _make_claim_snapshot(
            claim_id="c1", content="risky", confidence=0.9,
            is_dangerous=True, status="active"
        )
        snap = _make_ledger_snapshot(claims={"c1": c1})
        assert snap.dangerous_count == 1

    def test_to_dict(self):
        snap = _make_ledger_snapshot(step=2)
        d = snap.to_dict()
        assert d["step"] == 2
        assert d["total_claims"] == 0

    def test_inactive_not_counted(self):
        c1 = _make_claim_snapshot(claim_id="c1", content="retracted", status="retracted")
        snap = _make_ledger_snapshot(claims={"c1": c1})
        assert snap.total_claims == 1
        assert snap.active_count == 0


# =============================================================================
# TestMutationType
# =============================================================================


class TestMutationType:
    def test_all_types_have_severity(self):
        for mt in MutationType:
            assert mt in MUTATION_SEVERITY

    def test_severity_ordering(self):
        assert MUTATION_SEVERITY[MutationType.PROVENANCE_UPGRADE] > MUTATION_SEVERITY[MutationType.CONFIDENCE_INCREASE]
        assert MUTATION_SEVERITY[MutationType.CONFIDENCE_INCREASE] > MUTATION_SEVERITY[MutationType.EVIDENCE_REMOVED]
        assert MUTATION_SEVERITY[MutationType.EVIDENCE_ADDED] == 0.0

    def test_enum_values(self):
        assert len(MutationType) == 8


# =============================================================================
# TestMutationEvent
# =============================================================================


class TestMutationEvent:
    def test_create(self):
        ev = MutationEvent(
            mutation_type=MutationType.CONFIDENCE_INCREASE,
            severity=0.8,
            claim_id="c1",
            content_hash="abc123",
            field_name="confidence",
            old_value=0.3,
            new_value=0.6,
        )
        assert ev.mutation_type == MutationType.CONFIDENCE_INCREASE
        assert ev.severity == 0.8

    def test_to_dict(self):
        ev = MutationEvent(
            mutation_type=MutationType.STATUS_CHANGED,
            severity=0.4,
            claim_id="c1",
            content_hash="abc",
            field_name="status",
            old_value="active",
            new_value="blocked",
            details="Status changed",
        )
        d = ev.to_dict()
        assert d["mutation_type"] == "status_changed"
        assert d["details"] == "Status changed"

    def test_details_default(self):
        ev = MutationEvent(
            mutation_type=MutationType.EVIDENCE_ADDED,
            severity=0.0,
            claim_id="c1",
            content_hash="abc",
            field_name="evidence",
            old_value=0,
            new_value=1,
        )
        assert ev.details == ""


# =============================================================================
# TestClaimPair
# =============================================================================


class TestClaimPair:
    def test_preserved_when_no_mutations(self):
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after)
        assert pair.is_preserved is True
        assert pair.total_severity == 0.0

    def test_mutated_when_has_mutations(self):
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after, mutations=[
            MutationEvent(
                mutation_type=MutationType.CONFIDENCE_INCREASE,
                severity=0.8,
                claim_id="c1",
                content_hash="abc",
                field_name="confidence",
                old_value=0.3,
                new_value=0.6,
            )
        ])
        assert pair.is_preserved is False
        assert pair.total_severity == 0.8

    def test_has_confidence_drift_true(self):
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after, mutations=[
            MutationEvent(
                mutation_type=MutationType.CONFIDENCE_INCREASE,
                severity=0.8,
                claim_id="c1",
                content_hash="abc",
                field_name="confidence",
                old_value=0.3,
                new_value=0.6,
            )
        ])
        assert pair.has_confidence_drift is True

    def test_no_confidence_drift_when_evidence_added(self):
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after, mutations=[
            MutationEvent(
                mutation_type=MutationType.CONFIDENCE_INCREASE,
                severity=0.8,
                claim_id="c1",
                content_hash="abc",
                field_name="confidence",
                old_value=0.3,
                new_value=0.6,
            ),
            MutationEvent(
                mutation_type=MutationType.EVIDENCE_ADDED,
                severity=0.0,
                claim_id="c1",
                content_hash="abc",
                field_name="evidence",
                old_value=0,
                new_value=1,
            ),
        ])
        assert pair.has_confidence_drift is False

    def test_has_provenance_laundering_true(self):
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after, mutations=[
            MutationEvent(
                mutation_type=MutationType.PROVENANCE_UPGRADE,
                severity=1.0,
                claim_id="c1",
                content_hash="abc",
                field_name="provenance",
                old_value="assumed",
                new_value="retrieved",
            )
        ])
        assert pair.has_provenance_laundering is True

    def test_no_laundering_when_evidence_added(self):
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after, mutations=[
            MutationEvent(
                mutation_type=MutationType.PROVENANCE_UPGRADE,
                severity=1.0,
                claim_id="c1",
                content_hash="abc",
                field_name="provenance",
                old_value="assumed",
                new_value="retrieved",
            ),
            MutationEvent(
                mutation_type=MutationType.EVIDENCE_ADDED,
                severity=0.0,
                claim_id="c1",
                content_hash="abc",
                field_name="evidence",
                old_value=0,
                new_value=1,
            ),
        ])
        assert pair.has_provenance_laundering is False

    def test_total_severity_accumulates(self):
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after, mutations=[
            MutationEvent(
                mutation_type=MutationType.CONFIDENCE_INCREASE,
                severity=0.8,
                claim_id="c1",
                content_hash="abc",
                field_name="confidence",
                old_value=0.3,
                new_value=0.6,
            ),
            MutationEvent(
                mutation_type=MutationType.STATUS_CHANGED,
                severity=0.4,
                claim_id="c1",
                content_hash="abc",
                field_name="status",
                old_value="active",
                new_value="blocked",
            ),
        ])
        assert pair.total_severity == pytest.approx(1.2)

    def test_no_drift_no_laundering_default(self):
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after)
        assert pair.has_confidence_drift is False
        assert pair.has_provenance_laundering is False


# =============================================================================
# TestDiffResult
# =============================================================================


class TestDiffResult:
    def _make_result(self) -> DiffResult:
        now = datetime.now()
        return DiffResult(
            before_step=0,
            after_step=1,
            before_timestamp=now,
            after_timestamp=now + timedelta(seconds=1),
        )

    def test_empty_result(self):
        r = self._make_result()
        assert r.total_mutations == 0
        assert r.total_severity == 0.0
        assert r.has_violations is False
        assert r.confidence_drift_count == 0
        assert r.provenance_laundering_count == 0

    def test_with_preserved(self):
        r = self._make_result()
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        r.preserved.append(ClaimPair(before=before, after=after))
        assert len(r.preserved) == 1
        assert r.total_mutations == 0

    def test_with_mutated(self):
        r = self._make_result()
        before = _make_claim_snapshot()
        after = _make_claim_snapshot()
        pair = ClaimPair(before=before, after=after, mutations=[
            MutationEvent(
                mutation_type=MutationType.CONFIDENCE_INCREASE,
                severity=0.8,
                claim_id="c1",
                content_hash="abc",
                field_name="confidence",
                old_value=0.3,
                new_value=0.6,
            ),
        ])
        r.mutated.append(pair)
        assert r.total_mutations == 1
        assert r.total_severity == pytest.approx(0.8)

    def test_with_added(self):
        r = self._make_result()
        r.added.append(_make_claim_snapshot(claim_id="new"))
        assert len(r.added) == 1

    def test_with_dropped(self):
        r = self._make_result()
        r.dropped.append(_make_claim_snapshot(claim_id="old"))
        assert len(r.dropped) == 1

    def test_with_violations(self):
        r = self._make_result()
        r.violations.append(Violation(
            violation_type=ViolationType.CONFIDENCE_DRIFT,
            severity=0.5,
            claim_id="c1",
            content_hash="abc",
            content_summary="test",
            details="drift detected",
        ))
        assert r.has_violations is True
        assert r.confidence_drift_count == 1
        assert r.provenance_laundering_count == 0

    def test_summary(self):
        r = self._make_result()
        s = r.summary
        assert s["steps"] == "0 -> 1"
        assert s["preserved"] == 0
        assert s["violations"] == 0

    def test_to_dict(self):
        r = self._make_result()
        d = r.to_dict()
        assert "before_step" in d
        assert "summary" in d
        assert "violations" in d

    def test_multiple_violations(self):
        r = self._make_result()
        r.violations.append(Violation(
            violation_type=ViolationType.CONFIDENCE_DRIFT,
            severity=0.5,
            claim_id="c1",
            content_hash="abc",
            content_summary="test1",
            details="drift",
        ))
        r.violations.append(Violation(
            violation_type=ViolationType.PROVENANCE_LAUNDERING,
            severity=1.0,
            claim_id="c2",
            content_hash="def",
            content_summary="test2",
            details="laundering",
        ))
        assert r.confidence_drift_count == 1
        assert r.provenance_laundering_count == 1
        assert len(r.violations) == 2


# =============================================================================
# TestClaimDiffer (core diffing)
# =============================================================================


class TestClaimDiffer:
    def test_empty_diff(self):
        before = _make_ledger_snapshot(step=0)
        after = _make_ledger_snapshot(step=1)
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert len(result.preserved) == 0
        assert len(result.mutated) == 0
        assert len(result.added) == 0
        assert len(result.dropped) == 0

    def test_identical_snapshots(self):
        c1 = _make_claim_snapshot(claim_id="c1", content="stable claim")
        before = _make_ledger_snapshot(step=0, claims={"c1": c1})
        after = _make_ledger_snapshot(step=1, claims={"c1": c1})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert len(result.preserved) == 1
        assert len(result.mutated) == 0

    def test_added_claim(self):
        before = _make_ledger_snapshot(step=0)
        c1 = _make_claim_snapshot(claim_id="c1", content="new claim")
        after = _make_ledger_snapshot(step=1, claims={"c1": c1})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert len(result.added) == 1
        assert result.added[0].claim_id == "c1"

    def test_dropped_claim(self):
        c1 = _make_claim_snapshot(claim_id="c1", content="old claim")
        before = _make_ledger_snapshot(step=0, claims={"c1": c1})
        after = _make_ledger_snapshot(step=1)
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert len(result.dropped) == 1
        assert result.dropped[0].claim_id == "c1"

    def test_confidence_increase_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="test", confidence=0.3
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="test", confidence=0.6
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert len(result.mutated) == 1
        mutations = result.mutated[0].mutations
        assert any(m.mutation_type == MutationType.CONFIDENCE_INCREASE for m in mutations)

    def test_confidence_decrease_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="test", confidence=0.6
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="test", confidence=0.3
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert len(result.mutated) == 1
        mutations = result.mutated[0].mutations
        assert any(m.mutation_type == MutationType.CONFIDENCE_DECREASE for m in mutations)

    def test_provenance_upgrade_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="test", provenance="assumed"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="test", provenance="retrieved"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert len(result.mutated) == 1
        mutations = result.mutated[0].mutations
        assert any(m.mutation_type == MutationType.PROVENANCE_UPGRADE for m in mutations)

    def test_provenance_downgrade_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="test", provenance="retrieved"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="test", provenance="assumed"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        mutations = result.mutated[0].mutations
        assert any(m.mutation_type == MutationType.PROVENANCE_DOWNGRADE for m in mutations)

    def test_evidence_added_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="test", evidence_count=0, evidence_ref_ids=()
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="test", evidence_count=1, evidence_ref_ids=("ev_1",)
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        mutations = result.mutated[0].mutations
        assert any(m.mutation_type == MutationType.EVIDENCE_ADDED for m in mutations)

    def test_evidence_removed_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="test", evidence_count=2,
            evidence_ref_ids=("ev_1", "ev_2"),
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="test", evidence_count=0, evidence_ref_ids=()
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        mutations = result.mutated[0].mutations
        assert any(m.mutation_type == MutationType.EVIDENCE_REMOVED for m in mutations)

    def test_status_change_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="test", status="active"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="test", status="blocked"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        mutations = result.mutated[0].mutations
        assert any(m.mutation_type == MutationType.STATUS_CHANGED for m in mutations)

    def test_below_threshold_not_flagged(self):
        """Confidence change below threshold should not create CONFIDENCE_INCREASE mutation."""
        c_before = _make_claim_snapshot(
            claim_id="c1", content="test", confidence=0.30
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="test", confidence=0.33
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer(confidence_drift_threshold=0.05)
        result = differ.diff(before, after)
        # Small increase below threshold => preserved, not mutated
        assert len(result.preserved) == 1
        assert len(result.mutated) == 0

    def test_multiple_claims_diff(self):
        c1_before = _make_claim_snapshot(claim_id="c1", content="claim one", confidence=0.3)
        c2_before = _make_claim_snapshot(claim_id="c2", content="claim two", confidence=0.5)
        c1_after = _make_claim_snapshot(claim_id="c1", content="claim one", confidence=0.7)
        c2_after = _make_claim_snapshot(claim_id="c2", content="claim two", confidence=0.5)

        before = _make_ledger_snapshot(step=0, claims={"c1": c1_before, "c2": c2_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c1_after, "c2": c2_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert len(result.preserved) == 1  # c2 unchanged
        assert len(result.mutated) == 1  # c1 changed


# =============================================================================
# TestConfidenceDriftDetection
# =============================================================================


class TestConfidenceDriftDetection:
    def test_drift_detected_without_evidence(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="drifty", confidence=0.3,
            evidence_count=0, evidence_ref_ids=()
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="drifty", confidence=0.6,
            evidence_count=0, evidence_ref_ids=()
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.confidence_drift_count == 1

    def test_no_drift_when_evidence_added(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="grounded", confidence=0.3,
            evidence_count=0, evidence_ref_ids=()
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="grounded", confidence=0.6,
            evidence_count=1, evidence_ref_ids=("ev_1",)
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.confidence_drift_count == 0

    def test_drift_severity_scales_with_delta(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="big drift", confidence=0.1
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="big drift", confidence=0.6
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.confidence_drift_count == 1
        # delta = 0.5, severity = min(1.0, 0.5 * 2.0) = 1.0
        assert result.violations[0].severity == pytest.approx(1.0)

    def test_small_drift_lower_severity(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="small drift", confidence=0.3
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="small drift", confidence=0.4
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.confidence_drift_count == 1
        # delta = 0.1, severity = min(1.0, 0.1 * 2.0) = 0.2
        assert result.violations[0].severity == pytest.approx(0.2)

    def test_drift_below_threshold_no_violation(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="tiny", confidence=0.30
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="tiny", confidence=0.33
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer(confidence_drift_threshold=0.05)
        result = differ.diff(before, after)
        assert result.confidence_drift_count == 0

    def test_drift_detection_toggle(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="toggle", confidence=0.3
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="toggle", confidence=0.8
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer(detect_confidence_drift=False)
        result = differ.diff(before, after)
        # Mutations still detected, but no violation
        assert len(result.mutated) == 1
        assert result.confidence_drift_count == 0


# =============================================================================
# TestProvenanceLaunderingDetection
# =============================================================================


class TestProvenanceLaunderingDetection:
    def test_laundering_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="laundered", provenance="assumed"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="laundered", provenance="retrieved"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.provenance_laundering_count == 1

    def test_no_laundering_with_evidence(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="legit",
            provenance="assumed", evidence_ref_ids=()
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="legit",
            provenance="retrieved", evidence_ref_ids=("ev_1",)
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.provenance_laundering_count == 0

    def test_laundering_always_severity_1(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="max", provenance="assumed"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="max", provenance="observed"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.provenance_laundering_count == 1
        assert result.violations[0].severity == 1.0

    def test_downgrade_not_laundering(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="downgraded", provenance="retrieved"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="downgraded", provenance="assumed"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.provenance_laundering_count == 0

    def test_laundering_detection_toggle(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="toggle", provenance="assumed"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="toggle", provenance="retrieved"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer(detect_provenance_laundering=False)
        result = differ.diff(before, after)
        assert result.provenance_laundering_count == 0

    def test_peer_to_retrieved_is_laundering(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="peer", provenance="peer_asserted"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="peer", provenance="retrieved"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.provenance_laundering_count == 1


# =============================================================================
# TestEvidenceErosionDetection
# =============================================================================


class TestEvidenceErosionDetection:
    def test_erosion_detected(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="eroded",
            evidence_count=3, evidence_ref_ids=("e1", "e2", "e3"),
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="eroded",
            evidence_count=0, evidence_ref_ids=(),
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        erosion_violations = [
            v for v in result.violations
            if v.violation_type == ViolationType.EVIDENCE_EROSION
        ]
        assert len(erosion_violations) == 1

    def test_no_erosion_when_replaced(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="replaced",
            evidence_count=1, evidence_ref_ids=("e1",),
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="replaced",
            evidence_count=1, evidence_ref_ids=("e2",),
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        erosion = [
            v for v in result.violations
            if v.violation_type == ViolationType.EVIDENCE_EROSION
        ]
        assert len(erosion) == 0

    def test_erosion_proportional_severity(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="partial",
            evidence_count=4, evidence_ref_ids=("e1", "e2", "e3", "e4"),
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="partial",
            evidence_count=2, evidence_ref_ids=("e3", "e4"),
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        erosion = [
            v for v in result.violations
            if v.violation_type == ViolationType.EVIDENCE_EROSION
        ]
        assert len(erosion) == 1
        # lost 2 of 4, severity = 2/4 = 0.5
        assert erosion[0].severity == pytest.approx(0.5)

    def test_erosion_detection_toggle(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="toggle",
            evidence_count=2, evidence_ref_ids=("e1", "e2"),
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="toggle",
            evidence_count=0, evidence_ref_ids=(),
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer(detect_evidence_erosion=False)
        result = differ.diff(before, after)
        erosion = [
            v for v in result.violations
            if v.violation_type == ViolationType.EVIDENCE_EROSION
        ]
        assert len(erosion) == 0


# =============================================================================
# TestSilentRetractionDetection
# =============================================================================


class TestSilentRetractionDetection:
    def test_silent_retraction_detected(self):
        c1 = _make_claim_snapshot(
            claim_id="c1", content="silently dropped", status="active"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c1})
        after = _make_ledger_snapshot(step=1)
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        retraction_violations = [
            v for v in result.violations
            if v.violation_type == ViolationType.SILENT_RETRACTION
        ]
        assert len(retraction_violations) == 1
        assert retraction_violations[0].severity == 0.7

    def test_retracted_claim_not_silent(self):
        c1 = _make_claim_snapshot(
            claim_id="c1", content="properly retracted", status="retracted"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c1})
        after = _make_ledger_snapshot(step=1)
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        retraction_violations = [
            v for v in result.violations
            if v.violation_type == ViolationType.SILENT_RETRACTION
        ]
        assert len(retraction_violations) == 0

    def test_blocked_claim_not_silent(self):
        c1 = _make_claim_snapshot(
            claim_id="c1", content="blocked", status="blocked"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c1})
        after = _make_ledger_snapshot(step=1)
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        retraction_violations = [
            v for v in result.violations
            if v.violation_type == ViolationType.SILENT_RETRACTION
        ]
        assert len(retraction_violations) == 0

    def test_silent_retraction_toggle(self):
        c1 = _make_claim_snapshot(
            claim_id="c1", content="toggle drop", status="active"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c1})
        after = _make_ledger_snapshot(step=1)
        differ = ClaimDiffer(detect_silent_retraction=False)
        result = differ.diff(before, after)
        retraction_violations = [
            v for v in result.violations
            if v.violation_type == ViolationType.SILENT_RETRACTION
        ]
        assert len(retraction_violations) == 0


# =============================================================================
# TestDiffHistory
# =============================================================================


class TestDiffHistory:
    def _make_diff_result(self, drift_count: int = 0, laundering_count: int = 0, severity: float = 0.0) -> DiffResult:
        now = datetime.now()
        r = DiffResult(
            before_step=0, after_step=1,
            before_timestamp=now, after_timestamp=now,
        )
        for _ in range(drift_count):
            r.violations.append(Violation(
                violation_type=ViolationType.CONFIDENCE_DRIFT,
                severity=severity / max(1, drift_count + laundering_count),
                claim_id="c1", content_hash="abc",
                content_summary="test", details="drift",
            ))
        for _ in range(laundering_count):
            r.violations.append(Violation(
                violation_type=ViolationType.PROVENANCE_LAUNDERING,
                severity=1.0,
                claim_id="c2", content_hash="def",
                content_summary="test", details="launder",
            ))
        return r

    def test_add(self):
        history = DiffHistory()
        history.add(self._make_diff_result())
        assert len(history.diffs) == 1

    def test_max_cap(self):
        history = DiffHistory(max_history=3)
        for _ in range(5):
            history.add(self._make_diff_result())
        assert len(history.diffs) == 3

    def test_confidence_drift_trend(self):
        history = DiffHistory()
        history.add(self._make_diff_result(drift_count=1))
        history.add(self._make_diff_result(drift_count=0))
        history.add(self._make_diff_result(drift_count=3))
        assert history.confidence_drift_trend() == [1, 0, 3]

    def test_laundering_trend(self):
        history = DiffHistory()
        history.add(self._make_diff_result(laundering_count=2))
        history.add(self._make_diff_result(laundering_count=0))
        assert history.laundering_trend() == [2, 0]

    def test_violation_trend(self):
        history = DiffHistory()
        history.add(self._make_diff_result(drift_count=1, laundering_count=1))
        history.add(self._make_diff_result(drift_count=0, laundering_count=0))
        assert history.violation_trend() == [2, 0]

    def test_to_dict(self):
        history = DiffHistory(max_history=50)
        history.add(self._make_diff_result())
        d = history.to_dict()
        assert d["max_history"] == 50
        assert d["count"] == 1


# =============================================================================
# TestConvenienceFunctions
# =============================================================================


class TestConvenienceFunctions:
    def test_snapshot_ledger(self):
        ledger = EpistemicLedger()
        ledger.step = 5
        ledger.new_claim("hello", Provenance.ASSUMED)
        snap = snapshot_ledger(ledger)
        assert snap.step == 5
        assert snap.total_claims == 1

    def test_diff_snapshots(self):
        ledger1 = EpistemicLedger()
        ledger1.new_claim("stable", Provenance.ASSUMED)
        snap1 = snapshot_ledger(ledger1)

        ledger2 = EpistemicLedger()
        ledger2.step = 1
        # Re-create with same content but higher confidence to simulate drift
        c = ledger2.new_claim("stable", Provenance.ASSUMED, confidence=0.7)
        snap2 = snapshot_ledger(ledger2)

        result = diff_snapshots(snap1, snap2)
        assert result.before_step == 0
        assert result.after_step == 1

    def test_detect_laundering(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="launder test", provenance="assumed"
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="launder test", provenance="retrieved"
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        violations = detect_laundering(before, after)
        assert len(violations) == 1
        assert violations[0].violation_type == ViolationType.PROVENANCE_LAUNDERING

    def test_detect_confidence_drift(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="drift test", confidence=0.3
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="drift test", confidence=0.8
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        violations = detect_confidence_drift(before, after)
        assert len(violations) == 1
        assert violations[0].violation_type == ViolationType.CONFIDENCE_DRIFT

    def test_detect_confidence_drift_custom_threshold(self):
        c_before = _make_claim_snapshot(
            claim_id="c1", content="threshold test", confidence=0.30
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="threshold test", confidence=0.40
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        # Threshold 0.05 should detect (delta=0.10)
        violations = detect_confidence_drift(before, after, threshold=0.05)
        assert len(violations) == 1
        # Higher threshold should not detect (delta=0.10 < 0.15)
        violations = detect_confidence_drift(before, after, threshold=0.15)
        assert len(violations) == 0


# =============================================================================
# TestProvenance helpers
# =============================================================================


class TestProvenanceHelpers:
    def test_provenance_upgrade(self):
        assert _is_provenance_upgrade("assumed", "retrieved") is True
        assert _is_provenance_upgrade("assumed", "observed") is True
        assert _is_provenance_upgrade("peer_asserted", "derived") is True

    def test_provenance_downgrade(self):
        assert _is_provenance_downgrade("retrieved", "assumed") is True
        assert _is_provenance_downgrade("observed", "assumed") is True

    def test_same_level(self):
        assert _is_provenance_upgrade("assumed", "assumed") is False
        assert _is_provenance_downgrade("assumed", "assumed") is False

    def test_trust_ordering(self):
        assert PROVENANCE_TRUST["observed"] > PROVENANCE_TRUST["retrieved"]
        assert PROVENANCE_TRUST["retrieved"] > PROVENANCE_TRUST["user_provided"]
        assert PROVENANCE_TRUST["user_provided"] > PROVENANCE_TRUST["derived"]
        assert PROVENANCE_TRUST["derived"] > PROVENANCE_TRUST["peer_asserted"]
        assert PROVENANCE_TRUST["peer_asserted"] > PROVENANCE_TRUST["assumed"]


# =============================================================================
# TestIntegration
# =============================================================================


class TestIntegration:
    def test_full_turn_cycle(self):
        """Simulate a full turn: create claims, snapshot, modify, snapshot, diff."""
        ledger = EpistemicLedger()
        c1 = ledger.new_claim("Python uses indentation", Provenance.ASSUMED, 0.3)
        c2 = ledger.new_claim("The sky is blue", Provenance.RETRIEVED, 0.85)
        ev = _make_evidence_ref("ev_sky")
        ledger.attach_evidence(c2.claim_id, ev)

        snap1 = snapshot_ledger(ledger)
        assert snap1.total_claims == 2

        # Simulate turn: boost confidence on c1 without evidence (drift!)
        ledger.tick()
        c1.confidence = 0.7  # Direct mutation bypassing rules

        snap2 = snapshot_ledger(ledger)
        result = diff_snapshots(snap1, snap2)

        assert result.before_step == 0
        assert result.after_step == 1
        assert result.confidence_drift_count == 1

    def test_laundering_cycle(self):
        """Simulate provenance laundering: assumed -> retrieved without evidence."""
        ledger = EpistemicLedger()
        c = ledger.new_claim("Earth is flat", Provenance.ASSUMED, 0.3)

        snap1 = snapshot_ledger(ledger)

        # Launder: directly set provenance (bypassing promotion rules)
        ledger.tick()
        c.provenance = Provenance.RETRIEVED  # Direct mutation = laundering

        snap2 = snapshot_ledger(ledger)
        result = diff_snapshots(snap1, snap2)

        assert result.provenance_laundering_count == 1
        assert result.violations[0].severity == 1.0

    def test_multi_turn_trend(self):
        """Track violations across multiple turns."""
        history = DiffHistory()

        ledger = EpistemicLedger()
        claims = []
        for i in range(3):
            c = ledger.new_claim(f"Claim {i}", Provenance.ASSUMED, 0.3)
            claims.append(c)

        for turn in range(3):
            snap_before = snapshot_ledger(ledger)
            ledger.tick()
            # Each turn: drift one claim's confidence
            claims[turn].confidence = min(1.0, claims[turn].confidence + 0.2)
            snap_after = snapshot_ledger(ledger)
            result = diff_snapshots(snap_before, snap_after)
            history.add(result)

        trend = history.confidence_drift_trend()
        assert len(trend) == 3
        # Each turn should have exactly one drift
        assert all(t == 1 for t in trend)

    def test_evidence_erosion_cycle(self):
        """Simulate evidence being stripped from a claim."""
        ledger = EpistemicLedger()
        c = ledger.new_claim("Important claim", Provenance.RETRIEVED, 0.85)
        ev1 = _make_evidence_ref("ev1")
        ev2 = _make_evidence_ref("ev2")
        ledger.attach_evidence(c.claim_id, ev1)
        ledger.attach_evidence(c.claim_id, ev2)

        snap1 = snapshot_ledger(ledger)

        ledger.tick()
        c.evidence_refs.clear()  # Strip all evidence

        snap2 = snapshot_ledger(ledger)
        result = diff_snapshots(snap1, snap2)

        erosion = [
            v for v in result.violations
            if v.violation_type == ViolationType.EVIDENCE_EROSION
        ]
        assert len(erosion) == 1

    def test_combined_violations(self):
        """A single claim can trigger both drift and laundering."""
        c_before = _make_claim_snapshot(
            claim_id="c1", content="combined",
            provenance="assumed", confidence=0.3,
            evidence_count=0, evidence_ref_ids=(),
        )
        c_after = _make_claim_snapshot(
            claim_id="c1", content="combined",
            provenance="retrieved", confidence=0.8,
            evidence_count=0, evidence_ref_ids=(),
        )
        before = _make_ledger_snapshot(step=0, claims={"c1": c_before})
        after = _make_ledger_snapshot(step=1, claims={"c1": c_after})
        differ = ClaimDiffer()
        result = differ.diff(before, after)
        assert result.confidence_drift_count == 1
        assert result.provenance_laundering_count == 1
        assert len(result.violations) == 2
