# Directional Invariants — The Non-Conversion Kernel

**Status: doctrine note, not implementation spec.** Filed 2026-06-09.
Captures the directional shape that the meta-plan
(`docs/agent-governor-meta-plan.md`) and the sentinel
(`working/sentinel-observation-not-authority.md`) both depend on, in one
place where future cross-fence work can find it.

## The philosophical fork — wards subtract, warrants attest

Two coherent positions exist for constraining what an agent can do.
They are not the same thing, and the difference is not cosmetic.

**Containment by subtraction.** Define the action space as
`actions = all_capabilities − wards`. Agents may act unless explicitly
warded. Subtractive permission is real engineering — deny-by-default
network policy, writable-path allowlists, sandboxed eval, port-isolated
runtime — and it is the dominant model in agent-runtime substrates today.
Its failure mode is **fail-open under novelty**: anything not warded is
permitted. A new capability nobody thought to ward is permitted by
default.

**Consequence by warrant.** Define admissible action as a positive
chain: standing → admission → spendable capacity → execution → receipt.
Each step is a *witnessed attestation*, not a subtraction. Absence of an
attestation fails *closed*: no standing means no admission, regardless
of whether the action was warded. Positive warrant is what AG / Wicket /
linear_accountant / Continuity are doing as a constellation.

Slogan:

> **Wards subtract. Warrants attest.**

Neither is wrong. They protect against different failure modes. The seam
where containment runs out is the moment trust is asserted rather than
witnessed — phrases like `sandbox: unrestricted` for "trusted operator-
local work" are exactly that seam. **Trust asserted is not trust
witnessed.** The admissibility layer begins where containment ends.

## The directional kernel

The single meta-rule from which the rest of this file falls out:

> **No later-stage artifact may supply an earlier-stage authority
> condition.**

The chain is one-way:

```
observation / testimony
  → standing question
  → standing grant / refusal
  → wicket admission / refusal
  → linear accountant spendability
  → governor / nightshift execution
  → outcome / refusal receipt
  → continuity reliance
```

The forbidden conversions:

```
observation        ≠ standing
standing           ≠ admission
admission          ≠ spendability
spendability       ≠ execution proof
execution receipt  ≠ prior authorization
history            ≠ reliance
```

Each `≠` is a directional invariant. The meta-rule generates them all:
no downstream artifact may cure or imply an upstream prerequisite.

## The ten directional invariants

A closed list. New entries earn admission via gap spec or sentinel
specimen, not by accretion.

1. **Standing is the first entitlement boundary.** Observation may
   raise standing. Observation may not satisfy standing. This is the
   MVP hinge. (See sentinel doctrine: *testimony can call the court
   into session; it cannot make the plaintiff.*)

2. **Capacity is downstream of entitlement.** Linear Accountant must
   never be queried as if budget availability can authorize the actor.
   Slogan: **capacity cannot cure lack of standing.** (Composes with
   `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md`.)

3. **Admission is not spendability.** Wicket can admit an operation as
   admissible, but cannot authorize replay or consumption. That is the
   accountant's job. (Composes with VALIDITY_SPENDABILITY_SPLIT.)

4. **Receipts are not retroactive warrants.** Outcome receipts prove
   what happened. They do not prove it was entitled unless the upstream
   chain exists. (Composes with `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md`.)

5. **Continuity is reliance discipline, not laundering.** Continuity
   may preserve promoted premises. It must not turn observed history
   into relied-upon authority merely because it was recorded. (Composes
   with `memory/continuity_governor_split.md`.)

6. **`outOfScope` / `unknown` / `absent` are audible non-authority.**
   They may block, degrade, or raise review. They must not become
   permission-by-silence. (Composes with
   `working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md`.)

7. **Current protection is topological, not mechanical.** The bad path
   is mostly absent because no surface authors it. That is weaker than
   a gate refusing it. Say so plainly. (See sentinel doc, current
   status: *guarded topological absence. Not mechanical refusal.*)

8. **Typed `ArtifactKind` / `UseKind` is earned by the standing hinge,
   not before.** Do not mint generic enums to satisfy the
   courthouse-itch. First make the standing transition real enough that
   the type distinction has something to bite. (Composes with sentinel
   ladder step 3.)

9. **Z3 waits until there is a graph.** Otherwise it verifies theater.
   Its eventual role is checking forbidden paths, not blessing policy.
   (See meta-plan §Z3 verifier role; integration seam is wicket, not
   AG kernel.)

10. **AG's core promise is directional non-conversion.** Restated
    product sentence:

    > **Agents may observe loosely, but may only act through standing,
    > admission, spendable capacity, and receipted consequence.**

    Companion to the meta-plan's ignition sentence (*AG may observe
    loosely, but may only act through promoted authority, fresh
    evidence, spendable budget, and receipted refusal*) — same shape,
    different framing. The standing/admission/capacity/consequence
    variant ties the slogan to the chain stages explicitly; the
    promoted-authority/evidence/budget/refusal variant emphasizes the
    qualifying properties. Either can lead; both name the same
    invariant.

## Why this file exists

The ten invariants individually compose with material already filed.
Together, as a *directional set*, they expose a stronger property than
any single gap names:

> **The agent-action pipeline is one-way and non-conversion-bearing.**

That stronger property is the actual MVP-shape of the consequence layer.
Filing it as a single record means future cross-fence work
(constellation alignment, primitive minting, executable sentinel work)
can cite *one* directional kernel instead of stitching six gap specs
together each time.

## What this file is not

- Not authorization to build the ten invariants as typed code-level
  checks. The forcing case for typed primitives still gates per
  `~/.claude/CLAUDE.md` § YAGNI scope and per sentinel doc ladder.
- Not a replacement for the gap specs and working notes it composes
  with. Those still carry the load at their respective surfaces.
- Not a competitor or comparison artifact. Names the philosophical
  fork (wards-subtract vs warrants-attest) on its own merits.
- Not a roadmap. Composes with the parked alignment pass and the
  parked grep-audit sentinel; doesn't force either's execution.

## Cross-references

- `docs/agent-governor-meta-plan.md` — orientation across constellation
  planes; carries the "wards subtract; warrants attest" section as a
  positioning fork.
- `working/sentinel-observation-not-authority.md` — invariant 1's
  current carrier; the standing-mint trapdoor in long form.
- `working/parked-constellation-alignment-pass.md` — composes via
  invariant 8 (typed primitives earned by standing hinge).
- `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md` — load-bearing
  for invariants 2 and 3.
- `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md` — load-bearing for
  invariant 4.
- `working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md` —
  load-bearing for invariant 6.
- `memory/continuity_governor_split.md` — load-bearing for invariant 5.
- `memory/standing_integration.md` — upstream entitlement-mint role at
  `~/git/standing` (Rust, not in AG runtime loop).
