---
audience: repo-local
status: draft
---

# GOV_GAP_INTERFEROMETRY_IDENTIFIABILITY_001

Status: draft
Owner: Governor
Type: semantic / API-contract gap
Drafted: 2026-04-21

## 1. Problem

The interferometry subsystem currently frames its job as multi-model
claim comparison: run N backends on the same prompt, identify shared
and unique claims, and promote shared claims to the epistemic ledger:

```
governor interferometry accept --shared    # default
governor interferometry accept --all
```

The implicit semantic is: **if multiple models produced the same claim,
the claim is more trustworthy, and belongs in the ledger with
elevated standing.**

This framing is epistemically too strong.

The ops-non-self-identical-controller paper (§3.2, condition iii —
local gain aliasing) establishes that output agreement across
controllers is **consistent with composition being unresolvable from
outputs.** Two controllers can produce the same realized action
trajectory either because they are substantively in agreement, or
because one is a different controller running at different gain, or
because one is the other plus a latent compensator — and no amount of
output comparison can distinguish those cases within the operating
region.

In interferometry terms: **shared output does not imply resolved
composition.** It only rules out gross disagreement.

The current `accept --shared` verb promotes to the epistemic ledger as
if the composition question were answered. It is not.

## 2. Goal

Reframe interferometry as an **identifiability probe**: a structured
check on whether the controllers under test are distinguishable from
outputs under the current operating conditions. The output of a run
should answer *"is the composition of the realized controller resolved
from the compared outputs?"* — not *"which model is right?"*

Concretely, in v1 the system should:

- split the `--shared` verb into distinct states with distinct
  epistemic standing,
- stop promoting shared outputs to the epistemic ledger as "resolved"
  by default,
- preserve the existing multi-model run and comparison machinery — the
  probe itself is already built, only its interpretation layer is too
  strong.

## 3. Non-goals

This gap does **not** propose:

- removing interferometry or the multi-backend compare flow,
- changing how claims are extracted or fingerprinted,
- solving identity-side continuity end-to-end (this is one probe,
  not the whole axis),
- introducing new backends, prompts, or run modes,
- changing code interferometry's risk-marker and anchor-conflict
  machinery (that already operates on a different semantic and is
  unaffected).

## 4. The reframe

Interferometry currently answers:

> *Which claims did models agree on?*

The reframe answers:

> *Under the current measurement map (output comparison), is the
> controller composition distinguishable?*

The outputs of a run distribute across three epistemically distinct
cases:

| Case                  | Current name  | Proposed name                | Standing                                                          |
|-----------------------|---------------|------------------------------|-------------------------------------------------------------------|
| Output agreement      | shared        | **indistinguishable**        | Consistent with agreement OR with aliasing; composition unresolved. |
| Output disagreement   | conflicting   | **discriminating**           | At least one backend is doing something different; composition is identifiably non-shared. |
| Single-backend output | unique        | **unobserved-elsewhere**     | No information about composition — the other backends didn't speak. |

"Indistinguishable" is the important rename. It is the observational
conclusion the probe is actually licensed to make. "Shared" names an
epistemic status (agreement) the outputs cannot support.

## 5. Proposed API

### 5.1 Acceptance vocabulary

Replace the current `accept --shared / --all` with:

```
governor interferometry accept --discriminating
    Promote only discriminating claims — backends disagreed, so the
    claim's origin is identifiable. Standing: SUPPORTED at comparison
    confidence.

governor interferometry accept --indistinguishable --under-aliasing-caveat
    Promote indistinguishable claims with explicit aliasing caveat.
    Standing: SUPPORTED only if paired with a separate evidence source.
    Without that pairing: ASSUMED.

governor interferometry accept --all
    Promote everything with case-appropriate standing. Requires explicit
    caveat flag.
```

The default (no flag) should emit no promotion: the probe runs, the
classification is stored, but acceptance is an explicit second step.
Promotion-by-default is the current wrong thing.

### 5.2 Run output

The `results` and `divergence` views should display the three-case
classification, not the two-case shared/conflicting split. The run
summary should report:

- indistinguishable-output rate
- discriminating-output rate
- unobserved-elsewhere rate
- identifiability verdict: **resolved** (discriminating ≥ threshold),
  **partially resolved**, or **unresolved** (indistinguishable
  dominates)

An unresolved verdict on a run is an informative finding, not a
failed run.

### 5.3 Backwards compatibility

`--shared` remains as a deprecated alias for
`--indistinguishable --under-aliasing-caveat` for one release cycle,
with a stderr warning. After that, remove.

## 6. First consumer

The reframe is not worth shipping without a concrete consumer.
The smallest credible consumer:

**Pre-commit interferometry probe on ambiguous code changes.** When
the agent produces a changeset on an unfamiliar region, run
interferometry across two backends and emit an identifiability verdict.

- Resolved → proceed normally.
- Partially resolved → proceed with warning.
- Unresolved → annotate the commit with "composition not resolved from
  outputs; rely on orthogonal evidence."

This consumer exercises the three-case classification in a place where
the distinction materially changes downstream behavior: an unresolved
verdict does not block, but it changes the admissibility shape of the
resulting evidence bundle.

Without this or an equivalent consumer, the reframe is doc churn.

## 7. Migration

1. Add the three-case classification alongside existing shared/unique/
   conflicting in `Interferometry` run output. Both coexist for one
   release.
2. Ship `accept --discriminating` as a new verb. Existing `--shared`
   keeps working.
3. Introduce the first consumer (pre-commit probe or equivalent).
4. Flip the default: `accept` with no flag no longer promotes.
5. Deprecate `--shared` in CLI and daemon RPC surfaces.
6. Remove after one release.

At each step, the receipt shape of `interferometry accept` should
record which verb was used and which classification the promoted
claims carried.

## 8. Why this earns a draft

Unlike the continuity-budget envelope (which was falsified by receipt
distribution showing its trigger events do not fire — see
`docs/RECEIPT_SNAPSHOT_001.md`), the interferometry reframe operates
on a subsystem that is already invoked explicitly by users and
already emits receipts. The question is not whether it fires but
what its outputs mean.

The falsification for this gap is different: does the three-case
classification materially change downstream behavior in at least one
consumer? Section 6 names that consumer. If it cannot be built, or if
the resulting behavior is identical to current `--shared` semantics,
the reframe is cosmetic and this gap fails its own acceptance bar.

## 9. Open questions

- Threshold for "discriminating ≥ threshold → resolved": literal count,
  fraction of claims, or weighted by claim salience?
- How should the aliasing caveat propagate through the ledger?
  Specifically: if an indistinguishable claim is later corroborated by
  independent evidence, does its standing upgrade, and if so, by what
  mechanism?
- Does code interferometry's risk-marker logic interact with this
  reframe, or is it strictly orthogonal? (Preliminary: orthogonal —
  risk markers are structural properties of individual outputs, not
  claims about composition.)
- What is the minimum backend count for a credible identifiability
  verdict? Two is enough to detect disagreement; three provides
  triangulation. Single-backend runs cannot emit an identifiability
  verdict at all.

## 10. Related

- `~/git/papers/working/ops-non-self-identical-controller.md` — §3.2
  condition (iii), local gain aliasing; §3.3 Operational Masking
  Theorem.
- `docs/RECEIPT_SNAPSHOT_001.md` — the falsification result that
  surfaced this as the candidate live gap.
- `specs/interferometry/` — existing subsystem specs (not yet audited
  against this reframe; audit is part of step 1 of the migration).
