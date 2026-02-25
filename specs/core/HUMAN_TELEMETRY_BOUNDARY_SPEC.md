# Human Telemetry Boundary Specification

## Version 0.1 — Design Constraint

### Companion to: Kernel Constraints, Instrument Spec, Measurement Integrity

---

## Executive Summary

The governor gates **agent** proposals against evidence. It is not a human performance analytics tool. This boundary is structural, not political: applying governance instrumentation to human operators collapses the proposal/commitment separation that makes the governor work.

status: canonical

**Status**: `canonical` (design constraint, not feature spec)

See also: [`GOVERNANCE_ABUSE_AUDIT.md`](GOVERNANCE_ABUSE_AUDIT.md) — recurring
abuse audit rubric. This spec is an example of a design constraint that passes
the rubric (abuse path P4: Telemetry as Surveillance).

---

## 1. The Constraint

**The governor MUST NOT be used to measure, rank, compare, or evaluate human operator performance.**

This is not a policy preference. It is a structural requirement.

---

## 2. Why This Is Structural, Not Political

### 2.1 The Governor's Authority Derives from Proposal/Commitment Separation

The governor works because:

1. An agent **proposes** (generates output, selects tool, makes claim)
2. The governor **gates** (checks evidence, detects contradictions, scores custody)
3. Only then does **commitment** happen (tool executes, file writes, code ships)

This separation is the NLAI invariant: language is a proposal, not an authority.

### 2.2 Human Performance Measurement Collapses the Separation

If operators know the governor traces their diagnostic behavior, they will optimize their proposals to look good in the trace. This is Goodhart's Law applied to the governance layer itself:

- Operators avoid exploratory probes that might look "wasteful"
- Operators select safe-looking diagnostic paths instead of efficient ones
- Operators front-load justification instead of investigating first
- Escalation gets delayed because it "looks bad"

The result: the governor's own instrumentation degrades the quality of the cognition it's observing. The measurement corrupts the signal. This is the same eigenstructure evaporation the scalar collapse research describes — optimize for a proxy (trace aesthetics) and the true objective (diagnostic quality) degrades silently.

### 2.3 The Failure Mode Is Self-Referential

A governor that measures human performance will be gamed by humans. A gamed governor produces corrupted evidence. Corrupted evidence makes the governor's own gating decisions unreliable.

This is not "people might misuse it." This is: **the tool stops working correctly when pointed at the wrong target.**

---

## 3. Concrete Boundaries

### 3.1 MUST NOT

| Prohibited | Why |
|------------|-----|
| Per-operator efficiency metrics | Goodhart — operators optimize for trace aesthetics |
| Leaderboards or rankings derived from traces | Incentivizes gaming over diagnostic quality |
| Identity-linked aggregate analytics by default | Surveillance chilling effect degrades signal |
| "Top performers" or "improvement needed" classifications | Governor is not HR tooling |
| Operator comparison across incidents | Incidents differ; comparison is unsound |

### 3.2 MAY (With Constraints)

| Permitted | Required Constraint |
|-----------|-------------------|
| Anonymized aggregate patterns across incidents | No identity linkage; purpose-bound to reliability improvement |
| Team-level (not individual) incident metrics | MTTR, recurrence rate — never attributed to individuals |
| Operator-initiated self-review of own traces | Operator controls access; not visible to management by default |

### 3.3 Artifact Design Implications

If the governor ever ingests human-generated traces (incident logs, runbook executions, diagnostic sessions):

- **Two-tier artifacts**: `raw_trace` (restricted, short retention) and `derived_receipt` (shareable, long retention). The derived view is the default.
- **Data minimization**: Store structure (probe type, outcome class, timestamps), not content (commands, hostnames, tokens). Hash/redact by default.
- **Purpose binding**: Queries declare an intent class (`debug`, `training`, `postmortem`, `audit`). Governor enforces field visibility per intent.
- **No default identity linkage**: Pseudonymous actor IDs. Binding to real identity is opt-in, revocable, and audited.

---

## 4. The Test

> If a manager could use this feature to build a case for or against an employee, the feature is out of scope.

That's the bright line. Not because managers are bad, but because the incentive structure it creates destroys the governor's own signal quality.

---

## 5. Relationship to Existing Specs

| Spec | Connection |
|------|-----------|
| KERNEL_CONSTRAINTS | This boundary protects the kernel invariants from being undermined by misapplication |
| MEASUREMENT_INTEGRITY | Tidepool defense applies here — human gaming of traces is a measurement integrity threat |
| SCALAR_COLLAPSE_SPEC | The theoretical basis: optimizing for a proxy (trace appearance) while the true objective (diagnostic quality) degrades is the collapse pattern |
| INSTRUMENT_SPEC | Instrumentation is designed for agent runs, not human evaluation |

---

## 6. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-14 | Initial spec. Design constraint establishing human telemetry boundary. |

---

*"The governor gates agent proposals against evidence. It is not a panopticon."*

*"A measurement tool that corrupts what it measures has failed at its only job."*
