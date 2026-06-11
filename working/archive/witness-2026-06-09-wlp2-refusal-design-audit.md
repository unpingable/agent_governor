# Witness: WLP2 — Refusal-Design Audit for `ns_unsettled.kind == freshness`

**Filed:** 2026-06-09. **Scope:** classification + minimal next-slice spec. No code. No WLP/Wicket crate changes. No new receipt type unless already present.

## Verdict

**B. Cook but refuse to wrap.** Variant **B1: skip the WLP wrap entirely on the NS side.**

NS still cooks the Wicket Intent and persists the Wicket Outcome (the classification itself is sound). NS does **not** invoke `wrap_authorization` and does **not** invoke `wlp::handle`. No WLP `AuthorizationReceipt` and no WLP `HandlingReceipt` are minted for this run. A new NS-side refusal artifact carries the Wicket Outcome reference + the `ns_unsettled` content + the reason code.

The doctrinal claim:

> A packet carrying `ns_unsettled[*].kind == freshness` may be cooked into a Wicket Intent — the classification surface is honest — but must not be wrapped as a WLP `AuthorizationReceipt`. WLP `AuthorizationReceipt` is the warranty for downstream reliance, and reliance is not warranted while a freshness condition remains unsettled.

## Why not A or C

### Why not A (refuse to cook)

A is the precedent the existing `ns.refusal.v1` path uses for *upstream data structurally unsuitable for translation* (e.g., unverified NQ receipt, per `evaluate_basis_admissibility`). It refuses BEFORE Wicket sees anything; no Intent, no Outcome.

Freshness-unsettled is a different shape. NS+Wicket *can* classify the packet correctly. The packet says exactly what it says; the question is whether *reliance* on the classification is warranted while the freshness window remains open. Routing freshness-unsettled through A would hide Wicket's classification, which is structurally honest. Worse, it would collapse two semantically distinct refusal kinds:

- "I cannot translate this" (upstream data unsuitable)
- "I can translate this, but I refuse to warrant downstream reliance" (this case)

### Why not C (wrap with conditioned/deferred status)

`wlp::HandlingVerdict` is a closed enum: `Accepted | Refused | Expired | Unsupported`. **No "Conditioned" variant exists.** Adding one would be a WLP crate change, which the slice's `no WLP/Wicket crate changes` constraint forbids. C also requires propagating "conditioned" semantics through Continuity persistence + downstream consumers, which is a wider blast radius than the slice authorizes.

### Why B1 over B2

B2 would mean "call `wlp::handle` and let WLP decide to refuse." Inspection of WLP confirms this is not currently reachable from NS:

- `wlp::HandleOpts` (`~/git/wlp/src/validate.rs:25-32`) exposes only `consumer`, `reference_time`, `supported_policy_schemes`. There is **no flag or hook by which NS can instruct WLP to return `Refused` for a parent it would otherwise `Accept`**.
- WLP's `decide(parent, opts)` makes its verdict from the parent artifact's own admissibility + context revocations. It does not inspect `ns_unsettled` because that field is in `transition.payload`, which `decide` doesn't enter.

So B2 requires WLP changes. B1 does not.

**Net:** WLP itself stays untouched. The refusal-of-reliance lives at the NS side as "I did not mint a warranty for this run."

## Existing precedent NS already provides

`~/git/scheduler/crates/nightshiftd/src/mvp_a.rs`:

- `pub enum MvpAResult { Cooked(MvpAOutcome), Refused(MvpARefusal) }` already exists.
- `write_refusal_artifact(...)` emits a `ns.refusal.v1` JSON artifact with a `reason_code` parameter.
- The dispatch site (line ~675) calls `evaluate_basis_admissibility(nq_receipt)` and routes to `Refused` when the upstream data is unsuitable.
- Comment at the dispatch site is explicit: *"No Wicket Intent / Outcome / WLP artifacts are produced on this branch"* — which is the A-pattern semantic.

The B1 path needs a *different* dispatch site (after the Wicket Outcome is produced, before `wrap_authorization`) and a *different* artifact shape (one that carries the Wicket Outcome reference, not just NQ context).

## Minimal next code slice

**Name:** WLP3 — refuse to mint WLP AuthorizationReceipt when `ns_unsettled` contains `freshness`.

**Scope:** `scheduler/crates/nightshiftd/src/mvp_a.rs` only. No WLP, no Wicket, no Continuity crate changes.

**Edits required:**

1. New `MvpAResult` variant or extension of existing dispatch. Recommended shape:
   ```rust
   pub enum MvpAResult {
       Cooked(MvpAOutcome),
       Refused(MvpARefusal),                          // existing (refuse-to-cook)
       WlpAuthorizationRefused(WlpAuthorizationRefusal), // new
   }

   pub struct WlpAuthorizationRefusal {
       pub posture_packet_path: PathBuf,
       pub wicket_intent_path: PathBuf,
       pub wicket_outcome_path: PathBuf,
       pub refusal_artifact_path: PathBuf,  // ns.wlp_refusal.v1
       pub reason_code: String,
       pub unsettled_kinds: Vec<NonDischargeKind>, // which kinds triggered
       pub governor_receipt_ids: Vec<String>,
   }
   ```
2. New artifact schema `ns.wlp_refusal.v1` distinct from `ns.refusal.v1`. Fields:
   - `schema: "ns.wlp_refusal.v1"`
   - `reason_code: "WLP_AUTHORIZATION_REFUSED_<unsettled_kind>_UNSETTLED"` (closed reason vocabulary)
   - `refused_at`, `agenda_id`, `finding_key`, `run_id` (parallels `ns.refusal.v1`)
   - `wicket_outcome_ref` — the input_hash of the Wicket Outcome that NS did classify successfully (chain still walkable to the Wicket side)
   - `ns_unsettled: Vec<UnsettledSummary>` — full copy (kind + reason + receipt_id per entry)
   - `governor_receipt_ids: Vec<String>` — the source Governor receipts
3. New dispatch site in `run_pipeline`: after `wicket::check` returns Outcome and after Outcome is persisted, but BEFORE `wrap_authorization`. Inspect `packet.unsettled` for any entry with `kind == NonDischargeKind::Freshness`. If found:
   - Emit `ns.wlp_refusal.v1` artifact
   - Skip `wrap_authorization` and `wlp::handle`
   - Return `MvpAResult::WlpAuthorizationRefused`
4. Closed reason-code vocabulary should match the closed `NonDischargeKind` enum — six possible codes for the six unsettled kinds. Initial slice covers Freshness only; the other five are named-not-built per the prior population slice's discipline.

**Acceptance criteria:**

1. ✅ A packet with `ns_unsettled` containing a `freshness` claim produces a Wicket Intent on disk and a Wicket Outcome on disk (cook + classify happened).
2. ✅ Same packet produces **no WLP `AuthorizationReceipt` artifact** and **no WLP `HandlingReceipt` artifact**.
3. ✅ Same packet produces a `ns.wlp_refusal.v1` artifact that carries:
   - the Wicket Outcome reference (chain to Wicket side preserved)
   - `ns_unsettled` content (kind, reason, receipt_id per entry)
   - `governor_receipt_ids` (binding to Governor receipts)
   - `reason_code = WLP_AUTHORIZATION_REFUSED_FRESHNESS_UNSETTLED`
4. ✅ Empty `packet.unsettled` produces no WLP-refusal artifact (existing happy path unchanged; `MvpAResult::Cooked` returned).
5. ✅ Non-freshness `ns_unsettled` kinds do NOT trigger refusal yet (initial slice scope; one kind at a time).
6. ✅ Existing pipeline tests still pass for the happy path.
7. ✅ Existing refuse-to-cook precedent (`ns.refusal.v1`) is unchanged.
8. ✅ Continuity adapter is unchanged (no WLP artifact to persist → Continuity sees nothing for this run; correct behavior).
9. ✅ One new test asserts the cook-yes / wrap-no / refusal-artifact-shape semantic.

**Hard fence:** the receiver-side gate refuses to mint a warranty. It does NOT delete, hide, or contradict the upstream Governor receipt or the Nightshift packet. Both still exist on disk. The refusal is "I will not stake my name on this" — not "this never happened."

## Design tensions surfaced (not resolved in this audit)

1. **Should the refusal artifact include the Wicket Outcome content inline, or only a reference?** Inline is heavier but self-contained for audit. Reference matches the chain-walkable pattern of the existing `wlp_handling.causal_parents[0]` shape. Recommendation: reference, matching the existing chain discipline.

2. **What happens if NS later wants to retry?** A new run with the same finding could produce a fresh receipt; the unsettled signal would or wouldn't be present based on whether the horizon resolved. No state migration is needed — each run is independent. But: the refusal artifact's existence may be a useful audit signal for "this finding has been refused at the WLP boundary before"; downstream tooling could surface that, *future slice*.

3. **Should NS log the refusal as a `RunHorizonOutcome` ledger event variant?** The existing `RunHorizonOutcome` event tracks Defer outcomes from `reconcile_phase_with_horizon`. The WLP-refusal happens later, in `run_pipeline`. Probably a separate ledger event kind (`RunWlpAuthorizationRefused`?), but this audit doesn't open it; the next slice author should decide.

4. **What about the other five `NonDischargeKind` variants?** This slice covers Freshness only because that's the only kind populated today. If/when Authority / EvidenceSufficiency / Scope / Standing / ConsumerReliance are populated (future slices), each will need its own decision: refuse-to-wrap, or some weaker treatment? Don't generalize prematurely.

## What this audit did NOT do

- **Did not** write any code.
- **Did not** modify any test.
- **Did not** open the WLP3 slice; only spec'd it.
- **Did not** decide between inline-Wicket-Outcome vs reference (tension #1).
- **Did not** decide the ledger-event shape for the WLP refusal (tension #3).
- **Did not** generalize the refusal pattern to other `NonDischargeKind` variants.
- **Did not** inspect Continuity's adapter under "no AuthorizationReceipt" — assumed correct based on its existing "consume AuthorizationReceipt, skip if absent" pattern; future slice author should verify.
- **Did not** widen any enum.
- **Did not** touch WLP, Wicket, or Continuity crates.
- **Did not** fix standing-validator bootstrap drift.

## Provenance

Filed 2026-06-09 after WLP1 landed (`ns_unsettled` preserved into `transition.payload`). Direct reads this pass:

- `~/git/scheduler/crates/nightshiftd/src/mvp_a.rs:195-242` (`MvpAResult`, `MvpAOutcome`, `MvpARefusal` shapes)
- `~/git/scheduler/crates/nightshiftd/src/mvp_a.rs:592-620` (`write_refusal_artifact` + `ns.refusal.v1` schema)
- `~/git/scheduler/crates/nightshiftd/src/mvp_a.rs:670-695` (existing refuse-to-cook dispatch site)
- `~/git/wlp/src/validate.rs:25-55` (`HandleOpts` shape + `handle` body)
- `~/git/wlp/WLP_RECEIVER_GATE_CANDIDATE.md` (carried forward from WLP0 audit)

No code changed. No tests added. The WLP3 slice is named, scoped, and ready to open when the next operator pulls the thread. Verdict B (refuse to wrap) is the right teeth-bearing minimum; B1 (skip wrap entirely, NS-side) is the minimum-blast-radius implementation path.
