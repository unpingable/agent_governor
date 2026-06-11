# Witness: WLP1 — Observational Carry-Forward of `unsettled` into MVP-A Payload

**Filed:** 2026-06-09. **Scope:** observational preservation only. No admission rule, no refusal, no WLP/Wicket crate changes. Follows the WLP0 receiver-fit audit (verdict C — receiver consumes packet but ignores `unsettled`).

## What landed

The MVP-A path now preserves `packet.unsettled` and `packet.receipt_references.governor_receipts` into the WLP `AuthorizationReceipt`'s `transition.payload`. Downstream consumers (Continuity persistence; future receiver-side gates) now have custody of the non-discharge signal NS surfaced on the packet.

Concretely, the wrapped artifact now carries:

```json
{
  "transition": {
    "payload": {
      "...": "...",
      "ns_unsettled": [
        {
          "kind": "freshness",
          "reason": "defer outcome does not settle closure authority while horizon remains active",
          "receipt_id": "fixture_receipt_freshness_001"
        }
      ],
      "governor_receipt_ids": ["fixture_receipt_freshness_001"]
    }
  }
}
```

## Invariant (verbatim from `mvp_a.rs` source comment)

> **Forwarding is preservation, not adjudication.** Carrying `ns_unsettled` does NOT accept the unsettled claim, does NOT reject it, and does NOT imply automatic refusal of the AuthorizationReceipt. It records that the upstream Defer verdict explicitly did not settle these conditions, so a downstream receiver can decide what reliance is appropriate.
>
> Future gremlins will try to treat this as decorative metadata or as an automatic denial. Both wrong. Equal-opportunity wrongness. Don't.

The invariant lives inline at the only populate site so a future reader cannot miss it.

## Edits

### Rust (`~/git/scheduler/crates/nightshiftd/src/mvp_a.rs`)

- `wrap_authorization` payload extended with two fields:
  - `"ns_unsettled": packet.unsettled` — serializes the `Vec<UnsettledSummary>` directly via serde-derived `Serialize`. Each summary's `kind` enum serializes as `snake_case` ("freshness"), matching the Governor wire form and the Python `VALID_NON_DISCHARGE_KINDS` values.
  - `"governor_receipt_ids": packet.receipt_references.governor_receipts` — pass-through of the existing receipt-id list.
- Both fields are **always emitted** (even when empty). Empty array = positive claim *"no unsettled claims surfaced"*, NOT silence. Mirrors the v4 GateReceipt schema's same discipline.
- Inline invariant comment block (quoted above) sits immediately before the payload construction.

### Tests (`~/git/scheduler/crates/nightshiftd/tests/mvp_a_pipeline.rs`)

Two new tests added under the existing pipeline test:

1. `wlp1_observational_carry_forward_preserves_unsettled_and_receipts` — Builds a `sushi_k_packet` with one `UnsettledSummary { kind: Freshness, reason, receipt_id }` populated; runs `run_pipeline`; reads the AuthorizationReceipt artifact from disk; asserts:
   - `payload["ns_unsettled"]` is a 1-element array
   - `[0]["kind"]` == `"freshness"`
   - `[0]["reason"]` contains the prose verbatim
   - `[0]["receipt_id"]` equals the source receipt_id
   - `payload["governor_receipt_ids"]` is `[receipt_id]`

2. `wlp1_empty_unsettled_emits_empty_array_not_missing_field` — Baseline packet (no unsettled). Asserts `ns_unsettled` and `governor_receipt_ids` are present as empty arrays, not absent. Preserves "missing != zero" discipline.

Both pass on first invocation. Existing tests (`mvp_a_pipeline_produces_walkable_hash_chain_against_sushi_k_receipt`, `ns_refuses_to_cook_not_verified_receipt_and_writes_refusal_artifact`) still pass — adding payload fields changes the artifact hash but does not change the chain shape.

## Test results

- `cargo test -p nightshiftd`: 283 tests across all bins, all green (was 281; +2 from new WLP1 tests)
- `mvp_a_pipeline.rs`: 3 passed (1 existing + 2 new)
- `mvp_a_refusal.rs`: 1 passed
- `horizon_packet_state.rs` / `horizon_cross_run.rs`: unaffected, still green

## Acceptance criteria

1. ✅ Existing MVP-A cook/wrap path includes `ns_unsettled` when `packet.unsettled` is non-empty
2. ✅ Includes `governor_receipt_ids` AND preserves each summary's `receipt_id` within the summary itself
3. ✅ Existing packets with no unsettled emit empty array intentionally (not absent field)
4. ✅ No Continuity fixture/sample updates — that path is downstream and re-runs would regenerate the live MVP-A run artifact; this slice is upstream of that regeneration
5. ✅ No refusal
6. ✅ No WLP AuthorizationReceipt suppression
7. ✅ No WLP/Wicket crate changes (zero edits outside `scheduler/`)
8. ✅ Test proves `transition.payload` preserves kind=freshness, reason, receipt_id

## What this slice did NOT do

- **Did not** refuse to cook on `unsettled.contains(freshness)`. That's effect 1 from the WLP0 candidate list; governed; deferred until the preservation witness exists (it now does).
- **Did not** refuse to wrap. Effect 3; same deferral.
- **Did not** add admission policy or quarantine behavior.
- **Did not** edit WLP, Wicket, or Continuity crates.
- **Did not** widen `NonDischargeKind`.
- **Did not** add semantic widening of `unsettled`.
- **Did not** regenerate `~/git/continuity/tests/fixtures/ns_wlp_*_sample.json` — those are 2026-05-28 frozen artifacts; if/when re-run, they'll naturally carry the new fields. The continuity adapter parses generic JSON, so absence-of-the-new-field in the frozen samples doesn't break compatibility; presence of the new field in future MVP-A runs is also forward-compatible at the adapter level.

## Why this comes before refusal

Per the user's framing of this slice:

> Effect 1 or 3 is stronger, but it changes admission behavior. That's a governed effect. Do it after the preservation witness exists.

The non-discharge signal now survives the receiver boundary. *Now* the policy question is legitimate:

> Should `ns_unsettled[freshness]` prevent WLP authorization, or merely mark it as conditioned/deferred?

Whoever opens that next slice has a corpse to adjudicate against. Without this slice, the policy would have been *"adjudicating a corpse it helped bury"* (verbatim from the user).

## Provenance

Filed 2026-06-09 after the WLP0 receiver-fit audit confirmed verdict C. One stitch in `mvp_a.rs`. The receiver still doesn't *act* on `unsettled`, but it has been promoted from *"walks past it whistling"* to *"preserves it in transition.payload for downstream custody."* The signal now survives the cook/wrap boundary; the future refusal rule will have something real to refuse against.
