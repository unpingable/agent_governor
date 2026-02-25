# v2.4 Phase C — Replay & Calibration Spine

Replay stored signal/receipt windows under alternative parameters.
Normalize heuristic outputs to comparable [0,1] scales.
Make B thresholds **auditable and tunable** instead of "seems right in tests."

**Build label:** C (paper-derived from "Receipt the Compiler" §5).
Two parts: C1 (REPLAY_HARNESS) and C2 (CALIBRATION_LAYER).
Both are still **observe-only**.

**Upstream dependencies:**
- Phase A (A0–A3): signal envelope + 3 derivation signals — shipped
- Phase B1 (CAPTURE_SELF_DIAGNOSTIC): envelope-native advisory — shipped
- Phase B2 (DECISION_EVIDENCE_LAG): receipt-native temporal — shipped
- B3 (POSTERIOR_SHIFT_ATTRIBUTION): deferred to post-C

---

## 1. Phase C Invariants

### C.1 Observe-Only

Phase C may:
- Replay derivations
- Compute comparisons
- Emit envelopes/reports
- Produce frozen calibration parameter sets

Phase C must NOT:
- Alter live policy/gating
- Rewrite historical envelopes
- Mutate thresholds in place
- Backfill "corrected" values into original receipts/signals

No retroactive truth editing.

### C.2 Raw Signal Immutability

A/B envelopes are source-of-record artifacts. Calibration/replay outputs
must be companion artifacts — versioned, traceable to input hashes. Never
overwrite A/B outputs.

### C.3 Deterministic Replay

Given same input artifacts, same replay spec, and same parameter set(s),
replay must produce the same outputs. Byte-stable canonical JSON where
possible. No hidden time dependence. No ambient state.

### C.4 Provenance Closure

Every C output must carry:
- Replay run ID / hash
- Input artifact hashes (or manifest hash)
- Parameter set IDs/versions
- Derivation version

If a chart moves, you need to know why.

### C.5 Missing ≠ Zero (Still)

Phase C must preserve upstream semantics:
- Unavailable stays unavailable unless explicitly reconstructed with new inputs
- No coercing nulls into zeros during normalization
- Calibration never "repairs" missing data

### C.6 Calibration Is Parametric

Normalization must use frozen, versioned parameter sets. No adaptive online
fitting in live derivation paths (that's a v3+ governance problem).

### C.7 Suppression-Aware Calibration

By default, windows classified as instrumentation-compromised or likely
suppressed must be:
- Excluded from fitting
- Or explicitly downweighted (if weighting is supported)

Do not calibrate on blind windows and call it robust.

---

## 2. C1 — REPLAY_HARNESS

### 2.1 Purpose

Replay stored signal/receipt windows under alternative:
- Threshold sets
- Matching rules
- Weighting configs
- Calibration params (later, from C2)

Main use:
- Test threshold sensitivity
- Compare drift across versions
- Generate calibration training corpora

### 2.2 Replay Substrates

C1 supports two explicit replay modes, matching real architecture:

#### Mode A — Envelope Replay (preferred for B1-type signals)

Consumes stored `SignalEnvelope` artifacts (A/B outputs) and reruns
downstream derivations against them.

- Fastest, most deterministic
- Ideal for B1 threshold tuning
- Input: list of SignalEnvelope dicts (or JSONL path)

#### Mode B — Receipt Replay (required for B2-type signals)

Consumes stored gate receipts / receipt bundles to rerun receipt-native
derivations.

- Needed for `DECISION_EVIDENCE_LAG`
- Must be explicit, not smuggled into envelope replay
- Input: list of ReceiptRecord dicts (or receipt JSONL path)

B1 is layered (envelope-mode). B2 is parallel (receipt-mode). The replay
harness must respect this distinction explicitly.

### 2.3 Replay Inputs

#### `ReplaySpec` dataclass

Frozen config object describing one replay run:

```python
@dataclass(frozen=True)
class ReplaySpec:
    replay_spec_version: str         # "replay-harness-v1"
    replay_run_label: str            # human identifier
    target_signals: list[str]        # e.g. ["CAPTURE_SELF_DIAGNOSTIC"]
    mode: str                        # "envelope" | "receipt" | "mixed"
    time_range_start: str | None     # ISO 8601 UTC, optional filter
    time_range_end: str | None
    subject_filter: list[str] | None # optional subject_id filter
    threshold_overrides: dict[str, dict[str, Any]]  # signal_id → override dict
    derivation_version_overrides: dict[str, str]     # signal_id → version override
    include_quality_statuses: frozenset[str]          # e.g. {"ok", "partial"}
    exclude_classifications: frozenset[str]           # e.g. {"instrumentation_compromised"}
    emit_per_window: bool            # emit per-window companion outputs
    emit_summary: bool               # emit run-level summary (required True)
    notes: str                       # operator notes
    operator_id: str | None          # for provenance only
```

#### `ReplayManifest` dataclass

Content-addressed inventory of inputs consumed by a replay run:

```python
@dataclass(frozen=True)
class ReplayManifest:
    manifest_hash: str               # H(canonical_json(sorted input hashes))
    input_count: int
    input_hashes: list[str]          # content hashes of each input artifact
    source_mode: str                 # "envelope" | "receipt"
    source_path: str | None          # filesystem path for audit trail
```

### 2.4 Replay Outputs

#### A) Per-Window Replay Outputs (optional, controlled by `emit_per_window`)

Recomputed signal envelopes for each target window:

- Same `signal_id` as replayed target
- `phase = "2.4C"`
- `derivation = "derived"` (recomputed, not original)
- `derivation_version` = replay spec version
- `annotations.replay_run_id`
- `annotations.source_signal_hash` (hash of original envelope/receipts)
- `annotations.threshold_overrides` (what changed)
- Top-level `value` = replayed value

These are companion outputs, not replacements.

#### B) Replay Summary Output (required)

Run-level aggregate artifact summarizing drift and sensitivity:

```python
signal_id = "REPLAY_HARNESS"
signal_version = 1
phase = "2.4C"
subject_type = "replay_run"
unit = "score"  # or None if no drift score
derivation = "derived"
derivation_version = "replay-harness-v1"
```

`values` dict:

```python
{
    "window_count_total": int,           # windows in input corpus
    "window_count_replayed": int,        # windows actually replayed
    "window_count_skipped": int,         # windows skipped (with reasons)
    "skip_reasons": dict[str, int],      # reason → count
    "mean_abs_delta": float | None,      # mean |replayed - original| value
    "p95_abs_delta": float | None,       # p95 |replayed - original| value
    "max_abs_delta": float | None,       # max |replayed - original| value
    "classification_change_count": int,  # windows where classification changed
    "quality_status_change_count": int,  # windows where quality_status changed
    "value_increase_count": int,         # windows where replayed > original
    "value_decrease_count": int,         # windows where replayed < original
    "value_unchanged_count": int,        # windows where |delta| < epsilon
    "source_mode": str,                  # "envelope" | "receipt" | "mixed"
    "target_signals": list[str],
    "target_signal_count": int,
    "config_version": str,               # "replay-harness-v1"
}
```

`annotations` dict:

```python
{
    "config_version": str,
    "replay_spec_hash": str,             # H(canonical_json(replay_spec))
    "manifest_hash": str,                # from ReplayManifest
    "threshold_overrides": dict,
    "derivation_version_overrides": dict,
    "include_quality_statuses": list[str],
    "exclude_classifications": list[str],
}
```

Skip reasons (exhaustive):

| Reason | When |
|--------|------|
| `missing_inputs` | Required input artifact not found |
| `suppressed_excluded` | Window classification in exclude set |
| `quality_filtered` | Window quality_status not in include set |
| `alignment_failure` | Window boundaries don't match replay spec |
| `derivation_error` | Derivation function raised (logged, not fatal) |

If replay silently drops bad windows, calibration gets fake confidence.

### 2.5 Replay Semantics

Key rules:
1. Never mutate originals
2. Window alignment rules must match production
3. Input selection must be explicit and reproducible
4. Skipped windows must be counted and reasoned
5. Replay of unavailable windows stays unavailable (missing ≠ zero)
6. Derivation errors are caught, counted, and logged — never fatal

### 2.6 Replay Derivation Dispatch

The harness doesn't hardcode derivation logic. It dispatches to registered
derivation functions:

```python
# Registry maps signal_id → derivation callable
ENVELOPE_DERIVATIONS: dict[str, Callable] = {
    "CAPTURE_SELF_DIAGNOSTIC": derive_capture_self_diagnostic,
}

RECEIPT_DERIVATIONS: dict[str, Callable] = {
    "DECISION_EVIDENCE_LAG": derive_decision_evidence_lag,
}
```

This keeps the harness generic and makes adding new signals to replay
mechanical (register, don't modify).

### 2.7 Acceptance Criteria (C1)

1. Replay at least one envelope-native signal (B1)
2. Replay at least one receipt-native signal (B2)
3. Emit per-window companion outputs (on/off via spec)
4. Emit a replay summary artifact with drift stats
5. Preserve provenance (input hashes + replay spec hash + manifest hash)
6. Be deterministic on repeated runs
7. Stay observe-only
8. Skipped windows are counted with reasons
9. Missing ≠ zero preserved through replay

---

## 3. C2 — CALIBRATION_LAYER

### 3.1 Purpose

Normalize selected signal outputs to [0,1] using frozen, versioned
parameter sets.

This is how you turn useful-but-heuristic scores/rates into comparable
inputs for D (`PREDICT_REGIME_PREFLIGHT`) without changing the underlying
raw signals.

### 3.2 Scope

C2 calibrates **numeric** A/B signals only:

| Signal | Raw Range | Notes |
|--------|-----------|-------|
| `EXPOSURE_PROXY` | unbounded positive | needs normalization |
| `SIGMA_RATE` | bounded-ish | already rate, but versioned mapping |
| `CAPTURE_SELF_DIAGNOSTIC` | [0, 1] heuristic | may be identity/clip initially |
| `DECISION_EVIDENCE_LAG` backfill_rate | [0, 1] | already bounded, identity_clip |
| `DECISION_EVIDENCE_LAG` unsupported_rate | [0, 1] | already bounded, identity_clip |

Rules:
- Signals with `value=None` remain `None`
- Classification labels remain labels; calibration does not replace them
- Only top-level `value` or named fields in `values` are calibration targets

### 3.3 Calibration Parameter Sets

#### `CalibrationParamSet` dataclass

Frozen, versioned params for one source signal + one target field:

```python
@dataclass(frozen=True)
class CalibrationParamSet:
    param_set_id: str              # e.g. "exposure-proxy-cal-v1"
    signal_id: str                 # source signal
    signal_version: int            # must match source
    target_field: str              # "value" or named field in values
    method: str                    # "identity_clip" | "linear_minmax" | "log_minmax"
    params: dict[str, Any]         # method-specific frozen values
    fit_source: str | None         # replay_run_id or corpus ID
    fit_window_range: str | None   # time range used for fitting
    include_quality_statuses: frozenset[str]   # what was included in fit
    exclude_classifications: frozenset[str]    # what was excluded from fit
    fit_window_count: int | None   # how many windows contributed to fit
    fit_skipped_count: int | None  # how many windows were excluded
    created_at: str                # ISO 8601 UTC
    derivation_version: str        # "calibration-layer-v1"
```

The `params` dict is method-specific:

```python
# identity_clip
{"min": 0.0, "max": 1.0}

# linear_minmax
{"observed_min": float, "observed_max": float, "clip_min": 0.0, "clip_max": 1.0}

# log_minmax
{"observed_min": float, "observed_max": float, "log_base": float, "clip_min": 0.0, "clip_max": 1.0}
```

### 3.4 Calibration Output Semantics

Emit a new companion envelope (don't mutate source):

```python
signal_id = "<SOURCE_SIGNAL_ID>"      # same concept
phase = "2.4C"
signal_version = <source signal_version>  # unchanged
value = <normalized value [0,1]>
unit = "normalized"
derivation = "derived"
derivation_version = "calibration-layer-v1"
```

`values` dict includes:

```python
{
    "raw_value": float | None,          # original value
    "normalized_value": float | None,   # calibrated value (== top-level value)
    "calibration_method": str,
    "param_set_id": str,
    "input_quality_status": str,
    "config_version": str,              # "calibration-layer-v1"
}
```

`annotations` dict includes:

```python
{
    "source_signal_hash": str,          # H(canonical_json(source envelope))
    "calibration_applied": True,
    "param_set_id": str,
    "config_version": str,
}
```

**Important:** Do not emit calibrated values without the raw value alongside.

### 3.5 Calibration Methods (Phase C Baseline)

Small and boring. Interpretability first.

#### `identity_clip`

For already-bounded [0,1] metrics. Clips to [min, max]:

```python
def identity_clip(value: float, params: dict) -> float:
    return max(params["min"], min(params["max"], value))
```

#### `linear_minmax`

For stable bounded-ish ranges. Linear rescale + clip:

```python
def linear_minmax(value: float, params: dict) -> float:
    obs_min, obs_max = params["observed_min"], params["observed_max"]
    if obs_max == obs_min:
        return 0.5  # degenerate: all same value
    normalized = (value - obs_min) / (obs_max - obs_min)
    return max(params["clip_min"], min(params["clip_max"], normalized))
```

#### `log_minmax`

For skewed positive metrics (e.g., `EXPOSURE_PROXY`). Log transform + minmax:

```python
import math

def log_minmax(value: float, params: dict) -> float:
    base = params["log_base"]
    obs_min, obs_max = params["observed_min"], params["observed_max"]
    log_val = math.log(max(value, 1e-10)) / math.log(base)
    log_min = math.log(max(obs_min, 1e-10)) / math.log(base)
    log_max = math.log(max(obs_max, 1e-10)) / math.log(base)
    if log_max == log_min:
        return 0.5
    normalized = (log_val - log_min) / (log_max - log_min)
    return max(params["clip_min"], min(params["clip_max"], normalized))
```

No z-score wizardry unless explicitly needed. Can add `piecewise_linear`
later if signal distributions demand it.

### 3.6 Quality Propagation

Calibration must propagate quality honestly:

| Source Quality | Calibrated Quality | Notes |
|---------------|-------------------|-------|
| `ok` | `ok` | Normal calibration |
| `partial` | `partial` | Unless explicitly split |
| `unavailable` | `unavailable` | value stays None |
| `invalid` | `invalid` | value stays None |

Calibration must NOT upgrade quality.

### 3.7 Fitting Rules

When building param sets from replay corpora:

1. Exclude suppressed/instrumentation-compromised windows by default
2. Exclude invalid windows
3. Be explicit about whether partials are included
4. Record inclusion/exclusion counts in the param-set artifact
5. Require minimum window count for fit (e.g., >= 10 windows)
6. Log degenerate cases (all-same values, single window fits)

Otherwise normalized scales drift based on junk windows.

### 3.8 Param Set Mismatch Handling

When a param set doesn't match the source signal:

| Mismatch | Behavior |
|----------|----------|
| `signal_id` doesn't match | Refuse. Return error, not degraded output. |
| `signal_version` doesn't match | Refuse. Version-locked. |
| `target_field` not found | Refuse. |
| Source `value=None` | Pass through as None. quality_status preserved. |
| Method not recognized | Refuse. |

Never silently produce garbage when params don't match.

### 3.9 Acceptance Criteria (C2)

1. Apply a frozen param set to at least 2 signals (one bounded, one unbounded)
2. Emit calibrated companion envelopes with raw + normalized values
3. Preserve quality semantics (no upgrades)
4. Carry source hash + param set provenance
5. Keep normalized values in [0, 1]
6. Refuse/mark invalid when param set doesn't match signal/version
7. Stay observe-only
8. identity_clip and log_minmax both working
9. Missing ≠ zero preserved through calibration

---

## 4. Build Order

### C0 — Spec Lock (this file)

### C1 — Replay Harness Implementation

Why first:
- B1 thresholds and B2 classifications are provisionally versioned
- Replay gives the corpus + drift stats to fit calibration sanely

### C2 — Calibration Application Path

Start with **apply-only** first:
- Consume frozen param sets
- Emit calibrated envelopes

Then add fitting (from replay corpus) as a second pass. Don't merge
fitting + application in one shot.

---

## 5. Module Layout

```
src/governor/signals/
├── replay_harness.py         # C1: ReplaySpec, ReplayManifest, ReplayRunResult
│                             #     replay_windows(), replay_summary_envelope()
├── replay_sources.py         # C1: adapters for envelope/receipt bundles
│                             #     load_envelopes(), load_receipts()
├── calibration_layer.py      # C2: CalibrationParamSet, apply_calibration()
└── calibration_methods.py    # C2: identity_clip, linear_minmax, log_minmax

tests/
├── test_signals_replay_harness.py
├── test_signals_calibration_layer.py
└── fixtures/signals/
    ├── replay_summary_golden.json
    └── calibrated_envelope_golden.json
```

Keep replay orchestration separate from derivations.
Keep calibration fitting separate from application.

---

## 6. What NOT to Build in Phase C

- Live threshold adaptation (v3)
- Policy/gating changes
- Retroactive mutation of A/B artifacts
- Hidden data cleaning
- Online learning
- D-phase prediction logic (PREDICT_REGIME_PREFLIGHT)
- B3 attribution creep inside calibration
- CLI commands (deferred)
- Dashboard integration
- Cross-run trending
- Param set auto-selection

That last note matters: B3 will try to sneak in because "it's statistical."
Keep it out until calibration is stable.

---

## 7. Pre-Calibration Notice

C1 replay and C2 calibration parameter sets are initial implementations.
Phase D may require revisions to replay spec schemas, calibration methods,
or output contracts. Consumers MUST NOT treat C outputs as permanent until
validated by D-phase integration testing.

---

## 8. Relation to Existing Specs

| Document | Role |
|----------|------|
| `V2_4A_SPINE.md` | Phase A contracts + B status |
| `V2_4B_CAPTURE_SELF_DIAGNOSTIC.md` | B1 envelope-native diagnostic |
| `V2_4B_DECISION_EVIDENCE_LAG.md` | B2 receipt-native diagnostic |
| This file | C1 replay + C2 calibration contracts |
