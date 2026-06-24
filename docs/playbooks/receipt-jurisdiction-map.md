# Governed Playbooks — Receipt Jurisdiction Map (claim-first)

> **Status:** Phase-0 input. This is the cheap falsification the design conversation
> couldn't run: a claim-by-claim map of every proposed Phase-0 receipt/invariant against
> the receipts AG *already ships*. Authored 2026-06-24 from a cold read of
> `agent_gov/src/governor/` with file:line grounding. It is a **scoping artifact**, not
> authorization to build, and it is a record for review.

## What this tests

The surviving risk in [governed-playbooks.md](./governed-playbooks.md) is not "frontend bad"
or "ConvergenceFence impossible." It is **jurisdiction drift** — the frontend repo
describing organs AG already owns, producing a shadow constitution with better markdown
and worse authority.

The operator's bet: *most of W-001 / SL-001 / LE-001 collapses into "cite or extend AG
receipts," and only three frontend-native artifacts survive* — `playbook_spec_digest`,
`certified_kind_receipt`, `dependency_closure_digest`.

**Result: bet confirmed, with one sharpening.** *Every* ledger seam invariant resolves to
cite-existing / extend-existing / reuse-doctrine / decompose-into-existing; the **only**
frontend-native mints are the three certification artifacts. (A per-row tally lives in this
document's tables — treat it as local accounting, not a portable "N of M" doctrine claim; the
load-bearing result is qualitative, the numeral is soft.) And SL-001 is worse than "extend":
as written it is a **jurisdiction blur** that bundles three different organs' claims under one
new receipt name.

The nasty-but-useful test, applied at the end: *after this map, the ledger should read as
mostly references.* It originally read like a full authority pipeline (the tell that the
"frontend" was a shadow constitution). The ledger has since been rewritten to references, and
the whole capture moved in-tree under `agent_gov` — which dissolves the standalone-repo
pressure at the source rather than just renaming it.

---

## Headline findings

1. **The RunRequest-onward chain already exists in AG, as receipts.** `cooked_context_orchestrator.py`
   runs `wicket → standing-verify → standing-spendability → LA-request → LA-consume`, each
   seam emitting a content-addressed `GateReceipt` with real parent linkage walkable by
   `governor why`. The ledger's W/SL/LE are not new receipts; they are this chain, renamed.

2. **SL-001 `StandingAdmission` is a three-organ blur.** It binds `allowed_effect_classes`,
   `max_effect_budget`, `revocation_epoch` (owned by external **standing**,
   `~/git/standing`), *and* "may this actor run now" (which in AG is the **wicket** verdict,
   not a standing claim), *and* freshness (the **spendability** seam). AG keeps these three
   apart on purpose. Collapsing them into one `StandingAdmission` is the exact shadow-
   constitution move the map exists to catch.

3. **CF-001's `ConvergenceOutcome` typing is solved doctrine, not new.** AG's `ChainResult`
   is already a closed sum type where exactly one variant (`OperationalConsumed`) passes the
   single spend wall (`confer_operational_effect`), by `isinstance`, not by a flag. The only
   genuinely unproven part of the ConvergenceFence is the **DAG-acyclicity / sealing lemma**
   (reactor multiplicity → one pipeline edge) — AG's chain is linear, so AG has never proven
   it. Isolate *that*; do not re-prove typed refusal.

4. **AG never mints authority — it verifies references and consumes against external grants.**
   `StandingClient.verify()` checks that a standing receipt id *resolves* (does not mint
   standing). `LinearAccountantClient` requests/consumes against an LA-issued token (does not
   mint capacity). The frontend inherits this: its certification gate certifies *kind*, never
   *execution authority*.

---

## AG's existing receipt substrate (the thing to cite)

- **`GateReceipt`** (`gate_receipt.py:402`) — content-addressed decision receipt.
  `receipt_id = H(schema_version : gate : subject_hash : evidence_hash : policy_hash :
  receipt_role [: horizon] [: unsettled])` (`:389`). Timestamp/principal are metadata, not
  identity. `verdict ∈ {pass, warn, block, observe, proceed}` (`:68`); `receipt_role ∈
  {measurement, proposal, authority, recovery_plan, reset}` (`:48`). Split store:
  `ReceiptStore` (JSONL) + `EvidenceStore` (content-addressed blobs, `:617`). **Every row
  below that says "extend" means: same gate, richer `subject_bytes`/`evidence_bundle` — not
  a new receipt type.**
- Seam gates already wired and emitting: `wicket_seam`, `standing_seam`,
  `standing_spendability_seam` (`spendability_gate`), `la_seam`, plus `nightshift_adapter`,
  `intent_compiler`, `evidence_gate`, … (28+ gates).

Each block below is the operator's 10-field schema:
`(1) proposed · (2) claim · (3) subject · (4) authority/evidence status · (5) existing AG
owner · (6) fields already covered · (7) missing/extension · (8) consumer · (9) refusal shape
· (10) verdict.`

---

## Group A — collapses into REUSE / EXTEND (the bet)

### W-001 — `WicketAdmission`
1. `WicketAdmission` (proposal intake).
2. *Claim:* "this RunRequest is admitted to judgment (procedural admissibility)."
3. *Subject:* the run proposal — actor, action, target, + playbook digests.
4. Authority gate (admission ≠ execution).
5. **AG owner:** `wicket_seam` GateReceipt; `WicketVerdict`/`WicketRefusal`
   (`wicket_client.py:200`, `:495`). Already cites verified-standing as parent.
6. *Covered:* actor, intended_action, target, standing receipt linkage, issued-at (timestamp),
   verdict, content-addressed subject (`wicket_client.py:322`).
7. *Extension:* bind `certified_playbook_digest`, `certified_kind_receipt_digest`,
   `dependency_closure_digest`, `bound_input_digest`, `parser_version`, `checker_version`
   into the existing subject/evidence bundle. (Four of those are the frontend-native
   survivors — see Group C.)
8. *Consumer:* the LA seam, via `admission_receipt_id` (`wicket → LA` parent linkage).
9. *Refusal:* `WicketRefusal{standing_required | dangling_receipt_reference}`, receipted
   verdict=`block`.
10. **Verdict: EXTEND `wicket_seam`.** "WicketAdmission" is a rename of the shipped
    admission GateReceipt + the three certification digests.

### LE-001 — LA → Executor consumption
1. exactly-once effect consumption.
2. *Claim:* "this effect was consumed exactly once against token T for run R, step S."
3. *Subject:* `consumption_event_id`, `token_id`, action/target/scope.
4. Evidence (positive proof of spend), gated by an external grant.
5. **AG owner:** `la_seam` `ConsumedResult` / `CookedConsumeRequest`
   (`linear_accountant_client.py:377`, `:283`).
6. *Covered:* exactly-once via `consumption_event_id`; replay refusal; principal; resource;
   amount; token; parent grant linkage.
7. *Extension:* add `step_id` and `effect_class` to the consume request/receipt.
8. *Consumer:* the Executor (effect gated on receiving `ConsumedResult`).
9. *Refusal:* `RefusalResult{already_consumed | token_expired | token_revoked |
   unknown_token | scope_mismatch | insufficient_capacity}` (closed vocab,
   `linear_accountant_client.py:109`).
10. **Verdict: EXTEND `la_seam` consume.** Exactly-once is *reuse* — already shipped and
    tested. Nothing new but two fields.

### NS-001 — schedule is not standing (Nightshift)
1. scheduled firing → candidate, never license.
2. *Claim:* "a trigger fired; re-resolve standing live."
3. *Subject:* the trigger event.
4. No authority (machine trigger).
5. **AG owner:** `nightshift_adapter.py` (event → `ReceiptRole`); the chain it feeds is the
   existing orchestrator.
6. *Covered:* trigger → candidate RunRequest → full chain re-resolution.
7. *Extension:* missed-run default policy (don't run-on-reconnect) — a Nightshift config, not
   a new receipt.
8. *Consumer:* Wicket (candidate enters the same intake).
9. *Refusal:* whatever the live chain refuses.
10. **Verdict: REUSE.** Nightshift firing produces a candidate that flows the existing chain.

### RV-001 — revocation beats cache
1. cached admissibility invalidated on revocation.
2. *Claim:* "this cached decision is stale; re-resolve."
3. *Subject:* cached closure + `revocation_epoch` / `grant_generation`.
4. Evidence (freshness), authority owned upstream.
5. **AG owner:** LA token state (`Expired`/`Revoked` → `REFUSAL_TOKEN_*`) + external-standing
   `revocation_epoch` + spendability freshness.
6. *Covered:* token expiry/revocation refusals; spendability horizon.
7. *Extension:* `valid_until` / `grant_generation` / `dependency_closure_digest` invalidation
   fields on any frontend-side cache (the cache is frontend-local; the *authority* to revoke
   is upstream).
8. *Consumer:* the cache reader, before reuse.
9. *Refusal:* `token_expired` / `token_revoked`; `standing_before_spendability_not_bounded`.
10. **Verdict: REUSE/EXTEND.** Revocation authority is upstream; only the cache-invalidation
    bookkeeping is frontend-local.

---

## Group B — belongs to ANOTHER organ (cite, don't define)

These are the rows where the ledger is most at risk of writing another organ's constitution.

### SL-001 — `StandingAdmission` *(the blur — decompose)*
The proposed `StandingAdmission` binds, in one receipt: `run_plan_digest`, principals,
`allowed_effect_classes`, `max_effect_budget`, `revocation_epoch`, plus "may this actor run
now." That is **three claims with three owners**:

- **(a) the grant** — `allowed_effect_classes`, `max_effect_budget`, `revocation_epoch`:
  owned and minted by external **standing** (`~/git/standing`). AG only *verifies the
  reference*. → **CITE** the standing grant; do not re-mint its fields.
- **(b) "may run now"** — in AG this is the **wicket** verdict (`surface_verdict`,
  `allowed`/`forbidden`), not a standing claim at all. → already covered by W-001.
- **(c) freshness** — "standing valid when observed, void when spent." Owned by the
  **`standing_spendability_seam`** (`StandingWindow`, two-clock `MonotonicReading` gap,
  refusal `standing_before_spendability_not_bounded`, `standing_spendability.py:85`). →
  **CITE** the spendability receipt.

AG's own `standing_seam` receipt asserts only **(d) "this standing receipt id resolves to a
real ref (kind, digest)"** (`standing_client.py:253`) — a *verification* claim, independently
emitted and cited as parent. That is a legitimate peer receipt (see the determination below),
but it is **not** the authorization claim the ledger labels it.

10. **Verdict: DECOMPOSE.** SL-001 is not one new receipt; it is `cite(standing grant) +
    W-001(wicket verdict) + cite(spendability) + extend(la grant)`. Writing it as a single
    `StandingAdmission` is the shadow constitution. **The LA *reservation* half** (the ledger's
    `standing_admission_digest, reserved_resource, amount, ttl, run_plan_digest`) **= EXTEND
    `la_seam` `GrantedResult`** (`token_id, granted_capacity, scope, expires_at, parent=
    admission_receipt_id`, `linear_accountant_client.py:352`).

### WF-001 / WS-001 / OE-001 — witness validity (NQ's jurisdiction)
1. fresh-witness consumption; scope non-expansion; observation effect-typing.
2. *Claim:* "this witness may satisfy this precondition."
3. *Subject:* witness ↔ precondition relation.
4. **No authority** ("NQ may testify; it may not promote testimony into permission").
5. **AG owner:** *partial only.* The **freshness-as-relation** doctrine and the
   `clock_witness` machinery (`MonotonicReading`, `elapsed_ns` refusing incompatible bases)
   are reusable substrate (`standing_spendability.py` is the worked example). But a general
   **NQ-witness-precondition consumer** — claim-type unification, observer admissibility,
   scope non-expansion, observe-effect classes — **is not built in AG, and is NQ's grammar,
   not the frontend's.**
6. *Covered (reuse):* clock basis + freshness gap + typed refusal.
7. *Missing:* the witness-typing rules themselves → **NQ.**
8. *Consumer:* the precondition checker.
9. *Refusal:* `CannotTestify` (NQ-side) / freshness refusal (reuse spendability shape).
10. **Verdict: CITE NQ + REUSE `clock_witness`.** The frontend consumes NQ witnesses; it
    does not author witness-validity law. (Phase-witness mapping is already a tracked
    cross-repo gap, blocked on NQ ratification — do not pre-empt it here.)

### MC-001 — cockpit input is proposal (Maude)
5. **AG owner:** the "input is proposal" doctrine is already AG's (runtime supervisor:
   pre-tool gate, "presence ≠ authority"). The human-approval receipt (`approved_run_plan_
   digest, expires_at`) = **EXTEND `GateReceipt` with `receipt_role=proposal`** then the same
   chain. Maude owns the *affordance typing* (which button adjudicates vs triggers vs
   displays) — a Maude concern, not a frontend receipt.
10. **Verdict: REUSE doctrine + Maude owns the UI typing.**

### SP-001 / SP-002 — index carries no status; corpus recoverable (Spine)
5. **AG owner:** Spine C4/C6. The "Playbook Registry" is a Spine *edition/index*, not a new
   organ — and **Spine is parked; do not reactivate it by accident.**
10. **Verdict: CITE Spine doctrine.** Not the frontend's to define.

### EC-001 — execution custody (Executor)
5. **AG owner:** the *typed-terminal-state ADT discipline* is shipped (`ChainResult`,
   `DemonstratedConsumed`, `RecompositionRefusal`, the `confer_operational_effect` wall,
   `cooked_context_orchestrator.py:455–545`). But the specific `InterruptedUnknownEffect`
   custody state (chaos between dispatch and witness) is an **Executor** concern, and AG has
   no executor yet (the orchestrator consumes; it does not dispatch interruptible external
   effects).
10. **Verdict: REUSE the ADT doctrine; the executor custody states are new Executor-side
    work, gated behind a real executor.**

---

## Group C — genuinely FRONTEND-NATIVE (the only survivors)

Exactly the three the operator predicted. These have no AG equivalent because AG hashes
generic subjects, not playbook specs.

1. **`playbook_spec_digest`** — what authored bytes were certified. *Claim:* "these exact
   restricted-YAML bytes are the certified artifact." Subject = the canonical IR bytes.
   Status: evidence (provenance + replay anchor). New. **Frontend owns.**
2. **`certified_kind_receipt`** — what restricted kind the checker accepted. *Claim:* "checker
   C classified canonical spec digest D as `certified_kind` K under grammar/checker versions
   V." This is a **measurement, not authority** — `receipt_role=measurement`, AG's *default*
   role (`gate_receipt.py:48`, grep-confirmed). The checker *originates* the kind-fact the way
   a thermometer originates a temperature; **originating a measured fact is not minting
   authority** (the same scalpel the map turned on standing-verify, recursed inward). **Wicket
   owns the consequence** — it refuses absent/mismatched certification; the frontend authorizes
   nothing. The frontend's authority surface is therefore **exactly zero**, which is the
   strongest version of what this repo is. **Frontend owns the *measurement*.**

   > **Frontend certification is admissible evidence for Wicket, not authority.** *(The spine
   > sentence. The earlier phrase "authority over certification only" was a future bug report
   > — retired.)*
3. **`dependency_closure_digest`** — what composition closure was checked. *Claim:* "this
   import/sub-playbook closure was resolved and pinned (no `latest`)." Status: admissibility
   support + replay protection + build provenance (all three — and the ledger should say
   which, per its own open question). New. **Frontend owns.**

Everything downstream of these three digests — RunRequest, Wicket, Standing, spendability,
LA, consume, custody — **cites AG receipts**.

---

## The Wicket/Standing determination (asked for explicitly)

**Question:** is Standing a peer receipt in the RunRequest path, or Wicket-internal evidence?

**From the code:** `WicketClient.check()` calls `standing_client.verify()` *first*
(`wicket_client.py:435`); on success the StandingClient **independently emits a verified-
standing `GateReceipt`** under its own `standing_seam` gate (`standing_client.py:365`),
exposes its id via `_last_verified_receipt_id`, and the wicket admission receipt **cites it as
parent** (`wicket_client.py:490`), making `wicket-admission → standing-verification → (NQ
finding)` walkable by `governor why`.

**Determination:** Standing-**verification** is a genuine **peer receipt** — distinct gate,
distinct subject (`standing_receipt_id`), distinct claim, independently consumed (as parent
linkage). Implementation composition (called *inside* `WicketClient`) is **not** constitutional
collapse here. The tiny powdered wig is **not** being worn.

**But** — and this is the sharpening the cooling-off review wanted — the claim that peer
receipt makes is **"the reference resolves,"** *not* **"may run with these effects."** The
ledger's SL-001 attaches the second claim to the standing row. That authorization claim is
owned by external-standing's **grant** (cite) plus wicket's **verdict** (W-001). So: keep SL
as a distinct row, but **rename its claim to "verified standing reference"** and move the
"may run / effect budget" bindings to where they're actually minted. Verification cosplaying
as authorization is the failure mode; the receipt boundary already exists in AG to prevent it.

---

## ConvergenceFence — isolate only the unproven lemma

`ConvergenceOutcome` (`AlreadyConverged | Converged | RefusedPreEffect | NonConvergedNoEffect
| NonConvergedPartialKnown | InterruptedUnknownEffect`, only the first two progressing) is
**structurally the pattern AG already ships**: `ChainResult` is a closed sum type; exactly one
variant (`OperationalConsumed`) passes `confer_operational_effect`; the gate is `isinstance`,
**not** a `.operational` flag ("a flag is the blocklist pattern wearing a flag costume … the
type split makes misuse unrepresentable", `cooked_context_orchestrator.py:439`). The
"`InterruptedUnknownEffect` poisons downstream" rule = a non-`OperationalConsumed` refused at
the wall.

So the typed-refusal / progress-gating half of CF-001 is **reuse**. Do not spend Phase-1
re-proving it. But the unproven remainder is **two lemmas, not one** — and naming it
"acyclicity" smuggles the easy half, because *acyclicity ≠ confluence*: an acyclic DAG can
still fail if two reactor edges fire conflicting effects with **no cycle** (a diamond, not a
loop). AG's chain is **linear** (`admission → consume`), never a pipeline DAG with embedded
reactor multiplicity, so AG has prior art on *neither*:

- **CF-001-L1 · Seal Acyclicity** — the seal introduces no cycle into the pipeline DAG. *Graph
  hygiene. Necessary, not sufficient — and a Lean owner handed only this can prove it and miss
  the real thing.*
- **CF-001-L2 · Seal Single-Outcome / Confluence** *(load-bearing)* — a sealed reactor site
  yields **exactly one** terminal pipeline outcome (`AlreadyConverged | Converged |
  RefusedPreEffect | NonConvergedNoEffect | NonConvergedPartialKnown |
  InterruptedUnknownEffect`); **no two competing successful effects escape as sibling pipeline
  facts.** This is the genuinely hard, genuinely new obligation.

A useful narrowing of L2's scope, from the hostile cases: case **#2 repeated-firing** is
exactly-once, which **LE-001 already routes to reuse**; case **#3 interruption** is
`InterruptedUnknownEffect`, which **EC-001 already parks behind a real executor**. So two of
the three hostile cases dissolve into already-handled doctrine — what's left for L2 is the
pure confluence core (conflicting concurrent effects, no cycle). **L1 + L2 are the Lean
owner's Phase-1 footing; L2 is the one that must not be allowed to hide behind L1's name.**

---

## Scope verdict for the playbooks layer (`governor.playbooks`)

The playbooks package should own **Group C only**: the restricted-YAML → canonical IR → `playbook_spec_digest`
→ `certified_kind_receipt` → `dependency_closure_digest` path. Everything from RunRequest
onward **cites** AG's shipped receipts (`wicket_seam`, `standing_seam`,
`standing_spendability_seam`, `la_seam`, the orchestrator's `ChainResult` + spend wall) and
the sibling organs (NQ witnesses, Spine editions, Nightshift triggers, Maude affordances).

**The lying-name test (settled):** the rewrite made each seam row read *"= AG `<gate>`,
extended with `<digest>`"* or *"cite `<organ>`"* instead of *"MUST bind `<full field list>`."*
The ledger now reads as **mostly references** — *every seam → cite / extend / reuse /
decompose-into-existing; only the three certification artifacts are native.* That is what a
genuine measurement/authoring layer looks like. The capture then moved in-tree under
`agent_gov`, so there is no longer a standalone-repo name to keep honest — the structural
pressure is gone, not merely relabeled.

---

## What this map did *not* settle (handed back up)

- The **field-level** map (column 7 of every Group-A/B row) — deferred by design; do it only
  after these claim boundaries are ratified. **But each "cite/extend AG X" row must carry a
  *resolution target* — gate + field + file:line — not prose** (Patch 4). A citation is a
  *claim with a target*, not a settled fact, and is only honest once the field it points at is
  confirmed to exist — which *is* the field diff. The rewrite writes the checks; the deferred
  diff cashes them; a citation that doesn't resolve is the same lie in a cheaper suit. (The
  load-bearing citations were already runtime-confirmed — see Evidence below — but every row's
  target must resolve before Phase 0 hardens.)
- `certified_kind_receipt` gate-vs-role: **settled** — it is a `receipt_role=measurement`
  receipt (Patch 1), not an authority surface. Whether it rides a new `playbook_certification`
  gate or an existing one is a small `gate_receipt.py` call, deferred to Phase 2.
- The seal lemmas (**CF-001-L1** acyclicity + **CF-001-L2** confluence) — **paper, then Lean,
  then nothing downstream until green** (build-phases Phase 1). This map narrowed *what* must
  be proven and split the easy half (L1) from the load-bearing half (L2).

---

## Evidence — the code-shaped falsification (run 2026-06-24)

The common-mode risk in this whole stack: every reviewer (multiple models, this author
included) was reasoning *about* AG. Model agreement is correlated and worth little; the only
test code can't pass out of politeness is whether the cited symbols resolve and the chain
walks. Both were run against the live repo, not transcribed:

**1. Symbol resolution (`git grep`)** — every load-bearing citation exists at its claimed site:
- `wicket_client.py:435` — `self._standing_client.verify(` is the literal call. ✓
- `standing_client.py:365` — `_last_verified_receipt_id` set via `_emit_verified_receipt`. ✓
- `cooked_context_orchestrator.py` — `confer_operational_effect`, `class OperationalConsumed`,
  `class DemonstratedConsumed` all present. ✓
- gate names `wicket_seam` / `standing_seam` / `la_seam` / `standing_spendability` all defined. ✓
- `gate_receipt.py:48` — `ROLE_MEASUREMENT = "measurement"` is the **default** role (decides
  Patch 1). `ROLE_AUTHORITY` exists but is not what certification needs. ✓

**2. Chain resolution (`governor why` on a live receipt)** — the demo emitted a real refused
chain (`demo/refused-spend.sh`); walking the leaf produced, through real receipt ids:

```
REFUSED  standing_spendability_seam   standing_before_spendability_not_bounded
  OK     wicket_seam     verdict=pass          ← admission
    OK   standing_seam   verdict=pass          ← standing reference verification
      → NQ finding origin (drill mint; terminates at the NQ-side origin)
```

This is exactly the acceptance shape the review demanded (`wicket-admission → standing-
reference-resolution → spendability → LA`). LA is absent here **because the impostor refused at
spendability before LA was invoked** (`effect_count=0`) — the correct behavior, and itself
evidence the chain short-circuits at the right wall. The legitimate twin's chain reaches LA
grant/consume.

**Standing requirement for Phase 0:** before the ledger hardens, *every* "cite AG X" row's
file:line target must resolve under `git grep`, and at least one `governor why` walk must show
the full `wicket → standing → spendability → LA` chain resolving on real ids. Prose is not a
substitute. The two checks above discharge the load-bearing subset; the rest is mechanical.
