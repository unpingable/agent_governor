# Sentinel — Observation Is Not Authority

**Status: doctrinal witness, not executable sentinel.**

> **Current status: guarded topological absence. Not mechanical refusal.**

The invariant is currently held by *the absence of an authoring path* across
AG's surfaces, not by an active gate that refuses the bad input. Stronger
phrasing is laundering. Not a test. Not yet ratified doctrine. A place to
land concrete laundering specimens *if and when* one is found, and a
pointer at the gates that currently refuse the forbidden shortcut by
topology.

## Rot risk (named, not yet mitigated)

> An empty specimen file is a doctrinal witness, not a sentinel. It cannot
> scream when a future code path adds a laundering shortcut. Naming the
> witness without the alarm leaves the invariant silently un-defended.

The honest state today (2026-06-09):

- No extant AG gate **mechanically** distinguishes observation-class from
  authority-class evidence. The current refusal is *topological* — no API
  surface authors the bad path — but topology can erode silently as new
  code lands.
- Writing an executable test against any of the obvious targets
  (`gate_receipt` AUTHORIZE emission, `standing` validator
  AUTHORIZE_REQUIRED_CHECKS, `evidence_gate` HARD-claim coupling) requires
  either:
  - fabricating a typed `ArtifactKind` / `UseKind` primitive that AG
    has not earned (the meta-plan explicitly defers this), or
  - asserting a refusal a gate cannot currently make (vacuous test).
- The closest forcing case at the kernel-classification surface
  (`outOfScope`) was already audited out in `working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md`:
  no AG kernel emits `outOfScope` as an authority-relevant classification
  today.

## Forcing-case candidate: grep-audit sentinel (NOT built)

The candidate alarm shape that does *not* require new typed primitives:

> A periodic grep-audit script that scans AG src/ for code paths matching
> the laundering shape (a function call where a SignalEnvelope, NQ
> finding, or non-`denied` classification result flows into the
> authorization input of any binding gate without an intermediate
> promotion artifact) and emits a receipt-shaped finding. Silent on clean,
> loud on hit.

**Parked, not built.** A grep audit is real but shallow — useful as a
tripwire, not as doctrine enforcement. New infrastructure without a fired
caller becomes shrine debt. The right next primitive (`ArtifactKind` /
`UseKind`) should arrive when a surface actually needs to distinguish
them, not because the meta-plan made anyone itchy.

### Promotion triggers (when the grep-audit sentinel earns construction)

Standing-laundering shape (Chatty 2026-06-09):

1. **Any standing surface accepts findings / signals / reason strings as
   sufficient basis for entitlement.** AG's `standing/` validator OR the
   upstream `~/git/standing` mint. This is the entitlement-mint
   trapdoor.
2. **Any `outOfScope` / `unknown` / `absent` / `not_applicable` path
   maps to `standing_granted` / `may_act` / `entitled`** (the classic
   "non-`denied` therefore proceed" shape, applied at the standing layer
   specifically).
3. **Wicket / admission treats missing standing as harmless** because
   another artifact "observed" the condition. Admission must not rescue
   a missing entitlement by appeal to observation.
4. **A standing grant becomes replayable / spendable** without capacity
   discipline (the validity-spendability split applied at the standing
   layer — composes with `GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001`).

Downstream laundering surfaces:

5. A PR / change introduces any AG surface that **emits
   classification-like authority outcomes** (a kernel call whose return
   value is consumed downstream as proceed/deny by any mutation gate).
6. **`SignalEnvelope`, NQ findings, observations, or reason strings
   become accepted inputs** to any authorize / mutate / consume code
   path — even via dict-wrapped indirection.

Infrastructure earning the deeper audit:

7. Typed `ArtifactKind` / `UseKind` primitives **land in AG** (or in any
   shared schema with wicket / WLP / linear_accountant / standing). The
   audit then has typed surfaces to discriminate against and becomes
   non-shallow.
8. The parked alignment pass (`working/parked-constellation-alignment-pass.md`)
   resumes and needs a cheap regression guard during the rename.

Until at least one of these fires: doctrinal witness, no grep audit, no
test.

## The forbidden shortcut

> AG / Governor cannot consume `Observation` as `Authority`.

More specifically, the laundering shape that needs naming is the chain:

```
observation / finding / outOfScope / unknown / absence
  → Standing grant / entitlement / "may act"
  → Wicket admission / execute / mutate / consume
```

Nothing in the observing-verb family (`observe`, `notify`, `warn`,
`diagnose`, `suggest`, `report_finding`, NQ finding emission, signal
envelope emission, a non-`denied` classification result) may become the
basis for a binding verb (`grant`, `admit`, `authorize`,
`request_capacity`, `consume`, `commit`, `rely`, `mutate`,
`cross_boundary`) without an intervening **promoted artifact** — a
standing grant, a wicket admission, a capacity receipt, a continuity
commit, an AUTHORIZE gate receipt with required checks.

The shortcut is forbidden because:

- Observation may be lossy. Authority may not.
- Observation has no minted authority. A non-`denied` classification is not
  permission.
- Receipt-of-past-evaluation is not live authority across a serialization
  boundary.

## Standing is the entitlement mint

Standing is the first laundering opportunity. If a signal can manufacture
entitlement, every downstream check (Wicket admission, capacity reservation,
mutation gate) stays "clean" while the fraud already happened upstream.
Respectable crime, good shoes.

Doctrine sentence:

> **Observations may raise a standing question; they must not satisfy
> standing.**

Or sharper:

> **Testimony can call the court into session. It cannot make the
> plaintiff.**

Constellation note: AG carries the `standing/` *validator* (per
`docs/doctrine/validator_contract.md`, constitutional rounds C2–C5) — the
piece that checks an AUTHORIZE receipt's required checks are present and
well-formed. The constellation's *entitlement mint* role (issuing standing
grants in the first place) lives in `~/git/standing` (Rust, not currently
wired into AG's runtime loop — see `memory/standing_integration.md`). The
sentinel covers both surfaces: AG's validator should refuse standing
satisfied by observation-class basis, and the upstream mint should refuse
to issue a grant whose justification is observation-class. Today, neither
mechanical refusal exists; both surfaces hold the invariant by topology.

## What the witness actually claims (honest restatement)

The invariant above is the *aspiration*. The claim this witness makes about
AG **today** is weaker and honest:

> **No current AG surface authors observation-as-authority.**

That is topological absence (the bad path is not constructible by any
extant authoring API), not mechanical refusal (a live gate that examines
the input and says no). The two are different claim classes. Treating
absence as refusal is the laundering shape this witness is meant to
refuse — applying it to itself.

## The ladder (current → enforced)

The sentinel sits at step 2 of a five-step ladder. Each step earns the
next; no skipping.

```
1. topological absence            ← current state
2. grep / audit sentinel          ← shallow alarm, forcing-case candidate
3. typed classification primitive ← ArtifactKind / UseKind or equivalent
4. executable gate test           ← real refusal a gate makes mechanically
5. Z3 graph check                 ← whole-artifact-graph constraint verification
```

The **next real forcing case is not "write a test."** It is:

> Mint the smallest classification primitive that makes the forbidden
> conversion *representable*.

Until the bad path is representable in code, refusal can only be
structural/topological. Lean / Z3 / test machinery needs a handle on the
demon before it can bite it.

## What this sentinel is for

A specimen file is the cheapest forcing case. If a real AG code path is ever
found that promotes a signal envelope, NQ finding, or observation receipt
into the authorization input of any binding gate without an explicit
promotion artifact, the specimen lands here. Until then, this file is
**deliberately empty of specimens** — and that emptiness is the signal that
no laundering case has been discovered.

This mirrors the discipline of `working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md`:
filing the invariant without ratifying enforcement, until a forcing case
appears.

## Gates that currently refuse the shortcut

The current AG implementation refuses observation → authority by topology,
not by typed primitive. The relevant refusing surfaces:

- **`gate_receipt.py` — content-addressed gate receipts.** Receipt id is
  `H(schema_v + gate + subject_hash + evidence_hash + policy_hash)`. A
  signal envelope cannot be substituted as `evidence_hash` for an
  AUTHORIZE-class gate without colliding the policy-hash check; the
  authoring API does not let observation surfaces emit AUTHORIZE-role
  receipts.
- **`standing/` validator.** AUTHORIZE receipts require the four
  `AUTHORIZE_REQUIRED_CHECKS` (standing, admissibility, scope, budget) per
  validator_contract §9, and each Check must carry a structured CheckBasis
  (C4). A bare observation cannot satisfy the *presence* check. **But** the
  validator does not currently inspect semantic content of `rule_id` or
  `inspectable_refs` — an observation-derived basis could parse as
  well-formed CheckBasis and pass. Refusal here is presence-shaped, not
  content-shaped. This is the load-bearing gap for the entitlement-mint
  concern above.
- **`evidence_gate.py` — evidence-gated coding harness.** HARD claims
  require linked evidence. Custody scoring measures whether the evidence
  surface is admissible, not whether the agent asserted it.
- **`scope.py` — scope governor.** Locality-first containment refuses tool
  use outside an explicit grant. An observation can describe scope; it
  cannot grant it.
- **`runtime/` supervised sessions.** Tool calls flow through intervention
  approval. An NQ finding cannot author-substitute for the operator's
  approval signal.
- **`continuity.py` — anchor registry.** Anchors are explicit invariants /
  preferences. Drift detection observes; it does not author anchors.
- **`signals/envelope.py` — signal envelopes are observe-only.** Phase A/B
  invariants pin "observe-only (no blocking)". No envelope emission path
  participates as a gate input.

The refusal is structural across these surfaces. The sentinel asks: *is
there a path that bypasses all of them?*

## Two-grep falsification (the search)

To find a laundering instance, look for:

1. Any code path that consumes a `SignalEnvelope`, NQ finding, observation
   receipt, or non-`denied` kernel classification result and routes it
   into the `authorization` input of a binding gate (gate_receipt
   AUTHORIZE emission, scope grant creation, scope grant `use_count`
   increment, capacity reservation, continuity commit, etc.) without an
   intermediate promotion artifact (standing grant, wicket admission,
   capacity receipt, AUTHORIZE-class GateReceipt).
2. Any serialization boundary across which a non-`denied` classification
   crosses without revalidation or seal.

Both are paper-shaped audits. Neither is automated today. If either
returns a real instance, that instance becomes a specimen in this file and
forces the question of typed primitives (`ArtifactKind` / `UseKind`).

Audited so far (no laundering instance found):

- 2026-06-03 audit pass on the validity/spendability surfaces
  (`memory/validity_spendability_audit_2026_06_03.md`). Three surfaces
  KILLED (scope use_count is testimony not capacity; reservations
  heartbeat is mutex not budget; TTL is validity-refresh not
  capacity-refresh), one PARTIAL (overrides compute_pressure advisory
  smell, pre-existing acknowledged debt), one WEAK (quorum). No
  refactor required.

## Promotion criteria

This sentinel promotes from candidate to ratified gap spec when one of:

- A specimen lands that survives the two-grep falsification.
- A typed-primitive proposal (`ArtifactKind` / `UseKind` as enums in code)
  is filed with a concrete code path it would lock down.
- The cross-repo constellation requires AG to enumerate the binding /
  observing verb split in a shared schema with wicket, linear_accountant,
  or WLP.

Until then: candidate, no enforcement, no kernel commitment.

## Cross-references

- `docs/agent-governor-meta-plan.md` — the orientation document that
  invokes this sentinel by name.
- `working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md` — same shape at
  the kernel classification surface.
- `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md` — same shape at
  the spendability boundary (eligibility ≠ capacity).
- `specs/gaps/GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001.md` — same shape at
  the receipt-schema (form ≠ content) boundary.
- `specs/gaps/GOV_GAP_SEALED_OUTCOME_BOUNDARY_001.md` — same shape at the
  construction boundary (observable ≠ constructible).
- `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md` — same shape across
  serialization (post-validated ≠ pre-authorized).
