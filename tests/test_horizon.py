# SPDX-License-Identifier: Apache-2.0
"""Tests for tolerability horizon on GateReceipt.

Covers GOV_GAP_TOLERABILITY_HORIZON_001 acceptance criteria:
- HorizonBlock construction across the seven frozen enum values
- Schema validation (basis required for non-'none', expiry required for
  clock-bounded classes, basis_hash format, bad expiry rejection)
- Backward compatibility (receipts without horizon unchanged)
- Canonical JSON stability (horizon omitted when None, present when not)
- Receipt_id content-binding (horizon changes receipt_id, expiry changes
  receipt_id, basis changes receipt_id)
- Roundtrip through to_dict / from_dict preserves all fields
- Advisory-signal-path fixture demonstrating all seven enum values
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.gate_receipt import (
    HORIZON_BUSINESS_HOURS,
    HORIZON_DEFERRAL_PERSISTENCE_OBLIGED,
    HORIZON_EXPIRY_REQUIRED,
    HORIZON_HOURS,
    HORIZON_INDEFINITE,
    HORIZON_NONE,
    HORIZON_NOW,
    HORIZON_OBSERVE_ONLY,
    HORIZON_SCHEDULED,
    VALID_HORIZON_KINDS,
    GateReceipt,
    GateReceiptSystem,
    HorizonBlock,
    create_receipt,
)


VALID_BASIS_HASH = "sha256:" + "a" * 64
VALID_BASIS_HASH_2 = "sha256:" + "b" * 64
VALID_EXPIRY = "2026-04-24T03:00:00Z"
VALID_EXPIRY_2 = "2026-04-25T03:00:00Z"


# =============================================================================
# Enum shape and closed-set invariant
# =============================================================================


class TestHorizonEnum:
    def test_seven_values_frozen(self):
        assert len(VALID_HORIZON_KINDS) == 7
        assert VALID_HORIZON_KINDS == frozenset({
            "none", "now", "hours", "business_hours",
            "scheduled", "observe_only", "indefinite",
        })

    def test_expiry_required_subset(self):
        # Only hours, business_hours, scheduled require expiry.
        assert HORIZON_EXPIRY_REQUIRED == frozenset({
            HORIZON_HOURS, HORIZON_BUSINESS_HOURS, HORIZON_SCHEDULED,
        })

    def test_deferral_persistence_alias(self):
        # A5 persistence obligation applies to the same set as EXPIRY_REQUIRED.
        assert HORIZON_DEFERRAL_PERSISTENCE_OBLIGED == HORIZON_EXPIRY_REQUIRED


# =============================================================================
# Construction across the seven values
# =============================================================================


class TestHorizonConstruction:
    def test_none_valid(self):
        h = HorizonBlock(kind=HORIZON_NONE)
        assert h.kind == HORIZON_NONE
        assert h.basis_id is None
        assert h.basis_hash is None
        assert h.expiry is None

    def test_now_valid(self):
        h = HorizonBlock(
            kind=HORIZON_NOW,
            basis_id="policy:act_now.v1",
            basis_hash=VALID_BASIS_HASH,
        )
        assert h.kind == HORIZON_NOW

    def test_hours_valid(self):
        h = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:defer.v1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        assert h.expiry == VALID_EXPIRY

    def test_business_hours_valid(self):
        h = HorizonBlock(
            kind=HORIZON_BUSINESS_HOURS,
            basis_id="policy:defer.v1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        assert h.kind == HORIZON_BUSINESS_HOURS

    def test_scheduled_valid(self):
        h = HorizonBlock(
            kind=HORIZON_SCHEDULED,
            basis_id="event:q2_maintenance",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        assert h.kind == HORIZON_SCHEDULED

    def test_observe_only_valid_without_expiry(self):
        h = HorizonBlock(
            kind=HORIZON_OBSERVE_ONLY,
            basis_id="policy:observe.v1",
            basis_hash=VALID_BASIS_HASH,
        )
        assert h.expiry is None

    def test_indefinite_valid_without_expiry(self):
        h = HorizonBlock(
            kind=HORIZON_INDEFINITE,
            basis_id="policy:tolerated.v1",
            basis_hash=VALID_BASIS_HASH,
        )
        assert h.expiry is None


# =============================================================================
# Rejection / schema violations
# =============================================================================


class TestHorizonValidation:
    def test_invalid_kind_rejected(self):
        with pytest.raises(ValueError, match="Invalid horizon kind"):
            HorizonBlock(kind="sometimes")

    def test_non_none_without_basis_id_rejected(self):
        with pytest.raises(ValueError, match="requires basis_id"):
            HorizonBlock(kind=HORIZON_NOW, basis_hash=VALID_BASIS_HASH)

    def test_non_none_without_basis_hash_rejected(self):
        with pytest.raises(ValueError, match="requires basis_hash"):
            HorizonBlock(kind=HORIZON_NOW, basis_id="policy:p1")

    def test_bad_basis_hash_format_rejected(self):
        with pytest.raises(ValueError, match="sha256:<64 hex chars>"):
            HorizonBlock(
                kind=HORIZON_NOW,
                basis_id="policy:p1",
                basis_hash="not-a-sha256-hash",
            )

    def test_none_with_basis_rejected(self):
        # 'none' must not carry basis — prevents misrepresenting
        # non-declaration as declaration.
        with pytest.raises(ValueError, match="missing != declared-none"):
            HorizonBlock(
                kind=HORIZON_NONE,
                basis_id="policy:p1",
                basis_hash=VALID_BASIS_HASH,
            )

    def test_none_with_expiry_rejected(self):
        with pytest.raises(ValueError, match="must not carry expiry"):
            HorizonBlock(kind=HORIZON_NONE, expiry=VALID_EXPIRY)

    def test_hours_without_expiry_rejected(self):
        with pytest.raises(ValueError, match="requires expiry"):
            HorizonBlock(
                kind=HORIZON_HOURS,
                basis_id="policy:p1",
                basis_hash=VALID_BASIS_HASH,
            )

    def test_business_hours_without_expiry_rejected(self):
        with pytest.raises(ValueError, match="requires expiry"):
            HorizonBlock(
                kind=HORIZON_BUSINESS_HOURS,
                basis_id="policy:p1",
                basis_hash=VALID_BASIS_HASH,
            )

    def test_scheduled_without_expiry_rejected(self):
        with pytest.raises(ValueError, match="requires expiry"):
            HorizonBlock(
                kind=HORIZON_SCHEDULED,
                basis_id="policy:p1",
                basis_hash=VALID_BASIS_HASH,
            )

    def test_bad_expiry_format_rejected(self):
        with pytest.raises(ValueError, match="expiry must be ISO 8601"):
            HorizonBlock(
                kind=HORIZON_HOURS,
                basis_id="policy:p1",
                basis_hash=VALID_BASIS_HASH,
                expiry="whenever",
            )


# =============================================================================
# Serialization / roundtrip
# =============================================================================


class TestHorizonSerialization:
    def test_none_to_dict_minimal(self):
        h = HorizonBlock(kind=HORIZON_NONE)
        assert h.to_dict() == {"kind": "none"}

    def test_hours_to_dict_full(self):
        h = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        assert h.to_dict() == {
            "kind": "hours",
            "basis_id": "policy:p1",
            "basis_hash": VALID_BASIS_HASH,
            "expiry": VALID_EXPIRY,
        }

    def test_observe_only_omits_absent_expiry(self):
        h = HorizonBlock(
            kind=HORIZON_OBSERVE_ONLY,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
        )
        d = h.to_dict()
        assert "expiry" not in d

    def test_roundtrip_all_seven_kinds(self):
        cases = [
            HorizonBlock(kind=HORIZON_NONE),
            HorizonBlock(kind=HORIZON_NOW, basis_id="p1", basis_hash=VALID_BASIS_HASH),
            HorizonBlock(kind=HORIZON_HOURS, basis_id="p2", basis_hash=VALID_BASIS_HASH, expiry=VALID_EXPIRY),
            HorizonBlock(kind=HORIZON_BUSINESS_HOURS, basis_id="p3", basis_hash=VALID_BASIS_HASH, expiry=VALID_EXPIRY),
            HorizonBlock(kind=HORIZON_SCHEDULED, basis_id="e1", basis_hash=VALID_BASIS_HASH, expiry=VALID_EXPIRY),
            HorizonBlock(kind=HORIZON_OBSERVE_ONLY, basis_id="p4", basis_hash=VALID_BASIS_HASH),
            HorizonBlock(kind=HORIZON_INDEFINITE, basis_id="p5", basis_hash=VALID_BASIS_HASH),
        ]
        for original in cases:
            restored = HorizonBlock.from_dict(original.to_dict())
            assert restored == original

    def test_content_hash_deterministic(self):
        h1 = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        h2 = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        assert h1.content_hash() == h2.content_hash()

    def test_content_hash_changes_with_expiry(self):
        h1 = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        h2 = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY_2,
        )
        assert h1.content_hash() != h2.content_hash()


# =============================================================================
# GateReceipt integration: identity, serialization, backward compat
# =============================================================================


class TestGateReceiptHorizonIntegration:
    def _make_receipt(self, horizon=None, subject=b"hello"):
        return create_receipt(
            gate="evidence_gate",
            verdict="pass",
            subject_kind="text",
            subject_bytes=subject,
            evidence_bundle={"k": "v"},
            gate_config={"strict": True},
            timestamp="2026-04-23T00:00:00Z",
            horizon=horizon,
        )

    def test_no_horizon_backward_compat(self):
        # A receipt created without horizon must have the receipt_id it
        # would have had before horizon existed: the payload should not
        # include any ':horizon:' fragment.
        r = self._make_receipt()
        assert r.horizon is None
        # Explicitly verify the canonical payload shape via _compute_receipt_id.
        from governor.gate_receipt import _compute_receipt_id
        expected = _compute_receipt_id(
            r.schema_version, r.gate,
            r.subject_hash, r.evidence_hash, r.policy_hash,
            r.receipt_role,
            horizon_hash=None,
        )
        assert r.receipt_id == expected

    def test_horizon_presence_changes_receipt_id(self):
        r_bare = self._make_receipt()
        h = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        r_horizoned = self._make_receipt(horizon=h)
        assert r_bare.receipt_id != r_horizoned.receipt_id

    def test_horizon_expiry_changes_receipt_id(self):
        h1 = HorizonBlock(
            kind=HORIZON_HOURS, basis_id="p1", basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        h2 = HorizonBlock(
            kind=HORIZON_HOURS, basis_id="p1", basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY_2,
        )
        r1 = self._make_receipt(horizon=h1)
        r2 = self._make_receipt(horizon=h2)
        assert r1.receipt_id != r2.receipt_id

    def test_horizon_basis_changes_receipt_id(self):
        h1 = HorizonBlock(
            kind=HORIZON_NOW, basis_id="p1", basis_hash=VALID_BASIS_HASH,
        )
        h2 = HorizonBlock(
            kind=HORIZON_NOW, basis_id="p2", basis_hash=VALID_BASIS_HASH_2,
        )
        r1 = self._make_receipt(horizon=h1)
        r2 = self._make_receipt(horizon=h2)
        assert r1.receipt_id != r2.receipt_id

    def test_horizon_kind_changes_receipt_id(self):
        h1 = HorizonBlock(
            kind=HORIZON_NOW, basis_id="p1", basis_hash=VALID_BASIS_HASH,
        )
        h2 = HorizonBlock(
            kind=HORIZON_INDEFINITE, basis_id="p1", basis_hash=VALID_BASIS_HASH,
        )
        r1 = self._make_receipt(horizon=h1)
        r2 = self._make_receipt(horizon=h2)
        assert r1.receipt_id != r2.receipt_id

    def test_identical_horizon_same_receipt_id(self):
        # Content-addressed: same inputs including horizon → same id.
        h1 = HorizonBlock(
            kind=HORIZON_HOURS, basis_id="p1", basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        h2 = HorizonBlock(
            kind=HORIZON_HOURS, basis_id="p1", basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        r1 = self._make_receipt(horizon=h1)
        r2 = self._make_receipt(horizon=h2)
        assert r1.receipt_id == r2.receipt_id

    def test_to_dict_omits_horizon_when_none(self):
        r = self._make_receipt()
        d = r.to_dict()
        assert "horizon" not in d

    def test_to_dict_includes_horizon_when_present(self):
        h = HorizonBlock(
            kind=HORIZON_INDEFINITE,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
        )
        r = self._make_receipt(horizon=h)
        d = r.to_dict()
        assert d["horizon"] == {
            "kind": "indefinite",
            "basis_id": "policy:p1",
            "basis_hash": VALID_BASIS_HASH,
        }

    def test_receipt_roundtrip_no_horizon(self):
        r = self._make_receipt()
        restored = GateReceipt.from_dict(json.loads(r.to_json()))
        assert restored.horizon is None
        assert restored.receipt_id == r.receipt_id

    def test_receipt_roundtrip_with_horizon(self):
        h = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:p1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        r = self._make_receipt(horizon=h)
        restored = GateReceipt.from_dict(json.loads(r.to_json()))
        assert restored.horizon == h
        assert restored.receipt_id == r.receipt_id

    def test_parsing_legacy_receipt_without_horizon_field(self):
        # A receipt payload that has no 'horizon' key (the pre-horizon
        # shape) must deserialize with horizon=None, not raise.
        legacy = {
            "receipt_id": "anyhex" * 10 + "abcd",
            "schema_version": 3,
            "timestamp": "2026-04-23T00:00:00Z",
            "gate": "evidence_gate",
            "verdict": "pass",
            "subject_hash": "a" * 64,
            "evidence_hash": "b" * 64,
            "policy_hash": "c" * 64,
        }
        r = GateReceipt.from_dict(legacy)
        assert r.horizon is None


# =============================================================================
# Full store roundtrip
# =============================================================================


class TestHorizonInStore:
    def test_emit_and_retrieve_horizon_receipt(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)
        h = HorizonBlock(
            kind=HORIZON_HOURS,
            basis_id="policy:defer.v1",
            basis_hash=VALID_BASIS_HASH,
            expiry=VALID_EXPIRY,
        )
        receipt = system.emit(
            gate="evidence_gate",
            verdict="warn",
            subject_kind="text",
            subject_bytes=b"output",
            evidence_bundle={"k": "v"},
            gate_config={"strict": True},
            horizon=h,
        )
        assert receipt.horizon == h
        # Retrieved from disk via get_by_id must match.
        fetched = system.receipt_store.get_by_id(receipt.receipt_id)
        assert fetched is not None
        assert fetched.horizon == h
        assert fetched.receipt_id == receipt.receipt_id


# =============================================================================
# Advisory-signal-path producer fixture (GOV_GAP acceptance criterion)
# =============================================================================


class TestAdvisoryHorizonProducer:
    """One producer demonstrating all seven horizon classes.

    This fixture is the GOV_GAP_TOLERABILITY_HORIZON_001 acceptance
    criterion: at least one producer path emits horizon in a test
    fixture covering every enum value. Serves as the reference
    example for future producers.
    """

    def test_producer_emits_all_seven_kinds(self, tmp_path: Path):
        system = GateReceiptSystem(tmp_path)

        # Each advisory-path emission pairs a horizon declaration with
        # a verdict that the consumer must treat as orthogonal. The
        # horizons are orthogonal to the verdicts — e.g. block+hours
        # means "block now, condition tolerable until expiry" not
        # "soft-block."
        cases = [
            ("pass", HorizonBlock(kind=HORIZON_NONE)),
            ("block", HorizonBlock(
                kind=HORIZON_NOW, basis_id="policy:act_now",
                basis_hash=VALID_BASIS_HASH,
            )),
            ("warn", HorizonBlock(
                kind=HORIZON_HOURS, basis_id="policy:defer_hours",
                basis_hash=VALID_BASIS_HASH, expiry=VALID_EXPIRY,
            )),
            ("warn", HorizonBlock(
                kind=HORIZON_BUSINESS_HOURS, basis_id="policy:defer_bizhrs",
                basis_hash=VALID_BASIS_HASH, expiry=VALID_EXPIRY,
            )),
            ("warn", HorizonBlock(
                kind=HORIZON_SCHEDULED, basis_id="event:next_maintenance",
                basis_hash=VALID_BASIS_HASH, expiry=VALID_EXPIRY,
            )),
            ("observe", HorizonBlock(
                kind=HORIZON_OBSERVE_ONLY, basis_id="policy:watch_only",
                basis_hash=VALID_BASIS_HASH,
            )),
            ("observe", HorizonBlock(
                kind=HORIZON_INDEFINITE, basis_id="policy:tolerated_indefinite",
                basis_hash=VALID_BASIS_HASH,
            )),
        ]

        emitted = []
        for verdict, horizon in cases:
            receipt = system.emit(
                gate="advisory_signal",
                verdict=verdict,
                subject_kind="signal_id",
                subject_bytes=horizon.kind.encode("utf-8"),
                evidence_bundle={"signal": horizon.kind},
                gate_config={"producer": "advisory"},
                horizon=horizon,
            )
            emitted.append(receipt)

        # All seven kinds were emitted and are distinguishable.
        kinds_emitted = {r.horizon.kind for r in emitted}
        assert kinds_emitted == VALID_HORIZON_KINDS

        # All receipt_ids are distinct (horizon binds identity).
        receipt_ids = {r.receipt_id for r in emitted}
        assert len(receipt_ids) == len(emitted)

        # Verdict and horizon remained orthogonal — no verdict was
        # altered by the presence of horizon.
        expected_verdicts = [v for v, _ in cases]
        actual_verdicts = [r.verdict for r in emitted]
        assert expected_verdicts == actual_verdicts

    def test_consumer_fail_closed_on_undeclared_horizon(self, tmp_path: Path):
        """Documented consumer-policy behavior: undeclared horizon on an
        adverse finding is treated as 'now' by default (fail-closed).

        This test documents the contract rather than enforcing it at the
        governor layer — governor emits; consumer policy binds the
        default. The test demonstrates the producer side (no horizon
        declared) and the consumer-side rule as applied in test code.
        """
        system = GateReceiptSystem(tmp_path)
        adverse = system.emit(
            gate="advisory_signal",
            verdict="warn",  # adverse
            subject_kind="signal_id",
            subject_bytes=b"some_signal",
            evidence_bundle={"condition": "adverse"},
            gate_config={"producer": "advisory"},
            # no horizon: undeclared
        )
        assert adverse.horizon is None

        # Consumer applies fail-closed default: treat as 'now'.
        effective_horizon_kind = (
            adverse.horizon.kind if adverse.horizon is not None
            else HORIZON_NOW
        )
        assert effective_horizon_kind == HORIZON_NOW
