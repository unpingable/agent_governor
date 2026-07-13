# Activation debt — a candidate backlog class (handle, not a census)

**STATUS: candidate / non-binding.** Filed 2026-07-13; trimmed same day.
Names a distinction so it stops living only in chat. Authorizes **nothing** to
build, enumerate, or queue.

The *measurement boundary* — what the portfolio report counts and refuses to
count — now lives where it belongs, in `scripts/portfolio_report.py`'s module
docstring. This note keeps only the two things a report's docs shouldn't carry:
the **class taxonomy** (a durable handle) and the **gate on the future census**.

## The four-class cut

| Class | Meaning | Owed when |
|---|---|---|
| **Named backlog** | ruled + queued | now (it's what the report measures) |
| **Activation debt** | required to operate a node *persistently in its intended environment* (TLS, supervision, backup/restore, health, identity, secrets) | its node's **operating posture is ratified** |
| **Scale debt** | required only at higher load / redundancy / multi-host | a *scale* posture is ratified |
| **Ambition** | plausible future, not entailed by any ruling | named |

## The rule (why this is a handle, not a TODO dump)

> **Activation/scale obligations are un-entailed until a deployment posture is
> ratified.** A prototype at posture "private, no stability claim" (RRP) owes
> almost none — a property of its posture, not an omission.

Enumerating TLS rotation / supervision / health endpoints before postures are
ruled declares every prototype owes Kubernetes and a compliance binder before
it may speak. **Do not add activation-debt items to `.governor/backlog/`** —
they are not named work until entailed.

## The future census this gates (LATER)

Not "find more TODOs." If a node's posture is ratified past "local prototype,"
the census asks, per node: *what obligations follow from that posture that have
not been named?* Output = a maturity matrix (node × current posture × intended
posture × missing activation surfaces). **Precondition:** shared **service
profiles** ratified once (one TLS doctrine, one health contract, one identity
model) so nodes *conform to* a profile rather than each inventing certificate
rotation. **Forcing case:** the first node ratified past local prototype — none
as of 2026-07-13.

## Non-goals

Not a deployment plan, a posture ratification, or authorization to build any
service surface. Does not rule any node's intended posture — an operator act,
per node.
