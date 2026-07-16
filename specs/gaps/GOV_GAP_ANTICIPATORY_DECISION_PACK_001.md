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

## Non-goals

- **No new effect authority.** Packs derive permissions already expressible
  in ration/scope/capability vocabulary; anticipatory mode changes *when*
  the human decides, never *how much* an agent may do.
- Not a replacement for interactive governance; the ladder keeps all rungs.
- No runtime inference of "what the operator would have wanted" — that
  slippery slope is precisely what the pack exists to kill.
- Packs do not self-modify; amendment is an operator act (docket/ruling).
- No build until a forcing case; this filing is the handle for review.

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
