# V2_4D_PREDICT_REGIME_PREFLIGHT

**Phase D: observe-only pre-session regime prediction from calibrated signals**
**Status:** shipped (v2.5.0 — `signals/predict_regime.py`, 72 tests)
**Scope:** pure derivation over calibrated A/B envelopes. No gating, no policy, no IO.
**Design authority:** extends v2.4 instrumentation spine (A→B→C→D).

---

## 0) Purpose

Consume calibrated A/B signal envelopes and produce a single prediction
envelope: predicted regime + confidence + provenance.

This is the "typed preflight brain" on top of the calibration substrate.
It does not gate, does not learn, does not mutate anything.

---

## 1) Invariants

1. **Observe-only** — no policy/gating changes
2. **Calibrated inputs only** — raw A/B envelopes are out of scope
3. **No hidden state** — pure function over bounded input window
4. **Missing ≠ zero** — None inputs degrade prediction, not fake it
5. **Confidence is not certainty** — separate confidence score + quality
6. **Provenance closure** — input hashes, param_set hashes, window refs
7. **Suppression precedence** — instrumentation-dark overrides capture scores

---

## 2) Input contract

Bounded pre-session window of calibrated signal envelopes.

### Required signals
- EXPOSURE_PROXY (calibrated)
- SIGMA_RATE (calibrated)
- CAPTURE_SELF_DIAGNOSTIC (calibrated)

### Optional signals
- DECISION_EVIDENCE_LAG (calibrated, target_field="backfill_rate")
- SILENT_SUPPRESSION (calibrated or raw — already [0,1])

### Alignment rules
- Same window semantics (window_kind match)
- Within recency threshold
- If not aligned → indeterminate/insufficient_history

### Fallback
- Missing required → insufficient_history
- Missing optional → degrade confidence, not refuse

---

## 3) Output contract

Single SignalEnvelope:
- signal_id = "PREDICT_REGIME_PREFLIGHT"
- signal_version = 1
- phase = "2.4D"
- derivation = "derived"
- derivation_version = "predict-regime-preflight-v1"
- unit = "score"
- value = confidence [0,1]

### values payload
- predicted_regime
- confidence
- risk_score
- input_count_expected
- input_count_present
- input_count_usable
- feature_values (dict of calibrated input values)
- reason_codes (list)
- model_version

### annotations payload
- input_envelope_hashes (dict: signal_id → hash)
- suppression_precedence_applied (bool)
- config_version

---

## 4) Regime taxonomy (v1)

Compact enum, aligned with B1:
- normal
- watch
- warning
- instrumentation_compromised
- insufficient_history
- indeterminate

---

## 5) Prediction method (v1: explicit weighted heuristic)

Not ML. Deterministic weighted decision function.

1. Suppression check → if suppressed, hard branch to instrumentation_compromised
2. Insufficient usable inputs → insufficient_history
3. Compute risk_score = weighted sum of calibrated features
4. Map risk_score to {normal, watch, warning} via thresholds
5. Confidence from input completeness + quality + alignment

### Default weights (v1)
- capture_self_diagnostic: 0.40
- sigma_rate: 0.30
- decision_evidence_lag: 0.20
- exposure_proxy: 0.10

### Default thresholds (v1)
- risk_score < 0.3 → normal
- risk_score < 0.6 → watch
- risk_score >= 0.6 → warning

---

## 6) Confidence semantics

Confidence inputs:
- completeness_ratio (usable / expected)
- quality_ratio (ok inputs / usable inputs)
- alignment freshness
- any required signals missing → cap at 0.5

Confidence must be low when:
- many partials
- missing required inputs
- suppression active
- alignment mismatch

---

## 7) Failure/quality behavior

- Missing required → quality_status="unavailable", regime=insufficient_history
- Schema/alignment error → quality_status="invalid", regime=indeterminate
- Suppression branch → quality_status="ok" (evidence is clear)
- All inputs present and ok → quality_status="ok"
- Some partial → quality_status="partial"

---

## 8) Acceptance criteria

1. Consumes calibrated envelopes only
2. Deterministic for same inputs
3. Emits provenance for all input envelopes
4. Suppression precedence enforced
5. Missing inputs → insufficient_history (not fake certainty)
6. Confidence bounded [0,1]
7. Output passes validate_envelope()
8. Pure function (no IO)
9. Goldens for: normal, warning, instrumentation_compromised, insufficient_history

---

## 9) What not to build

- No ML model fitting
- No live adaptation
- No feedback loop into calibration
- No B3 attribution
- No policy/gating effects
- No hidden state between calls
