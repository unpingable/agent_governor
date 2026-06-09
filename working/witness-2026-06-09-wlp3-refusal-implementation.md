# Witness: WLP3 — Refuse WLP Warranty on Freshness-Unsettled

**Filed:** 2026-06-09. **Scope:** B1 implementation of the WLP2-spec refusal. `mvp_a.rs` only (plus the test surface and a CLI render arm). No WLP/Wicket/Continuity crate changes. One ratified refusal kind: `Freshness`.

## The first refusal with teeth

A packet whose `unsettled` carries a `Freshness` claim now:

- **Still cooks** into a Wicket Intent.
- **Still classifies** through `wicket::check` (Outcome on disk).
- **Does NOT mint** a WLP `AuthorizationReceipt`.
- **Does NOT mint** a WLP `HandlingReceipt`.
- **Emits** a `ns.wlp_refusal.v1` artifact carrying the closed reason code, the triggering kinds, the source Governor receipt ids, and references to the Wicket Intent + Outcome artifacts.

The chain remains walkable to the Wicket side. The WLP warranty is intentionally absent. *"I will not stake my name on this"* — not *"this never happened."*

## Edits

### Rust (`~/git/scheduler/crates/nightshiftd/src/mvp_a.rs`)

- New `WlpAuthorizationRefused(WlpAuthorizationRefusal)` variant on `MvpAResult`.
- New `WlpAuthorizationRefusal` struct: posture/intent/outcome/refusal paths, reason_code, `unsettled_kinds: Vec<NonDischargeKind>`, `governor_receipt_ids: Vec<String>`.
- New closed-vocabulary constant `WLP_AUTHORIZATION_REFUSED_FRESHNESS_UNSETTLED`.
- New helper `wlp3_refusal_triggering_kinds(packet)` — closed-vocabulary filter for ratified refusal kinds (currently Freshness only). **The doc comment on this function is the structural defense against laundering this into a non-empty check.**
- New `write_wlp_refusal_artifact` — emits `ns.wlp_refusal.v1` (distinct schema from `ns.refusal.v1`). References (not inlines) the Wicket Intent and Outcome paths; carries the full `ns_unsettled` summary list and reason code.
- New dispatch site in `run_pipeline` between `wicket::check` and `wrap_authorization`. If `wlp3_refusal_triggering_kinds(packet)` is non-empty, write the refusal artifact, skip `wrap_authorization` + `wlp::handle`, return `MvpAResult::WlpAuthorizationRefused(...)`.
- New `SinkPaths.wlp_refusal: PathBuf` (`ns-wlp-refusal-{run_id}.json`).

### Rust (`~/git/scheduler/crates/nightshiftd/src/main.rs`)

- CLI render arm for the new variant. Prints refusal artifact path, reason code, kinds, Wicket paths, and Governor receipt ids. Doc comment makes the boundary explicit: classification preserved, warranty absent.

### Tests

- **`wlp3_freshness_unsettled_refuses_authorization_but_preserves_wicket_chain`** (new) — Builds a packet with `unsettled[Freshness]`; runs `run_pipeline`; asserts:
  - Variant is `WlpAuthorizationRefused` (not `Cooked`, not A.5 `Refused`).
  - `reason_code == WLP_AUTHORIZATION_REFUSED_FRESHNESS_UNSETTLED`.
  - `unsettled_kinds == vec![Freshness]`.
  - `governor_receipt_ids == vec![<the receipt id>]`.
  - Wicket Intent + Outcome files exist on disk.
  - WLP AuthorizationReceipt + HandlingReceipt files do NOT exist on disk.
  - Refusal artifact has `schema == "ns.wlp_refusal.v1"`, correct reason code, `unsettled_kinds: ["freshness"]`, full `ns_unsettled` summary including verbatim reason prose.
- **`wlp3_non_freshness_unsettled_does_not_refuse`** (new) — Builds a packet with `unsettled[Authority]`; asserts result is `Cooked`, NOT `WlpAuthorizationRefused`. The trap-avoidance regression: if anyone "simplifies" `wlp3_refusal_triggering_kinds` to a non-empty check, this test fails.
- **`wlp1_observational_carry_forward_preserves_unsettled_and_receipts`** (updated) — Switched from `Freshness` to `Authority` to avoid colliding with WLP3 refusal. The WLP1 preservation invariant now asserts on a non-ratified-for-refusal kind, which is honest: WLP1 carry-forward holds for any kind that hasn't yet earned WLP3 teeth.
- **`wlp1_empty_unsettled_emits_empty_array_not_missing_field`** (added arm) — Match arm panics on unexpected `WlpAuthorizationRefused`; otherwise unchanged.
- All other existing match sites (`mvp_a_pipeline_produces_walkable_hash_chain_against_sushi_k_receipt`, `ns_refuses_to_cook_not_verified_receipt_and_writes_refusal_artifact` and its re-run case) updated with panicking `WlpAuthorizationRefused(_)` arms. Each carries an explicit error message distinguishing A.5 vs WLP3 paths.

## Test results

- `cargo test -p nightshiftd`: 285 tests across all bins, all green (was 283; +2 from new WLP3 tests)
- `mvp_a_pipeline.rs`: 5 passed (1 existing happy path + 2 WLP1 + 2 WLP3)
- `mvp_a_refusal.rs`: 1 passed
- All other suites unchanged

## Acceptance criteria mapping

1. ✅ Packet with unsettled freshness still cooks through Wicket — Intent + Outcome files asserted present.
2. ✅ Wicket Intent/Outcome artifacts still exist — explicit `.exists()` assertions on both paths.
3. ✅ No WLP AuthorizationReceipt is minted — explicit `!path.exists()` assertion on both AuthorizationReceipt and HandlingReceipt files.
4. ✅ New `ns.wlp_refusal.v1` artifact emitted — schema string asserted byte-for-byte.
5. ✅ Result variant is `WlpAuthorizationRefused` — `match` arm gates the test.
6. ✅ Refusal includes freshness reason code, unsettled kinds, governor receipt IDs — all three asserted on both the in-memory struct and the on-disk artifact.
7. ✅ Baseline packet with empty unsettled still produces normal WLP AuthorizationReceipt — existing happy-path test still passes; `wlp1_empty_unsettled_emits_empty_array_not_missing_field` confirms the empty path still cooks + wraps.
8. ✅ No WLP/Wicket/Continuity crate changes — zero edits outside `~/git/scheduler/crates/nightshiftd/`.
9. ✅ No behavior for other `NonDischargeKind` values yet — `wlp3_non_freshness_unsettled_does_not_refuse` enforces this; the `wlp3_refusal_triggering_kinds` helper filters explicitly on `Freshness`.

## The trap that almost was

The user named the trap explicitly in the slice spec:

> Do not make this: `if packet.unsettled is non-empty, refuse`
> Make it: `if any kind == freshness, refuse`

This is enforced at three places:

1. The `wlp3_refusal_triggering_kinds` helper itself uses `matches!(s.kind, NonDischargeKind::Freshness)`, not `!packet.unsettled.is_empty()`.
2. The doc comment on `wlp3_refusal_triggering_kinds` calls out the laundering move by name: *"Do NOT replace this with a `!packet.unsettled.is_empty()` catch-all; that would be the laundering move WLP3 exists to refuse."*
3. The `wlp3_non_freshness_unsettled_does_not_refuse` test exercises the negative case directly: an `Authority`-only unsettled packet must `Cooked`, not refuse. A future "simplification" that broadens the check fails this test loudly.

## What this slice did NOT do

- **Did not** populate any other `NonDischargeKind` for refusal. Five kinds remain carried-but-not-adjudicated.
- **Did not** modify WLP, Wicket, or Continuity crates.
- **Did not** add a `RunWlpAuthorizationRefused` ledger event kind. Future slice; the WLP2 design audit named this as design tension #3.
- **Did not** widen the `NonDischargeKind` enum.
- **Did not** regenerate Continuity fixtures. The Continuity adapter consumes `AuthorizationReceipt` artifacts; when this path runs, none is emitted, so the adapter has nothing to persist for that run. Correct behavior.
- **Did not** fix the pre-existing standing-validator bootstrap drift.

## Provenance

Filed 2026-06-09 after the WLP2 audit named the variant as **B1** (skip WLP wrap entirely on the NS side). The slice landed exactly within the WLP2 spec: new variant, new schema, new dispatch site, new reason code constant, two new focused tests, panic-arms for the unexpected paths in other tests.

The gerbil has its first bite. Small, documented, hard to launder into "everything unsettled is forbidden." Future ratifications of other kinds require their own slices — same scope, same spec shape, different one-line check.
