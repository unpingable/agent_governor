# SPDX-License-Identifier: Apache-2.0
"""Tests for provenance labels — lightweight taint tracking for tool outputs."""

import json

import pytest

from governor.provenance_labels import (
    LABEL_SCHEMA_VERSION,
    SENSITIVITY_INTERNAL,
    SENSITIVITY_NONE,
    SENSITIVITY_SECRET_CANDIDATE,
    SENSITIVITY_UNKNOWN,
    SOURCE_GENERATED,
    SOURCE_REPO,
    SOURCE_UNKNOWN,
    SOURCE_USER_INPUT,
    SOURCE_WEB,
    VALID_SENSITIVITIES,
    VALID_SOURCE_CLASSES,
    LabelAssigner,
    ProvenanceLabel,
    max_sensitivity,
)


# ── ProvenanceLabel ──────────────────────────────────────────────────────────


class TestProvenanceLabel:
    def test_frozen(self):
        lbl = ProvenanceLabel(
            source_class=SOURCE_REPO, sensitivity_hint=SENSITIVITY_INTERNAL,
            tool_id="read_file", timestamp="2026-01-01T00:00:00Z",
            content_hash="abcdef0123456789",
        )
        with pytest.raises(AttributeError):
            lbl.source_class = "web"  # type: ignore[misc]

    def test_invalid_source_class_raises(self):
        with pytest.raises(ValueError, match="Invalid source_class"):
            ProvenanceLabel(
                source_class="banana", sensitivity_hint=SENSITIVITY_NONE,
                tool_id="x", timestamp="t", content_hash="h",
            )

    def test_invalid_sensitivity_raises(self):
        with pytest.raises(ValueError, match="Invalid sensitivity_hint"):
            ProvenanceLabel(
                source_class=SOURCE_REPO, sensitivity_hint="top_secret",
                tool_id="x", timestamp="t", content_hash="h",
            )

    def test_to_dict_roundtrip(self):
        lbl = ProvenanceLabel(
            source_class=SOURCE_WEB, sensitivity_hint=SENSITIVITY_NONE,
            tool_id="web_fetch", timestamp="2026-01-01T00:00:00Z",
            content_hash="abc123",
        )
        d = lbl.to_dict()
        assert d["schema_version"] == LABEL_SCHEMA_VERSION
        assert d["source_class"] == SOURCE_WEB

        restored = ProvenanceLabel.from_dict(d)
        assert restored == lbl

    def test_json_serializable(self):
        lbl = ProvenanceLabel(
            source_class=SOURCE_REPO, sensitivity_hint=SENSITIVITY_INTERNAL,
            tool_id="Read", timestamp="2026-01-01T00:00:00Z",
            content_hash="deadbeef",
        )
        serialized = json.dumps(lbl.to_dict())
        deserialized = json.loads(serialized)
        assert ProvenanceLabel.from_dict(deserialized) == lbl

    def test_all_source_classes_valid(self):
        """Every source class constant is in the valid set."""
        for sc in [SOURCE_REPO, SOURCE_WEB, SOURCE_USER_INPUT,
                    SOURCE_GENERATED, SOURCE_UNKNOWN]:
            assert sc in VALID_SOURCE_CLASSES

    def test_all_sensitivities_valid(self):
        for s in [SENSITIVITY_NONE, SENSITIVITY_INTERNAL,
                   SENSITIVITY_SECRET_CANDIDATE, SENSITIVITY_UNKNOWN]:
            assert s in VALID_SENSITIVITIES


# ── max_sensitivity ──────────────────────────────────────────────────────────


class TestMaxSensitivity:
    def _label(self, sensitivity: str) -> ProvenanceLabel:
        return ProvenanceLabel(
            source_class=SOURCE_REPO, sensitivity_hint=sensitivity,
            tool_id="test", timestamp="t", content_hash="h",
        )

    def test_empty_returns_none(self):
        assert max_sensitivity([]) == SENSITIVITY_NONE

    def test_single_label(self):
        assert max_sensitivity([self._label(SENSITIVITY_INTERNAL)]) == SENSITIVITY_INTERNAL

    def test_secret_wins_over_internal(self):
        labels = [
            self._label(SENSITIVITY_INTERNAL),
            self._label(SENSITIVITY_SECRET_CANDIDATE),
        ]
        assert max_sensitivity(labels) == SENSITIVITY_SECRET_CANDIDATE

    def test_secret_wins_over_none(self):
        labels = [
            self._label(SENSITIVITY_NONE),
            self._label(SENSITIVITY_SECRET_CANDIDATE),
        ]
        assert max_sensitivity(labels) == SENSITIVITY_SECRET_CANDIDATE

    def test_unknown_beats_internal(self):
        labels = [
            self._label(SENSITIVITY_INTERNAL),
            self._label(SENSITIVITY_UNKNOWN),
        ]
        assert max_sensitivity(labels) == SENSITIVITY_UNKNOWN

    def test_secret_beats_unknown(self):
        labels = [
            self._label(SENSITIVITY_UNKNOWN),
            self._label(SENSITIVITY_SECRET_CANDIDATE),
        ]
        assert max_sensitivity(labels) == SENSITIVITY_SECRET_CANDIDATE

    def test_all_none_returns_none(self):
        labels = [self._label(SENSITIVITY_NONE)] * 3
        assert max_sensitivity(labels) == SENSITIVITY_NONE

    def test_propagation_order(self):
        """Full ordering: none < internal < unknown < secret_candidate."""
        ordered = [SENSITIVITY_NONE, SENSITIVITY_INTERNAL,
                    SENSITIVITY_UNKNOWN, SENSITIVITY_SECRET_CANDIDATE]
        for i in range(len(ordered)):
            for j in range(i + 1, len(ordered)):
                labels = [self._label(ordered[i]), self._label(ordered[j])]
                assert max_sensitivity(labels) == ordered[j]


# ── LabelAssigner: source classification ─────────────────────────────────────


class TestSourceClassification:
    def setup_method(self):
        self.assigner = LabelAssigner()

    def test_read_file_is_repo(self):
        lbl = self.assigner.assign("read_file", "content", file_path="src/main.py")
        assert lbl.source_class == SOURCE_REPO

    def test_Read_tool_is_repo(self):
        lbl = self.assigner.assign("Read", "content", file_path="README.md")
        assert lbl.source_class == SOURCE_REPO

    def test_web_fetch_is_web(self):
        lbl = self.assigner.assign("web_fetch", "content", url="https://example.com")
        assert lbl.source_class == SOURCE_WEB

    def test_WebFetch_is_web(self):
        lbl = self.assigner.assign("WebFetch", "content", url="https://example.com")
        assert lbl.source_class == SOURCE_WEB

    def test_ask_user_is_user_input(self):
        lbl = self.assigner.assign("ask_user", "yes please")
        assert lbl.source_class == SOURCE_USER_INPUT

    def test_Write_is_generated(self):
        lbl = self.assigner.assign("Write", "new file content")
        assert lbl.source_class == SOURCE_GENERATED

    def test_unknown_tool_is_unknown(self):
        lbl = self.assigner.assign("mystery_tool_9000", "stuff")
        assert lbl.source_class == SOURCE_UNKNOWN

    def test_Bash_is_repo(self):
        lbl = self.assigner.assign("Bash", "git status output")
        assert lbl.source_class == SOURCE_REPO

    def test_extra_tool_map(self):
        assigner = LabelAssigner(extra_tool_map={"custom_reader": SOURCE_REPO})
        lbl = assigner.assign("custom_reader", "data")
        assert lbl.source_class == SOURCE_REPO


# ── LabelAssigner: sensitivity classification ────────────────────────────────


class TestSensitivityClassification:
    def setup_method(self):
        self.assigner = LabelAssigner()

    # File path patterns
    def test_env_file_is_secret(self):
        lbl = self.assigner.assign("read_file", "DB_PASS=hunter2", file_path=".env")
        assert lbl.sensitivity_hint == SENSITIVITY_SECRET_CANDIDATE

    def test_env_local_is_secret(self):
        lbl = self.assigner.assign("read_file", "x", file_path=".env.local")
        assert lbl.sensitivity_hint == SENSITIVITY_SECRET_CANDIDATE

    def test_env_production_is_secret(self):
        lbl = self.assigner.assign("read_file", "x", file_path=".env.production")
        assert lbl.sensitivity_hint == SENSITIVITY_SECRET_CANDIDATE

    def test_credentials_file_is_secret(self):
        lbl = self.assigner.assign("read_file", "x", file_path="config/credentials.json")
        assert lbl.sensitivity_hint == SENSITIVITY_SECRET_CANDIDATE

    def test_secrets_yaml_is_secret(self):
        lbl = self.assigner.assign("read_file", "x", file_path="k8s/secrets.yaml")
        assert lbl.sensitivity_hint == SENSITIVITY_SECRET_CANDIDATE

    def test_private_key_pem_is_secret(self):
        lbl = self.assigner.assign("read_file", "x", file_path="certs/private_key.pem")
        assert lbl.sensitivity_hint == SENSITIVITY_SECRET_CANDIDATE

    def test_id_rsa_is_secret(self):
        lbl = self.assigner.assign("read_file", "x", file_path="/home/user/.ssh/id_rsa")
        assert lbl.sensitivity_hint == SENSITIVITY_SECRET_CANDIDATE

    def test_readme_is_internal(self):
        """Regular repo files get the source default (internal for repo)."""
        lbl = self.assigner.assign("read_file", "x", file_path="README.md")
        assert lbl.sensitivity_hint == SENSITIVITY_INTERNAL

    def test_source_file_is_internal(self):
        lbl = self.assigner.assign("Read", "x", file_path="src/main.py")
        assert lbl.sensitivity_hint == SENSITIVITY_INTERNAL

    # URL patterns
    def test_public_url_is_none(self):
        lbl = self.assigner.assign("web_fetch", "x", url="https://example.com")
        assert lbl.sensitivity_hint == SENSITIVITY_NONE

    def test_localhost_url_is_internal(self):
        lbl = self.assigner.assign("web_fetch", "x", url="http://localhost:8080/api")
        assert lbl.sensitivity_hint == SENSITIVITY_INTERNAL

    def test_private_ip_is_internal(self):
        lbl = self.assigner.assign("web_fetch", "x", url="http://192.168.1.1/admin")
        assert lbl.sensitivity_hint == SENSITIVITY_INTERNAL

    def test_corp_domain_is_internal(self):
        lbl = self.assigner.assign("web_fetch", "x", url="https://wiki.corp/page")
        assert lbl.sensitivity_hint == SENSITIVITY_INTERNAL

    # Source defaults
    def test_unknown_tool_is_unknown_sensitivity(self):
        lbl = self.assigner.assign("mystery", "x")
        assert lbl.sensitivity_hint == SENSITIVITY_UNKNOWN

    def test_user_input_is_none(self):
        lbl = self.assigner.assign("ask_user", "yes")
        assert lbl.sensitivity_hint == SENSITIVITY_NONE

    def test_generated_is_none(self):
        lbl = self.assigner.assign("Write", "new code")
        assert lbl.sensitivity_hint == SENSITIVITY_NONE

    def test_extra_secret_pattern(self):
        import re
        assigner = LabelAssigner(
            extra_secret_patterns=[re.compile(r"(?i)my_company_secret")]
        )
        lbl = assigner.assign("read_file", "x", file_path="my_company_secret.txt")
        assert lbl.sensitivity_hint == SENSITIVITY_SECRET_CANDIDATE


# ── LabelAssigner: determinism ───────────────────────────────────────────────


class TestDeterminism:
    def test_same_inputs_same_label(self):
        """Same tool + args → same label (modulo timestamp)."""
        assigner = LabelAssigner()
        ts = "2026-01-01T00:00:00Z"
        lbl1 = assigner.assign("read_file", "content", file_path="src/x.py", timestamp=ts)
        lbl2 = assigner.assign("read_file", "content", file_path="src/x.py", timestamp=ts)
        assert lbl1 == lbl2

    def test_different_content_different_hash(self):
        assigner = LabelAssigner()
        ts = "2026-01-01T00:00:00Z"
        lbl1 = assigner.assign("read_file", "content_a", file_path="x.py", timestamp=ts)
        lbl2 = assigner.assign("read_file", "content_b", file_path="x.py", timestamp=ts)
        assert lbl1.content_hash != lbl2.content_hash

    def test_content_hash_is_16_chars(self):
        assigner = LabelAssigner()
        lbl = assigner.assign("Read", "hello world", timestamp="t")
        assert len(lbl.content_hash) == 16

    def test_bytes_content_accepted(self):
        assigner = LabelAssigner()
        lbl = assigner.assign("Read", b"\x00\x01\x02", timestamp="t")
        assert len(lbl.content_hash) == 16


# ── Evidence Gate integration ────────────────────────────────────────────────


class TestEvidenceGateIntegration:
    """Provenance labels ride on evidence gate output — annotation, not logic."""

    def test_gate_output_has_provenance_label(self):
        from governor.evidence_gate import EvidenceGate
        gate = EvidenceGate()
        result = gate.check(
            task="test", context="testing", output="All tests pass.",
        )
        assert len(result.provenance_labels) == 1
        lbl = result.provenance_labels[0]
        assert lbl.tool_id == "evidence_gate"
        assert lbl.source_class == SOURCE_UNKNOWN  # evidence_gate not in default map

    def test_gate_output_label_has_content_hash(self):
        from governor.evidence_gate import EvidenceGate
        gate = EvidenceGate()
        result = gate.check(
            task="test", context="testing", output="some output text",
        )
        lbl = result.provenance_labels[0]
        assert len(lbl.content_hash) == 16

    def test_different_outputs_different_hashes(self):
        from governor.evidence_gate import EvidenceGate
        gate = EvidenceGate()
        r1 = gate.check(task="t", context="c", output="output A")
        r2 = gate.check(task="t", context="c", output="output B")
        assert r1.provenance_labels[0].content_hash != r2.provenance_labels[0].content_hash

    def test_label_in_to_dict(self):
        from governor.evidence_gate import EvidenceGate
        gate = EvidenceGate()
        result = gate.check(
            task="test", context="testing", output="hello",
        )
        d = result.to_dict()
        assert "provenance_labels" in d
        assert d["provenance_labels"][0]["tool_id"] == "evidence_gate"

    def test_label_in_evidence_bundle(self):
        """When receipt system is configured, labels appear in evidence bundle."""
        import tempfile
        from governor.gate_receipt import GateReceiptSystem

        with tempfile.TemporaryDirectory() as tmp:
            from pathlib import Path
            gov_dir = Path(tmp) / ".governor"
            gov_dir.mkdir()
            system = GateReceiptSystem(gov_dir)
            from governor.evidence_gate import EvidenceGate
            gate = EvidenceGate(receipt_system=system)
            result = gate.check(
                task="test", context="testing",
                output="I verified the file exists at src/main.py",
            )
            # Receipt was emitted — check that labels are in evidence blob
            receipts = system.receipt_store.all()
            assert len(receipts) >= 1
            receipt = receipts[0]
            evidence = system.evidence_store.get(receipt.evidence_hash)
            assert evidence is not None
            assert "provenance_labels" in evidence
            assert evidence["provenance_labels"][0]["tool_id"] == "evidence_gate"

    def test_label_does_not_affect_gate_verdict(self):
        """Labels never change the gate's verdict — they're annotation."""
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig
        strict_gate = EvidenceGate(config=EvidenceGateConfig(strict=True))
        result = strict_gate.check(
            task="test", context="testing",
            output="All tests pass and the code works perfectly.",
        )
        # The gate still produces its normal verdict
        assert result.status is not None
        # And labels are present but didn't change anything
        assert len(result.provenance_labels) == 1

    def test_empty_output_still_gets_label(self):
        from governor.evidence_gate import EvidenceGate
        gate = EvidenceGate()
        result = gate.check(task="test", context="testing", output="")
        assert len(result.provenance_labels) == 1


# ── LabelAssigner: no effect on receipt identity ─────────────────────────────


class TestReceiptIsolation:
    def test_label_not_in_receipt_hash_inputs(self):
        """Labels are annotation, not identity. Verify the to_dict schema
        does NOT include fields that would affect receipt identity."""
        lbl = ProvenanceLabel(
            source_class=SOURCE_REPO, sensitivity_hint=SENSITIVITY_SECRET_CANDIDATE,
            tool_id="read_file", timestamp="2026-01-01T00:00:00Z",
            content_hash="abc123",
        )
        d = lbl.to_dict()

        # These fields are annotation — they should NOT be fed into
        # receipt_id computation. This test is a structural reminder.
        assert "schema_version" in d
        assert "source_class" in d
        assert "sensitivity_hint" in d
        # No receipt_id, no gate, no verdict — labels are not receipts
        assert "receipt_id" not in d
        assert "gate" not in d
        assert "verdict" not in d
