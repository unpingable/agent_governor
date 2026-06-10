# SPDX-License-Identifier: Apache-2.0
"""D0-Bridge: end-to-end test that NQ-side origin_mode crosses into AG.

Cross-repo bridge contract (D0-Bridge, 2026-06-09):

  * NQ migration 057 (``crates/nq-db/migrations/057_origin_mode_discriminator.sql``)
    lands the closed-vocabulary mint-provenance discriminator on every
    ``FindingSnapshot.origin_mode`` value: ``observed`` / ``drill`` /
    ``replay`` / ``synthetic``.
  * AG consumes the value verbatim via
    ``cooked_context_orchestrator.NQ_ORIGIN_MODES``; the orchestrator
    stamps ``origin_mode`` on every emitted gate receipt's
    ``evidence_bundle``.
  * ``governor why <receipt-id>`` walks the chain and renders a closed-
    vocabulary prefix (``DRILL`` / ``REPLAY`` / ``SYNTHETIC``) at the
    top when the chain origin is non-observed.

Test discipline (per operator's D0-Bridge spec, verbatim):

    If implementing this test in pure Python is awkward (because the NQ
    side is Rust), use a controlled fixture: a tiny Python helper that
    constructs the AG-side input by simulating the wire DTO shape NQ
    exposes (the same shape verified by the NQ-side Rust tests). The
    AG-side test should NOT shell out to the NQ binary; it should
    consume the DTO shape directly.

This file builds a fixture matching NQ's ``FindingSnapshot`` wire shape
(verified end-to-end by ``crates/nq-db/tests/origin_mode_discriminator.rs``),
drives the orchestrator with the consumed origin_mode, and asserts:

  1. every emitted GateReceipt's ``evidence_bundle["origin_mode"]``
     carries the drill value;
  2. ``governor why <receipt-id>`` renders ``DRILL`` at the top of
     output (text mode) and surfaces ``"drill": true`` / ``"observed":
     false`` (JSON mode).

The bridge holds if and only if BOTH assertions pass.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from governor.cli import cli
from governor.cooked_context_orchestrator import (
    EVIDENCE_KEY_ORIGIN_MODE,
    NQ_ORIGIN_MODES,
    ORIGIN_MODE_DRILL,
    ORIGIN_MODE_OBSERVED,
    ORIGIN_MODE_REPLAY,
    ORIGIN_MODE_SYNTHETIC,
    CookedContextOrchestrator,
    wrap_receipt_sink_with_origin_mode,
)
from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import (
    LA_DECISION_CONSUMED,
    LA_DECISION_GRANTED,
    CookedCapacityRequest,
    CookedConsumeRequest,
    LinearAccountantClient,
)
from governor.standing_client import StandingClient, StandingReceiptRef
from governor.wicket_client import (
    ActorStanding,
    CookedContext,
    Precedence,
    Revocation,
    ScopeAssertion,
    WicketClient,
)
from governor.why import (
    NON_OBSERVED_RENDER_PREFIX,
    RENDER_PREFIX_DRILL,
    RENDER_PREFIX_REPLAY,
    RENDER_PREFIX_SYNTHETIC,
    render_json,
    render_text,
    walk_chain,
)


# ---------------------------------------------------------------------------
# NQ wire DTO simulator.
#
# This dict matches the JSON shape produced by NQ's
# ``export_findings_from_conn`` (serde to JSON via ``serde_json`` in
# ``crates/nq-db/src/export.rs``) for a drilled / replayed / synthetic
# finding under migration 057. The Rust-side test
# ``crates/nq-db/tests/origin_mode_discriminator.rs::
# export_dto_distinguishes_all_four_origin_modes_simultaneously`` is
# the NQ-side counterpart that proves the same shape comes off the
# real wire.
#
# AG does NOT depend on the Rust binary, the Rust crate, or the SQLite
# schema — only on the wire DTO's top-level ``origin_mode`` string field,
# which is what crosses the repo boundary.
# ---------------------------------------------------------------------------


def _nq_finding_snapshot_dto(origin_mode: str, host: str = "host-bridge") -> dict[str, Any]:
    """Build a minimal NQ FindingSnapshot wire DTO with the given origin_mode.

    Matches the canonical wire shape established by NQ migration 057.
    Fields the bridge cares about: ``finding_key`` (chain identity),
    ``origin_mode`` (the discriminator). Other fields are sketched so
    a consumer reading the dict shape sees the canonical structure.
    """
    return {
        "schema": "nq.finding_snapshot.v1",
        "contract_version": 1,
        "finding_key": f"local/{host}/wal_bloat/%2Fdb",
        "identity": {
            "scope": "local",
            "host": host,
            "detector": "wal_bloat",
            "subject": "/db",
            "rule_hash": None,
        },
        "origin_mode": origin_mode,
        # Other DTO fields elided — the bridge contract is on origin_mode
        # alone (and finding_key for join identity). The Rust-side tests
        # cover the full DTO shape; here we focus on the bridge axis.
    }


# ---------------------------------------------------------------------------
# Bridge-side wiring helpers.
#
# Identical shape to the test helpers in test_cooked_context_orchestrator;
# duplicated here so this file remains the canonical end-to-end bridge
# witness and is readable in isolation.
# ---------------------------------------------------------------------------


_VALID_STANDING_DIGEST = "b" * 64


def _make_cooked_context(standing_receipt_id: str | None) -> CookedContext:
    return CookedContext(
        actor="claude-code",
        actor_standing=ActorStanding(cls="interpret", provenance="caller_asserted"),
        intended_action="write_file",
        operation_class="execute",
        target="/tmp/bridge_target",
        claimed_basis={"rule": "bridge_test", "evidence_refs": []},
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
        expected_effect="bridge end-to-end",
        call_timestamp="2026-06-09T12:00:00Z",
        standing_receipt_id=standing_receipt_id,
        scope_assertion=ScopeAssertion(
            scope_includes_target=True,
            provenance="caller_asserted",
            evidence_refs=(),
        ),
        prev_receipt_hash=None,
    )


def _capacity_template() -> CookedCapacityRequest:
    return CookedCapacityRequest(
        request_id="req-bridge-1",
        actor="claude-code",
        action="write_file",
        target="/tmp/bridge_target",
        scope="fs_write",
        requested_capacity=1,
        admission_receipt_id="will-be-replaced",
        eligibility_valid_until=1000,
        expires_after=1000,
        idempotency_key="req-bridge-1",
    )


def _consume_template() -> CookedConsumeRequest:
    return CookedConsumeRequest(
        consumption_event_id="evt-bridge-1",
        token_id="will-be-replaced",
        actor="claude-code",
        action="write_file",
        target="/tmp/bridge_target",
        amount=1,
        scope="fs_write",
    )


def _granted_response():
    def response(la_request: dict, now: int) -> dict:
        return {
            "decision": LA_DECISION_GRANTED,
            "token_id": "token-bridge-1",
            "granted_capacity": la_request["requested_capacity"],
            "scope": la_request["scope"],
            "expires_at": now + la_request["expires_after"],
            "receipt": {"la_receipt_id": "la-receipt-bridge"},
        }
    return response


def _consumed_response():
    def response(la_request: dict, now: int) -> dict:
        return {
            "decision": LA_DECISION_CONSUMED,
            "token_id": "token-bridge-1",
            "consumed_amount": la_request["amount"],
            "remaining_capacity": 0,
            "receipt": {"la_receipt_id": "la-consume-receipt-bridge"},
        }
    return response


def _admit_any(cooked_context: CookedContext) -> dict:
    return {"surface_verdict": "authorized", "_fake": True}


def _drive_chain(
    *,
    origin_mode: str,
    sink: GateReceiptSystem,
):
    """Drive standing → wicket → LA-request → LA-consume under origin_mode."""
    wrapped = wrap_receipt_sink_with_origin_mode(sink, origin_mode)
    standing_id = _VALID_STANDING_DIGEST
    ref = StandingReceiptRef(digest=standing_id, kind="grant_activated")
    standing_client = StandingClient(
        verify_fn=lambda sid: ref if sid == standing_id else None,
        receipt_sink=wrapped,
    )
    wicket_client = WicketClient(
        standing_client=standing_client,
        wicket_check_fn=_admit_any,
        receipt_sink=wrapped,
    )
    la_client = LinearAccountantClient(
        request_capacity_callable=_granted_response(),
        consume_callable=_consumed_response(),
        admission_verifier=lambda rid: rid is not None,
        receipt_sink=wrapped,
    )
    orchestrator = CookedContextOrchestrator(
        wicket_client=wicket_client,
        la_client=la_client,
        origin_mode=origin_mode,
    )
    return orchestrator.run(
        cooked_context=_make_cooked_context(standing_receipt_id=standing_id),
        capacity_request_template=_capacity_template(),
        consume_request_template=_consume_template(),
        now=0,
    )


# ---------------------------------------------------------------------------
# Bridge contract tests.
# ---------------------------------------------------------------------------


class TestNqWireDtoConsumesIntoAg:
    """NQ's ``FindingSnapshot.origin_mode`` is a string that AG admits.

    The bridge's discipline is verbatim consumption: AG never invents or
    aliases NQ values. These tests assert the four NQ-side closed-set
    values pass straight through into the AG-side ``origin_mode``
    parameter without translation.
    """

    @pytest.mark.parametrize(
        "nq_origin_mode",
        ["observed", "drill", "replay", "synthetic"],
    )
    def test_nq_wire_dto_origin_mode_consumes_into_ag_directly(
        self, tmp_path, nq_origin_mode
    ):
        # Step 1: construct an NQ wire DTO with the given origin_mode.
        nq_dto = _nq_finding_snapshot_dto(origin_mode=nq_origin_mode)
        # Step 2: cross the repo boundary by reading the field verbatim.
        consumed = nq_dto["origin_mode"]
        assert consumed == nq_origin_mode
        # Step 3: it is admissible by the AG-side closed set without
        # translation / renaming / aliasing.
        assert consumed in NQ_ORIGIN_MODES
        # Step 4: the orchestrator constructs against it cleanly.
        sink = GateReceiptSystem(tmp_path)
        result = _drive_chain(origin_mode=consumed, sink=sink)
        # The happy-path chain ran to consumption.
        assert result.consumed


class TestEvidenceBundlePropagation:
    """Every gate receipt on the chain carries the consumed origin_mode.

    Operator's bridge invariant 3: the discriminator propagates through
    every downstream gate receipt's ``evidence_bundle``.
    """

    @pytest.mark.parametrize(
        "nq_origin_mode",
        ["observed", "drill", "replay", "synthetic"],
    )
    def test_every_emitted_receipt_carries_origin_mode(
        self, tmp_path, nq_origin_mode
    ):
        sink = GateReceiptSystem(tmp_path)
        result = _drive_chain(origin_mode=nq_origin_mode, sink=sink)
        assert result.consumed

        receipts = sink.query()
        # Happy path emits at least one receipt (the wicket admission per
        # D0c-a). Refusal paths emit more — but every emitted receipt on
        # any path must carry the stamp.
        assert len(receipts) >= 1
        for receipt in receipts:
            evidence = sink.evidence_for(receipt)
            assert evidence is not None, (
                f"receipt {receipt.receipt_id!r} missing evidence bundle"
            )
            assert evidence.get(EVIDENCE_KEY_ORIGIN_MODE) == nq_origin_mode, (
                f"receipt {receipt.receipt_id!r} evidence_bundle missing "
                f"origin_mode={nq_origin_mode!r}; got "
                f"{evidence.get(EVIDENCE_KEY_ORIGIN_MODE)!r}"
            )


class TestGovernorWhyRendersDrillFirst:
    """Operator's bridge invariant 4: ``governor why`` renders a
    DRILL-first (or equivalent non-observed) prefix when the chain
    origin is non-observed.
    """

    def _emit_chain_under_origin(
        self, tmp_path: Path, origin_mode: str
    ) -> tuple[GateReceiptSystem, str]:
        """Drive a happy-path chain and return (sink, latest_receipt_id)."""
        sink = GateReceiptSystem(tmp_path / "gov")
        (tmp_path / "gov").mkdir(parents=True, exist_ok=True)
        result = _drive_chain(origin_mode=origin_mode, sink=sink)
        assert result.consumed
        receipts = sink.query()
        assert len(receipts) >= 1
        # ``query`` returns newest-first; take the head as the leaf id.
        leaf_id = receipts[0].receipt_id
        return sink, leaf_id

    @pytest.mark.parametrize(
        "nq_origin_mode,expected_prefix",
        [
            (ORIGIN_MODE_DRILL, RENDER_PREFIX_DRILL),
            (ORIGIN_MODE_REPLAY, RENDER_PREFIX_REPLAY),
            (ORIGIN_MODE_SYNTHETIC, RENDER_PREFIX_SYNTHETIC),
        ],
    )
    def test_non_observed_origin_renders_prefix_at_top(
        self, tmp_path, nq_origin_mode, expected_prefix
    ):
        sink, leaf_id = self._emit_chain_under_origin(tmp_path, nq_origin_mode)
        result = walk_chain(sink, leaf_id)
        assert result.found

        text = render_text(result)
        # The DRILL/REPLAY/SYNTHETIC prefix appears in the output BEFORE
        # any link header — the operator never mistakes a drilled chain
        # for an observed one.
        lines = text.splitlines()
        # Header lines: "why <id>" then "──...──" separator.
        # Then the bridge prefix. Then a separator. Then the link list.
        # We check the prefix lands in the first 5 lines.
        prefix_line_index = None
        for i, line in enumerate(lines[:5]):
            if line.startswith(expected_prefix + "  chain origin:"):
                prefix_line_index = i
                break
        assert prefix_line_index is not None, (
            f"expected line starting with {expected_prefix!r} in top of "
            f"output; got:\n{text}"
        )

    def test_observed_origin_renders_no_drill_prefix(self, tmp_path):
        sink, leaf_id = self._emit_chain_under_origin(
            tmp_path, ORIGIN_MODE_OBSERVED
        )
        result = walk_chain(sink, leaf_id)
        assert result.found

        text = render_text(result)
        # Observed chains MUST NOT carry a DRILL / REPLAY / SYNTHETIC
        # prefix — that's the no-laundering-the-other-direction guard.
        for prefix in NON_OBSERVED_RENDER_PREFIX.values():
            assert (
                f"{prefix}  chain origin:" not in text
            ), (
                f"observed-origin chain rendered {prefix!r} prefix; got:\n"
                f"{text}"
            )

    @pytest.mark.parametrize(
        "nq_origin_mode",
        ["drill", "replay", "synthetic"],
    )
    def test_json_output_surfaces_chain_origin_flags(
        self, tmp_path, nq_origin_mode
    ):
        sink, leaf_id = self._emit_chain_under_origin(tmp_path, nq_origin_mode)
        result = walk_chain(sink, leaf_id)
        payload = render_json(result)
        assert payload["origin_mode"] == nq_origin_mode
        assert payload["observed"] is False
        assert payload["drill"] == (nq_origin_mode == "drill")
        assert payload["replay"] == (nq_origin_mode == "replay")
        assert payload["synthetic"] == (nq_origin_mode == "synthetic")

    def test_json_output_surfaces_observed_flag_for_observed_origin(
        self, tmp_path
    ):
        sink, leaf_id = self._emit_chain_under_origin(
            tmp_path, ORIGIN_MODE_OBSERVED
        )
        result = walk_chain(sink, leaf_id)
        payload = render_json(result)
        assert payload["origin_mode"] == ORIGIN_MODE_OBSERVED
        assert payload["observed"] is True
        assert payload["drill"] is False
        assert payload["replay"] is False
        assert payload["synthetic"] is False


# ---------------------------------------------------------------------------
# The load-bearing end-to-end test: NQ DTO → AG chain → governor why
# renders DRILL. This is the bridge invariant in one test.
# ---------------------------------------------------------------------------


class TestCustodyBridgeHoldsEndToEnd:
    """The single load-bearing test for D0-Bridge.

    Operator's contract (verbatim, from the slice spec):

      1. Construct a real NQ finding (via the new mint / import API)
         with origin_mode = drill.
      2. Pass the finding's origin discriminator into AG via the cooked-
         context orchestrator.
      3. Drive the standing / wicket / LA chain (using the existing
         real-emission paths).
      4. Assert each emitted GateReceipt's
         ``evidence_bundle["origin_mode"]`` carries the drill value.
      5. Invoke ``governor why <receipt-id>`` and assert it renders DRILL
         at the top.

    The "real NQ finding" is constructed by simulating the NQ wire DTO
    shape directly (per operator's allowed fallback: "use a controlled
    fixture: a tiny Python helper that constructs the AG-side input by
    simulating the wire DTO shape NQ exposes (the same shape verified
    by the NQ-side Rust tests)."). The NQ-side Rust tests prove the
    same shape comes off the real wire; this test proves AG receives
    and propagates it.
    """

    def test_drill_finding_to_governor_why_drill_prefix_end_to_end(
        self, tmp_path
    ):
        # ---- Step 1: NQ-side fixture matching the wire DTO shape. -----
        # Mirrors what
        # crates/nq-db/tests/origin_mode_discriminator.rs::
        # export_dto_carries_origin_mode_for_drilled_imports
        # produces from a real DB after a drill-tagged ingest.
        nq_dto = _nq_finding_snapshot_dto(
            origin_mode=ORIGIN_MODE_DRILL,
            host="host-bridge-drill",
        )
        assert nq_dto["origin_mode"] == ORIGIN_MODE_DRILL

        # ---- Step 2: cross the repo boundary verbatim. ----------------
        consumed_origin_mode = nq_dto["origin_mode"]
        # AG admits the NQ-side concrete value through the closed set
        # without translation / renaming / aliasing.
        assert consumed_origin_mode in NQ_ORIGIN_MODES

        # ---- Step 3: drive the AG chain under the bridge value. -------
        # Initialize a minimal .governor/ tree (mirrors test_why_command).
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        (gov_dir / "facts").mkdir()
        (gov_dir / "facts" / "receipts").mkdir()
        (gov_dir / "facts" / "index.json").write_text("[]")
        (gov_dir / "decisions").mkdir()
        (gov_dir / "decisions" / "index.json").write_text("[]")
        (gov_dir / "proposals.json").write_text("{}")
        (gov_dir / "receipts").mkdir()
        sink = GateReceiptSystem(gov_dir)
        result = _drive_chain(origin_mode=consumed_origin_mode, sink=sink)
        assert result.consumed, (
            "happy-path chain did not run to consumption; bridge cannot "
            "be tested under refusal here"
        )

        # ---- Step 4: every emitted receipt carries the drill stamp. ---
        receipts = sink.query()
        assert len(receipts) >= 1
        for receipt in receipts:
            evidence = sink.evidence_for(receipt)
            assert evidence is not None
            assert evidence.get(EVIDENCE_KEY_ORIGIN_MODE) == ORIGIN_MODE_DRILL, (
                f"receipt {receipt.receipt_id!r} dropped the drill stamp; "
                f"evidence={evidence}"
            )

        # ---- Step 5: governor why renders DRILL at the top. -----------
        leaf_id = receipts[0].receipt_id
        runner = CliRunner()
        # CLI exercises the full path (cli wiring + walk_chain +
        # render_text). The DRILL prefix must appear before any link
        # line — operator's invariant: "DRILL-first (or equivalent
        # non-observed) prefix when the chain's origin is non-observed".
        cli_result = runner.invoke(
            cli,
            ["-r", str(tmp_path), "why", leaf_id],
        )
        assert cli_result.exit_code == 0, (
            f"governor why failed: exit={cli_result.exit_code}, "
            f"output={cli_result.output!r}"
        )
        lines = cli_result.output.splitlines()
        # The first non-separator line after the header must be the
        # bridge prefix.
        drill_lines = [
            line
            for line in lines[:5]
            if line.startswith(f"{RENDER_PREFIX_DRILL}  chain origin:")
        ]
        assert drill_lines, (
            f"governor why did not render DRILL prefix at top of output; "
            f"got:\n{cli_result.output}"
        )

        # ---- Step 5b: --json output carries drill=true ----------------
        cli_json = runner.invoke(
            cli,
            ["-r", str(tmp_path), "why", leaf_id, "--json"],
        )
        assert cli_json.exit_code == 0
        payload = json.loads(cli_json.output)
        assert payload["origin_mode"] == ORIGIN_MODE_DRILL
        assert payload["drill"] is True
        assert payload["observed"] is False
