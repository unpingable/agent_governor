# SPDX-License-Identifier: Apache-2.0
"""
Tests for Layer 4: Premise Rule & Dependency Tracking.

Covers:
- depends_on field on GroundedClaim (serialization, backward compat)
- add_dependency / remove_dependency (cycles, self-loops, persistence)
- get_dependents / get_all_dependents (reverse lookup, transitive, diamond)
- check_premise_rule (HARD/SOFT/STALE/INVALIDATED combos)
- enforce_premise_rule (downgrade, idempotency)
- CascadeEvent dataclass (serialization, storage)
- invalidation_cascade (retract/block/stale triggers, transitive, diamond, atomic)
- Schema V5 migration (fresh DB, upgrade, idempotent)
- Quorum Gate 7 (premise check, backward compat)
- Backward compatibility (in-memory, old JSON, old DB rows)
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from governor.epistemic import (
    CascadeEvent,
    ClaimStatus,
    EpistemicLedger,
    GroundedClaim,
    GroundedClaimStatus,
    PremiseCheckResult,
    Provenance,
)
from governor.quorum import (
    ClaimType,
    QuorumManager,
    QuorumStatus,
    VoteVerdict,
    create_quorum_manager,
)
from governor.dissent import EvidencePointer
from governor.storage import SCHEMA_VERSION, Storage


# =============================================================================
# Helpers
# =============================================================================


def _make_ledger(with_storage=False):
    """Create an EpistemicLedger, optionally backed by SQLite."""
    if with_storage:
        tmp = tempfile.mkdtemp()
        storage = Storage(Path(tmp) / "test.db")
        return EpistemicLedger(storage=storage)
    return EpistemicLedger()


def _make_hard_claim(ledger, content="claim A"):
    claim = ledger.new_claim(content, Provenance.RETRIEVED, confidence=0.9)
    ledger.set_commit_level(claim.claim_id, "hard")
    return claim


def _make_soft_claim(ledger, content="claim B"):
    claim = ledger.new_claim(content, Provenance.ASSUMED, confidence=0.5)
    ledger.set_commit_level(claim.claim_id, "soft")
    return claim


# =============================================================================
# TestDependsOnField
# =============================================================================


class TestDependsOnField:
    """Tests for the depends_on field on GroundedClaim."""

    def test_default_empty(self):
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
        )
        assert claim.depends_on == []

    def test_field_set(self):
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
            depends_on=["gc_dep1", "gc_dep2"],
        )
        assert claim.depends_on == ["gc_dep1", "gc_dep2"]

    def test_to_dict_includes_depends_on(self):
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
            depends_on=["gc_dep1"],
        )
        d = claim.to_dict()
        assert d["depends_on"] == ["gc_dep1"]

    def test_to_dict_omits_empty_depends_on(self):
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
        )
        d = claim.to_dict()
        assert "depends_on" not in d

    def test_from_dict_with_depends_on(self):
        data = {
            "claim_id": "gc_test",
            "content": "test",
            "provenance": "assumed",
            "confidence": 0.5,
            "created_at": datetime.now().isoformat(),
            "depends_on": ["gc_dep1", "gc_dep2"],
        }
        claim = GroundedClaim.from_dict(data)
        assert claim.depends_on == ["gc_dep1", "gc_dep2"]

    def test_from_dict_without_depends_on(self):
        """Backward compat: old dicts without depends_on should default to []."""
        data = {
            "claim_id": "gc_test",
            "content": "test",
            "provenance": "assumed",
            "confidence": 0.5,
            "created_at": datetime.now().isoformat(),
        }
        claim = GroundedClaim.from_dict(data)
        assert claim.depends_on == []

    def test_round_trip_to_dict_from_dict(self):
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test",
            provenance=Provenance.RETRIEVED,
            confidence=0.85,
            depends_on=["gc_a", "gc_b"],
        )
        d = claim.to_dict()
        restored = GroundedClaim.from_dict(d)
        assert restored.depends_on == ["gc_a", "gc_b"]

    def test_to_row_includes_depends_on_json(self):
        claim = GroundedClaim(
            claim_id="gc_test",
            content="test",
            provenance=Provenance.ASSUMED,
            confidence=0.5,
            depends_on=["gc_dep1"],
        )
        row = EpistemicLedger._to_row(claim)
        assert json.loads(row["depends_on_json"]) == ["gc_dep1"]


# =============================================================================
# TestAddDependency
# =============================================================================


class TestAddDependency:
    """Tests for add_dependency and remove_dependency."""

    def test_basic_add(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        assert ledger.add_dependency(a.claim_id, b.claim_id)
        assert b.claim_id in ledger.claims[a.claim_id].depends_on

    def test_self_loop_rejected(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        assert not ledger.add_dependency(a.claim_id, a.claim_id)

    def test_nonexistent_claim_rejected(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        assert not ledger.add_dependency(a.claim_id, "gc_nonexistent")
        assert not ledger.add_dependency("gc_nonexistent", a.claim_id)

    def test_cycle_rejected(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        assert ledger.add_dependency(a.claim_id, b.claim_id)
        assert ledger.add_dependency(b.claim_id, c.claim_id)
        # c → a would create cycle: a→b→c→a
        assert not ledger.add_dependency(c.claim_id, a.claim_id)

    def test_idempotent_add(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        assert ledger.add_dependency(a.claim_id, b.claim_id)
        assert ledger.add_dependency(a.claim_id, b.claim_id)  # idempotent
        assert ledger.claims[a.claim_id].depends_on.count(b.claim_id) == 1

    def test_remove_dependency(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        assert ledger.remove_dependency(a.claim_id, b.claim_id)
        assert b.claim_id not in ledger.claims[a.claim_id].depends_on

    def test_remove_nonexistent_returns_false(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        assert not ledger.remove_dependency(a.claim_id, b.claim_id)

    def test_remove_nonexistent_claim_returns_false(self):
        ledger = _make_ledger()
        assert not ledger.remove_dependency("gc_nonexistent", "gc_other")

    def test_reverse_index_updated_on_add(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        assert a.claim_id in ledger._reverse_deps[b.claim_id]

    def test_reverse_index_updated_on_remove(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        ledger.remove_dependency(a.claim_id, b.claim_id)
        assert a.claim_id not in ledger._reverse_deps.get(b.claim_id, [])

    def test_persistence_on_add(self):
        ledger = _make_ledger(with_storage=True)
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)

        cursor = ledger.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM claim_dependencies WHERE claim_id = ? AND depends_on_id = ?",
            (a.claim_id, b.claim_id),
        )
        assert cursor.fetchone() is not None

    def test_persistence_on_remove(self):
        ledger = _make_ledger(with_storage=True)
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        ledger.remove_dependency(a.claim_id, b.claim_id)

        cursor = ledger.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM claim_dependencies WHERE claim_id = ? AND depends_on_id = ?",
            (a.claim_id, b.claim_id),
        )
        assert cursor.fetchone() is None


# =============================================================================
# TestGetDependents
# =============================================================================


class TestGetDependents:
    """Tests for get_dependents and get_all_dependents."""

    def test_direct_dependents(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.add_dependency(c.claim_id, a.claim_id)
        deps = ledger.get_dependents(a.claim_id)
        assert set(deps) == {b.claim_id, c.claim_id}

    def test_no_dependents(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        assert ledger.get_dependents(a.claim_id) == []

    def test_transitive_dependents(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.add_dependency(c.claim_id, b.claim_id)
        all_deps = ledger.get_all_dependents(a.claim_id)
        assert set(all_deps) == {b.claim_id, c.claim_id}

    def test_diamond_dependents(self):
        """Diamond: A←B, A←C, B←D, C←D. All of B,C,D depend on A transitively."""
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        d = _make_hard_claim(ledger, "D")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.add_dependency(c.claim_id, a.claim_id)
        ledger.add_dependency(d.claim_id, b.claim_id)
        ledger.add_dependency(d.claim_id, c.claim_id)
        all_deps = ledger.get_all_dependents(a.claim_id)
        assert set(all_deps) == {b.claim_id, c.claim_id, d.claim_id}

    def test_get_dependents_returns_list_copy(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        deps = ledger.get_dependents(a.claim_id)
        deps.clear()
        assert len(ledger.get_dependents(a.claim_id)) == 1

    def test_nonexistent_claim_returns_empty(self):
        ledger = _make_ledger()
        assert ledger.get_dependents("gc_nonexistent") == []
        assert ledger.get_all_dependents("gc_nonexistent") == []


# =============================================================================
# TestPremiseRuleCheck
# =============================================================================


class TestPremiseRuleCheck:
    """Tests for check_premise_rule."""

    def test_hard_with_hard_deps_passes(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        result = ledger.check_premise_rule(a.claim_id)
        assert result.passed

    def test_hard_with_soft_dep_fails(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed
        assert any("soft" in v for v in result.violations)

    def test_hard_with_retracted_dep_fails(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        # Retract b (but prevent cascade from affecting a first)
        b_claim = ledger.claims[b.claim_id]
        b_claim.status = GroundedClaimStatus.RETRACTED
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed
        assert any("retracted" in v for v in result.violations)

    def test_hard_with_stale_epistemic_dep_fails(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        b_claim = ledger.claims[b.claim_id]
        b_claim.epistemic_status = ClaimStatus.STALE
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed
        assert any("stale" in v for v in result.violations)

    def test_hard_with_invalidated_dep_fails(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        b_claim = ledger.claims[b.claim_id]
        b_claim.epistemic_status = ClaimStatus.INVALIDATED
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed

    def test_hard_with_contested_dep_fails(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        b_claim = ledger.claims[b.claim_id]
        b_claim.epistemic_status = ClaimStatus.CONTESTED
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed

    def test_hard_with_refused_dep_fails(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        b_claim = ledger.claims[b.claim_id]
        b_claim.epistemic_status = ClaimStatus.REFUSED
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed

    def test_hard_with_expired_dep_fails(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        b_claim = ledger.claims[b.claim_id]
        b_claim.epistemic_status = ClaimStatus.EXPIRED
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed

    def test_soft_claim_always_passes(self):
        """Premise rule only applies to HARD claims."""
        ledger = _make_ledger()
        a = _make_soft_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        result = ledger.check_premise_rule(a.claim_id)
        assert result.passed

    def test_no_deps_passes(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        result = ledger.check_premise_rule(a.claim_id)
        assert result.passed

    def test_nonexistent_claim_fails(self):
        ledger = _make_ledger()
        result = ledger.check_premise_rule("gc_nonexistent")
        assert not result.passed
        assert "not found" in result.violations[0]

    def test_missing_dep_claim_fails(self):
        """If a dependency references a claim_id that's been removed, fail."""
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        # Remove b from claims dict (simulate cleanup)
        del ledger.claims[b.claim_id]
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed
        assert any("not found" in v for v in result.violations)

    def test_hard_with_unclassified_dep_passes(self):
        """Dep with commit_level=None (unclassified) should not violate."""
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = ledger.new_claim("B", Provenance.RETRIEVED, confidence=0.8)
        # b has commit_level=None
        ledger.add_dependency(a.claim_id, b.claim_id)
        result = ledger.check_premise_rule(a.claim_id)
        assert result.passed

    def test_multiple_violations_reported(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        c = _make_soft_claim(ledger, "C")
        ledger.add_dependency(a.claim_id, b.claim_id)
        ledger.add_dependency(a.claim_id, c.claim_id)
        result = ledger.check_premise_rule(a.claim_id)
        assert not result.passed
        assert len(result.violations) == 2


# =============================================================================
# TestEnforcePremiseRule
# =============================================================================


class TestEnforcePremiseRule:
    """Tests for enforce_premise_rule (check + downgrade)."""

    def test_downgrade_hard_to_soft(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        result = ledger.enforce_premise_rule(a.claim_id)
        assert result.downgraded
        assert result.old_commit_level == "hard"
        assert result.new_commit_level == "soft"
        assert ledger.claims[a.claim_id].commit_level == "soft"

    def test_no_downgrade_when_passing(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        result = ledger.enforce_premise_rule(a.claim_id)
        assert not result.downgraded
        assert ledger.claims[a.claim_id].commit_level == "hard"

    def test_idempotent_enforce(self):
        """Enforcing twice on same violation should only downgrade once."""
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        result1 = ledger.enforce_premise_rule(a.claim_id)
        assert result1.downgraded
        # Second call: a is now SOFT, so premise rule doesn't apply
        result2 = ledger.enforce_premise_rule(a.claim_id)
        assert result2.passed  # SOFT claims always pass

    def test_enforce_persists_to_storage(self):
        ledger = _make_ledger(with_storage=True)
        a = _make_hard_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        ledger.enforce_premise_rule(a.claim_id)

        cursor = ledger.storage.conn.cursor()
        cursor.execute(
            "SELECT commit_level FROM epistemic_claims WHERE claim_id = ?",
            (a.claim_id,),
        )
        row = cursor.fetchone()
        assert row["commit_level"] == "soft"

    def test_soft_claim_not_downgraded(self):
        ledger = _make_ledger()
        a = _make_soft_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        result = ledger.enforce_premise_rule(a.claim_id)
        assert result.passed
        assert not result.downgraded

    def test_nonexistent_claim_not_downgraded(self):
        ledger = _make_ledger()
        result = ledger.enforce_premise_rule("gc_nonexistent")
        assert not result.passed
        assert not result.downgraded

    def test_enforce_with_blocked_dep(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        # Block b directly (bypassing cascade for this test)
        b_claim = ledger.claims[b.claim_id]
        b_claim.status = GroundedClaimStatus.BLOCKED
        result = ledger.enforce_premise_rule(a.claim_id)
        assert result.downgraded

    def test_result_to_dict(self):
        result = PremiseCheckResult(
            claim_id="gc_test",
            passed=False,
            violations=["Dep is soft"],
            downgraded=True,
            old_commit_level="hard",
            new_commit_level="soft",
        )
        d = result.to_dict()
        assert d["claim_id"] == "gc_test"
        assert d["passed"] is False
        assert d["downgraded"] is True


# =============================================================================
# TestCascadeEvent
# =============================================================================


class TestCascadeEvent:
    """Tests for CascadeEvent dataclass."""

    def test_to_dict(self):
        event = CascadeEvent(
            event_id="ce_test",
            trigger_claim_id="gc_trigger",
            trigger_reason="retracted",
            affected_claim_id="gc_affected",
            old_commit_level="hard",
            new_commit_level="soft",
            depth=1,
        )
        d = event.to_dict()
        assert d["event_id"] == "ce_test"
        assert d["trigger_reason"] == "retracted"
        assert d["depth"] == 1

    def test_from_dict(self):
        d = {
            "event_id": "ce_test",
            "trigger_claim_id": "gc_trigger",
            "trigger_reason": "blocked",
            "affected_claim_id": "gc_affected",
            "old_commit_level": "hard",
            "new_commit_level": "soft",
            "depth": 2,
            "created_at": datetime.now().isoformat(),
        }
        event = CascadeEvent.from_dict(d)
        assert event.event_id == "ce_test"
        assert event.depth == 2

    def test_round_trip(self):
        event = CascadeEvent(
            event_id="ce_rt",
            trigger_claim_id="gc_t",
            trigger_reason="stale",
            affected_claim_id="gc_a",
            depth=3,
        )
        d = event.to_dict()
        restored = CascadeEvent.from_dict(d)
        assert restored.event_id == event.event_id
        assert restored.depth == 3

    def test_storage_persistence(self):
        ledger = _make_ledger(with_storage=True)
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        # Retract a triggers cascade on b
        ledger.retract(a.claim_id)

        cursor = ledger.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM cascade_events WHERE trigger_claim_id = ?",
            (a.claim_id,),
        )
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0]["affected_claim_id"] == b.claim_id


# =============================================================================
# TestInvalidationCascade
# =============================================================================


class TestInvalidationCascade:
    """Tests for invalidation_cascade and its hooks."""

    def test_retract_triggers_cascade(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.retract(a.claim_id)
        assert ledger.claims[b.claim_id].commit_level == "soft"

    def test_block_triggers_cascade(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.block(a.claim_id)
        assert ledger.claims[b.claim_id].commit_level == "soft"

    def test_set_epistemic_status_invalidated_triggers_cascade(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.set_epistemic_status(a.claim_id, ClaimStatus.INVALIDATED)
        assert ledger.claims[b.claim_id].commit_level == "soft"

    def test_set_epistemic_status_stale_triggers_cascade(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.set_epistemic_status(a.claim_id, ClaimStatus.STALE)
        assert ledger.claims[b.claim_id].commit_level == "soft"

    def test_set_epistemic_status_contested_triggers_cascade(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.set_epistemic_status(a.claim_id, ClaimStatus.CONTESTED)
        assert ledger.claims[b.claim_id].commit_level == "soft"

    def test_set_epistemic_status_supported_no_cascade(self):
        """Setting to SUPPORTED should NOT trigger cascade."""
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.set_epistemic_status(a.claim_id, ClaimStatus.SUPPORTED)
        assert ledger.claims[b.claim_id].commit_level == "hard"

    def test_transitive_cascade(self):
        """A→B→C: retract A should cascade through B to C."""
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.add_dependency(c.claim_id, b.claim_id)
        ledger.retract(a.claim_id)
        assert ledger.claims[b.claim_id].commit_level == "soft"
        assert ledger.claims[c.claim_id].commit_level == "soft"

    def test_diamond_cascade(self):
        """Diamond: A←B, A←C, B←D, C←D. Retract A should cascade to B, C, D."""
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        d = _make_hard_claim(ledger, "D")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.add_dependency(c.claim_id, a.claim_id)
        ledger.add_dependency(d.claim_id, b.claim_id)
        ledger.add_dependency(d.claim_id, c.claim_id)
        ledger.retract(a.claim_id)
        assert ledger.claims[b.claim_id].commit_level == "soft"
        assert ledger.claims[c.claim_id].commit_level == "soft"
        assert ledger.claims[d.claim_id].commit_level == "soft"

    def test_soft_dependents_not_downgraded(self):
        """Cascade should only affect HARD dependents."""
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        events = ledger.invalidation_cascade(a.claim_id, "test")
        assert len(events) == 0
        assert ledger.claims[b.claim_id].commit_level == "soft"

    def test_cascade_returns_events(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        events = ledger.invalidation_cascade(a.claim_id, "retracted")
        assert len(events) == 1
        assert events[0].trigger_claim_id == a.claim_id
        assert events[0].affected_claim_id == b.claim_id
        assert events[0].old_commit_level == "hard"
        assert events[0].new_commit_level == "soft"

    def test_cascade_depth_tracking(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.add_dependency(c.claim_id, b.claim_id)
        events = ledger.invalidation_cascade(a.claim_id, "retracted")
        depths = {e.affected_claim_id: e.depth for e in events}
        assert depths[b.claim_id] == 1
        assert depths[c.claim_id] == 2

    def test_cascade_metrics(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.invalidation_cascade(a.claim_id, "test")
        assert ledger.total_cascades == 1
        assert ledger.total_cascade_downgrades == 1

    def test_cascade_history(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.invalidation_cascade(a.claim_id, "test")
        assert len(ledger.cascade_history) == 1

    def test_no_dependents_no_cascade(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        events = ledger.invalidation_cascade(a.claim_id, "test")
        assert len(events) == 0
        assert ledger.total_cascades == 0

    def test_cascade_persistence(self):
        ledger = _make_ledger(with_storage=True)
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        ledger.add_dependency(b.claim_id, a.claim_id)
        ledger.add_dependency(c.claim_id, b.claim_id)
        ledger.retract(a.claim_id)

        cursor = ledger.storage.conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM cascade_events")
        assert cursor.fetchone()["cnt"] == 2


# =============================================================================
# TestSchemaV5Migration
# =============================================================================


class TestSchemaV5Migration:
    """Tests for Schema V5+ migration (V5 tables still present in V6)."""

    def test_schema_version_is_current(self):
        # Schema has progressed to V6 (staleness/docket), but V5 tables should still exist
        assert SCHEMA_VERSION >= 5

    def test_fresh_db_has_v5_tables(self):
        tmp = tempfile.mkdtemp()
        storage = Storage(Path(tmp) / "test.db")
        cursor = storage.conn.cursor()

        # Check claim_dependencies table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='claim_dependencies'"
        )
        assert cursor.fetchone() is not None

        # Check cascade_events table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cascade_events'"
        )
        assert cursor.fetchone() is not None

    def test_fresh_db_has_depends_on_json_column(self):
        tmp = tempfile.mkdtemp()
        storage = Storage(Path(tmp) / "test.db")
        cursor = storage.conn.cursor()
        cursor.execute("PRAGMA table_info(epistemic_claims)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "depends_on_json" in columns

    def test_migration_from_v4(self):
        """Simulate a V4 database and migrate to V5."""
        tmp = tempfile.mkdtemp()
        db_path = Path(tmp) / "test.db"

        # Create a V4 database manually
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        from governor.storage import SCHEMA, SCHEMA_V2, _SCHEMA_V3_STMTS, SCHEMA_V4
        conn.executescript(SCHEMA)
        conn.executescript(SCHEMA_V2)
        for stmt in _SCHEMA_V3_STMTS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
        conn.executescript(SCHEMA_V4)
        conn.execute("INSERT INTO schema_version (version) VALUES (4)")
        conn.execute("INSERT OR IGNORE INTO epoch_counter (id, value) VALUES (1, 0)")
        conn.commit()
        conn.close()

        # Now open with Storage, which should auto-migrate to current version
        storage = Storage(db_path)
        cursor = storage.conn.cursor()

        cursor.execute("SELECT version FROM schema_version")
        assert cursor.fetchone()["version"] == SCHEMA_VERSION

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='claim_dependencies'"
        )
        assert cursor.fetchone() is not None

        cursor.execute("PRAGMA table_info(epistemic_claims)")
        columns = {row["name"] for row in cursor.fetchall()}
        assert "depends_on_json" in columns

    def test_idempotent_migration(self):
        """Running migration twice should not fail."""
        tmp = tempfile.mkdtemp()
        storage = Storage(Path(tmp) / "test.db")
        # Close and re-open
        storage.close()
        storage2 = Storage(Path(tmp) / "test.db")
        cursor = storage2.conn.cursor()
        cursor.execute("SELECT version FROM schema_version")
        assert cursor.fetchone()["version"] == SCHEMA_VERSION

    def test_depends_on_json_default(self):
        """New claims should have depends_on_json defaulting to '[]'."""
        tmp = tempfile.mkdtemp()
        storage = Storage(Path(tmp) / "test.db")
        ledger = EpistemicLedger(storage=storage)
        claim = ledger.new_claim("test claim", Provenance.ASSUMED)

        cursor = storage.conn.cursor()
        cursor.execute(
            "SELECT depends_on_json FROM epistemic_claims WHERE claim_id = ?",
            (claim.claim_id,),
        )
        row = cursor.fetchone()
        assert json.loads(row["depends_on_json"]) == []

    def test_depends_on_json_persisted(self):
        """Dependencies should be persisted in depends_on_json."""
        tmp = tempfile.mkdtemp()
        storage = Storage(Path(tmp) / "test.db")
        ledger = EpistemicLedger(storage=storage)
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)

        cursor = storage.conn.cursor()
        cursor.execute(
            "SELECT depends_on_json FROM epistemic_claims WHERE claim_id = ?",
            (a.claim_id,),
        )
        row = cursor.fetchone()
        assert b.claim_id in json.loads(row["depends_on_json"])


# =============================================================================
# TestQuorumGate7
# =============================================================================


class TestQuorumGate7:
    """Tests for Gate 7 (premise rule) in QuorumManager.can_proceed()."""

    def _make_quorum_with_votes(self, ledger=None):
        """Create a quorum that reaches REACHED status."""
        qm = create_quorum_manager(epistemic_ledger=ledger)
        qs = qm.create_quorum("prop_1", ClaimType.MATH)
        t0 = datetime.now()
        qm.cast_vote("prop_1", "agent_1", VoteVerdict.APPROVE, "ok",
                      evidence=[EvidencePointer(description="calc proof", evidence_type="calc_result")],
                      timestamp=t0)
        qm.cast_vote("prop_1", "agent_2", VoteVerdict.APPROVE, "ok",
                      evidence=[EvidencePointer(description="calc verify", evidence_type="calc_result")],
                      timestamp=t0)
        # Advance past delta_t
        future = t0 + timedelta(seconds=10)
        qm.update("prop_1", now=future)
        return qm, future

    def test_no_ledger_passes(self):
        """Without epistemic_ledger, Gate 7 should not block."""
        qm, future = self._make_quorum_with_votes(ledger=None)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        assert ok

    def test_clean_ledger_passes(self):
        """Ledger with no HARD claims should not block."""
        ledger = _make_ledger()
        qm, future = self._make_quorum_with_votes(ledger=ledger)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        assert ok

    def test_hard_claim_no_deps_passes(self):
        """HARD claim without deps should pass."""
        ledger = _make_ledger()
        _make_hard_claim(ledger, "standalone")
        qm, future = self._make_quorum_with_votes(ledger=ledger)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        assert ok

    def test_hard_claim_with_valid_deps_passes(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        qm, future = self._make_quorum_with_votes(ledger=ledger)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        assert ok

    def test_hard_claim_with_soft_dep_blocks(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        qm, future = self._make_quorum_with_votes(ledger=ledger)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        assert not ok
        assert any("Premise rule" in r for r in reasons)

    def test_hard_claim_with_stale_dep_blocks(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        b_claim = ledger.claims[b.claim_id]
        b_claim.epistemic_status = ClaimStatus.STALE
        qm, future = self._make_quorum_with_votes(ledger=ledger)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        assert not ok

    def test_backward_compat_no_epistemic_ledger_arg(self):
        """QuorumManager without epistemic_ledger should work fine."""
        qm = QuorumManager()
        qs = qm.create_quorum("prop_1", ClaimType.MATH)
        t0 = datetime.now()
        qm.cast_vote("prop_1", "a1", VoteVerdict.APPROVE, "ok",
                      evidence=[EvidencePointer(description="calc1", evidence_type="calc_result")],
                      timestamp=t0)
        qm.cast_vote("prop_1", "a2", VoteVerdict.APPROVE, "ok",
                      evidence=[EvidencePointer(description="calc2", evidence_type="calc_result")],
                      timestamp=t0)
        future = t0 + timedelta(seconds=10)
        qm.update("prop_1", now=future)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        assert ok

    def test_create_quorum_manager_with_epistemic_ledger(self):
        ledger = _make_ledger()
        qm = create_quorum_manager(epistemic_ledger=ledger)
        assert qm.epistemic_ledger is ledger

    def test_multiple_violations_reported(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_soft_claim(ledger, "B")
        c = _make_hard_claim(ledger, "C")
        d = _make_soft_claim(ledger, "D")
        ledger.add_dependency(a.claim_id, b.claim_id)
        ledger.add_dependency(c.claim_id, d.claim_id)
        qm, future = self._make_quorum_with_votes(ledger=ledger)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        assert not ok
        premise_reasons = [r for r in reasons if "Premise rule" in r]
        assert len(premise_reasons) >= 2

    def test_retracted_dep_blocks_via_gate7(self):
        ledger = _make_ledger()
        a = _make_hard_claim(ledger, "A")
        b = _make_hard_claim(ledger, "B")
        ledger.add_dependency(a.claim_id, b.claim_id)
        # Block b directly to test status check
        b_claim = ledger.claims[b.claim_id]
        b_claim.status = GroundedClaimStatus.RETRACTED
        qm, future = self._make_quorum_with_votes(ledger=ledger)
        ok, reasons = qm.can_proceed("prop_1", now=future)
        # a is still HARD because we set b's status directly, not through retract()
        # But check_premise_rule should detect the bad status
        assert not ok


# =============================================================================
# TestBackwardCompatibility
# =============================================================================


class TestBackwardCompatibility:
    """Tests for backward compatibility with pre-Layer 4 data."""

    def test_in_memory_ledger_no_deps(self):
        """In-memory ledger without storage should work normally."""
        ledger = EpistemicLedger()
        claim = ledger.new_claim("test", Provenance.ASSUMED)
        assert claim.depends_on == []
        result = ledger.check_premise_rule(claim.claim_id)
        assert result.passed

    def test_old_json_without_depends_on(self):
        """JSON from pre-Layer 4 should deserialize correctly."""
        old_data = {
            "step": 5,
            "claims": {
                "gc_old": {
                    "claim_id": "gc_old",
                    "content": "old claim",
                    "provenance": "assumed",
                    "confidence": 0.3,
                    "created_at": datetime.now().isoformat(),
                    "commit_level": "hard",
                }
            },
            "total_claims_created": 1,
        }
        ledger = EpistemicLedger.from_dict(old_data)
        assert ledger.claims["gc_old"].depends_on == []
        result = ledger.check_premise_rule("gc_old")
        assert result.passed

    def test_old_json_round_trip(self):
        """Old-format JSON should round-trip through from_dict/to_dict."""
        old_data = {
            "step": 0,
            "claims": {
                "gc_1": {
                    "claim_id": "gc_1",
                    "content": "test",
                    "provenance": "retrieved",
                    "confidence": 0.85,
                    "created_at": datetime.now().isoformat(),
                }
            },
        }
        ledger = EpistemicLedger.from_dict(old_data)
        d = ledger.to_dict()
        # depends_on is empty so should not appear in to_dict
        assert "depends_on" not in d["claims"]["gc_1"]

    def test_cascade_on_empty_ledger(self):
        """Cascade on ledger with no claims should return empty."""
        ledger = EpistemicLedger()
        events = ledger.invalidation_cascade("gc_nonexistent", "test")
        assert events == []
