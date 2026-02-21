# SPDX-License-Identifier: Apache-2.0
"""
Tests for Claim↔Receipt Correlation Layer.

Covers:
- Core data model (ClaimRecord, ReceiptLink, status derivation)
- Store persistence + idempotency
- Evidence gate wiring
- Backwards compatibility + replay safety
"""

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from governor.claim_correlation import (
    MAX_CLAIM_TEXT,
    VALID_LINK_ROLES,
    ClaimCorrelationStore,
    ClaimRecord,
    ClaimVerificationStatus,
    ClaimVerificationSummary,
    CorrelationContext,
    ReceiptLink,
    WindowResult,
    derive_status,
    parse_iso_timestamp,
    receipt_verdict,
    _compute_claim_key,
    _compute_claim_fingerprint,
    _normalize_text,
)


# =============================================================================
# Helpers
# =============================================================================


@pytest.fixture
def tmp_gov_dir(tmp_path):
    """Create a temporary governor directory."""
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()
    return gov_dir


@pytest.fixture
def store(tmp_gov_dir):
    """Create an empty ClaimCorrelationStore."""
    return ClaimCorrelationStore(tmp_gov_dir)


@dataclass
class FakeReceipt:
    """Minimal receipt for testing."""
    receipt_id: str
    verdict: str
    timestamp: str = "2026-02-21T00:00:00+00:00"
    gate: str = "evidence_gate"


class FakeReceiptStore:
    """Minimal receipt store for summarize() testing."""

    def __init__(self, receipts: list[FakeReceipt] | None = None):
        self._receipts = {r.receipt_id: r for r in (receipts or [])}

    def get_by_id(self, receipt_id: str) -> FakeReceipt | None:
        return self._receipts.get(receipt_id)


class FakeReceiptSystem:
    """Minimal receipt system for summarize() testing."""

    def __init__(self, receipts: list[FakeReceipt] | None = None):
        self.receipt_store = FakeReceiptStore(receipts)


# =============================================================================
# Core Model Tests
# =============================================================================


class TestClaimRecord:
    """Tests for ClaimRecord data model."""

    def test_creation_and_to_dict(self):
        record = ClaimRecord(
            claim_id="abc123",
            claim_key="key456",
            claim_kind="evidence_gate",
            claim_text="improves performance by 50%",
            claim_level="hard",
            claim_fingerprint="fp789",
            source_gate="evidence_gate",
            created_at="2026-02-21T00:00:00+00:00",
        )
        d = record.to_dict()
        assert d["claim_id"] == "abc123"
        assert d["claim_kind"] == "evidence_gate"
        assert d["claim_level"] == "hard"

    def test_round_trip(self):
        record = ClaimRecord(
            claim_id="abc123",
            claim_key="key456",
            claim_kind="evidence_gate",
            claim_text="test claim",
            claim_level="soft",
            claim_fingerprint="fp789",
            run_id="run1",
            task_id="task1",
            step_id="step1",
            source_gate="evidence_gate",
            created_at="2026-02-21T00:00:00+00:00",
        )
        restored = ClaimRecord.from_dict(record.to_dict())
        assert restored == record


class TestReceiptLink:
    """Tests for ReceiptLink data model."""

    def test_creation_and_serialization(self):
        link = ReceiptLink(
            link_id="link1",
            claim_id="claim1",
            receipt_id="receipt1",
            role="supports",
            created_at="2026-02-21T00:00:00+00:00",
        )
        d = link.to_dict()
        assert d["role"] == "supports"
        restored = ReceiptLink.from_dict(d)
        assert restored == link


class TestClaimVerificationStatus:
    """Tests for the verification status enum."""

    def test_enum_values(self):
        assert ClaimVerificationStatus.UNVERIFIED.value == "unverified"
        assert ClaimVerificationStatus.PARTIAL.value == "partial"
        assert ClaimVerificationStatus.VERIFIED.value == "verified"
        assert ClaimVerificationStatus.CONTRADICTED.value == "contradicted"

    def test_from_string(self):
        assert ClaimVerificationStatus("unverified") == ClaimVerificationStatus.UNVERIFIED


class TestReceiptVerdict:
    """Tests for the centralized verdict helper."""

    def test_verdict_from_object(self):
        r = FakeReceipt(receipt_id="r1", verdict="pass")
        assert receipt_verdict(r) == "pass"

    def test_verdict_from_dict(self):
        assert receipt_verdict({"verdict": "block"}) == "block"

    def test_verdict_unknown(self):
        assert receipt_verdict({"verdict": "something_else"}) == "unknown"

    def test_verdict_case_insensitive(self):
        assert receipt_verdict({"verdict": "PASS"}) == "pass"
        assert receipt_verdict({"verdict": "Block"}) == "block"


# =============================================================================
# Derivation Logic Tests
# =============================================================================


class TestDeriveStatus:
    """Tests for the pure derive_status function."""

    def test_no_links_unverified(self):
        status, unresolved = derive_status([], {})
        assert status == ClaimVerificationStatus.UNVERIFIED
        assert unresolved == 0

    def test_supporting_pass_verified(self):
        links = [ReceiptLink("l1", "c1", "r1", "supports")]
        receipts = {"r1": FakeReceipt("r1", "pass")}
        status, unresolved = derive_status(links, receipts)
        assert status == ClaimVerificationStatus.VERIFIED
        assert unresolved == 0

    def test_contradicting_role(self):
        links = [ReceiptLink("l1", "c1", "r1", "contradicts")]
        receipts = {"r1": FakeReceipt("r1", "pass")}
        status, _ = derive_status(links, receipts)
        assert status == ClaimVerificationStatus.CONTRADICTED

    def test_block_verdict_contradicts(self):
        links = [ReceiptLink("l1", "c1", "r1", "supports")]
        receipts = {"r1": FakeReceipt("r1", "block")}
        status, _ = derive_status(links, receipts)
        assert status == ClaimVerificationStatus.CONTRADICTED

    def test_warn_only_partial(self):
        links = [ReceiptLink("l1", "c1", "r1", "supports")]
        receipts = {"r1": FakeReceipt("r1", "warn")}
        status, _ = derive_status(links, receipts)
        assert status == ClaimVerificationStatus.PARTIAL

    def test_contradiction_trumps_support(self):
        links = [
            ReceiptLink("l1", "c1", "r1", "supports"),
            ReceiptLink("l2", "c1", "r2", "contradicts"),
        ]
        receipts = {
            "r1": FakeReceipt("r1", "pass"),
            "r2": FakeReceipt("r2", "pass"),
        }
        status, _ = derive_status(links, receipts)
        assert status == ClaimVerificationStatus.CONTRADICTED

    def test_support_chain_not_ok_partial(self):
        links = [ReceiptLink("l1", "c1", "r1", "supports")]
        receipts = {"r1": FakeReceipt("r1", "pass")}
        status, _ = derive_status(links, receipts, chain_ok=False)
        assert status == ClaimVerificationStatus.PARTIAL

    def test_unresolved_receipts_counted(self):
        links = [
            ReceiptLink("l1", "c1", "r1", "supports"),
            ReceiptLink("l2", "c1", "r2", "supports"),
        ]
        receipts = {"r1": FakeReceipt("r1", "pass"), "r2": None}
        status, unresolved = derive_status(links, receipts)
        assert status == ClaimVerificationStatus.VERIFIED  # r1 passes
        assert unresolved == 1

    def test_all_unresolved_partial(self):
        links = [ReceiptLink("l1", "c1", "r1", "supports")]
        receipts = {"r1": None}
        status, unresolved = derive_status(links, receipts)
        assert status == ClaimVerificationStatus.PARTIAL
        assert unresolved == 1

    def test_neutral_only_partial(self):
        links = [ReceiptLink("l1", "c1", "r1", "neutral")]
        receipts = {"r1": FakeReceipt("r1", "pass")}
        status, _ = derive_status(links, receipts)
        assert status == ClaimVerificationStatus.PARTIAL


# =============================================================================
# Store Tests
# =============================================================================


class TestClaimCorrelationStore:
    """Tests for the JSONL-backed store."""

    def test_mint_claim_returns_record(self, store):
        record = store.mint_claim("evidence_gate", "test claim", "hard")
        assert record.claim_id
        assert record.claim_kind == "evidence_gate"
        assert record.claim_level == "hard"
        assert record.claim_key

    def test_mint_claim_idempotent(self, store):
        r1 = store.mint_claim("evidence_gate", "test claim", "hard", run_id="run1")
        r2 = store.mint_claim("evidence_gate", "test claim", "hard", run_id="run1")
        assert r1.claim_id == r2.claim_id
        assert len(store._claims) == 1

    def test_mint_claim_different_run_different_claim(self, store):
        r1 = store.mint_claim("evidence_gate", "test claim", "hard", run_id="run1")
        r2 = store.mint_claim("evidence_gate", "test claim", "hard", run_id="run2")
        assert r1.claim_id != r2.claim_id

    def test_mint_claim_truncates_text(self, store):
        long_text = "x" * 1000
        record = store.mint_claim("evidence_gate", long_text, "soft")
        assert len(record.claim_text) == MAX_CLAIM_TEXT

    def test_link_receipt_creates_junction(self, store):
        claim = store.mint_claim("evidence_gate", "test", "hard")
        link = store.link_receipt(claim.claim_id, "receipt1", "supports")
        assert link.claim_id == claim.claim_id
        assert link.receipt_id == "receipt1"
        assert link.role == "supports"

    def test_link_receipt_idempotent(self, store):
        claim = store.mint_claim("evidence_gate", "test", "hard")
        l1 = store.link_receipt(claim.claim_id, "r1", "supports")
        l2 = store.link_receipt(claim.claim_id, "r1", "supports")
        assert l1.link_id == l2.link_id
        assert len(store._links) == 1

    def test_link_receipt_different_role_not_deduped(self, store):
        claim = store.mint_claim("evidence_gate", "test", "hard")
        l1 = store.link_receipt(claim.claim_id, "r1", "supports")
        l2 = store.link_receipt(claim.claim_id, "r1", "contradicts")
        assert l1.link_id != l2.link_id
        assert len(store._links) == 2

    def test_link_receipt_invalid_role_raises(self, store):
        claim = store.mint_claim("evidence_gate", "test", "hard")
        with pytest.raises(ValueError, match="Invalid role"):
            store.link_receipt(claim.claim_id, "r1", "invalid_role")

    def test_get_claim_by_id(self, store):
        claim = store.mint_claim("evidence_gate", "test", "hard")
        found = store.get_claim(claim.claim_id)
        assert found is not None
        assert found.claim_id == claim.claim_id

    def test_get_claim_not_found(self, store):
        assert store.get_claim("nonexistent") is None

    def test_get_links_oldest_first(self, store):
        claim = store.mint_claim("evidence_gate", "test", "hard")
        store.link_receipt(claim.claim_id, "r1", "supports")
        store.link_receipt(claim.claim_id, "r2", "supports")
        links = store.get_links(claim.claim_id)
        assert len(links) == 2
        assert links[0].created_at <= links[1].created_at

    def test_get_claims_for_receipt(self, store):
        c1 = store.mint_claim("evidence_gate", "claim one", "hard")
        c2 = store.mint_claim("evidence_gate", "claim two", "soft")
        store.link_receipt(c1.claim_id, "r1", "supports")
        store.link_receipt(c2.claim_id, "r1", "supports")
        claims = store.get_claims_for_receipt("r1")
        ids = {c.claim_id for c in claims}
        assert c1.claim_id in ids
        assert c2.claim_id in ids

    def test_list_claims_newest_first(self, store):
        store.mint_claim("evidence_gate", "old", "hard")
        store.mint_claim("evidence_gate", "new", "soft")
        claims = store.list_claims()
        assert len(claims) == 2
        assert claims[0].created_at >= claims[1].created_at

    def test_list_claims_filter_by_run_id(self, store):
        store.mint_claim("evidence_gate", "a", "hard", run_id="run1")
        store.mint_claim("evidence_gate", "b", "hard", run_id="run2")
        claims = store.list_claims(run_id="run1")
        assert len(claims) == 1
        assert claims[0].run_id == "run1"

    def test_list_claims_filter_by_since(self, store):
        c1 = store.mint_claim("evidence_gate", "old", "hard")
        # Mint another — will have a slightly later timestamp
        c2 = store.mint_claim("evidence_gate", "new", "soft")
        # Filter since the first claim's timestamp
        claims = store.list_claims(since=c1.created_at)
        assert len(claims) >= 1

    def test_summarize_returns_summary(self, store):
        claim = store.mint_claim("evidence_gate", "test", "hard")
        r = FakeReceipt("r1", "pass")
        store.link_receipt(claim.claim_id, "r1", "supports")
        system = FakeReceiptSystem([r])
        summary = store.summarize(claim.claim_id, system)
        assert summary is not None
        assert summary.status == ClaimVerificationStatus.VERIFIED
        assert "r1" in summary.supporting_receipt_ids

    def test_summarize_unknown_claim_returns_none(self, store):
        assert store.summarize("nonexistent") is None

    def test_window_returns_time_filtered(self, store):
        c = store.mint_claim("evidence_gate", "test", "hard")
        result = store.window(since="2020-01-01T00:00:00+00:00")
        assert result.count >= 1
        assert result.schema == "claims_window.v1"

    def test_stats_empty_store(self, store):
        s = store.stats()
        assert s["total"] == 0
        assert s["total_links"] == 0
        assert s["newest_at"] == ""

    def test_stats_with_claims(self, store):
        store.mint_claim("evidence_gate", "test", "hard")
        store.mint_claim("evidence_gate", "test2", "soft")
        s = store.stats()
        assert s["total"] == 2
        assert s["counts_by_level"]["hard"] == 1
        assert s["counts_by_level"]["soft"] == 1

    def test_persistence_survives_reload(self, tmp_gov_dir):
        store = ClaimCorrelationStore(tmp_gov_dir)
        claim = store.mint_claim("evidence_gate", "persistent", "hard")
        store.link_receipt(claim.claim_id, "r1", "supports")

        # Reload from disk
        store2 = ClaimCorrelationStore.load(tmp_gov_dir)
        assert store2.get_claim(claim.claim_id) is not None
        links = store2.get_links(claim.claim_id)
        assert len(links) == 1
        assert links[0].receipt_id == "r1"

    def test_resilient_load_skips_corrupt_lines(self, tmp_gov_dir, caplog):
        claims_dir = tmp_gov_dir / "claims"
        claims_dir.mkdir(parents=True, exist_ok=True)
        (claims_dir / "claims.jsonl").write_text(
            '{"claim_id":"ok","claim_key":"k","claim_kind":"x","claim_text":"t","claim_level":"h","claim_fingerprint":"f"}\n'
            'THIS IS CORRUPT\n'
            '{"claim_id":"ok2","claim_key":"k2","claim_kind":"x","claim_text":"t2","claim_level":"s","claim_fingerprint":"f2"}\n'
        )
        with caplog.at_level(logging.WARNING):
            store = ClaimCorrelationStore.load(tmp_gov_dir)
        assert len(store._claims) == 2
        assert "skipping corrupt record" in caplog.text

    def test_empty_store_returns_empty_lists(self, store):
        assert store.list_claims() == []
        assert store.get_links("nonexistent") == []
        assert store.get_claims_for_receipt("nonexistent") == []


# =============================================================================
# Evidence Gate Wiring Tests
# =============================================================================


class TestEvidenceGateWiring:
    """Tests for evidence_gate.check() integration with correlation."""

    def test_check_with_correlation_ctx_mints_claims(self, tmp_gov_dir):
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig

        store = ClaimCorrelationStore(tmp_gov_dir)
        ctx = CorrelationContext(claim_store=store, run_id="run1")

        gate = EvidenceGate(config=EvidenceGateConfig(strict=False))
        # Text with a HARD claim pattern
        result = gate.check(
            task="test",
            context=".",
            output="This guarantees thread safety and is faster than the old approach",
            correlation_ctx=ctx,
        )
        # Should have minted claims
        claims = store.list_claims()
        assert len(claims) >= 1
        # At least one should be HARD
        hard_claims = [c for c in claims if c.claim_level == "hard"]
        assert len(hard_claims) >= 1

    def test_check_with_correlation_ctx_links_receipt(self, tmp_gov_dir):
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig
        from governor.gate_receipt import GateReceiptSystem

        receipt_system = GateReceiptSystem(tmp_gov_dir)
        store = ClaimCorrelationStore(tmp_gov_dir)
        ctx = CorrelationContext(claim_store=store, run_id="run1")

        gate = EvidenceGate(
            config=EvidenceGateConfig(strict=False),
            receipt_system=receipt_system,
        )
        result = gate.check(
            task="test",
            context=".",
            output="This guarantees safety",
            correlation_ctx=ctx,
        )
        claims = store.list_claims()
        if claims:
            links = store.get_links(claims[0].claim_id)
            assert len(links) >= 1

    def test_check_without_correlation_ctx_works(self, tmp_gov_dir):
        """Backwards compat: check() with no correlation_ctx doesn't crash."""
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig

        gate = EvidenceGate(config=EvidenceGateConfig(strict=False))
        result = gate.check(
            task="test",
            context=".",
            output="This guarantees safety",
        )
        assert result.status is not None

    def test_contradiction_claim_gets_contradicts_role(self, tmp_gov_dir):
        from governor.evidence_gate import (
            EvidenceGate,
            EvidenceGateConfig,
            EvidenceGateClaim,
            ClaimLevel,
        )
        from governor.gate_receipt import GateReceiptSystem

        receipt_system = GateReceiptSystem(tmp_gov_dir)
        store = ClaimCorrelationStore(tmp_gov_dir)
        ctx = CorrelationContext(claim_store=store, run_id="run1")

        # First, create a claim with a prior
        prior = EvidenceGateClaim(
            id="prior1",
            text="is slower than the old approach",
            level=ClaimLevel.HARD,
        )

        gate = EvidenceGate(
            config=EvidenceGateConfig(strict=False),
            receipt_system=receipt_system,
        )
        result = gate.check(
            task="test",
            context=".",
            output="This is faster than the old approach",
            prior_claims=[prior],
            correlation_ctx=ctx,
        )
        claims = store.list_claims()
        # Check if any claim got a contradicts link
        for claim in claims:
            links = store.get_links(claim.claim_id)
            roles = [l.role for l in links]
            # At least look for the claim that has conflicts_with
            for eg_claim in result.claims:
                if eg_claim.conflicts_with:
                    # This claim should have a contradicts link in the store
                    matched = [c for c in claims if c.claim_text.lower().strip() == eg_claim.text.lower().strip() or eg_claim.text.lower() in c.claim_text.lower()]
                    if matched:
                        links = store.get_links(matched[0].claim_id)
                        roles = [l.role for l in links]
                        assert "contradicts" in roles

    def test_fail_open_on_store_error(self, tmp_gov_dir):
        """If the store blows up, check() still returns a result."""
        from governor.evidence_gate import EvidenceGate, EvidenceGateConfig

        store = ClaimCorrelationStore(tmp_gov_dir)
        # Sabotage the store
        store.mint_claim = MagicMock(side_effect=RuntimeError("boom"))

        ctx = CorrelationContext(claim_store=store, run_id="run1")

        gate = EvidenceGate(config=EvidenceGateConfig(strict=False))
        result = gate.check(
            task="test",
            context=".",
            output="This guarantees safety",
            correlation_ctx=ctx,
        )
        # Should not crash — fail-open
        assert result.status is not None


# =============================================================================
# Backwards Compat + Replay Tests
# =============================================================================


class TestBackwardsCompat:
    """Tests for backwards compatibility and replay safety."""

    def test_claims_list_empty_store(self, store):
        assert store.list_claims() == []

    def test_claims_for_receipt_unknown_receipt(self, store):
        assert store.get_claims_for_receipt("unknown_receipt") == []

    def test_same_gate_pass_twice_no_duplicate(self, store):
        """Same gate call with same text → no duplicate claim."""
        r1 = store.mint_claim("evidence_gate", "guarantees safety", "hard", run_id="run1")
        r2 = store.mint_claim("evidence_gate", "guarantees safety", "hard", run_id="run1")
        assert r1.claim_id == r2.claim_id
        assert store.stats()["total"] == 1

    def test_reload_stable_counts(self, tmp_gov_dir):
        """After daemon restart + reload, claim counts are stable."""
        store = ClaimCorrelationStore(tmp_gov_dir)
        store.mint_claim("evidence_gate", "a", "hard", run_id="r1")
        store.mint_claim("evidence_gate", "b", "soft", run_id="r1")
        store.link_receipt(
            store.list_claims()[0].claim_id, "receipt1", "supports"
        )

        store2 = ClaimCorrelationStore.load(tmp_gov_dir)
        assert store2.stats()["total"] == 2
        assert store2.stats()["total_links"] == 1

    def test_legacy_receipts_without_claims_queryable(self, store):
        """Legacy receipts (no claims linked) still return empty from reverse lookup."""
        result = store.get_claims_for_receipt("old_legacy_receipt")
        assert result == []


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions:
    """Tests for helper/utility functions."""

    def test_normalize_text(self):
        assert _normalize_text("  Hello   World  ") == "hello world"
        assert _normalize_text("UPPERCASE") == "uppercase"

    def test_compute_claim_key_deterministic(self):
        k1 = _compute_claim_key("gate", "run1", "text", "hard")
        k2 = _compute_claim_key("gate", "run1", "text", "hard")
        assert k1 == k2

    def test_compute_claim_key_varies_by_field(self):
        k1 = _compute_claim_key("gate", "run1", "text", "hard")
        k2 = _compute_claim_key("gate", "run2", "text", "hard")
        assert k1 != k2

    def test_compute_claim_fingerprint(self):
        f1 = _compute_claim_fingerprint("hello world")
        f2 = _compute_claim_fingerprint("hello world")
        assert f1 == f2
        f3 = _compute_claim_fingerprint("different text")
        assert f1 != f3

    def test_parse_iso_timestamp_utc(self):
        dt = parse_iso_timestamp("2026-02-21T12:00:00+00:00")
        assert dt.year == 2026
        assert dt.month == 2

    def test_parse_iso_timestamp_naive_becomes_utc(self):
        dt = parse_iso_timestamp("2026-02-21T12:00:00")
        assert dt.tzinfo is not None

    def test_summary_to_dict(self):
        summary = ClaimVerificationSummary(
            claim_id="c1",
            status=ClaimVerificationStatus.VERIFIED,
        )
        d = summary.to_dict()
        assert d["status"] == "verified"
        assert d["schema"] == "claim_verification_summary.v1"

    def test_window_result_to_dict(self):
        wr = WindowResult(count=0, counts_by_status={})
        d = wr.to_dict()
        assert d["schema"] == "claims_window.v1"
        assert d["count"] == 0
