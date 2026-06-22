# The enemy shape: weak property treated as strong property

**Status:** doctrine note, candidate. Named 2026-06-13 across a three-context design
exchange (operator + ChatGPT + Claude-web) when the same error recurred enough times to
stop being an error and start being a *shape*. This is not new doctrine — it is the
**generalization of NLAI** (*language is a proposal, not an authority*), and it names the
generator of which most of this repo's specific refusals are instances.

## The shape

> A weaker, true property is silently closed into a stronger, false one.

The weak property is real and worth having. The strong property does not follow from it.
The conversion is seductive because it *feels* like "it's handled" — local coherence
papering over the missing step.

| Weak property (true) | Strong property (does NOT follow) |
|---|---|
| witnessed | authorized |
| tamper-evident / content-addressed | legitimate / rightful authority |
| cannot launder | cannot occur |
| signed | witnessed |
| launched | admitted |
| standing | entitlement |
| valid when observed | valid when exercised |
| recovered (data) | re-admitted (authority) |
| complete (claimed) | complete (proven) |
| fresh self-report of coldness | actually cold |
| treaty / contractual adoption | enforcement |
| receipt (names its root) | force (universal authority) |
| stamped `enforcement_basis` | the strength a reader actually has |

Each row is a place where this repo has had to install an explicit refusal. They are not
separate bugs; they are the **same ghost, different bedsheet**.

## Why it's hard to see in self-report

The reasoner *building* an anti-laundering system keeps committing micro-launderings of
exactly this shape, and **cannot reliably see them in self-report** — because the
conversion is the path of local coherence, and a same-style reviewer shares the
attractor and waves it through. This was demonstrated live: the same author closed
weak→strong **four** times in one session (standing→entitlement, "can't act in the
dark"→impossible, tamper-evident→legitimate, and a stamped `enforcement_basis` field on a
receipt — *treaty→mechanical by typing the stronger word*, the field built to prevent
laundering laundering), and each time the catch came from a **different model**, never from
self-review. The fourth is instructive: it was caught by the system's *own axis* pointed
back at its *own design* — "scale is root-distance, so strength is a relation between
reader and root, therefore it cannot be a property the receipt stamps." A distance is
between two points; it cannot live on one endpoint. (See
`GOV_GAP_GOVERNOR_AS_SERVICE_AUTHORITY_ECONOMY_001` § "Scale is root-distance".)

That is not a footnote. It *is* the argument for heterogeneous review, demonstrated on the
arguer:

> **`signed-is-not-witnessed`, applied to one's own reasoning.**

A homogeneous reviewer (same model, same training attractor) preserves the error. A
heterogeneous one introduces useful phase noise. The interferometer is not a metaphor
here; it is the load-bearing control. (Composes with `independence.py` /
cooperative-redundancy and the correlator capture indicators.)

## How to apply

1. **When you feel "it's handled," name the weak property and the strong one explicitly.**
   Write the row. If the strong one does not *derive* from the weak one by a stated step,
   you have found the shape.
2. **The repair is never to make the weak property stronger by assertion.** It is to
   install the missing step as a refusal: the strong property holds only when its actual
   warrant is present; absent the warrant, refuse / quarantine / mark non-relying.
3. **Bad evidence is allowed to exist. It is not allowed to launder into authority.** You
   do not prevent the weak state; you make it non-authoritative. (You cannot stop a
   process writing files in the dark; you make the dark action have no standing.)
4. **At authority-bearing seams, get a heterogeneous check.** The error class this note
   names is precisely the one a same-model reviewer cannot be trusted to catch.

## The irreducible exception

There is exactly one place the chain is *allowed* to bottom out in an unwitnessed,
underived property: the **named genesis fiat** (the ratification root). The maturity is
not pretending no unwitnessed thing exists — that is theology. It is **naming and
minimizing** the axiom: exactly one unwitnessed root per authority instance, declared,
with everything else accountable relative to it. (See
`GOV_GAP_GOVERNOR_AS_SERVICE_AUTHORITY_ECONOMY_001` Law 5 and
`GOV_GAP_STATE_REENTRY_PROTOCOL_001`.)

## The refusal posture is scoop-proof (convergence includes the bug)

The enemy shape is *convergent*: anyone sufficiently allergic to bullshit and exposed to
enough governance / compliance / moderation / agent substrate eventually builds legibility
— receipts, checkpoints, envelopes, attestations — and then walks into the same mistake:
treating a well-formed artifact as force-bearing because it is well-formed. The rival and
the flaw converge *together*. The bug is not incidental; it is the gravity well. (Live
case: the leading near-twin, PCAA arXiv 2606.04104, *appears* to stamp its enforceability
class issuer-side — found the shape, built through the crack. Held at `appears-to` pending
a full read; the posture survives either verdict.)

So the durable claim is **not** "I built the legibility tool" — those converge; the rival
builds one too, and "I made it legible" is itself scoopable. The durable claim is one layer
down:

> **Most legibility systems accidentally launder description into authority. This work
> exists to catch that conversion error.**

That is scoop-proof, because reaching it means *not making the convergent mistake*, and the
mistake is part of the shape everyone else builds through. A certificate can describe; a
witness can attest; a receipt can preserve — **none self-promotes into binding force.**
Force is derived by the receiver / adopting root, never stamped by the packet because it
wore a little suit. *Everyone builds the stamp; the question is who gave the stamp a gun.*
It is a **refusal posture, not a feature** — which is exactly why a feature comparison
misses it.

**The proof it is real: the posture ran on itself.** The convergent meta-bug, one level up,
would have been treating an LLM's clean structured read of a rival paper as a *confirmed
finding* — well-formed testimony mistaken for force, on good news, under emotional load.
The discipline held it at `appears-to` instead. A feature can be copied; "the thing refuses
to launder even its own vindication" cannot be copied without actually building the refusal.
The product claim (catch the description→authority conversion) and the night's own process
(refuse to convert a clean read into a verdict) are the *same move*. That is the artifact.

## Laundering is conserved (the law-form of "predictive")

The shape above names *what* the error is. There is a sharper, falsifiable statement of
*where it goes when you fix it*, recovered 2026-06-22 in a fourth same-genre exchange
(operator + ChatGPT + Claude) that re-derived this whole table independently — itself a
confirming pass, and a live instance of the coupling caveat below (the two LLM witnesses
share a prior; agreement is partly resonance, not only confirmation):

> **Laundering is conserved. Close the conversion at one seam and it reappears at the
> first unreceipted boundary or interval. You never annihilate it — you force it upward,
> narrow it, name it, and make the residual assumption visible.**

The relocation ladder, each rung an actual AG seam:

```
read-time laundering        -> closed by demanding the receipt at the sink, not the read
sink-check laundering       -> moves to the check->commit interval (TOCTOU at the sink)
check->commit laundering    -> moves to resource-side enforcement (fencing / idempotency)
resource-fencing laundering -> moves to authority incumbency (is the closer still seated?)
authority-incumbency        -> moves to anchor fiat (the named genesis root)
anchor fiat                 -> the one irreducible exception above; named, not eliminated
```

This is why the shape is *predictive*: it does not just classify a past bug, it points at
the next site. Two consequences worth holding:

- **Enforcement belongs at the sink, not the read.** A read-time receipt is testimony; a
  refusal at the irreversible effect is enactment. `Declared ⊬ Enacted` at the protocol
  layer. AG already honors this on the temporal axis: the check->commit relocation is
  exactly the seam `standing_spendability.py` closes (*valid when observed, void when
  spent*), and `demo_refused_spend` is the enacted refusal. Scope this precisely: the
  **temporal axis has an enacted witness; the fencing axis (below) remains
  declaration-only**. One enacted case does not launder into "the doctrine is enacted" —
  that would be this table's own ghost, on the table.
- **The next unreceipted rung is authority incumbency.** Following the ladder past the
  seams AG has already closed lands on the one rung with *no* primitive yet: the closure
  authority's own standing at issue time (see the fencing-token candidate,
  `docs/cross-tool/closure-authority-incumbency-note.md`). The conservation law *found*
  that gap — which is the law paying rent.

The bound is also not a scalar. Temporal freshness collapses to one duration
(age ± skew); a causal frontier is a position in a partial order and does not. Folding a
frontier into one ε is the eigenstructure collapse the repo already refuses elsewhere —
admission is membership in a product region, not a `fresh_enough: bool`.

## Promotion note

This shape recurs across the constellation (standing, AG, the kernel-fuse work, cold-start,
the authority economy) and is *predictive* — it tells you where the next laundering site
will be. It is a candidate for promotion to `~/.claude/CLAUDE.md` once it has paid rent in
a second repo's review (per the doctrine-promotion rule: candidate until repeated). Kept
local for now with its firing cases here.
