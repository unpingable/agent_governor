# SPDX-License-Identifier: Apache-2.0
"""Tests for governor.doctrine — read-only consultation of continuity doctrine."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from governor import doctrine
from governor.doctrine import (
    DEFAULT_DOCTRINE_KINDS,
    ConsultationResult,
    DoctrineEntry,
    GATE_NAME,
    consult,
    emit_consult_receipt,
)


# =============================================================================
# Continuity availability fixture
# =============================================================================


# Continuity is an optional dep. Skip continuity-present tests if it isn't
# installed in this environment, but always run the unavailable-path tests.
try:
    import continuity  # noqa: F401
    from continuity.api.models import (
        ActorRef,
        CommitMemoryRequest,
        ObserveMemoryRequest,
    )
    from continuity.store.sqlite import SQLiteStore

    CONTINUITY_AVAILABLE = True
except ImportError:
    CONTINUITY_AVAILABLE = False


requires_continuity = pytest.mark.skipif(
    not CONTINUITY_AVAILABLE,
    reason="continuity package not installed in this environment",
)


@pytest.fixture
def seeded_store(tmp_path: Path) -> Path:
    """Create a continuity store with one constraint memory at a doctrine scope.

    Returns the db path. The seeded memory is committed (not just observed)
    so it shows up in the supersede-aware latest_memory query.
    """
    if not CONTINUITY_AVAILABLE:
        pytest.skip("continuity not installed")

    db = tmp_path / "continuity.db"
    store = SQLiteStore(db)
    store.initialize(scope_kind="explicit", scope_label="doctrine-test")

    actor = ActorRef(principal_id="test:fixture", auth_method="test")

    obs_req = ObserveMemoryRequest(
        scope="doctrine:test-rule",
        kind="constraint",
        basis="operator_assertion",
        content={"rule": "default to reduction over integration"},
        confidence=1.0,
        actor=actor,
    )
    obs_resp = store.observe_memory(obs_req)

    commit_req = CommitMemoryRequest(
        memory_id=obs_resp.memory.memory_id,
        reliance_class="advisory",
        note="seeded for doctrine test",
        approved_by=actor,
    )
    store.commit_memory(commit_req)

    return db


@pytest.fixture
def seeded_store_with_supersede(tmp_path: Path) -> Path:
    """Create a store with a superseded chain — old + new committed at same scope.

    latest_memory should return the chain head (the new one), not the old one.
    """
    if not CONTINUITY_AVAILABLE:
        pytest.skip("continuity not installed")

    db = tmp_path / "continuity.db"
    store = SQLiteStore(db)
    store.initialize(scope_kind="explicit", scope_label="doctrine-supersede-test")

    actor = ActorRef(principal_id="test:fixture", auth_method="test")

    # Old version
    old_obs = store.observe_memory(ObserveMemoryRequest(
        scope="doctrine:supersede-test",
        kind="constraint",
        basis="operator_assertion",
        content={"rule": "old version"},
        confidence=1.0,
        actor=actor,
    ))
    store.commit_memory(CommitMemoryRequest(
        memory_id=old_obs.memory.memory_id,
        reliance_class="advisory",
        approved_by=actor,
    ))

    # New version supersedes old
    new_obs = store.observe_memory(ObserveMemoryRequest(
        scope="doctrine:supersede-test",
        kind="constraint",
        basis="operator_assertion",
        content={"rule": "new version"},
        confidence=1.0,
        actor=actor,
    ))
    store.commit_memory(CommitMemoryRequest(
        memory_id=new_obs.memory.memory_id,
        reliance_class="advisory",
        supersedes=old_obs.memory.memory_id,
        approved_by=actor,
    ))

    return db


# =============================================================================
# Continuity-unavailable path
# =============================================================================


def test_consult_returns_unavailable_when_continuity_missing(monkeypatch):
    """When continuity isn't importable, consult() degrades cleanly."""
    monkeypatch.setattr(doctrine, "_try_import_continuity", lambda: None)

    result = consult(scope="doctrine:any")

    assert result.quality == "unavailable"
    assert result.scope == "doctrine:any"
    assert result.entries == []
    assert result.continuity_version is None
    assert result.error is not None
    assert "not installed" in result.error


def test_unavailable_result_still_makes_evidence_bundle(monkeypatch):
    """A degraded result still produces a valid evidence bundle."""
    monkeypatch.setattr(doctrine, "_try_import_continuity", lambda: None)

    result = consult(scope="doctrine:any")
    bundle = result.to_evidence_bundle()

    assert bundle["quality"] == "unavailable"
    assert bundle["scope"] == "doctrine:any"
    assert bundle["entry_count"] == 0
    assert "error" in bundle
    # Bundle must be JSON-serializable
    json.dumps(bundle)


# =============================================================================
# Continuity-present path
# =============================================================================


@requires_continuity
def test_consult_finds_seeded_doctrine(seeded_store: Path):
    """A seeded constraint memory is found by consult()."""
    result = consult(
        scope="doctrine:test-rule",
        kinds=("constraint",),
        explicit_db=seeded_store,
    )

    assert result.quality == "ok"
    assert result.scope == "doctrine:test-rule"
    assert result.kinds == ("constraint",)
    assert len(result.entries) == 1
    assert result.continuity_version is not None
    assert result.db_path == str(seeded_store)
    assert result.resolver_source == "explicit"
    assert result.scope_kind == "explicit"

    entry = result.entries[0]
    assert entry.kind == "constraint"
    assert entry.status == "committed"
    assert entry.reliance_class == "advisory"
    assert entry.content == {"rule": "default to reduction over integration"}
    assert entry.rely_ok is True
    assert isinstance(entry.rely_reason, str)


@requires_continuity
def test_consult_supersede_returns_chain_head_only(seeded_store_with_supersede: Path):
    """latest_memory should return the new version, not the superseded one.

    This is the critical test for the supersede convention. If we used
    query_memory instead of latest_memory, this test would fail because
    both old and new versions would be returned.
    """
    result = consult(
        scope="doctrine:supersede-test",
        kinds=("constraint",),
        explicit_db=seeded_store_with_supersede,
    )

    assert result.quality == "ok"
    assert len(result.entries) == 1, "should return only the chain head, not all versions"
    entry = result.entries[0]
    assert entry.content == {"rule": "new version"}, "should be the latest, not the superseded one"


@requires_continuity
def test_consult_empty_scope_returns_no_entries(seeded_store: Path):
    """Querying a scope with no matching memories returns empty entries, not an error."""
    result = consult(
        scope="doctrine:nothing-here",
        kinds=("constraint", "decision"),
        explicit_db=seeded_store,
    )

    assert result.quality == "ok"
    assert result.entries == []
    assert result.error is None


@requires_continuity
def test_consult_includes_store_metadata(seeded_store: Path):
    """The store_metadata block is captured for audit provenance."""
    result = consult(
        scope="doctrine:test-rule",
        kinds=("constraint",),
        explicit_db=seeded_store,
    )

    assert result.store_metadata is not None
    assert "store_id" in result.store_metadata
    assert result.store_metadata.get("scope_kind") == "explicit"


@requires_continuity
def test_consult_missing_db_returns_store_error(tmp_path: Path):
    """Pointing at a non-existent db file degrades to store_error, not a crash."""
    fake_db = tmp_path / "does-not-exist.db"

    result = consult(
        scope="doctrine:any",
        explicit_db=fake_db,
    )

    assert result.quality == "store_error"
    assert result.error is not None
    assert "not found" in result.error


# =============================================================================
# Receipt emission
# =============================================================================


@requires_continuity
def test_emit_consult_receipt_writes_observe_receipt(
    seeded_store: Path, tmp_path: Path
):
    """The receipt is shaped, content-addressed, and verdict=observe."""
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()

    result = consult(
        scope="doctrine:test-rule",
        kinds=("constraint",),
        explicit_db=seeded_store,
    )
    receipt = emit_consult_receipt(result, gov_dir)

    assert receipt.gate == GATE_NAME
    assert receipt.verdict == "observe"
    assert receipt.subject_hash
    assert receipt.evidence_hash
    assert receipt.policy_hash

    # Receipt and evidence should be on disk
    receipts_file = gov_dir / "receipts" / "gate_receipts.jsonl"
    assert receipts_file.exists()
    lines = receipts_file.read_text().strip().splitlines()
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["gate"] == GATE_NAME
    assert stored["verdict"] == "observe"


@requires_continuity
def test_emit_consult_receipt_is_content_addressed(
    seeded_store: Path, tmp_path: Path
):
    """Same query + same store state produces the same receipt_id."""
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()

    r1 = consult(
        scope="doctrine:test-rule",
        kinds=("constraint",),
        explicit_db=seeded_store,
    )
    r2 = consult(
        scope="doctrine:test-rule",
        kinds=("constraint",),
        explicit_db=seeded_store,
    )

    rcpt1 = emit_consult_receipt(r1, gov_dir)
    rcpt2 = emit_consult_receipt(r2, gov_dir)

    assert rcpt1.receipt_id == rcpt2.receipt_id, (
        "Same query + same store state must produce identical receipts"
    )


def test_unavailable_result_can_emit_receipt(monkeypatch, tmp_path: Path):
    """Even a degraded (continuity-missing) result emits a meaningful receipt."""
    monkeypatch.setattr(doctrine, "_try_import_continuity", lambda: None)
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()

    result = consult(scope="doctrine:any")
    receipt = emit_consult_receipt(result, gov_dir)

    assert receipt.gate == GATE_NAME
    assert receipt.verdict == "observe"
    receipts_file = gov_dir / "receipts" / "gate_receipts.jsonl"
    assert receipts_file.exists()


# =============================================================================
# Default kinds
# =============================================================================


def test_default_kinds_are_constraint_and_decision():
    """We deliberately use existing memory kinds, not a new doctrine kind."""
    assert DEFAULT_DOCTRINE_KINDS == ("constraint", "decision")
