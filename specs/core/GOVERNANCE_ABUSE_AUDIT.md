# Governance Abuse Audit Rubric

## Purpose

A recurring audit checklist for governance infrastructure features.

This is not a build spec (see `ETHICAL_HARDENING.md`) or a design constraint
(see `HUMAN_TELEMETRY_BOUNDARY_SPEC.md`). It is a **per-feature question set**
that surfaces abuse vectors before they ship.

The failure mode it targets: governance tooling that *looks* safe but creates
perverse incentives, unreceipted authority, or legitimacy cover for bad actors.

**Scope:** This audit does not certify policy morality. It audits capture
resistance, accountability symmetry, and contestability. Using this rubric
as a halo ("we ran the abuse audit") is itself a P8 risk.

status: canonical

---

## The Six-Question Test

Run these against every new feature, subsystem, or policy surface.

### 1. Who benefits from this feature being misused?

Not "could someone abuse it" (everything can be abused). Who has a
*structural incentive* to misuse it, and what does the payoff look like?

### 2. What is the appeal surface?

Where does the feature create authority, and can that authority be exercised
without leaving a receipt? Unreceipted power is the primary abuse vector.

### 3. Can the governed entity contest a decision?

If the system blocks an action, can the affected party:
- See *why* it was blocked (not just *that* it was blocked)?
- Challenge the decision with counter-evidence?
- Request a different evaluation (not just retry)?

If "no" to any of these, the feature is a gate pretending to be governance.

### 4. Can the operator change the rules without the change being visible?

Threshold changes, policy edits, exception grants — are these receipted
with the same rigor as the decisions they affect? If the operator can
quietly loosen a constraint, the constraint is decorative.

### 5. Does this feature's output get used as *input* to something else?

Observe-only signals that become gating inputs. Advisory diagnostics that
become enforcement thresholds. Exception logs that become approval records.
Every advisory→binding transition is a potential authority escalation.

### 6. What happens when this feature is used *correctly* at scale?

Some features are safe in isolation but create systemic risk at volume:
- Legitimate exceptions that accumulate into de facto policy
- Throughput that outruns review capacity
- Automation that displaces the judgment it was supposed to support

### 7. What is the operator-power delta?

For every feature, answer:
- What new power does this give operators or policy authors?
- What new accountability or receipts does it add for them?
- If power increases and accountability stays flat, flag it.

Unreceipted operator power is the single most common governance failure.
Features that add authority must add commensurate receipting.

---

## Abuse Path Taxonomy

Eight categories of governance abuse, ordered by how quietly they fail.

### P1. Legitimacy Laundering

**Pattern:** System produces receipts that look like verification but don't
actually verify anything. The receipt becomes the evidence.

**What to look for:**
- Receipt emission without meaningful evaluation
- "Pass" verdicts that don't check the thing they claim to check
- Governance artifacts cited as proof of safety downstream

**Load-bearing defenses in this codebase:**
- HARD claims require evidence (not just receipts)
- Content-addressed receipt IDs prevent forgery
- Oracle independence classes (ETHICAL_HARDENING §3) grade evidence strength

**Known gaps:**
- No mechanism to challenge a specific receipt's validity after emission
- No policy counterfactual replay ("would this have passed under policy X?")

### P2. Selective Enforcement

**Pattern:** Rules apply to some actions but not others, without a receipted
reason for the difference. "We enforce on tool calls but not on chat" is
selective enforcement unless the boundary is documented and principled.

**What to look for:**
- Code paths that bypass the gate with a good reason that isn't receipted
- Mode switches (strict→exploratory) that aren't logged
- Subsystems that emit receipts in some configurations but not others

**Load-bearing defenses:**
- Lane A (tool composition) vs Lane B (generation governance) is a documented,
  principled boundary — not selective enforcement
- Envelope mode (strict/exploratory) is explicit and persistent
- `receipt_suppressed` logging prevents silent discard

**Known gaps:**
- No unified view of "what is and isn't governed" per deployment
- Threshold changes are not receipted with the same rigor as decisions

### P3. Policy Capture via Definitions

**Pattern:** Changing what words mean instead of changing the rules. If you
control what counts as "evidence," "violation," or "HARD claim," you control
the outcome without touching the policy.

**What to look for:**
- Enum values or classification boundaries that can be changed at runtime
- Semantic terms used in policy that aren't pinned to a specific definition
- Configuration that changes *what the system measures* (not just thresholds)

**Load-bearing defenses:**
- Core terms are closed enums (ClaimType, OperationalRegime, QualityStatus)
- Golden file tests lock serialization schemas
- Signal IDs are versioned strings, not mutable labels

**Known gaps:**
- ~~`verdict` in gate receipts is a bare string, not an enum~~ **Fixed** (2.4.0:
  `VALID_VERDICTS` frozenset + `__post_init__` validation in `gate_receipt.py`)
- Policy rules aren't exportable for external inspection
- No "definition changelog" that tracks when a classification boundary moved

### P4. Telemetry as Surveillance

**Pattern:** Instrumentation designed for system health gets repurposed to
evaluate human operators. Detailed in `HUMAN_TELEMETRY_BOUNDARY_SPEC.md`.

**What to look for:**
- Identity-linked metrics that could build a performance case
- Traces that record operator *behavior* (not just system *state*)
- Features where "opt-in" is the default and opting out is conspicuous

**Load-bearing defenses:**
- HUMAN_TELEMETRY_BOUNDARY_SPEC is a canonical design constraint
- v2.4 signals are system-state derivations, not operator behavior traces
- Redaction hook in receipt kernel strips secrets pre-write

**Known gaps:**
- `principal_id` in gate receipts links decisions to operators — necessary for
  accountability but creates the exact data a surveillance regime would want
- No explicit access control on receipt queries by principal

### P5. Appeals Theater

**Pattern:** The system offers a contestability mechanism that doesn't
actually change outcomes. "You can object, but the objection is logged
and ignored."

**What to look for:**
- Resolution paths where all options lead to the same outcome
- "Proceed" options that don't actually change the evaluation
- Challenge mechanisms that require the same authority that made the decision

**Load-bearing defenses:**
- ViolationResolver offers 3 distinct paths (fix/revise/proceed) with
  different outcomes
- Override management with scoped expiry and receipted justification
- Dissent ledger preserves objections as first-class artifacts

**Known gaps:**
- No receipt-level challenge command ("I dispute this specific receipt")
- No mechanism to request re-evaluation under different parameters
- Exception records don't track whether the exception was *meaningful*
  (did the operator actually review, or just click "proceed"?)

### P6. Provenance Asymmetry

**Pattern:** The system tracks provenance for some things but not others,
creating a two-tier evidence regime. Well-tracked artifacts look more
trustworthy than poorly-tracked ones, regardless of actual quality.

**What to look for:**
- Subsystems with receipt emission vs subsystems without
- Evidence types with different levels of hash verification
- Claims that can enter the system without provenance tags

**Load-bearing defenses:**
- All gates wired: evidence_gate, intent_compiler, pre_commit, wrapper,
  continuity_checker — no silent discard
- Content-addressed hashing throughout receipt system
- `ASSUMED` provenance tag for claims that enter without evidence

**Known gaps:**
- Threshold values that affect outcomes aren't themselves receipted
- No unified audit dossier export (receipts + evidence + policy state
  for a given decision timeline)

### P7. Emergency-State Expansion

**Pattern:** Emergency modes (exploratory, fail-open) that are easy to enter
and hard to leave. The exception becomes the norm.

**What to look for:**
- Mode switches without automatic reversion
- Temporary grants that don't expire
- "Degraded" states that persist indefinitely without alerting

**Load-bearing defenses:**
- Override management requires explicit expiry
- Boil control has dwell time enforcement
- Regime detection surfaces UNSTABLE state

**Known gaps:**
- No audit trail of how long the system spent in exploratory vs strict
- No alerting when exception count crosses a threshold
- `fail_open` in governed_dispatch is binary — no graduated degradation

### P8. Compliance Theater

**Pattern:** The system's existence is cited as evidence of governance,
regardless of whether it's configured to actually constrain anything.

**What to look for:**
- Default configurations that are permissive enough to be inert
- Features that emit "pass" on everything unless explicitly tightened
- Governance artifacts that look impressive but don't block anything

**Load-bearing defenses:**
- Strict mode is fail-closed by default
- HARD claims require evidence (not just assertion)
- Preflight checks surface non-nominal configuration

**Known gaps:**
- No "governance effectiveness score" (what fraction of actions were
  actually constrained vs rubber-stamped?)
- Default thresholds are pre-calibration heuristics — they may be too
  loose for production use
- No mechanism to verify that a deployment is *actually governing*
  vs just running

---

## Finding Classification

Sort every finding into exactly one bucket. This prevents "security concern"
from becoming a catch-all that nobody can act on.

### Bucket 1: Architecture-Level Risk

Bad boundary, wrong coupling, hidden authority. Requires code changes.

*Examples:* Unreceipted operator power, advisory signal that silently
became a gating input, missing contestability path.

### Bucket 2: Spec/Documentation Risk

Built safely, but the docs don't force safe interpretation. Requires
spec or doc changes.

*Examples:* Undefined term used in policy, missing non-goal statement,
ambiguous boundary between observe-only and enforcement.

### Bucket 3: Deployment/Policy Risk

The system is fine; the regime using it isn't. Requires operational
guidance, not code.

*Examples:* Permissive defaults left unconfigured, exception grants
never reviewed, exploratory mode used in production.

---

## Running the Audit

### When to run

- Before shipping a new feature that creates authority or emits receipts
- Before promoting a signal from advisory to gating
- Before adding a new exception or override mechanism
- Annually, against the full system

### How to run

1. Pick a feature or subsystem
2. Run the six-question test (§1)
3. Check each abuse path (§2) for relevance
4. Classify findings into the three buckets (§3)
5. For each Bucket 1 finding: file a spec or create a gap doc
6. For each Bucket 2 finding: update the relevant spec
7. For each Bucket 3 finding: add to deployment guidance

### Audit record template

Each completed audit produces one record:

```
Target:      <module or spec name>
Version:     <commit hash or version>
Assessor:    <who ran the audit>
Date:        <date>
Scope:       <what was evaluated>

Questions:
  Q1 (incentive):     <finding | "no structural incentive identified">
  Q2 (appeal surface): <finding | "no unreceipted authority">
  Q3 (contestability): <finding | "N/A — does not block">
  Q4 (rule visibility): <finding | "config is explicit and frozen">
  Q5 (output coupling): <finding | "output not consumed by gates">
  Q6 (scale effects):  <finding | "no systemic risk at volume">
  Q7 (power delta):    <finding | "no operator power increase">

Findings:     <bucketed list, or "none">
Mitigations:  <required actions, or "none required">
Deferred:     <risks accepted for now, with justification>
Sign-off:     <assessor>
```

### Pass conditions

An audit passes when:
1. No unbounded operator-power increase without commensurate receipting
2. No hidden thresholds or undocumented exceptions
3. No prediction→adjudication coupling without explicit authorization path
4. All seven questions answered concretely (not "we considered it")

### Output format

Each finding should have:
- **Path**: Which abuse path (P1-P8) it falls under
- **Bucket**: Architecture / Spec / Deployment
- **Description**: What the risk is, concretely
- **Existing defense**: What already mitigates it (if anything)
- **Remediation**: What would close the gap

---

## Relationship to Other Specs

| Spec | Relationship |
|------|-------------|
| `ETHICAL_HARDENING.md` | Build backlog — features derived from running this rubric |
| `HUMAN_TELEMETRY_BOUNDARY_SPEC.md` | Design constraint — an example of a boundary that passes this rubric |
| `SELF_GOVERNANCE_SPEC.md` | 3.x architecture — many P1-P8 gaps are addressed by executor/proposer separation |
| `RECEIPT_KERNEL_CONTRACT.md` | Audit trail substrate — receipts are the primary defense against P1, P2, P6 |
| `WHY.md` | Motivation — explains why gate-not-memory matters (anti-P8) |

---

## Known Findings (as of 2.4.0)

### Architecture-Level (Bucket 1)

| # | Path | Finding | Status |
|---|------|---------|--------|
| A1 | P1 | No receipt-level challenge mechanism | Open |
| A2 | P2 | Threshold changes not receipted | Open |
| A3 | P3 | `verdict` in gate receipts is bare string, not enum | **Fixed** (2.4.0: `VALID_VERDICTS` + `__post_init__` validation) |
| A4 | P5 | No re-evaluation under different parameters | Open |
| A5 | P6 | No unified audit dossier export | Open |

### Spec/Documentation (Bucket 2)

| # | Path | Finding | Status |
|---|------|---------|--------|
| S1 | P3 | Policy rules not exportable for inspection | Open |
| S2 | P3 | No definition changelog for classification boundaries | Open |
| S3 | P7 | No documented time-in-mode tracking requirement | Open |

### Deployment/Policy (Bucket 3)

| # | Path | Finding | Status |
|---|------|---------|--------|
| D1 | P7 | No alerting when exception count crosses threshold | Open |
| D2 | P8 | No governance effectiveness metric | Open |
| D3 | P8 | Default thresholds are pre-calibration heuristics | Open |
| D4 | P4 | No access control on receipt queries by principal | Open |

---

## Appendix A: Audit Records

### A.1 — Phase D: PREDICT_REGIME_PREFLIGHT

```
Target:      src/governor/signals/predict_regime.py
Version:     2.4.0 (d3ae40e)
Assessor:    jbeck + claude
Date:        2026-02-25
Scope:       Phase D signal — regime prediction from calibrated envelopes

Questions:
  Q1 (incentive):      No structural incentive. Pure function, no authority.
                        Could be cited as "system predicted X" to justify a
                        decision, but that's P1 not D-specific.
  Q2 (appeal surface):  No authority created. Returns an envelope, does not gate.
                        No receipts emitted by the function itself.
  Q3 (contestability):  N/A — does not block any action.
  Q4 (rule visibility): Config is a frozen dataclass (PreflightConfig). Thresholds
                        explicit. Passed in, not read from hidden state.
  Q5 (output coupling): YES — designed for consumption by integration surfaces
                        (post-2.4). If wired into a gate, that's an advisory→binding
                        transition (P2/P5 risk). V2_STATUS.md says "intentionally
                        not wired" but the signal spec itself should state this.
  Q6 (scale effects):   False positives → unnecessary caution. False negatives →
                        masked regime changes. Both tolerable at current scale
                        (observe-only). Becomes material if wired to gating.
  Q7 (power delta):     No new operator power. Config is explicit. No unreceipted
                        authority added.

Findings:
  S-D1 | Bucket 2 | P5 | Prediction output could be wired as gating input
       |          |    | without the advisory→binding transition being documented.
       |          |    | Defense: V2_STATUS says "intentionally not wired."
       |          |    | Gap: signal spec should carry an explicit observe-only tag.

Mitigations:  S-D1 is low-severity. Document in signal spec when integration
              lane ships.
Deferred:     None.
Sign-off:     jbeck
```

**Result: PASS.** Phase D is a pure derivation with no authority surface.
The only finding (S-D1) is Bucket 2 (documentation) and low severity.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-25 | Initial rubric. 8 abuse paths, 7-question test, 12 known findings. Phase D audit record. |
