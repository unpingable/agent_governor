# V2_4C_CALIBRATION_FITTING

**Phase C2 (part 2): calibration param-set fitting from replay corpus**
**Status:** locked
**Scope:** offline fitting only. Produces frozen `CalibrationParamSet` artifacts for C2 apply path.
**Design authority:** extends `V2_4C_SPINE.md §3` (C2 apply shipped at `bcfa564`).

---

## 0) Purpose

C2 apply normalizes signals using frozen param sets. C2 fitting builds those
param sets from a replay corpus in a deterministic, auditable way.

No live adaptation. No policy changes. No prediction logic.

---

## 1) Invariants

### 1.1 Observe-only
Fitting reads corpus, computes params, emits artifacts. No policy/gating changes,
no mutation of source envelopes, no auto-apply.

### 1.2 Deterministic
Same corpus + same fit spec + same method → byte-stable param set and summary.
No ambient clock dependence except explicit `created_at` (injectable for tests).

### 1.3 Provenance closure
Every fitted param set carries: fit spec hash, source manifest hash,
signal/version, target field, method, inclusion/exclusion counts.

### 1.4 Missing ≠ zero
Null/unavailable values excluded, counted, reason-coded. Never coerced to 0.

### 1.5 Suppression-aware by default
Instrumentation-compromised / suppressed windows excluded by default.
Intentional inclusion must be explicit in fit spec and visible in summary.

### 1.6 Parametric only
Fitting outputs frozen params + summary. No hidden heuristics, no online
adaptation, no mutable model state.

### 1.7 Method-specific domain validity
Fitting refuses to emit param sets that would be invalid for their apply method
(inverted bounds, missing epsilon_shift, clip outside [0,1], bad log_base).

---

## 2) Corpus Model

Fit one target at a time: one signal_id, one signal_version, one target_field,
one method.

### 2.1 Allowed sources

**A) Replay outputs (preferred):** C1 per-window companion envelopes.
Already deterministic with pinned provenance.

**B) Native signal envelopes (allowed):** Existing A/B envelopes directly.
Useful for bootstrapping before heavy replay use.

---

## 3) CalibrationFitSpec contract

Frozen dataclass. Fitting analogue to ReplaySpec.

Fields: fit_id, signal_id, signal_version, target_field, method,
source_mode ("replay"|"signal_envelopes"), source_manifest_hash,
source_replay_run_id (optional), include_quality_statuses,
exclude_classifications, exclude_null_values, min_sample_count,
clip_min, clip_max, log_base (optional), epsilon_shift (optional),
notes, created_by, created_at, derivation_version.

Content-addressed hash: `sha256:<hex>` over canonical JSON.

---

## 4) Method fitting semantics

### 4.1 identity_clip
Fixed clip bounds from spec. No corpus-derived min/max in v1.
Still requires min_sample_count consistency.

### 4.2 linear_minmax
observed_min = min(valid_samples), observed_max = max(valid_samples).
Degenerate (min == max) allowed, flagged. No quantile trimming in v1.

### 4.3 log_minmax
Same min/max extraction but with domain filtering (value + epsilon_shift > 0).
epsilon_shift explicit from spec. Degenerate allowed, flagged.

---

## 5) Exclusion reason taxonomy

One reason per dropped item (no double-counting):
- signal_version_mismatch
- target_field_missing
- non_numeric_value
- bool_value
- missing_value
- quality_excluded
- classification_excluded
- domain_invalid (log_minmax: value + epsilon_shift <= 0)

---

## 6) Outputs

### 6.1 Fitted CalibrationParamSet (on success only)
Populated with fit provenance: fit_source, fit_window_range,
fit_window_count, fit_skipped_count, include/exclude sets.

### 6.2 Fit summary SignalEnvelope (always emitted)
signal_id="CALIBRATION_FIT_SUMMARY", phase="2.4C", derivation="derived".
quality_status="ok" on success, "unavailable"/"invalid" on failure.
values payload: all corpus stats, exclusion counts, provenance hashes.

---

## 7) Failure behavior

No param set emitted. Summary emitted with quality_status="unavailable" or
"invalid" and explicit failure reason in quality_reasons.

---

## 8) Acceptance criteria

1. Fit identity_clip deterministically
2. Fit linear_minmax from valid corpus
3. Fit log_minmax with explicit epsilon_shift
4. Refuse invalid fit specs
5. Refuse insufficient valid samples
6. Emit exclusion counts with explicit reasons
7. Exclude suppressed windows by default
8. Emit fit summary with provenance + stats
9. Deterministic param_set_hash + summary for same corpus/spec
10. Fitted param sets accepted by apply_calibration()

---

## 9) What not to build

- No online/adaptive fitting
- No auto-rotation of param sets
- No auto-apply of newly fit params
- No policy/gating changes
- No D-phase prediction
- No B3 attribution
- No hidden outlier trimming (quantiles deferred)
- No silent coercion of invalid values
