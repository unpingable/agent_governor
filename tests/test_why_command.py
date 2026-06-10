# SPDX-License-Identifier: Apache-2.0
"""Tests for S5 — `governor why <receipt-id>`.

Slice contract (per
``working/campaign-standing-before-spendability.md`` §S5):

  * Join ReceiptStore → EvidenceStore on the existing GateReceiptSystem
    (no new top-level receipt store).
  * Closed refusal vocabulary only (imported from
    linear_accountant_client.CLOSED_REFUSAL_KINDS).
  * Bypass receipts render as BYPASS, not REFUSED, and include a pointer
    to working/post-mvp-debt-ba3-hardshort-to-la.md.
  * Chain walked back through evidence_bundle.parent_receipt_ids.
  * Absence is rendered, not erred:
      - unknown receipt id → "receipt id not found", exit 1, no traceback
      - missing evidence blob → "evidence blob missing for hash sha256:..."
      - dangling parent ref → "no receipt found for cited parent ..."
      - stale refusal kind → "stale vocabulary: <kind>", warning marker

Tests use ``click.testing.CliRunner`` to mirror the existing convention in
``tests/test_cli_receipts_v1.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from governor.cli import cli
from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import (
    BYPASS_BA3_FOR_MVP,
    REFUSAL_ADMISSION_DENIED,
    REFUSAL_CAPACITY_REFUSED,
    REFUSAL_STANDING_REQUIRED,
)
from governor.why import BA3_DEBT_POINTER, render_text, walk_chain


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def gov_dir(tmp_path: Path) -> Path:
    """Initialize a minimal .governor/ tree (mirrors test_cli_receipts_v1)."""
    gd = tmp_path / ".governor"
    gd.mkdir()
    (gd / "facts").mkdir()
    (gd / "facts" / "receipts").mkdir()
    (gd / "facts" / "index.json").write_text("[]")
    (gd / "decisions").mkdir()
    (gd / "decisions" / "index.json").write_text("[]")
    (gd / "proposals.json").write_text("{}")
    (gd / "receipts").mkdir()
    return gd


@pytest.fixture
def system(gov_dir: Path) -> GateReceiptSystem:
    return GateReceiptSystem(gov_dir)


def _emit(
    system: GateReceiptSystem,
    *,
    gate: str,
    verdict: str,
    bundle: dict[str, Any],
    subject_bytes: bytes = b"workload-subject",
    timestamp: str | None = None,
):
    """Helper: emit a receipt via the GateReceiptSystem under test."""
    return system.emit(
        gate=gate,
        verdict=verdict,
        subject_kind="text",
        subject_bytes=subject_bytes,
        evidence_bundle=bundle,
        gate_config={"profile": "s5_test"},
        timestamp=timestamp or "2026-06-09T12:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# Operator-required negative tests (verbatim).
# ---------------------------------------------------------------------------


class TestNegativePathsRequired:
    """Operator-mandated negative tests for S5."""

    def test_unknown_receipt_id_renders_cleanly(self, runner, gov_dir, tmp_path):
        """Unknown id → render absence cleanly, exit nonzero, no traceback."""
        result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", "definitely-not-a-real-receipt-id"]
        )
        assert result.exit_code != 0, (
            "absence must exit nonzero per S5 spec"
        )
        assert "receipt id not found" in result.output
        # No traceback marker should leak into output.
        assert "Traceback" not in result.output
        # Absence is rendered, not raised — the exception attr is None.
        assert result.exception is None or isinstance(result.exception, SystemExit)

    def test_missing_evidence_blob_does_not_crash(
        self, runner, gov_dir, tmp_path, system
    ):
        """Receipt cites an evidence_hash but blob is absent → render the gap."""
        # Emit a receipt normally so the receipt row exists.
        r = _emit(system, gate="happy", verdict="pass", bundle={"foo": "bar"})
        # Now nuke the evidence blob to simulate the gap.
        blob_dir = gov_dir / "evidence" / r.evidence_hash[:2]
        for f in blob_dir.iterdir():
            f.unlink()

        result = runner.invoke(cli, ["-r", str(tmp_path), "why", r.receipt_id])
        assert result.exit_code == 0  # receipt was found; only the blob is gone
        assert "Traceback" not in result.output
        assert "evidence blob missing for hash sha256:" in result.output
        assert r.evidence_hash in result.output

    def test_malformed_refusal_kind_renders_as_stale_vocabulary(
        self, runner, gov_dir, tmp_path, system
    ):
        """Refusal kind not in closed set → "stale vocabulary: <kind>"."""
        bundle = {"refusal_kind": "this_is_not_a_valid_kind"}
        r = _emit(system, gate="weird_seam", verdict="block", bundle=bundle)

        result = runner.invoke(cli, ["-r", str(tmp_path), "why", r.receipt_id])
        assert result.exit_code == 0
        assert "Traceback" not in result.output
        assert "stale vocabulary" in result.output
        assert "this_is_not_a_valid_kind" in result.output
        # The header carries the STALE-VOCAB prefix, NOT REFUSED/BYPASS.
        assert "STALE-VOCAB" in result.output
        assert "REFUSED" not in result.output

    def test_stale_deprecated_vocabulary_treated_same_as_malformed(
        self, runner, gov_dir, tmp_path, system
    ):
        """Simulate a receipt whose closed-set was older than the current one.

        Per the operator: "you may simulate this by writing a fixture receipt
        whose kind is a deprecated name like 'wicket_blocked' or similar."
        """
        bundle = {"refusal_kind": "wicket_blocked"}  # deprecated/never-ratified
        r = _emit(system, gate="legacy_wicket_seam", verdict="block", bundle=bundle)

        result = runner.invoke(cli, ["-r", str(tmp_path), "why", r.receipt_id])
        assert result.exit_code == 0
        assert "Traceback" not in result.output
        assert "stale vocabulary" in result.output
        assert "wicket_blocked" in result.output
        # No auto-correction.
        for kind in ("standing_required", "admission_denied", "capacity_refused"):
            assert kind not in result.output, (
                "stale vocabulary must not be silently rewritten"
            )


# ---------------------------------------------------------------------------
# Refusal vs bypass — visible distinctness invariant.
# ---------------------------------------------------------------------------


class TestRefusalVsBypassDistinctness:
    """Refusal and bypass MUST render visibly differently (S5 spec rule 3)."""

    def test_refusal_renders_with_REFUSED_prefix(
        self, runner, gov_dir, tmp_path, system
    ):
        bundle = {"refusal_kind": REFUSAL_STANDING_REQUIRED, "reason": "no SR"}
        r = _emit(system, gate="standing_seam", verdict="block", bundle=bundle)

        result = runner.invoke(cli, ["-r", str(tmp_path), "why", r.receipt_id])
        assert result.exit_code == 0
        assert "REFUSED" in result.output
        assert REFUSAL_STANDING_REQUIRED in result.output
        assert "BYPASS" not in result.output
        # Refusal receipts must NOT carry the BA3 debt pointer.
        assert BA3_DEBT_POINTER not in result.output

    def test_bypass_renders_with_BYPASS_prefix_and_debt_pointer(
        self, runner, gov_dir, tmp_path, system
    ):
        bundle = {
            "refusal_kind": BYPASS_BA3_FOR_MVP,
            "suppressed_surface": "RunBudgetLedger",
        }
        r = _emit(system, gate="run_budget_ledger", verdict="observe", bundle=bundle)

        result = runner.invoke(cli, ["-r", str(tmp_path), "why", r.receipt_id])
        assert result.exit_code == 0
        # Visible distinctness: BYPASS prefix, NOT REFUSED.
        assert "BYPASS" in result.output
        assert BYPASS_BA3_FOR_MVP in result.output
        assert "REFUSED" not in result.output
        # Debt pointer present per S5 spec rule 3.
        assert BA3_DEBT_POINTER in result.output

    def test_bypass_kind_is_not_in_closed_refusal_set(self):
        """Cross-check: the bypass kind is NOT a refusal kind in the closed set.

        This is the structural reason BYPASS must render differently from
        REFUSED — they are two different vocabularies that share the
        ``refusal_kind`` evidence-bundle key.
        """
        from governor.linear_accountant_client import CLOSED_REFUSAL_KINDS

        assert BYPASS_BA3_FOR_MVP not in CLOSED_REFUSAL_KINDS


# ---------------------------------------------------------------------------
# Happy path — non-refusal receipt walks cleanly.
# ---------------------------------------------------------------------------


class TestHappyPath:
    def test_happy_path_receipt_renders_OK_prefix(
        self, runner, gov_dir, tmp_path, system
    ):
        bundle = {"workload": "wal-bloat", "outcome": "proposal_packet_landed"}
        r = _emit(system, gate="effect_emit", verdict="pass", bundle=bundle)

        result = runner.invoke(cli, ["-r", str(tmp_path), "why", r.receipt_id])
        assert result.exit_code == 0
        # No refusal/bypass framing on a happy receipt.
        assert "REFUSED" not in result.output
        assert "BYPASS" not in result.output
        assert "STALE-VOCAB" not in result.output
        # Happy receipts render with OK prefix.
        assert "OK" in result.output
        assert "verdict=pass" in result.output


# ---------------------------------------------------------------------------
# Chain walking.
# ---------------------------------------------------------------------------


class TestChainWalk:
    def test_chain_walks_back_through_parent_receipt_ids(
        self, runner, gov_dir, tmp_path, system
    ):
        # Build a 3-step chain: standing → admission → capacity.
        standing = _emit(
            system,
            gate="standing_seam",
            verdict="pass",
            bundle={"actor": "agent-1", "scope": "wal-bloat"},
            subject_bytes=b"standing-subject",
        )
        admission = _emit(
            system,
            gate="wicket_seam",
            verdict="pass",
            bundle={
                "parent_receipt_ids": [standing.receipt_id],
                "admission_kind": "granted",
            },
            subject_bytes=b"admission-subject",
        )
        capacity = _emit(
            system,
            gate="la_seam",
            verdict="pass",
            bundle={
                "parent_receipt_ids": [admission.receipt_id],
                "granted_capacity": 1,
            },
            subject_bytes=b"capacity-subject",
        )

        result = runner.invoke(cli, ["-r", str(tmp_path), "why", capacity.receipt_id])
        assert result.exit_code == 0
        # All three receipts surface in the output.
        for r in (capacity, admission, standing):
            assert r.receipt_id[:12] in result.output
        # Order: root first, then walked back.
        idx_cap = result.output.index(capacity.receipt_id[:12])
        idx_adm = result.output.index(admission.receipt_id[:12])
        idx_std = result.output.index(standing.receipt_id[:12])
        assert idx_cap < idx_adm < idx_std

    def test_chain_terminates_cleanly_on_dangling_parent(
        self, runner, gov_dir, tmp_path, system
    ):
        """Parent id cited but absent → render the gap, no traceback."""
        bundle = {
            "parent_receipt_ids": [
                "dangling-id-that-was-never-minted-0123456789abcdef"
            ],
            "refusal_kind": REFUSAL_ADMISSION_DENIED,
        }
        r = _emit(system, gate="wicket_seam", verdict="block", bundle=bundle)

        result = runner.invoke(cli, ["-r", str(tmp_path), "why", r.receipt_id])
        assert result.exit_code == 0
        assert "Traceback" not in result.output
        assert "no receipt found for cited parent" in result.output
        assert "dangling-id-that-was-never-minted" in result.output

    def test_cycle_detection_terminates_walk(
        self, runner, gov_dir, tmp_path, system
    ):
        """A cycle in parent refs must terminate the walk, not loop forever."""
        # Emit two receipts and then fabricate a cycle by emitting a third
        # whose evidence cites the first via a self-loop. Because gate
        # receipts are content-addressed, we have to be careful — the
        # cleanest cycle is a receipt whose bundle cites itself.
        r = _emit(
            system,
            gate="self_loop_seam",
            verdict="pass",
            bundle={"parent_receipt_ids": []},
        )
        # Re-emit with the same receipt as a self-parent (the resulting
        # content hash differs from r.receipt_id, so build a 2-node cycle
        # via a separate path: write a receipt that cites itself by
        # patching the JSONL directly.
        cycle_bundle = {"parent_receipt_ids": [r.receipt_id], "loop": "true"}
        r2 = _emit(system, gate="cycle_seam", verdict="pass", bundle=cycle_bundle)

        # Update r's bundle on disk so it cites r2 → 2-cycle.
        new_bundle = {"parent_receipt_ids": [r2.receipt_id], "loop_back": True}
        # Re-put the blob at r.evidence_hash by writing the canonical bytes
        # — but r.evidence_hash binds the old content. Instead, monkey-patch
        # the blob path to contain a bundle naming r2 as a parent.
        from governor.gate_receipt import canonical_json
        blob_path = (
            gov_dir / "evidence" / r.evidence_hash[:2] / f"{r.evidence_hash}.json"
        )
        blob_path.write_bytes(canonical_json(new_bundle))

        # Now r → r2 → r → cycle.
        result = runner.invoke(cli, ["-r", str(tmp_path), "why", r.receipt_id])
        assert result.exit_code == 0
        assert "Traceback" not in result.output
        assert "CYCLE" in result.output or "cycle detected" in result.output


# ---------------------------------------------------------------------------
# JSON output.
# ---------------------------------------------------------------------------


class TestJsonOutput:
    def test_json_flag_emits_structured_output(
        self, runner, gov_dir, tmp_path, system
    ):
        bundle = {"refusal_kind": REFUSAL_CAPACITY_REFUSED, "reason": "no stock"}
        r = _emit(system, gate="la_seam", verdict="block", bundle=bundle)

        result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", r.receipt_id, "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["requested_id"] == r.receipt_id
        assert data["found"] is True
        assert len(data["links"]) == 1
        link = data["links"][0]
        assert link["status"] == "resolved"
        assert link["kind"] == "refusal"
        assert link["refusal_kind"] == REFUSAL_CAPACITY_REFUSED
        assert link["receipt"]["receipt_id"] == r.receipt_id
        assert link["evidence"]["reason"] == "no stock"

    def test_json_unknown_id_still_emits_structured_output(
        self, runner, gov_dir, tmp_path
    ):
        result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", "ghost-id", "--json"]
        )
        # Absence still exits nonzero, but JSON must be parseable.
        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["requested_id"] == "ghost-id"
        assert data["found"] is False
        assert data["links"] == []

    def test_json_bypass_includes_debt_pointer(
        self, runner, gov_dir, tmp_path, system
    ):
        bundle = {
            "refusal_kind": BYPASS_BA3_FOR_MVP,
            "suppressed_surface": "ExecutionBudget",
        }
        r = _emit(system, gate="execution_budget", verdict="observe", bundle=bundle)

        result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", r.receipt_id, "--json"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        link = data["links"][0]
        assert link["kind"] == "bypass"
        assert link["debt_pointer"] == BA3_DEBT_POINTER


# ---------------------------------------------------------------------------
# Pure-function tests on the join module (no CLI).
# ---------------------------------------------------------------------------


class TestWalkChainDirect:
    """walk_chain() returns structured WhyResult; never raises on absence."""

    def test_unknown_id_returns_not_found_result(self, system: GateReceiptSystem):
        result = walk_chain(system, "totally-fake-id")
        assert result.found is False
        assert result.links == []

    def test_resolved_receipt_classification_non_refusal(
        self, system: GateReceiptSystem
    ):
        r = _emit(system, gate="g", verdict="pass", bundle={"ok": True})
        result = walk_chain(system, r.receipt_id)
        assert result.found is True
        assert len(result.links) == 1
        assert result.links[0].kind == "non_refusal"
        assert result.links[0].refusal_kind is None

    def test_resolved_receipt_classification_refusal(self, system):
        bundle = {"refusal_kind": REFUSAL_ADMISSION_DENIED}
        r = _emit(system, gate="g", verdict="block", bundle=bundle)
        result = walk_chain(system, r.receipt_id)
        assert result.links[0].kind == "refusal"
        assert result.links[0].refusal_kind == REFUSAL_ADMISSION_DENIED

    def test_resolved_receipt_classification_bypass(self, system):
        bundle = {"refusal_kind": BYPASS_BA3_FOR_MVP}
        r = _emit(system, gate="g", verdict="observe", bundle=bundle)
        result = walk_chain(system, r.receipt_id)
        assert result.links[0].kind == "bypass"
        assert result.links[0].refusal_kind == BYPASS_BA3_FOR_MVP

    def test_resolved_receipt_classification_stale_vocabulary(self, system):
        bundle = {"refusal_kind": "wicket_blocked"}  # deprecated fixture
        r = _emit(system, gate="g", verdict="block", bundle=bundle)
        result = walk_chain(system, r.receipt_id)
        link = result.links[0]
        assert link.kind == "stale_vocabulary"
        assert link.refusal_kind == "wicket_blocked"
        # Warning is recorded.
        assert any("stale vocabulary" in w for w in link.warnings)

    def test_max_depth_bound_terminates(self, system):
        # Build a 5-deep linear chain.
        prev_id = None
        receipts = []
        for i in range(5):
            bundle: dict[str, Any] = {"step": i}
            if prev_id is not None:
                bundle["parent_receipt_ids"] = [prev_id]
            r = _emit(
                system,
                gate=f"step_{i}",
                verdict="pass",
                bundle=bundle,
                subject_bytes=f"step-{i}".encode(),
            )
            receipts.append(r)
            prev_id = r.receipt_id

        # Walk with max_depth=2 — should render exactly 2 links plus warning.
        result = walk_chain(system, receipts[-1].receipt_id, max_depth=2)
        assert result.found is True
        assert len(result.links) == 2
        # Final link carries the max_depth warning.
        assert any("max_depth" in w for w in result.links[-1].warnings)


class TestRenderTextSmoke:
    def test_render_text_contains_header_and_separator(
        self, system: GateReceiptSystem
    ):
        r = _emit(system, gate="g", verdict="pass", bundle={"x": 1})
        result = walk_chain(system, r.receipt_id)
        text = render_text(result)
        assert text.startswith(f"why {r.receipt_id}\n")
        assert "─" * 22 in text


# ---------------------------------------------------------------------------
# D0a load-bearing test: `governor why` walks a REAL emitted refusal chain.
#
# The operator-mandated load-bearing test: drive the standing/wicket/LA
# clients (with a real GateReceiptSystem wired in) through a refusal path
# end-to-end, then invoke `governor why <receipt-id>` via CliRunner and
# assert the rendering walks the actual chain. No synthetic fixtures for
# the receipt chain — every receipt rendered must have been emitted by a
# real client refusal path.
# ---------------------------------------------------------------------------


class TestWhyWalksRealRefusalChain:
    """End-to-end: real refusal in the clients → walked by `governor why`."""

    def test_why_renders_real_wicket_refusal_with_standing_parent(
        self, runner, gov_dir, tmp_path
    ):
        """Wicket refusal caused by standing refusal: walk surfaces both.

        Wiring: GateReceiptSystem(gov_dir) is the *same* system the CLI's
        `governor why` discovers via the -r flag. The standing and wicket
        clients are constructed with this real sink. We invoke
        WicketClient.check() with a missing standing_receipt_id; both
        clients emit refusal receipts; `governor why` walks the wicket
        receipt back to its standing parent.
        """
        # Imports inside the test so the suite has no import-time coupling
        # to the LA/standing client construction.
        from governor.standing_client import StandingClient
        from governor.wicket_client import (
            ActorStanding,
            CookedContext,
            Precedence,
            Revocation,
            ScopeAssertion,
            WicketClient,
            WicketRefusal,
        )

        sink = GateReceiptSystem(gov_dir)
        # Standing downstream is intentionally empty (any id would dangle).
        # The cooked context passes None so the StandingRequired path fires.
        standing_client = StandingClient(
            verify_fn=lambda sid: None,
            receipt_sink=sink,
        )
        wicket_client = WicketClient(
            standing_client=standing_client,
            wicket_check_fn=lambda c: pytest.fail(
                "wicket-check must NOT be invoked on missing standing"
            ),
            receipt_sink=sink,
        )
        cooked = CookedContext(
            actor="agent-d0a",
            actor_standing=ActorStanding(cls="interpret", provenance="caller_asserted"),
            intended_action="git.commit",
            operation_class="execute",
            target="docs/d0a.md",
            claimed_basis={"rule": "test", "evidence_refs": []},
            precedence=Precedence(
                resolution="active",
                provenance="caller_asserted",
                evidence_refs=(),
            ),
            revocation=Revocation(
                basis_revoked=False,
                standing_forbidden=False,
                provenance="caller_asserted",
                evidence_refs=(),
            ),
            expected_effect="commit",
            call_timestamp="2026-06-09T12:00:00Z",
            standing_receipt_id=None,
            scope_assertion=ScopeAssertion(
                scope_includes_target=True,
                provenance="caller_asserted",
                evidence_refs=(),
            ),
        )

        # Drive the real refusal path.
        result = wicket_client.check(cooked)
        assert isinstance(result, WicketRefusal)
        wicket_rid = result.receipt_id
        standing_rid = result.parent_receipt_id
        assert wicket_rid is not None
        assert standing_rid is not None

        # Now `governor why` walks the wicket receipt → standing receipt.
        cli_result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", wicket_rid]
        )
        assert cli_result.exit_code == 0
        assert "Traceback" not in cli_result.output
        # Both receipts surface in the chain rendering.
        assert wicket_rid[:12] in cli_result.output
        assert standing_rid[:12] in cli_result.output
        # Walked in the right order: child (wicket) first, parent (standing)
        # second.
        idx_wicket = cli_result.output.index(wicket_rid[:12])
        idx_standing = cli_result.output.index(standing_rid[:12])
        assert idx_wicket < idx_standing
        # The refusal kind is visible at both layers.
        assert "REFUSED" in cli_result.output
        assert "standing_required" in cli_result.output
        # Gate names visible (proving the chain crossed seams).
        assert "wicket_seam" in cli_result.output
        assert "standing_seam" in cli_result.output

    def test_why_renders_real_la_refusal_with_admission_parent(
        self, runner, gov_dir, tmp_path
    ):
        """LA refusal cites admission receipt id as parent.

        D0c-a update: the admission parent is emitted by a real
        ``WicketClient.check()`` success path (not by a direct
        ``sink.emit(...)`` call). This closes required test #3 (LA refusal
        cites a real wicket-emitted admission receipt id as parent) and
        the D0a-surfaced "one synthesized link" debt — every receipt in
        the chain that ``governor why`` renders is produced by a real
        client call.
        """
        from governor.linear_accountant_client import (
            LA_DECISION_DENIED,
            CookedCapacityRequest,
            LinearAccountantClient,
            RefusalResult,
        )
        from governor.standing_client import (
            StandingClient,
            StandingReceiptRef,
        )
        from governor.wicket_client import (
            ActorStanding,
            CookedContext,
            Precedence,
            Revocation,
            ScopeAssertion,
            WicketClient,
            WicketVerdict,
        )

        sink = GateReceiptSystem(gov_dir)

        # Step 1: drive the wicket happy path against the same sink so the
        # admission receipt is emitted by ``WicketClient.check()`` directly.
        # The standing service knows one valid digest; the wicket-check
        # downstream returns an opaque sentinel verdict (the seam routes,
        # it does not interpret).
        valid_digest = "a" * 64
        standing_ref = StandingReceiptRef(
            digest=valid_digest, kind="grant_issued"
        )

        def standing_verify(sid: str):
            return standing_ref if sid == valid_digest else None

        def wicket_check(_cooked):
            return {"surface_verdict": "authorized"}

        standing_client = StandingClient(
            verify_fn=standing_verify, receipt_sink=sink
        )
        wicket_client = WicketClient(
            standing_client=standing_client,
            wicket_check_fn=wicket_check,
            receipt_sink=sink,
        )
        cooked = CookedContext(
            actor="agent-d0c-a",
            actor_standing=ActorStanding(
                cls="interpret", provenance="caller_asserted"
            ),
            intended_action="write_file",
            operation_class="execute",
            target="/tmp/d0c-a",
            claimed_basis={"rule": "test", "evidence_refs": []},
            precedence=Precedence(
                resolution="active",
                provenance="caller_asserted",
                evidence_refs=(),
            ),
            revocation=Revocation(
                basis_revoked=False,
                standing_forbidden=False,
                provenance="caller_asserted",
                evidence_refs=(),
            ),
            expected_effect="write file at target path",
            call_timestamp="2026-06-09T12:00:00Z",
            standing_receipt_id=valid_digest,
            scope_assertion=ScopeAssertion(
                scope_includes_target=True,
                provenance="caller_asserted",
                evidence_refs=(),
            ),
        )
        admission = wicket_client.check(cooked)
        assert isinstance(admission, WicketVerdict)
        admission_id = admission.receipt_id
        assert admission_id is not None
        # Sanity: the receipt is in the same store the LA verifier reads.
        assert sink.receipt_store.get_by_id(admission_id) is not None

        # Step 2: drive the LA refusal against the real admission id.
        def denied_response(la_request, now):
            return {
                "decision": LA_DECISION_DENIED,
                "denial_reason": "insufficient stock",
                "receipt": "la_rcpt_deny_d0c_a",
            }

        la_client = LinearAccountantClient(
            request_capacity_callable=denied_response,
            consume_callable=lambda req, now: pytest.fail(
                "consume must not be called"
            ),
            # The admission_verifier resolves through the same sink — the
            # wicket-emitted id flows across the seam.
            admission_verifier=(
                lambda rid: sink.receipt_store.get_by_id(rid) is not None
            ),
            receipt_sink=sink,
        )
        request = CookedCapacityRequest(
            request_id="req-d0c-a",
            actor="agent-d0c-a",
            action="write_file",
            target="/tmp/d0c-a",
            scope="fs_write",
            requested_capacity=1,
            admission_receipt_id=admission_id,
            eligibility_valid_until=1000,
            expires_after=1000,
        )
        result = la_client.request_capacity(request, now=0)
        assert isinstance(result, RefusalResult)
        assert result.kind == "capacity_refused"
        assert result.receipt_id is not None
        # The LA refusal cites the REAL wicket-emitted admission id as parent.
        assert result.parent_receipt_id == admission_id

        cli_result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", result.receipt_id]
        )
        assert cli_result.exit_code == 0
        assert "Traceback" not in cli_result.output
        # LA refusal receipt + admission parent both surface in the chain.
        assert result.receipt_id[:12] in cli_result.output
        assert admission_id[:12] in cli_result.output
        # Chain order: LA (child) before admission (parent).
        idx_la = cli_result.output.index(result.receipt_id[:12])
        idx_adm = cli_result.output.index(admission_id[:12])
        assert idx_la < idx_adm
        # Refusal classification visible.
        assert "REFUSED" in cli_result.output
        assert "capacity_refused" in cli_result.output
        # Seam names visible — both seams crossed by real receipts.
        assert "la_seam" in cli_result.output
        assert "wicket_seam" in cli_result.output
        # The admission parent renders as OK (non_refusal), not as a
        # MISSING dangling link — the load-bearing assertion for required
        # test #4 ("walks the real parent chain with no synthetic
        # fixture ids").
        assert "OK" in cli_result.output

    def test_why_walks_full_real_la_to_standing_chain(
        self, runner, gov_dir, tmp_path
    ):
        """Three-link chain, all emitted by real client refusal paths.

        Standing client's refusal mints the standing receipt; wicket
        client's refusal cites the standing receipt and mints its own;
        an admission-authorized receipt would normally bridge to LA, but
        the missing-standing refusal stops the chain at the wicket layer.
        We extend by also driving the LA path: its refusal cites the
        wicket-authorized admission receipt as parent (the admission
        comes from the same GateReceiptSystem so it is real).

        Validates the "at least one chain must be real, not synthetic"
        load-bearing assertion: every receipt rendered traces back to a
        client refusal call.
        """
        from governor.linear_accountant_client import (
            CookedCapacityRequest,
            LA_DECISION_DENIED,
            LinearAccountantClient,
            RefusalResult,
        )
        from governor.standing_client import StandingClient
        from governor.wicket_client import (
            ActorStanding,
            CookedContext,
            Precedence,
            Revocation,
            ScopeAssertion,
            WicketClient,
        )

        sink = GateReceiptSystem(gov_dir)

        # Step 1: drive a real wicket refusal (standing missing). This
        # emits two real receipts: standing + wicket. We do NOT use these
        # in the LA chain — they prove the standing/wicket emission path
        # works under the same sink. They surface in the receipt store as
        # independent receipts.
        standing_client = StandingClient(
            verify_fn=lambda sid: None,
            receipt_sink=sink,
        )
        wicket_client = WicketClient(
            standing_client=standing_client,
            wicket_check_fn=lambda c: pytest.fail("wicket-check forbidden"),
            receipt_sink=sink,
        )
        cooked = CookedContext(
            actor="agent-d0a",
            actor_standing=ActorStanding(cls="interpret", provenance="caller_asserted"),
            intended_action="git.commit",
            operation_class="execute",
            target="docs/d0a.md",
            claimed_basis={"rule": "test", "evidence_refs": []},
            precedence=Precedence(
                resolution="active",
                provenance="caller_asserted",
                evidence_refs=(),
            ),
            revocation=Revocation(
                basis_revoked=False,
                standing_forbidden=False,
                provenance="caller_asserted",
                evidence_refs=(),
            ),
            expected_effect="commit",
            call_timestamp="2026-06-09T12:00:00Z",
            standing_receipt_id=None,
            scope_assertion=ScopeAssertion(
                scope_includes_target=True,
                provenance="caller_asserted",
                evidence_refs=(),
            ),
        )
        wicket_refusal = wicket_client.check(cooked)
        wicket_rid = wicket_refusal.receipt_id
        standing_rid = wicket_refusal.parent_receipt_id
        assert wicket_rid is not None and standing_rid is not None

        # Step 2: walk the wicket refusal chain via `governor why` — this
        # is the real chain the demo will surface.
        cli_result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", wicket_rid]
        )
        assert cli_result.exit_code == 0
        # The chain contains both real receipts, in order.
        assert wicket_rid[:12] in cli_result.output
        assert standing_rid[:12] in cli_result.output
        # Step 3: cross-check that the LA seam emission also chains. D0c-a
        # update: the admission parent is emitted by a real
        # ``WicketClient.check()`` success path (not by ``sink.emit``) so
        # every receipt the chain rendering surfaces has a real client
        # provenance — the synthesized-link debt from D0a is closed.
        valid_digest = "b" * 64
        from governor.standing_client import StandingReceiptRef

        ref = StandingReceiptRef(digest=valid_digest, kind="grant_issued")
        happy_standing = StandingClient(
            verify_fn=lambda sid: ref if sid == valid_digest else None,
            receipt_sink=sink,
        )
        happy_wicket = WicketClient(
            standing_client=happy_standing,
            wicket_check_fn=lambda _c: {"surface_verdict": "authorized"},
            receipt_sink=sink,
        )
        happy_cooked = CookedContext(
            actor="agent-d0c-a-full",
            actor_standing=ActorStanding(
                cls="interpret", provenance="caller_asserted"
            ),
            intended_action="write_file",
            operation_class="execute",
            target="/tmp/full",
            claimed_basis={"rule": "test", "evidence_refs": []},
            precedence=Precedence(
                resolution="active",
                provenance="caller_asserted",
                evidence_refs=(),
            ),
            revocation=Revocation(
                basis_revoked=False,
                standing_forbidden=False,
                provenance="caller_asserted",
                evidence_refs=(),
            ),
            expected_effect="write",
            call_timestamp="2026-06-09T12:00:00Z",
            standing_receipt_id=valid_digest,
            scope_assertion=ScopeAssertion(
                scope_includes_target=True,
                provenance="caller_asserted",
                evidence_refs=(),
            ),
        )
        admission = happy_wicket.check(happy_cooked)
        assert admission.receipt_id is not None

        la_client = LinearAccountantClient(
            request_capacity_callable=lambda r, n: {
                "decision": LA_DECISION_DENIED,
                "denial_reason": "no stock",
                "receipt": "la_full_chain",
            },
            consume_callable=lambda r, n: pytest.fail("consume forbidden"),
            admission_verifier=(
                lambda rid: sink.receipt_store.get_by_id(rid) is not None
            ),
            receipt_sink=sink,
        )
        la_result = la_client.request_capacity(
            CookedCapacityRequest(
                request_id="req-full",
                actor="agent-d0a",
                action="write_file",
                target="/tmp/full",
                scope="fs_write",
                requested_capacity=1,
                admission_receipt_id=admission.receipt_id,
                eligibility_valid_until=1000,
                expires_after=1000,
            ),
            now=0,
        )
        assert isinstance(la_result, RefusalResult)
        la_cli_result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", la_result.receipt_id]
        )
        assert la_cli_result.exit_code == 0
        assert la_result.receipt_id[:12] in la_cli_result.output
        assert admission.receipt_id[:12] in la_cli_result.output

    def test_why_renders_real_la_refusal_json(self, runner, gov_dir, tmp_path):
        """JSON renderer also consumes a real client-emitted refusal."""
        from governor.linear_accountant_client import (
            LinearAccountantClient,
            RefusalResult,
        )

        sink = GateReceiptSystem(gov_dir)
        from governor.linear_accountant_client import CookedCapacityRequest

        client = LinearAccountantClient(
            request_capacity_callable=lambda r, n: pytest.fail("no call"),
            consume_callable=lambda r, n: pytest.fail("no call"),
            admission_verifier=lambda rid: False,
            receipt_sink=sink,
        )
        result = client.request_capacity(
            CookedCapacityRequest(
                request_id="req-json",
                actor="agent",
                action="write",
                target="/tmp/x",
                scope="fs",
                requested_capacity=1,
                admission_receipt_id=None,
                eligibility_valid_until=1,
                expires_after=1,
            ),
            now=0,
        )
        assert isinstance(result, RefusalResult)
        cli_result = runner.invoke(
            cli, ["-r", str(tmp_path), "why", result.receipt_id, "--json"]
        )
        assert cli_result.exit_code == 0
        data = json.loads(cli_result.output)
        assert data["requested_id"] == result.receipt_id
        assert data["found"] is True
        link = data["links"][0]
        assert link["kind"] == "refusal"
        assert link["refusal_kind"] == "admission_denied"
        assert link["receipt"]["gate"] == "la_seam"
