# SPDX-License-Identifier: Apache-2.0
"""S1 seam tests: StandingClient refuses on missing / dangling receipts.

Tests honor the operator preflight: minimal correctness, SPEC-defined
error shape, no new vocabulary, no real transport.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.gate_receipt import GateReceiptSystem
from governor.standing_client import (
    REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE,
    REFUSAL_KIND_STANDING_REQUIRED,
    DanglingStandingReceiptError,
    StandingClient,
    StandingReceiptRef,
    StandingRequiredError,
)


# ---------------------------------------------------------------------------
# Fake downstream standing service (operator-allowed: "fake downstreams").
# Maps digest -> StandingReceiptRef. Missing keys return None per the
# StandingVerifier contract.
# ---------------------------------------------------------------------------


class _FakeStandingService:
    """In-memory fake of the standing downstream verifier."""

    def __init__(self, receipts: dict[str, StandingReceiptRef] | None = None):
        self.receipts = dict(receipts or {})
        self.call_count = 0
        self.last_id: str | None = None

    def __call__(self, standing_receipt_id: str):
        self.call_count += 1
        self.last_id = standing_receipt_id
        return self.receipts.get(standing_receipt_id)


# A digest shaped like standing's hex SHA-256 (64 hex chars). Mirrors
# the standing-receipt crate's `digest: String` field.
_VALID_DIGEST = "a" * 64


class TestStandingClientConstruction:
    def test_requires_verify_fn(self):
        with pytest.raises(ValueError):
            StandingClient(verify_fn=None)  # type: ignore[arg-type]


class TestStandingRequired:
    def test_none_id_raises_standing_required(self):
        fake = _FakeStandingService()
        client = StandingClient(verify_fn=fake)
        with pytest.raises(StandingRequiredError) as ei:
            client.verify(None)
        assert ei.value.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED
        # Teeth: downstream never consulted.
        assert fake.call_count == 0

    def test_empty_id_raises_standing_required(self):
        fake = _FakeStandingService()
        client = StandingClient(verify_fn=fake)
        with pytest.raises(StandingRequiredError) as ei:
            client.verify("")
        assert ei.value.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED
        # Teeth: downstream never consulted on empty id.
        assert fake.call_count == 0


class TestDanglingReceiptReference:
    def test_unknown_id_raises_dangling(self):
        fake = _FakeStandingService(receipts={})
        client = StandingClient(verify_fn=fake)
        with pytest.raises(DanglingStandingReceiptError) as ei:
            client.verify("deadbeef" * 8)
        assert ei.value.refusal_kind == REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE
        assert ei.value.standing_receipt_id == "deadbeef" * 8
        # Downstream was consulted exactly once (the lookup-miss).
        assert fake.call_count == 1
        assert fake.last_id == "deadbeef" * 8


class TestHappyPath:
    def test_known_id_returns_ref(self):
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        fake = _FakeStandingService(receipts={_VALID_DIGEST: ref})
        client = StandingClient(verify_fn=fake)
        out = client.verify(_VALID_DIGEST)
        assert out is ref
        assert out.digest == _VALID_DIGEST
        assert out.kind == "grant_issued"
        assert fake.call_count == 1


class TestReceiptRefShape:
    """Standing-receipt crate vocabulary: digest is hex SHA-256, kind is
    the standing-side receipt kind string."""

    def test_ref_is_frozen(self):
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        with pytest.raises(Exception):
            ref.digest = "x"  # type: ignore[misc]

    def test_kinds_are_pass_through_strings(self):
        # AG does not interpret the standing-side kind enum; it carries
        # the string through verbatim. This documents that contract.
        for kind in (
            "grant_requested",
            "grant_issued",
            "grant_denied",
            "grant_activated",
            "grant_used",
            "grant_expired",
            "grant_revoked",
            "grant_abandoned",
            "policy_decision",
        ):
            ref = StandingReceiptRef(digest=_VALID_DIGEST, kind=kind)
            assert ref.kind == kind


# ---------------------------------------------------------------------------
# D0a: refusal-time GateReceipt emission.
# ---------------------------------------------------------------------------


class TestRefusalReceiptEmission:
    """Every standing-seam refusal path emits a GateReceipt via the injected
    sink and attaches the minted receipt_id to the raised exception."""

    def test_standing_required_emits_gate_receipt_with_closed_kind(
        self, tmp_path: Path
    ):
        sink = GateReceiptSystem(tmp_path)
        fake = _FakeStandingService()
        client = StandingClient(verify_fn=fake, receipt_sink=sink)

        with pytest.raises(StandingRequiredError) as ei:
            client.verify(None)

        # Receipt id was attached to the exception.
        rid = ei.value.receipt_id
        assert rid is not None and isinstance(rid, str)
        # The receipt is retrievable from the store by its id.
        receipt = sink.receipt_store.get_by_id(rid)
        assert receipt is not None
        assert receipt.gate == "standing_seam"
        assert receipt.verdict == "block"
        # Evidence bundle carries the closed-vocab refusal_kind.
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert bundle["refusal_kind"] == REFUSAL_KIND_STANDING_REQUIRED
        # Standing seam is the chain origin — parent list is empty.
        assert bundle["parent_receipt_ids"] == []
        # TEETH: downstream verifier was never consulted on a None id.
        assert fake.call_count == 0

    def test_dangling_standing_receipt_emits_gate_receipt(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        fake = _FakeStandingService(receipts={})
        client = StandingClient(verify_fn=fake, receipt_sink=sink)

        dangling = "deadbeef" * 8
        with pytest.raises(DanglingStandingReceiptError) as ei:
            client.verify(dangling)

        rid = ei.value.receipt_id
        assert rid is not None
        receipt = sink.receipt_store.get_by_id(rid)
        assert receipt is not None
        assert receipt.gate == "standing_seam"
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert (
            bundle["refusal_kind"] == REFUSAL_KIND_DANGLING_RECEIPT_REFERENCE
        )
        assert bundle["cited_standing_receipt_id"] == dangling
        # Origin — no parents.
        assert bundle["parent_receipt_ids"] == []

    def test_happy_path_emits_verified_standing_receipt(self, tmp_path: Path):
        """D0d-b: a successful verify() now mints a positive
        verified-standing GateReceipt (verdict="pass") and NO refusal
        receipt.

        Amended from D0a's ``test_happy_path_emits_no_receipt`` — D0d-b
        flipped the happy-path emission semantics across all three
        client seams (standing, wicket, LA) for chain completeness.
        The descriptive marker is ``evidence_bundle["verified_standing"]
        = True`` (internal-only — NOT promoted into the closed refusal
        vocabulary).
        """
        sink = GateReceiptSystem(tmp_path)
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        fake = _FakeStandingService(receipts={_VALID_DIGEST: ref})
        client = StandingClient(verify_fn=fake, receipt_sink=sink)

        out = client.verify(_VALID_DIGEST)
        assert out is ref
        # D0d-b: exactly one positive receipt minted.
        all_receipts = sink.receipt_store.all()
        assert len(all_receipts) == 1
        receipt = all_receipts[0]
        assert receipt.gate == "standing_seam"
        assert receipt.verdict == "pass"
        # The minted id is exposed on the side channel for the wicket
        # client to use as parent linkage on its own admission receipt.
        assert client._last_verified_receipt_id == receipt.receipt_id
        # Evidence bundle: descriptive admission marker, NOT a refusal kind.
        bundle = sink.evidence_for(receipt)
        assert bundle is not None
        assert bundle.get("verified_standing") is True
        assert bundle.get("cited_standing_receipt_id") == _VALID_DIGEST
        # No finding_id threaded in this call → parent list is empty.
        assert bundle["parent_receipt_ids"] == []
        # No refusal_kind on a positive receipt.
        assert "refusal_kind" not in bundle

    def test_happy_path_with_finding_id_cites_finding_as_parent(
        self, tmp_path: Path
    ):
        """D0d-b: when ``finding_id`` is plumbed, the verified-standing
        receipt cites it as parent so ``governor why`` walks
        standing-verification → NQ finding."""
        sink = GateReceiptSystem(tmp_path)
        ref = StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")
        fake = _FakeStandingService(receipts={_VALID_DIGEST: ref})
        client = StandingClient(verify_fn=fake, receipt_sink=sink)

        finding_id = "nq_fnd_test_drill_001"
        out = client.verify(_VALID_DIGEST, finding_id=finding_id)
        assert out is ref
        all_receipts = sink.receipt_store.all()
        assert len(all_receipts) == 1
        bundle = sink.evidence_for(all_receipts[0])
        assert bundle["parent_receipt_ids"] == [finding_id]

    def test_no_sink_preserves_back_compat(self):
        """Absent sink: refusal still raises, receipt_id is None."""
        fake = _FakeStandingService()
        client = StandingClient(verify_fn=fake)  # no sink

        with pytest.raises(StandingRequiredError) as ei:
            client.verify(None)
        assert ei.value.receipt_id is None
        assert ei.value.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED

    def test_emitted_receipt_id_is_content_addressed(self, tmp_path: Path):
        """Two refusals on the same input mint the same receipt_id.

        Content-addressing is a GateReceipt invariant; this just confirms
        the emission path does not accidentally seed entropy.
        """
        sink = GateReceiptSystem(tmp_path)
        fake = _FakeStandingService()
        client = StandingClient(verify_fn=fake, receipt_sink=sink)

        with pytest.raises(StandingRequiredError) as a:
            client.verify(None)
        with pytest.raises(StandingRequiredError) as b:
            client.verify(None)
        assert a.value.receipt_id == b.value.receipt_id
