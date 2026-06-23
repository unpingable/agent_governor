# Next packet — ForbiddenSurfaceGate (named, NOT built)

Per [D008](DECISIONS.md): build order is **reproducibility capsule (this directory) →
ForbiddenSurfaceGate → self-correction-within-scope**. This file is the seed for the next
packet only. **Do not build it in the capsule packet.** A clean first draft existed and
was deliberately removed so the tree honestly reads "named, not built"; this seed preserves
the design so the rebuild has cold-start context.

## Goal

Prevent AG-on-AG steps from being admitted merely because touched paths are in scope when
the diff mutates a forbidden **semantic** surface. The semantic companion to
`DiffPathScopeGate`: path authority is necessary but not sufficient (Slice 3 specimen —
`gate_receipt.py` was *in* the path grant, but the closed-enum change was forbidden).

## Question

Can the admission path detect forbidden authority-surface changes from a diff and return
`REJECT` / `CANNOT_TESTIFY` without the conductor deciding?

## Invariant

Path authority is necessary but not sufficient. The conductor stays dumb (D003/D005).
`DiffPathScopeGate` handles path containment; `ForbiddenSurfaceGate` classifies semantic
surfaces. It is a classifier over a **declared** forbidden-surface list — **not** a general
semantic oracle. No "the model thinks this smells authority-ish." Literal markers only; the
receipt records exactly what was observed.

## Allowed

- A narrow in-process `ForbiddenSurfaceGate` beside `DiffPathScopeGate` (new module
  `src/governor/forbidden_surface_gate.py`; satisfies the `PreflightClient` Protocol).
- Detect forbidden surfaces from diff/file changes (touched files + changed +/- lines vs
  declared `(path_suffixes, markers)` rules).
- Route its source verdict through the **existing** `ag_admit` projection (import the
  `SOURCE_*` constants; emit `PreflightDecision` with `raw.source_verdict`). Put detected
  surfaces in `block_reasons` so the **unchanged** dumb conductor records them.
- Tests proving path-allowed-but-semantically-forbidden changes are rejected.

## Forbidden

No conductor logic; no global receipt-semantics changes; no closed-enum changes; no
`ScopeGovernor` coupling; no policy inference beyond the declared list; no automatic
widening; **no self-correction build in this packet**. (Do not edit the forbidden surfaces
in [GRANTS.yaml](GRANTS.yaml) while building the thing that guards them.)

## Classifier semantics (conservative)

- forbidden-surface file touched **and** a declared marker present in a changed line →
  source `BLOCK`, reason `semantic_surface_forbidden` (list detected surfaces).
- forbidden-surface file touched but **no** marker matched → source `CANNOT_TESTIFY`,
  reason `semantic_surface_ambiguous` (a sacred file changed in a way the classifier cannot
  certify benign — escalate, never ADMIT).
- a whole-file forbidden surface (`markers: []`, e.g. `.governor/loop.json`) touched →
  `BLOCK`.
- no forbidden-surface file touched → source `PROCEED`, reason `no_forbidden_surface`.
- diff unparseable / no headers → `CANNOT_TESTIFY`, reason `cannot_observe_diff`.

Declared forbidden surfaces: use [GRANTS.yaml](GRANTS.yaml) `forbidden_surfaces` as the
seed list (stepverdict_projection, preflight_contract, conductor_authority,
closed_receipt_enums, receipt_emission_semantics, loop_state, ci_accept_semantics).

## Toy / specimen + exit

- path-allowed **and** semantic-forbidden specimen → **refuses** (e.g. a diff editing a
  `VALID_NON_DISCHARGE_KINDS` line) — run both gates; `DiffPathScopeGate` ADMITs,
  `ForbiddenSurfaceGate` REJECTs.
- path-allowed **and** semantic-allowed specimen → **admits** (both gates).
- ambiguous classifier result → `CANNOT_TESTIFY`.
- receipts record observed paths, detected forbidden surfaces, source verdict/reason,
  projected `StepVerdict`, and `conductor_decided: false`.

## After this

Self-correction-within-scope (D008): given a refused/failing `CandidateStep`, generate a
repaired one constrained by the refusal/test receipt, resubmit through the **same**
`ag_admit` path — same grant, same intent, same semantic-surface class. Not a planner. See
`working/doctrine-ag-admit-throttle-ladder.md`.
