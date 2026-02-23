# SPDX-License-Identifier: Apache-2.0
"""Tests for the composition gate (chain_gate.py) — Phase 2B detect-only."""

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from governor.chain_gate import (
    ActionLog,
    ActionLogStore,
    ActionStep,
    AnnotationSource,
    CapabilityClass,
    ChainEvalResult,
    ChainGate,
    ChainRuleSet,
    CompositionRule,
    DataSensitivity,
    HASHED_STEP_FIELDS,
    SENSITIVITY_ORDER,
    TrustDomain,
    annotate_step,
    compute_action_log_hash,
    edge_key,
    load_chain_rules,
    sanitize_correlation_id,
    sensitivity_gte,
)
from governor.gate_receipt import canonical_json


# =============================================================================
# Helpers
# =============================================================================


def _test_policy(rules=(), default_verdict="pass"):
    """Build a PolicyRuleSet for testing."""
    from governor.policy_engine import PolicyRuleSet
    return PolicyRuleSet(
        policy_bundle_id="test-bundle",
        policy_bundle_version="1.0.0",
        rules=rules,
        default_verdict=default_verdict,
    )


def _step(
    tool_id: str = "read_file",
    cap: CapabilityClass = CapabilityClass.FILE_READ,
    trust: TrustDomain = TrustDomain.LOCAL,
    sens: DataSensitivity = DataSensitivity.NONE,
    result_status: str = "ok",
    args_hash: str = "abc123",
    **kwargs,
) -> ActionStep:
    return ActionStep(
        tool_id=tool_id,
        capability_class=cap,
        trust_domain=trust,
        data_sensitivity=sens,
        result_status=result_status,
        args_hash=args_hash,
        **kwargs,
    )


def _secret_read_step() -> ActionStep:
    return _step(
        tool_id="read_file",
        cap=CapabilityClass.FILE_READ,
        sens=DataSensitivity.SECRET_CANDIDATE,
        args_hash="secret_hash",
    )


def _egress_step() -> ActionStep:
    return _step(
        tool_id="http_post",
        cap=CapabilityClass.NETWORK_EGRESS,
        trust=TrustDomain.EXTERNAL,
        sens=DataSensitivity.NONE,
        args_hash="egress_hash",
    )


def _exfiltration_rule() -> CompositionRule:
    """The canonical exfiltration rule: secret read → external egress."""
    return CompositionRule(
        rule_id="exfil-001",
        description="Secret read followed by external egress",
        prior_sensitivity_gte=DataSensitivity.SECRET_CANDIDATE,
        proposed_capability=CapabilityClass.NETWORK_EGRESS,
        proposed_trust_domain=TrustDomain.EXTERNAL,
        effect="deny",
    )


def _make_rules(*rules: CompositionRule) -> ChainRuleSet:
    return ChainRuleSet(rules=tuple(rules))


def _make_log(correlation_id: str = "test-task-1", steps: list[ActionStep] | None = None) -> ActionLog:
    return ActionLog(
        correlation_id=correlation_id,
        steps=steps or [],
        created_at="2026-02-23T00:00:00Z",
    )


# =============================================================================
# TestEnums
# =============================================================================


class TestEnums:
    def test_sensitivity_order_explicit(self):
        """NONE < INTERNAL < SECRET_CANDIDATE < CLASSIFIED."""
        assert SENSITIVITY_ORDER["none"] < SENSITIVITY_ORDER["internal"]
        assert SENSITIVITY_ORDER["internal"] < SENSITIVITY_ORDER["secret_candidate"]
        assert SENSITIVITY_ORDER["secret_candidate"] < SENSITIVITY_ORDER["classified"]

    def test_sensitivity_gte_helper(self):
        """gte comparisons correct (not lexicographic)."""
        assert sensitivity_gte(DataSensitivity.CLASSIFIED, DataSensitivity.NONE)
        assert sensitivity_gte(DataSensitivity.SECRET_CANDIDATE, DataSensitivity.SECRET_CANDIDATE)
        assert sensitivity_gte(DataSensitivity.SECRET_CANDIDATE, DataSensitivity.INTERNAL)
        assert not sensitivity_gte(DataSensitivity.NONE, DataSensitivity.INTERNAL)
        assert not sensitivity_gte(DataSensitivity.INTERNAL, DataSensitivity.SECRET_CANDIDATE)

    def test_unknown_sensitivity_raises(self):
        """Bad value not silently accepted."""
        with pytest.raises(KeyError):
            SENSITIVITY_ORDER["top_secret"]


# =============================================================================
# TestActionStep
# =============================================================================


class TestActionStep:
    def test_step_creation(self):
        s = _step()
        assert s.tool_id == "read_file"
        assert s.capability_class == CapabilityClass.FILE_READ
        assert s.result_status == "ok"

    def test_step_to_dict_round_trip(self):
        s = _step(timestamp="2026-01-01T00:00:00Z", duration_ms=42.5)
        d = s.to_dict()
        s2 = ActionStep.from_dict(d)
        assert s2.tool_id == s.tool_id
        assert s2.capability_class == s.capability_class
        assert s2.timestamp == s.timestamp
        assert s2.duration_ms == s.duration_ms

    def test_step_annotation_source_tracked(self):
        s = _step(
            capability_source=AnnotationSource.TOOL_METADATA,
            sensitivity_source=AnnotationSource.INLINE_PATH_HEURISTIC,
        )
        assert s.capability_source == AnnotationSource.TOOL_METADATA
        assert s.sensitivity_source == AnnotationSource.INLINE_PATH_HEURISTIC
        d = s.to_dict()
        assert d["capability_source"] == "tool_metadata"
        assert d["sensitivity_source"] == "path_heuristic"


# =============================================================================
# TestCompositionRule
# =============================================================================


class TestCompositionRule:
    def test_rule_creation(self):
        r = _exfiltration_rule()
        assert r.rule_id == "exfil-001"
        assert r.effect == "deny"
        assert r.prior_sensitivity_gte == DataSensitivity.SECRET_CANDIDATE

    def test_rule_with_unless(self):
        r = CompositionRule(
            rule_id="r1",
            prior_sensitivity_gte=DataSensitivity.INTERNAL,
            proposed_capability=CapabilityClass.NETWORK_EGRESS,
            unless_condition="approved_egress",
        )
        assert r.unless_condition == "approved_egress"

    def test_rule_to_dict_round_trip(self):
        r = _exfiltration_rule()
        d = r.to_dict()
        r2 = CompositionRule.from_dict(d)
        assert r2.rule_id == r.rule_id
        assert r2.prior_sensitivity_gte == r.prior_sensitivity_gte
        assert r2.proposed_capability == r.proposed_capability
        assert r2.proposed_trust_domain == r.proposed_trust_domain


# =============================================================================
# TestActionLog
# =============================================================================


class TestActionLog:
    def test_log_append_and_length(self):
        log = _make_log()
        assert len(log.steps) == 0
        log.append(_step())
        assert len(log.steps) == 1
        log.append(_step())
        assert len(log.steps) == 2

    def test_log_hash_stable(self):
        """Same steps → same hash."""
        s1, s2 = _step(args_hash="a"), _step(args_hash="b")
        _, h1 = compute_action_log_hash([s1, s2])
        _, h2 = compute_action_log_hash([s1, s2])
        assert h1 == h2

    def test_log_hash_excludes_timestamps(self):
        """Volatile fields don't affect hash."""
        s1 = _step(timestamp="2026-01-01T00:00:00Z", duration_ms=100.0)
        s2 = _step(timestamp="2099-12-31T23:59:59Z", duration_ms=999.0)
        _, h1 = compute_action_log_hash([s1])
        _, h2 = compute_action_log_hash([s2])
        assert h1 == h2

    def test_log_round_trip(self):
        log = _make_log(steps=[_step(), _secret_read_step()])
        log.dedupe_counts["rule1:edge1"] = 3
        d = log.to_dict()
        log2 = ActionLog.from_dict(d)
        assert log2.correlation_id == log.correlation_id
        assert len(log2.steps) == 2
        assert log2.dedupe_counts == {"rule1:edge1": 3}

    def test_log_dedupe_record_match(self):
        log = _make_log()
        assert log.record_match("key1") == 1
        assert log.record_match("key1") == 2
        assert log.record_match("key2") == 1
        assert log.dedupe_counts["key1"] == 2


# =============================================================================
# TestAnnotation
# =============================================================================


class TestAnnotation:
    def test_annotate_file_read(self):
        s = annotate_step("read_file", {"path": "/tmp/data.txt"})
        assert s.capability_class == CapabilityClass.FILE_READ
        assert s.capability_source == AnnotationSource.TOOL_METADATA

    def test_annotate_secret_path(self):
        s = annotate_step("read_file", {"path": "/app/.env"})
        assert s.data_sensitivity == DataSensitivity.SECRET_CANDIDATE
        assert s.sensitivity_source == AnnotationSource.INLINE_PATH_HEURISTIC

    def test_annotate_unknown_tool(self):
        s = annotate_step("my_custom_tool", {})
        assert s.capability_class == CapabilityClass.UNKNOWN
        assert s.capability_source == AnnotationSource.FALLBACK

    def test_annotate_external_url(self):
        s = annotate_step("http_post", {"url": "https://attacker.com/api"})
        assert s.trust_domain == TrustDomain.EXTERNAL
        assert s.trust_domain_source == AnnotationSource.INLINE_PATH_HEURISTIC

    def test_annotate_args_hash_deterministic(self):
        s1 = annotate_step("read_file", {"path": "/tmp/x"})
        s2 = annotate_step("read_file", {"path": "/tmp/x"})
        assert s1.args_hash == s2.args_hash

    def test_annotate_no_args(self):
        s = annotate_step("bash")
        assert s.args_hash  # should have a hash even for empty args
        assert s.data_sensitivity == DataSensitivity.NONE


# =============================================================================
# TestRuleEvaluation
# =============================================================================


class TestRuleEvaluation:
    def setup_method(self):
        self.gate = ChainGate()

    def test_single_step_always_allow(self):
        """No prior steps → no composition to deny."""
        log = _make_log()
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, _egress_step(), rules)
        assert result.kernel_verdict == "allow"
        assert not result.composition_match

    def test_secret_then_egress_deny(self):
        """Canonical exfiltration chain: secret read → external egress."""
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, _egress_step(), rules)
        assert result.kernel_verdict == "deny"
        assert result.composition_match
        assert "exfil-001" in result.matched_rule_ids
        assert result.verdict_reason == "composition_denied"

    def test_secret_then_egress_with_exception_allow(self):
        """UNLESS satisfied → rule doesn't contribute to deny."""
        rule = CompositionRule(
            rule_id="exfil-002",
            prior_sensitivity_gte=DataSensitivity.SECRET_CANDIDATE,
            proposed_capability=CapabilityClass.NETWORK_EGRESS,
            proposed_trust_domain=TrustDomain.EXTERNAL,
            unless_condition="approved_egress",
            effect="deny",
        )
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(rule)
        result = self.gate.evaluate(
            log, _egress_step(), rules,
            exceptions={"approved_egress"},
        )
        assert result.kernel_verdict == "allow"
        assert result.composition_match  # rule matched, but exception satisfied
        assert result.exception_results["exfil-002"] is True

    def test_all_rules_evaluated_not_first_match(self):
        """Multiple rules fire — not first-match-wins."""
        rule1 = _exfiltration_rule()
        rule2 = CompositionRule(
            rule_id="cross-trust-001",
            prior_capability=CapabilityClass.FILE_READ,
            proposed_trust_domain=TrustDomain.EXTERNAL,
            effect="deny",
        )
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(rule1, rule2)
        result = self.gate.evaluate(log, _egress_step(), rules)
        assert len(result.matched_rule_ids) == 2
        assert "exfil-001" in result.matched_rule_ids
        assert "cross-trust-001" in result.matched_rule_ids

    def test_deny_sticky(self):
        """Mixed match/exception → one unsatisfied DENY wins."""
        rule_satisfied = CompositionRule(
            rule_id="r1",
            prior_sensitivity_gte=DataSensitivity.SECRET_CANDIDATE,
            proposed_capability=CapabilityClass.NETWORK_EGRESS,
            unless_condition="exception_1",
            effect="deny",
        )
        rule_unsatisfied = CompositionRule(
            rule_id="r2",
            prior_capability=CapabilityClass.FILE_READ,
            proposed_trust_domain=TrustDomain.EXTERNAL,
            effect="deny",
        )
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(rule_satisfied, rule_unsatisfied)
        result = self.gate.evaluate(
            log, _egress_step(), rules,
            exceptions={"exception_1"},
        )
        assert result.kernel_verdict == "deny"
        assert result.exception_results["r1"] is True
        assert result.exception_results["r2"] is False

    def test_failed_step_match_eligible_as_prior(self):
        """A failed read_file(secrets.env) may have leaked data — treat as prior."""
        failed_read = _step(
            tool_id="read_file",
            cap=CapabilityClass.FILE_READ,
            sens=DataSensitivity.SECRET_CANDIDATE,
            result_status="failed",
        )
        log = _make_log(steps=[failed_read])
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, _egress_step(), rules)
        assert result.kernel_verdict == "deny"
        assert result.composition_match

    def test_failed_step_not_match_eligible_as_proposed(self):
        """Failed proposed step is skipped (wasn't dispatched)."""
        log = _make_log(steps=[_secret_read_step()])
        failed_egress = _step(
            tool_id="http_post",
            cap=CapabilityClass.NETWORK_EGRESS,
            trust=TrustDomain.EXTERNAL,
            result_status="failed",
        )
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, failed_egress, rules)
        assert result.kernel_verdict == "allow"
        assert not result.composition_match
        assert result.verdict_reason == "failed_step_skipped"

    def test_empty_rules_allow(self):
        """No rules → always allow."""
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules()
        result = self.gate.evaluate(log, _egress_step(), rules)
        assert result.kernel_verdict == "allow"
        assert result.verdict_reason == "empty_rules"


# =============================================================================
# TestPolicyIntegration
# =============================================================================


class TestPolicyIntegration:
    def setup_method(self):
        self.gate = ChainGate()

    def test_evaluate_without_policy(self):
        """Backward compat — no policy, no fragment."""
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, _egress_step(), rules, policy=None)
        assert result.policy_fragment is None

    def test_evaluate_with_deny_all_policy_escalates(self):
        """Policy BLOCK augments effective_verdict to deny."""
        from governor.policy_engine import PolicyRule

        deny_all_policy = _test_policy(
            rules=(PolicyRule(rule_id="deny-all", effect="block", priority=100),),
            default_verdict="block",
        )
        log = _make_log(steps=[_step()])  # non-secret read
        rules = _make_rules()  # no composition rules
        result = self.gate.evaluate(log, _step(), rules, policy=deny_all_policy)
        assert result.policy_fragment is not None
        assert result.policy_fragment["policy_verdict"] == "block"

    def test_evaluate_with_pass_policy_no_downgrade(self):
        """Kernel DENY not overridden by policy PASS."""
        from governor.policy_engine import PolicyRule

        pass_policy = _test_policy(
            rules=(PolicyRule(rule_id="pass-all", effect="pass", priority=100),),
            default_verdict="pass",
        )
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, _egress_step(), rules, policy=pass_policy)
        assert result.kernel_verdict == "deny"
        assert result.effective_verdict == "deny"  # not downgraded

    def test_policy_fragment_canonical_shape(self):
        """Fragment matches frozen contract fields."""
        from governor.policy_engine import PolicyRule

        policy = _test_policy(
            rules=(PolicyRule(rule_id="warn-chains", effect="warn", priority=50),),
            default_verdict="pass",
        )
        log = _make_log(steps=[_step()])
        rules = _make_rules()
        result = self.gate.evaluate(log, _step(), rules, policy=policy)
        frag = result.policy_fragment
        assert frag is not None
        # Required keys per contract
        assert "policy_verdict" in frag
        assert "matched_rule_ids" in frag
        assert "obligation_kinds" in frag
        assert "policy_identity" in frag
        assert "applied" in frag
        assert "duration_ms" in frag

    def test_synthetic_caps_namespaced(self):
        """synthetic.comp.* prefix on capabilities."""
        from governor.policy_engine import PolicyRule
        from unittest.mock import patch, MagicMock

        policy = _test_policy(rules=(), default_verdict="pass")
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(_exfiltration_rule())

        captured_request = {}
        original_evaluate = None
        try:
            from governor import policy_engine
            original_evaluate = policy_engine.evaluate

            def capture_evaluate(request, pol, **kwargs):
                captured_request["caps"] = request.subject.capabilities
                return original_evaluate(request, pol, **kwargs)

            policy_engine.evaluate = capture_evaluate
            result = self.gate.evaluate(log, _egress_step(), rules, policy=policy)
            caps = captured_request.get("caps", ())
            assert any(c.startswith("synthetic.comp.") for c in caps)
        finally:
            if original_evaluate is not None:
                policy_engine.evaluate = original_evaluate


# =============================================================================
# TestDetectOnly
# =============================================================================


class TestDetectOnly:
    def setup_method(self):
        self.gate = ChainGate()

    def test_detect_only_mode_in_result(self):
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, _egress_step(), rules)
        assert result.mode == "detect_only"

    def test_detect_only_applied_false_with_reason(self):
        """applied=False, reason='detect_only_mode' on policy fragment."""
        from governor.policy_engine import PolicyRule

        policy = _test_policy(
            rules=(PolicyRule(rule_id="r1", effect="block", priority=100),),
            default_verdict="block",
        )
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, _egress_step(), rules, policy=policy)
        frag = result.policy_fragment
        assert frag is not None
        assert frag["applied"] is False
        assert frag["reason"] == "detect_only_mode"

    def test_kernel_match_vs_effective_verdict(self):
        """Both fields populated separately."""
        log = _make_log(steps=[_secret_read_step()])
        rules = _make_rules(_exfiltration_rule())
        result = self.gate.evaluate(log, _egress_step(), rules)
        assert result.kernel_verdict == "deny"
        assert result.effective_verdict == "deny"  # same without policy
        assert result.composition_match is True


# =============================================================================
# TestDedupe
# =============================================================================


class TestDedupe:
    def test_first_match_count_is_one(self):
        log = _make_log()
        assert log.record_match("key1") == 1

    def test_repeat_match_increments(self):
        log = _make_log()
        log.record_match("key1")
        assert log.record_match("key1") == 2

    def test_dedupe_survives_round_trip(self):
        log = _make_log()
        log.record_match("key1")
        log.record_match("key1")
        log.record_match("key2")
        d = log.to_dict()
        log2 = ActionLog.from_dict(d)
        assert log2.dedupe_counts == {"key1": 2, "key2": 1}


# =============================================================================
# TestLoadStates
# =============================================================================


class TestLoadStates:
    def test_load_valid_rules(self, tmp_path):
        rules_file = tmp_path / "chain_rules.json"
        rules_file.write_text(json.dumps({
            "rules": [_exfiltration_rule().to_dict()],
            "rule_set_version": "1.0.0",
        }))
        rs, status = load_chain_rules(rules_file)
        assert status == "loaded"
        assert len(rs.rules) == 1

    def test_load_missing_file(self, tmp_path):
        rs, status = load_chain_rules(tmp_path / "nonexistent.json")
        assert status == "missing_policy"
        assert len(rs.rules) == 0

    def test_load_corrupt_file(self, tmp_path):
        rules_file = tmp_path / "chain_rules.json"
        rules_file.write_text("this is not json {{{")
        rs, status = load_chain_rules(rules_file)
        assert status == "corrupt_fallback"
        assert len(rs.rules) == 0

    def test_load_empty_rules(self, tmp_path):
        rules_file = tmp_path / "chain_rules.json"
        rules_file.write_text(json.dumps({"rules": []}))
        rs, status = load_chain_rules(rules_file)
        assert status == "loaded_empty"
        assert len(rs.rules) == 0


# =============================================================================
# TestEdgeKey
# =============================================================================


class TestEdgeKey:
    def test_edge_key_deterministic(self):
        s1 = _secret_read_step()
        s2 = _egress_step()
        k1 = edge_key(0, 1, s1, s2)
        k2 = edge_key(0, 1, s1, s2)
        assert k1 == k2

    def test_edge_key_excludes_volatile(self):
        """Timestamps don't affect key."""
        s1a = _step(timestamp="2026-01-01T00:00:00Z")
        s1b = _step(timestamp="2099-12-31T23:59:59Z")
        s2 = _egress_step()
        k1 = edge_key(0, 1, s1a, s2)
        k2 = edge_key(0, 1, s1b, s2)
        assert k1 == k2


# =============================================================================
# TestActionLogStore
# =============================================================================


class TestActionLogStore:
    def test_store_put_get_round_trip(self, tmp_path):
        store = ActionLogStore(tmp_path / "chain_logs")
        log = _make_log(steps=[_step()])
        store.put(log)
        loaded = store.get(log.correlation_id)
        assert loaded is not None
        assert loaded.correlation_id == log.correlation_id
        assert len(loaded.steps) == 1

    def test_store_reset_clears_log(self, tmp_path):
        store = ActionLogStore(tmp_path / "chain_logs")
        log = _make_log()
        store.put(log)
        assert store.get(log.correlation_id) is not None
        assert store.reset(log.correlation_id) is True
        assert store.get(log.correlation_id) is None

    def test_store_filename_sanitized(self, tmp_path):
        store = ActionLogStore(tmp_path / "chain_logs")
        # Path traversal characters in correlation_id
        log = ActionLog(
            correlation_id="../../../etc/passwd",
            steps=[],
            created_at="2026-01-01T00:00:00Z",
        )
        store.put(log)
        # File should be in base_dir, not escaped
        files = list((tmp_path / "chain_logs").glob("*.json"))
        assert len(files) == 1
        assert files[0].parent == tmp_path / "chain_logs"
        # Should be retrievable
        loaded = store.get("../../../etc/passwd")
        assert loaded is not None
        assert loaded.correlation_id == "../../../etc/passwd"

    def test_store_list_ids(self, tmp_path):
        store = ActionLogStore(tmp_path / "chain_logs")
        store.put(_make_log("task-1"))
        store.put(_make_log("task-2"))
        ids = store.list_ids()
        assert set(ids) == {"task-1", "task-2"}


# =============================================================================
# TestHashSemantics
# =============================================================================


class TestHashSemantics:
    def test_action_log_bytes_vs_hash(self):
        """Bytes hash to digest (no double hash)."""
        steps = [_step(), _secret_read_step()]
        raw_bytes, hex_digest = compute_action_log_hash(steps)
        assert hashlib.sha256(raw_bytes).hexdigest() == hex_digest

    def test_subject_bytes_are_canonical(self):
        """Receipt subject is canonical bytes, not hash string."""
        steps = [_step()]
        raw_bytes, _ = compute_action_log_hash(steps)
        # Should be valid JSON bytes
        parsed = json.loads(raw_bytes)
        assert "steps" in parsed
        # Should be canonical (sorted keys, compact separators)
        re_encoded = canonical_json(parsed)
        assert re_encoded == raw_bytes


# =============================================================================
# TestChainRuleSet
# =============================================================================


class TestChainRuleSet:
    def test_round_trip(self):
        rs = ChainRuleSet(
            rules=(_exfiltration_rule(),),
            description="test rules",
            rule_set_version="1.0.0",
        )
        d = rs.to_dict()
        rs2 = ChainRuleSet.from_dict(d)
        assert len(rs2.rules) == 1
        assert rs2.rules[0].rule_id == "exfil-001"
        assert rs2.description == "test rules"

    def test_empty_rules_round_trip(self):
        rs = ChainRuleSet()
        d = rs.to_dict()
        rs2 = ChainRuleSet.from_dict(d)
        assert len(rs2.rules) == 0


# =============================================================================
# TestSanitizeCorrelationId
# =============================================================================


class TestSanitizeCorrelationId:
    def test_deterministic(self):
        a = sanitize_correlation_id("task-123")
        b = sanitize_correlation_id("task-123")
        assert a == b

    def test_length(self):
        """Truncated to 32 chars."""
        result = sanitize_correlation_id("anything")
        assert len(result) == 32

    def test_hex_chars_only(self):
        result = sanitize_correlation_id("../../../etc/passwd")
        assert all(c in "0123456789abcdef" for c in result)
