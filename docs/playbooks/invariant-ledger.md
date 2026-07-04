# Governed Playbooks — Invariant Ledger (jurisdiction map)

> **Status:** Phase-0 artifact, **reference-form** (rewritten 2026-06-24 from
> [receipt-jurisdiction-map.md](./receipt-jurisdiction-map.md), which is the authority for
> this shape). This ledger no longer specifies receipts the frontend must mint — that
> framing read as a standalone authority pipeline and was the jurisdiction-drift risk. Each
> seam below names **which organ's receipt already holds it**, so the frontend can *cite*
> rather than re-constitute. A record for review, not authorization to build.

## What changed and why

The previous version listed full field blocks (`X MUST bind a, b, c, …`) for every seam.
That is how a frontend repo grows a shadow constitution: by writing, in better markdown, the
receipts that AG already ships. The claim-by-claim map found that **every seam collapses into
cite / extend / reuse / decompose-into-existing; only the three certification artifacts are
frontend-native.** (Per-row tallies are local accounting, not a portable "N of M" claim.) So
this pass is deflationary by design — it *removes* invented authority, it does not add detail.

**Rules for this pass (held):** no new receipt types; no field-level diff (deferred until
this rewrite is reviewed); no expanded authority language; **verification is never renamed as
admission.**

Each row is tagged with exactly one jurisdiction verb:

| Tag | Meaning |
| --- | --- |
| **FRONTEND-NATIVE** | the frontend owns and mints this; no AG equivalent exists |
| **EXTEND `<gate>`** | reuse a shipped AG gate; add playbook-specific bytes to its subject/evidence (field diff later) |
| **CITE `<organ>`** | another organ owns the claim; the frontend references its receipt |
| **REUSE doctrine** | the *discipline* is shipped AG behaviour; nothing new to define |
| **DECOMPOSED** | the original seam bundled several organs' claims; split below |
| **UNRESOLVED LEMMA** | genuinely new proof work, isolated |

The recurring demon is unchanged: *a claim (past / proposed / present-but-unverified) doing a
signing receipt's job.* The rewrite's contribution is naming **whose** signing receipt, so the
frontend stops impersonating it.

---

## The three frontend-native artifacts (the whole of what this repo owns)

Everything downstream of these cites AG. These are the only rows the frontend mints.

- **FN-001 · `playbook_spec_digest`** — *"these exact canonical-IR bytes are the certified
  artifact."* Evidence / replay anchor over the restricted-YAML → IR output. **FRONTEND-NATIVE.**
- **FN-002 · `certified_kind_receipt`** — *"checker C classified canonical spec digest D as
  `certified_kind` K under grammar/checker versions V."* A **measurement, not authority**:
  `receipt_role=measurement` (AG's default role). The checker *originates* the kind-fact like
  a thermometer originates a temperature — originating a measured fact is not minting
  authority. **Wicket owns the consequence** (it refuses absent/mismatched certification); the
  frontend authorizes nothing, so its authority surface is **exactly zero**. (`claimed_kind`
  proposes; the checker disposes; Wicket's admission dispatches on `certified_kind` only.)
  **FRONTEND-NATIVE measurement.**
  > **Frontend certification is admissible evidence for Wicket, not authority.** *(spine
  > sentence; "authority over certification only" retired as a future bug report)*
- **FN-003 · `dependency_closure_digest`** — *"this import / sub-playbook closure was resolved
  and pinned (no `latest`)."* Admissibility support + replay protection + build provenance.
  **FRONTEND-NATIVE.**

> Inherited from AG and binding on the frontend: **certification is not minting.** AG's
> standing seam verifies a reference; LA consumes against an externally-issued token; neither
> mints authority. The certification gate above certifies kind, not the right to run.

---

## Seams that cite or extend AG (the collapse)

### W-001 — Proposal intake
*Claim:* "this RunRequest is admitted **to judgment** (procedural admissibility)" — admission
to review, not to execution. **EXTEND `wicket_seam`** (the shipped `WicketVerdict` /
`WicketRefusal` admission receipt, which already cites verified standing as parent), carrying
`FN-001`/`FN-002`/`FN-003` + `bound_input_digest` in its subject. Refusal stays the shipped
`{standing_required | dangling_receipt_reference}`. *Wicket admits proposals to judgment;
Standing does not admit runs to execution here — see SL-001's rename.*

### SL-001 — *DECOMPOSED* (was "StandingAdmission-Bound Reservation")
**`StandingAdmission` was a laundering name.** It read as "the standing seam admits
execution." It does not. AG's standing seam only verifies that a standing receipt *reference
resolves*; the effect budget is minted elsewhere, "may run now" is Wicket's verdict, and
freshness is the spendability seam's. The seam splits into four claims with four owners:

- **SL-001a · `StandingReferenceResolution`** — *"the standing receipt reference resolves to a
  real ref (kind, digest)."* This is *"the badge exists and scans,"* **not** *"you may drive
  the forklift."* **CITE `standing_seam`** (`StandingClient.verify`). The name carries no
  authority verb on purpose. **Verification is not admission.**
- **SL-001b · the grant** — `allowed_effect_classes`, `max_effect_budget`, `revocation_epoch`
  are minted by **external standing** (`~/git/standing`). **CITE the standing grant.** The
  frontend does not re-mint these fields.
- **SL-001c · "may run now"** — this is the **Wicket verdict**, already covered by **W-001**.
  It is not a standing claim.
- **SL-001d · freshness** — *"standing valid when observed, void when spent."* **CITE
  `standing_spendability_seam`** (the two-clock `StandingWindow`; refusal
  `standing_before_spendability_not_bounded`).
- **SL-001e · LA reservation** — the reserve-against-grant claim. **EXTEND `la_seam`**
  (`GrantedResult`: token, capacity, scope, expiry, parent = admission receipt). LA reserves
  against a fresh signed grant; it never mints capacity.

> The TOCTOU window is *bounded* by the reservation, not closed. That bound lives in
> `la_seam` + `standing_spendability_seam` already; the frontend adds nothing to it.

### LE-001 — LA → Executor consumption
*Claim:* "this effect was consumed **exactly once** against token T for run R, step S."
**EXTEND `la_seam`** consume (`ConsumedResult` / `CookedConsumeRequest`; exactly-once is the
shipped `consumption_event_id` → `already_consumed` refusal). Extension is `step_id` /
`effect_class` only. Exactly-once itself is **REUSE**.

### NS-001 — schedule is not standing
*Claim:* "a trigger fired; re-resolve standing live." **REUSE** — a Nightshift firing
(`nightshift_adapter`) produces a *candidate* RunRequest that flows the existing chain
(candidate → W-001 → SL-001 → LA). Missed-run-default ("never run-on-reconnect") is a
Nightshift config, not a frontend receipt. A schedule is only a request to re-resolve.

### RV-001 — revocation beats cache
*Claim:* "this cached decision is stale; re-resolve." **REUSE / EXTEND** — revocation
*authority* is upstream (`la_seam` `token_expired`/`token_revoked`; external-standing
`revocation_epoch`; spendability horizon). Only the cache-invalidation bookkeeping
(`valid_until`, `grant_generation`, `dependency_closure_digest` change-detection) is
frontend-local, on the frontend's own cache.

---

## Seams owned by a sibling organ (cite, do not define)

The frontend is most at risk of writing another organ's constitution here. It does not.

### WF-001 / WS-001 / OE-001 — witness validity
Fresh-witness consumption (WF-001), scope non-expansion (WS-001), observation effect-typing
(OE-001). **CITE NQ.** *NQ may testify; it may not promote testimony into permission* — so
witness-validity law (claim-type unification, observer admissibility, scope non-expansion,
observe-effect classes) is **NQ's grammar, not the frontend's.** The frontend **REUSEs**
`clock_witness` (`MonotonicReading` / `elapsed_ns`) for the freshness-as-relation half only.
(Phase-witness mapping is already a tracked cross-repo gap blocked on NQ ratification — do not
pre-empt it.)

### MC-001 — cockpit input is proposal
*Claim:* "a human click is a candidate activation, not authority." **REUSE doctrine** — AG's
runtime supervisor already holds *presence ≠ authority*. The human-approval receipt
(`approved_run_plan_digest`, `expires_at`) is a `GateReceipt` with `receipt_role=proposal`,
then the same chain. **Maude owns the affordance typing** (which button adjudicates vs
triggers vs displays); the frontend does not specify Maude's buttons.

### SP-001 / SP-002 — index carries no status; corpus recoverable
**CITE Spine** (C4 / C6). The "Playbook Registry" is a Spine *edition / index*, not a new
organ — *listing is not blessing.* **Spine is parked; do not reactivate it by accident.**

### EC-001 — execution custody
*Claim:* "unknown effect is unknown custody, not no-effect." **REUSE** the typed-terminal-
state ADT discipline AG already ships (`ChainResult` + `confer_operational_effect`). The
specific `interrupted_unknown_effect` custody state is **Executor-side work, gated behind a
real executor** (AG's orchestrator consumes; it does not yet dispatch interruptible external
effects). New custody states wait for that organ to exist.

---

## ConvergenceFence — reused doctrine + one isolated lemma

### CF-001 — typed convergence outcome
*Claim:* "a reactor embedded in a pipeline exposes only a terminal `ConvergenceOutcome`; only
`AlreadyConverged` / `Converged` progress." The **typed-outcome discipline is REUSED AG
doctrine** — `ChainResult` is already a closed sum type where exactly one variant
(`OperationalConsumed`) passes the single spend wall (`confer_operational_effect`) by
`isinstance`, not by a `.operational` flag. "Poison blocks downstream" = a non-progressing
variant refused at the wall. **Phase 1 must not retreat into re-proving closed-sum typed
refusal** — that hat is already on.

### CF-001-L1 — seal acyclicity  ·  **UNRESOLVED LEMMA (graph hygiene)**
The seal introduces no cycle into the pipeline DAG. *Necessary, not sufficient* — and a Lean
owner handed only this can prove it and miss the real thing, because **acyclicity ≠
confluence**: an acyclic DAG still fails if two reactor edges fire conflicting effects with no
cycle (a diamond, not a loop).

### CF-001-L2 — seal single-outcome / confluence  ·  **UNRESOLVED LEMMA (load-bearing)**
A sealed reactor site yields **exactly one** terminal pipeline outcome (`AlreadyConverged |
Converged | RefusedPreEffect | NonConvergedNoEffect | NonConvergedPartialKnown |
InterruptedUnknownEffect`); **no two competing successful effects escape as sibling pipeline
facts.** This is the genuinely hard, genuinely new obligation. AG's chain is **linear**
(`admission → consume`), never a DAG with embedded reactor multiplicity — no prior art to
borrow. Narrowing from the hostile cases: #2 repeated-firing is exactly-once (**LE-001
reuse**) and #3 interruption is `InterruptedUnknownEffect` (**EC-001**, behind a real
executor), so what's left for L2 is the pure confluence core. **Paper first, then the Lean
owner; L2 must not hide behind L1's name. Everything downstream is provisional until both
close.**

---

## The big soft cluster (unchanged — still the red marker)

Most failure modes collapse into three master risks. They are the *reason* for the
jurisdiction tags above, not separate work:

1. **Durable artifacts impersonating live authority** — promotion, authorship, history,
   cached standing, schedules, index-presence, cockpit-presence. (W-001, SL-001a, MC-001,
   SP-001, NS-001, RV-001 are all this demon in costume.)
2. **Composition hiding authority** — imports, parameters, sub-playbooks, shell, secrets,
   derived candidates. (FN-003 + the deferred composition phase.)
3. **UI compressing uncertainty into green** — dry runs, partial execution, weak verification,
   fake rollback, local success criteria. (MC-001, EC-001, WF-001.)

> The dangerous run is `good playbook + weird parameters + stale grant + mutated import +
> optimistic preview + one irreversible step`. Input binding + dependency closure + live
> standing are evaluated **together** — and in AG that evaluation is the orchestrator's chain,
> which the frontend cites rather than rebuilds.

---

## Deferred to the next pass (not this one)

- **Field-level diff** for every EXTEND/CITE row — held until this ledger is reviewed
  (boundaries first, fields second). **Requirement (Patch 4):** each row carries a *resolution
  target* — gate + field + file:line — not prose. A citation is a *claim with a target*, only
  honest once the field resolves; a citation that doesn't resolve is the same lie in a cheaper
  suit. The load-bearing subset is already runtime-confirmed (`git grep` + a `governor why`
  walk of `wicket → standing → spendability`; see the map's Evidence section); the rest is
  mechanical.
- **`certified_kind_receipt` role: settled.** It is `receipt_role=measurement`, not authority
  (see FN-002). Whether it rides a new `playbook_certification` gate or an existing one is a
  small `gate_receipt.py` call, deferred to Phase 2.
- **Term reconciliation in sibling docs: DONE** (2026-06-24). `StandingAdmission` →
  `StandingReferenceResolution` across `governed-playbooks.md` and `glossary.md`; zero live
  assertions of the laundering name remain (the only surviving hits are diagnostic — the map
  and this ledger naming the dead term to kill it). The *abstract* "Standing evaluates the
  RunPlan / is the judge" thesis in `governed-playbooks.md` is a deeper design-model
  reconciliation, deliberately not gutted in the terminology pass — flagged for a separate
  decision.
