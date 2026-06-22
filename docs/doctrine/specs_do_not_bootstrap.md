# Specs do not bootstrap — the calculus judges construction, it does not perform it

**Status:** doctrine note + candidate primitive. Captured 2026-06-22 from a design dialogue
(emotional framing disregarded per operator; only the technical residue kept). Composes with
`weak_property_strong_property.md`, `organ-separation-and-refusal-closure-note.md`, and the
meta-plan (`docs/agent-governor-meta-plan.md`).

## The principle

> An admissibility calculus is a **specification**. Specs were never going to bootstrap into
> a built thing. A calculus *judges* construction; it does not *perform* it.

The recurring "I keep re-skinning the same work and it never becomes a built system" loop has
a precise cause: the **spec layer is being asked to become the builder layer**. It can't, so
it loops. That is not idea-exhaustion and not a missing theorem — it is one seam (spec →
built artifact) being solved by repeatedly polishing the layer next to it. The three layers
are distinct and must stay distinct:

1. **Admissibility calculus** — defines what counts as authorized / witnessed / fresh /
   spendable / admissible. (Mostly built across AG: standing, admissibility, gate receipts.)
2. **Builder / generator layer** — produces the boring glue: diffs, manifests, tests,
   harnesses, receipts, repo plumbing. **Allowed to be dumb, cheap, vibe-coded, wrong.**
3. **Governor / verifier layer** — refuses bad output; checks scope, invariants, receipts,
   authority, freshness. (Built: this is the existing gates.)

The mistake is wanting layer 1 to become layer 2. The fix needs no new doctrine — it needs a
deliberately stupid construction surface (templates, generators, narrow acceptance tests,
refusal gates) feeding the judge.

## The reframe (and the positioning)

Not **"AG builds AG."** Instead: **"AG admits or rejects generated construction steps."**

> Cheap construction, expensive admission.

When code is cheap, "looks like it works" becomes worthless and "which parts are
load-bearing / witnessed / authorized / replayable / failed-closed" becomes the scarce thing.
That is AG's whole thesis (`signed is not witnessed`). The cheap-generation wave is the
condition that makes the work matter, not the threat to it. (Composes with memory
`project_antiagentic_thesis`, `project_sidecar_retrofit_posture`.)

## Candidate primitive: `ag-admit`

The viable next move is **not a new organ** (no clever conductor, no planner, no builder-god).
It is the **mouth**: a callable surface a dumb generator talks to in order to get a
construction step admitted. The reusable piece is the **admission client**, not the loop. The
loop ("conductor") is a disposable script.

```
generate step (dumb)  →  wrap as candidate  →  submit to AG
   ADMIT          → commit + emit receipt
   REJECT         → refusal reason becomes the next constraint
   CANNOT_TESTIFY → request the missing evidence
   NEEDS_HUMAN    → stop at the human boundary
```

The intelligence lives at the **two ends** — the generator proposes (Codex/Claude, allowed
to be wrong), AG refuses (already smart, already built). **The middle stays mechanical.** The
moment the conductor starts to feel clever, that is `specs_do_not_bootstrap` reincarnated in a
new host (an "orchestrator" daemon that's secretly the self-build fantasy again). Keep the
middle stupid or the disease moves.

### Substrate check — the mouth mostly exists (do not build from scratch)

The dialogue's open fork was "does AG already expose a programmatic admission surface, or is
step zero giving it a mouth?" Grep answer (2026-06-22): **the mouth substantially exists; the
delta is shaping + unifying, not building.**

- `governed_dispatch.py`: `PreflightRequest → PreflightDecision`, with a `PreflightClient`
  **Protocol** and a `DaemonPreflightClient` RPC adapter. Already client-shaped. *But* its
  candidate is a transport/composition call and its verdict is 3-way
  `allow | would_block | blocked`.
- Runtime supervisor pre-tool gate: candidate (tool call) → `approve | deny`. Submit→verdict
  already, scoped to tool calls.
- `admissibility.py`: `AdmissibilityAssessment`, `Unknown` / `ResolvableBy` / `PushbackMode`,
  `Waiver` — the **CANNOT_TESTIFY / NEEDS_HUMAN** logic already lives here (unknowns, S3
  actuation block, clarifying questions), just not surfaced as verdicts.
- `gate check` / `evidence_gate`: submit text → `pass | block | proceed`.
- receipt_kernel: `UNKNOWN` verdict (UNKNOWN-is-failure) — the testimony-absent case.

So the **delta** is narrow:

1. A repo-agnostic `CandidateStep` shape for *construction steps* (repo, base_commit, diff,
   declared_intent, scope, touched_paths, required_authorities, tests_to_run,
   invariants_claimed, receipts_proposed, rollback_note) — distinct from `PreflightRequest`,
   which is dispatch-shaped, not diff-shaped.
2. A unified four-verdict union — `ADMIT | REJECT | CANNOT_TESTIFY | NEEDS_HUMAN` — that
   **promotes the already-existing** CANNOT_TESTIFY (admissibility unknowns / kernel UNKNOWN)
   and NEEDS_HUMAN (pushback / S3 block / pre-tool deny) concepts to first-class verdicts
   alongside allow/block. They exist scattered; the delta is the union.
3. A thin client over the existing `PreflightClient` / `DaemonPreflightClient` pattern — i.e.
   write an adapter against an API that is substantially already there.

### Hard constraints on the client (if/when built)

No planning, no generation, no policy invention, no retries inside the client, no auto-commit
unless explicitly authorized, refusal reasons are **data not vibes**, the conductor script may
loop but must stay disposable.

### Not built — forcing case to build

Not built (operator-directed: capture, do not build). **Forcing case:** a real generator
(Codex/Claude scaffold) that needs to submit construction steps programmatically and act on
the four-verdict result — i.e. the moment you actually want to remove the human as courier in
the interferometry loop you already run by hand. Until then this is the record; the
`CandidateStep` shape and verdict union are named, not ratified (no typed enum promotion until
a consumer exists — methodology `task-packet-methodology.md`, tripwire
`feedback_kind_fit_is_guard_not_enum`).

## The one-line forms (for recall)

- `specs_do_not_bootstrap` — a calculus judges construction; it does not perform it. The
  self-build loop is layer 1 trying to be layer 2.
- `ag-admit` — transcribe AG's existing refusal/admission surface (`governed_dispatch`
  PreflightClient) into a repo-agnostic `submit CandidateStep → ADMIT/REJECT/CANNOT_TESTIFY/
  NEEDS_HUMAN` client. Conductor stays stupid. Keep the middle mechanical or the disease moves.
