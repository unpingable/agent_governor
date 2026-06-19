# Cross-tool doctrine note: monitoring is a projection, not a peer

## Status

**Cross-constellation candidate doctrine — non-binding, no implementation
authorized.** Filed 2026-06-19 under AG custody (see
`managed-repo-candidate-filing-note.md`). Companion to
`active-witnessing-probe-is-transition-note.md`: that note governs the **epistemic
seam** (how a witness fact is earned); this one governs the **user-surface seam** (how
a witness fact is shown). The two pair as one constraint set — they block opposite
failure modes at opposite ends of the same pipe.

> Monitoring is the face. Witnessing is the architecture. The projection between them
> must preserve negatives **and their salience** unless an explicit relaxation receipt
> lawfully downgrades attention.

## The cut (do not mistake it for two systems)

"Split traditional ops monitoring out of the witness system" implies **two peer
systems watching the same fleet side by side.** That framing is the error. The honest
cut is **layered**, with monitoring as the *consuming* layer on top — not a peer
beside the witness:

| Layer | What it is | What it says |
|---|---|---|
| 1. Passive telemetry | cheap, dumb, continuous (CPU, latency, counts, scrape values) | "I observed X" |
| 2. Witness layer (the system proper) | deliberate, admissible, receipt-bearing, includes active probes-as-transitions | scoped witness facts + verdicts |
| 3. Monitoring / actionability | operator-facing: paging, SLO burn, trend, dashboard | "does a human care?" |

Layer 3 **consumes** layers 1 and 2; it maps admissible facts plus telemetry onto
operational decisions through an **explicit policy.** The witness system is a
monitoring system the way an engine is a car: monitoring is what it looks like from the
operator's chair; witnessing is what it is under the hood.

## The dangerous seam is the join

Telemetry and witness facts can disagree, and the operator looks at the dashboard:

- dashboard says green; the witness holds `Contradicted`;
- passive telemetry says normal; an active probe says `WitnessedAbsent`;
- the SLO says no page; the witness layer says the evidence basis is stale/inadmissible.

`No alert` is not `fine`. `Green dashboard` is not `admissible state`. The projection
from witness facts into the monitoring surface is where these get silently reconciled
in the wrong direction.

## Rule 1 — No Silent Conversion (preserve existence)

> A monitoring surface may downgrade attention, suppress paging, or classify a
> witness-negative as non-actionable **under explicit policy.** It may not erase, hide,
> or convert a witness-negative into green **without a receipt.**

- `WitnessedAbsent(valid_cert)` may be non-paging on a staging host — but the surface
  must still **show** the negative as present and scoped.
- `Contradicted(binary_identity)` may not become "service healthy" because latency and
  HTTP 200s are normal.
- `CannotTestify` may not project as green; only as "no actionable alert under policy"
  **if a policy receipt says so.**

## Rule 2 — No Silent Burial (preserve salience)

Rule 1 preserves a negative's **existence**, not its **salience** — and operationally,
salience is the whole game. Two laundering paths survive Rule 1 untouched, and they are
the two most common real monitoring failures:

**Policy accretion.** Rule 1 permits "suppress / classify non-actionable under explicit
policy." Each call has a receipt, so it isn't *silent* — but a fleet goes blind one
scoped downgrade at a time. A receipt reading "`CannotTestify` on `*-staging` is
non-actionable" satisfies Rule 1 while erasing the negative from attention.

> Therefore an **attention downgrade is a relaxation act.** It emits a
> **RelaxationReceipt** recording scope, authority, reason, horizon/expiry, and
> affected verdict class. The negative remains present. The **accumulated** relaxations
> are themselves a witness surface. (Same demon as the existing AG split: accepted live
> risk and cleared concern are different; a downgrade does not discharge the negative,
> it changes operational attention under policy. "Auditable suppression" is still
> suppression.)

**Visual dominance.** Telemetry is continuous, fresh, familiar; witness-negatives are
sparse and stale-between-probes. Even with existence preserved, the gestalt is
"mostly-green telemetry, one weird flag in a panel," and the operator trusts the green.
Slogans ("green ≠ admissible") tell the operator how to *read* the surface; they don't
stop it from *being* green-dominant. Slogans don't survive 3am.

> Therefore a precedence rule: **admissibility outranks freshness.** A sparse
> witness-negative dominates primary attention over concordant continuous telemetry
> unless an explicit RelaxationReceipt says otherwise. "Mostly green" is not the
> default visual state when an admissibility negative is present.

## The type-wall (the load-bearing implementation constraint)

"A hard internal seam in one codebase" is a comment, not a constraint, unless
type-enforced. Negative-preserving *tests* cover the paths you remember; they don't
stop anyone at 2am from writing `if verdict.is_green()` straight past the projection.
Six months later the architecture is moldering in the docs while the dashboard does
vibes-based epistemology in production.

The seam holds only if the witness verdict type **has no operational coercion**:

- `WitnessVerdict` is **not** an `OperationalStatus`. No `is_green()`, `is_ok()`,
  `healthy()`, `Into<bool>`, or implicit severity mapping on the verdict type.
- The **only** path from verdict to operational status is
  `project_verdict(policy, verdict, context) -> OperationalStatus` — un-bypassable by
  type.
- If projection reduces attention for a negative verdict, it **attaches** a
  RelaxationReceipt.
- Negative-preserving **and** salience-preserving tests cover the projection boundary.
- The UI renders witness-negatives in primary attention unless relaxed.

## Sequencing — split the semantics now, not the systems

Split the **semantics** today: it is free, and it keeps "no-alert equals fine" out of
the verdict ladder. Do **not** split into separate **systems** yet — a physical split
buys a join, a consistency problem, and a two-surface lie-risk before the witness layer
has emitted one useful fact.

For now: one codebase; one hard, type-enforced internal seam between telemetry
collection, witness receipts/verdicts, and monitoring projection; an explicit
projection policy; negative- and salience-preserving projection tests.

A future **physical** split becomes necessary only when **cadence** forces it:
telemetry wants frequent cheap scrapes; active witnessing is deliberate and
perturbation-budgeted; a probe is a transition and cannot run at scrape frequency
without scarring the subject every fifteen seconds. That mismatch is real but it
**announces itself.** Let cadence and perturbation budget force the deployment split
later; preserve the semantic split inside one implementation now.

## The premature-taxonomy fence

The projection **policy** and the relaxation taxonomy are a prediction about which
negatives operators will lawfully downgrade and how. Predictions get discovered, not
drawn. The durable content here is the **constraints** (the layered cut; the join;
No Silent Conversion; No Silent Burial; admissibility-outranks-freshness; the
type-wall). Any complete policy/relaxation taxonomy is **premature until real
projection receipts exist.** Ship the policy reality filled, not the one drawn from the
armchair.

## NON_CLAIMS

This note does **not**:

- mean every witness-negative pages, or is operationally urgent;
- eliminate policy — it makes attention changes **governed acts**, not UI accidents;
- authorize building a second monitoring system beside the witness layer;
- ratify a projection-policy schema or a relaxation taxonomy (the NQ candidate proposes
  a *first, ugly* one);
- claim any current surface already enforces the type-wall (the NQ candidate's
  grounding pass must check whether the seam exists, leaks, or is merely absent).

## Doctrine lines

- Monitoring is the face. Witnessing is the architecture.
- Monitoring is a projection, not a peer.
- The projection must preserve negatives **and their salience.**
- No Silent Conversion (existence) **and** No Silent Burial (salience).
- An attention downgrade is a relaxation act; attention is a governed resource.
- Admissibility outranks freshness.
- The seam is a comment until the type wall makes it un-bypassable.
- A green dashboard with auditable suppression is still a lie, just a notarized one.
