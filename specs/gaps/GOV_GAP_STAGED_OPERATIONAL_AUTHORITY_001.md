# GOV_GAP_STAGED_OPERATIONAL_AUTHORITY_001: Staged Remediation — Authority Per Phase, Witness Per Transition

## Status

Gap spec — containment vessel. **Nothing here is ratified or authorized by
this filing.** Candidate / non-binding until locally ratified.

**Provenance:** operator, night of 2026-07-15; filed 2026-07-16. Sibling:
`GOV_GAP_ANTICIPATORY_DECISION_PACK_001.md` — an ops incident-class doctrine
is an anticipatory pack whose derived permissions are the stage grants below.

## Problem

Operational remediation is one activity with three different purposes,
evidence profiles, and blast radii — and today it would run under one
undifferentiated authority. The correct shape:

1. **Restore service** — narrow, reversible, known-safe actions (rollback,
   restart, failover, shed load, disable feature, restore last-known-good).
   Optimize for recovery, not understanding. Tight time and blast-radius
   bounds.
2. **Investigate** — mostly read-only scope expansion (logs, traces, diffs,
   topology, recent changes, dependency state). Produces a failure
   hypothesis bound to evidence. **Restoration success does not prove the
   diagnosis.**
3. **Prevent recurrence** — modify code/config/infrastructure, test, stage,
   deploy — under a separate grant, or return to the human when the proposed
   repair falls outside pre-legislated classes.

The critical law: **each stage gets its own authority and each transition
requires the prior stage's witness.** Otherwise "permission to restart the
service" quietly becomes "permission to rewrite the scheduler and deploy it
globally" — exactly the authority laundering the constellation exists to
murder. And recovery must be able to **terminate successfully without a
speculative root-cause fix** — closing an incident at stage 1 is a legal
terminal state, not an incomplete run.

Candidate primitive vocabulary (names are handles, not commitments):

```text
RecoveryGrant        permits bounded restoration
RecoveryReceipt      records service state and interventions
InvestigationGrant   permits evidence acquisition
FailureFinding       binds diagnosis to evidence
PreventionGrant      permits a classified remediation path
DeploymentReceipt    proves validation and rollout constraints
```

The governor advances between stages only when the prior stage produced the
required witness.

## What exists (census 2026-07-16)

| Piece | Existing surface |
|---|---|
| Incident lifecycle vocabulary | `ops_governor/types.py` — `IncidentStatus` (DETECTED→ACKNOWLEDGED→INVESTIGATING→IDENTIFIED→MITIGATING→RESOLVED→POSTMORTEM→CLOSED), `IncidentEvent` timeline. **Bookkeeping only: transitions record, they do not gate authority.** |
| Evidence-bound claims | ops `ClaimDefinition` / `ProofRequirement` / `ProofEvidence`; `PolicyPack` |
| Bounded-action verifiers | ops `TimeWindowVerifier`, `BlastRadiusVerifier`, `PreconditionChainVerifier`, `RunbookVerifier` |
| Phase + budget machinery | `phase_control.py` (phases with budget locks, novelty debt) |
| Scope escalation ladder | `scope.py` — expanding rings, widen exactly one axis per request, escalation receipts |
| Authority classes / tool typing | `deployment_profiles.py` (AuthorityClass, CapabilityToken, RateLimit); `nightshift_adapter.py` (AuthorityLevel, BlastRadius, ToolClass) |
| Grant containment predicate | S7: `execution_request ⊆ cited_ration` (load-bearing, single verified read) |
| Refusal-by-type precedent | origin fence type split (`OperationalConsumed` vs `DemonstratedConsumed` — the wrong type *cannot* confer effect, not merely may-not) |
| Two-man rule / severity gating | `quorum_ext.py` |
| Drift-gated retry | `governed_activity.py` (etag/fingerprint drift verdicts between attempts) |

So: the incident FSM exists, the containment vocabulary exists, the
witness/receipt machinery exists. **What does not exist: any grant that is
scoped to a stage, and any transition that demands a witness.**

## What needs building

### Seam 1 — stage-typed grants

Grants whose permitted-action class is a function of incident stage:
recovery-class (reversible, enumerated, time-boxed), investigation-class
(read-mostly; new scope, no new mutation), prevention-class (classified
remediation paths only). Expressed in existing containment vocabulary
(ration axes / scope contracts / capability tokens), not a new algebra.
Preferred enforcement idiom is the type split, not the boolean guard: a
recovery-stage session should be *unable to represent* a prevention-class
request (R4-adjacent; see `working/rulings-pending-inexpressibility-2026-07-15.md`).

### Seam 2 — transition witnesses

Stage N+1's grant is mintable only against stage N's required witness:

- Recovery → Investigation: `RecoveryReceipt` (service state, interventions
  taken, reversibility record).
- Investigation → Prevention: `FailureFinding` — diagnosis **bound to
  evidence**, adjudicated under the testimony shape already ratified
  (`required ≤ asserted ≤ authorized`; NQ owns the authorized ceiling,
  the plan declares the required floor, AG adjudicates).
- Prevention → done: `DeploymentReceipt` (validation + rollout constraints
  observed).

Restoration success is *typed apart* from diagnosis: a `RecoveryReceipt`
can never satisfy the `FailureFinding` requirement.

### Seam 3 — legal terminals

`RESOLVED`-at-stage-1 (recovered, no prevention attempted) is a first-class
successful terminal with an honest receipt ("recovered; cause not
established"). No pressure toward speculative fixes to "complete" a run.

### Seam 4 — escalation edges as pack data

Per-incident-class doctrine (the sibling spec's pack): preapproved
responses, forbidden actions, escalation thresholds ("> 3 nodes affected,
root cause unknown after 30 min, data corruption suspected" → human).
Escalation conditions are pack data evaluated against evidence, not agent
judgment calls.

## Constellation division of labor (the seam this completes)

- **Maude** decides *how* — generates plans against the pack's questions.
- **AG** decides *whether* — verifies instantiated answers are evidenced and
  the requested stage grant is contained.
- **Nightshift** executes authorized acts and produces receipts. This is the
  standing-delegation layer Nightshift has been missing: it knows *how* to
  observe/classify/remediate/verify, but not *why it is allowed* beyond the
  immediate witness. It never asks "what should I do?" — it asks "which
  branch of the pre-legislated doctrine matches the evidence?"
- **NQ** is the escape hatch: no applicable branch, or evidence fits no
  authorized answer → governed inquiry, not confident guessing.

## Acceptance criteria (for an eventual build; none scheduled)

1. A recovery-stage session requesting a prevention-class action is refused
   **by type** (the request is unrepresentable or a typed refusal names the
   stage mismatch), with a receipt.
2. An investigation grant is unmintable without a `RecoveryReceipt`; a
   prevention grant is unmintable without a `FailureFinding`; forging either
   from the other's fields fails (distinct types, not tag strings).
3. A `FailureFinding` whose evidence bindings fail verification blocks the
   prevention stage — diagnosis-as-prose is inert.
4. Stage-1 terminal closes with an honest "cause not established" receipt
   and no dangling obligations.
5. An escalation threshold in the pack fires from evidence (e.g. affected
   count) and halts auto-advance, producing a docket case.
6. Mutation probes: deleting the transition-witness check makes test 2 fail;
   deleting the stage typing makes test 1 fail.

## Non-goals

- **Nothing armed.** No live incident automation, no supervisor changes, no
  autopilot wiring. Playbook-substrate doctrine applies: evidence, never
  facts; landing ≠ operational promotion.
- Does not redefine the ops incident FSM; stage grants attach to the
  existing status vocabulary rather than replacing it.
- No new permission algebra (containment stays in ration/scope/capability
  vocabulary).
- No cross-repo builds from this filing (Nightshift/Maude/NQ integration is
  named, not scheduled; each lands in its own repo's idiom).
- Break-glass interaction is out of scope here — the alternate-path
  candidate (`working/candidate-break-glass-2026-07-15.md`) is the door;
  this spec is walls.

## Open questions

- **OQ-A:** where do stage grants live — LA capacity leases, standing
  receipts, or RationCard extensions? (Provider choice changes admissibility
  basis; see `provider_substitution_basis_mutation`.)
- **OQ-B:** who may sign a `FailureFinding` — is it NQ testimony adjudicated
  by AG (the ratified shape), or can a human operator assert one directly
  (and is that a different type)?
- **OQ-C:** concurrent incidents sharing scope — does stage authority
  compose per-incident or per-resource (WORK_RESERVATION interaction)?
- **OQ-D:** does stage regression (service degrades again mid-investigation)
  re-mint the recovery grant automatically, or is re-entry an escalation?
