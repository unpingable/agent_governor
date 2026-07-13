# Activation debt — a candidate backlog class (handle, not a census)

**STATUS: candidate / non-binding. A handle for review, filed 2026-07-13.**
Names a distinction so it stops living only in chat. Authorizes **nothing** to
build, enumerate, or queue. The census (`working/constellation-census-2026-07-13.md`)
answered "how much *named* work remains"; this note records the class it does
**not** measure, and the rule that keeps that class from poisoning the queue.

## The completion-predicate split

The reconciled backlog + `scripts/portfolio_report.py` measure the constellation
**as governed machinery**. They do not measure it **as an operated distributed
system**. Those are different completion predicates. Roughly: mostly built on
the first, unknown fraction on the second. The report now says so in its own
output; this note is where the class is defined.

## Four classes (the cut)

| Class | Meaning | Gate |
|---|---|---|
| **Named backlog** | already ruled + queued | in `.governor/backlog/`, the report measures it |
| **Activation debt** | required to operate a node *persistently in its intended environment* | owed only once that node's **operating posture is ratified** |
| **Scale debt** | required only at higher load / redundancy / multi-host | owed only once a *scale* posture is ratified |
| **Ambition** | plausible future, not entailed by any ruling | never owed until named |

## The load-bearing rule (why this is a handle, not a TODO dump)

> **Activation/scale obligations are un-entailed until a deployment posture is
> ratified.** A prototype at posture "private, no stability claim" (e.g. RRP)
> owes almost none of them — that is a property of its posture, not an omission.

Enumerating TLS rotation / supervision / health endpoints / backup-restore /
abuse boundaries *before* postures are ruled would declare that every prototype
owes Kubernetes and a compliance binder before it may speak. That is the exact
failure this note exists to refuse. **Do not add activation-debt items to
`.governor/backlog/` as named work.** They are not named work until entailed.

## The census this would license (LATER, forcing-case-gated)

Not "find more TODOs." The future census, if a posture gets ratified, asks
per node: *what is its intended operating posture, and what obligations follow
from that posture that have not been named?* Output shape = a maturity matrix
(node × current posture × intended posture × missing activation surfaces).
Shared-substrate discipline is a precondition, not an afterthought: ratify
common **service profiles** once (one TLS doctrine, one health contract, one
identity model), then each node declares which profile it conforms to — not
seven bespoke TLS doctrines and four creative certificate-rotation schemes.

**Forcing case for the census:** the first node whose posture is ratified to
something past "local prototype." None has been, as of 2026-07-13. **Forcing
case for *this note*:** the operator asked "how much is left," the working
report could be misread as covering activation debt, and the answer was living
only in a chat transcript — exactly the folklore the census fought.

## Non-goals

- Not a deployment plan. Not a posture ratification. Not authorization to build
  any service surface. Not queue stubs.
- Does not rule any node's intended posture — that is an operator act, per node.
