"""
Golden-file tests for JSON artifact shapes.

Purpose: Lock down the serialization schema of every data type that will be
consumed by UI, CLI, or external integrations. If a `to_dict()` shape changes,
these tests break BEFORE downstream consumers silently break.

Strategy: For each type, construct a canonical instance, serialize, and assert:
  1. Exact key set (no extra, no missing keys)
  2. Value types for each key
  3. Round-trip: from_dict(to_dict(x)) reproduces the original

This is NOT about testing logic — it's about protecting the wire format.
"""

import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# =============================================================================
# Receipts
# =============================================================================

from governor.receipts import FileSnapshot, CmdRun, DiffReceipt, receipt_from_dict


class TestFileSnapshotShape:
    """FileSnapshot.to_dict() golden shape."""

    def _make(self) -> FileSnapshot:
        return FileSnapshot(
            path="src/main.py",
            blob_hash="abc123def456",
            size_bytes=1024,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            excerpt_spans=[(1, 10), (20, 30)],
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "type", "path", "blob_hash", "size_bytes",
            "timestamp", "excerpt_spans",
        }

    def test_type_tag(self):
        d = self._make().to_dict()
        assert d["type"] == "file_snapshot"

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["path"], str)
        assert isinstance(d["blob_hash"], str)
        assert isinstance(d["size_bytes"], int)
        assert isinstance(d["timestamp"], str)
        assert isinstance(d["excerpt_spans"], list)
        # Each span is a list of two ints
        for span in d["excerpt_spans"]:
            assert isinstance(span, (list, tuple))
            assert len(span) == 2

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = FileSnapshot.from_dict(d)
        assert restored.path == orig.path
        assert restored.blob_hash == orig.blob_hash
        assert restored.size_bytes == orig.size_bytes
        assert restored.timestamp == orig.timestamp
        assert restored.excerpt_spans == orig.excerpt_spans

    def test_json_serializable(self):
        d = self._make().to_dict()
        s = json.dumps(d)
        assert isinstance(s, str)

    def test_none_excerpt_spans(self):
        snap = FileSnapshot(
            path="x.py", blob_hash="abc", size_bytes=0,
            timestamp=datetime.now(), excerpt_spans=None,
        )
        d = snap.to_dict()
        assert d["excerpt_spans"] is None

    def test_receipt_from_dict_dispatch(self):
        d = self._make().to_dict()
        restored = receipt_from_dict(d)
        assert isinstance(restored, FileSnapshot)


class TestCmdRunShape:
    """CmdRun.to_dict() golden shape."""

    def _make(self) -> CmdRun:
        return CmdRun(
            command=("pytest", "-v"),
            exit_code=0,
            stdout_hash="stdout_abc",
            stderr_hash="stderr_def",
            cwd="/project",
            duration_ms=1234,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "type", "command", "exit_code", "stdout_hash",
            "stderr_hash", "cwd", "duration_ms", "timestamp",
        }

    def test_type_tag(self):
        d = self._make().to_dict()
        assert d["type"] == "cmd_run"

    def test_command_is_list(self):
        """to_dict converts tuple to list for JSON compatibility."""
        d = self._make().to_dict()
        assert isinstance(d["command"], list)
        assert d["command"] == ["pytest", "-v"]

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["exit_code"], int)
        assert isinstance(d["stdout_hash"], str)
        assert isinstance(d["stderr_hash"], str)
        assert isinstance(d["cwd"], str)
        assert isinstance(d["duration_ms"], int)
        assert isinstance(d["timestamp"], str)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = CmdRun.from_dict(d)
        assert restored.command == orig.command
        assert restored.exit_code == orig.exit_code
        assert restored.duration_ms == orig.duration_ms

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)

    def test_receipt_from_dict_dispatch(self):
        d = self._make().to_dict()
        restored = receipt_from_dict(d)
        assert isinstance(restored, CmdRun)


class TestDiffReceiptShape:
    """DiffReceipt.to_dict() golden shape."""

    def _make(self) -> DiffReceipt:
        return DiffReceipt(
            paths_touched=("src/a.py", "src/b.py"),
            unified_diff_hash="diff_hash_abc",
            base_tree_hash="tree_hash_def",
            additions=10,
            deletions=3,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "type", "paths_touched", "unified_diff_hash",
            "base_tree_hash", "additions", "deletions", "timestamp",
        }

    def test_type_tag(self):
        d = self._make().to_dict()
        assert d["type"] == "diff_receipt"

    def test_paths_is_list(self):
        d = self._make().to_dict()
        assert isinstance(d["paths_touched"], list)

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["unified_diff_hash"], str)
        assert isinstance(d["base_tree_hash"], str)
        assert isinstance(d["additions"], int)
        assert isinstance(d["deletions"], int)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = DiffReceipt.from_dict(d)
        assert restored.paths_touched == orig.paths_touched
        assert restored.additions == orig.additions

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


# =============================================================================
# Execution types
# =============================================================================

from governor.execution import (
    ExecutionBudget, ExecutionUsage, ExecutionState,
    ExecutionStatus, StopReason,
)


class TestExecutionBudgetShape:
    """ExecutionBudget.to_dict() golden shape."""

    def _make(self) -> ExecutionBudget:
        return ExecutionBudget(
            max_tokens=100000,
            max_iterations=50,
            max_time_seconds=1800,
            max_cost_usd=5.00,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "max_tokens", "max_iterations",
            "max_time_seconds", "max_cost_usd",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["max_tokens"], int)
        assert isinstance(d["max_iterations"], int)
        assert isinstance(d["max_time_seconds"], int)
        assert isinstance(d["max_cost_usd"], float)

    def test_none_values(self):
        d = ExecutionBudget().to_dict()
        for v in d.values():
            assert v is None

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = ExecutionBudget.from_dict(d)
        assert restored.max_tokens == orig.max_tokens
        assert restored.max_cost_usd == orig.max_cost_usd

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestExecutionUsageShape:
    """ExecutionUsage.to_dict() golden shape."""

    def _make(self) -> ExecutionUsage:
        return ExecutionUsage(
            tokens=5000, iterations=10,
            elapsed_seconds=45.2, cost_usd=0.50,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "tokens", "iterations", "elapsed_seconds", "cost_usd",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["tokens"], int)
        assert isinstance(d["iterations"], int)
        assert isinstance(d["elapsed_seconds"], float)
        assert isinstance(d["cost_usd"], float)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = ExecutionUsage.from_dict(d)
        assert restored.tokens == orig.tokens
        assert restored.cost_usd == orig.cost_usd


class TestExecutionStateShape:
    """ExecutionState.to_dict() golden shape."""

    def _make(self) -> ExecutionState:
        return ExecutionState(
            session_id="test123",
            task="Build feature X",
            spine_id="spine_001",
            invariant_ids=["tests_pass", "no_secrets"],
            budget=ExecutionBudget(max_iterations=50),
            used=ExecutionUsage(iterations=5, tokens=2000),
            progress={"step": "writing tests"},
            violations=[{"invariant_id": "x", "message": "fail"}],
            status=ExecutionStatus.RUNNING,
            stop_reason=None,
            started_at="2025-01-01T12:00:00",
            last_checkpoint="2025-01-01T12:05:00",
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "session_id", "task", "spine_id", "invariant_ids",
            "budget", "used", "progress", "violations",
            "status", "stop_reason", "started_at", "last_checkpoint",
        }

    def test_nested_budget(self):
        d = self._make().to_dict()
        assert isinstance(d["budget"], dict)
        assert "max_iterations" in d["budget"]

    def test_nested_used(self):
        d = self._make().to_dict()
        assert isinstance(d["used"], dict)
        assert "tokens" in d["used"]

    def test_status_is_string(self):
        d = self._make().to_dict()
        assert isinstance(d["status"], str)
        assert d["status"] == "running"

    def test_stop_reason_null_when_running(self):
        d = self._make().to_dict()
        assert d["stop_reason"] is None

    def test_stop_reason_serialized(self):
        state = self._make()
        state.stop(StopReason.BUDGET_EXHAUSTED)
        d = state.to_dict()
        assert d["stop_reason"] == "budget_exhausted"

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = ExecutionState.from_dict(d)
        assert restored.session_id == orig.session_id
        assert restored.task == orig.task
        assert restored.status == orig.status

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


# =============================================================================
# Spine types
# =============================================================================

from governor.spine import Spine, SpineCheckResult, SpineViolation


class TestSpineShape:
    """Spine.to_dict() golden shape."""

    def _make(self) -> Spine:
        return Spine(
            id="main_spine",
            structure={
                "files": {"src/main.py": "required"},
                "directories": {"src/": "required"},
                "forbidden_paths": ["*.secret"],
            },
            description="Main project spine",
            locked_at="2025-01-01T12:00:00",
            locked_by="human",
            unlock_requires="explicit_confirmation",
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "id", "structure", "description",
            "locked_at", "locked_by", "unlock_requires",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["id"], str)
        assert isinstance(d["structure"], dict)
        assert isinstance(d["description"], str)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = Spine.from_dict(d)
        assert restored.id == orig.id
        assert restored.structure == orig.structure

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestSpineCheckResultShape:
    """SpineCheckResult.to_dict() golden shape."""

    def test_valid_keys(self):
        r = SpineCheckResult(valid=True, violations=[])
        d = r.to_dict()
        assert set(d.keys()) == {"valid", "violations"}

    def test_violation_keys(self):
        r = SpineCheckResult(valid=False, violations=[
            SpineViolation(
                path="files.main.py",
                message="Cannot delete required file",
                constraint="files.main.py = required",
                actual="deleted",
            ),
        ])
        d = r.to_dict()
        assert len(d["violations"]) == 1
        v = d["violations"][0]
        assert set(v.keys()) == {"path", "message", "constraint", "actual"}


# =============================================================================
# Invariant types
# =============================================================================

from governor.invariants import InvariantResult, Invariant, InvariantType, InvariantSet


class TestInvariantResultShape:
    """InvariantResult.to_dict() golden shape."""

    def _make(self) -> InvariantResult:
        return InvariantResult(
            passed=False,
            message="Tests failed",
            invariant_id="tests_pass",
            details={"returncode": 1},
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "passed", "message", "invariant_id", "details",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["passed"], bool)
        assert isinstance(d["message"], str)
        assert isinstance(d["invariant_id"], str)
        assert isinstance(d["details"], dict)


class TestInvariantShape:
    """Invariant.to_dict() golden shape (metadata only, no verify callable)."""

    def test_keys(self):
        inv = Invariant(
            id="test_inv", type=InvariantType.TEST,
            rule="Tests must pass", verify=lambda **kw: None,
        )
        d = inv.to_dict()
        assert set(d.keys()) == {"id", "type", "rule", "on_violation", "enabled"}

    def test_type_is_string(self):
        inv = Invariant(
            id="test_inv", type=InvariantType.STRUCTURE,
            rule="File exists", verify=lambda **kw: None,
        )
        d = inv.to_dict()
        assert d["type"] == "structure"


class TestInvariantSetShape:
    """InvariantSet.to_dict() golden shape."""

    def test_keys(self):
        iset = InvariantSet()
        d = iset.to_dict()
        assert set(d.keys()) == {"invariants"}
        assert isinstance(d["invariants"], list)


# =============================================================================
# Ledger types (Fact, Decision)
# =============================================================================

from governor.ledgers import Fact, Decision
from governor.claims import Claim, ClaimType as BaseClaimType


class TestFactShape:
    """Fact.to_dict() golden shape."""

    def _make(self) -> Fact:
        return Fact(
            id=uuid.UUID("12345678-1234-1234-1234-123456789abc"),
            claim=Claim(type=BaseClaimType.FILE_EXISTS, path="src/main.py"),
            receipt=FileSnapshot(
                path="src/main.py", blob_hash="abc", size_bytes=100,
                timestamp=datetime(2025, 1, 1),
            ),
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            file_hashes={"src/main.py": "abc123"},
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "id", "claim", "receipt", "created_at", "file_hashes",
        }

    def test_nested_claim(self):
        d = self._make().to_dict()
        assert isinstance(d["claim"], dict)
        assert "type" in d["claim"]

    def test_nested_receipt(self):
        d = self._make().to_dict()
        assert isinstance(d["receipt"], dict)
        assert d["receipt"]["type"] == "file_snapshot"

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = Fact.from_dict(d)
        assert restored.id == orig.id
        assert restored.claim.type == orig.claim.type

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestDecisionShape:
    """Decision.to_dict() golden shape."""

    def _make(self) -> Decision:
        return Decision(
            id=uuid.UUID("12345678-1234-1234-1234-123456789abc"),
            claim=Claim(type=BaseClaimType.DECISION, topic="framework", choice="react"),
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            rationale="Industry standard",
            supersedes=None,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "id", "claim", "created_at", "rationale", "supersedes",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["id"], str)
        assert isinstance(d["claim"], dict)
        assert isinstance(d["rationale"], str)
        assert d["supersedes"] is None

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = Decision.from_dict(d)
        assert restored.id == orig.id
        assert restored.claim.topic == "framework"


# =============================================================================
# Epistemic types
# =============================================================================

from governor.epistemic import (
    EvidenceRef, EvidenceType, GroundedClaim, GroundedClaimStatus,
    Provenance, ClaimStatus, StatusTransition, TransitionReason,
    CascadeEvent, PremiseCheckResult,
)


class TestEvidenceRefShape:
    """EvidenceRef.to_dict() golden shape."""

    def _make(self) -> EvidenceRef:
        return EvidenceRef(
            ref_id="ev_abc12345",
            ref_type=EvidenceType.TOOL_TRACE,
            locator="trace_001",
            scope="tests",
            confidence=0.9,
            retrieved_at=datetime(2025, 1, 1, 12, 0, 0),
        )

    def test_base_keys(self):
        """Base keys always present."""
        d = self._make().to_dict()
        assert {"ref_id", "ref_type", "locator", "scope", "confidence", "retrieved_at"} <= set(d.keys())

    def test_optional_persistence_keys_absent(self):
        """Persistence keys absent when not set."""
        d = self._make().to_dict()
        assert "evidence_id" not in d
        assert "claim_id" not in d
        assert "collected_by" not in d

    def test_optional_persistence_keys_present(self):
        """Persistence keys present when set."""
        ev = EvidenceRef(
            ref_id="ev_1", ref_type=EvidenceType.TOOL_TRACE,
            locator="t", scope="s",
            evidence_id="eid_1", claim_id="c_1", collected_by="agent_a",
        )
        d = ev.to_dict()
        assert d["evidence_id"] == "eid_1"
        assert d["claim_id"] == "c_1"
        assert d["collected_by"] == "agent_a"

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["ref_type"], str)
        assert isinstance(d["confidence"], float)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = EvidenceRef.from_dict(d)
        assert restored.ref_id == orig.ref_id
        assert restored.ref_type == orig.ref_type
        assert restored.confidence == orig.confidence


class TestGroundedClaimShape:
    """GroundedClaim.to_dict() golden shape."""

    def _make(self) -> GroundedClaim:
        return GroundedClaim(
            claim_id="c_001",
            content="The tests pass",
            provenance=Provenance.OBSERVED,
            confidence=0.95,
            evidence_refs=[
                EvidenceRef(
                    ref_id="ev_1", ref_type=EvidenceType.TOOL_TRACE,
                    locator="trace_1", scope="tests",
                ),
            ],
            status=GroundedClaimStatus.ACTIVE,
            created_at=datetime(2025, 1, 1, 12, 0, 0),
            created_at_step=1,
            last_updated_at=datetime(2025, 1, 1, 12, 0, 0),
            last_updated_step=1,
            source_agent_id="agent_a",
        )

    def test_base_keys_always_present(self):
        d = self._make().to_dict()
        required = {
            "claim_id", "content", "provenance", "confidence",
            "evidence_refs", "status", "created_at", "created_at_step",
            "last_updated_at", "last_updated_step",
            "is_grounded", "is_dangerous", "source_agent_id",
        }
        assert required <= set(d.keys())

    def test_optional_keys_absent_when_unset(self):
        """commit_level, assumptions, epistemic_status, depends_on absent when unset."""
        d = self._make().to_dict()
        # commit_level is None, so should not be present
        assert "commit_level" not in d
        # assumptions is empty, so should not be present
        assert "assumptions" not in d
        # epistemic_status is None
        assert "epistemic_status" not in d
        # depends_on is empty
        assert "depends_on" not in d

    def test_optional_keys_present_when_set(self):
        claim = self._make()
        claim.commit_level = "hard"
        claim.assumptions = ["All tests exist"]
        claim.epistemic_status = ClaimStatus.SUPPORTED
        claim.depends_on = ["c_002"]
        d = claim.to_dict()
        assert d["commit_level"] == "hard"
        assert d["assumptions"] == ["All tests exist"]
        assert d["epistemic_status"] == "supported"
        assert d["depends_on"] == ["c_002"]

    def test_evidence_refs_nested(self):
        d = self._make().to_dict()
        assert isinstance(d["evidence_refs"], list)
        assert len(d["evidence_refs"]) == 1
        assert "ref_id" in d["evidence_refs"][0]

    def test_computed_fields(self):
        d = self._make().to_dict()
        assert isinstance(d["is_grounded"], bool)
        assert isinstance(d["is_dangerous"], bool)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = GroundedClaim.from_dict(d)
        assert restored.claim_id == orig.claim_id
        assert restored.provenance == orig.provenance
        assert restored.confidence == orig.confidence

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestStatusTransitionShape:
    """StatusTransition.to_dict() golden shape."""

    def _make(self) -> StatusTransition:
        return StatusTransition(
            claim_id="c_001",
            from_status=ClaimStatus.PROPOSED,
            to_status=ClaimStatus.SUPPORTED,
            reason=TransitionReason.EVIDENCE,
            justification="New evidence attached",
            step=5,
            timestamp="2025-01-01T12:00:00",
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "claim_id", "from_status", "to_status",
            "reason", "justification", "step", "timestamp",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["from_status"], str)
        assert isinstance(d["to_status"], str)
        assert isinstance(d["reason"], str)

    def test_from_status_null_for_first_assignment(self):
        t = StatusTransition(
            claim_id="c_001", from_status=None,
            to_status=ClaimStatus.PROPOSED,
            reason=TransitionReason.EVIDENCE,
            justification="First",
        )
        d = t.to_dict()
        assert d["from_status"] is None

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = StatusTransition.from_dict(d)
        assert restored.from_status == orig.from_status
        assert restored.to_status == orig.to_status
        assert restored.reason == orig.reason


class TestCascadeEventShape:
    """CascadeEvent.to_dict() golden shape."""

    def _make(self) -> CascadeEvent:
        return CascadeEvent(
            event_id="cas_001",
            trigger_claim_id="c_001",
            trigger_reason="retracted",
            affected_claim_id="c_002",
            old_commit_level="hard",
            new_commit_level="soft",
            old_epistemic_status="supported",
            new_epistemic_status="stale",
            depth=1,
            created_at=datetime(2025, 1, 1, 12, 0, 0),
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "event_id", "trigger_claim_id", "trigger_reason",
            "affected_claim_id", "old_commit_level", "new_commit_level",
            "old_epistemic_status", "new_epistemic_status",
            "depth", "created_at",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["depth"], int)
        assert isinstance(d["created_at"], str)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = CascadeEvent.from_dict(d)
        assert restored.event_id == orig.event_id
        assert restored.trigger_reason == orig.trigger_reason
        assert restored.depth == orig.depth


class TestPremiseCheckResultShape:
    """PremiseCheckResult.to_dict() golden shape."""

    def _make(self) -> PremiseCheckResult:
        return PremiseCheckResult(
            claim_id="c_001",
            passed=False,
            violations=["Depends on STALE claim c_002"],
            downgraded=True,
            old_commit_level="hard",
            new_commit_level="soft",
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "claim_id", "passed", "violations",
            "downgraded", "old_commit_level", "new_commit_level",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["passed"], bool)
        assert isinstance(d["violations"], list)
        assert isinstance(d["downgraded"], bool)


# =============================================================================
# Quorum types
# =============================================================================

from governor.quorum import (
    QuorumPolicy, Vote, QuorumState,
    ClaimType as QClaimType, VoteVerdict, QuorumStatus, RiskLevel,
)
from governor.ttl import VolatilityClass
from governor.dissent import EvidencePointer


class TestQuorumPolicyShape:
    """QuorumPolicy.to_dict() golden shape."""

    def _make(self) -> QuorumPolicy:
        return QuorumPolicy(
            claim_type=QClaimType.STATIC_FACT,
            min_voters=2,
            approval_threshold=0.67,
            delta_t=timedelta(seconds=120),
            volatility=VolatilityClass.MODERATE,
            timeout=timedelta(hours=1),
            risk_multiplier=1.0,
            independence_threshold=0.3,
        )

    def test_keys(self):
        d = self._make().to_dict()
        expected = {
            "claim_type", "min_voters", "approval_threshold",
            "delta_t_seconds", "effective_delta_t_seconds",
            "volatility", "requires_human", "timeout_seconds",
            "risk_multiplier", "independence_threshold",
            "required_evidence_types", "required_roles",
        }
        assert set(d.keys()) == expected

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["claim_type"], str)
        assert isinstance(d["min_voters"], int)
        assert isinstance(d["approval_threshold"], float)
        assert isinstance(d["delta_t_seconds"], (int, float))
        assert isinstance(d["volatility"], str)

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestVoteShape:
    """Vote.to_dict() golden shape."""

    def _make(self) -> Vote:
        return Vote(
            vote_id="v_001",
            proposal_id="p_001",
            agent_id="agent_a",
            verdict=VoteVerdict.APPROVE,
            reason="Looks correct",
            evidence=[],
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
        )

    def test_base_keys(self):
        d = self._make().to_dict()
        required = {
            "vote_id", "proposal_id", "agent_id",
            "verdict", "reason", "evidence", "timestamp",
        }
        assert required <= set(d.keys())

    def test_optional_keys_absent(self):
        d = self._make().to_dict()
        # These are optional and absent when None
        assert "tool_path_hash" not in d
        assert "model_id" not in d
        assert "provider_id" not in d

    def test_optional_keys_present(self):
        v = self._make()
        v.tool_path_hash = "hash_abc"
        v.model_id = "gpt-4"
        d = v.to_dict()
        assert d["tool_path_hash"] == "hash_abc"
        assert d["model_id"] == "gpt-4"

    def test_verdict_is_string(self):
        d = self._make().to_dict()
        assert d["verdict"] == "approve"

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = Vote.from_dict(d)
        assert restored.vote_id == orig.vote_id
        assert restored.verdict == orig.verdict

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestQuorumStateShape:
    """QuorumState.to_dict() golden shape."""

    def _make(self) -> QuorumState:
        policy = QuorumPolicy(
            claim_type=QClaimType.CODE,
            min_voters=1,
            approval_threshold=0.5,
            delta_t=timedelta(seconds=10),
            volatility=VolatilityClass.STABLE,
        )
        return QuorumState(
            proposal_id="p_001",
            claim_type=QClaimType.CODE,
            policy=policy,
            status=QuorumStatus.COLLECTING,
            created_at=datetime(2025, 1, 1, 12, 0, 0),
        )

    def test_keys_include_core(self):
        d = self._make().to_dict()
        required = {
            "proposal_id", "claim_type", "status", "policy",
            "votes", "approval_count", "rejection_count", "abstain_count",
            "approval_ratio", "threshold_met", "created_at",
        }
        assert required <= set(d.keys())

    def test_nested_policy(self):
        d = self._make().to_dict()
        assert isinstance(d["policy"], dict)
        assert "claim_type" in d["policy"]

    def test_status_is_string(self):
        d = self._make().to_dict()
        assert d["status"] == "collecting"


# =============================================================================
# Claim diff types
# =============================================================================

from governor.claim_diff import (
    ClaimSnapshot, LedgerSnapshot, MutationEvent, MutationType,
    Violation, ViolationType, DiffResult,
)


class TestClaimSnapshotShape:
    """ClaimSnapshot.to_dict() golden shape."""

    def _make(self) -> ClaimSnapshot:
        return ClaimSnapshot(
            claim_id="c_001",
            content="The tests pass",
            content_hash="abc123",
            provenance="observed",
            confidence=0.95,
            evidence_count=1,
            evidence_ref_ids=("ev_1",),
            status="active",
            is_grounded=True,
            is_dangerous=False,
            source_agent_id="agent_a",
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "claim_id", "content", "content_hash", "provenance",
            "confidence", "evidence_count", "evidence_ref_ids",
            "status", "is_grounded", "is_dangerous", "source_agent_id",
        }

    def test_evidence_ref_ids_is_list(self):
        d = self._make().to_dict()
        assert isinstance(d["evidence_ref_ids"], list)

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["confidence"], float)
        assert isinstance(d["evidence_count"], int)
        assert isinstance(d["is_grounded"], bool)


class TestLedgerSnapshotShape:
    """LedgerSnapshot.to_dict() golden shape."""

    def _make(self) -> LedgerSnapshot:
        snap = ClaimSnapshot(
            claim_id="c_001", content="X", content_hash="h",
            provenance="assumed", confidence=0.3, evidence_count=0,
            evidence_ref_ids=(), status="active",
            is_grounded=False, is_dangerous=False,
        )
        return LedgerSnapshot(
            step=5,
            timestamp=datetime(2025, 1, 1, 12, 0, 0),
            claims={"c_001": snap},
            claims_by_hash={"h": ["c_001"]},
            total_claims=1,
            active_count=1,
            dangerous_count=0,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "step", "timestamp", "claims",
            "total_claims", "active_count", "dangerous_count",
        }

    def test_nested_claims(self):
        d = self._make().to_dict()
        assert isinstance(d["claims"], dict)
        assert "c_001" in d["claims"]
        assert "claim_id" in d["claims"]["c_001"]


class TestMutationEventShape:
    """MutationEvent.to_dict() golden shape."""

    def _make(self) -> MutationEvent:
        return MutationEvent(
            mutation_type=MutationType.CONFIDENCE_INCREASE,
            severity=0.8,
            claim_id="c_001",
            content_hash="h",
            field_name="confidence",
            old_value=0.3,
            new_value=0.9,
            details="Increased without evidence",
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "mutation_type", "severity", "claim_id",
            "content_hash", "field_name",
            "old_value", "new_value", "details",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["mutation_type"], str)
        assert isinstance(d["severity"], float)
        # old_value and new_value are stringified
        assert isinstance(d["old_value"], str)
        assert isinstance(d["new_value"], str)


class TestViolationShape:
    """Violation.to_dict() golden shape."""

    def _make(self) -> Violation:
        return Violation(
            violation_type=ViolationType.CONFIDENCE_DRIFT,
            severity=0.8,
            claim_id="c_001",
            content_hash="h",
            content_summary="The tests pass",
            details="Confidence went from 0.3 to 0.9 without evidence",
            mutations=[],
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "violation_type", "severity", "claim_id",
            "content_hash", "content_summary", "details", "mutations",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["violation_type"], str)
        assert d["violation_type"] == "confidence_drift"


class TestDiffResultShape:
    """DiffResult.to_dict() golden shape."""

    def _make(self) -> DiffResult:
        return DiffResult(
            before_step=1,
            after_step=5,
            before_timestamp=datetime(2025, 1, 1, 12, 0, 0),
            after_timestamp=datetime(2025, 1, 1, 12, 5, 0),
            violations=[],
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "before_step", "after_step",
            "before_timestamp", "after_timestamp",
            "summary", "violations",
        }

    def test_summary_keys(self):
        d = self._make().to_dict()
        s = d["summary"]
        assert set(s.keys()) == {
            "steps", "preserved", "mutated", "added", "dropped",
            "total_mutations", "total_severity",
            "violations", "confidence_drift", "provenance_laundering",
        }

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


# =============================================================================
# Adapter types
# =============================================================================

from governor.adapters import AdapterFinding


# =============================================================================
# Continuity types
# =============================================================================

from governor.continuity import (
    Anchor, AnchorType, Severity, Violation, ContinuityReport,
    RecommendedAction, AttemptLog, ConvergenceResult,
)


class TestAnchorShape:
    """Anchor.to_dict() golden shape."""

    def _make(self) -> Anchor:
        return Anchor(
            id="char_voice_001",
            anchor_type=AnchorType.PERSONA,
            description="Character must speak in first person",
            required_patterns=["\\bI\\b"],
            required_concepts=["first-person narration"],
            forbidden_patterns=["\\bhe said\\b"],
            forbidden_concepts=["third-person narration"],
            severity=Severity.CORRECT,
            source="fiction_bible",
            established_at=5,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "id", "anchor_type", "description",
            "required_patterns", "required_concepts",
            "forbidden_patterns", "forbidden_concepts",
            "severity", "source", "established_at",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["id"], str)
        assert isinstance(d["anchor_type"], str)
        assert isinstance(d["description"], str)
        assert isinstance(d["required_patterns"], list)
        assert isinstance(d["required_concepts"], list)
        assert isinstance(d["forbidden_patterns"], list)
        assert isinstance(d["forbidden_concepts"], list)
        assert isinstance(d["severity"], str)
        assert isinstance(d["source"], str)
        assert isinstance(d["established_at"], int)

    def test_enum_values_are_strings(self):
        d = self._make().to_dict()
        assert d["anchor_type"] == "persona"
        assert d["severity"] == "correct"

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = Anchor.from_dict(d)
        assert restored.id == orig.id
        assert restored.anchor_type == orig.anchor_type
        assert restored.required_patterns == orig.required_patterns
        assert restored.forbidden_concepts == orig.forbidden_concepts
        assert restored.severity == orig.severity

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestViolationShape:
    """Violation.to_dict() golden shape (continuity)."""

    def _make(self) -> Violation:
        return Violation(
            anchor_id="char_voice_001",
            anchor_type=AnchorType.PERSONA,
            severity=Severity.CORRECT,
            description="Missing first-person pronoun",
            evidence=["Line 5: 'He walked away'"],
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "anchor_id", "anchor_type", "severity",
            "description", "evidence",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["anchor_id"], str)
        assert isinstance(d["anchor_type"], str)
        assert isinstance(d["severity"], str)
        assert isinstance(d["description"], str)
        assert isinstance(d["evidence"], list)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = Violation.from_dict(d)
        assert restored.anchor_id == orig.anchor_id
        assert restored.anchor_type == orig.anchor_type
        assert restored.severity == orig.severity
        assert restored.evidence == orig.evidence

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestContinuityReportShape:
    """ContinuityReport.to_dict() golden shape."""

    def _make(self) -> ContinuityReport:
        return ContinuityReport(
            passed=False,
            score=0.75,
            violations=[
                Violation(
                    anchor_id="a1", anchor_type=AnchorType.CANON,
                    severity=Severity.CORRECT,
                    description="Missing canon element",
                ),
            ],
            recommended_action=RecommendedAction.SOFT_REPROMPT,
            correction_context="Add canon element X",
            checked_anchors=4,
            check_time_ms=12.5,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "passed", "score", "violations",
            "recommended_action", "correction_context",
            "checked_anchors", "check_time_ms",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["passed"], bool)
        assert isinstance(d["score"], float)
        assert isinstance(d["violations"], list)
        assert isinstance(d["recommended_action"], str)
        assert isinstance(d["checked_anchors"], int)
        assert isinstance(d["check_time_ms"], float)

    def test_nested_violations(self):
        d = self._make().to_dict()
        assert len(d["violations"]) == 1
        assert "anchor_id" in d["violations"][0]

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = ContinuityReport.from_dict(d)
        assert restored.passed == orig.passed
        assert restored.score == orig.score
        assert restored.recommended_action == orig.recommended_action

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestConvergenceResultShape:
    """ConvergenceResult.to_dict() golden shape."""

    def _make(self) -> ConvergenceResult:
        report = ContinuityReport(
            passed=True, score=1.0, violations=[],
            recommended_action=RecommendedAction.ACCEPT,
            checked_anchors=2, check_time_ms=5.0,
        )
        return ConvergenceResult(
            output="Generated text here.",
            converged=True,
            attempts=2,
            final_report=report,
            attempt_log=[
                AttemptLog(
                    attempt_number=0,
                    prompt_hash="abc123",
                    output_hash="def456",
                    report=report,
                    tokens_generated=100,
                    latency_ms=50.0,
                ),
            ],
            final_prompt="Write about X",
            total_tokens=200,
            total_latency_ms=100.0,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "output", "converged", "attempts",
            "final_report", "attempt_log",
            "final_prompt", "total_tokens", "total_latency_ms",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["output"], str)
        assert isinstance(d["converged"], bool)
        assert isinstance(d["attempts"], int)
        assert isinstance(d["final_report"], dict)
        assert isinstance(d["attempt_log"], list)
        assert isinstance(d["total_tokens"], int)
        assert isinstance(d["total_latency_ms"], float)

    def test_nested_report(self):
        d = self._make().to_dict()
        assert "passed" in d["final_report"]
        assert "score" in d["final_report"]

    def test_nested_attempt_log(self):
        d = self._make().to_dict()
        assert len(d["attempt_log"]) == 1
        log = d["attempt_log"][0]
        assert set(log.keys()) == {
            "attempt_number", "prompt_hash", "output_hash",
            "report", "correction_applied",
            "tokens_generated", "latency_ms",
        }

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


# =============================================================================
# Telemetry report types
# =============================================================================

from governor.telemetry import (
    ContinuityTraceFields, ContinuityResultFields,
    AnchorStats as TelemetryAnchorStats,
    ConvergenceReport as TelemetryConvergenceReport,
    CostReport, PerformanceReport,
)


class TestContinuityTraceFieldsShape:
    """ContinuityTraceFields.to_dict() golden shape."""

    def _make(self) -> ContinuityTraceFields:
        return ContinuityTraceFields(
            run_id="abc123def456",
            mode="fiction",
            attempt=1,
            error_total=0.25,
            error_by_anchor={"a1": 0.5, "a2": 0.0},
            violations=[{"anchor_id": "a1", "severity": "correct", "description": "Missing X"}],
            action="soft_reprompt",
            action_params={"temperature": 0.7},
            delta_total=-0.1,
            delta_by_anchor={"a1": -0.2},
            tokens=150,
            latency_ms=45.67,
            prompt_hash="deadbeef01234567",
            anchors_hash="cafebabe01234567",
        )

    def test_keys_with_delta(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "run_id", "mode", "attempt",
            "error_total", "error_by_anchor",
            "violations", "action", "action_params",
            "delta_total", "delta_by_anchor",
            "tokens", "latency_ms",
            "prompt_hash", "anchors_hash",
        }

    def test_keys_without_delta(self):
        """attempt 0 has no delta fields."""
        fields = ContinuityTraceFields(
            run_id="abc", mode="code", attempt=0,
        )
        d = fields.to_dict()
        assert "delta_total" not in d
        assert "delta_by_anchor" not in d

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["run_id"], str)
        assert isinstance(d["attempt"], int)
        assert isinstance(d["error_total"], float)
        assert isinstance(d["error_by_anchor"], dict)
        assert isinstance(d["violations"], list)
        assert isinstance(d["action_params"], dict)
        assert isinstance(d["tokens"], int)
        assert isinstance(d["latency_ms"], float)

    def test_float_rounding(self):
        d = self._make().to_dict()
        # error_total rounded to 6 decimal places
        assert d["error_total"] == round(0.25, 6)
        # latency_ms rounded to 2 decimal places
        assert d["latency_ms"] == round(45.67, 2)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = ContinuityTraceFields.from_dict(d)
        assert restored.run_id == orig.run_id
        assert restored.attempt == orig.attempt
        assert restored.mode == orig.mode

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestContinuityResultFieldsShape:
    """ContinuityResultFields.to_dict() golden shape."""

    def _make(self) -> ContinuityResultFields:
        return ContinuityResultFields(
            run_id="abc123def456",
            mode="fiction",
            attempts=3,
            final_status="ACCEPTED",
            residual_error_total=0.05,
            residual_error_by_anchor={"a1": 0.05},
            action_path=["none", "soft_reprompt", "hard_reprompt"],
            total_tokens=450,
            total_latency_ms=150.75,
            monotone=True,
            oscillation_detected=False,
            deadzone_actions=[],
            interference_edges=[{"from_anchor": "a1", "to_anchor": "a2"}],
            anchors_hash="cafebabe01234567",
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "run_id", "mode", "attempts",
            "final_status", "residual_error_total",
            "residual_error_by_anchor",
            "action_path", "total_tokens", "total_latency_ms",
            "monotone", "oscillation_detected",
            "deadzone_actions", "interference_edges",
            "anchors_hash",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["final_status"], str)
        assert isinstance(d["monotone"], bool)
        assert isinstance(d["oscillation_detected"], bool)
        assert isinstance(d["action_path"], list)
        assert isinstance(d["interference_edges"], list)
        assert isinstance(d["total_tokens"], int)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = ContinuityResultFields.from_dict(d)
        assert restored.run_id == orig.run_id
        assert restored.final_status == orig.final_status
        assert restored.monotone == orig.monotone

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestTelemetryAnchorStatsShape:
    """AnchorStats (telemetry).to_dict() golden shape."""

    def _make(self) -> TelemetryAnchorStats:
        return TelemetryAnchorStats(
            anchor_id="a1",
            violation_count=5,
            run_count=3,
            action_success_rates={"soft_reprompt": 0.8, "hard_reprompt": 1.0},
            deadzone_count=1,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "anchor_id", "violation_count", "run_count",
            "action_success_rates", "deadzone_count",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["anchor_id"], str)
        assert isinstance(d["violation_count"], int)
        assert isinstance(d["run_count"], int)
        assert isinstance(d["action_success_rates"], dict)
        assert isinstance(d["deadzone_count"], int)

    def test_roundtrip(self):
        orig = self._make()
        d = orig.to_dict()
        restored = TelemetryAnchorStats.from_dict(d)
        assert restored.anchor_id == orig.anchor_id
        assert restored.violation_count == orig.violation_count

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestTelemetryConvergenceReportShape:
    """ConvergenceReport (telemetry).to_dict() golden shape."""

    def _make(self) -> TelemetryConvergenceReport:
        return TelemetryConvergenceReport(
            total_runs=10,
            accepted=8,
            refused=1,
            escalated=1,
            acceptance_rate=0.8,
            avg_attempts=2.5,
            avg_tokens_per_run=300.0,
            avg_latency_per_run_ms=120.5,
            efficiency=150.0,
            monotone_rate=0.7,
            oscillation_rate=0.1,
            windup_count=1,
            anchor_stats={
                "a1": TelemetryAnchorStats(
                    anchor_id="a1", violation_count=3, run_count=2,
                ),
            },
            interference_graph={"a1→a2": 2},
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "total_runs", "accepted", "refused", "escalated",
            "acceptance_rate", "avg_attempts",
            "avg_tokens_per_run", "avg_latency_per_run_ms",
            "efficiency", "monotone_rate", "oscillation_rate",
            "windup_count", "anchor_stats", "interference_graph",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["total_runs"], int)
        assert isinstance(d["acceptance_rate"], float)
        assert isinstance(d["anchor_stats"], dict)
        assert isinstance(d["interference_graph"], dict)

    def test_nested_anchor_stats(self):
        d = self._make().to_dict()
        assert "a1" in d["anchor_stats"]
        assert "anchor_id" in d["anchor_stats"]["a1"]

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestCostReportShape:
    """CostReport.to_dict() golden shape."""

    def _make(self) -> CostReport:
        return CostReport(
            total_cost_usd=1.23,
            by_model={"gpt-4": 0.80, "claude-3": 0.43},
            by_operation={"verification": 0.50, "generation": 0.73},
            total_calls=15,
            total_input_tokens=5000,
            total_output_tokens=3000,
            period="2025-01-01 to 2025-01-31",
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "total_cost_usd", "by_model", "by_operation",
            "total_calls", "total_input_tokens",
            "total_output_tokens", "period",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["total_cost_usd"], float)
        assert isinstance(d["by_model"], dict)
        assert isinstance(d["by_operation"], dict)
        assert isinstance(d["total_calls"], int)
        assert isinstance(d["total_input_tokens"], int)
        assert isinstance(d["total_output_tokens"], int)
        assert isinstance(d["period"], str)

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestPerformanceReportShape:
    """PerformanceReport.to_dict() golden shape."""

    def _make(self) -> PerformanceReport:
        return PerformanceReport(
            verification_latency_p50=25.0,
            verification_latency_p95=120.0,
            verification_latency_p99=350.0,
            approval_rate=0.85,
            total_proposals=20,
            total_verified=17,
            total_rejected=3,
            avg_claims_per_proposal=3.5,
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "verification_latency_p50", "verification_latency_p95",
            "verification_latency_p99", "approval_rate",
            "total_proposals", "total_verified",
            "total_rejected", "avg_claims_per_proposal",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["verification_latency_p50"], float)
        assert isinstance(d["verification_latency_p95"], float)
        assert isinstance(d["approval_rate"], float)
        assert isinstance(d["total_proposals"], int)
        assert isinstance(d["total_verified"], int)

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


class TestAdapterFindingShape:
    """AdapterFinding.to_dict() golden shape."""

    def _make(self) -> AdapterFinding:
        return AdapterFinding(
            source="security",
            file_path="src/main.py",
            message="SQL injection detected",
            severity="error",
            details={"pattern": "SELECT.*"},
        )

    def test_keys(self):
        d = self._make().to_dict()
        assert set(d.keys()) == {
            "source", "file_path", "message", "severity", "details",
        }

    def test_value_types(self):
        d = self._make().to_dict()
        assert isinstance(d["source"], str)
        assert isinstance(d["severity"], str)
        assert isinstance(d["details"], dict)

    def test_json_serializable(self):
        s = json.dumps(self._make().to_dict())
        assert isinstance(s, str)


# =============================================================================
# Cross-type JSON stability tests
# =============================================================================


class TestJsonStability:
    """Ensure all types produce deterministic, JSON-safe output."""

    def test_receipt_types_have_type_tag(self):
        """All receipt types include a 'type' discriminator."""
        for cls, tag in [
            (FileSnapshot, "file_snapshot"),
            (CmdRun, "cmd_run"),
            (DiffReceipt, "diff_receipt"),
        ]:
            if cls == FileSnapshot:
                obj = FileSnapshot(path="x", blob_hash="h", size_bytes=0, timestamp=datetime.now())
            elif cls == CmdRun:
                obj = CmdRun(command=("ls",), exit_code=0, stdout_hash="", stderr_hash="", cwd=".", duration_ms=0, timestamp=datetime.now())
            else:
                obj = DiffReceipt(paths_touched=(), unified_diff_hash="", base_tree_hash="", additions=0, deletions=0, timestamp=datetime.now())
            d = obj.to_dict()
            assert d["type"] == tag, f"{cls.__name__} should have type={tag}"

    def test_all_types_json_safe(self):
        """Every to_dict() output is JSON-serializable (no datetime, UUID, etc.)."""
        objects = [
            FileSnapshot(path="x", blob_hash="h", size_bytes=0, timestamp=datetime.now()),
            CmdRun(command=("ls",), exit_code=0, stdout_hash="", stderr_hash="", cwd=".", duration_ms=0, timestamp=datetime.now()),
            DiffReceipt(paths_touched=(), unified_diff_hash="", base_tree_hash="", additions=0, deletions=0, timestamp=datetime.now()),
            ExecutionBudget(max_iterations=10),
            ExecutionUsage(tokens=100),
            InvariantResult(passed=True, message="ok", invariant_id="x"),
            AdapterFinding(source="s", file_path="f", message="m"),
            PremiseCheckResult(claim_id="c", passed=True),
            Anchor(id="a", anchor_type=AnchorType.CANON, description="d"),
            Violation(anchor_id="a", anchor_type=AnchorType.CANON, severity=Severity.WARN, description="d"),
            ContinuityReport(passed=True, score=1.0, violations=[], recommended_action=RecommendedAction.ACCEPT),
            ContinuityTraceFields(run_id="r", mode="m"),
            ContinuityResultFields(run_id="r", mode="m"),
            TelemetryAnchorStats(anchor_id="a"),
            CostReport(total_cost_usd=0.0),
            PerformanceReport(approval_rate=1.0),
        ]
        for obj in objects:
            d = obj.to_dict()
            s = json.dumps(d)
            parsed = json.loads(s)
            assert isinstance(parsed, dict), f"{type(obj).__name__} did not round-trip through JSON"

    def test_execution_state_full_roundtrip_through_json(self):
        """ExecutionState survives JSON serialization + deserialization."""
        state = ExecutionState(
            session_id="test_rt",
            task="test task",
            budget=ExecutionBudget(max_iterations=10),
        )
        s = json.dumps(state.to_dict())
        d = json.loads(s)
        restored = ExecutionState.from_dict(d)
        assert restored.session_id == "test_rt"
        assert restored.task == "test task"
        assert restored.budget.max_iterations == 10

    def test_spine_full_roundtrip_through_json(self):
        """Spine survives JSON serialization + deserialization."""
        spine = Spine(id="sp1", structure={"files": {"a.py": "required"}})
        s = json.dumps(spine.to_dict())
        d = json.loads(s)
        restored = Spine.from_dict(d)
        assert restored.id == "sp1"
        assert restored.structure == {"files": {"a.py": "required"}}

    def test_anchor_full_roundtrip_through_json(self):
        """Anchor survives JSON serialization + deserialization."""
        anchor = Anchor(
            id="a1", anchor_type=AnchorType.CANON, description="Rule X",
            required_patterns=["\\bX\\b"], severity=Severity.REJECT,
        )
        s = json.dumps(anchor.to_dict())
        d = json.loads(s)
        restored = Anchor.from_dict(d)
        assert restored.id == "a1"
        assert restored.anchor_type == AnchorType.CANON
        assert restored.severity == Severity.REJECT

    def test_continuity_report_full_roundtrip_through_json(self):
        """ContinuityReport survives JSON serialization + deserialization."""
        report = ContinuityReport(
            passed=False, score=0.5,
            violations=[
                Violation(
                    anchor_id="a1", anchor_type=AnchorType.STYLE,
                    severity=Severity.CORRECT, description="Style violation",
                ),
            ],
            recommended_action=RecommendedAction.HARD_REPROMPT,
            checked_anchors=3, check_time_ms=10.0,
        )
        s = json.dumps(report.to_dict())
        d = json.loads(s)
        restored = ContinuityReport.from_dict(d)
        assert restored.passed is False
        assert restored.score == 0.5
        assert len(restored.violations) == 1
        assert restored.recommended_action == RecommendedAction.HARD_REPROMPT
