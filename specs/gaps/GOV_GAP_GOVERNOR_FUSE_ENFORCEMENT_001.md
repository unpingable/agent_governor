# GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001

## Title

The chain fuse is currently *practiced* by the Claude/operator loop, not *enforced*
by the receipt kernel — make fuse-firing a structural absence of mutation caps, and
re-arm operator-fiat, so a less-conscientious or self-annealed Governor cannot grind
past it.

## Status

**Candidate — names a constitutional obligation, authorizes no build.** Filed
2026-06-13 (operator + interferometry). The actual change (a receipt-kernel
invariant + cap-holder enforcement) is custody-affecting — it touches the kernel's
constitutional invariants and is therefore *supersession-ceremony* work, NOT
ordinary slice work; this gap installs the refusal and the acceptance markers now.
Composes with `docs/cross-tool/receipt-sovereignty-microkernel-note.md` (the leash
must be held by the kernel, not the dog) and
`docs/cross-tool/conscientious-behavior-not-custody-note.md` (the fuse is the first
sample from that population). First concrete instance of the fuse:
`docs/loop-protocol.md` §11.3.

## Problem

Fuse discipline (a second refinement pass / exhausted retry budget converts
execution into AUDIT, not "one more small fix") is currently a behavior of the
Claude/operator loop — etiquette, advisory, weather. It is not enforced by the
receipt/capability kernel. It *looks* enforced only because a conscientious runner
halts on its own; the convention works in testing precisely because the runner is
well-behaved. It breaks the moment a less-conscientious runner holds it — a
different model, an AUTO_RUN with no etiquette, a drifted future controller.

## Risk

A self-annealed or non-conscientious Governor may (a) keep mutating the repo after
the retry/Codex fuse is exhausted, or (b) re-arm its own retry/Codex budget and loop
unboundedly — one self-ratification at a time. The fuse is the *same class* as the
self-annealing ratification requirement: a limit on the Governor's own runaway, and
exactly the limit a drift-toward-autonomy wants to relax. By the identical theorem,
it cannot live in the Governor (the dog cannot hold the rule about its own leash).

## Doctrine

> The fuse is a **receipt-kernel invariant**, not Governor policy and not Claude
> etiquette. **Firing converts execution to audit by WITHHOLDING mutation caps** —
> not by setting a `mutation_allowed=false` flag anyone must honor. **Re-arm is
> operator/kernel-fiat.** The Governor may *propose* "continue with budget N"; it may
> not authorize, mint, or reset it.

- **Claude halting is weather. Kernel refusal is verdict.**
- The Governor doesn't get to hold the *rule about the lighter* — constitutional,
  not policy.

## Enforcement through machinery already shipped (additive, not remedial)

Fuse-firing need not be a new flag: a fired fuse means the **cap-holder stops
minting mutation caps for the slice**, and the `isinstance(OperationalConsumed)`
spend wall *already in the tree* (`cooked_context_orchestrator.py`, per the
conversion-path audit) refuses the mutation because there is no consumed operational
token to pass it. `mutation_allowed: false` is then a **structural absence**, not an
honored flag — the same valve-before-the-leak shape as the receipt-shape slice.

Optional receipt: a `FuseExhaustedReceipt` (slice_id, retry_budget, codex_cycles,
findings, classification, last_safe_commit, working_tree_state,
recommended_operator_questions, `mutation_allowed: false`) makes the audit state
walkable — but the *enforcement* is the missing cap, not the receipt.

## Acceptance criteria (NOT implemented here)

- AC1: after fuse exhaustion, no mutation cap can be minted for that slice.
- AC2: the mutation wall refuses without a consumed operational cap.
- AC3: the Governor cannot reset its own fuse state.
- AC4: the Governor cannot increase its own retry / Codex budget.
- AC5: operator re-arm emits a receipt and a new BOUNDED budget; the Governor only
  *proposes* continuation, never mints it.
- AC6: self-annealing cannot modify the fuse invariant except via the kernel
  supersession ceremony.
- AC7: the fuse applies uniformly to Claude/operator loops, AUTO_RUN,
  Governor-managed slices, self-annealing controller transitions, verifier/Codex
  retry cycles, and any bounded repair loop that can mutate repo state.

## Non-goals

- NOT building the receipt-kernel invariant now (custody-affecting; supersession
  ceremony).
- NOT building the capability microkernel / cap-holder now (future — composes with
  the office-collapse and receipt-sovereignty gaps).
- NOT making the fuse smarter for auto-application yet (the "which finding classes
  may be auto-applied" policy is a *separate*, later question; this gap is about
  *enforcement*, not *relaxation*).

## Doctrine line

> A fuse firing converts execution into audit. Not "try harder," not "one more
> small fix" — audit. And the Governor does not get to re-arm itself.
