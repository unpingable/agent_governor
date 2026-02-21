# Background

This is platform reliability applied to agent runtimes.

## Why this looks like infrastructure engineering

Agent Governor treats the model as an unreliable proposer crossing a trust
boundary into real systems. The failure model is not "the model is evil," but
"the model is an unreliable component in a distributed runtime with no
guaranteed coherence, freshness, or authority." This is the same class of
problem platform reliability engineering solves at system boundaries.

## Design lineage

The patterns here come from boundary enforcement in distributed systems:
typed contracts at trust boundaries, proof-of-state before action, freshness
windows on assertions, and receipted execution for replay and audit.

The correspondences are direct:
- Δt freshness windows ↔ TTL-like freshness/cache validation semantics
  (generalized to claims and actions)
- Proof binding ↔ content-addressed state verification
- Receipts ↔ structured request logs with integrity guarantees
- Actuator gating ↔ boundary enforcement ("don't execute on
  stale/unauthorized state")
- Typed claims ↔ schema enforcement at ingress

The substrate changed. The failure modes didn't.

## What this is not

- Not a training-time alignment method. It does not attempt to make models
  morally correct.
- Not prompt engineering. It operates at the execution boundary, not the
  text boundary.
- Not an agent framework. It governs whatever runtime you use.

Training-time alignment (Constitutional AI, RLHF, etc.) can reduce bad
proposals. Runtime governance (PCAR / Agent Governor) prevents bad proposals
from becoming state changes. These are complementary layers solving different
problems.

## How PCAR fits

PCAR is the protocol family. Agent Governor is a reference implementation.
See `docs/spec/` for the draft specifications.
