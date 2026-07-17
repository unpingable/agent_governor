# GOV_GAP_ANTICIPATORY_DECISION_PACK_001: Anticipatory Governance — Human Over the Loop

## Status

Gap spec — containment vessel. **Nothing here is ratified or authorized by
this filing.** A record is not authorization to build (per `~/.claude/CLAUDE.md`
§ YAGNI scope). Candidate / non-binding until locally ratified.

**Provenance:** operator, night of 2026-07-15 ("I figured out what's bugging
me with the gov loop"); filed 2026-07-16. Sibling spec:
`GOV_GAP_STAGED_OPERATIONAL_AUTHORITY_001.md` (the ops instantiation).

## Problem

The gov loop is not full-auto because it (correctly) gates in the human. But
the human's role is pinned at the wrong time: **runtime operator** instead of
**design-time legislator**. The current shape is

> agent proposes → governor asks → human answers → agent acts.

The missing mode is anticipatory:

> human defines the questions, admissible answer space, evidence
> requirements, and escalation boundaries **ahead of time** → agent later
> instantiates that policy **from evidence** → governor checks the
> instantiated answers → agent acts.

Not "human out of the loop" — **human over the loop**. The distinguishing
law: at runtime the agent never *invents* answers. It fills out the survey
from repository state and produces evidence bindings:

```text
Question:    Does this change alter the public API?
Answer:      No
Evidence:    exported-symbol diff is empty        (governor-verified pointer)
Consequence: patch release path permitted
```

If the evidence does not fit a predefined answer, or the agent discovers a
question nobody anticipated, it stops. **Novelty is the escalation trigger.**
Novelty is not a failure of automation; it is a first-class state that routes
into governed inquiry (NQ / docket) instead of being papered over with
increasingly confident guesses.

## The mode ladder (naming, so we stop conflating them)

- **Interactive governance** — unexpected or genuinely novel decisions;
  the current loop. Stays.
- **Anticipatory governance** — previously legislated decisions instantiated
  from current evidence. THIS GAP.
- **Staged operations** — different purposes, evidence, and authority at
  each phase of an operational response. Sibling gap.

## What exists (census 2026-07-16 — most of the machine is built)

The operator's own caveat ("we're 90% of the way there and I've just named
the destination") survives audit. Parts inventory:

| Piece of the destination | Existing surface |
|---|---|
| Questions + admissible answers + validation | `intent_compiler.py` — `IntentFormSchema`, `FormField`, `FieldOption`, `validate_response`; content-addressed schemas; mode-gated form policy |
| Novelty → typed classification | `intent_compiler.EscapeClassification` (schema_violation / new_constraint / waiver_candidate / clarification_needed); scars action-level novelty gating (`scars.py` fingerprints); `admit` Unknown registry (`admissibility.py` — Severity, ResolvableBy) |
| Evidence kinds per requirement | Evidence Type Validation (Layer 3, `required_evidence_kinds` on PolicyEntry); evidence gate custody scoring; `ClaimDefinition`/`ProofRequirement`/`ProofEvidence` (ops governor) |
| Pre-legislated permitted/forbidden action doctrine | playbooks: `PlaybookSpec`→`CertifiedPlaybook`, `RationCard` (absence-restrictive allowlists, locked axes), `QueuedPlaybook` operator_approved latch — candidate substrate, deliberately inert |
| Derived permission containment | S7 predicate (`execution_request ⊆ cited_ration`, load-bearing); scope contracts; `deployment_profiles.py` authority classes + capability tokens |
| Legislated precedent | `docket.py` / `rule` / `precedent` — operator rulings as reusable records |
| Static-analysis substrate | `constraint_gate.py` (Z3 sidecar); `constraint_compiler.py` pre-execution projection; `chain_gate.py` composition-aware gating (GOV-GAP-CHAIN-001, shipped) |

Adjacent but distinct: `GOV_GAP_AGENT_OPERATIONAL_LOGIC_001` GAP-1 is
witness-guided proof *search* (constructing derivations). This gap is
narrower and cheaper: *instantiating pre-legislated answers* from evidence.
No search; a pack is a closed decision table, not a derivation space.

## What needs building (the actual 10%)

### Seam 1 — the pack artifact

`AnticipatoryDecisionPack`: a content-addressed, versioned, operator-ratified
artifact binding, per question:

- admissible answer classes (closed set — allowlist discipline per
  `feedback_allowlist_authority_blocklist_detection`: novel answer → typed
  refusal, never best-effort);
- **evidence requirements per answer** (which evidence kinds, verified how);
- **derived permissions per answer combination** (what the verified answers
  authorize — expressed in existing containment vocabulary: ration axes,
  scope contracts, capability tokens; the pack does not mint a new
  permission algebra);
- constraints (test/budget/scope/dependency/deployment limits);
- hard refusals and escalation rules.

The project supplies the instance; AG evaluates it. This is a governor
primitive, not project prompt lore.

### Seam 2 — evidence-instantiation (the genuinely new mechanism)

At runtime, an answer is admissible **only when bound to governor-verified
evidence of the declared kind**. NLAI applies with full force: the agent
provides pointers; the governor produces the receipts; an agent-asserted
answer with no fitting evidence binding is a typed refusal, not a warning.
`intent_compiler.validate_response` today checks that an answer is
*well-formed*; nothing checks that it is *evidenced*. That check is the gap.

**Structural constraint (anti-duplicate-authority):** a survey answer is
just another claim. `answer → evidence → authority` is the same judgment as
the existing `claim → provenance → admissibility`; instantiation MUST reuse
the claim/evidence machinery (typed claims, evidence kinds, receipts), not
grow a parallel evidence system with its own vocabulary. If the pack needs a
binding the claim machinery cannot express, that is a claim-machinery gap to
file, not a fork to build.

### Seam 3 — the novelty fence

Closed-world at two levels: (a) a question the pack does not contain, and
(b) evidence that fits no admissible answer of a contained question. Both
route to escalation (docket case / operator), carrying the offending
question/evidence verbatim (per the origin-fence idiom: refused-X ≠
refused-Y). The fence is what makes "full auto" honest — the automation's
boundary is legible, typed, and immutable at runtime.

### Seam 4 — doctrine lint (static, pre-deploy)

Governance you can lint. Analysis over the pack, before any run:

- questions with no admissible evidence path (unanswerable by construction);
- evidence classes that authorize nothing (dead weight);
- contradictory grants; grant *combinations* yielding unintended authority
  (compose with `chain_gate`);
- remediation/permission paths with no escalation edge;
- unreachable answers.

Same move the Lean work keeps making: compile the policy once, execute it
many times. Z3 sidecar is the natural substrate; not committed here.

### Seam 5 — decay (the anti-YAML-burial clause)

The named failure mode of every prior "full auto": *someone buried the human
judgment in a YAML file and stopped checking whether reality still matched
it.* A pack must carry revalidation semantics — TTL/volatility class on its
factual premises (existing `ttl.py` machinery), and drift detection when
instantiation-time evidence systematically diverges from the pack's
legislated assumptions. A stale pack degrades to interactive mode; it never
silently keeps spending.

The pack's lifecycle shape is a **certificate**, not eternal configuration:
scope, issuance conditions, freshness, review cadence, revocation. The
runtime question is not only "was this answer evidenced?" but "**is this
legislation still entitled to govern?**" — the doctrine itself is
evidence-sensitive. (A serialized pack is a compiled representation of a
reviewed policy whose validity can expire; the YAML is never the authority.)

## Seam 6 — challenge separation (added 2026-07-16, second operator capture)

> **Proposal does not carry its own adjudication.**

The runtime law: **an agent may not exercise derived authority from a
proposal it has not subjected to an explicit challenge pass.** Advisory work
needs no such ceremony — "trust but challenge" is operator craft there, and
formalizing every thinking technique is a monastery with YAML. The law
activates precisely when the same actor interprets evidence, chooses the
frame, derives permission, and would exercise it — the spot where an
imported assumption becomes authority without ever appearing as a decision.

**Schema consequence (pack artifact, Seam 1):** the instantiated pack keeps
four record kinds separate, so a rejected recommendation cannot take its
valid observation down with it:

- `findings` — pressure points identified (observations; survive rejection);
- `recommendations` — proposed dispositions;
- `challenges` — the hostile pass: assumptions the proposal depends on;
  strongest admissible competing interpretation; any doctrine/boundary the
  recommendation would relax; evidence that would REVERSE it; whether the
  evidence fits no registered answer class (novelty fence tie-in, Seam 3);
- `dispositions` — final adjudication of each challenge.

**Authority derivation consumes the adjudicated pack, never the raw
proposal.** First pass proposes and prefills; second pass challenges the
frame; only the adjudicated artifact reaches the permission derivation.

**Independence is proportional to the authority delta** (a ladder, not a
uniform mandate — same-agent self-critique is useful but is NOT
independence; models defend their own decomposition while generating
objections):

| Authority delta | Challenger independence |
|---|---|
| testimony-only work | same agent, separate challenge phase |
| reversible low-impact action | separate context or agent role |
| guarantee expansion / production authority | independent agent or model; human adjudicates unresolved novelty |
| irreversible or constitutional action | proposer is not the final signer, full stop |

Without the ladder, "challenge" degrades into a decorative paragraph the
proposing agent writes before approving itself — corporate risk assessment,
but faster.

**Prior art already in the estate (recognition, not invention):** the A-1
runtime-admission decision packet ran this exact pipeline with a human
terminal (drafted → Opus-refute found 2 FATAL → amended → operator ruled;
`09104ba`→`401ba69`) and its findings survived its refuted recommendations
because they were recorded separately. `ActorOutputNormalizer` (playbooks) —
actor cannot green its own gate. `oracle_independence` (receipt-kernel
constitutional invariant). Dissent ledger — objections are first-class and
gate commits. `quorum_ext` two-man rule. `independence.py` anti-cheat
scoring. The Opus-refute/codex-exec HIGH-checkpoint practice
(`memory/feedback_codex_for_adversarial_review`). This seam is what those
become when the adjudicator is no longer always the operator.

**Insertion map (recorded, not applied):** the capture names three landing
points — (1) the governed-loop contract (proposal → challenge → adjudication
→ permission derivation), (2) this pack schema, (3) an authority rule
(guarantee-typed actions require challenger independence per the ladder).
Item (2) is absorbed here. Items (1) and (3) touch `docs/loop-protocol.md`
and gate policy — **ratified/custody-affecting surfaces; each needs its own
ruling at build time.** Named so the retrofit cost is visible; not amended
by this filing.

## Acceptance criteria (for an eventual build; none scheduled)

1. A pack with one question, two admissible answers, distinct evidence
   requirements, and distinct derived permissions: agent run under answer-A
   evidence receives exactly answer-A permissions (containment-checked), and
   a forged/absent evidence binding is refused with a typed reason.
2. Novel question and non-fitting evidence each produce an escalation record
   carrying the novelty verbatim; nothing proceeds.
3. Lint catches a seeded contradictory-grant pack and a seeded
   no-evidence-path question before any runtime.
4. An expired pack premise flips the affected questions back to interactive;
   receipts show the degradation.
5. Mutation probe: removing the evidence-binding check makes test 1 fail.
6. Challenge separation: a permission derivation offered the raw
   (unadjudicated) pack refuses by type; a rejected recommendation leaves
   its findings intact and queryable; a guarantee-typed derivation whose
   challenge record names the proposer as challenger is refused
   (independence ladder enforced at the top rung).

## Non-goals

- **No new effect authority.** Packs derive permissions already expressible
  in ration/scope/capability vocabulary; anticipatory mode changes *when*
  the human decides, never *how much* an agent may do.
- Not a replacement for interactive governance; the ladder keeps all rungs.
- No runtime inference of "what the operator would have wanted" — that
  slippery slope is precisely what the pack exists to kill.
- Packs do not self-modify; amendment is an operator act (docket/ruling).
- No build until a forcing case; this filing is the handle for review.

## Composes with fail-logical (verifier, named 2026-07-16)

The verifier's fail-logical surface (`~/git/verifier/VERIFIER_FAIL_LOGICAL_GAP.md`,
named the same week) inserts the missing rung in this spec's escalation
ladder. As filed above, a pack routes: evidence fits an admissible answer →
proceed; novelty → escalate to the human. Fail-logical adds the middle case:
*no legislated answer, but the answer is derivable from the pack's
constraints + admitted facts* — a bounded formal obligation the verifier can
decide (`entailed`/`refuted`), whose own machinery failures remain closed
(UNKNOWN = refusal). The full ladder becomes:

    legislated answer (pack) → derivable answer (fail-logical) → human

This narrows Seam 3's escalation volume without weakening it: only questions
that cannot even be FORMED without a new premise page the human
(`RequiresJudgment`), and machinery failures page as machinery
(`indeterminate`). Custody stays split: the pack legislates the admissible
world; AG constructs the typed obligation; the verifier owns the proof
machinery and never invents premises. Cross-ref only — neither surface's
construction gate is altered by this note.

## Open questions

- **OQ-A:** pack home — in-repo artifact (`.governor/packs/`) vs. sibling of
  playbook specs? Relation to `IntentFormSchema` (extend vs. new artifact
  consuming it)?
- **OQ-B:** who verifies evidence bindings — existing verifiers per evidence
  kind, or a dedicated instantiation gate emitting one receipt per answer?
- **OQ-C:** is a ratified pack custody-affecting per se (it pre-authorizes
  permissions), and does ratification require the C2 standing-chain shape?
- **OQ-D:** relation to the orientation family — an anomaly score may make a
  pack question *salient* but must not count as evidence for its answer
  (orientation ≠ evidence; see `working/candidate-orientation-crosswalk-2026-07-16.md`).
