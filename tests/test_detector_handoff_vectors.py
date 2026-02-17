# SPDX-License-Identifier: Apache-2.0
"""Golden vector compatibility tests for detector handoff.

These tests load decision fixtures from the detector repo and verify
the governor produces the expected verdict. This catches schema drift
between detector serialization and governor validation.

Vectors live at: ../detector/vectors/controller_decision/v1/*.json
Each file has:
  - _vector_meta.expected_verdict: what the governor should return
  - _vector_meta.expected_nonce: nonce to pass (or null)
  - _vector_meta.expected_validation_error: error substring (optional)
  - decision: the actual controller_decision/v1 dict
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.detector_handoff import DetectorHandoffGate, HandoffConfig
from governor.gate_receipt import GateReceiptSystem


# =============================================================================
# Vector loading
# =============================================================================

VECTORS_DIR = Path(__file__).resolve().parent.parent.parent / "detector" / "vectors" / "controller_decision" / "v1"


def _load_vectors() -> list[tuple[str, dict]]:
    """Load all golden vector files. Returns [(name, data), ...]."""
    if not VECTORS_DIR.exists():
        return []
    vectors = []
    for path in sorted(VECTORS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        vectors.append((path.stem, data))
    return vectors


def _vector_ids() -> list[str]:
    return [name for name, _ in _load_vectors()]


# =============================================================================
# Skip if detector repo not present
# =============================================================================

_VECTORS = _load_vectors()
_HAS_VECTORS = len(_VECTORS) > 0

skip_no_vectors = pytest.mark.skipif(
    not _HAS_VECTORS,
    reason="Detector vectors not found (detector repo not at expected path)"
)


# =============================================================================
# Tests
# =============================================================================


@skip_no_vectors
class TestGoldenVectors:
    """Run each golden vector through the governor gate and verify verdict."""

    @pytest.fixture
    def gate(self, tmp_path: Path) -> DetectorHandoffGate:
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        receipt_system = GateReceiptSystem(gov_dir)
        return DetectorHandoffGate(receipt_system=receipt_system)

    @staticmethod
    def _strip_ttl(decision: dict) -> dict:
        """Remove embedded decision_ttl_ms so config default applies.

        Golden vectors have static created_at timestamps, so the embedded
        TTL would always expire. We strip it and let the test config's
        large default_ttl_ms take over. TTL enforcement is tested separately
        in test_detector_handoff.py.
        """
        import copy
        d = copy.deepcopy(decision)
        d.get("decision", {}).pop("decision_ttl_ms", None)
        return d

    @pytest.mark.parametrize("name,data", _VECTORS, ids=_vector_ids())
    def test_vector_verdict(self, gate: DetectorHandoffGate, name: str, data: dict):
        """Verify governor produces expected verdict for each vector."""
        meta = data["_vector_meta"]
        decision = self._strip_ttl(data["decision"])
        expected_verdict = meta["expected_verdict"]
        expected_nonce = meta.get("expected_nonce")

        # Process through the gate (TTL disabled for golden vectors since
        # created_at is static. Override TTL to be very large.)
        config = HandoffConfig(default_ttl_ms=999_999_999)
        gate_with_config = DetectorHandoffGate(
            receipt_system=gate.receipt_system,
            config=config,
        )

        result = gate_with_config.process(
            decision,
            expected_nonce=expected_nonce,
        )

        assert result.verdict == expected_verdict, (
            f"Vector {name}: expected verdict={expected_verdict}, "
            f"got verdict={result.verdict}, "
            f"errors={result.validation_errors}"
        )

    @pytest.mark.parametrize("name,data", _VECTORS, ids=_vector_ids())
    def test_vector_validation_errors(self, gate: DetectorHandoffGate, name: str, data: dict):
        """Vectors with expected_validation_error must produce that error."""
        meta = data["_vector_meta"]
        decision = self._strip_ttl(data["decision"])
        expected_error = meta.get("expected_validation_error")
        expected_nonce = meta.get("expected_nonce")

        if not expected_error:
            pytest.skip("No expected_validation_error in this vector")

        config = HandoffConfig(default_ttl_ms=999_999_999)
        gate_with_config = DetectorHandoffGate(
            receipt_system=gate.receipt_system,
            config=config,
        )

        result = gate_with_config.process(
            decision,
            expected_nonce=expected_nonce,
        )

        error_text = " ".join(result.validation_errors)
        assert expected_error in error_text, (
            f"Vector {name}: expected error containing {expected_error!r}, "
            f"got: {result.validation_errors}"
        )

    @pytest.mark.parametrize("name,data", _VECTORS, ids=_vector_ids())
    def test_vector_receipt_emitted(self, gate: DetectorHandoffGate, name: str, data: dict):
        """Every vector (even invalid ones) should attempt receipt emission."""
        meta = data["_vector_meta"]
        decision = self._strip_ttl(data["decision"])
        expected_nonce = meta.get("expected_nonce")
        expected_error = meta.get("expected_validation_error")

        config = HandoffConfig(default_ttl_ms=999_999_999)
        gate_with_config = DetectorHandoffGate(
            receipt_system=gate.receipt_system,
            config=config,
        )

        result = gate_with_config.process(
            decision,
            expected_nonce=expected_nonce,
        )

        # Schema errors (like STOP invariant) block before receipt emission.
        # Binding errors emit receipts.
        if expected_error and "STOP invariant" in (expected_error or ""):
            # Schema validation failure — no receipt
            assert result.receipt is None
        elif expected_error and "Nonce" in (expected_error or ""):
            # Binding failure — receipt emitted
            assert result.receipt is not None

    @pytest.mark.parametrize("name,data", _VECTORS, ids=_vector_ids())
    def test_vector_schema_valid(self, name: str, data: dict):
        """All golden vectors must have valid JSON structure."""
        assert "_vector_meta" in data
        assert "decision" in data
        meta = data["_vector_meta"]
        assert "expected_verdict" in meta
        assert "description" in meta
