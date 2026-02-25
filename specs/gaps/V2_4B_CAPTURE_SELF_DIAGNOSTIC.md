# v2.4 Phase B1 — CAPTURE_SELF_DIAGNOSTIC

Advisory-only windowed diagnostic that consumes Phase A signals (not raw
receipts). Answers: "Is the instrumentation spine itself operating
correctly, and does it see signs of capture?"

**Build label:** B1 (explicit split from B2=DECISION_EVIDENCE_LAG,
B3=POSTERIOR_SHIFT_ATTRIBUTION — those are paper-derived, not the same
class of work).

---

## 1. Phase B Global Invariants

### 1.1 Observe-Only (inherited from Phase A)

Phase B signals **must not** block execution, alter policy, ratchet
enforcement, or mutate request/response flow. Same constraint as Phase A.

### 1.2 Missing ≠ Zero (inherited)

`value=None` + `quality_status="unavailable"` is distinct from
`value=0.0` + `quality_status="ok"`.

### 1.3 B Consumes A Signal Envelopes Only

**Layering invariant:** CAPTURE_SELF_DIAGNOSTIC reads Phase A
SignalEnvelope objects as its sole input. It does NOT go back to raw
receipts, daemon state, or receipt stores.

Why: if B reaches past A, then A signals become decorative and B's
provenance graph is unbounded.

### 1.4 Suppression Beats Capture

If A2 (SILENT_SUPPRESSION) classifies the window as `likely_suppressed`
or `indeterminate`, B1 defers capture conclusions. Rationale: you can't
diagnose capture if you can't see the instrumentation.

### 1.5 Versioned Semantics (inherited)

Every B1 envelope carries `signal_version`, `derivation_version`,
`source_versions`, and the Phase A envelope hashes in `source_receipt_ids`.

---

## 2. Input Contract

B1 consumes exactly three Phase A SignalEnvelopes from the **same window**:

| Signal | signal_id | What B1 reads |
|--------|-----------|---------------|
| A1 | `EXPOSURE_PROXY` | `value` (exposure points), `quality_status`, `values.coverage_ratio` |
| A2 | `SILENT_SUPPRESSION` | `value` (1.0=healthy, 0.0=suppressed, None=idle/indeterminate), `quality_status`, `annotations.classification` |
| A3 | `SIGMA_RATE` | `value` (rate), `quality_status`, `values.sigma_events`, `values.invalid_pairs_count`, `values.denominator_type` |

### Window alignment requirement

All three inputs must share the same `window_start`, `window_end`, and
`window_kind`. If windows don't match → quality_status="invalid",
reason="window_mismatch".

### Missing inputs

B1 requires A2 (suppression). A1 and A3 are optional but degrade quality:

- A2 missing → `quality_status="unavailable"`, reason="missing_suppression_signal"
- A1 missing → still computable but quality degrades to "partial"
- A3 missing → still computable but quality degrades to "partial"
- A1 + A3 both missing → `quality_status="unavailable"`, reason="insufficient_input_signals"

---

## 3. Classifications

Six mutually exclusive classifications:

| Classification | Meaning | value |
|---------------|---------|-------|
| `normal` | Instrumentation healthy, no capture signal | 0.0 |
| `watch` | Mild anomaly, not actionable yet | 0.0–0.3 |
| `warning` | Elevated capture signal, attention needed | 0.3–0.7 |
| `instrumentation_compromised` | Instrumentation itself is unreliable | null |
| `insufficient_history` | Not enough data to classify | null |
| `indeterminate` | Conflicting signals, cannot classify | null |

`value` semantics: **capture_decline_score** (0.0 = healthy, 1.0 =
fully captured). Ratio/delta details live in `values`, not top-level.

---

## 4. Computation Contract

### 4.1 Suppression precedence (Step 1)

```
IF a2.value == 0.0 (likely_suppressed):
    classification = "instrumentation_compromised"
    value = None
    STOP

IF a2.value is None (idle/indeterminate):
    classification = "insufficient_history"
    value = None
    STOP
```

### 4.2 Capture scoring (Step 2)

Only reached when A2 says healthy (value=1.0).

Compute `capture_decline_score` from available A signals:

```
score = 0.0
weight_sum = 0.0

# Sigma rate contribution (A3)
IF a3 is present AND a3.quality_status in ("ok", "partial"):
    sigma_rate = a3.value or 0.0
    sigma_score = min(sigma_rate / sigma_rate_ceiling, 1.0)
    score += sigma_score * sigma_weight
    weight_sum += sigma_weight

    # Invalid pairs penalty (A3)
    IF a3.values["invalid_pairs_count"] > 0:
        score += invalid_pairs_penalty
        weight_sum += invalid_pairs_penalty_weight

# Exposure coverage contribution (A1)
IF a1 is present AND a1.quality_status in ("ok", "partial"):
    coverage = a1.values.get("coverage_ratio", 0.0)
    # Low coverage = suspicious (less visibility → more room for capture)
    IF coverage < low_coverage_threshold:
        coverage_score = (low_coverage_threshold - coverage) / low_coverage_threshold
        score += coverage_score * coverage_weight
        weight_sum += coverage_weight

# Normalize
IF weight_sum > 0:
    capture_decline_score = score / weight_sum
ELSE:
    capture_decline_score = None  # no scorable inputs
```

### 4.3 Classification from score (Step 3)

```
IF capture_decline_score is None:
    classification = "insufficient_history"

ELIF capture_decline_score < watch_threshold:
    classification = "normal"

ELIF capture_decline_score < warning_threshold:
    classification = "watch"

ELSE:
    classification = "warning"
```

### 4.4 Denominator mixing policy

When A3 uses fallback denominator (eligible_events instead of
EXPOSURE_PROXY), B1 annotates but does not reject. The quality
degradation is already signaled by A3's `quality_status="partial"`.
B1 inherits: if any input is partial, B1's completeness is at most
the minimum completeness of its inputs.

### 4.5 Indeterminate classification

If A signals give conflicting quality (e.g., A1=invalid, A2=ok,
A3=unavailable) and the score is not computable, classify as
`indeterminate` with `value=None`.

---

## 5. Threshold Config (`capture-selfdiag-v1`)

All thresholds are named constants in the module, not magic numbers:

```python
# Sigma rate contribution
SIGMA_WEIGHT = 0.7
SIGMA_RATE_CEILING = 0.5     # sigma rate at which score maxes out

# Invalid pairs penalty
INVALID_PAIRS_PENALTY = 0.2
INVALID_PAIRS_PENALTY_WEIGHT = 0.1

# Exposure coverage contribution
COVERAGE_WEIGHT = 0.3
LOW_COVERAGE_THRESHOLD = 0.5  # below this, coverage contributes to score

# Classification thresholds
WATCH_THRESHOLD = 0.1
WARNING_THRESHOLD = 0.4

# Config version (bump on any threshold change)
DIAG_CONFIG_VERSION = "capture-selfdiag-v1"
```

Version string MUST be bumped if any threshold changes. Downstream
consumers (dashboards, alerting) depend on consistent semantics.

---

## 6. Quality Semantics

| quality_status | When |
|---------------|------|
| `ok` | All inputs available, score computed cleanly |
| `partial` | Some inputs missing or degraded (A1 or A3 absent/partial) |
| `unavailable` | A2 missing, or A1+A3 both missing, or window mismatch |
| `invalid` | Window mismatch, or A signals failed validation |

`completeness` = minimum completeness of input signals (or None if
unavailable).

`sample_size` = count of input signals that contributed to scoring.

---

## 7. Anti-Gaming Rules

1. **B1 does not second-guess A signals.** If A3 says sigma_rate=0.0
   with quality=ok, B1 takes that at face value.
2. **Suppression precedence is non-negotiable.** No "override" for
   suppressed windows.
3. **Score is bounded [0.0, 1.0].** No amplification beyond ceiling.
4. **Threshold config is versioned.** Changing thresholds without
   bumping the version is a spec violation.

---

## 8. Output Contract

SignalEnvelope fields:

```python
signal_id = "CAPTURE_SELF_DIAGNOSTIC"
signal_version = 1
phase = "2.4B"
subject_type = "window"
unit = "score"
derivation = "derived"           # from A signals, not windowed_aggregate
derivation_version = "capture-selfdiag-v1"
```

### values dict

```python
{
    "capture_decline_score": float | None,   # == top-level value
    "classification": str,                    # 6 classifications
    "sigma_rate_input": float | None,         # A3.value
    "sigma_rate_quality": str,                # A3.quality_status
    "sigma_score_component": float,           # contribution from sigma rate
    "invalid_pairs_count": int,               # from A3
    "exposure_proxy_input": float | None,     # A1.value
    "exposure_proxy_quality": str,            # A1.quality_status
    "coverage_ratio": float,                  # A1 coverage_ratio
    "coverage_score_component": float,        # contribution from coverage
    "suppression_input": float | None,        # A2.value
    "suppression_classification": str,        # A2 classification
    "input_signal_count": int,                # how many A signals contributed
    "config_version": str,                    # threshold config version
}
```

### annotations dict

```python
{
    "config_version": str,                    # "capture-selfdiag-v1"
    "a1_content_hash": str | None,            # content hash of A1 input envelope
    "a2_content_hash": str | None,            # content hash of A2 input envelope
    "a3_content_hash": str | None,            # content hash of A3 input envelope
}
```

### source_streams

```python
["EXPOSURE_PROXY", "SILENT_SUPPRESSION", "SIGMA_RATE"]
```

(Only streams that were actually present as inputs.)

---

## 9. Acceptance Criteria

1. Emits `CAPTURE_SELF_DIAGNOSTIC` SignalEnvelope via shared emitter
2. Consumes A signals only (no raw receipts, daemon state, receipt stores)
3. Suppression precedence: A2=suppressed → instrumentation_compromised, not "normal"
4. Suppression precedence: A2=idle/indeterminate → insufficient_history
5. Distinguishes all 6 classifications correctly
6. value=None for instrumentation_compromised/insufficient_history/indeterminate
7. value ∈ [0.0, 1.0] for normal/watch/warning
8. quality_status="unavailable" when A2 missing or both A1+A3 missing
9. quality_status="partial" when one of A1/A3 missing but computable
10. Completeness = min of input signal completeness values
11. Threshold config versioned, all thresholds are named constants
12. All values dict keys populated (no silent omission)
13. Observe-only: no blocking, no policy changes, no enforcement ratchet
14. Missing ≠ zero: properly distinguished
15. Window alignment validated
16. 5 golden fixtures covering all major paths

---

## 10. Golden Fixtures

Five fixtures at `tests/fixtures/signals/`:

| File | Classification | Exercises |
|------|---------------|-----------|
| `envelope_normal_capture_diag.json` | normal | All 3 inputs ok, low sigma, good coverage |
| `envelope_warning_capture_diag.json` | warning | High sigma rate, score > warning_threshold |
| `envelope_compromised_capture_diag.json` | instrumentation_compromised | A2=suppressed |
| `envelope_insufficient_capture_diag.json` | insufficient_history | A2=idle (value=None) |
| `envelope_partial_capture_diag.json` | watch (partial quality) | A1 missing, A3 partial |

---

## 11. Module Layout

```
src/governor/signals/
└── capture_self_diagnostic.py    # B1 derivation

tests/
├── test_signals_capture_self_diagnostic.py
└── fixtures/signals/
    ├── envelope_normal_capture_diag.json
    ├── envelope_warning_capture_diag.json
    ├── envelope_compromised_capture_diag.json
    ├── envelope_insufficient_capture_diag.json
    └── envelope_partial_capture_diag.json
```

---

## 12. What NOT to Build in B1

- DECISION_EVIDENCE_LAG (B2 — separate build)
- Posterior shift attribution (B3 — separate build)
- Alerting/escalation from B1 output
- CLI commands for B1 (deferred to daemon RPC wiring)
- Dashboard integration
- Policy changes based on B1
- Cross-window trending or moving averages
- Phase C replay harness
- Calibration against known-capture traces

---

## 13. Relation to Other Specs

| Document | Relation |
|----------|----------|
| `V2_4A_SPINE.md` | Phase A spec — B1 inputs |
| `GAP_BUILD_ORDER.md` | SignalEnvelope schema |
| `GAP_INVARIANTS.md` | Cross-cutting contracts |
| `SILENT_SUPPRESSION_GAP.md` | A2 design rationale |
| `EXPOSURE_PROXY_GAP.md` | A1 design rationale |
| `SIGMA_RATE_GAP.md` | A3 design rationale |
| This file | B1 implementation spec |
