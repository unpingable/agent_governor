# SPDX-License-Identifier: Apache-2.0
"""Tests for the policy engine abstraction substrate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.policy_engine import (
    # Constants
    POLICY_EVAL_REQUEST_SCHEMA,
    POLICY_EVAL_RESULT_SCHEMA,
    CAPABILITY_VOCAB_VERSION,
    OBLIGATION_VOCAB_VERSION,
    POLICY_ENGINE_VERSION,
    # Enums
    PolicyVerdict,
    Capability,
    ObligationKind,
    SubjectKind,
    PayloadClass,
    DestinationClass,
    EnforcementStatus,
    TrustMode,
    # Request model
    SubjectInfo,
    PrincipalsInfo,
    ContextInfo,
    ProvenanceInfo,
    DestinationInfo,
    PayloadInfo,
    AttributesInfo,
    PolicyEvalRequest,
    request_content_hash,
    # Result model
    Obligation,
    MatchedRule,
    RationaleInfo,
    PolicyIdentity,
    PolicyEvalResult,
    ObligationEnforcementRecord,
    PolicyReceiptFragment,
    # Rule model
    PolicyRule,
    PolicyRuleSet,
    # Evaluator
    evaluate,
    default_policy,
    save_policy,
    load_policy,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_request(
    *,
    capabilities: tuple[str, ...] = ("read_fs",),
    action: str = "read",
    kind: str = "tool_call",
    subject_id: str = "test-subject",
    gate_name: str = "test_gate",
    trust_mode: str = "local",
    actor_id: str | None = None,
    agent_id: str | None = None,
    provenance_labels: tuple[str, ...] = (),
    payload_class: str | None = None,
    destination_class: str | None = None,
    extra: dict | None = None,
) -> PolicyEvalRequest:
    payload = None
    if payload_class or destination_class:
        dest = DestinationInfo(destination_class=destination_class or "unknown") if destination_class else None
        payload = PayloadInfo(payload_class=payload_class, destination=dest)

    return PolicyEvalRequest(
        request_id="req-1",
        subject=SubjectInfo(
            kind=kind,
            subject_id=subject_id,
            action=action,
            capabilities=capabilities,
        ),
        principals=PrincipalsInfo(actor_id=actor_id, agent_id=agent_id),
        context=ContextInfo(gate_name=gate_name, trust_mode=trust_mode),
        provenance=ProvenanceInfo(labels=provenance_labels),
        payload=payload,
        attributes=AttributesInfo(extra=extra or {}),
    )


def _make_rule(
    rule_id: str = "r1",
    effect: str = "pass",
    priority: int = 0,
    **kwargs,
) -> PolicyRule:
    return PolicyRule(rule_id=rule_id, effect=effect, priority=priority, **kwargs)


def _make_policy(
    *rules: PolicyRule,
    default_verdict: str = "block",
) -> PolicyRuleSet:
    return PolicyRuleSet(
        policy_bundle_id="test.bundle",
        policy_bundle_version="1.0.0",
        rules=rules,
        default_verdict=default_verdict,
    )


# ============================================================================
# Enums + Constants (~8)
# ============================================================================

class TestEnumsAndConstants:
    def test_capability_count(self):
        assert len(Capability) == 21

    def test_capability_values_are_strings(self):
        for cap in Capability:
            assert isinstance(cap.value, str)

    def test_capability_vocab_version(self):
        assert CAPABILITY_VOCAB_VERSION == "cap-v1"

    def test_obligation_kind_count(self):
        assert len(ObligationKind) == 14

    def test_obligation_vocab_version(self):
        assert OBLIGATION_VOCAB_VERSION == "obl-v1"

    def test_policy_verdict_values(self):
        assert set(v.value for v in PolicyVerdict) == {"pass", "block", "escalate", "warn"}

    def test_supporting_enums_exist(self):
        assert len(SubjectKind) == 5
        assert len(PayloadClass) == 6
        assert len(DestinationClass) == 6
        assert len(EnforcementStatus) == 3
        assert len(TrustMode) == 2

    def test_schema_constants_contain_v1(self):
        assert "v1" in POLICY_EVAL_REQUEST_SCHEMA
        assert "v1" in POLICY_EVAL_RESULT_SCHEMA


# ============================================================================
# Serialization Round-Trips (~12)
# ============================================================================

class TestSerialization:
    def test_request_full_round_trip(self):
        req = PolicyEvalRequest(
            schema=POLICY_EVAL_REQUEST_SCHEMA,
            request_id="req-42",
            created_at="2026-02-23T00:00:00Z",
            subject=SubjectInfo(
                kind="tool_call",
                subject_id="bash",
                action="exec",
                capabilities=("exec", "write_fs"),
                tool_id="bash-v1",
                tool_manifest_hash="abc123",
                capability_vocab_version="cap-v1",
            ),
            principals=PrincipalsInfo(
                actor_id="user-1", agent_id="agent-1", session_id="sess-1",
            ),
            context=ContextInfo(
                gate_name="evidence_gate",
                trust_mode="local",
                task_id="task-1",
                task_class="coding",
                lane="2",
                request_nonce="nonce-1",
            ),
            provenance=ProvenanceInfo(labels=("human",), refs=("ref-1",)),
            payload=PayloadInfo(
                payload_hash="h1",
                payload_class="repo_source",
                destination=DestinationInfo(
                    destination_class="file", identity="/tmp/out",
                ),
            ),
            attributes=AttributesInfo(
                sensitivity="high",
                is_composed=True,
                chain_length=3,
                extra={"regime": "WARM"},
            ),
        )
        d = req.to_dict()
        req2 = PolicyEvalRequest.from_dict(d)
        assert req2.to_dict() == d

    def test_request_minimal_round_trip(self):
        req = PolicyEvalRequest(
            subject=SubjectInfo(kind="tool_call", subject_id="x", action="read"),
            context=ContextInfo(gate_name="g"),
        )
        d = req.to_dict()
        req2 = PolicyEvalRequest.from_dict(d)
        assert req2.to_dict() == d

    def test_result_round_trip(self):
        result = PolicyEvalResult(
            request_id="req-1",
            verdict=PolicyVerdict.WARN,
            matched_rules=(
                MatchedRule(rule_id="r1", effect="warn", priority=5, reason_code="rc1"),
            ),
            obligations=(
                Obligation(kind="require_evidence", params={"min": 2}, priority=1),
            ),
            rationale=RationaleInfo(summary="test", reason_codes=("rc1",)),
            policy_identity=PolicyIdentity(
                policy_engine_version="1.0.0",
                policy_bundle_id="b1",
                policy_bundle_version="0.1",
            ),
        )
        d = result.to_dict()
        result2 = PolicyEvalResult.from_dict(d)
        assert result2.to_dict() == d

    def test_rule_round_trip(self):
        rule = PolicyRule(
            rule_id="r1",
            description="test rule",
            priority=10,
            match_capabilities_any=frozenset({"read_fs", "write_fs"}),
            match_capabilities_all=frozenset({"exec"}),
            match_action_types=frozenset({"exec"}),
            match_subject_kinds=frozenset({"tool_call"}),
            match_modes=frozenset({"local"}),
            match_target_pattern="^bash",
            effect="block",
            obligations=(Obligation(kind="log_high_priority"),),
            reason_code="test_block",
        )
        d = rule.to_dict()
        rule2 = PolicyRule.from_dict(d)
        assert rule2.to_dict() == d

    def test_ruleset_round_trip(self):
        rs = PolicyRuleSet(
            policy_bundle_id="test",
            policy_bundle_version="1.0",
            rules=(
                PolicyRule(rule_id="r1", effect="pass"),
                PolicyRule(rule_id="r2", effect="block"),
            ),
            default_verdict="block",
            description="test set",
        )
        d = rs.to_dict()
        rs2 = PolicyRuleSet.from_dict(d)
        assert rs2.to_dict() == d

    def test_obligation_round_trip(self):
        ob = Obligation(
            kind="require_oracle",
            params={"oracle_class": 0, "threshold": 0.9},
            obligation_id="obl-1",
            priority=5,
        )
        d = ob.to_dict()
        ob2 = Obligation.from_dict(d)
        assert ob2.to_dict() == d

    def test_matched_rule_round_trip(self):
        mr = MatchedRule(rule_id="r1", effect="escalate", priority=3, reason_code="rc")
        d = mr.to_dict()
        mr2 = MatchedRule.from_dict(d)
        assert mr2.to_dict() == d

    def test_subject_info_round_trip(self):
        si = SubjectInfo(
            kind="tool_call", subject_id="s1", action="write",
            capabilities=("write_fs",), tool_id="t1",
        )
        assert SubjectInfo.from_dict(si.to_dict()).to_dict() == si.to_dict()

    def test_principals_context_provenance_round_trip(self):
        pi = PrincipalsInfo(actor_id="a", agent_id="b", session_id="c")
        assert PrincipalsInfo.from_dict(pi.to_dict()).to_dict() == pi.to_dict()

        ci = ContextInfo(gate_name="g", trust_mode="remote", task_id="t")
        assert ContextInfo.from_dict(ci.to_dict()).to_dict() == ci.to_dict()

        pv = ProvenanceInfo(labels=("l1",), refs=("r1",))
        assert ProvenanceInfo.from_dict(pv.to_dict()).to_dict() == pv.to_dict()

    def test_payload_destination_round_trip(self):
        di = DestinationInfo(destination_class="http", identity="https://example.com")
        assert DestinationInfo.from_dict(di.to_dict()).to_dict() == di.to_dict()

        pi = PayloadInfo(
            payload_hash="h1", payload_class="secret_candidate",
            destination=di,
        )
        assert PayloadInfo.from_dict(pi.to_dict()).to_dict() == pi.to_dict()

    def test_attributes_extra_round_trip(self):
        ai = AttributesInfo(
            sensitivity="high", is_composed=True, chain_length=5,
            extra={"regime": "WARM", "custom": [1, 2]},
        )
        d = ai.to_dict()
        ai2 = AttributesInfo.from_dict(d)
        assert ai2.to_dict() == d

    def test_receipt_fragment_round_trip(self):
        frag = PolicyReceiptFragment(
            policy_verdict="pass",
            matched_rule_ids=("r1", "r2"),
            obligation_kinds=("log_high_priority",),
            policy_identity=PolicyIdentity(
                policy_engine_version="1.0.0",
                policy_bundle_id="b1",
                policy_bundle_version="0.1",
            ),
            applied=True,
            reason=None,
            duration_ms=1.23,
        )
        d = frag.to_dict()
        frag2 = PolicyReceiptFragment.from_dict(d)
        assert frag2.to_dict() == d

    def test_receipt_fragment_canonical_shape(self):
        """Lock the canonical fragment field names — composition gate depends on this."""
        frag = PolicyReceiptFragment(
            policy_verdict="block",
            matched_rule_ids=("rule-1",),
            obligation_kinds=("require_evidence",),
            applied=False,
            reason="no_escalation_handler",
            duration_ms=2.5,
        )
        d = frag.to_dict()
        # Canonical fields (frozen contract)
        assert set(d.keys()) == {
            "policy_verdict",
            "matched_rule_ids",
            "obligation_kinds",
            "policy_identity",
            "applied",
            "reason",
            "duration_ms",
        }
        assert isinstance(d["matched_rule_ids"], list)
        assert all(isinstance(x, str) for x in d["matched_rule_ids"])
        assert isinstance(d["obligation_kinds"], list)
        assert all(isinstance(x, str) for x in d["obligation_kinds"])
        assert isinstance(d["policy_identity"], dict)
        assert set(d["policy_identity"].keys()) == {
            "policy_engine_version",
            "policy_bundle_id",
            "policy_bundle_version",
        }
        assert isinstance(d["applied"], bool)
        assert isinstance(d["duration_ms"], float)

    def test_receipt_fragment_reason_omitted_when_none(self):
        """reason field absent from dict when None (not null)."""
        frag = PolicyReceiptFragment(policy_verdict="pass", applied=True)
        d = frag.to_dict()
        assert "reason" not in d
        # Round-trip still works
        frag2 = PolicyReceiptFragment.from_dict(d)
        assert frag2.reason is None

    def test_obligation_enforcement_record_round_trip(self):
        rec = ObligationEnforcementRecord(
            kind="require_evidence",
            enforcement_status="failed",
            params={"min_count": 2},
            evidence_ref="ev-2",
        )
        d = rec.to_dict()
        rec2 = ObligationEnforcementRecord.from_dict(d)
        assert rec2.to_dict() == d


# ============================================================================
# Evaluator Logic (~22)
# ============================================================================

class TestEvaluator:
    def test_empty_policy_default_verdict_block(self):
        req = _make_request()
        policy = _make_policy()
        result = evaluate(req, policy)
        assert result.verdict == PolicyVerdict.BLOCK

    def test_single_pass_rule(self):
        rule = _make_rule(match_capabilities_any=frozenset({"read_fs"}))
        result = evaluate(_make_request(), _make_policy(rule))
        assert result.verdict == PolicyVerdict.PASS

    def test_single_block_rule(self):
        rule = _make_rule(effect="block", match_capabilities_any=frozenset({"read_fs"}))
        result = evaluate(_make_request(), _make_policy(rule))
        assert result.verdict == PolicyVerdict.BLOCK

    def test_block_trumps_pass_regardless_of_priority(self):
        pass_rule = _make_rule(
            rule_id="allow", effect="pass", priority=100,
            match_capabilities_any=frozenset({"read_fs"}),
        )
        block_rule = _make_rule(
            rule_id="deny", effect="block", priority=0,
            match_capabilities_any=frozenset({"read_fs"}),
        )
        result = evaluate(
            _make_request(), _make_policy(pass_rule, block_rule),
        )
        assert result.verdict == PolicyVerdict.BLOCK

    def test_escalate_trumps_warn(self):
        warn_rule = _make_rule(
            rule_id="w", effect="warn", priority=100,
            match_capabilities_any=frozenset({"read_fs"}),
        )
        escalate_rule = _make_rule(
            rule_id="e", effect="escalate", priority=0,
            match_capabilities_any=frozenset({"read_fs"}),
        )
        result = evaluate(
            _make_request(), _make_policy(warn_rule, escalate_rule),
        )
        assert result.verdict == PolicyVerdict.ESCALATE

    def test_priority_ordering_within_class(self):
        low = _make_rule(
            rule_id="low", effect="pass", priority=1,
            match_capabilities_any=frozenset({"read_fs"}),
            reason_code="low_priority",
        )
        high = _make_rule(
            rule_id="high", effect="pass", priority=10,
            match_capabilities_any=frozenset({"read_fs"}),
            reason_code="high_priority",
        )
        result = evaluate(_make_request(), _make_policy(low, high))
        assert result.matched_rules[0].rule_id == "high"

    def test_match_capabilities_any_single(self):
        rule = _make_rule(match_capabilities_any=frozenset({"read_fs"}))
        result = evaluate(_make_request(capabilities=("read_fs",)), _make_policy(rule))
        assert result.verdict == PolicyVerdict.PASS

    def test_match_capabilities_any_multi(self):
        rule = _make_rule(
            match_capabilities_any=frozenset({"write_fs", "delete_fs"}),
        )
        # Request has write_fs — should match ANY
        result = evaluate(
            _make_request(capabilities=("write_fs",)),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_capabilities_all_composition(self):
        rule = _make_rule(
            effect="block",
            match_capabilities_all=frozenset({"exec", "network_ingress"}),
            reason_code="composition_blocked",
        )
        # Both present → match
        result = evaluate(
            _make_request(capabilities=("exec", "network_ingress")),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.BLOCK

    def test_match_capabilities_all_partial_no_fire(self):
        rule = _make_rule(
            effect="block",
            match_capabilities_all=frozenset({"exec", "network_ingress"}),
        )
        # Only one present → no match → default
        result = evaluate(
            _make_request(capabilities=("exec",)),
            _make_policy(rule, default_verdict="pass"),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_action_types(self):
        rule = _make_rule(match_action_types=frozenset({"exec"}))
        result = evaluate(
            _make_request(action="exec"), _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_subject_kinds(self):
        rule = _make_rule(match_subject_kinds=frozenset({"egress_attempt"}))
        result = evaluate(
            _make_request(kind="egress_attempt"), _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_modes(self):
        rule = _make_rule(match_modes=frozenset({"remote"}))
        result = evaluate(
            _make_request(trust_mode="remote"), _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_principal_ids(self):
        rule = _make_rule(match_principal_ids=frozenset({"agent-x"}))
        result = evaluate(
            _make_request(agent_id="agent-x"), _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_provenance_labels(self):
        rule = _make_rule(match_provenance=frozenset({"human"}))
        result = evaluate(
            _make_request(provenance_labels=("human", "reviewed")),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_payload_classes(self):
        rule = _make_rule(match_payload_classes=frozenset({"secret_candidate"}))
        result = evaluate(
            _make_request(payload_class="secret_candidate"),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_destination_classes(self):
        rule = _make_rule(match_destination_classes=frozenset({"http"}))
        result = evaluate(
            _make_request(destination_class="http"),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_target_pattern(self):
        rule = _make_rule(match_target_pattern=r"^bash")
        result = evaluate(
            _make_request(subject_id="bash-v1"), _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_and_across_fields(self):
        rule = _make_rule(
            match_capabilities_any=frozenset({"read_fs"}),
            match_modes=frozenset({"remote"}),
        )
        # Caps match but mode doesn't → no match → default block
        result = evaluate(
            _make_request(capabilities=("read_fs",), trust_mode="local"),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.BLOCK

    def test_empty_match_field_is_wildcard(self):
        rule = _make_rule()  # no match conditions = matches everything
        result = evaluate(_make_request(), _make_policy(rule))
        assert result.verdict == PolicyVerdict.PASS

    def test_no_match_default_verdict(self):
        rule = _make_rule(match_capabilities_any=frozenset({"delete_fs"}))
        result = evaluate(
            _make_request(capabilities=("read_fs",)),
            _make_policy(rule, default_verdict="escalate"),
        )
        assert result.verdict == PolicyVerdict.ESCALATE

    def test_unknown_capability_strict_taxonomy(self):
        result = evaluate(
            _make_request(capabilities=("invented_cap",)),
            _make_policy(),
            strict_taxonomy=True,
        )
        assert result.verdict == PolicyVerdict.BLOCK
        assert any(r.reason_code == "unknown_capability" for r in result.matched_rules)

    def test_unknown_capability_strict_false(self):
        rule = _make_rule()  # wildcard
        result = evaluate(
            _make_request(capabilities=("invented_cap",)),
            _make_policy(rule),
            strict_taxonomy=False,
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_pass_with_obligations(self):
        obl = Obligation(kind="require_evidence", params={"min": 1})
        rule = _make_rule(obligations=(obl,))
        result = evaluate(_make_request(), _make_policy(rule))
        assert result.verdict == PolicyVerdict.PASS
        assert result.has_obligations
        assert result.obligations[0].kind == "require_evidence"

    def test_warn_with_obligations(self):
        obl = Obligation(kind="log_high_priority")
        rule = _make_rule(effect="warn", obligations=(obl,))
        result = evaluate(_make_request(), _make_policy(rule))
        assert result.verdict == PolicyVerdict.WARN
        assert result.has_obligations

    def test_matched_rules_populated(self):
        rule = _make_rule(rule_id="my-rule", reason_code="allowed")
        result = evaluate(_make_request(), _make_policy(rule))
        assert len(result.matched_rules) == 1
        assert result.matched_rules[0].rule_id == "my-rule"

    def test_rationale_reason_codes(self):
        rule = _make_rule(reason_code="rc-test")
        result = evaluate(_make_request(), _make_policy(rule))
        assert "rc-test" in result.rationale.reason_codes


# ============================================================================
# Built-In Default Policy (~3)
# ============================================================================

class TestDefaultPolicy:
    def test_default_policy_returns_ruleset(self):
        p = default_policy()
        assert isinstance(p, PolicyRuleSet)

    def test_default_policy_blocks_everything(self):
        p = default_policy()
        result = evaluate(_make_request(), p)
        assert result.verdict == PolicyVerdict.BLOCK

    def test_default_policy_has_bundle_id(self):
        p = default_policy()
        assert p.policy_bundle_id == "governor.default"


# ============================================================================
# Persistence (~5)
# ============================================================================

class TestPersistence:
    def test_save_load_round_trip(self, tmp_path: Path):
        policy = _make_policy(
            _make_rule(rule_id="r1", effect="pass"),
            _make_rule(rule_id="r2", effect="block"),
        )
        path = tmp_path / "policy.json"
        save_policy(policy, path)
        loaded = load_policy(path)
        assert loaded.to_dict() == policy.to_dict()

    def test_canonical_json_determinism(self, tmp_path: Path):
        policy = _make_policy(
            _make_rule(rule_id="r1"),
            _make_rule(rule_id="r2"),
        )
        p1 = tmp_path / "p1.json"
        p2 = tmp_path / "p2.json"
        save_policy(policy, p1)
        save_policy(policy, p2)
        assert p1.read_bytes() == p2.read_bytes()

    def test_policy_many_rules_round_trip(self, tmp_path: Path):
        rules = tuple(
            _make_rule(rule_id=f"r{i}", priority=i)
            for i in range(50)
        )
        policy = _make_policy(*rules)
        path = tmp_path / "big.json"
        save_policy(policy, path)
        loaded = load_policy(path)
        assert len(loaded.rules) == 50

    def test_version_fields_preserved(self, tmp_path: Path):
        policy = PolicyRuleSet(
            policy_bundle_id="test",
            policy_bundle_version="2.0.0",
            capability_vocab_version="cap-v1",
            obligation_vocab_version="obl-v1",
        )
        path = tmp_path / "v.json"
        save_policy(policy, path)
        loaded = load_policy(path)
        assert loaded.capability_vocab_version == "cap-v1"
        assert loaded.obligation_vocab_version == "obl-v1"
        assert loaded.policy_bundle_version == "2.0.0"

    def test_request_content_hash_deterministic(self):
        req = _make_request()
        h1 = request_content_hash(req)
        h2 = request_content_hash(req)
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex


# ============================================================================
# Golden Fixtures (~4)
# ============================================================================

class TestGoldenFixtures:
    def test_simple_pass_read_fs(self):
        """Simple scenario: read_fs allowed by explicit rule."""
        rule = _make_rule(
            rule_id="allow-read",
            effect="pass",
            match_capabilities_any=frozenset({"read_fs"}),
            reason_code="read_allowed",
        )
        result = evaluate(
            _make_request(capabilities=("read_fs",), action="read"),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS
        assert result.allowed

    def test_block_with_reason_codes(self):
        """Block scenario: write_fs denied with reason."""
        rule = _make_rule(
            rule_id="deny-write",
            effect="block",
            match_capabilities_any=frozenset({"write_fs"}),
            reason_code="write_blocked",
            explanation="Writes are prohibited in this context.",
        )
        result = evaluate(
            _make_request(capabilities=("write_fs",), action="write"),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.BLOCK
        assert not result.allowed
        assert "write_blocked" in result.rationale.reason_codes

    def test_chain_gate_composition_block(self):
        """Chain gate scenario: exec + network_ingress composition → BLOCK."""
        composition_rule = _make_rule(
            rule_id="block-exec-net",
            effect="block",
            match_capabilities_all=frozenset({"exec", "network_ingress"}),
            reason_code="composition_blocked",
            explanation="Exec with network ingress is a composition violation.",
        )
        result = evaluate(
            _make_request(
                capabilities=("exec", "network_ingress", "read_fs"),
                action="exec",
                kind="action_chain",
            ),
            _make_policy(composition_rule),
        )
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rules[0].reason_code == "composition_blocked"

    def test_egress_gate_escalate_with_obligations(self):
        """Egress gate: network_egress + secret_read → ESCALATE with obligations."""
        obl = Obligation(
            kind="require_human_approval",
            params={"reason": "secret egress"},
        )
        egress_rule = _make_rule(
            rule_id="escalate-secret-egress",
            effect="escalate",
            match_capabilities_all=frozenset({"network_egress", "secret_read"}),
            reason_code="secret_egress",
            obligations=(obl,),
        )
        result = evaluate(
            _make_request(
                capabilities=("network_egress", "secret_read"),
                action="send",
                kind="egress_attempt",
            ),
            _make_policy(egress_rule),
        )
        assert result.verdict == PolicyVerdict.ESCALATE
        assert not result.allowed
        assert result.has_obligations
        assert result.obligations[0].kind == "require_human_approval"


# ============================================================================
# Edge Cases (~6)
# ============================================================================

class TestEdgeCases:
    def test_request_zero_capabilities(self):
        rule = _make_rule(match_capabilities_any=frozenset({"read_fs"}))
        result = evaluate(
            _make_request(capabilities=()),
            _make_policy(rule),
        )
        # Rule doesn't match (no caps to match), falls through to default
        assert result.verdict == PolicyVerdict.BLOCK

    def test_wildcard_rule_matches_everything(self):
        rule = _make_rule()
        result = evaluate(
            _make_request(capabilities=(), action="anything", kind="gate_event"),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_invalid_regex_blocks(self):
        rule = _make_rule(
            effect="pass",
            match_target_pattern="[invalid",
        )
        # Invalid regex → no match → default block
        result = evaluate(_make_request(), _make_policy(rule))
        assert result.verdict == PolicyVerdict.BLOCK

    def test_large_rule_set(self):
        rules = []
        for i in range(100):
            rules.append(_make_rule(
                rule_id=f"r{i}",
                effect="pass",
                match_capabilities_any=frozenset({f"cap_{i}"}),
            ))
        # None match read_fs → default
        result = evaluate(
            _make_request(capabilities=("read_fs",)),
            _make_policy(*rules),
        )
        assert result.verdict == PolicyVerdict.BLOCK

    def test_multiple_classes_highest_wins(self):
        """BLOCK from low-priority rule beats PASS from high-priority rule."""
        rules = [
            _make_rule(rule_id="pass-high", effect="pass", priority=100),
            _make_rule(rule_id="warn-mid", effect="warn", priority=50),
            _make_rule(rule_id="block-low", effect="block", priority=1),
        ]
        result = evaluate(_make_request(), _make_policy(*rules))
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rules[0].rule_id == "block-low"

    def test_allowed_property(self):
        for verdict, expected in [
            (PolicyVerdict.PASS, True),
            (PolicyVerdict.WARN, True),
            (PolicyVerdict.BLOCK, False),
            (PolicyVerdict.ESCALATE, False),
        ]:
            result = PolicyEvalResult(verdict=verdict)
            assert result.allowed is expected, f"{verdict} → allowed should be {expected}"

    def test_policy_identity_in_result(self):
        rule = _make_rule()
        result = evaluate(_make_request(), _make_policy(rule))
        assert result.policy_identity.policy_engine_version == POLICY_ENGINE_VERSION
        assert result.policy_identity.policy_bundle_id == "test.bundle"

    def test_match_regimes(self):
        rule = _make_rule(match_regimes=frozenset({"WARM"}))
        result = evaluate(
            _make_request(extra={"regime": "WARM"}),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.PASS

    def test_match_regimes_no_match(self):
        rule = _make_rule(match_regimes=frozenset({"UNSTABLE"}))
        result = evaluate(
            _make_request(extra={"regime": "ELASTIC"}),
            _make_policy(rule),
        )
        assert result.verdict == PolicyVerdict.BLOCK
