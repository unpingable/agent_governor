# SPDX-License-Identifier: Apache-2.0
"""Tests for egress_gate: outbound data-flow policy gate."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from governor.egress_gate import (
    DestinationClassifier,
    EgressGate,
    EgressGateConfig,
    EgressRequest,
    EgressResult,
    JustificationCode,
    PayloadClassifier,
    _R1_SECRET_DENY,
    _R2_SENSITIVE_EXTERNAL,
    _R3_UNKNOWN_DEST,
    _R4_INTERNAL_ALLOW,
    _R5_ALLOWLISTED,
    _R6_DEFAULT,
    _max_payload_class,
)
from governor.gate_receipt import GateReceiptSystem
from governor.policy_engine import ObligationKind, PayloadClass, PolicyVerdict
from governor.provenance_labels import ProvenanceLabel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _label(
    source_class: str = "repo",
    sensitivity: str = "none",
    tool_id: str = "test",
) -> ProvenanceLabel:
    return ProvenanceLabel(
        source_class=source_class,
        sensitivity_hint=sensitivity,
        tool_id=tool_id,
        timestamp="2026-03-04T00:00:00Z",
        content_hash="abcd1234abcd1234",
    )


def _request(
    dest: str = "https://example.com",
    size: int = 100,
    labels: list[ProvenanceLabel] | None = None,
    justification: JustificationCode = JustificationCode.API_CALL,
    tool_id: str = "test_tool",
    content_probe: str | bytes | None = None,
) -> EgressRequest:
    return EgressRequest(
        destination_ref=dest,
        payload_size=size,
        provenance_labels=labels or [],
        justification=justification,
        tool_id=tool_id,
        content_probe=content_probe,
    )


# ===========================================================================
# TestPayloadClassifier
# ===========================================================================


class TestPayloadClassifier:

    def test_label_secret_candidate(self):
        labels = [_label(sensitivity="secret_candidate")]
        assert PayloadClassifier.classify(labels=labels) == PayloadClass.SECRET_CANDIDATE

    def test_label_internal(self):
        labels = [_label(sensitivity="internal")]
        assert PayloadClassifier.classify(labels=labels) == PayloadClass.REPO_SOURCE

    def test_label_none(self):
        labels = [_label(sensitivity="none")]
        assert PayloadClassifier.classify(labels=labels) == PayloadClass.UNCLASSIFIED

    def test_path_env(self):
        result = PayloadClassifier.classify(labels=[], file_path="/app/.env")
        assert result == PayloadClass.SECRET_CANDIDATE

    def test_precedence_label_over_path(self):
        # Label says secret, path is normal -> SECRET_CANDIDATE
        labels = [_label(sensitivity="secret_candidate")]
        result = PayloadClassifier.classify(labels=labels, file_path="/app/main.py")
        assert result == PayloadClass.SECRET_CANDIDATE

    def test_monotone_high_label_low_path(self):
        labels = [_label(sensitivity="secret_candidate")]
        result = PayloadClassifier.classify(labels=labels, file_path="/app/readme.md")
        assert result == PayloadClass.SECRET_CANDIDATE

    def test_multiple_labels_max_sensitivity(self):
        labels = [
            _label(sensitivity="none"),
            _label(sensitivity="internal"),
            _label(sensitivity="secret_candidate"),
        ]
        assert PayloadClassifier.classify(labels=labels) == PayloadClass.SECRET_CANDIDATE

    def test_content_probe_api_key_upgrades(self):
        result = PayloadClassifier.scan_content("key: sk-ant-abcdefghijklmnopqrstuvwxyz")
        assert result == PayloadClass.SECRET_CANDIDATE

    def test_content_probe_cannot_downgrade(self):
        # Primary is SECRET_CANDIDATE, probe returns None -> stays SECRET
        labels = [_label(sensitivity="secret_candidate")]
        primary = PayloadClassifier.classify(labels=labels)
        probe = PayloadClassifier.scan_content("nothing secret here")
        if probe is not None:
            combined = _max_payload_class(primary, probe)
        else:
            combined = primary
        assert combined == PayloadClass.SECRET_CANDIDATE

    def test_no_content_probe_no_regex_scan(self):
        # Without content, scan returns None
        result = PayloadClassifier.scan_content("")
        assert result is None

    def test_label_unknown_sensitivity(self):
        labels = [_label(sensitivity="unknown")]
        assert PayloadClassifier.classify(labels=labels) == PayloadClass.UNKNOWN


# ===========================================================================
# TestDestinationClassifier
# ===========================================================================


class TestDestinationClassifier:

    def test_github_url(self):
        cls, host = DestinationClassifier.classify("https://github.com/foo")
        assert cls == "external"
        assert host == "github.com"

    def test_localhost_with_port(self):
        cls, host = DestinationClassifier.classify("http://localhost:8080")
        assert cls == "internal"
        assert host == "localhost"

    def test_private_ip_default_port_stripped(self):
        cls, host = DestinationClassifier.classify("https://10.0.0.1:443")
        assert cls == "internal"
        assert host == "10.0.0.1"

    def test_bare_private_ip(self):
        cls, host = DestinationClassifier.classify("192.168.1.1")
        assert cls == "internal"
        assert host == "192.168.1.1"

    def test_ipv6_loopback(self):
        cls, host = DestinationClassifier.classify("[::1]")
        assert cls == "internal"
        assert host == "::1"

    def test_s3_uri(self):
        cls, host = DestinationClassifier.classify("s3://my-bucket/path")
        assert cls == "external"
        assert host == "my-bucket"

    def test_corp_tld(self):
        cls, host = DestinationClassifier.classify("https://app.corp")
        assert cls == "internal"
        assert host == "app.corp"

    def test_local_tld(self):
        cls, host = DestinationClassifier.classify("https://registry.local")
        assert cls == "internal"
        assert host == "registry.local"

    def test_internal_tld(self):
        cls, host = DestinationClassifier.classify("https://api.internal")
        assert cls == "internal"
        assert host == "api.internal"

    def test_bare_host_with_port(self):
        cls, host = DestinationClassifier.classify("host:3000")
        assert cls == "external"
        assert host == "host"

    def test_empty_string(self):
        cls, host = DestinationClassifier.classify("")
        assert cls == "unknown"
        assert host == ""

    def test_case_folding(self):
        cls, host = DestinationClassifier.classify("https://GitHub.COM/foo")
        assert cls == "external"
        assert host == "github.com"

    def test_trailing_slash_normalized(self):
        # Both should produce same host
        _, host1 = DestinationClassifier.classify("https://github.com/")
        _, host2 = DestinationClassifier.classify("https://github.com")
        assert host1 == host2 == "github.com"

    def test_unicode_hostname(self):
        cls, host = DestinationClassifier.classify("https://xn--example.com")
        assert cls == "external"
        assert host == "xn--example.com"

    def test_172_16_internal(self):
        cls, host = DestinationClassifier.classify("http://172.16.0.1")
        assert cls == "internal"

    def test_172_15_external(self):
        cls, host = DestinationClassifier.classify("http://172.15.0.1")
        assert cls == "external"


# ===========================================================================
# TestAllowlist
# ===========================================================================


class TestAllowlist:

    def test_exact_host_match(self):
        config = EgressGateConfig(
            allowed_external_hosts=frozenset({"github.com"}),
        )
        gate = EgressGate(config=config)
        result = gate.evaluate(_request(dest="https://github.com/api"))
        assert result.verdict == PolicyVerdict.PASS
        assert result.matched_rule == _R5_ALLOWLISTED

    def test_suffix_match_with_leading_dot(self):
        config = EgressGateConfig(
            allowed_external_hosts=frozenset({".github.com"}),
        )
        gate = EgressGate(config=config)
        result = gate.evaluate(_request(dest="https://api.github.com/v1"))
        assert result.verdict == PolicyVerdict.PASS
        assert result.matched_rule == _R5_ALLOWLISTED

    def test_no_substring_match(self):
        config = EgressGateConfig(
            allowed_external_hosts=frozenset({"hub"}),
        )
        gate = EgressGate(config=config)
        result = gate.evaluate(_request(dest="https://github.com/"))
        # Should NOT match — "hub" is not github.com
        assert result.matched_rule != _R5_ALLOWLISTED

    def test_allowlist_only_unclassified(self):
        config = EgressGateConfig(
            allowed_external_hosts=frozenset({"github.com"}),
        )
        gate = EgressGate(config=config)
        # REPO_SOURCE -> allowlisted host should NOT pass via R5
        labels = [_label(sensitivity="internal")]
        result = gate.evaluate(_request(
            dest="https://github.com/api",
            labels=labels,
        ))
        assert result.matched_rule != _R5_ALLOWLISTED
        assert result.verdict == PolicyVerdict.BLOCK


# ===========================================================================
# TestEgressGateRules
# ===========================================================================


class TestEgressGateRules:

    def test_r1_secret_any_block(self):
        gate = EgressGate()
        labels = [_label(sensitivity="secret_candidate")]
        result = gate.evaluate(_request(dest="https://example.com", labels=labels))
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R1_SECRET_DENY

    def test_r1_secret_internal_block(self):
        gate = EgressGate()
        labels = [_label(sensitivity="secret_candidate")]
        result = gate.evaluate(_request(dest="http://localhost:8080", labels=labels))
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R1_SECRET_DENY

    def test_r1_secret_allowlisted_block(self):
        config = EgressGateConfig(
            allowed_external_hosts=frozenset({"example.com"}),
        )
        gate = EgressGate(config=config)
        labels = [_label(sensitivity="secret_candidate")]
        result = gate.evaluate(_request(dest="https://example.com", labels=labels))
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R1_SECRET_DENY

    def test_r3_unknown_dest_block(self):
        gate = EgressGate()
        result = gate.evaluate(_request(dest=""))
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R3_UNKNOWN_DEST
        assert any(
            o.kind == ObligationKind.RESTRICT_DESTINATION.value
            for o in result.obligations
        )

    def test_r5_unclassified_allowlisted_pass(self):
        config = EgressGateConfig(
            allowed_external_hosts=frozenset({"example.com"}),
        )
        gate = EgressGate(config=config)
        result = gate.evaluate(_request(dest="https://example.com"))
        assert result.verdict == PolicyVerdict.PASS
        assert result.matched_rule == _R5_ALLOWLISTED

    def test_r4_unclassified_internal_pass(self):
        gate = EgressGate()
        result = gate.evaluate(_request(dest="http://localhost:8080"))
        assert result.verdict == PolicyVerdict.PASS
        assert result.matched_rule == _R4_INTERNAL_ALLOW

    def test_r2_repo_source_external_block(self):
        gate = EgressGate()
        labels = [_label(sensitivity="internal")]
        result = gate.evaluate(_request(dest="https://example.com", labels=labels))
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R2_SENSITIVE_EXTERNAL
        assert any(
            o.kind == ObligationKind.REQUIRE_PAYLOAD_CLASSIFICATION.value
            for o in result.obligations
        )

    def test_r2_user_requested_no_bypass(self):
        gate = EgressGate()
        labels = [_label(sensitivity="internal")]
        result = gate.evaluate(_request(
            dest="https://example.com",
            labels=labels,
            justification=JustificationCode.USER_REQUESTED,
        ))
        # USER_REQUESTED does NOT change verdict
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R2_SENSITIVE_EXTERNAL

    def test_r6_unclassified_external_strict_block(self):
        gate = EgressGate(config=EgressGateConfig(strict=True))
        result = gate.evaluate(_request(dest="https://example.com"))
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R6_DEFAULT

    def test_r6_unclassified_external_nonstrict_warn(self):
        gate = EgressGate(config=EgressGateConfig(strict=False))
        result = gate.evaluate(_request(dest="https://example.com"))
        assert result.verdict == PolicyVerdict.WARN
        assert result.matched_rule == _R6_DEFAULT

    def test_rule_ordering_r1_before_r5(self):
        config = EgressGateConfig(
            allowed_external_hosts=frozenset({"example.com"}),
        )
        gate = EgressGate(config=config)
        labels = [_label(sensitivity="secret_candidate")]
        result = gate.evaluate(_request(dest="https://example.com", labels=labels))
        assert result.matched_rule == _R1_SECRET_DENY
        assert result.verdict == PolicyVerdict.BLOCK

    def test_obligations_present_on_r3_block(self):
        gate = EgressGate()
        result = gate.evaluate(_request(dest=""))
        assert len(result.obligations) > 0

    def test_matched_rule_set_correctly(self):
        gate = EgressGate()
        result = gate.evaluate(_request(dest="http://localhost:8080"))
        assert result.matched_rule is not None

    def test_r4_repo_source_internal_pass(self):
        gate = EgressGate()
        labels = [_label(sensitivity="internal")]
        result = gate.evaluate(_request(dest="http://localhost:8080", labels=labels))
        assert result.verdict == PolicyVerdict.PASS
        assert result.matched_rule == _R4_INTERNAL_ALLOW

    def test_r2_unknown_payload_external_block(self):
        gate = EgressGate()
        labels = [_label(sensitivity="unknown")]
        result = gate.evaluate(_request(dest="https://example.com", labels=labels))
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R2_SENSITIVE_EXTERNAL


# ===========================================================================
# TestReceiptRedaction
# ===========================================================================


class TestReceiptRedaction:

    @pytest.fixture()
    def system(self, tmp_path: Path) -> GateReceiptSystem:
        return GateReceiptSystem(tmp_path)

    def _evaluate_with_receipt(
        self, system: GateReceiptSystem, dest: str = "https://secret.example.com/api/v1",
    ) -> tuple[EgressResult, dict]:
        gate = EgressGate(
            config=EgressGateConfig(strict=False),
            receipt_system=system,
        )
        result = gate.evaluate(_request(dest=dest, labels=[_label()]))
        receipts = system.receipt_store.all()
        assert len(receipts) == 1
        evidence = system.evidence_for(receipts[0])
        assert evidence is not None
        return result, evidence

    def test_raw_destination_ref_not_in_receipt(self, system: GateReceiptSystem):
        _, evidence = self._evaluate_with_receipt(system)
        evidence_str = json.dumps(evidence)
        assert "secret.example.com/api/v1" not in evidence_str

    def test_raw_payload_content_not_in_receipt(self, system: GateReceiptSystem):
        gate = EgressGate(
            config=EgressGateConfig(strict=False),
            receipt_system=system,
        )
        gate.evaluate(_request(
            dest="https://example.com",
            content_probe="my secret data here",
        ))
        receipts = system.receipt_store.all()
        evidence = system.evidence_for(receipts[0])
        evidence_str = json.dumps(evidence)
        assert "my secret data here" not in evidence_str

    def test_destination_hash_present(self, system: GateReceiptSystem):
        _, evidence = self._evaluate_with_receipt(system)
        assert "destination_hash" in evidence
        assert len(evidence["destination_hash"]) == 64  # SHA-256 hex

    def test_destination_class_present(self, system: GateReceiptSystem):
        _, evidence = self._evaluate_with_receipt(system)
        assert "destination_class" in evidence

    def test_payload_class_present(self, system: GateReceiptSystem):
        _, evidence = self._evaluate_with_receipt(system)
        assert "payload_class" in evidence

    def test_label_summaries_no_paths(self, system: GateReceiptSystem):
        gate = EgressGate(
            config=EgressGateConfig(strict=False),
            receipt_system=system,
        )
        labels = [_label(source_class="web", sensitivity="internal")]
        gate.evaluate(_request(
            dest="https://example.com",
            labels=labels,
        ))
        receipts = system.receipt_store.all()
        evidence = system.evidence_for(receipts[0])
        summaries = evidence["provenance_label_summaries"]
        assert len(summaries) == 1
        # Only source_class and sensitivity_hint — no paths, URIs, etc.
        assert set(summaries[0].keys()) == {"source_class", "sensitivity_hint"}

    def test_label_summary_content(self, system: GateReceiptSystem):
        gate = EgressGate(
            config=EgressGateConfig(strict=False),
            receipt_system=system,
        )
        labels = [_label(source_class="web", sensitivity="internal")]
        gate.evaluate(_request(dest="https://example.com", labels=labels))
        receipts = system.receipt_store.all()
        evidence = system.evidence_for(receipts[0])
        summary = evidence["provenance_label_summaries"][0]
        assert summary["source_class"] == "web"
        assert summary["sensitivity_hint"] == "internal"

    def test_timing_fragment_present(self, system: GateReceiptSystem):
        gate = EgressGate(
            config=EgressGateConfig(strict=False),
            receipt_system=system,
        )
        gate.evaluate(_request(dest="https://example.com"))
        receipts = system.receipt_store.all()
        assert receipts[0].timing is not None
        assert "duration_ms" in receipts[0].timing


# ===========================================================================
# TestEgressGateLifecycle
# ===========================================================================


class TestEgressGateLifecycle:

    def test_works_without_receipt_system(self):
        gate = EgressGate()
        result = gate.evaluate(_request(dest="https://example.com"))
        assert result.verdict is not None

    def test_stateless_multiple_evaluations(self):
        gate = EgressGate()
        r1 = gate.evaluate(_request(dest="http://localhost:8080"))
        r2 = gate.evaluate(_request(dest="https://example.com"))
        # Different verdicts, gate doesn't carry state between calls
        assert r1.verdict == PolicyVerdict.PASS
        assert r2.verdict != r1.verdict  # external -> not PASS in strict

    def test_to_dict_roundtrip(self):
        gate = EgressGate()
        result = gate.evaluate(_request(dest="http://localhost:8080"))
        d = result.to_dict()
        assert d["verdict"] == "pass"
        assert d["matched_rule"] == _R4_INTERNAL_ALLOW
        assert isinstance(d["obligations"], list)

    def test_obligations_serializable(self):
        gate = EgressGate()
        result = gate.evaluate(_request(dest=""))  # unknown -> obligations
        d = result.to_dict()
        for o in d["obligations"]:
            json.dumps(o)  # Should not raise


# ===========================================================================
# TestReceiptIntegration
# ===========================================================================


class TestReceiptIntegration:

    def test_receipt_emitted_on_pass(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        config = EgressGateConfig(
            allowed_external_hosts=frozenset({"example.com"}),
        )
        gate = EgressGate(config=config, receipt_system=system)
        gate.evaluate(_request(dest="https://example.com"))
        receipts = system.receipt_store.all()
        assert len(receipts) == 1
        assert receipts[0].verdict == "pass"
        assert receipts[0].gate == "egress_policy"

    def test_receipt_emitted_on_block(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        gate = EgressGate(receipt_system=system)
        labels = [_label(sensitivity="secret_candidate")]
        gate.evaluate(_request(dest="https://example.com", labels=labels))
        receipts = system.receipt_store.all()
        assert len(receipts) == 1
        assert receipts[0].verdict == "block"
        assert receipts[0].gate == "egress_policy"


# ===========================================================================
# TestContentProbeIntegration
# ===========================================================================


class TestContentProbeIntegration:

    def test_content_probe_upgrades_classification(self):
        gate = EgressGate(config=EgressGateConfig(strict=False))
        # No labels (UNCLASSIFIED), but probe contains secret
        result = gate.evaluate(_request(
            dest="http://localhost:8080",
            content_probe="key: sk-ant-abcdefghijklmnopqrstuvwxyz",
        ))
        assert result.payload_class == PayloadClass.SECRET_CANDIDATE
        assert result.verdict == PolicyVerdict.BLOCK
        assert result.matched_rule == _R1_SECRET_DENY

    def test_content_probe_bytes(self):
        gate = EgressGate()
        result = gate.evaluate(_request(
            dest="http://localhost:8080",
            content_probe=b"password = \"hunter2\"",
        ))
        assert result.payload_class == PayloadClass.SECRET_CANDIDATE


# ===========================================================================
# TestEdgeCases
# ===========================================================================


class TestEdgeCases:

    def test_empty_labels(self):
        gate = EgressGate(config=EgressGateConfig(strict=False))
        result = gate.evaluate(_request(dest="http://localhost:8080", labels=[]))
        assert result.payload_class == PayloadClass.UNCLASSIFIED

    def test_pii_candidate_external_block(self):
        # PII_CANDIDATE doesn't come from sensitivity mapping but test the rule
        gate = EgressGate()
        # Directly test _evaluate_rules
        verdict, rule, _, _ = gate._evaluate_rules(
            PayloadClass.PII_CANDIDATE, "external", "example.com",
        )
        assert verdict == PolicyVerdict.BLOCK
        assert rule == _R2_SENSITIVE_EXTERNAL

    def test_config_defaults(self):
        config = EgressGateConfig()
        assert config.strict is True
        assert config.allowed_external_hosts == frozenset()

    def test_justification_codes(self):
        assert JustificationCode.API_CALL.value == "api_call"
        assert JustificationCode.USER_REQUESTED.value == "user_requested"
        assert JustificationCode.AUTOMATED.value == "automated"
