# SPDX-License-Identifier: Apache-2.0
"""Tests for the constraint gate (formal admissibility via Z3 verifier).

These tests work in two modes:
- When the verifier package is installed: full integration tests
- When not installed: graceful degradation tests only

The gate must never fail hard when the verifier is absent.
"""

from __future__ import annotations

import pytest

from governor.constraint_gate import (
    GATE_NAME,
    VERIFIER_AVAILABLE,
    ConstraintGate,
    ConstraintGateResult,
    ConstraintGateStatus,
    ConstraintAtom,
    ConstraintRule,
    Fact,
)


# =============================================================================
# Helpers
# =============================================================================

def _make_standing_grant(
    grant_id: str = "g-101",
    subject_id: str = "wl:deploy-bot:host-abc",
    action: str = "deploy",
    target: str = "prod/web-api",
) -> dict:
    return {
        "id": grant_id,
        "subject": {"id": subject_id, "label": "deploy-bot"},
        "scope": {"action": action, "target": target},
        "issued_at": "2026-04-08T10:00:00Z",
        "expires_at": "2026-04-08T11:00:00Z",
    }


def _make_continuity_memory(
    memory_id: str = "mem_001",
    scope: str = "prod/web-api",
    kind: str = "constraint",
    status: str = "committed",
    reliance_class: str = "actionable",
    content: dict | None = None,
) -> dict:
    return {
        "memory_id": memory_id,
        "scope": scope,
        "kind": kind,
        "status": status,
        "reliance_class": reliance_class,
        "content": content or {"frozen": "false", "deploy_policy": "active"},
    }


class FakeReceiptSystem:
    """Captures emitted receipts for test assertions."""

    def __init__(self):
        self.receipts: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.receipts.append(kwargs)


# =============================================================================
# Status and availability
# =============================================================================


class TestStatus:
    def test_status_available_reflects_import(self):
        gate = ConstraintGate()
        assert gate.available == VERIFIER_AVAILABLE

    def test_status_to_dict(self):
        status = ConstraintGateStatus(available=True, reason="ok")
        d = status.to_dict()
        assert d["available"] is True
        assert d["reason"] == "ok"

    def test_verdict_ceiling_when_available(self):
        status = ConstraintGateStatus(available=True, reason="ok")
        assert status.verdict_ceiling == "pass"

    def test_verdict_ceiling_when_unavailable(self):
        status = ConstraintGateStatus(available=False, reason="verifier_not_installed")
        assert status.verdict_ceiling == "observe"


class TestResultSerialization:
    def test_minimal_result_to_dict(self):
        r = ConstraintGateResult(verdict="pass", status="allowed")
        d = r.to_dict()
        assert d == {"verdict": "pass", "status": "allowed"}

    def test_result_with_failures_to_dict(self):
        r = ConstraintGateResult(
            verdict="block",
            status="denied",
            failed_rules=[{"rule_id": "r1", "description": "bad", "severity": "deny"}],
            timing_ms=12.34,
        )
        d = r.to_dict()
        assert d["verdict"] == "block"
        assert len(d["failed_rules"]) == 1
        assert d["timing_ms"] == 12.34

    def test_used_facts_excluded_from_default_serialization(self):
        r = ConstraintGateResult(
            verdict="pass",
            status="allowed",
            used_facts=[{"subject": "actor", "field": "scope", "value": "deploy"}],
        )
        d = r.to_dict()
        assert "used_facts" not in d


# =============================================================================
# Graceful degradation (always run, even without verifier)
# =============================================================================


class TestGracefulDegradation:
    def test_check_when_unavailable_returns_observe(self, monkeypatch):
        """When verifier not installed, check returns observe, not error."""
        monkeypatch.setattr(
            "governor.constraint_gate.VERIFIER_AVAILABLE", False
        )
        gate = ConstraintGate.__new__(ConstraintGate)
        gate._receipt_system = None
        gate._rules = []
        gate._status = ConstraintGateStatus(
            available=False, reason="verifier_not_installed"
        )

        result = gate.check(
            action="deploy", actor="bot", target="prod", scope="deploy"
        )

        assert result.verdict == "observe"
        assert result.status == "unavailable"
        assert result.failed_rules == []

    def test_unavailable_still_emits_receipt(self, monkeypatch):
        """Even when unavailable, receipt is emitted (with observe verdict)."""
        monkeypatch.setattr(
            "governor.constraint_gate.VERIFIER_AVAILABLE", False
        )
        receipts = FakeReceiptSystem()
        gate = ConstraintGate.__new__(ConstraintGate)
        gate._receipt_system = receipts
        gate._rules = []
        gate._status = ConstraintGateStatus(
            available=False, reason="verifier_not_installed"
        )

        gate.check(action="deploy", actor="bot", target="prod", scope="deploy")

        assert len(receipts.receipts) == 1
        assert receipts.receipts[0]["verdict"] == "observe"
        assert receipts.receipts[0]["gate"] == GATE_NAME

    def test_no_receipt_system_no_error(self, monkeypatch):
        monkeypatch.setattr(
            "governor.constraint_gate.VERIFIER_AVAILABLE", False
        )
        gate = ConstraintGate.__new__(ConstraintGate)
        gate._receipt_system = None
        gate._rules = []
        gate._status = ConstraintGateStatus(
            available=False, reason="verifier_not_installed"
        )

        # Should not raise
        result = gate.check(
            action="deploy", actor="bot", target="prod", scope="deploy"
        )
        assert result.verdict == "observe"


# =============================================================================
# Integration tests (only run when verifier is installed)
# =============================================================================

needs_verifier = pytest.mark.skipif(
    not VERIFIER_AVAILABLE,
    reason="z3-verifier not installed",
)


@needs_verifier
class TestVerifierIntegration:
    """Full integration: Standing grants + Continuity memories → Z3 → verdict."""

    def _scope_rule(self):
        return ConstraintRule(
            rule_id="standing.scope_match",
            description="Granted scope must match requested action",
            require=[
                ConstraintAtom(
                    subject="actor",
                    field="granted_scope",
                    op="eq",
                    value="deploy",
                ),
            ],
            severity="deny",
        )

    def _freeze_rule(self):
        return ConstraintRule(
            rule_id="continuity.no_frozen_target",
            description="Target must not be frozen",
            require=[
                ConstraintAtom(
                    subject="target",
                    field="frozen",
                    op="eq",
                    value="false",
                ),
            ],
            severity="deny",
        )

    def _stale_warning_rule(self):
        return ConstraintRule(
            rule_id="continuity.stale_advisory",
            description="Warn if reliance is only advisory",
            require=[
                ConstraintAtom(
                    subject="target",
                    field="constraint_reliance",
                    op="eq",
                    value="actionable",
                ),
            ],
            severity="warn",
        )

    def test_allowed_with_valid_grant_and_memory(self):
        gate = ConstraintGate(rules=[self._scope_rule(), self._freeze_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            standing_grants=[_make_standing_grant()],
            continuity_memories=[_make_continuity_memory()],
        )

        assert result.verdict == "pass"
        assert result.status == "allowed"
        assert result.failed_rules == []
        assert result.timing_ms is not None

    def test_denied_on_scope_mismatch(self):
        gate = ConstraintGate(rules=[self._scope_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            standing_grants=[_make_standing_grant(action="read")],
        )

        assert result.verdict == "block"
        assert result.status == "denied"
        assert any(r["rule_id"] == "standing.scope_match" for r in result.failed_rules)

    def test_denied_on_frozen_target(self):
        gate = ConstraintGate(rules=[self._freeze_rule()])
        frozen_memory = _make_continuity_memory(content={"frozen": "true"})
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            continuity_memories=[frozen_memory],
        )

        assert result.verdict == "block"
        assert result.status == "denied"
        assert any(
            r["rule_id"] == "continuity.no_frozen_target"
            for r in result.failed_rules
        )

    def test_denied_on_missing_standing(self):
        """No standing grant → scope fact missing → rule fails closed."""
        gate = ConstraintGate(rules=[self._scope_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            # No standing grants provided
        )

        assert result.verdict == "block"
        assert result.status == "denied"

    def test_denied_on_missing_continuity(self):
        """No continuity memory → frozen fact missing → rule fails closed."""
        gate = ConstraintGate(rules=[self._freeze_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            # No continuity memories provided
        )

        assert result.verdict == "block"
        assert result.status == "denied"

    def test_warning_on_advisory_reliance(self):
        gate = ConstraintGate(rules=[self._stale_warning_rule()])
        advisory_memory = _make_continuity_memory(reliance_class="advisory")
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            continuity_memories=[advisory_memory],
        )

        assert result.verdict == "warn"
        assert result.status == "allowed"  # verifier says allowed
        assert any(
            r["rule_id"] == "continuity.stale_advisory"
            for r in result.warnings
        )

    def test_contradictory_facts_return_block(self):
        """Contradictory upstream state → invalid_input → block."""
        gate = ConstraintGate(rules=[self._freeze_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            continuity_memories=[
                _make_continuity_memory(
                    memory_id="mem_001", content={"frozen": "true"}
                ),
                _make_continuity_memory(
                    memory_id="mem_002", content={"frozen": "false"}
                ),
            ],
        )

        assert result.verdict == "block"
        assert result.status == "invalid_input"
        assert len(result.contradictions) > 0

    def test_source_traceability(self):
        """Facts carry source IDs back to Standing/Continuity artifacts."""
        gate = ConstraintGate(rules=[self._scope_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            standing_grants=[_make_standing_grant(grant_id="g-999")],
        )

        # used_facts should contain sources tracing to upstream artifacts
        standing_facts = [
            f for f in result.used_facts
            if f.get("source", "").startswith("standing:")
        ]
        assert len(standing_facts) > 0
        assert any("g-999" in f["source"] for f in standing_facts)

    def test_receipt_emission_on_allow(self):
        receipts = FakeReceiptSystem()
        gate = ConstraintGate(
            receipt_system=receipts,
            rules=[self._scope_rule()],
        )
        gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            standing_grants=[_make_standing_grant()],
        )

        assert len(receipts.receipts) == 1
        r = receipts.receipts[0]
        assert r["gate"] == GATE_NAME
        assert r["verdict"] == "pass"
        assert r["subject_kind"] == "constraint_check"

    def test_receipt_emission_on_deny(self):
        receipts = FakeReceiptSystem()
        gate = ConstraintGate(
            receipt_system=receipts,
            rules=[self._scope_rule()],
        )
        gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            standing_grants=[_make_standing_grant(action="read")],
        )

        assert len(receipts.receipts) == 1
        assert receipts.receipts[0]["verdict"] == "block"

    def test_receipt_evidence_has_failed_rules(self):
        receipts = FakeReceiptSystem()
        gate = ConstraintGate(
            receipt_system=receipts,
            rules=[self._scope_rule()],
        )
        gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            standing_grants=[_make_standing_grant(action="read")],
        )

        evidence = receipts.receipts[0]["evidence_bundle"]
        assert "failed_rules" in evidence
        assert evidence["verifier_status"] == "denied"

    def test_receipt_policy_includes_rule_ids(self):
        receipts = FakeReceiptSystem()
        gate = ConstraintGate(
            receipt_system=receipts,
            rules=[self._scope_rule(), self._freeze_rule()],
        )
        gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            standing_grants=[_make_standing_grant()],
            continuity_memories=[_make_continuity_memory()],
        )

        policy = receipts.receipts[0]["gate_config"]
        assert policy["gate"] == GATE_NAME
        assert policy["rule_count"] == 2
        assert "standing.scope_match" in policy["rule_ids"]
        assert "continuity.no_frozen_target" in policy["rule_ids"]

    def test_bad_standing_grant_skipped_gracefully(self):
        """Malformed standing grant doesn't crash — skipped with warning."""
        gate = ConstraintGate(rules=[self._scope_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            standing_grants=[{"garbage": True}],  # Missing required keys
        )

        # Should not crash — returns denied (no facts to satisfy rule)
        assert result.verdict == "block"
        assert result.status == "denied"

    def test_bad_continuity_memory_skipped_gracefully(self):
        """Malformed continuity memory doesn't crash — skipped with warning."""
        gate = ConstraintGate(rules=[self._freeze_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            continuity_memories=[{"garbage": True}],
        )

        assert result.verdict == "block"
        assert result.status == "denied"

    def test_no_rules_allows_everything(self):
        """With no rules configured, everything is allowed."""
        gate = ConstraintGate(rules=[])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
        )

        assert result.verdict == "pass"
        assert result.status == "allowed"

    def test_extra_facts_are_included(self):
        """Extra facts passed directly are included in verification."""
        gate = ConstraintGate(rules=[self._freeze_rule()])
        result = gate.check(
            action="deploy",
            actor="wl:deploy-bot:host-abc",
            target="prod/web-api",
            scope="deploy",
            extra_facts=[
                Fact(subject="target", field="frozen", value="false", source="manual"),
            ],
        )

        assert result.verdict == "pass"
        assert result.status == "allowed"
