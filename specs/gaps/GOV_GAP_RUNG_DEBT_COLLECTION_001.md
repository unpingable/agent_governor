# GOV_GAP_RUNG_DEBT_COLLECTION_001

## Title

Non-launderable deferral, classification, and seam-handoff — wire AG's existing
parts so a finding's *jurisdiction*, a debt's *collection*, and a parked
obligation's *carry* are each witnessed by an authority that is not the thing
being cleared.

## Status

**Wirings 1–2 LANDED 2026-06-13 (P3.0 `activation_preflight.py` + P3.0b
`debt_ledger.py`, consumed by P3.1 `activation.py`); collector-binding at the
discharge→activation edge remains future (see
`GOV_GAP_DISCHARGE_COLLECTOR_BINDING_001`).** Output of the 2026-06-13 recursive
design pass (ChatGPT/Claude critique + grep against the tree + operator
synthesis). The grep scorecard below is the load-bearing finding: AG already has
the mechanisms under its own vocabulary; this gap is
**two wirings + three refinements**, not new machinery. Parent doctrine:
GOV_GAP_PLAN_DECOMPOSITION_PROTOCOL_001 (the kernel); loop §11.2/§11.3 (rungs +
rung-scoped findings).

## The conservation theorem (the spine of this gap)

> **The authority that clears X cannot be X.**

Same No-Negative-Clearance theorem in three jurisdictions, federated (three
checks at three seams, not one universal check):

```
finding classification:  the rung cannot classify its own validator finding
                          as safe-to-continue
debt collection:          the gated rung cannot discharge the debt that gates
                          its own activation
handoff:                  the component that parks a debt cannot be the only
                          component claiming it arrived
```

Doctrine lines:
> Named is not collected. Carried is not collected either.
> Recomposition detects unaccounted boundaries; rung activation refuses
> uncollected obligations — and the handoff between them is where a
> named-and-carried obligation can still slip if nothing accounts the carry.

## Grep scorecard — what AG already has (2026-06-13, verified against the tree)

Thin concepts vs thick: `rung` (9 files), `future-rung` (1), `scope-expand` (1)
are the *framing* that hasn't landed; but `chain` (167), `classif` (182),
`fuse` (93), `ratif` (80), `seam` (53), `debt` (40) are everywhere. The
mechanisms mostly exist:

- **Seam-admissibility = `GOV_GAP_RECOMPOSITION_RECEIPT_001`** (specced 2026-06-12).
  `account_boundaries` is total: any unaccounted admitted boundary forces
  `refused_laundering`. "All slices passed must not imply the whole is
  admissible" is already doctrine. The earlier "carry-forward vs assert-intact"
  open question was a false dichotomy — totality does both; `parked` is the carry
  disposition.
- **Two-order split exists**: chain gate (shipped v2.5.0) = action-level
  composition; recomposition receipt = slice-level. Order-0 (chain-eligibility,
  per-slice) vs order-1 (seam-admissibility, per-join).
- **Classification jurisdiction = loop §11.2/§11.3** (ratified 2026-06-13):
  rung-scoped findings, venue split, builder/validator agreement settles,
  disagreement halts, scope-expanding remedy → operator. The P2.1 three-venue
  worked example is in §11.3.
- **`independence_class` on `EvidenceRef`** already types evidence by provenance
  (self / tool / peer / operator); `self` = "evidence produced by the same agent
  making the claim." The classification-authority hook exists today.
- **`NonDischargeClaim` (gate_receipt.py, v4)** already types "what a verdict
  explicitly leaves unsettled" — closed kind enum, the consumer that would
  discharge it, the witness that would discharge it. The substrate to bind debt
  to a collector already exists at the receipt kernel.

So most of the "gaps" were protocol AG already ratified. **Two things survive
contact with the tree**, both wirings of parts already built.

## Wiring 1 — finding classification must be independence-typed (venue-dependent)

§11.3 settles a finding's venue by builder+validator agreement. But if builder
and validator share a provenance class, the agreement is *correlated* — the
agent grading its own homework, an NNC violation at the classification layer.
§11.1 already knows this ("before any quorum over the diagnosis counts agreement
as evidence") but that guard lives in the confusion-receipt path and never
touches finding-classification. `independence_class` exists on `EvidenceRef` and
never touches the classification path.

Wiring: port `independence_class` into the §11.3 agreement; agreement settles
jurisdiction only when the agreeing witnesses are independence-admissible **for
that classification**, with the floor **rising monotonically with how much
continuation the venue authorizes**:

```
current_rung_blocker:    low floor   — conservative (halts/fixes); self+peer may ratify
scope_expanding_remedy:  N/A         — auto-halt by identity; no permissive continuation
defense_in_depth:        medium      — low if fixed cheaply in-scope; medium if continuing
future_rung_debt:        HIGH floor  — the continue path; needs a tool/operator witness,
                                       not just correlated model-class agreement
false_positive:          HIGH floor  — discards the finding entirely
```

> The independence floor rises with the amount of continuation authorized.
> Correlated agreement is most toxic exactly on the classifications that keep
> the chain alive.

## Wiring 2 — future-rung debt must be a `NonDischargeClaim`, and rung activation must gate on it

§11.3 records future-rung debt as commit-body prose. **Named is not collected:**
prose is a sticky note on the courthouse door. Wire it:

```
validator finding classified future_rung_debt
  → mint a NonDischargeClaim (NOT prose)
  → claim names: target_rung, authorized_collector, discharge_witness, blocks_before
  → rung activation checks open claims targeting that rung
  → activation REFUSED unless discharged by an authorized collector
```

The `refused_laundering` teeth fire on a dropped boundary at the *recomposition*
seam; they do **not** fire on activating a rung over its own outstanding debt —
that is a *different seam* (rung-activation). This gap adds the second.

## The three refinements (conservation-law corollaries)

1. **Venue-dependent independence floor** — Wiring 1 above; the floor is not
   uniform.
2. **Authorized collector must be EXTERNAL to the gated rung.** If N+1's
   activation is gated on open claims and N+1 discharges them itself, that is
   self-clearance rebuilt. `authorized_collector != target_rung`. (Wiring 1's
   lemma, one seam over — same theorem.)
3. **The handoff needs its own accounting.** A debt parked at the recomposition
   seam must **mint-or-reference** the `NonDischargeClaim` the activation gate
   later consumes, or two ledgers drift and a boundary parked-but-never-claimed
   launders through the gap *between* the checkers. Fix: **content-addressed
   boundary IDs** (the RecompositionReceipt bias) make the parked disposition and
   the NonDischargeClaim the *same referent* across both seams. The obligation
   crossing recomposition→activation is itself a boundary that must be accounted.

## The seven rules (the law; schema is elaboration)

```
1. Finding classification uses venue-dependent independence floors.
2. future_rung_debt must mint/reference a NonDischargeClaim (never prose).
3. The NonDischargeClaim must name target_rung AND authorized_collector
   AND discharge_witness AND blocks_before.
4. authorized_collector != target_rung.
5. A parked recomposition boundary must share content-addressed identity with
   the claim it mints/references.
6. Rung activation refuses if any claim targeting that rung is open, missing,
   self-collected, or identity-broken.
7. account_boundaries stays a shared total-accounting COMBINATOR (a library,
   not an authority); neither seam owns it.
```

## Ownership (federated — the primitive is a library, not a god-object)

```
DebtLedger / NonDischargeClaim store:  owns outstanding obligation state
account_boundaries:                    total-accounting combinator; two call sites
recomposition seam:                    instantiates it over admitted decomposition
                                       boundaries — "did every admitted boundary
                                       get accounted?"
rung-transition (scope/annealing):     instantiates it over open NonDischargeClaims
                                       targeting the rung — "is this authority
                                       transition allowed now?"; OWNS the activation gate
```

> Debt-gating is a rung-transition responsibility, backed by recomposition/
> accounting machinery. Shared primitive, two call sites, two owners. Putting
> the gate inside the recomposition kernel makes every authority transition drag
> recomposition semantics around like a velvet rope; putting it only in scope
> re-implements boundary accounting badly. Primitive shared, authority local.

## Phase 3 split (this gap reshapes Phase 3's first slice)

The design pass moved Phase 3's opening from "start activation machinery" to
"prove activation cannot begin unless the debt/authority gates are real":

```
P3.0 — activation preflight, NO activation (this gap's home)
P3.1 — scoped activation + rollback
P3.2 — enforcement / recomposition flip
```

**P3.0 must discharge `P2_GENESIS_TARGET_ALLOWLIST_001` by mechanism, not prose,
before any activation code exists.** P3.0 acceptance criteria (the decomposition
doctrine as criteria, not a reason to stall) are recorded in the campaign card.

## Non-goals

- NOT new mechanism — this is wiring existing parts (`independence_class`,
  `NonDischargeClaim`, `account_boundaries`) at the seams where a polite note
  becomes permission.
- NOT activation. P3.0 builds the *gates that keep activation impossible* until
  debts are collected; it does not activate anything.
- NOT a merge of recomposition and rung-transition — federation is the safety
  property.

## Open question (resolve before schema hardens)

Is the activation gate the recomposition kernel's job (extend `account_boundaries`
to consume open `NonDischargeClaim`s as a disposition) or the rung-transition
layer's (annealing.py/scope.py)? **Operator lean: rung-transition owns the gate;
recomposition supplies the shared accounting primitive.** Confirm against the
rung-transition code before the schema hardens.

## SUPERSEDED by the four-office note (2026-06-13)

The cross-tool interferometry pass (against the real `standing` / `linear_accountant`
repo types) refined the answer: the "rung-activation gate" is **not one gate** —
it is a transaction across **four offices** (Governor/Wicket admissibility ·
Standing entitlement · LA spend · NQ custody), which AG currently co-hosts. The
debt-collection accounting here (`account_boundaries` over open claims) is the
**eligibility** half only; it is NOT the activation. See
`docs/cross-tool/rung-activation-four-office-note.md` for the full ownership split.

Key corrections this gap must inherit before P3.1:
- **`DebtClearVerdict` must never write `active_rung`** — debt-clear is
  eligibility; activation is a separate LA spend (exactly-once).
- **Finding classification is assert-standing** (roadmap-only in Standing); rung
  activation is act-standing + spend. Different surfaces, principals, times.
- **Freshness: deferral is cargo, re-verification is standing.** A carried
  eligibility digest / deferral classification must be RECOMPUTED at the
  activation gate (bootstrap substitute) until assert-standing + Nightshift
  freshness machinery ship.
- **Override is custodial deposit + Δh pressure, never reversal.**
- P3.0 (`activation_preflight.py`) built the eligibility half; P3.1 must wire the
  act-standing / spend / custody offices per the note, not collapse them.
