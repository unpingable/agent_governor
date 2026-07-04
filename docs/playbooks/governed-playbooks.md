# Governed Playbooks

> **Status:** design capture, Phase 0 (pre-implementation). **Provisional** — the
> whole construction is gated on the ConvergenceFence hostile-contract proof
> (see [build-phases.md](./build-phases.md) Phase 1). Nothing here is certified,
> ratified, or implemented. This is a record for review, not authorization to build.

Captured 2026-06-23 from a multi-model design conversation. The job of this doc is
to preserve the sharp distinctions before they smooth into generic "workflow
automation." If you find yourself reading this as "Ansible but governed," stop: the
Ansible resemblance is **UX bait**, and the object is **governed procedure
admission**.

---

## Problem

The Agent Governor frontend needs a primitive. Not "agent UI," not "prompt library,"
not "Ansible with vibes." The missing noun is **declarative reusable procedures whose
whole job is to make an action admissible *before* execution.**

| Thing             | What it is                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------ |
| Prompt            | Request-shaped desire                                                                             |
| Script            | Execution-shaped mechanism                                                                        |
| Ansible playbook  | Desired-state-ish automation bundle                                                               |
| **Governor playbook** | **Admissible action checklist with custody, scope, witnesses, refusal paths, and spend semantics** |

Ansible had the right ergonomic insight — operators want named, repeatable,
declarative operational moves. AG needs the thing Ansible does not have: every
operational move must carry **declared authority, bounded effects, evidence
requirements, refusal semantics, and receipt custody.**

> The frontend is not a command surface. It is a procedure admission surface.

Mean version: *Ansible for grownups, where YAML does not magically become permission.*

---

## What a playbook is

> A playbook is a reusable action claim whose steps declare what authority they need,
> what evidence they must collect, what state they may change, what refusal means, and
> what receipt proves the run.

A stored playbook is **inert**. A beautifully typed, signed, promoted playbook sitting
in the store is still a recipe card. It does not get to cook dinner unsupervised
because it has a hash and good vibes.

The adjective is load-bearing. The primitive is **Governed Playbooks**, not playbooks —
a tiny architectural hard hat.

---

## The executable unit is not the playbook

The playbook by itself is inert. The thing that actually runs is:

> certified playbook spec **+** live standing resolution **+** instantiated run plan
> **+** fresh witnesses **+** spend authority

Conflating "the artifact" with "the executable" is the first and most repeated mistake.
Keep them apart at every layer.

---

## Four-layer object model

```
1. PlaybookSpec      inert authored artifact: text, hash, claimed_kind, provenance,
                     typed input constraints. No authority.
2. CertifiedPlaybook PlaybookSpec + composition receipt: certified_kind,
                     structural check result. Certified ONLY over its input domain.
3. RunRequest /      CertifiedPlaybook + bound inputs + target scope + actor +
   RunPlan           state assumptions + locked dependency closure.
                     >>> This is the object Wicket admits (runtime verdict),
                     >>> citing standing-reference + spendability + certification. <<<
4. RunInstance       executed RunPlan: step receipts, witnesses, spends, refusals,
                     final claim, custody state.
```

The critical move, stated once and never weakened:

> **The runtime verdict is over the RunPlan, not the PlaybookSpec — and no single organ
> owns it.**

The live question is not "may this playbook exist?" It is "may *this principal* execute
*this certified artifact* with *these inputs* against *this target* under *current
conditions*?" — and that permission is **conjunctive and non-atomic**. There is no
`StandingAdmission`-style "may run" receipt to wave. It holds only when *all* line up:
external Standing owns a **grant/eligibility basis**, AG's `standing_seam` **resolves the
referenced grant**, `standing_spendability_seam` finds it **fresh**, the frontend
**certification measurement** classifies the kind, and **Wicket** issues the **runtime
procedural admission verdict** over the RunPlan. Evaluating the Spec instead of the
RunPlan is how the store becomes authority and promotion becomes a skeleton key.

---

## The matrix: authorship ≠ standing

A playbook carries at least these distinct facts. The trap is letting any *durable*
fact impersonate a *live* one.

| Axis                 | Question                                          | Durable?                |
| -------------------- | ------------------------------------------------- | ----------------------- |
| Authorship           | Who wrote or proposed this?                        | Yes                     |
| Promotion            | Has this artifact cleared review/signing?          | Yes-ish                 |
| Certified kind       | What composition law did it prove against?         | Yes, for that version   |
| Standing (grant basis) | Does a referenced grant/eligibility basis resolve? | **No** (live)         |
| Run admissibility    | Is this run procedurally admitted now (Wicket)?    | **No**                  |
| Effect authorization | May this step mutate/send/spend?                   | **No**                  |

Authorship is immutable metadata. Promotion is a one-time receipt. Standing is a live
query. The intuitive mapping "user-created = safe, governor-proposed = needs review" is
**wrong in both directions**: it under-gates durable user playbooks running against
drifted state, and over-suspects promoted governor playbooks that already cleared the
gate.

The master demon, which every failure mode below is a costume of:

> **Past validity is not present authority.**
> YAML is not standing. Promotion is not standing. History is not standing.
> Schedule is not standing. Presence is not standing. The run gets standing or it doesn't.

---

## claimed_kind vs certified_kind

Two tags, different times, different authorities, a gate between them. **Never the same
tag wearing two hats.**

```
claimed_kind    = author says "I intend this to be a pipeline."   (a proposal; input to the check)
certified_kind  = checker says "this satisfies pipeline invariants." (a signing receipt; output)
```

The admission gate (Wicket) dispatches on **certified_kind only** — never on a field the
artifact wrote about itself. Otherwise a pipeline-kind playbook tags itself "episodic" to route around
the structural proof. The claim proposes; the proof disposes; the gate between them is
the whole architecture.

An uncertified-but-claimed playbook sits in **Candidate** (Candidate / Quarantined /
Refused / Admitted). The mistake — the same mistake as every other seam — is letting
Candidate execute on the strength of its claim. *Uncertified means not-yet-Admitted
means no standing, full stop. No provisional "los dos."*

---

## The organ chain

```
RunRequest → Wicket → Standing → LA → Executor → Continuity
                 (NQ witnesses across)   (Nightshift / Maude trigger in)
```

**Every arrow is a bridge that needs a typed receipt, not a hand-off that needs a
convention.** Five clean verbs with four un-typed seams is worse than three verbs with
typed bridges — the cleanliness hides the joints. The organ map is a separation of
powers, and separations of powers fail at the seams between the powers.

| Organ      | Verb                                                              | Authority? |
| ---------- | ----------------------------------------------------------------- | ---------- |
| Spine      | what can be **found / read** (read plane)                         | No (C4)    |
| Continuity | what can be **relied on** (recorded substrate)                    | substrate  |
| Maude      | human **cockpit**: render (from Spine) + adjudicate + trigger     | No         |
| Wicket     | runtime **admission verdict** over RunRequest/RunPlan (procedural) | gate (procedural admission only; **not** execution authority) |
| Standing   | referenced **grant resolves** / grant basis exists                | No local execution authorization |
| LA         | is scarce effect **capacity** reserved / consumed?                | turnstile  |
| NQ         | what was **witnessed / refused**?                                 | No         |
| Nightshift | what **triggered** a future candidate? (machine)                  | No         |
| Executor   | what **effect happened**?                                         | did        |
| Registry   | **index** of inert artifacts (a Spine concern; no status)         | No         |

Mnemonic: *YAML is the bait, IR is the specimen, Wicket is the bouncer who issues the
admission verdict, Standing is the badge-check that the referenced grant is real (not the
judge of whether you may act), LA is the turnstile, Nightshift is the alarm clock, Maude
is the cockpit, Continuity is the cop with the notebook, NQ is the witness who saw one
thing and would like everyone to stop exaggerating.* No organ is the judge — execution
permission is the **conjunction** at the wall, not any one verb.

The anti-bypass rule: **nothing hits Standing as a naked object.** Every RunRequest
carries a fresh `WicketAdmission` receipt; Standing emits `StandingReferenceResolution`
(the referenced grant resolves — *not* an execution admission); LA reserves only against a
fresh signed grant. No vibes between organs.

> Standing reference resolution verifies that a referenced standing grant resolves; it is
> not execution authorization. "May run now" is Wicket's verdict; the grant
> (effect/budget/revocation) is external Standing's; freshness is the spendability seam's.

---

## NQ: recorder vs precondition-witness

NQ has no authority, but its witnesses can become admissibility inputs. Two roles on
opposite sides of the authority line:

- **Recorder** (downstream of an effect): testifies what happened, attaches to the
  RunInstance. No authority — nothing depends on it to *permit* anything. Safe.
- **Precondition-witness** (gates a step): a witness consumed as typed input to decide
  whether the run proceeds. Now it is load-bearing, and inherits every seam problem —
  freshness and claim-scope typing.

Two doctrines that bite here:

> **witnessed ≠ currently true.** A witness is a statement about a past instant
> presented as a present fact. `service_active` was true when NQ observed it; the step
> proceeds later trusting it; the service died in between. The witness is *honest* and
> the inference is *wrong*. (Cousin of `signed ≠ witnessed`.)

> **A witness may only satisfy what its witnesses can testify.** `service_active`
> witnesses *process liveness*, not "healthy and publishing correct data." Green
> checkmarks are tiny fraud engines.

Also: **observation can be effectful** (an API read increments counters, reading email
marks it read, a probe trips an IDS). NQ's own witness-gathering needs effect-typing.
And: **missing witness is silence; refusal witness is testimony** — a typed
`CannotTestify` receipt is real evidence about the epistemic state of the run.

> **NQ may testify. It may not promote its testimony into permission.**

---

## Reactor vs Pipeline (no unifier — a partition with a bridge)

Two composition laws, and they do **not** melt into each other:

- **Reactor** — *conditional convergence*. Fires when state matches, drives toward a
  declared state, idempotent, replayable. Most of ops. Continuity is the natural witness.
- **Pipeline** — *typed dataflow*. Threads an artifact forward through stages; safety is
  a property of the *flow* (acyclic, forward-only), provable structurally without ever
  running. Build/CI. A Lean-style invariant is the natural witness.

The shared leaf is **not** `StepContract`. It is a **BoundaryContract** (preconditions,
authority requirements, allowed effects, required witnesses, emitted terminal outcome,
custody behavior, freshness/reuse semantics). A step is one implementation of a
boundary; a reactor is a *sub-algebra behind a boundary*, not secretly a step.

**Do NOT assume reactor-step == pipeline-step. That bridge is unproven and load-bearing.**
The crossing object is the **ConvergenceFence** — see
[convergence-fence.md](./convergence-fence.md). Everything downstream of that proof is
provisional until the three hostile contracts close on paper.

---

## Format

> The format people edit is not the thing Standing trusts.

```
authoring source  →  parser/checker  →  canonical typed IR  →  certification receipt
(restricted YAML)                       (JSON / CBOR, hashable)
```

- **Authoring:** a *restricted* YAML dialect — no anchors, no aliases, no custom tags,
  no implicit booleans, no duplicate keys, no merge keys, explicit schema, canonical
  parser only. YAML as a friendly skin over a typed AST.
- **Custody:** canonical typed IR (JSON/CBOR/protobuf-style), hashable. Standing trusts
  `playbook_spec_digest`, `parser_version`, `certified_kind_receipt`,
  `dependency_closure_digest`, `run_plan_digest` — never "this YAML said it was fine."
- **Interchange:** XML only *later*, for document-grade archival/export. Never the
  primary authoring path. (XML canonicalization/signature history is a haunted subway.)

---

## Derived playbooks (compression laundering)

Agents may infer a procedure, but **inference does not confer authority to run it.** A
derived playbook is a Candidate (`executable: false`), and it is already a *claim*: by
naming three actions "a deploy," the agent asserts a boundary, an ordering, a causal
claim, and that some omissions are irrelevant.

So a derived candidate must carry the receipt set it was derived *from*, and promotion
must be reviewable against the **raw observations**, not just the proposed name:

```
derived_from: { receipts: [run_abc, run_def, run_xyz] }
compression_claim:
  proposed_boundary: "repair user systemd service"
  included_steps: [...]
  excluded_steps: [...]
  ordering_basis: observed_order | inferred_dependency | user_supplied
  observed_always: [...]
  observed_sometimes: [...]
  possible_accidental_steps: [...]
status: candidate
executable: false
```

Otherwise "derived" is just "fabricated with a citation," and the agent compresses
accidents into procedure (that is how organizations are born, tragically).

**Boundary disputes route to Maude (adjudication), not Standing.** "Is this derived
compression a valid boundary?" is a *contested decision*, not a `may-run` resolution.
Maude owns it; the governor does not build compression-adjudication inline.

---

## Maude: the cockpit, not the god-surface

Maude is the **human-facing render-and-input plane** — the cockpit where a human sits to
drive runs. It is a *client of the organs*, not a replacement for them. Three wires in,
one verb of its own:

- **renders** what Spine makes legible (read plane → display),
- **triggers** runs — and a human click is a **candidate activation**, flowing the
  *identical* path machine triggers flow: candidate → Standing (`may`) → LA (capacity)
  → Executor (`did`),
- **adjudicates** the contested decisions only humans adjudicate (derived-playbook
  boundaries, refusal review, waivers, unresolved standing disputes).

The trap, sharp: **"a human clicked it" feels like authority and isn't.** A TUI is the
maximum density of `presence ≠ delegation` — the human is *right there*, hands on keys,
and every instinct says "obviously they authorized it." But clicking "run" is a
*proposal*. It still crosses Standing, still binds to a **frozen RunPlan digest**, still
re-resolves live. The cockpit does not fly the plane; it sends inputs to the surfaces
that do, and those surfaces can refuse.

If Maude adjudicates *and* triggers *and* authorizes undifferentiated — because they're
all "stuff I do at the terminal" — it stops being an organ and becomes a **god-surface**,
the one thing the federation exists to forbid. The implementation is easy (it's a TUI).
The *typing of its affordances* is the whole game: this button adjudicates, this one
triggers (→ candidate → Standing), this one displays (← Spine), and **none of them
authorize**, because authorization is not a button — it is Standing's response to the
candidate the button produced.

> **Input at Maude is proposal, not authority.** (See ledger MC-001.)

**Open design-taste call (yours, not the architecture's):** whether adjudication and
trigger share a screen. A human who just *ruled a boundary valid* and then *launches a
run* in the same view will conflate "I decided this is valid" with "I authorized this to
execute" — two distinct verbs the architecture keeps separate but the UI can blur. If
they share a pane, that pane is the one place that needs a *visible* seam.

---

## Spine / read-plane note

Governed Playbooks are **not** a Spine feature. They are an AG execution-admission
design spanning Wicket / Standing / LA / NQ / Continuity / Nightshift / Maude / Executor.

Spine may **index, orient, package, or later publish** stable playbook doctrine, but it
must not own certification, standing, execution authority, witness validity, or spend
semantics. The "Playbook Registry" this design keeps reaching for **is a Spine concern**,
governed by Spine's C4 (*presentation must not collapse into authority*):

- **index** — mutable, navigational, **carries no status**. Lists playbooks; listing is
  not blessing. (This is "registry finds but doesn't bless," now with a doctrine.)
- **edition** — a curated, readable presentation of a set of certified specs.
- **stele** — the durable, hash-pinned certified PlaybookSpec.

"Presence-in-the-index must not impersonate authority" is the same demon as
claimed≠certified and witnessed≠currently-true. Spine is the organ that catches that
costume — and the boundary was drawn (in Spine's `DOCTRINE.md`) before the need arrived.
**Do not build a new registry; check whether the library is a Spine edition.** Spine is
currently **parked (backburner)** — do not reactivate it by accident.

These docs may be indexed by Spine later, but their authority lives in the
AG/Wicket/Standing/LA/NQ receipts, not in presentation.

---

## Out of scope for first implementation

Named here as records (candidate, non-binding), so forgetting them later doesn't create
retrofit cost — **not** as authorization to build:

- parser / canonical IR, registry, scheduler integration, executor runtime
- secrets-as-capabilities (scoped, receipted, step-bound, never in receipts)
- typed shell escape hatch (untyped shell taints the enclosing playbook)
- rollback vs compensating-action vs abort vs quarantine (no step advertises rollback
  without a pre-effect restoration witness)
- concurrency / resource leases beyond the LA reservation sketch (TOCTOU)
- partial-execution custody states, including `interrupted_unknown_effect`
- principal / delegation chain typing (`human_present ≠ human_authorized_this_effect`)
- multi-governor contention (LA as the shared lockbox of scarce things)
- parameter-binding as a privilege-escalation surface (a certified playbook is only
  certified over its **input domain**)
- import / sub-playbook lock semantics (no `latest`, digest-pinned, closure-resolved,
  no transitive standing)

The footing (ConvergenceFence hostile contracts, Phase 1) gates all of it.

---

## Related docs

- [invariant-ledger.md](./invariant-ledger.md) — the seam/effect-boundary invariants.
- [convergence-fence.md](./convergence-fence.md) — the load-bearing bridge.
- [build-phases.md](./build-phases.md) — phasing by dangerous seam, not by object.
- [glossary.md](./glossary.md) — terms.
