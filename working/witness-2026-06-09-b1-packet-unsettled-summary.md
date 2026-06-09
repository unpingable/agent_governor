# Witness: B1 — Packet-Side `unsettled` Summary

**Filed:** 2026-06-09. **Scope:** packet visibility only. No Governor schema change, no default CLI widening, no new enum kinds, no other-outcome population. Follows the B0 audit (verdict B) and lifts the Nightshift packet surface from "receipt-linked but not visible" to "displayed alongside the receipt binding."

## What landed

Horizon-Defer packets now carry an operator-visible `unsettled` summary section. Reading the packet alone is sufficient to see *what the verdict left unsettled* without crossing to `governor receipts show <id>`.

Rendered YAML excerpt (from the actual extended test):

```yaml
unsettled:
- kind: freshness
  reason: defer outcome does not settle closure authority while horizon remains active
  receipt_id: fixture_receipt_0001
```

The summary preserves custody:

| Surface | Role |
|---|---|
| Packet `unsettled` | Display-only, derived; the operator's reading surface |
| Governor v4 `GateReceipt.unsettled` | Authority artifact; the content-bound record |
| Summary `receipt_id` | Binding back from display to source |

> **Invariant (documented inline in `packet.rs`):** the packet may *display* unsettled; it may not become the thing that *settles* unsettled.

## Edits

### Rust types (`~/git/scheduler/crates/nightshiftd/src/packet.rs`)

- Imported `NonDischargeKind` from `crate::governor_client`.
- New struct `UnsettledSummary { kind: NonDischargeKind, reason: String, receipt_id: String }` — display-only; intentionally drops the claim's optional `required_consumer` / `required_witness` to keep the packet surface distinct from the authority record.
- New field on `Packet`: `unsettled: Vec<UnsettledSummary>` with `#[serde(default, skip_serializing_if = "Vec::is_empty")]`. Empty by default for non-horizon / non-Defer paths; absent from YAML when empty.

### Plumbing (`reconcile_horizon.rs` + `pipeline.rs`)

- `HorizonReceipt` gained `unsettled: Vec<NonDischargeClaim>` so the populate site retains the claims sent to Governor, allowing the packet builder to derive summaries without re-deriving from the action variant.
- `apply_horizon_outcomes` (`Defer` arm) clones the request's `unsettled` into the `HorizonReceipt` before sending.
- `reconcile_phase_with_horizon` derives `Vec<UnsettledSummary>` from filtered (target-finding) `HorizonReceipt`s using `flat_map`. One summary per claim per receipt, each carrying its source `receipt_id`.
- `build_success_packet` gained a `target_unsettled: Vec<UnsettledSummary>` parameter and assigns it to `packet.unsettled`.
- Both non-horizon `Packet` literal sites (preflight-hold and liveness-gate-failed paths) initialize `unsettled: vec![]`. `mvp_a.rs` mock and two integration tests (`mvp_a_pipeline.rs`, `mvp_a_refusal.rs`) also updated.

### Tests (`horizon_packet_state.rs`)

Extended `defer_makes_governor_receipt_observable_in_packet_and_ledger` with a "Surface 3" assertion block:

1. `packet.unsettled.len() == 1`
2. `summary.kind == NonDischargeKind::Freshness`
3. `summary.reason` non-empty
4. `summary.receipt_id == packet_receipt` (same id surfaced in `receipt_references.governor_receipts[0]`)
5. **YAML rendering check:** `serde_yaml::to_string(&packet)` contains `"unsettled:"`, `"freshness"`, and the prose reason substring. This is the load-bearing operator-visible assertion — closes verdict B → A for the packet surface.

## Acceptance criteria mapping

1. ✅ Horizon Defer packet includes one visible unsettled summary
2. ✅ Summary includes kind=freshness and non-empty reason
3. ✅ Summary includes/goes next to the Governor receipt_id (the summary's `receipt_id` equals `receipt_references.governor_receipts[0]`)
4. ✅ Existing packet receipt_id behavior remains (`receipt_references.governor_receipts` untouched; existing assertions still pass)
5. ✅ Default watchbill remains governor-blind (no edits to `run_watchbill` / `run_watchbill_with_liveness` / `build_horizon_deps`; non-horizon Packet sites use empty `unsettled`)
6. ✅ No Governor receipt schema change (no Python changes this slice)
7. ✅ No new enum kinds (`NonDischargeKind` still six variants)
8. ✅ No packet claim for outcomes other than Defer (`apply_horizon_outcomes` populates only the `Defer` arm; other variants set no claims)
9. ✅ Tests prove operator-visible packet output contains freshness/reason (Surface 3 YAML rendering check)

## Test results

- `cargo test -p nightshiftd`: 281 tests across all bins, all green
- `horizon_packet_state` 6 passed (1 ignored, pre-existing)
- `horizon_cross_run` 5 passed (the prior slice's per-call `unsettled` assertion still passes because `apply_horizon_outcomes` still populates the wire field)
- `mvp_a_pipeline` / `mvp_a_refusal` still green after field addition

## What this slice did NOT do

- **Did not** add Governor text-mode rendering. The user explicitly scoped this out ("do not add Governor text-mode rendering unless already required by the packet test"). It wasn't required.
- **Did not** populate `unsettled` for any HorizonAction other than `Defer`. Same discipline as the prior slice.
- **Did not** widen the default `watchbill` CLI path.
- **Did not** add new `NonDischargeKind` variants.
- **Did not** change the v4 `GateReceipt` schema or any Python code.
- **Did not** add an operator-facing keeper section to the packet (`Render` action subcommand etc.). Packet shape change is structural; further usability iteration is its own slice.
- **Did not** version-bump `packet_version`. The change is additive with `skip_serializing_if = "Vec::is_empty"`, so existing parsers that ignore the field keep working. If downstream YAML consumers strictly reject unknown keys, that's a future docket item; for now the assumption is forward-compat parsers.

## Provenance

Filed 2026-06-09 after the B0 forcing-case audit confirmed verdict B (receipt-linked but not visible). One stitch on the Nightshift side. The label moved from inside the cabinet (Governor receipt store) to the packet surface where a human with a pulse can read it.

The cabinet itself is unchanged: Governor `GateReceipt v4.unsettled` remains the authority artifact, content-addressed, hash-bound. The packet is the display.
