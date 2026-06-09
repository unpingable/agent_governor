# Nightshift ↔ Governor Unsettled Integration — State of the Seam

**Filed:** 2026-06-09. **Purpose:** single-page index + summary so future-you can land cold without reconstructing five witness files. **Status:** consolidation only. No code; no doctrine expansion.

## TL;DR

```
GateReceipt v4 .unsettled field:                     built + tested (Python + Rust)
NonDischargeKind (closed enum, 6 kinds):             built (Python + Rust mirrors)
Nightshift → Governor seam (lower pipeline level):   witnessed
CLI reachability for receipt emission:               configured-only (flags required)
Default watchbill:                                   governor-blind by design (Option 3)
Horizon Defer → unsettled Freshness population:      built + witnessed end-to-end
Golden fixture v4 with non-empty unsettled:          checked in + asserted (8 tests)
Packet-side unsettled summary (operator-visible):    built + asserted in YAML (B1 landed)
Governor CLI text-mode rendering of unsettled:       NOT done; raw JSON dump only
WLP0 receiver-fit audit:                             verdict C — mvp_a is the receiver, ignores unsettled
WLP1 observational carry-forward (mvp_a payload):    built — ns_unsettled + governor_receipt_ids preserved
WLP2 refusal-design audit:                           verdict B1 — cook + skip wrap (NS-side); next slice scoped
WLP3 refuse warranty on freshness-unsettled:         built — cook+classify preserved; no AuthorizationReceipt minted
Other NonDischargeKind refusal rules:                NOT done; one kind at a time; each needs its own ratification
Other verdict kinds:                                 NOT populated yet (intentional)
Consumer of unsettled:                               operator reads packet; signal survives to Continuity
```

## Witness files (read order if landing cold)

1. [`nightshift-integration-sweater.md`](nightshift-integration-sweater.md) — the original integration map (component cut + edge tags). Has a CORRECTION on the Nightshift→Governor row reflecting the witness in #2.
2. [`witness-2026-06-09-gate-receipt-unsettled-gap.md`](witness-2026-06-09-gate-receipt-unsettled-gap.md) — captured the schema gap in 1,165 emitted receipts + sharpened the wiring gap. Contains the CORRECTION promoting the lower pipeline seam to `witnessed`.
3. [`witness-2026-06-09-cli-reachability-classification.md`](witness-2026-06-09-cli-reachability-classification.md) — verdict **C. Split** on CLI reachability. Documents Option 3 (preserve current boundary; do not widen default) + the link to unsettled population scope.
4. [`witness-2026-06-09-unsettled-population-horizon-defer.md`](witness-2026-06-09-unsettled-population-horizon-defer.md) — first stitch: Defer → Freshness claim. Both ends witnessed; 285 Rust + 441 Python tests green.
5. [`fixtures/witness-receipt-2026-06-09.json`](fixtures/witness-receipt-2026-06-09.json) — sample pre-v4 receipt artifact (motivating gap).

## 1. Receipt schema

- **Schema version:** `RECEIPT_SCHEMA_VERSION = 4` in `src/governor/gate_receipt.py`.
- **New field:** `GateReceipt.unsettled: tuple[NonDischargeClaim, ...]` (default `()`). v3 receipts still load and re-serialize without the field (byte-stable roundtrip).
- **Closed enum:** `VALID_NON_DISCHARGE_KINDS = {AUTHORITY, EVIDENCE_SUFFICIENCY, FRESHNESS, SCOPE, STANDING, CONSUMER_RELIANCE}`. Six values. Adding one requires ratification + a separate slice; freeform strings rejected at construction (`NonDischargeClaim.__post_init__`).
- **NonDischargeClaim shape:** `kind` (closed enum) + `reason` (freeform prose, *informational only*) + `required_consumer?` + `required_witness?` (both optional, repo-local strings).
- **Hash binding:** non-empty `unsettled` participates in `receipt_id` via `unsettled_hash` (mirrors the horizon pattern). Empty `unsettled` does not bind into the id.
- **Rust mirrors:** `nightshiftd/src/governor_client.rs` exports `NonDischargeKind` (closed enum, `#[serde(rename_all = "snake_case")]` matching Python wire values) and `NonDischargeClaim` (mirrored struct).

## 2. Reachable paths

**Receipt-emitting** (Governor's `record_receipt` fires):

```
watchbill --horizon-policy=X --governor-socket=Y <agenda> <finding>
  → capture_phase
  → reconcile_phase_with_horizon(Some(policy), Some(governor))
  → apply_horizon_outcomes  (on Defer)
  → governor.record_receipt(RecordReceiptRequest)
  → record_receipt(event, system)            # Python adapter
  → GateReceiptSystem.emit(unsettled=...)    # → v4 GateReceipt persisted
```

**Receipt-blind** (default; intentional per Option 3):

```
watchbill <agenda> <finding>                              # no flags
  → run_watchbill / run_watchbill_with_liveness
  → reconcile_phase  (always passes governor=None)
  → never reaches record_receipt
```

The split is documented in:
- `~/git/scheduler/README.md` quickstart step 6 (corrected this run)
- `--horizon-policy` / `--governor-socket` CLI help text
- The Authority model section of the README ("`observe` and `advise` may run without Governor")

## 3. Witnessed population

| Path | Populates `unsettled`? | Claim kind | Reason (informational) |
|---|---|---|---|
| Horizon-configured `Defer` outcome | **yes** | `Freshness` | *"defer outcome does not settle closure authority while horizon remains active"* |
| Horizon-configured `EscalateExpired` | no | — | — |
| Horizon-configured `EscalateBasisInvalidated` | no | — | — |
| Horizon-configured `ActOnVerdict` | no | — | — |
| `RenderNoIntervene` / `RenderHolding` | no | — | — |
| Default watchbill (any outcome) | unreachable | — | seam never crosses; see §2 |

## 4. Explicit non-claims

This integration **does NOT** claim or do any of the following. Each is a separate forcing case if/when surfaced; none should be assumed by default.

- **No Allow / Deny / Close / EscalationPaged / ActionVerified / AgendaPromoted population.** The five other `EventKind` variants emit `unsettled: ()` from Nightshift. Each would need its own justification of what *that* verdict leaves unsettled.
- **No default-CLI widening.** `run_watchbill` and `run_watchbill_with_liveness` do not take a `governor` parameter. The configured-only path is the only CLI route to `record_receipt` today.
- **No consumer semantics.** No programmatic caller reads `unsettled` and acts on it. The downstream consumer of "what did this verdict leave unsettled?" is the operator inspecting receipts. Adding a programmatic consumer is a separate slice with its own scope (likely involving who is allowed to clear vs. acknowledge an `unsettled` entry).
- **No new `NonDischargeKind` variants.** Closed at six. Adding one requires:
  1. New constant + `VALID_NON_DISCHARGE_KINDS` membership in `gate_receipt.py`.
  2. Mirror Rust enum variant in `governor_client.rs`.
  3. Forcing case in a witness note explaining the new verdict semantics.
  4. Test coverage for accept + roundtrip + reject-of-unknown.
- **No semantic widening of `unsettled`.** It means *"this specific Defer verdict did not close closure-authority while the horizon stays active."* It does NOT mean "everything this receipt didn't prove." That direction is infinite lint; refuse.
- **No fix for the pre-existing standing-validator bootstrap drift.** Unrelated; 14 ERRORs + 6 failures in `test_standing_validator.py` / `test_standing_schema.py` predate this work and remain to be fixed in a separate session.

## 5. Next admissible candidates (named, not opened)

Listed in suggested order. Pick the next one against forcing-case pressure; do not batch.

**A. ~~Golden fixture receipt with non-empty `unsettled`~~ — LANDED 2026-06-09.**
- Fixture at `tests/fixtures/golden_traces/receipt_v4_with_unsettled.json` (10 fields including schema_version=4, receipt_role=authority, horizon block with kind=hours, one Freshness unsettled claim).
- Emitted via the real `nightshift_adapter.record_receipt` path — no hand-crafted JSON. Re-generation discipline: emit-once-and-freeze.
- Asserted by `TestGoldenFixtureV4WithUnsettled` (8 tests): existence, parse, claim shape, receipt_role, horizon presence, content-addressed `receipt_id` recompute, `from_dict→to_dict` byte-stable roundtrip, non-vestigial unsettled binding.
- Wire shape now pinned across the cross-language seam.

**B. ~~Packet / ledger rendering exposes `unsettled` visibly~~ — B0 audit + B1 packet-side both LANDED 2026-06-09.**
- B0 (forcing-case audit, [`witness-2026-06-09-b0-rendering-audit.md`](witness-2026-06-09-b0-rendering-audit.md)): verdict **B. Receipt-linked but not visible.** Six surfaces enumerated; packet and Governor text-mode both lacked any unsettled rendering. Jurisdiction granted.
- B1 (packet-side, [`witness-2026-06-09-b1-packet-unsettled-summary.md`](witness-2026-06-09-b1-packet-unsettled-summary.md)): new `UnsettledSummary` struct + `Packet.unsettled` field; populated for Defer outcomes only; receipt_id binding preserved; YAML rendering asserted in extended packet-state test. Governor text-mode rendering deferred (not required for packet visibility close-out).
- Remaining B-family candidate (if needed): **B2 — Governor `receipts show <id>` text-mode rendering of `unsettled`.** Today it's `json.dumps(receipt.to_dict())` unconditionally; a `--format text` or default-text mode could render the unsettled list humanly. Forcing case: an audit workflow that doesn't have a packet on hand (e.g., post-hoc receipt inspection). Not opened.

**C. Populate another narrow horizon outcome.**
- Candidates: `EscalateExpired` could plausibly carry `Freshness` (the original tolerance expired); `EscalateBasisInvalidated` could carry `Authority` or `Standing` (the basis under which the tolerance was granted no longer holds). Neither is obvious without a forcing case.
- Discipline gate before opening: a concrete operator question of the form *"what did this Escalate decision NOT settle?"* that the operator cannot currently answer from the receipt.
- Risk: easy to populate plausibly-sounding kinds without honest justification. Refuse without forcing pressure.

**Not on this list** (deliberate omissions):
- Widening `run_watchbill_cmd` to construct a `JsonRpcGovernorClient` by default — covered by Option 3 / CLI reachability witness. Re-litigate only if a deployment forcing case appears.
- Adding programmatic receipt consumers — frontier marker per the sweater.
- Adding more `NonDischargeKind` variants — closed enum, ratification gate.
- Fixing standing-validator bootstrap drift — unrelated; separate session.

## Operating discipline reminder (verbatim from prior slices)

> Closed enum for machine-facing classification. Freeform prose only where prose cannot corrupt dispatch.

> If it doesn't fit the enum, don't improvise. Open a new ratification item.

> A gate receipt must distinguish what it permits from what it leaves unsettled.

> Default watchbill is governor-blind *and says so*.

> The closed enum is the load-bearing piece. Prose `reason` is informational.

## Provenance

Consolidation note filed 2026-06-09 after the first integration-result slice (Defer → Freshness population, witnessed both ends). Inputs:

- Five witness files listed above (read directly this pass).
- Test suites both ends still green: Rust `nightshiftd` 285, Python adapter + gate_receipt + daemon 441.
- No code changed this session; the quilt square has one stitch and now has its label.

The next code slice is candidate A (golden fixture). Open when ready. Not in this session.
