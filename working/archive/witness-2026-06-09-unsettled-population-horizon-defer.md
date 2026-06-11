# Witness: Unsettled Population on Horizon-Defer (First Stitch)

**Filed:** 2026-06-09. **Scope:** populate `unsettled` for horizon-configured Defer receipts only. One claim, one path, one assertion on each end of the seam.

## What landed

Closes the docket item identified in [witness-2026-06-09-cli-reachability-classification.md](witness-2026-06-09-cli-reachability-classification.md) §"Link to `unsettled` population scope". Both ends of the Nightshift→Governor seam now witness the same typed claim:

| End | What is witnessed | Test |
|---|---|---|
| Rust (Nightshift) | `apply_horizon_outcomes` populates one `NonDischargeKind::Freshness` claim on every `Defer` outcome; the `FixtureGovernorClient`-captured request carries it. | `horizon_cross_run::tolerated_active_continues_to_defer_before_expiry` (existing test, extended) — asserts `call.unsettled.len() == 1 && kind == Freshness`. |
| Python (Governor) | `record_receipt` threads `event.unsettled` through to `GateReceiptSystem.emit`, which lands it on the v4 `GateReceipt.unsettled` field. | `TestRecordReceipt::test_unsettled_forwarded_to_receipt` (new) — asserts `fetched.unsettled[0].kind == UNSETTLED_FRESHNESS`. |
| Wire (JSON) | `RecordReceiptRequest` roundtrips `unsettled` through `from_dict`/`to_dict` without loss. | `TestRecordReceipt::test_unsettled_roundtrips_through_from_dict` (new). |
| Backward compat | Existing requests without `unsettled` keep working; emitted v4 receipt carries `()` (the positive "nothing surfaced" claim). | `TestRecordReceipt::test_unsettled_defaults_empty_when_not_supplied` (new). |

## Files changed

### Rust (`~/git/scheduler/crates/nightshiftd/`)

- `src/governor_client.rs`: added closed-enum `NonDischargeKind` (mirrors `gate_receipt.py:VALID_NON_DISCHARGE_KINDS` exactly via `#[serde(rename_all = "snake_case")]`); added `NonDischargeClaim` struct with `kind`/`reason`/`required_consumer?`/`required_witness?`; added `unsettled: Vec<NonDischargeClaim>` to `RecordReceiptRequest` (default empty, `skip_serializing_if = "Vec::is_empty"`); updated one internal `basic_request` helper to set `unsettled: Vec::new()`.
- `src/reconcile_horizon.rs`: in `apply_horizon_outcomes`'s `Defer` arm, build a single `NonDischargeClaim { kind: Freshness, reason: "defer outcome does not settle closure authority while horizon remains active", … }` and attach it to the outgoing `RecordReceiptRequest`. Other variants (`ActOnVerdict`, `Escalate*`, `Render*`) untouched.
- `tests/horizon_cross_run.rs`: imported `NonDischargeKind`; extended `tolerated_active_continues_to_defer_before_expiry`'s per-call loop with three assertions (`unsettled.len() == 1`, `kind == Freshness`, `reason` non-empty).
- `tests/governor_rpc_live.rs`: added `unsettled: Vec::new()` to its single literal initializer (still env-gated; no behavior change).

### Python (`~/git/agent_gov/`)

- `src/governor/nightshift_adapter.py`: imported `NonDischargeClaim` from `.gate_receipt`; added `unsettled: tuple[NonDischargeClaim, ...] = ()` field to `RecordReceiptRequest`; updated `to_dict` (emit when non-empty), `from_dict` (parse list of claim dicts via `NonDischargeClaim.from_dict`), and `record_receipt` (pass `unsettled=event.unsettled` to `GateReceiptSystem.emit`).
- `tests/test_nightshift_adapter.py`: imported `UNSETTLED_FRESHNESS` and `NonDischargeClaim`; added three tests to `TestRecordReceipt`: `test_unsettled_forwarded_to_receipt`, `test_unsettled_defaults_empty_when_not_supplied`, `test_unsettled_roundtrips_through_from_dict`.

## Test results

| Suite | Count | Status |
|---|---|---|
| Rust `nightshiftd` full sweep | 285 (across all bins) | green |
| Python `test_nightshift_adapter.py` + `test_gate_receipt.py` + `test_daemon.py` | 441 | green |
| `horizon_packet_state` siblings (unaffected) | 6 passed, 1 ignored | green |

## Acceptance criteria mapping

1. ✅ Only horizon-configured path changes — populate site is exclusively inside the `Defer` arm of `apply_horizon_outcomes`, which is only reachable when `reconcile_phase_with_horizon` is called with `Some(GovernorClient)`.
2. ✅ Default watchbill remains governor-blind — no edits to `run_watchbill`, `run_watchbill_with_liveness`, or `reconcile_phase`. CLI default path (no `--horizon-policy` / `--governor-socket`) does not reach `record_receipt`, so cannot populate `unsettled`.
3. ✅ Defer receipt includes `unsettled` with kind `freshness` — Rust test asserts on the wire; Python test asserts on the emitted v4 `GateReceipt.unsettled`.
4. ✅ Unknown/freeform kinds remain impossible — Rust enum is closed at the type system; Python `NonDischargeClaim.__post_init__` raises `ValueError` on unknown kind (already verified in `TestNonDischargeClaim::test_rejects_unknown_kind`).
5. ✅ Existing packet/ledger receipt observability tests still pass — `horizon_packet_state::defer_makes_governor_receipt_observable_in_packet_and_ledger` and 5 sibling tests all green.
6. ✅ No attempt to populate unsettled for Allow/Deny/Close/etc — only the `Defer` arm populates. Other `HorizonAction` variants and other event kinds untouched.
7. ✅ No CLI widening — no changes to `main.rs`, `build_horizon_deps`, or `run_watchbill_cmd`. Option 3 from the prior slice still holds.

## What this slice did NOT do

- **Did not** populate `unsettled` for any event kind other than horizon-Defer. `EventKind::ActionApplied`, `ActionDenied`, `ActionVerified`, `EscalationPaged`, `AgendaPromoted` all still emit empty `unsettled`. Each would need its own forcing-case slice with explicit semantic justification for what *that* verdict leaves unsettled.
- **Did not** add new `NonDischargeKind` variants. The closed enum stays at the original six (`Authority`, `EvidenceSufficiency`, `Freshness`, `Scope`, `Standing`, `ConsumerReliance`).
- **Did not** widen the default watchbill CLI path. `run_watchbill_cmd` without flags still emits no Governor receipts.
- **Did not** make `unsettled` mean "everything this receipt didn't prove." For Defer specifically, it means *"this verdict does not settle closure authority while the horizon remains active."* One claim. One reason. One existing path.
- **Did not** fix the pre-existing standing-validator bootstrap drift.
- **Did not** touch `governor_rpc_live.rs`'s live-RPC assertion logic (only added the required new field default).

## Doctrine reminder

The closed enum is the load-bearing piece. The prose `reason` is informational only and does not participate in matching or dispatch (per the C4 discipline lifted onto this surface). If a future verdict surfaces a non-discharge that doesn't fit one of the six kinds, that's a *docket signal* — new kind needs ratification — not permission to add a freeform string.

## Provenance

Filed 2026-06-09 after the CLI reachability classification (Option 3 preserved) and immediately following the user's "Tiny needle. No loom." instruction for the first semantic-population slice. The needle went through:

```
horizon-Defer outcome in apply_horizon_outcomes
  → Rust NonDischargeClaim { Freshness, … }
  → RecordReceiptRequest.unsettled
  → JSON-RPC wire (or FixtureGovernorClient in test)
  → Python RecordReceiptRequest.unsettled
  → record_receipt → GateReceiptSystem.emit(unsettled=…)
  → GateReceipt v4 .unsettled field
```

One stitch. The first one that actually carries the doctrine through the cloth.
