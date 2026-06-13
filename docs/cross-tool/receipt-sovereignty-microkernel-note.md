# Cross-tool design note: receipts are sovereign; Governor is an implementation

## Status

**PROVISIONAL design note** for AG self-annealing, cross-tool co-location, and
constellation microkernel architecture. Filed 2026-06-13 (interferometry pass +
operator). Records the boundary between safe microkernel-style consolidation and
unsafe monolithic merge, BEFORE further decompose/recompose work can discover a
shortcut. Companion to `rung-activation-four-office-note.md` (how one activation
transaction decomposes) — this note is *why the whole constellation may
co-locate without collapsing authority*. NOTE: this note RECORDS a design
direction; the actual kernel-invariant changes it names are future
custody-affecting work requiring the receipt-kernel supersession ceremony, not
performed here.

## Core doctrine

> **Receipts govern. Governor implements. The sovereign cannot be semantic.**

The kernel is the small, un-pleadable substrate that mediates typed messages,
capabilities, receipt custody, supersession, and invariant enforcement, and holds
the non-annealable constitutional rules. **Governor is a service running on that
substrate** — it may propose, plan, decompose, recompose, arbitrate, and
implement policy, but must NOT hold ambient authority over the offices it
coordinates. If the pleadable thing (the semantic Governor — "no minting by the
persuadable" is its whole thesis) becomes the kernel, it gains ambient authority
over every office and you have rebuilt the monolith.

This inversion is what makes self-annealing *safe*: if authority lives in the
receipts and not the Governor, you can replace the Governor without touching the
sovereign. The thing that governs does not change when the thing that implements
anneals.

## Merge rule

"Merge" is safe ONLY if it means **co-locating services behind kernel-mediated
typed boundaries**. It is fatal the instant it means linking authorities into
Governor's address space or giving Governor ambient reach.

> Co-locate the repos; never merge the authorities.

## Microkernel interpretation

A safe AG microkernel has one job: **refuse ungranted cross-boundary reach.**
Bridges are not conventions — a bridge is a kernel-granted *capability*. A service
may send a typed message only over a capability it holds; an ungranted bridge is
not a policy violation, it is structurally untraversable. This makes "no
free-standing bridge" mechanical instead of conventional, and turns the
convertibility-not-co-location test from something you audit for into something
the kernel structurally won't forward.

The seed already exists: the **13-invariant receipt kernel** is microkernel-shaped
(small, ceremonially hard to extend — that was never aesthetic), and **WLP** is
the typed IPC bus. The pivot is making those the privileged core and demoting the
semantic Governor and the offices to services on top.

## Co-location vs conversion (the standalone/federated resolution)

In a capability microkernel, co-located and distributed are the same code behind
the same typed IPC, so **standalone = offices in one process, federated = offices
on separate machines** becomes a deployment toggle with zero surgery (LA's "roles,
not repos; the boundary is authority, not deployment", made literal). Standalone
AG can honestly host Governor/Wicket, LA exactly-once, Continuity freshness, the
verifier, and the witness — four of five offices were never meant to be remote.

The one office that does not thread is **Standing**: its refusal is the only
non-mechanical one ("the asker does not get to grant its own entitlement; model
identity is attribution, not authority"), and it becomes *pleadable* the instant
it is co-resident with what it governs. So standalone AG must NOT mint its own
act- or assert-standing; the honest substitute is **operator-fiat**, typed as a
non-convertible standing stub (the loop already mandates this — the nod is the
operator's, every time).

> Standalone mode may co-host offices. It may not collapse conversions.
> Co-location was never the violation; a *conversion path* is — the day say-so
> silently becomes standing, eligibility silently becomes spend, or an
> observation silently becomes reliance, the needle snapped and you didn't see it
> because it was all one process.

## Self-annealing rule

Governor self-annealing is a **controller transition**, not a privileged internal
rewrite — it reduces to the Governor-service proposing its own successor, with no
special path:

```
1. current Governor emits a successor proposal receipt
2. kernel admits the proposal shape
3. an above-Governor authority ratifies the transition (operator-fiat — changing
   what the system may decide is a rung change Standing cannot self-host)
4. the capability holder mints the successor's capabilities
5. successor inherits RECEIPTS, not warm intentions (Paper-23)
6. successor resumes in a fresh-context AUDIT
7. successor re-derives state from receipts
8. predecessor loses active controller force
```

The capability microkernel does the heavy lifting: a service cannot amplify its
own caps, so the Governor **structurally cannot** widen its own authority during
an anneal — it can only propose a successor whose caps the *holder* grants. The
controlled cannot grant its own controller. **If self-annealing needs a privileged
backdoor that skips the offices, that is the hole. If it goes through the same
pipeline as any other rung activation, the architecture closes.**

This is why the two ideas pair rather than coincide: the microkernel is what makes
self-annealing *annealing* (bounded convergence under a constraint envelope)
instead of *melting* (uncontrolled drift with a metallurgy metaphor stapled on).
The receipt invariants are the temperature schedule.

## Non-annealable invariant (the load-bearing trap)

> **The rule requiring above-Governor ratification for a controller transition
> must live in the receipt kernel, not in Governor policy.**

If that rule lives in annealable Governor policy, a drifting Governor anneals its
own leash first: anneal #1 quietly relaxes the ratification requirement for anneal
#2, and you bootstrap to autonomy with nobody seeing it. The leash must be held by
the kernel, not by the dog being leashed.

## Fixed points

Two fixed points; everything else is annealable only through the same governed
transition path:

1. **Receipt-kernel constitutional invariants** — changed only by supersession
   ceremony; not modifiable by ordinary Governor annealing.
2. **Genesis operator-fiat root** — the initial standing root for an instance;
   exactly one genesis root per governed instance (answers the who-governs-the-
   first-Governor chicken-and-egg; from there self-annealing is self-hosting).

## Failure modes to refuse

- Governor is treated as the kernel.
- Governor can mint or widen its own capabilities.
- Governor can authorize its own successor.
- Self-annealing bypasses Standing / operator ratification.
- Controller-transition rules live in annealable Governor policy.
- Co-location becomes authority conversion.
- Receipt inheritance becomes warm-state inheritance.
- "Internal refactor" bypasses the same offices required for external action.
- Services communicate through ambient imports instead of typed capabilities.
- A bridge exists because two modules *can* reach each other, not because the
  kernel granted it.

## Acceptance tests (markers for future work — NOT implemented here)

1. A Governor successor proposal without above-Governor ratification is denied.
2. A successor proposal attempting to widen its own caps is denied unless the
   cap-holder separately grants them.
3. A Governor policy change that weakens controller-transition ratification is
   denied as a kernel-invariant violation.
4. A successor Governor starts from receipts and re-derives state; it must not
   inherit predecessor warm context as authority.
5. Two co-located services cannot communicate unless a typed kernel capability
   permits the message.
6. A direct import path between offices does not count as an authorized bridge.
7. Kernel supersession requires a separate ceremony from ordinary Governor
   annealing.

## Doctrine lines

- Receipts govern. Governor implements. The sovereign cannot be semantic.
- The Governor must not be the microkernel.
- Co-locate the repos; never merge the authorities.
- Self-annealing is a controller transition; the controlled cannot grant its own
  controller.
- The leash must be held by the kernel, not by the dog being leashed.
- If self-annealing needs a privileged backdoor, it is not annealing — it is drift
  with a nicer hat.
- Design now so extraction later is a deployment change, not a constitutional crisis.
