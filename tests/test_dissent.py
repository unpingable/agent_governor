"""
Tests for contradiction persistence ledger (dissent tracking).

Covers: ObjectionSeverity, ObjectionStatus, BlockVerdict, EvidencePointer,
Objection, DissentLedger, commit gate, confidence trajectory, and edge cases.
"""

import pytest

from governor.dissent import (
    BlockVerdict,
    ClaimDissentSummary,
    ConfidenceSnapshot,
    DissentLedger,
    EvidencePointer,
    Objection,
    ObjectionSeverity,
    ObjectionStatus,
    create_dissent_ledger,
)


# =============================================================================
# TestEnums
# =============================================================================


class TestEnums:

    def test_severity_values(self):
        assert ObjectionSeverity.LOW == "low"
        assert ObjectionSeverity.MEDIUM == "medium"
        assert ObjectionSeverity.HIGH == "high"
        assert ObjectionSeverity.CRITICAL == "critical"

    def test_status_values(self):
        assert ObjectionStatus.OPEN == "open"
        assert ObjectionStatus.ACCEPTED == "accepted"
        assert ObjectionStatus.DISMISSED == "dismissed"
        assert ObjectionStatus.ESCALATED == "escalated"
        assert ObjectionStatus.SUPERSEDED == "superseded"

    def test_verdict_values(self):
        assert BlockVerdict.BLOCKS == "blocks"
        assert BlockVerdict.FLAGS == "flags"
        assert BlockVerdict.CLEAR == "clear"


# =============================================================================
# TestEvidencePointer
# =============================================================================


class TestEvidencePointer:

    def test_creation(self):
        ep = EvidencePointer(description="Log shows failure", locator="trace-123")
        assert ep.description == "Log shows failure"
        assert ep.locator == "trace-123"

    def test_to_dict(self):
        ep = EvidencePointer(description="Test", locator="loc", evidence_type="tool_trace")
        d = ep.to_dict()
        assert d["description"] == "Test"
        assert d["evidence_type"] == "tool_trace"

    def test_from_dict(self):
        data = {"description": "Test", "locator": "loc", "evidence_type": "receipt"}
        ep = EvidencePointer.from_dict(data)
        assert ep.evidence_type == "receipt"

    def test_roundtrip(self):
        original = EvidencePointer("desc", "loc", "url")
        restored = EvidencePointer.from_dict(original.to_dict())
        assert restored.description == original.description
        assert restored.locator == original.locator


# =============================================================================
# TestObjection
# =============================================================================


class TestObjection:

    def _make(self, severity=ObjectionSeverity.MEDIUM, evidence=None):
        return Objection(
            objection_id="obj_test",
            claim_id="claim_1",
            agent_id="agent_a",
            reason="This is wrong",
            severity=severity,
            evidence=evidence or [],
        )

    def test_creation(self):
        obj = self._make()
        assert obj.is_open
        assert not obj.is_resolved
        assert obj.claim_id == "claim_1"

    def test_has_evidence_false(self):
        obj = self._make()
        assert not obj.has_evidence

    def test_has_evidence_true(self):
        obj = self._make(evidence=[EvidencePointer("proof")])
        assert obj.has_evidence

    # --- Block / flag logic ---

    def test_low_does_not_block(self):
        obj = self._make(severity=ObjectionSeverity.LOW)
        assert not obj.blocks_commit
        assert not obj.flags_review

    def test_medium_flags(self):
        obj = self._make(severity=ObjectionSeverity.MEDIUM)
        assert not obj.blocks_commit
        assert obj.flags_review

    def test_high_without_evidence_flags(self):
        obj = self._make(severity=ObjectionSeverity.HIGH)
        assert not obj.blocks_commit
        assert obj.flags_review

    def test_high_with_evidence_blocks(self):
        obj = self._make(
            severity=ObjectionSeverity.HIGH,
            evidence=[EvidencePointer("proof")],
        )
        assert obj.blocks_commit
        assert not obj.flags_review  # It's a hard block, not a flag

    def test_critical_always_blocks(self):
        obj = self._make(severity=ObjectionSeverity.CRITICAL)
        assert obj.blocks_commit

    def test_critical_without_evidence_still_blocks(self):
        obj = self._make(severity=ObjectionSeverity.CRITICAL)
        assert not obj.has_evidence
        assert obj.blocks_commit

    # --- Verdict ---

    def test_verdict_blocks(self):
        obj = self._make(severity=ObjectionSeverity.CRITICAL)
        assert obj.get_verdict() == BlockVerdict.BLOCKS

    def test_verdict_flags(self):
        obj = self._make(severity=ObjectionSeverity.MEDIUM)
        assert obj.get_verdict() == BlockVerdict.FLAGS

    def test_verdict_clear(self):
        obj = self._make(severity=ObjectionSeverity.LOW)
        assert obj.get_verdict() == BlockVerdict.CLEAR

    # --- Resolved objections don't block ---

    def test_resolved_does_not_block(self):
        obj = self._make(severity=ObjectionSeverity.CRITICAL)
        obj.status = ObjectionStatus.ACCEPTED
        assert not obj.blocks_commit
        assert not obj.flags_review

    # --- Serialization ---

    def test_to_dict(self):
        obj = self._make()
        d = obj.to_dict()
        assert d["objection_id"] == "obj_test"
        assert d["severity"] == "medium"
        assert d["blocks_commit"] is False
        assert d["flags_review"] is True

    def test_from_dict_roundtrip(self):
        original = self._make(
            severity=ObjectionSeverity.HIGH,
            evidence=[EvidencePointer("proof", "loc")],
        )
        restored = Objection.from_dict(original.to_dict())
        assert restored.severity == original.severity
        assert restored.has_evidence
        assert restored.claim_id == original.claim_id


# =============================================================================
# TestDissentLedger
# =============================================================================


class TestDissentLedger:

    def test_creation(self):
        ledger = DissentLedger()
        assert len(ledger.objections) == 0
        assert ledger.step == 0

    def test_tick(self):
        ledger = DissentLedger()
        ledger.tick()
        assert ledger.step == 1

    def test_file_objection(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Wrong", severity=ObjectionSeverity.MEDIUM,
        )
        assert obj.is_open
        assert obj.claim_id == "c1"
        assert ledger.total_objections_filed == 1
        assert ledger.get(obj.objection_id) is obj

    def test_file_with_evidence(self):
        ledger = DissentLedger()
        ev = [EvidencePointer("Log output", "trace-1")]
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Contradicts log", severity=ObjectionSeverity.HIGH,
            evidence=ev,
        )
        assert obj.has_evidence
        assert obj.blocks_commit

    def test_add_evidence(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Wrong", severity=ObjectionSeverity.HIGH,
        )
        assert not obj.has_evidence
        assert not obj.blocks_commit

        ok = ledger.add_evidence(obj.objection_id, EvidencePointer("New proof"))
        assert ok
        assert obj.has_evidence
        assert obj.blocks_commit  # Now blocks

    def test_add_evidence_to_resolved_fails(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Wrong", severity=ObjectionSeverity.HIGH,
        )
        ledger.accept(obj.objection_id)
        ok = ledger.add_evidence(obj.objection_id, EvidencePointer("Late proof"))
        assert not ok

    def test_add_evidence_nonexistent(self):
        ledger = DissentLedger()
        assert not ledger.add_evidence("bad_id", EvidencePointer("x"))


# =============================================================================
# TestResolution
# =============================================================================


class TestResolution:

    def test_accept(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Wrong", severity=ObjectionSeverity.MEDIUM,
        )
        ok = ledger.accept(obj.objection_id, "Claim retracted")
        assert ok
        assert obj.status == ObjectionStatus.ACCEPTED
        assert obj.is_resolved
        assert ledger.total_objections_accepted == 1

    def test_dismiss_requires_reason(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Wrong", severity=ObjectionSeverity.LOW,
        )
        ok = ledger.dismiss(obj.objection_id, "")
        assert not ok  # Empty reason rejected
        assert obj.is_open  # Still open

    def test_dismiss_with_reason(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Wrong", severity=ObjectionSeverity.LOW,
        )
        ok = ledger.dismiss(obj.objection_id, "Evidence insufficient")
        assert ok
        assert obj.status == ObjectionStatus.DISMISSED
        assert obj.resolution_reason == "Evidence insufficient"
        assert ledger.total_objections_dismissed == 1

    def test_escalate(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Unclear", severity=ObjectionSeverity.HIGH,
        )
        ok = ledger.escalate(obj.objection_id, "Need human input")
        assert ok
        assert obj.status == ObjectionStatus.ESCALATED
        assert ledger.total_objections_escalated == 1

    def test_supersede(self):
        ledger = DissentLedger()
        obj1 = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="First objection", severity=ObjectionSeverity.MEDIUM,
        )
        obj2 = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Better objection", severity=ObjectionSeverity.HIGH,
        )
        ok = ledger.supersede(obj1.objection_id, obj2.objection_id)
        assert ok
        assert obj1.status == ObjectionStatus.SUPERSEDED
        assert obj2.is_open

    def test_resolve_already_resolved_fails(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Wrong", severity=ObjectionSeverity.LOW,
        )
        ledger.accept(obj.objection_id)
        assert not ledger.accept(obj.objection_id)  # Already resolved
        assert not ledger.dismiss(obj.objection_id, "Try again")
        assert not ledger.escalate(obj.objection_id)

    def test_resolve_nonexistent_fails(self):
        ledger = DissentLedger()
        assert not ledger.accept("bad")
        assert not ledger.dismiss("bad", "reason")
        assert not ledger.escalate("bad")
        assert not ledger.supersede("bad", "other")


# =============================================================================
# TestCommitGate
# =============================================================================


class TestCommitGate:

    def test_no_objections_can_commit(self):
        ledger = DissentLedger()
        can, blockers = ledger.can_commit("c1")
        assert can
        assert blockers == []

    def test_low_objection_can_commit(self):
        ledger = DissentLedger()
        ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Minor", severity=ObjectionSeverity.LOW,
        )
        can, blockers = ledger.can_commit("c1")
        assert can

    def test_medium_objection_can_commit(self):
        ledger = DissentLedger()
        ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Moderate concern", severity=ObjectionSeverity.MEDIUM,
        )
        can, blockers = ledger.can_commit("c1")
        assert can  # Flags but doesn't block

    def test_high_with_evidence_blocks(self):
        ledger = DissentLedger()
        ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Contradicts data", severity=ObjectionSeverity.HIGH,
            evidence=[EvidencePointer("Proof")],
        )
        can, blockers = ledger.can_commit("c1")
        assert not can
        assert len(blockers) == 1

    def test_critical_blocks(self):
        ledger = DissentLedger()
        ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Fatal flaw", severity=ObjectionSeverity.CRITICAL,
        )
        can, blockers = ledger.can_commit("c1")
        assert not can

    def test_resolved_blocker_unblocks(self):
        ledger = DissentLedger()
        obj = ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Fatal flaw", severity=ObjectionSeverity.CRITICAL,
        )
        can, _ = ledger.can_commit("c1")
        assert not can

        ledger.accept(obj.objection_id, "Fixed")
        can, blockers = ledger.can_commit("c1")
        assert can
        assert blockers == []

    def test_multiple_claims_independent(self):
        ledger = DissentLedger()
        ledger.file_objection(
            claim_id="c1", agent_id="a1",
            reason="Block c1", severity=ObjectionSeverity.CRITICAL,
        )
        can_c1, _ = ledger.can_commit("c1")
        can_c2, _ = ledger.can_commit("c2")
        assert not can_c1
        assert can_c2  # c2 unaffected


# =============================================================================
# TestQueries
# =============================================================================


class TestQueries:

    def test_open_objections(self):
        ledger = DissentLedger()
        o1 = ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.LOW)
        o2 = ledger.file_objection("c2", "a1", "R2", ObjectionSeverity.HIGH)
        ledger.accept(o1.objection_id)
        assert len(ledger.open_objections()) == 1
        assert ledger.open_objections()[0].objection_id == o2.objection_id

    def test_resolved_objections(self):
        ledger = DissentLedger()
        o1 = ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.LOW)
        ledger.dismiss(o1.objection_id, "Not valid")
        assert len(ledger.resolved_objections()) == 1

    def test_objections_for_claim(self):
        ledger = DissentLedger()
        ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.LOW)
        ledger.file_objection("c1", "a2", "R2", ObjectionSeverity.MEDIUM)
        ledger.file_objection("c2", "a1", "R3", ObjectionSeverity.HIGH)
        assert len(ledger.objections_for_claim("c1")) == 2
        assert len(ledger.objections_for_claim("c2")) == 1

    def test_objections_by_agent(self):
        ledger = DissentLedger()
        ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.LOW)
        ledger.file_objection("c2", "a1", "R2", ObjectionSeverity.MEDIUM)
        ledger.file_objection("c3", "a2", "R3", ObjectionSeverity.HIGH)
        assert len(ledger.objections_by_agent("a1")) == 2
        assert len(ledger.objections_by_agent("a2")) == 1

    def test_blocking_objections(self):
        ledger = DissentLedger()
        ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.LOW)
        ledger.file_objection("c2", "a1", "R2", ObjectionSeverity.CRITICAL)
        assert len(ledger.blocking_objections()) == 1

    def test_flagging_objections(self):
        ledger = DissentLedger()
        ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.MEDIUM)
        ledger.file_objection("c2", "a1", "R2", ObjectionSeverity.CRITICAL)
        assert len(ledger.flagging_objections()) == 1  # Only MEDIUM flags


# =============================================================================
# TestClaimDissentSummary
# =============================================================================


class TestClaimDissentSummary:

    def test_summary_no_objections(self):
        ledger = DissentLedger()
        s = ledger.claim_summary("c1")
        assert s.total_objections == 0
        assert s.open_objections == 0
        assert not s.has_unresolved_dissent
        assert s.highest_severity is None

    def test_summary_with_objections(self):
        ledger = DissentLedger()
        ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.LOW)
        ledger.file_objection("c1", "a2", "R2", ObjectionSeverity.HIGH)
        s = ledger.claim_summary("c1")
        assert s.total_objections == 2
        assert s.open_objections == 2
        assert s.has_unresolved_dissent
        assert s.highest_severity == ObjectionSeverity.HIGH

    def test_summary_with_resolved(self):
        ledger = DissentLedger()
        o1 = ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.HIGH)
        ledger.file_objection("c1", "a2", "R2", ObjectionSeverity.LOW)
        ledger.accept(o1.objection_id)
        s = ledger.claim_summary("c1")
        assert s.total_objections == 2
        assert s.open_objections == 1
        assert s.highest_severity == ObjectionSeverity.LOW

    def test_summary_blocking_count(self):
        ledger = DissentLedger()
        ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.CRITICAL)
        ledger.file_objection(
            "c1", "a2", "R2", ObjectionSeverity.HIGH,
            evidence=[EvidencePointer("proof")],
        )
        s = ledger.claim_summary("c1")
        assert s.blocking_objections == 2


# =============================================================================
# TestConfidenceTrajectory
# =============================================================================


class TestConfidenceTrajectory:

    def test_record_and_get(self):
        ledger = DissentLedger()
        ledger.record_confidence("c1", 0.8)
        ledger.tick()
        ledger.record_confidence("c1", 0.6)
        traj = ledger.get_trajectory("c1")
        assert len(traj) == 2
        assert traj[0].confidence == 0.8
        assert traj[1].confidence == 0.6

    def test_trajectory_per_claim(self):
        ledger = DissentLedger()
        ledger.record_confidence("c1", 0.8)
        ledger.record_confidence("c2", 0.5)
        assert len(ledger.get_trajectory("c1")) == 1
        assert len(ledger.get_trajectory("c2")) == 1

    def test_empty_trajectory(self):
        ledger = DissentLedger()
        assert ledger.get_trajectory("c1") == []


# =============================================================================
# TestMetrics
# =============================================================================


class TestMetrics:

    def test_metrics(self):
        ledger = DissentLedger()
        ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.LOW)
        o2 = ledger.file_objection("c1", "a2", "R2", ObjectionSeverity.HIGH)
        ledger.accept(o2.objection_id)
        m = ledger.get_metrics()
        assert m["total_objections"] == 2
        assert m["total_filed"] == 2
        assert m["open"] == 1
        assert m["accepted"] == 1

    def test_to_dict(self):
        ledger = DissentLedger()
        ledger.file_objection("c1", "a1", "R1", ObjectionSeverity.MEDIUM)
        d = ledger.to_dict()
        assert "objections" in d
        assert "metrics" in d
        assert d["step"] == 0


# =============================================================================
# TestConvenience
# =============================================================================


class TestConvenience:

    def test_create_dissent_ledger(self):
        ledger = create_dissent_ledger()
        assert isinstance(ledger, DissentLedger)
        assert len(ledger.objections) == 0
