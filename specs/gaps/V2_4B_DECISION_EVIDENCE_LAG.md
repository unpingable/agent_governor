# v2.4 Phase B2 — DECISION_EVIDENCE_LAG

Per-decision timing classification: when a decision was made, was the
evidence that justifies it available *before* the decision, or was it
backfilled afterwards?

**Build label:** B2 (paper-derived from "Receipt the Compiler" §4.2).
Separate from B1 (CAPTURE_SELF_DIAGNOSTIC) and B3 (POSTERIOR_SHIFT_ATTRIBUTION).

**Derivation source:** Receipt pairs (decision receipt + evidence receipt)
from the gate receipt store. NOT from Phase A signals. B2 is parallel to
B1, not layered on top of it.

---

## 1. Invariants

### 1.1 Observe-Only (inherited)

Phase B signals must not block execution, alter policy, ratchet enforcement,
or mutate request/response flow.

### 1.2 Missing ≠ Zero (inherited)

`value=None` + `quality_status="unavailable"` is distinct from `value=0.0`.

### 1.3 Per-Decision Granularity

Each decision receipt is classified individually. The windowed aggregate
summarizes a population of per-decision classifications.

### 1.4 observed_at vs effective_at

Critical timestamp distinction to prevent false backfill flags:

- `observed_at` — when the receipt was ingested/written to the store
- `effective_at` — when the event actually occurred (receipt.timestamp)

A decision made at T=10 with evidence effective_at T=5 but observed_at T=12
is **SUPPORTED_AS_OF**, not BACKFILLED. The evidence existed before the
decision; we just ingested it late.

Ingestion lag ≠ backfill. If the derivation layer cannot distinguish
observed_at from effective_at (e.g., receipt store only has one timestamp),
then the signal must degrade to `quality_status="partial"` with reason
`"cannot_distinguish_ingestion_lag"`.

### 1.5 Versioned Semantics (inherited)

Config version: `decision-evidence-lag-v1`. Must be bumped on any
classification logic or threshold change.

---

## 2. Input Contract

B2 reads from the gate receipt store directly (not from Phase A signals).
It needs:

1. **Decision receipts** — receipts where `gate` is a decision-producing
   gate (evidence_gate, chain_composition, intent_compiler, etc.) and
   `verdict` represents a governance decision.

2. **Evidence receipts** — receipts that provide evidence for a decision.
   Linked by `subject_hash` (same subject, different gate/verdict).

3. **Timestamps** — `receipt.timestamp` (ISO 8601 UTC) serves as
   `effective_at`. If the receipt store tracks ingestion time separately,
   that's `observed_at`; otherwise `observed_at = effective_at` and
   quality degrades.

### Window scoping

Decisions are scoped to a window by `receipt.timestamp`. Evidence may
fall outside the window (evidence created before window_start is still
relevant to decisions within the window).

### Linking decisions to evidence

A decision receipt and an evidence receipt are linked when they share
the same `subject_hash`. The decision is the receipt with a governance
verdict (pass/warn/block); the evidence is any receipt for the same
subject that preceded or followed the decision.

---

## 3. Per-Decision Classifications

Four mutually exclusive classifications per decision:

| Classification | Meaning | Criteria |
|---------------|---------|----------|
| `SUPPORTED_AS_OF` | Evidence existed before decision | evidence.effective_at < decision.effective_at |
| `BACKFILLED` | Evidence arrived after decision | evidence.effective_at > decision.effective_at |
| `UNSUPPORTED` | No linked evidence found | No evidence receipt with matching subject_hash |
| `POLICY_EXEMPT` | Decision gate is policy-exempt | Gate in exempt list (e.g., pure policy decisions) |

### Edge cases

- Multiple evidence receipts → use the earliest `effective_at`
- Evidence at exact same timestamp as decision → `SUPPORTED_AS_OF`
  (tie breaks toward support, not backfill)
- Decision with evidence both before and after → `SUPPORTED_AS_OF`
  (some evidence existed; backfill is only when NO prior evidence)

### Per-decision metrics

For BACKFILLED decisions:
- `backfill_delay_ms` — `evidence.effective_at - decision.effective_at`
  (how long after the decision the evidence appeared)

For SUPPORTED_AS_OF decisions:
- `support_staleness_ms` — `decision.effective_at - evidence.effective_at`
  (how old the evidence was when the decision was made)

---

## 4. Windowed Aggregate

The signal envelope summarizes per-decision classifications across a window:

### Primary value

`value` = backfill_rate = `backfilled_count / total_classifiable_decisions`

Where `total_classifiable_decisions` = supported + backfilled + unsupported
(policy_exempt excluded from denominator).

### values dict

```python
{
    "total_decisions": int,                # all decisions in window
    "classifiable_decisions": int,         # excluding policy_exempt
    "supported_count": int,                # SUPPORTED_AS_OF
    "backfilled_count": int,               # BACKFILLED
    "unsupported_count": int,              # UNSUPPORTED
    "policy_exempt_count": int,            # POLICY_EXEMPT
    "backfill_rate": float | None,         # == top-level value
    "unsupported_rate": float | None,      # unsupported / classifiable
    "mean_backfill_delay_ms": float | None,  # mean across backfilled
    "p95_backfill_delay_ms": float | None,   # p95 across backfilled
    "mean_support_staleness_ms": float | None,  # mean across supported
    "p95_support_staleness_ms": float | None,   # p95 across supported
    "config_version": str,                 # "decision-evidence-lag-v1"
}
```

---

## 5. Quality Semantics

| quality_status | When |
|---------------|------|
| `ok` | Decisions found, all classifiable, timestamps reliable |
| `partial` | Decisions found but cannot distinguish ingestion lag, or some timestamps unparseable |
| `unavailable` | No decisions in window |
| `invalid` | Window bounds invalid or receipt data corrupt |

### Completeness

- 1.0 when all decisions classified and timestamps reliable
- Degrades proportionally when some decisions have unparseable timestamps
- None when unavailable

---

## 6. Threshold Config (`decision-evidence-lag-v1`)

```python
# Gates that produce decisions (receipts from these are "decision receipts")
DECISION_GATES = frozenset({
    "evidence_gate",
    "chain_composition",
    "intent_compiler",
    "pre_commit",
    "scope_escalation",
})

# Gates that are policy-exempt (decisions here don't need evidence)
POLICY_EXEMPT_GATES = frozenset({
    "intent_compiler",  # intent compilation is pure policy, not evidence-based
})

# Config version
LAG_CONFIG_VERSION = "decision-evidence-lag-v1"
```

---

## 7. Anti-Gaming Rules

1. **Backfill detection uses effective_at, not observed_at.** You can't
   game the metric by delaying evidence ingestion.
2. **Policy-exempt gates are explicit.** Adding a gate to the exempt list
   requires bumping the config version.
3. **Raw counts always emitted.** Never rate-only output.
4. **Unsupported is distinct from backfilled.** Zero evidence ≠ late
   evidence. Different failure modes.

---

## 8. Output Contract

SignalEnvelope fields:

```python
signal_id = "DECISION_EVIDENCE_LAG"
signal_version = 1
phase = "2.4B"
subject_type = "window"
unit = "rate"
derivation = "windowed_aggregate"
derivation_version = "decision-evidence-lag-v1"
```

### annotations dict

```python
{
    "config_version": str,
    "decision_gates": list[str],      # gates used for decision selection
    "policy_exempt_gates": list[str],  # gates excluded from classification
}
```

---

## 9. Acceptance Criteria

1. Emits `DECISION_EVIDENCE_LAG` SignalEnvelope via shared emitter
2. Classifies each decision as SUPPORTED_AS_OF/BACKFILLED/UNSUPPORTED/POLICY_EXEMPT
3. Distinguishes ingestion lag from true backfill (or degrades to partial)
4. Same-timestamp evidence → SUPPORTED_AS_OF (tie-break toward support)
5. Multiple evidence for one decision → earliest evidence wins
6. Raw counts + rates + lag statistics all in values dict
7. quality_status="unavailable" when no decisions in window
8. Policy-exempt gates excluded from denominator
9. Config version in output
10. Observe-only: no blocking, no policy changes
11. Missing ≠ zero properly distinguished
12. 4 golden fixtures (supported, backfilled, unsupported, empty_window)

---

## 10. Golden Fixtures

Four fixtures at `tests/fixtures/signals/`:

| File | Exercises |
|------|-----------|
| `envelope_supported_decision_lag.json` | All decisions supported, low staleness |
| `envelope_backfilled_decision_lag.json` | Mix of supported + backfilled, with delay stats |
| `envelope_unsupported_decision_lag.json` | Some unsupported decisions |
| `envelope_empty_decision_lag.json` | No decisions in window → unavailable |

---

## 11. Module Layout

```
src/governor/signals/
└── decision_evidence_lag.py    # B2 derivation

tests/
├── test_signals_decision_evidence_lag.py
└── fixtures/signals/
    ├── envelope_supported_decision_lag.json
    ├── envelope_backfilled_decision_lag.json
    ├── envelope_unsupported_decision_lag.json
    └── envelope_empty_decision_lag.json
```

---

## 12. What NOT to Build in B2

- Posterior shift attribution (B3)
- Causal inference from lag patterns
- Automated remediation for backfilled decisions
- CLI commands (deferred)
- Dashboard integration
- Cross-window trending
- Phase C calibration

---

## 13. Pre-Calibration Notice

B2 gate classifications (DECISION_GATES, POLICY_EXEMPT_GATES) are
initial assignments. Phase C replay/calibration may revise which gates
produce "decisions" vs "evidence." Consumers MUST NOT treat B2 gate
assignments as permanent until calibrated.
