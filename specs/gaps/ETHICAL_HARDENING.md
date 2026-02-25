# ETHICAL_HARDENING.md

Hardening items that address ethical failure modes of semi-automated
roadmap → code → tests → package pipelines.

This document defines **testable invariants** and **receipted enforcement**.
It is not an essay.

Status: `deferred` (v3 hardening, orthogonal to current kernel work)

See also: [`GOVERNANCE_ABUSE_AUDIT.md`](../core/GOVERNANCE_ABUSE_AUDIT.md) — the
recurring audit rubric that generates items for this backlog.

## Scope

Applies to any pipeline run capable of:
- writing code/tests/docs
- opening PRs
- producing build artifacts
- generating evidence claims used for merge/release decisions

## Non-Goals

- Moral philosophy
- "Responsible AI" branding
- Perfect prevention of misuse (we target *meaningful friction* + *auditability*)

## Threat Model

Primary:
- Accountability laundering (human rubber-stamping)
- Closed epistemic loops (model self-certification)
- Review debt collapse (throughput outruns humans)
- Externality dumping (OSS maintainer load)
- IP/licensing laundering (tainted inputs → "clean" outputs)

Secondary:
- Prompt injection via untrusted artifacts
- Policy drift / capability creep
- Governor-written-by-governed bootstrapping problem

---

## 1) Downstream Load Budget (Ecosystem Externalities)

### Failure Mode

Automation turns into an "OSS maintainer DoS" machine:
- mass PRs/issues to external repos
- noisy dependency churn
- drive-by refactors nobody asked for

### Invariant: `downstream.load_budget`

**The system must not create external load above a configured budget.**

#### Budget dimensions

- `external_prs_per_week`
- `external_issues_per_week`
- `dep_update_prs_per_week`
- `max_open_external_prs`
- `max_maintainers_touched_per_week` (anti-spam dispersion control)

#### Enforcement

- If action would exceed budget → **DENY** with structured next moves:
  - queue for later epoch
  - batch changes
  - convert to local patch only
  - require explicit human "external contribution" authorization token
- ViolationResolver handles deny path

#### Receipt fields (minimum)

- `downstream_budget_snapshot`
- `downstream_action_attempted`
- `decision` (ALLOW/DENY)
- `remediation_options`

#### Tests

- Deterministic budget counters by epoch
- Deny path emits correct resolver options
- Budgets are mode-aware (strict applies; exploratory may allow local-only but never external)

---

## 2) Input Provenance Classification (IP/Licensing)

### Failure Mode

Proprietary/tainted inputs (vendor docs, proprietary code, incident logs)
influence public outputs. Even "clean-room" diffs can be derivative.

### Invariant: `provenance.classification_required`

**All non-trivial inputs must carry a provenance label, and labels must propagate.**

#### Provenance labels

- `human:authored`
- `public:open_web`
- `oss:licensed`
- `vendor:restricted`
- `corp:confidential`
- `unknown:unclassified` (treated as tainted)

#### Propagation rule

If any upstream input is `vendor`, `corp`, or `unknown`, outputs are
**tainted** unless explicitly cleared by a human-reviewed classification step.

#### Output distribution gates

- `tainted` → may open *internal-only* PRs; **cannot publish** artifacts or open external PRs
- `unknown` → **DENY** until classified

#### Receipt fields

- `input_sources[]` (id, label, hash)
- `taint_state` (clean/tainted/unknown)
- `distribution_scope` (internal/external)

#### Tests

- Taint propagation unit tests
- "unknown blocks external" regression test
- Classification changes require separate workflow (trust-root split)

---

## 3) Oracle Independence Classes (Trust Boundary Strength)

### Failure Mode

"oracle:*" evidence exists but is weak: same box, same permissions,
same compromise domain as the model. The system self-certifies via a
fake externality.

### Invariant: `oracle.independence_minimum`

**Evidence must meet a minimum independence class for high-confidence
claims in strict mode.**

#### Oracle classes (ordered by independence)

| Class | Name | Example | Trust Level |
|-------|------|---------|-------------|
| 0 | `oracle:local` | pytest on same host/session | Weak |
| 1 | `oracle:isolated_ci` | CI runner model cannot write to or configure | Moderate |
| 2 | `oracle:signed_attestation` | Artifacts signed by key unavailable to model | Strong |
| 3 | `oracle:third_party` | Independent external verification | High |

#### Policy

- Strict mode, claim confidence > 0.8 → requires >= class 1
- Security-sensitive paths → requires >= class 2
- Exploratory mode → class 0 allowed but outputs are tainted (cannot merge/release)

#### Receipt fields

- `oracle_evidence[]` (type, class, ref, hash)
- `min_required_class`
- `class_satisfied` (bool)

#### Tests

- Policy table regression tests
- "class 0 not sufficient for strict/high-confidence" tests

#### Implementation status

**Plumbed.** The `oracle.independence_minimum` invariant exists in the receipt
kernel (`libs/receipt_kernel/src/receipt_kernel/invariants/oracle_independence.py`)
with a configurable policy table `(mode, claim_level) → min_required_class`.
All defaults are currently class 0 (inert). To enforce class 1 for strict + high,
pass `policy={("factual", "high"): 1}` to the constructor. 26 tests.

The `confidence.sanity` invariant in receipt_kernel already flags HARD claims
with weak evidence. Oracle independence classes refine *what counts as strong*
beyond the current `model:*` vs `oracle:*` binary.

---

## 4) Review Capacity Coupling (Throughput vs Human Queue)

### Failure Mode

PR throughput exceeds meaningful review, causing rubber-stamp norms.
Nobody is meaningfully responsible, but everyone is formally not at fault.

### Invariant: `throughput.review_coupling`

**Automation throughput must be gated by measured human review capacity.**

#### Signals (choose any locally measurable)

- `open_pr_count`
- `median_review_age_hours`
- `reviewer_queue_depth` (if tracked)
- `merge_latency_hours` (rolling)
- `unreviewed_diff_loc` (aggregate)

#### Policy shape

- Define `review_capacity_score` from signals
- Map score → max PRs created per epoch + max merges eligible per epoch
- When capacity low: system shifts to **batching** or **documentation-only** work

#### Enforcement

- Exceeding capacity → **DENY** new PR creation; may enqueue as "pending"
- ViolationResolver offers:
  - consolidate changes into fewer PRs
  - delay to next epoch
  - request human reviewer allocation (explicit)

#### Receipt fields

- `capacity_metrics_snapshot`
- `capacity_score`
- `allowed_actions` (enum set)
- `decision`

#### Tests

- Deterministic capacity scoring on synthetic metrics
- Deny gates trigger at thresholds
- "Pending queue" behavior is stable + idempotent

#### Existing machinery

Homeostat (exploration budgets), boil control (named presets with dwell),
and regime detection (ELASTIC→UNSTABLE) already provide the signal
infrastructure. This invariant wires those signals to merge/PR throughput.

---

## 5) Comprehension Gate with Drift Detection (Anti-Checkbox)

### Failure Mode

Humans become "merge clerks." Comprehension prompts become empty ritual.
"The governor approved it" becomes moral cover.

### Invariant: `merge.challenge_response_required`

**Merge requires a falsifiable human challenge-response, not a click.**

#### Required prompts (minimum)

1. "What changed?" (structured, must reference specific files/modules)
2. "What could break?" (must reference a specific component or failure mode)
3. "What evidence supports safety?" (must cite oracle refs)

#### Drift detection (anti-ritual)

Track:
- Response entropy / repetition rate across merges
- Time-to-respond vs diff size (suspiciously fast = no reading)
- Reuse of templated phrases
- Mismatch between described change and diff fingerprint

If drift crosses threshold → escalate:
- Require second reviewer
- Require higher oracle independence class for this merge
- Reduce throughput budget for that epoch

#### Receipt fields

- `human_responses` (Q/A pairs)
- `response_quality_metrics`
- `drift_status` (OK/WARN/BLOCK)
- `escalations_triggered[]`

#### Tests

- Non-empty + schema-valid response enforcement
- Drift detection triggers on synthetic repeated answers
- Escalation path is deterministic + receipted

---

## Integration Notes

### Existing machinery mapping

| Hardening item | Governor subsystem |
|---|---|
| Deny + structured next moves | ViolationResolver (fix/revise/proceed) |
| Budgets / epochs | Homeostat, boil control, execution budgets |
| Trust-root split | Spine locks, policy separation |
| Receipts | Gate receipt system (content-addressed, JSONL + evidence store) |
| Signal tracking | Correlator telemetry, regime detection |
| Tool stripping | Scope governor (capability narrowing) |
| Override management | Scoped, expiring, receipted overrides |

### Trust-root split

Governor policy + enforcement code must be write-protected in strict mode.
Changes require an explicitly separate workflow (different review path,
different key material). Otherwise the governed can argue itself into
loosening its own leash.

This is already partially addressed by spine locks. Full trust-root split
means governor config/policy changes are **not possible** under the same
envelope as codegen.

---

## Minimal Acceptance Criteria

This hardening work is considered "present" when:

1. Each invariant has: enforcement point, receipt schema fields, and at
   least one regression test
2. Strict mode cannot:
   - publish artifacts with tainted/unknown inputs
   - accept high-confidence claims without sufficient oracle independence
   - exceed review/downstream budgets
   - merge without challenge-response
3. All deny paths emit structured receipts with remediation options
4. Drift detection on comprehension responses is active and receipted

---

## Implementation Order

These items are orthogonal to each other and to current kernel work.
Suggested order (by dependency + risk):

1. **Oracle independence classes** (extends existing confidence.sanity)
2. **Input provenance classification** (new, but small surface)
3. **Downstream load budget** (new, requires external action tracking)
4. **Review capacity coupling** (wires existing signals to new gate)
5. **Comprehension gate** (requires human interaction protocol)

Items 1-2 can ship with `oracle:pytest_log` work.
Items 3-5 are needed before scaling throughput.
