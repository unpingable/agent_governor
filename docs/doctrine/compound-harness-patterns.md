# Compound harness patterns (steal the patterns, burn the vocabulary)

**Status: CANDIDATE — non-binding doctrine note.** A handle for review, not
authorization to build. Provenance: operator + ChatGPT framing, 2026-07-05, reacting
to a "self-improving agent" marketing thread. Most of what follows already exists in
AG under boring names; this note's job is to **map the seductive patterns onto the
governed primitives that admit them**, and to name the laundering cases each pattern
tempts.

## The one line

> **Compounding is admissible only when the increment is grounded outside the agent's
> own narration.**

Tests, failed runs, diffs, human rejects, governor blocks, verifier findings, CI
receipts, production telemetry — those ground an increment. "Claude learned that…"
does not. The model does not improve; **the harness accumulates reviewed state.** One
is a cape, the other is a clipboard. AG ships clipboards.

## Non-admission clause

"Self-improving," "autonomous," "routine," "skill," and "memory" are **marketing
terms** with no admission weight until reduced to governed primitives. A submission
that leans on the marketing word — not the reduced primitive — is refused, not
admitted on vibes.

## Pattern → governed primitive (the import table)

Import each thread pattern as a **harness pattern**, never a model capability. The
right column is what already exists — this is recognition, not a new module.

| Marketing term            | Governed reduction              | Already in AG (primitive)                                              |
| ------------------------- | ------------------------------- | --------------------------------------------------------------------- |
| "Self-improving agent"    | receipt-grounded refinement loop | receipt kernel + `ConvergenceExecutor` / correction ladder            |
| "Memory" / `STATE.md`     | candidate state ledger           | facts vs decisions ledgers; `ClaimStatus` (PROPOSED→…); candidate substrate |
| "Skills that compound"    | procedural rule candidates       | scars (`scars.py`, failure provenance) — updated from failures, not wins |
| `/goal` / outcomes        | bounded convergence loop         | `executor.py` spine + `InvariantSet` + `ExecutionBudget` (stop predicate + budget) |
| verifier sub-agent        | independent review actor         | `ActorOutputNormalizer` (actor can't green its own gate); independence scoring |
| dynamic workflows         | generated orchestration proposal | `intent_compiler` / plan-envelope — a plan candidate, not authority to run |
| routines                  | scheduled trigger w/ scoped standing | trigger fires within pre-granted scope; standing is separate (`standing_client`) |
| vision self-check         | artifact-level witness           | witness testifies about pixels/layout, never business truth           |
| worktrees                 | isolation boundary               | Tock-2 session-attributable promotion; the outer cage (bwrap/docker/porter) |
| fallback model routing    | capability/obstruction routing   | a classifier block becomes a recorded obstruction, not a re-route around refusal |

## Admissible loop shape

```
trigger → scoped plan → bounded execution → independent review →
receipt packet → candidate memory/rule update → human/Governor promotion
```

Every arrow is a gate that already has an implementation or a named seam. The loop is
admissible only if each arrow holds; skip one and the "compounding" is laundering.

## Forbidden laundering cases (the ones this doctrine exists to refuse)

1. Agent writes `STATE.md`, then cites `STATE.md` as evidence. *(self-authored
   evidence — the `claims_evidence_binding` / custody invariants refuse it.)*
2. Verifier sees maker reasoning and merely agrees. *(no independence — the review
   actor must run in a separate context/checkout, blind to maker rationale.)*
3. Routine runs because the schedule fired, not because standing exists. *(a clock is
   not consent; a trigger only invokes pre-granted scope.)*
4. Skill/rule update derived from a success narrative rather than failure evidence.
   *(scars are minted from failures, reverts, blocks, rulings — not from "it went
   well.")*
5. Fallback model used to route around a refusal/block. *(a block becomes an
   obstruction receipt; it is never re-tried through a weaker gate.)*
6. Generated workflow executes without being admitted as a plan. *(generated
   orchestration is reviewable recipe text, not authority to run.)*

## Promotion rule

Memory / skill / routine changes start as **candidate-class artifacts**. Promotion
requires receipts **not authored solely by the proposing agent**. This is the same
custody ladder AG already uses (local WIP → candidate → promoted) and the same law as
the "Someone" spine: **memory is not continuity until it survives rejection
pressure.**

## Not in scope (YAGNI)

No "agentic systems" module. This is a doctrine note that points at existing
primitives; build only when a specific loop needs a specific gate that does not yet
exist, with a testable acceptance criterion. Name early, ratify lazily.
