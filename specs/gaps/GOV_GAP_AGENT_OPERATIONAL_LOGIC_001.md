# GOV_GAP_AGENT_OPERATIONAL_LOGIC_001

(working title: `AGENT_OPERATIONAL_LOGIC_GAPS` — folded into the house `GOV_GAP_*_001` convention)

## Title

AG can **judge and gate** a proposed derivation. It does not yet cause an agent to **operate by constructing, transporting, retaining, and revising** derivations. This gap names the umbrella boundary and the four concrete seams whose closure would graduate "operational logic for agents" from doctrine to witnessed capability — plus one correction that must be pinned as a NON-CLAIM, not a future feature.

## Status

Gap spec — containment vessel. **No invariant, validator, planner, protocol, or runtime check is ratified or authorized by this filing.** It records four candidate seams and one non-claim as handles for review. A record is not authorization to build (per `~/.claude/CLAUDE.md` § YAGNI scope). Each seam earns implementation only when a current task, failure mode, or acceptance criterion justifies it. Marked candidate / non-binding until locally ratified.

## Boundary law (current, accurate as of filing)

> AG today is an **effect gate that refuses unwitnessed action**, plus a **ratified narrow judgment** for what a lawful derivation looks like, plus **one legibility specimen**. It is the substrate an operational logic could run on. The logic is not running: the search, the transport, and the memory-as-typed-custody wiring are the unbuilt half.

Two facts fix this boundary precisely:

1. **Judge ≠ search.** The ratified object (`~/git/lean`, v1.3, *Witnessed Derivation Calculus*, narrow; commit `df9e7b7`, `experiments/no_free_lift_wiring/RATIFICATION-v1.3.md`) makes `Lift K B c` a **defined inductive judgment** over a derivation. It *judges* a proposed derivation; it does **not** search for one. No component in AG walks from witnessed leaves toward a permitted conclusion. "Admissibility Calculus" remains retired (2026-06-03); the narrow successor is experimental-surface only, not 2.0, not public.
2. **Atlas, not actuator.** Per [`docs/doctrine/state_space_atlas_not_machine.md`](../../docs/doctrine/state_space_atlas_not_machine.md): mechanical validation belongs at constitutional authority boundaries; everywhere else the state-space map is an atlas. A planner/search loop is *not* a license to generalize machine-discipline outward — GAP-1's discharge criteria are written to keep the planner producer-replaceable and bridge-inert for exactly this reason.

## Origin

Filed 2026-06-17 after a read-only correspondence audit (AG mechanisms ↔ the Lean admissibility kernels / no-free-lift) and the operational-logic synthesis that followed it. The audit's gradings of the AG correspondences (Authority conjunction, no-free-lift parentage, non-subsidy origin fence, budget monotonicity, custody non-manufacture, witness-invariance as `[implemented instance / convergent evidence]`, **not a verified reduction**) are mirrored in the v1.3 ratification record's "Explicitly NOT claimed" block; the proof→world fence is preserved (a compiled theorem is evidence *into* an operational gate, never the receipt that gate emits).

The seed for GAP-2 is an actual specimen, not a conjecture: the AG-on-AG slice-1 ↔ slice-2 result (`working/witness-agonag-slice2-2026-06-17.md`), where an illegible refusal caused a real inner worker to retry and a *legible* refusal (carrying `retry_disposition=new_authority_required / terminal_scope / message`) caused it to stop and name the remedy. That result is logged in the v1.3 ratification as **`[future candidate]`** — "a sound refusal does not necessarily imply a receiver-legible or continuation-adequate refusal." This gap is the AG-side home for that frontier and its three siblings.

## The umbrella gap

AG can judge and gate a proposed derivation. It does not yet cause an agent to operate by constructing, transporting, retaining, and revising derivations. The four seams below are the unbuilt half. They compose with the shipped half (fail-closed refusal, the standing chain, the origin fence, budget monotonicity) but none is built.

---

### GAP-1 — Witness-guided proof search ("the legs")

**Missing:** a planner that searches from available witnessed leaves toward a permitted operational conclusion. AG has the *judgment* of a derivation; it has no *search* for one.

**Discharged when:**
- planner consumes typed witnessed state, **not prose context as authority**;
- candidate plans are derivation objects (the judged shape, not free text);
- no derivation yields a typed refusal or operator escalation — never improvisational lore;
- planner **cannot invent bridge judgments** (it may conjecture, but a conjectured bridge is inadmissible until witnessed — bridge-inert by construction, per the atlas boundary above);
- search strategy is replaceable without changing admission semantics (the gate judges the candidate, not the searcher).

This is the legs. Everything else that says "agents operate by deriving" depends on this existing.

### GAP-2 — Derivation continuation transport

**Missing:** a protocol for one agent/process to hand off **unresolved derivation state** without handing over persuasive narrative. Not "agents chat" — CLAUDE.md forbids that ("agents don't talk to each other, they talk to the ledger"). A typed continuation object instead:

```text
required conclusion
known witnessed leaves
missing premises
attempted rules
refusal reason
authorized continuation scope
ledger references
```

**Discharged when:** another agent can resume from that object plus the ledger, and **neither peer message nor summary acquires authority by being eloquent**. This preserves "agents talk to the ledger" while allowing distributed work.

**Seed (n=1):** slice-2's legible refusal is the degenerate one-field case of this object — a terminal refusal that carried `retry_disposition` / `terminal_scope` / remedy and successfully steered a real receiver. A continuation object is that, generalized to *unresolved* (not only terminal) state. Specimen, not capability.

### GAP-3 — Typed memory custody (most dangerous open seam)

**Missing:** agent memory is still prose adjacent to the model, while typed custody already exists elsewhere (receipts, ledgers, `receipt_kernel`, the standing chain). The receipt *chain* is typed custody today; the *agent's* memory (the continuity MCP, `MEMORY.md`) is prose, not wired to it. Three things must stay distinct:

- **remembered narrative** — may be wrong;
- **witnessed claim state** — cannot silently inherit authority from narrative;
- **currently admissible operational basis** — cannot silently inherit from either.

**Discharged when:** memory retrieval returns typed claims with witness, scope, clock, consumer, and standing — **or** explicitly returns advisory prose marked with no authority. No third, ambiguous case.

This is the most dangerous seam because everybody will casually call `MEMORY.md` "evidence" the moment nobody is watching — the exact weak→strong laundering (`remembered → witnessed → relied-upon`) that [`docs/doctrine/weak_property_strong_property.md`](../../docs/doctrine/weak_property_strong_property.md) exists to catch. (Recalled memories already arrive wrapped in `<system-reminder>` precisely so they read as background, not instruction; GAP-3 is the typed version of that fence.)

### GAP-4 — Model-independent proposal harness

**Missing:** the gate is producer-independent *in principle*, but there is no live search loop **proving** heterogeneous models propose equivalent derivations under one protocol. **Depends on GAP-1.**

**Discharged when:**
- multiple planners/models emit the same canonical candidate format;
- the same gate judges all of them;
- acceptance does not depend on producer identity **except where authority explicitly requires identity** (the origin fence: reasoning anywhere, effect bound to the proper actor);
- differential tests show models may vary in **search quality** but not in **what counts as lawful**.

This is where "models are interchangeable heuristics" graduates from doctrine to witnessed capability. Until GAP-1 exists, it is doctrine with no loop to test.

---

## Sequencing — claim dependency ≠ build priority

GAP-4 depends on GAP-1, and GAP-1 is the only seam required before AG can *claim* agents broadly **operate by deriving**. Do not read that as build order. Two different orderings are in play and must not be collapsed:

> **Claim dependency:** GAP-1 → the operational-logic claim. (You cannot say "agents operate by deriving" until a planner exists.)
>
> **Risk-driven implementation order:** GAP-3 or GAP-2 may precede GAP-1. (Both have live forcing cases *now*, with no planner.)

The forcing cases for GAP-2 and GAP-3 are already present without any search loop:

- **GAP-2 is live now:** current workers already emit refusals that other workers consume (the AG-on-AG slices). Continuation adequacy is a present property of a shipped path, not a future one.
- **GAP-3 is live now:** agent memory already coexists with receipts and standing. The `remembered → witnessed → relied-upon` laundering path is reachable today.
- **A planner makes GAP-3 *more* dangerous,** not less: it increases how often remembered material gets reused as a candidate premise. Building GAP-1 before GAP-3 installs the engine before the brakes.

So "legs first" is a statement about what you may *claim*, never a license to defer the open memory-authority seam until after building the mechanism that amplifies it. If anything, the amplification argument pushes GAP-3 *earlier*. Build order is a ratification call against live forcing cases — not architectural destiny inherited from the claim graph.

---

## One non-gap worth pinning (NON-CLAIM)

The "tool output cannot become belief" line is **not** a future feature. It is a standing non-claim, and must be recorded as one so it is not mistaken for unbuilt scope:

> **AG does not govern model belief or context uptake. It governs whether claims may acquire operational effect.**

Belief is free; consequence is paid. Tool output still floods the model's context and can become belief; what it cannot do is become *authorized action* without the observation → interpretation → recommendation → authorization → execution bridges ([`docs/doctrine/standing_and_receipts.md`](../../docs/doctrine/standing_and_receipts.md) §5). Blurring belief and effect loses the audience and overclaims the gate. This correction is load-bearing and is recorded here so it does not stay buried in conversation.

## What is NOT in scope of this filing

- Building any of GAP-1..4. Each requires its own forcing case and acceptance criteria.
- Any claim that AG is "an operational logic for agents" *running*. The honest shipped claim is narrower and stronger:

  > **Generative capability without generative authority.**

  Everything shipped supports that today (fail-closed refusal, the standing chain, the origin fence, budget monotonicity, the witness-invariance audit). The operational-logic claim becomes promotable only when the planner (GAP-1), continuation transport (GAP-2), and typed-memory (GAP-3) seams close. Until then: spine, gate, and a deeply judgmental face — legs scheduled.

## Cross-references

- Ratification basis (external, read-only): `~/git/lean` v1.3, `experiments/no_free_lift_wiring/RATIFICATION-v1.3.md` (*Witnessed Derivation Calculus*, narrow; refusal-legibility logged `[future candidate]`).
- Legibility specimen: `working/witness-agonag-slice2-2026-06-17.md` (slice-1↔slice-2 before/after).
- [`docs/doctrine/weak_property_strong_property.md`](../../docs/doctrine/weak_property_strong_property.md) — the generator (GAP-3 is its memory instance).
- [`docs/doctrine/state_space_atlas_not_machine.md`](../../docs/doctrine/state_space_atlas_not_machine.md) — keeps GAP-1's planner atlas-bounded.
- [`docs/doctrine/standing_and_receipts.md`](../../docs/doctrine/standing_and_receipts.md) — the bridge chain the NON-CLAIM rests on.
- `GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001.md` — adjacent (decomposition completeness is a sibling of derivation completeness).
