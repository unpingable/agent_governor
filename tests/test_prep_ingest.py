"""P3.4 prep-before-ingest indecomposable-gate blocker.

The 8 acceptance criteria (operator):
  1. indecomposable_gate blocks ingest.
  2. rerunning prep does not clear the claim.
  3. planner-proposed decomposition does not clear the claim.
  4. discharge requires structured OperatorDischargeEvidence(operator_receipt_ref).
  5. empty/whitespace/bool operator refs refused.
  6. discharged claim remains visible/auditable as prior blocker.
  7. generic discharge without operator evidence still refused for this claim path.
  8. the filed collector-binding gap remains open and referenced.

Plus the Codex-pass-1 fixes: claims are namespaced by plan_id (no cross-plan
collision); the READER is fail-closed (a discharged record with no operator ref
stays blocking).

Doctrine: P3.4 installs a clearance SOCKET, not a discharge subsystem.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.prep_ingest import (
    INDECOMPOSABLE_GATE,
    IndecomposableGateClaim,
    IngestRefused,
    OperatorDischargeEvidence,
    PlanGate,
    PrepIngestLedger,
    assert_ingest_admissible,
    prep_detect,
)

_PLAN = "plan-A"


def _gates(*, bad: int = 1, good: int = 1):
    gates = [PlanGate(gate_id=f"good{i}", decomposable=True) for i in range(good)]
    gates += [
        PlanGate(gate_id=f"bad{i}", decomposable=False, reason="ambiguous authority")
        for i in range(bad)
    ]
    return gates


class TestIngestBlocking:
    def test_indecomposable_gate_blocks_ingest(self, tmp_path: Path) -> None:
        # AC1
        led = PrepIngestLedger(tmp_path)
        claims = prep_detect(_PLAN, _gates(bad=1, good=2), led)
        assert len(claims) == 1  # only the indecomposable gate produced a claim
        assert claims[0].kind == INDECOMPOSABLE_GATE
        assert not led.ingest_admissible()
        with pytest.raises(IngestRefused) as exc:
            assert_ingest_admissible(led)
        assert claims[0].claim_id in exc.value.open_claim_ids

    def test_fully_decomposable_plan_ingests(self, tmp_path: Path) -> None:
        led = PrepIngestLedger(tmp_path)
        claims = prep_detect(_PLAN, _gates(bad=0, good=3), led)
        assert claims == ()
        assert led.ingest_admissible()
        assert_ingest_admissible(led)  # does not raise

    def test_rerunning_prep_does_not_clear(self, tmp_path: Path) -> None:
        # AC2: re-detecting the same indecomposable gate is idempotent, not a clear.
        led = PrepIngestLedger(tmp_path)
        first = prep_detect(_PLAN, _gates(bad=1), led)
        again = prep_detect(_PLAN, _gates(bad=1), led)
        assert first[0].claim_id == again[0].claim_id  # same content-addressed claim
        assert len(led.all_claims()) == 1  # no duplicate
        assert not led.ingest_admissible()  # still blocked

    def test_planner_proposed_decomposition_does_not_clear(self, tmp_path: Path) -> None:
        # AC3: a re-run where the planner now declares the SAME gate decomposable
        # does NOT discharge the open claim. The planner may propose; it may not
        # self-certify that the judgment vanished.
        led = PrepIngestLedger(tmp_path)
        prep_detect(_PLAN, [PlanGate("g1", decomposable=False, reason="x")], led)
        assert not led.ingest_admissible()
        # planner re-runs prep, now claiming g1 is decomposable:
        prep_detect(_PLAN, [PlanGate("g1", decomposable=True)], led)
        assert not led.ingest_admissible()  # claim still open — not self-cleared
        assert led.open_claims()[0].gate_id == "g1"

    def test_two_plans_same_gate_id_do_not_collide(self, tmp_path: Path) -> None:
        # Codex F1: plan_id namespaces the claim. Clearing plan-A's gate must NOT
        # clear plan-B's gate of the same id.
        led = PrepIngestLedger(tmp_path)
        a = prep_detect("plan-A", [PlanGate("g", decomposable=False)], led)[0]
        b = prep_detect("plan-B", [PlanGate("g", decomposable=False)], led)[0]
        assert a.claim_id != b.claim_id
        assert len(led.all_claims()) == 2
        led.operator_discharge(
            a.claim_id, OperatorDischargeEvidence(operator_receipt_ref="op-A")
        )
        # plan-B's claim is still open — discharging A did not bleed into B.
        assert b.claim_id in {c.claim_id for c in led.open_claims()}
        assert not led.ingest_admissible()


class TestOperatorDischargeSocket:
    def test_discharge_requires_structured_operator_evidence(self, tmp_path: Path) -> None:
        # AC4 + AC7: the only clearance is operator evidence; a generic/no-evidence
        # discharge is refused for this claim kind.
        led = PrepIngestLedger(tmp_path)
        claim = prep_detect(_PLAN, _gates(bad=1), led)[0]
        with pytest.raises(ValueError, match="requires OperatorDischargeEvidence"):
            led.operator_discharge(claim.claim_id, None)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="requires OperatorDischargeEvidence"):
            led.operator_discharge(claim.claim_id, "op-receipt-7")  # type: ignore[arg-type]
        # the real socket clears it:
        led.operator_discharge(
            claim.claim_id, OperatorDischargeEvidence(operator_receipt_ref="op-rcpt-7")
        )
        assert led.ingest_admissible()

    def test_operator_ref_anti_forgery(self, tmp_path: Path) -> None:
        # AC5: bare flag / whitespace ref refused (same shape as P3.3 sockets).
        with pytest.raises(ValueError, match="operator_receipt_ref"):
            OperatorDischargeEvidence(operator_receipt_ref="")
        with pytest.raises(ValueError, match="operator_receipt_ref"):
            OperatorDischargeEvidence(operator_receipt_ref="   ")
        with pytest.raises(ValueError, match="operator_receipt_ref"):
            OperatorDischargeEvidence(operator_receipt_ref=True)  # type: ignore[arg-type]

    def test_discharged_claim_remains_auditable(self, tmp_path: Path) -> None:
        # AC6: discharge does not delete; the claim stays visible as a prior
        # blocker, carrying the operator ref that cleared it.
        led = PrepIngestLedger(tmp_path)
        claim = prep_detect(_PLAN, _gates(bad=1), led)[0]
        led.operator_discharge(
            claim.claim_id, OperatorDischargeEvidence(operator_receipt_ref="op-cleared-9")
        )
        assert led.ingest_admissible()
        # gone from OPEN, still present in ALL with provenance:
        assert claim.claim_id not in {c.claim_id for c in led.open_claims()}
        audited = led.get(claim.claim_id)
        assert audited is not None
        assert audited.discharged is True
        assert audited.operator_receipt_ref == "op-cleared-9"
        assert claim.claim_id in {c.claim_id for c in led.all_claims()}

    def test_malformed_discharged_record_fails_closed(self, tmp_path: Path) -> None:
        # Codex F2: a stored discharged=True record with NO operator ref is
        # malformed/tampered — the reader must treat it as STILL BLOCKING, never
        # silently admit ingest. A claim becomes non-blocking ONLY through an
        # operator-receipted discharge, enforced at the read boundary.
        led = PrepIngestLedger(tmp_path)
        claim = prep_detect(_PLAN, _gates(bad=1), led)[0]
        store = tmp_path / "prep_ingest_ledger" / "claims.json"
        data = json.loads(store.read_text())
        data[claim.claim_id]["discharged"] = True  # forged clearance, no operator ref
        data[claim.claim_id]["operator_receipt_ref"] = None
        store.write_text(json.dumps(data))
        # Fail-closed: the tampered discharge does not clear ingest.
        assert not led.ingest_admissible()
        assert claim.claim_id in {c.claim_id for c in led.open_claims()}

    def test_no_generic_flag_flip_method_exists(self, tmp_path: Path) -> None:
        # AC7 (structural): there is no non-operator discharge path for this kind.
        led = PrepIngestLedger(tmp_path)
        assert not hasattr(led, "discharge")  # only operator_discharge exists

    def test_record_refuses_born_discharged(self, tmp_path: Path) -> None:
        led = PrepIngestLedger(tmp_path)
        with pytest.raises(ValueError, match="recorded OPEN"):
            led.record(
                IndecomposableGateClaim(
                    plan_id=_PLAN, gate_id="g", reason="x", discharged=True
                )
            )
        with pytest.raises(ValueError, match="recorded OPEN"):
            led.record(
                IndecomposableGateClaim(
                    plan_id=_PLAN, gate_id="g", reason="x",
                    operator_receipt_ref="smuggled",
                )
            )

    def test_discharge_unknown_claim_refused(self, tmp_path: Path) -> None:
        led = PrepIngestLedger(tmp_path)
        with pytest.raises(KeyError):
            led.operator_discharge(
                "nope", OperatorDischargeEvidence(operator_receipt_ref="x")
            )


class TestIdentityAndRepair:
    def test_blank_gate_id_refused(self, tmp_path: Path) -> None:
        # Codex F1: an empty/whitespace/bool gate_id is an invalid claim identity
        # (would collapse distinct blockers into one claim_id).
        for bad in ("", "   ", True):
            with pytest.raises(ValueError, match="gate_id"):
                IndecomposableGateClaim(plan_id=_PLAN, gate_id=bad)  # type: ignore[arg-type]
        # via prep_detect too:
        led = PrepIngestLedger(tmp_path)
        with pytest.raises(ValueError, match="gate_id"):
            prep_detect(_PLAN, [PlanGate("", decomposable=False)], led)

    def test_blank_plan_id_refused(self, tmp_path: Path) -> None:
        for bad in ("", "   ", True):
            with pytest.raises(ValueError, match="plan_id"):
                IndecomposableGateClaim(plan_id=bad, gate_id="g")  # type: ignore[arg-type]
        led = PrepIngestLedger(tmp_path)
        with pytest.raises(ValueError, match="plan_id"):
            prep_detect("  ", [PlanGate("g", decomposable=False)], led)

    def test_is_cleared_is_the_semantic_predicate(self) -> None:
        # Codex F3: raw discharged flag is storage; is_cleared is semantics.
        malformed = IndecomposableGateClaim(
            plan_id=_PLAN, gate_id="g", discharged=True, operator_receipt_ref=None
        )
        assert malformed.discharged is True
        assert malformed.is_cleared is False  # discharged but no operator ref
        proper = IndecomposableGateClaim(
            plan_id=_PLAN, gate_id="g", discharged=True, operator_receipt_ref="op-1"
        )
        assert proper.is_cleared is True

    def test_genuine_operator_receipt_repairs_tampered_record(self, tmp_path: Path) -> None:
        # Codex F2: a malformed discharged-without-ref record stays blocking
        # (fail-closed) AND can be repaired/re-cleared by a genuine operator
        # discharge through the official socket (idempotency keys on is_cleared,
        # not the raw flag).
        led = PrepIngestLedger(tmp_path)
        claim = prep_detect(_PLAN, _gates(bad=1), led)[0]
        store = tmp_path / "prep_ingest_ledger" / "claims.json"
        data = json.loads(store.read_text())
        data[claim.claim_id]["discharged"] = True
        data[claim.claim_id]["operator_receipt_ref"] = None
        store.write_text(json.dumps(data))
        assert not led.ingest_admissible()  # tampered clearance does not admit
        # genuine operator receipt repairs it:
        repaired = led.operator_discharge(
            claim.claim_id, OperatorDischargeEvidence(operator_receipt_ref="op-real")
        )
        assert repaired.is_cleared is True
        assert repaired.operator_receipt_ref == "op-real"
        assert led.ingest_admissible()


class TestGapReferenced:
    def test_collector_binding_gap_remains_open_and_referenced(self) -> None:
        # AC8: the deeper discharge hardening is filed and still OPEN (candidate,
        # authorizes no build), and this module points at it (socket, not subsystem).
        gap = Path("specs/gaps/GOV_GAP_DISCHARGE_COLLECTOR_BINDING_001.md")
        assert gap.exists()
        text = gap.read_text()
        status = text.split("## Status", 1)[1].split("##", 1)[0]
        assert "Candidate" in status and "authorizes no build" in status
        assert "LANDED" not in status  # not closed/shipped
        src = Path("src/governor/prep_ingest.py").read_text()
        assert "GOV_GAP_DISCHARGE_COLLECTOR_BINDING_001" in src
