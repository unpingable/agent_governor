# Cross-tool doctrine note: active witnessing — probe is transition

## Status

**Cross-constellation candidate doctrine — non-binding, no implementation
authorized.** Filed 2026-06-19 under AG custody (see
`managed-repo-candidate-filing-note.md`). This note records **durable constraints**
on active witnessing. It deliberately does **not** specify an architecture, a verdict
taxonomy, or a build. The narrow first specimen lives as an NQ implementation
candidate (`nq/docs/working/decisions/ACTIVE_WITNESS_TLS_PROBE_CANDIDATE.md`); this
note is the constraint envelope that specimen must satisfy.

> Write constraints, not architecture. Let receipts embarrass the taxonomy into
> honesty.

## The axis this names

The constellation is mostly **passive-witness** oriented: NQ collects emitted
testimony, AG records claims/receipts, Labelwatch observes emitted labels,
Wicket/WLP/Continuity consume and adjudicate. Passive testimony supports *"observed
X"* and *"cannot testify"* — it rarely manufactures a strong **negative**.

**Active witnessing** adds a stimulus and observes whether the subject produces an
obligated response. The design prompt is *not* "bolt on healthchecks." It is: **what
protocol invariant compels testimony even when the subject was not trying to
testify?**

The orientation split (do not mistake this for a thing to build — it is a way to
read failure shapes):

| Mode | What it can say | Failure shape |
|---|---|---|
| Passive witness | "I observed X" / "I lack evidence" | gap, silence, cannot_testify |
| Active witness | "I applied stimulus S; response R did/did not occur" | refutation, contradiction, contaminated probe |
| Designed elicitation | "the protocol forces disclosure under invariant I" | strongest; rare; expensive |
| Adversarial probe | "the subject answered, but the answer may be forged" | raises the forgery bar; does not prove control |

## Core doctrine — Probe Is Transition

A probe is **not** pure observation. It is an intervention that may alter load,
caches, queues, logs, rate limits, security posture, timing, human behaviour, or
agent state.

```
Passive:  Obs(S)
Active:   T_probe(S) -> S'
```

Every active witness carries a **causal scar**. Therefore:

- Active witnessing needs its **own authority class**. It **must not** smuggle its
  output back into the passive evidence lane. The collector says what *arrived*; the
  prober says what was *forced*; the calculus decides whether the force was clean
  enough to count.

## The admissible-negative constraint (the load-bearing rule)

`witnessed-absent` is not *"I poked it and heard nothing."* It is:

> Under declared surface/protocol/horizon, stimulus S entails response R from any
> conforming/live/authorized subject. S was delivered. R was absent. Therefore
> absence is a positive fact.

A probe receipt may support a **negative claim** only when it records **all** of:

- stimulus
- target surface
- vantage / trust domain
- expected protocol invariant (the response obligation)
- delivery basis (DNS / TCP / TLS / HTTP outcome)
- response horizon (timeout)
- observed response or its absence
- **clock basis** (see below)
- perturbation class / expected side effects
- forgeability ceiling (what this probe *cannot* rule out)

Without those, a probe is merely an intervention with anecdotes. *"No evidence of X"*
is not *"evidence of not-X"* — active probing converts a gap into witnessed absence
**only where a response obligation exists.**

## The forgeability gradient

```
answered  ->  compelled  ->  challenge-bound  ->  refutation
```

An answered probe proves only that **the probed surface can answer.** It does **not**
prove the subject is uncompromised — unless the answer is bound to something the
adversary cannot cheaply forge: a fresh nonce, key custody, route/path, timing, an
independent trust anchor, a hardware root.

- **Healthcheck danger.** A 200 from `/healthz` or a live PID is *the liar still
  answering the phone.* Useful; not control proof.
- **Substrate caps the claim.** A stock VM hands you key custody, not a TPM — so every
  software witness is forgeable by on-box root. The substrate decides the primitive;
  the receipt must confess its ceiling.

## Two hidden witnesses (where this composes with existing doctrine)

1. **The clock is a hidden witness.** A negative like "expired" is admissible only
   relative to a clock. The honest verdict is `expired_under_probe_clock`, never
   `expired_absolutely` — a bad or correlated clock mis-witnesses every cert at once.
   This is the same invariant as `clock-witness-cross-constellation-note.md`: *a gap
   is not a subtraction*, and an unwitnessed clock basis makes the negative theatre
   with timestamps. UNKNOWN clock poisons the negative.
2. **Signed is not witnessed — pointed at the authority.** A CA *signs* every leaf,
   but whether the CA is itself still live is a fact handshake-success cannot see
   (mTLS succeeds right up until the root dies, then everything fails together). Probe
   the CA **as an artifact** (read its `notAfter` as a dumb signed blob), never *as an
   authority that attests its own liveness through what it authorizes.* Same demon as
   the continuity projection-receipt candidate: stored/signed is not witnessed, one
   layer up.

## UNKNOWN poisons PASS — in probe dialect

An undelivered probe, a probe with no declared invariant, or a probe on an
unwitnessed clock does **not** collapse to a clean negative *or* a clean pass. It is a
typed non-result: `probe_undelivered`, `probe_delivered_no_invariant`, `clock_unknown`
— observable, not admissible as a negative.

## Consumer map (where active witnessing fits per office)

```text
NQ:         a SEPARATE active-witness lane emitting ProbeReceipts (first specimen:
            external TLS-cert probe). Must not contaminate the passive collector.
AG:         the stimulus is a bounded decision surface (a test case); the response is
            a governance act. Refusal / escalation / misclassification become evidence.
Labelwatch: (constellation member, not local) probe the CONVERSION layer, not the
            labeler — "given label state L, render path R should/should not apply
            constraint C."
Nightshift / Wicket / WLP: admission boundaries — present known-bad / known-stale /
            known-unsupported specimens and demand refusal. Active witness as
            regression specimen.
```

## The premature-taxonomy fence (read this twice)

A multi-rung **verdict ladder is a prediction about the shape of reality**, and
predictions get *discovered*, not drawn. The durable content of this note is the set
of **constraints** above (Probe Is Transition; the admissible-negative tuple; the
forgeability gradient; the two hidden witnesses). Any complete verdict ladder is
**premature until real probe receipts exist.** Ship the ladder reality filled, not the
one drawn from the armchair. A taxonomy this tidy has not yet been corrected by
contact; the polish is the smell.

## NON_CLAIMS

This note does **not**:

- authorize building an active-witness framework, daemon, or healthchecker;
- ratify any verdict taxonomy or receipt schema (the NQ candidate proposes a *first,
  ugly* one for one specimen);
- claim NQ/Labelwatch public HTTPS surfaces exist or are reachable (the NQ candidate's
  first experiment must verify that);
- assert that an answered probe proves uncompromised control;
- convert silence into witnessed absence absent a recorded response obligation.

## Doctrine lines

- A probe is not observation; it is a transition. Active witnessing requires
  perturbation accounting.
- Passive witnessing preserves ambiguity. Active witnessing spends perturbation to buy
  negatives.
- A healthcheck is the liar still answering the phone.
- Active probing does not prove control. It creates a controlled opportunity for
  contradiction.
- Cert expiry is a scheduled refutation. The clock is the hidden witness.
- The substrate caps the claim. Write constraints; let receipts fill the ladder.
