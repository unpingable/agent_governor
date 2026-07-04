# Governed Playbooks — Build Gap

> **Status:** Phase-0 gap spec (2026-06-24). Synthesizes
> [receipt-jurisdiction-map.md](./receipt-jurisdiction-map.md) (authority for the boundaries,
> with runtime evidence) + the rewritten [invariant-ledger.md](./invariant-ledger.md). Gated
> on the same footing as everything else here: nothing past Phase 0/1 is built until the seal
> lemmas close. A record for review, not authorization to build. **Code home (when it exists):
> `governor.playbooks` — a measurement/authoring package, not `governor.frontend`.**

## The gap in one sentence

> Everything from `RunRequest` onward already exists in AG as walkable receipts; the playbooks
> layer builds only the *inert authoring + measurement* layer that produces three artifacts —
> and **certification is admissible evidence for Wicket, not authority.**

That spine sentence is the whole scope. If a build task makes the frontend *authorize*
anything, it is out of scope by construction.

---

## What already exists (AG ships — cite / extend, do not rebuild)

Runtime-confirmed 2026-06-24 (`git grep` + a live `governor why` walk — see the map's Evidence
section; this is the one test code can't pass out of politeness, and it passed):

- **The organ chain** — `cooked_context_orchestrator.py` runs `wicket → standing-verify →
  standing-spendability → LA-request → LA-consume`, each seam emitting a content-addressed
  `GateReceipt` with walkable parentage. The `wicket → standing → spendability` chain resolves
  on real ids; LA short-circuits correctly when an upstream seam refuses (`effect_count=0`).
- **Typed outcomes + the spend wall** — `ChainResult` is a closed sum type; only
  `OperationalConsumed` passes `confer_operational_effect`, by `isinstance`, not a flag. This
  is CF-001's typed-refusal discipline, already shipped.
- **Receipt substrate** — `GateReceipt` (content-addressed; `receipt_role` ∈ {measurement,
  proposal, authority, …}, default `measurement`), split `ReceiptStore`/`EvidenceStore`,
  `governor why` chain walk.
- **The seams the ledger cites** — `wicket_seam`, `standing_seam` (verifies a *reference*,
  never mints), `standing_spendability_seam`, `la_seam` (consumes against an LA-issued token,
  never mints; exactly-once via `consumption_event_id`).
- **Sibling organs** — NQ (witness validity), Spine (index/edition, *parked*), Nightshift
  (triggers → candidates), Maude (cockpit affordances). The frontend cites these; it does not
  author their law.

---

## What needs building (frontend-native — the only mints)

The inert authoring/measurement layer, and nothing else:

1. **Restricted-YAML dialect + canonical parser → typed IR.** No anchors / aliases / custom
   tags / implicit bools / duplicate keys / merge keys; explicit schema; one canonical parser.
   YAML is a friendly skin over a typed AST; custody lives on the IR.
2. **`playbook_spec_digest`** (FN-001) — hash over the canonical IR bytes. Evidence / replay
   anchor. *"these exact bytes are the certified artifact."*
3. **Composition checker → `certified_kind_receipt`** (FN-002) — a **measurement**
   (`receipt_role=measurement`) asserting *"checker C classified spec digest D as
   `certified_kind` K under versions V."* The checker originates the kind-fact; it does not
   authorize. `claimed_kind` proposes, the checker disposes, **Wicket** owns any refusal.
   Reactor-kind first (simpler algebra); pipeline-kind in 2b.
4. **`dependency_closure_digest`** (FN-003) — hash over the resolved, digest-pinned closure
   (no `latest`). Admissibility support + replay protection + build provenance.

Everything downstream of these three digests **cites** AG (extend `wicket_seam` to bind them;
the chain takes over from there).

---

## The footing that gates all of it (Phase 1)

The reactor/pipeline partition holds only if the seal closes. **Two lemmas, not one** —
acyclicity is graph hygiene and must not be allowed to impersonate the hard obligation:

- **CF-001-L1 · seal acyclicity** — the seal introduces no cycle into the pipeline DAG.
- **CF-001-L2 · seal single-outcome / confluence** *(load-bearing)* — a sealed reactor site
  yields exactly one terminal outcome; no two competing successful effects escape as sibling
  pipeline facts. (`acyclicity ≠ confluence`: a diamond is acyclic and still wrong.)

Hostile-case narrowing: #2 repeated-firing → LE-001 exactly-once (reuse); #3 interruption →
EC-001 `InterruptedUnknownEffect` (behind a real executor). What's left for L2 is the pure
confluence core. **Paper first, then the Lean owner — not playbook-claude inline.** Reused AG
doctrine (typed refusal / spend wall) is *not* re-proven.

> **HARD GATE:** if L1 ∧ L2 don't close, STOP. The partition is wrong and nothing below is
> real. No registry / parser-for-execution / executor / Rust before this is green.

---

## Acceptance criteria

- **AC-1 (Phase 0 ledger).** [invariant-ledger.md](./invariant-ledger.md) ratified and
  hash-pinned. Every "cite/extend AG X" row carries a **resolution target** (gate + field +
  file:line); every target resolves under `git grep`; at least one `governor why` walk shows
  `wicket → standing → spendability → LA` resolving on real ids. Prose is not a substitute.
- **AC-2 (zero authority surface).** No frontend artifact carries `receipt_role=authority`.
  `certified_kind_receipt` is a measurement. Grep for `ROLE_AUTHORITY` / `receipt_role=
  authority` in frontend-emitted receipts must return nothing.
- **AC-3 (claimed ≠ certified).** The `certified_kind` tag is earned from the checker, never
  written on the artifact; an uncertified-but-claimed playbook is `Candidate`, never executes.
- **AC-4 (footing).** CF-001-L1 ∧ CF-001-L2 closed on paper, then formalized by the Lean
  owner, before any embedded-fence execution (Phase 5).
- **AC-5 (custody).** The first irreversible effect (Phase 4) passes the chaos-injection
  custody test: kill between dispatch and witness → `interrupted_unknown_effect`, never silent
  no-op (EC-001).

---

## Non-goals (out of scope by construction)

- **Any authority surface in the frontend.** The frontend measures and certifies; it does not
  authorize, admit, reserve, or spend.
- **Re-specifying the organ chain.** RunRequest-onward is AG's. The frontend cites
  `wicket_seam` / `standing_seam` / `standing_spendability_seam` / `la_seam` and the
  orchestrator's `ChainResult` / `confer_operational_effect`.
- **Witness-validity law** (NQ), **index/registry status** (Spine — parked; *listing is not
  blessing*), **schedule semantics** (Nightshift), **cockpit affordance typing** (Maude).
- **Re-proving typed refusal** (shipped as `confer_operational_effect`).
- The Phase-2-onward execution machinery (parser-for-execution, executor runtime, secrets,
  shell escape, rollback, concurrency, sub-playbook lock semantics) — named as records in
  [governed-playbooks.md](./governed-playbooks.md) §"Out of scope," gated on the footing.

---

## Open questions (handed up, not resolved here)

1. **The Standing-as-judge thesis — RESOLVED (option B, 2026-06-24).** The old
   *"Standing evaluates the RunPlan"* / *"Standing is the judge"* / *"Standing | may run it now
   | Yes"* is retired as **model-wrong** (not just terminology). Corrected doctrine, now live in
   `governed-playbooks.md` + `glossary.md`: external Standing owns the **grant/eligibility**
   fact; AG's `standing_seam` **resolves the referenced grant**; `standing_spendability_seam`
   owns **freshness**; **Wicket** owns the **runtime procedural admission verdict** (admission
   only — *not* execution authority, not a new god object); LA owns **reserve/consume**.
   **Execution permission is conjunctive at the wall (`confer_operational_effect`), not asserted
   by any single "may run" receipt.** No residual decision.
2. **`certified_kind_receipt` gate vs role** — settled as `measurement`; new gate
   (`playbook_certification`) vs existing gate is a Phase-2 `gate_receipt.py` detail.
3. **Reactor-first vs pipeline-first** for the checker — a you-call (build/CI-shaped near-term
   use may pay rent sooner pipeline-first, at the cost of harder early proofs).
4. **Where the canonical IR / parser lives** after Phase 0/1 — deferred.

---

## Ordering

Per [build-phases.md](./build-phases.md): Phase 0 (ledger, paper) → Phase 1 (seal lemmas L1+L2,
paper then Lean — **HARD GATE**) → Phase 2 (spec → certified-kind *measurement*, no effects) →
Phase 3 (RunRequest → Wicket → Standing → LA, observe-only seam test) → Phase 4 (one
irreversible effect, chaos custody) → Phase 5 (embedded fence, live) → Phase 6 (composition) →
Phase 7 (Nightshift). Phase the work by **dangerous seam, not object model**.

---

## Cold-start slices (the in-tree on-ramp, after the move)

Boring on purpose. Each slice produces one measurement and wires nothing runtime. **None of
these touch Wicket/Standing/LA/Executor/ConvergenceFence** — those are cited, not built. No
slice begins before Phase 0 (ledger ratified, resolution targets resolve) is green; Slice 5
(embedded fence) cannot begin before Phase 1 (L1∧L2) closes.

- **Slice 0 — canonical digest.** Input: one restricted-YAML fixture. Output: canonical
  `PlaybookSpec` bytes + `playbook_spec_digest` + a test fixture proving **digest stability**
  (same source → same digest; reject anchors/aliases/dup-keys at parse). *No certified_kind, no
  authority, no chain.* This is the smallest thing that can be wrong and worth being right.
- **Slice 1 — certified_kind measurement.** The composition checker emits a
  `certified_kind_receipt` as a `receipt_role=measurement` GateReceipt (reactor-kind first).
  Proves `claimed_kind ≠ certified_kind` in code: the tag is earned from the checker, never
  written on the artifact. *Still no authority surface (AC-2).*
- **Slice 2 — dependency_closure_digest.** Resolve + digest-pin a local import closure (no
  `latest`). Measurement only.
- **Slice 3 — Wicket consumes the measurements.** Extend `wicket_seam` to bind
  `playbook_spec_digest` / `certified_kind_receipt` / `dependency_closure_digest` as
  **evidence**; Wicket refuses absent/mismatched certification. First time the playbooks layer
  touches the chain — and it touches it as *evidence in*, never authority out. Discharges the
  spine sentence end-to-end: *certification is admissible evidence for Wicket, not authority.*

After Slice 3 the layer is feature-complete for what it owns; everything further (effects,
custody, embedded fence) is AG/Executor-side and gated on Phase 1.
