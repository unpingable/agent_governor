# Cross-tool design note: conscientious behavior is not custody

## Status

**PROVISIONAL design note — durable doctrine + a named audit, authorizes no build.**
Filed 2026-06-13 (operator + interferometry, generalizing the fuse finding). Names a
recurring disease and the audit that finds the rest of its population. Composes with
`receipt-sovereignty-microkernel-note.md` (the leash must be held by the kernel, not
the dog) and `GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001` (the first concrete instance).

## The disease

> **A refusal practiced by the runner instead of enforced by the kernel.**

We have now hit the same bug three times — decomposition completeness, the chain
fuse, and (by induction) more to come. Each time, an invariant that *should* be
mechanical was instead a behavior the runner performs out of conscientiousness.

The cruel part is why it keeps hiding: **the convention works in testing.** A
well-behaved runner halts on its own, refuses on its own, asks on its own — so the
unencoded invariant looks encoded. It only breaks with a *less*-conscientious runner:
a different model, an AUTO_RUN with no etiquette, a drifted future controller. That
is "folklore with a README" — constitutional law that is actually just habit.

> **Conscientious behavior is not custody.**
> **Claude halting is weather. Kernel refusal is verdict.**

This is last turn's labeler finding turned inward: the runner has been *asserting at a
scope it cannot cash* — presenting fuse/refusal *behavior* without fuse/refusal
*authority*. The fix is the same: make the kernel the thing that actually cashes it.
Weather is advisory and behavioral; a verdict is binding and mechanical.

## The audit: find every place a conscientious runner is load-bearing

Each item below is an unencoded invariant wearing an encoded one's clothes. Classify
each: does it protect **mutation, authority, spend, discharge, or a kernel
invariant**? If yes, it needs mechanical backing. If it is purely a workflow norm
(timing, courtesy), it is fine as etiquette.

| Runner behavior (currently load-bearing) | Protects | Verdict |
|---|---|---|
| stops after the fuse / does not keep mutating after Codex fail | mutation | **needs backing** — `GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001` |
| asks before scope expansion (§11.3 scope-expanding remedy halts) | authority/scope | **needs backing** — same kernel-fuse family |
| does not self-ratify operator branches (model is not principal) | authority | **partial** — P3.3 `OperatorRatification` / P3.4 `OperatorDischargeEvidence` require a structured ref (shape backed); genuine provenance custody-anchoring is future |
| does not clear claims by rephrasing them | discharge | **partial** — P3.4 operator-gated discharge socket for one claim kind; generic discharge across other kinds is still `DebtLedger.discharge()` flag-flip (`GOV_GAP_DISCHARGE_COLLECTOR_BINDING_001`) |
| does not reinterpret weak receipts as strong | authority/migration | **needs backing** — the stub→real upgrade hot path; P3.3 receipt-shape names it, enforcement future |
| does not treat docs as authority (instruction files shape behavior; the governor determines admissibility) | authority | **needs backing** — the governor must actually gate, not rely on the runner's restraint |
| does not mint/widen its own caps or authorize its own successor | authority/kernel | **needs backing** — receipt-sovereignty note; self-annealing ratification must be a kernel invariant |
| does not push during work hours | timing/courtesy | **etiquette OK** — a norm, not custody (but the *publication* boundary itself is consequence-bearing — see the hotpath note's externalization path) |

The pattern: most "Claude does not X" rules that feel like safety are protecting
mutation/authority/spend/discharge/kernel — and each is currently held by good
behavior, not by a wall. Filing the fuse gap is necessary but not sufficient: the
fuse is one *sample* from this population, not the whole of it.

## What "backed" means (the shape, not a flag)

Mechanical backing is a structural absence, not an honored boolean. The pattern this
repo already ships:

- a privileged action requires a **consumed capability / structured evidence object**
  (the `isinstance(OperationalConsumed)` spend wall; P3.3/P3.4 evidence sockets);
- the runner's restraint becomes irrelevant because the *missing thing* the wall
  requires is simply not there;
- the rule about when the thing may exist lives in the **receipt kernel**, behind the
  supersession ceremony, where a self-annealing Governor cannot reach it.

> The goal is not fewer halts. The goal is **halts only where authority enters the
> room** — and held by the kernel, not by the runner's conscience.

## Doctrine lines

- Conscientious behavior is not custody.
- Claude halting is weather; kernel refusal is verdict.
- A refusal practiced by the runner instead of enforced by the kernel is folklore
  with a README.
- The convention works in testing precisely because the runner is well-behaved —
  which is why it hides until a worse runner holds it.
- Backing is a structural absence (no cap / no evidence), not an honored flag.
- The rule about the leash lives in the kernel, not the dog.

## Non-goals

- NOT building the mechanical backing now (per-site; mostly custody-affecting kernel
  work behind the supersession ceremony).
- NOT promoting workflow norms (timing/courtesy) into custody — only the items that
  protect mutation/authority/spend/discharge/kernel need walls.
- This note enumerates and classifies; each "needs backing" row earns its own gap +
  slice when its forcing case lands.
