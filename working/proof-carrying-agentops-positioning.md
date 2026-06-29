# Positioning anchor: Proof-Carrying AgentOps (NOT a build, NOT doctrine)

> Status: **positioning note + guardrail.** Non-binding. Does NOT authorize a build.
> Captures a pitch frame that is true to the code, and the one sentence that would
> make it a lie. File-later; do not displace the active conveyor lane (S6 next).

## The frame

**Ops-centered agent governance, not policy.** "SRE for semi-autonomous software
workers." The wedge is the AgentOps readiness question — *what's its pager policy?* —
not AI-ethics theater.

Slogan (code-accurate, survives contact): **"Don't trust the agent. Prove the cage."**

The thesis is just NLAI restated for ops: don't formally verify the probabilistic
gremlin — verify the **operational perimeter** around it (capabilities, approval
transitions, forbidden compositions, fail-closed paths, evidence-before-action).

## Completion-redshift correction: this is mostly already AG

The "constellation, ops edition" control plane is a parts list of shipped modules,
not a roadmap. Map (verified 2026-06-29):

- identity/registry → `session.py`, `runtime/supervisor.py` (`SessionRecord`), `permissions.py`
- permission matrix (RBAC/IAM) → `scope.py` (absence-restrictive, tool contracts, escalation), `permissions.py`
- run tracer → `runtime/events.py`, `instrument.py`, gate receipts
- replay → `replay.py`, `trace_recorder.py`, `replay_harness`
- policy guard → `evidence_gate` / `egress_gate` / `strict` / `scope`
- cost monitor → `telemetry analyze costs`, correlator K-vector (Cost)
- drift → `drift.py`, `mode_detection.py`, `semantic_stability.py`, `claim_diff`
- eval-as-CI → `verifier_gate.py`, `ci.py`
- external-comms guard → `egress_gate.py`

**Honest gaps (the real backlog — 4 things, not a platform):**
1. first-class agent service-catalog *manifest* (owner / last-reviewed / escalation as a declared object)
2. canary old-vs-new *behavior* diff (interferometry compares models — adjacent, not canary)
3. postmortem auto-draft from trace
4. unified agent incident-class taxonomy (`ops_governor` runbooks are ops-shaped, not agent-incident-shaped)

## The three proof tiers — already separated in AG, KEEP them separate

- **Lean = kernel-tier abstract law.** `~/git/lean` ships `AuthorizedNotSafe.lean`,
  `AuthorizedStepNotSafe.lean`, `AuthorityScope.lean`, `AdmissibilityKernels.lean`
  (+ `*Witness.lean` model-exhibits). Proves the boundary *calculus* is coherent
  ("authorized ≠ safe" as a theorem). Class-not-instance (see `feedback_lean_citation_tiers`).
- **Z3 = per-config reachability.** `constraint_gate.py` (Z3 verifier sidecar) +
  `chain_gate.py` (*"denied action compositions — sequences of allowed tool calls
  that compose into a forbidden path"*) + `spectral_stability.py` (coupling matrix /
  hotspots). This is what proves a *specific* manifest's forbidden state unreachable.
- **Runtime = enforcement + evidence.** `scope` / `egress` / `permissions` enforce;
  gate receipts = the flight recorder.

### THE GUARDRAIL (the sentence that decides truth vs slop)

> **Lean proves the KERNEL. Z3/Cedar/OPA prove the INSTANCE. Never claim Lean proves
> your customer's permission graph — and never claim "we formally verify AI behavior."**

The prod-mutation example ("no sequence reaches mutate-without-approval") is a
per-deployment Z3/model-checking obligation (chain_gate/constraint_gate), NOT a Lean
per-deployment theorem. Lean's job is upstream: proving the *rules those checks
implement* have no hole. Collapse the tiers in marketing and you've rebuilt
"formally verified AI" with better syntax. Keep the tiers visible; the pitch stays
true to the code.

## The one genuinely-new object (candidate, forcing-case-gated)

AG has every piece of an **operational proof packet** but not the single *bound*
artifact (manifest + policy + eval results + Z3 cert + Lean-warrant ref + rollback +
trace schema, sealed together). And the `ReviewPacket` from the synthetic conveyor
(S3, `src/governor/playbooks/review_packet.py`) is the **seed of exactly this** —
proof-carrying AgentOps is the *deployment-time* generalization of the conveyor's
*work-review* packet. Same primitive: structured, evidence-not-authority, validated
against a fence. Do NOT build it on this note; it needs a forcing case. The conveyor
is already walking toward it.

## Division of labor (the clean story)

- Lean → rigor (kernel warrants)
- Z3/constraint_gate/chain_gate → per-config reachability
- scope/egress/permissions + receipts → realism (enforcement + black-box recorder)
- the proof packet → binds them per deployment
- "Agent Gov" → the conceptual umbrella

## Do-not

- Do not add the consumer "prompt forge" to AG (personal productivity, not governance).
- Do not create a parallel doctrine doc (duplicate-authority smell; NLAI + directional-invariants already hold the law).
- Do not promote this note; it is a positioning anchor + guardrail, nothing more.
