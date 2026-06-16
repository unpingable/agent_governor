# Candidate: Nightshift-local Conversion Route Checker (`ns.claim_route.v1`)

**Filed:** 2026-06-09. **Status:** candidate / parked. Not opened. Forcing case **exists** (WLP3 freshness-unsettled refusal); scope is intentionally Nightshift-local until runtime pressure proves it deserves to escape containment.

## The reframe (the load-bearing move)

Earlier framing: *park graph-checker work until a forcing consumer exists.*

New framing, with WLP3 landed:

> **Forcing consumer exists; scope it as Nightshift's conversion gate, not a general language.**

Nightshift already needs to answer questions of the form *"does this NQ thing convert to that WLP/Continuity thing under these receipts, or does it block?"* The dangerous conversions are exactly the ones a small typed graph checker is good at refusing. The same shape that refuses *"language ⇏ authority"* refuses these.

## Dangerous conversions Nightshift already cares about

(Pulled verbatim from the parking conversation. Each one is a real conversion seam Nightshift sees today.)

- `receipt present` ⇏ `authority`
- `witnessed` ⇏ `admissible`
- `authorized` ⇏ `safe`
- `freshness unresolved` ⇏ `authorization` ← *currently enforced by WLP3; serves as proof the family exists*
- `Wicket outcome exists` ⇏ `WLP authorization exists` ← *also enforced by WLP3*
- `refusal propagated` ⇏ `mandamus obligation`, unless locus bridge exists

The bottom two are exactly what WLP3 just shipped. That's the forcing-case evidence: the corpus already has at least one refusal that, structurally, *is* a missing-bridge claim. A `claim_route` checker is the generalization of that move under a closed inventory.

## Scope discipline (the boring-on-purpose part)

What this is NOT:

- Not generic Cedar-like infrastructure.
- Not a public-facing surface.
- Not a new ontology repo.
- Not a competitor to Wicket or WLP — those are receipt-emitting; this is route-classifying.
- Not load-bearing for any current operator workflow until proven so by runtime pressure.

What it IS:

- A Nightshift-local typed-graph preflight: given a `from`/`to` pair plus current receipts, return one of three verdicts and (if applicable) the missing bridge.
- Seeded with 5–10 surfaces from the existing Path A / A.5 flow, not the universe.
- A receipt-emitter when a route is `blocked`, so the operator sees a structural reason, not just a missing artifact.

## Sketched shapes (preserve verbatim — these are the user's working spec)

### Query

```json
{
  "from": "nq.finding.disk_state",
  "to": "nightshift.closure_candidate",
  "receipts": [
    "nq.sql_contract.public_views.v1",
    "nq.binary_mtime_state.v1",
    "ns.wlp_refusal.v1"
  ],
  "context": {
    "host": "lil-nas-x",
    "claim_kind": "disk_state"
  }
}
```

### Verdicts

**`path`** — a route exists in the current inventory; the certificate enumerates the surface-by-surface walk.

```json
{
  "verdict": "path",
  "path": ["nq.finding", "witnessed", "admissible_with_scope", "closure_candidate"],
  "receipts_used": ["..."]
}
```

**`blocked`** — no route in the current inventory; the certificate enumerates the partial walk reached, the missing bridge, and the refusal receipt that records the structural cut.

```json
{
  "verdict": "blocked",
  "cut": "freshness_unsettled_blocks_wlp_authorization",
  "certificate": ["witnessed", "wicket_intent", "wicket_outcome"],
  "missing_bridge": "freshness_to_wlp_authorization",
  "refusal_receipt": "ns.wlp_refusal.v1"
}
```

**`open`** — neither a route nor a registered cut. No claim made about reachability *in the world*, only about reachability *in this inventory*. Important: this verdict is the honest "I don't know" that prevents the checker from over-claiming.

```json
{
  "verdict": "open",
  "missing_bridge": "standing_to_mutate",
  "note": "no theorem-backed edge or cut registered"
}
```

### Receipt artifact (when blocked)

```text
ns.claim_route.v1
```

Fields:

```json
{
  "artifact_kind": "ns.claim_route.v1",
  "from_surface": "...",
  "to_surface": "...",
  "verdict": "path|blocked|open",
  "edge_receipts": [],
  "cut_receipts": [],
  "missing_bridge": null,
  "closed_set_certificate": [],
  "source_receipt_ids": [],
  "tree_or_build_id": "..."
}
```

## Concrete next move (when opened — NOT now)

1. **Do not build generic Cedar-like infrastructure.** Repeat: do not.
2. Build a tiny Nightshift-local conversion-route schema.
3. Seed it with only 5–10 surfaces from Path A / A.5.
4. Add the checker:
   - path certificate
   - blocked certificate
   - open/missing bridge
5. Emit `ns.claim_route.v1` from Nightshift when a route is blocked.

## Lean side (also small)

Four proof targets, total:

1. Closed-set certificate soundness.
2. Path certificate soundness.
3. Bridge-addition monotonicity (adding bridges may turn `blocked` into `path` but cannot turn `path` into `blocked`).
4. Optional: *blocked means no route in this inventory*, NOT *no route in reality*. This is the honesty-of-scope theorem; matches the existing corpus discipline.

## Why this is filed and not opened

The WLP3 work just landed. The pattern of *"refuse to mint a warranty when a structural bridge is missing"* is exactly one instance of what a `claim_route` checker generalizes. But:

- One instance does not yet justify a subsystem.
- The next semantic-population slice (other `NonDischargeKind` variants) will surface the second and third instances.
- Generalizing now would be premature.

Open this when **at least two more refusal-shapes** in the family have landed (e.g., `Authority`-unsettled or `Standing`-unsettled refusal rules), so the checker has more than a one-edge inventory to seed against. Until then, WLP3 alone is doing the work for the one bridge that matters today.

## Anti-pattern fences

If/when opened, the following are explicit non-goals:

- **No "language" or "ontology" framing.** The user already named the failure mode: state-space-atlas-not-machine (per the global tripwire in MEMORY.md). This is a checker, not a generator.
- **No external schema authority.** `ns.claim_route.v1` is repo-local. The schema lives next to the Nightshift consumer that emits it; the Lean side proves soundness, not ratifies the schema's right to exist.
- **No "promote to constellation" move.** The escape-from-containment criterion is *runtime pressure*, not *intellectual coherence*. Other repos may consume the receipt artifact; they may NOT take on the schema definition.
- **No general non-discharge graph.** Edges and cuts are populated from receipts that already exist in the Nightshift/Governor/WLP/Continuity chain. Adding speculative edges with no receipt is the laundering move.

## Keeper

> **Nightshift-local until runtime pressure proves it deserves to escape containment.**

That's the operating motto for this candidate. If it stays local forever, the project is healthier for the containment. If it earns escape, it earns it the same way WLP3 did: one bridge at a time, each one with a receipt and a forcing case.

## Cross-references

- WLP3 implementation: [`witness-2026-06-09-wlp3-refusal-implementation.md`](witness-2026-06-09-wlp3-refusal-implementation.md) — the existing instance of *"refuse warranty when structural bridge is missing"*.
- WLP3 closure inventory: [`wlp3-closure-and-artifact-inventory.md`](wlp3-closure-and-artifact-inventory.md) — the full path that `claim_route` would generalize.
- Integration state index: [`nightshift-governor-unsettled-integration-state.md`](nightshift-governor-unsettled-integration-state.md) — TL;DR + deferred candidates list (entry pointer to this file added there).
- Failure mode register (state_space_atlas_not_machine): MEMORY.md tripwire. Cited here as the *don't generalize prematurely* fence.

## Provenance

Filed 2026-06-09 immediately after the agent_gov + scheduler commits that landed the WLP3 refusal chain. Parked, not opened. The forcing case exists; the scope discipline requires waiting for a second instance before generalizing.
