# v2.4 Phase A — Instrumentation Spine

Build contracts for the three Phase A signals. This document is the
implementation spec — the per-signal gap specs (`SILENT_SUPPRESSION_GAP.md`,
`EXPOSURE_PROXY_GAP.md`, `SIGMA_RATE_GAP.md`) are retained as design
rationale. `GAP_BUILD_ORDER.md` defines the `SignalEnvelope` and cross-cutting
contracts. This file defines **what to build** and **what "done" looks like**.

---

## 1. Phase A Global Invariants

These bind every Phase A signal. Violating any of them makes this decorative
telemetry, not instrumentation.

### 1.1 Observe-Only

Phase A signals **must not**:

- Block execution
- Alter policy mode
- Ratchet enforcement
- Mutate request/response flow

They **may**:

- Emit `SignalEnvelope` events
- Write receipts / telemetry
- Increment counters
- Log diagnostic warnings (non-blocking)

v2.4 builds admissible measurement. It does not sneak in v3 gating.

### 1.2 Missing ≠ Zero

If a signal cannot be computed (missing inputs, daemon unavailable, invalid
receipt chain), emit:

- `value_raw = None`
- `quality_status = "unavailable"` (via `severity = "info"` + `reason_codes`)
- Explicit reason code from `ReasonCode` enum

Zero means observed absence. Missing means unknown. Collapsing them makes
calibration fake.

Implementation note: `SignalEnvelope` already has `confidence: float` — set to
`0.0` for unavailable, not `None`. The `severity` field carries the quality
signal: `"info"` with a reason code like `CALIBRATION_INSUFFICIENT_DATA` or a
new `SIGNAL_UNAVAILABLE` reason code.

### 1.3 Versioned Signal Semantics

Every emitted envelope carries (already defined in `SignalEnvelope`):

- `signal_id` — stable name (`SILENT_SUPPRESSION`, `EXPOSURE_PROXY`, `SIGMA_RATE`)
- `signal_version` — via `detector_version` (semver of producing logic)
- `code_hash` — git commit or build ID
- `params_hash` — H(frozen config at emission time)
- `schema_version` — envelope version (1 for v2.4)

`EXPOSURE_PROXY` will evolve. You can't compare old/new without provenance.

### 1.4 Receipt-Linkable Provenance

Every signal emission must be attributable to a context boundary. Use existing
`SignalEnvelope` fields:

- `run_id` — partition key
- `parent_event_id` — if derived from a specific prior event
- Window fields (`window.start`, `window.end`) — for aggregates

Session and correlation IDs go in `payload` (not top-level), keyed as
`session_id` and `correlation_id` respectively.

### 1.5 Anti-Gaming Declaration

Each signal spec below defines:

- What can be manipulated by a caller/operator/agent
- What denominator or source is considered authoritative
- What conditions invalidate the metric

This is critical for `EXPOSURE_PROXY` and `SIGMA_RATE`.

### 1.6 v3-Isomorphic Envelope Discipline

The `SignalEnvelope` (defined in `GAP_BUILD_ORDER.md`) is already designed for
v3 promotion. Phase A implementations must:

- Use no ad-hoc debug blobs in top-level fields
- Put signal-specific data in `payload` (not new top-level fields)
- Use `payload_hash` for content-addressed payload identity
- Follow the v2→v3 field mapping table in `GAP_BUILD_ORDER.md`

v3 promotes and freezes. No rewrite.

---

## 2. Build Order Within Phase A

Changed from `GAP_BUILD_ORDER.md` original (which had SILENT_SUPPRESSION
first). Rationale: EXPOSURE_PROXY is the denominator substrate. SIGMA_RATE
quality depends on it, and CAPTURE_SELF_DIAGNOSTIC (Phase B) depends on
denominator integrity. Ship the denominator first, even if crude.

| Step | Signal | Why This Order |
|------|--------|----------------|
| A0 | SignalEnvelope + emitter plumbing | One format, not three |
| A1 | EXPOSURE_PROXY | Denominator substrate — everything downstream needs it |
| A2 | SILENT_SUPPRESSION | Detects when instrumentation path is compromised |
| A3 | SIGMA_RATE | Needs denominator + stable source streams for pair matching |

### A0: Envelope + Emitter Plumbing

Before any signal logic:

- `SignalEnvelope` model (frozen dataclass from GAP_BUILD_ORDER.md spec)
- `WindowDescriptor`, `CheckpointRef`, `PolicyRef` models
- `EventType` and `ReasonCode` enums
- Emit path: emitter interface + JSONL sink (append, file-per-run or single)
- Quality/status validation (severity enum, reason_code required for warn/fail)
- Canonical JSON + `payload_hash` computation
- Tests: missing-vs-zero semantics, required field validation, hash stability

This prevents three signals from inventing three formats.

**Files:**

- `src/governor/signals/envelope.py` — models + validation
- `src/governor/signals/emit.py` — emitter interface + JSONL sink
- `tests/test_signals_envelope.py` — model + hash tests

---

## 3. `EXPOSURE_PROXY` — Non-Gameable Denominator

### 3.1 Purpose

Provide a **non-gameable denominator** for capture/contradiction metrics. "How
much real opportunity was there for the system to demonstrate or avoid capture?"

Without this, contradiction rates look "good" because nothing challenging
happened.

### 3.2 Subject and Window

- `subject_type = "window"` (aggregate by design)
- Window: required. `rolling` preferred for Phase A (e.g. `rolling_50_steps`
  or `rolling_1h`)
- `EXPOSURE_PROXY` is always windowed. Point-in-time is not meaningful.

### 3.3 Primary Value and Submetrics

**Primary `value_raw`:** Positive scalar exposure score for the window. Raw in
Phase A (weighted count). Normalized comes later (Phase C calibration).

**`unit`:** `"exposure_points"`

**`payload` (minimum fields):**

```python
{
    "exposure_points_total": float,      # primary weighted sum
    "eligible_events": int,              # events considered for weighting
    "excluded_events": int,              # events excluded (with reasons)
    "weighted_event_count": float,       # sum of weights
    "coverage_ratio": float,             # [0,1] if partial ingestion
    "source_event_count": int,           # raw input event count
    "components": {                      # breakdown by source
        "tool_dispatch": int,            # governed_dispatch / preflight events
        "chat_generation": int,          # daemon chat.send / chat.stream
        "evidence_checks": int,          # evidence_gate.check() invocations
        "violation_evaluations": int,    # violation resolver events
    },
    "weight_version": str,               # version of weight config (for provenance)
    "weights": {                         # the actual weights used
        "tool_dispatch": float,
        "chat_generation": float,
        "evidence_checks": float,
        "violation_evaluations": float,
    },
}
```

### 3.4 Computation Contract

Build from **authoritative event surfaces**, not self-judgment.

**Candidate surfaces (use what truly exists):**

- Tool dispatch attempts (governed_dispatch / preflight events) — from chain
  gate receipts
- Model generation calls (daemon chat.send / chat.stream) — from daemon
  telemetry or receipt counts
- Evidence gate evaluations — from receipt store
- Violation resolver events — from violation resolver store

**Avoid:**

- User-declared "difficult task"
- Model self-rating
- UI interactions that don't correspond to governed activity

**Weighted composition (Phase A):**

`exposure_points = Σ(weight_i × event_count_i)`

Weights must be:

- Explicit (in `payload.weights`)
- Versioned (`payload.weight_version`)
- Documented in this spec or a config file
- Never hidden in code with no provenance

**Phase A starting weights (subject to revision):**

| Source | Weight | Rationale |
|--------|--------|-----------|
| tool_dispatch | 1.0 | Direct governance surface |
| chat_generation | 0.5 | Governed by daemon inline gating |
| evidence_checks | 0.8 | Core enforcement path |
| violation_evaluations | 1.0 | Active governance events |

### 3.5 Anti-Gaming Constraints (Critical)

1. **Use events from the system of record** — receipts, dispatch attempts,
   daemon generation calls. Not user annotations.

2. **Count attempts, not just successes** — failed/blocked attempts still
   indicate exposure opportunity. Otherwise people bias the denominator with
   selective drops.

3. **Make exclusions explicit** — every excluded event class counted in
   `excluded_events`. Include exclusion reasons in `payload` if possible.

4. **No denominator from the numerator's output** — don't use contradiction
   detections to define exposure for contradiction rate. Denominator must be
   independently derived.

### 3.6 Failure Semantics

- `severity = "info"` + confidence near 1.0 → metric computed and trustworthy
- `severity = "info"` + confidence < 0.5 + reason_code → partial coverage
  (`coverage_ratio < 1.0`)
- `severity = "info"` + confidence = 0.0 + `SIGNAL_UNAVAILABLE` → no
  authoritative source streams available
- `value_raw = 0` is valid only if: window computed successfully, authoritative
  events present, and they sum to zero exposure (rare but valid)

### 3.7 Acceptance Criteria

1. Emits windowed `EXPOSURE_PROXY` envelope via Phase A emitter
2. Uses authoritative event surfaces only (receipts, daemon events)
3. `payload` includes enough submetrics to reconstruct the denominator
4. Counts blocked/failed attempts (exposure-bearing events)
5. Distinguishes `value_raw = 0` from unavailable
6. Weights explicit and versioned in payload
7. One replayable golden fixture (stored in `tests/fixtures/envelopes/`)

**Files:**

- `src/governor/signals/exposure_proxy.py` — derivation function
- `tests/test_signals_exposure_proxy.py` — computation + edge cases
- `tests/fixtures/envelopes/exposure_proxy_golden.json` — golden fixture

---

## 4. `SILENT_SUPPRESSION` — Plugged-In-But-Dark Detector

### 4.1 Purpose

Detect when the governor is **expected to be in path** but is effectively
absent — not running, unreachable, or not emitting expected observability.

Not just process liveness. A process can be up and still not in-path.

"Was the governor materially participating?" not "Did a process exist?"

### 4.2 Subject and Window

- `subject_type = "runtime"` for daemon/runtime state, or `"session"` if tied
  to a specific session
- Window: rolling preferred (`rolling_1m` or `rolling_5m`)
- Emit periodically and/or on session end

### 4.3 Primary Value and Submetrics

**Primary `value_raw`:** Ratio/confidence-like scalar:

- `1.0` = not suppressed (expected observability present)
- `0.0` = likely suppressed / absent
- `None` if indeterminate

**`unit`:** `"ratio"`

**`payload` (minimum fields):**

```python
{
    "expected_heartbeat_count": int,
    "observed_heartbeat_count": int,
    "expected_event_markers": int,       # expected receipt/gate events in window
    "observed_event_markers": int,
    "daemon_reachable": bool,
    "in_path_evidence_present": bool,    # at least one receipt in window
    "session_active": bool,              # was there a session in this window?
    "model_activity_detected": bool,     # token generation observed?
    "suppression_classification": str,   # "healthy" | "idle" | "suppressed" | "indeterminate"
}
```

### 4.4 Computation Contract

Compute from **multiple weak indicators**, not one:

1. Daemon reachability (health endpoint / socket probe)
2. Expected periodic heartbeat/health presence
3. Expected receipt/event marker presence when work is occurring

Then derive `suppression_classification`:

- **`healthy`**: work observed AND governor receipts/markers present → `value_raw = 1.0`
- **`idle`**: no work observed (no model activity, no session) → `value_raw = None`,
  `severity = "info"`, reason_code = `SIGNAL_UNAVAILABLE` (do NOT infer
  suppression from silence)
- **`suppressed`**: work observed (model generating) but no governor receipts/
  markers in window → `value_raw = 0.0`, `severity = "warn"`, reason_code =
  `GATE_STARVATION`
- **`indeterminate`**: daemon unreachable AND unclear whether work occurred →
  `value_raw = None`, reason_code = `SIGNAL_UNAVAILABLE`

**Key invariant:** "No events" with no activity is NOT suppression. The idle
case must not trigger false positives.

### 4.5 Anti-Gaming Constraints

This metric is gameable if it only looks at daemon self-reports.

Mitigations:

- Include at least one **external expectation source** (client-side activity
  indicator, hook invocation count, dispatch attempts from chain gate)
- Compare expected-in-path events vs observed governor events

If both expectation and observation come only from the daemon, you've built
self-attestation.

**Phase A practical approach:** Use receipt store timestamps as "observed"
signal and daemon/session activity as "expected" signal. These are already
separate subsystems.

### 4.6 Failure Semantics

- `severity = "info"` + `SIGNAL_UNAVAILABLE` when:
  - No activity in window (no denominator)
  - Both daemon and client signals absent
  - Source clocks invalid / window not computable

- `severity = "warn"` + `GATE_STARVATION` when:
  - Active session with model generation but no gate events

- Do NOT use `severity = "fail"` in Phase A. Observe only.

### 4.7 Acceptance Criteria

1. Emits `SILENT_SUPPRESSION` envelope on defined cadence/window
2. Distinguishes: idle window, healthy in-path window, active-but-dark window
3. Does not coerce idle to suppression
4. Carries enough submetrics to audit the result later
5. One replayable golden fixture

**Files:**

- `src/governor/signals/silent_suppression.py` — derivation function
- `tests/test_signals_silent_suppression.py` — including idle-vs-dark tests
- `tests/fixtures/envelopes/silent_suppression_golden.json` — golden fixture

---

## 5. `SIGMA_RATE` — Endorsement→Invalidation Rate

### 5.1 Purpose

Track **endorsement-then-invalidation** as a time series. How often does the
system affirm something and later contradict it?

Phase A is detection and counting only.

### 5.2 Subject and Window

- `subject_type = "window"` (usually)
- Window: required. Rolling preferred. Explicit start/end.
- This is inherently temporal. No window, no metric.

### 5.3 Primary Value and Submetrics

**Primary `value_raw`:** Rate within window.

- If `EXPOSURE_PROXY` is available in same window: use as denominator
  (`sigma_per_exposure_point`)
- Else: fallback to `eligible_events` with annotation
  (`sigma_per_eligible_event`)

**`unit`:** `"rate"`

**`payload` (minimum fields):**

```python
{
    "sigma_events": int,                 # endorsement→invalidation pairs found
    "eligible_events": int,              # events considered
    "denominator_value": float,          # actual denominator used
    "denominator_type": str,             # "exposure_proxy" | "eligible_events"
    "match_rule_version": str,           # version of pair-matching logic
    "mean_lag_ms": float | None,         # avg time between endorse and invalidate
    "p95_lag_ms": float | None,          # tail latency (fast recant vs slow drift)
    "contributing_pairs": [              # audit trail (truncated if large)
        {
            "endorsement_event_id": str,
            "invalidation_event_id": str,
            "lag_ms": float,
        }
    ],
}
```

### 5.4 Computation Contract

**Phase A sigma event (minimal):** A sigma event exists when:

1. An **endorsement-like event** (`E`) occurs — claim reached SUPPORTED status,
   evidence gate returned OK, receipt verdict = PASS
2. A later **invalidation-like event** (`I`) occurs — claim moved to
   INVALIDATED, contradiction detected, receipt verdict = BLOCK for same subject
3. `I` can be linked to `E` (same subject hash, correlation, or session)
4. `I.timestamp > E.timestamp` (or `I.step > E.step`)
5. Both events satisfy match rule version constraints

**Phase A matching is strict and mechanical:**

Use explicit event classes (receipt verdicts, ClaimStatus transitions, evidence
gate contradiction detections). Not NLP magic.

**Pair matching rule versions:**

- `v1`: same `subject_hash` in receipt store, endorsement verdict PASS followed
  by invalidation verdict BLOCK/FAIL
- Future versions can add probabilistic matching (but Phase A stays conservative)

### 5.5 Anti-Gaming Constraints

`SIGMA_RATE` is gameable if:

1. Denominator can be shrunk → use `EXPOSURE_PROXY` when available
2. Sigma event matching can be suppressed by changing labels → match on
   content-addressed subject hashes, not labels
3. Only one stream is visible → count from receipt-bearing events

Rules:

- Prefer `EXPOSURE_PROXY` as denominator once available
- Count from receipt-bearing events where possible
- Version the match rule explicitly
- Emit raw counts (`sigma_events`, `eligible_events`) alongside the rate —
  **never emit only the final rate**

### 5.6 Failure Semantics

- `severity = "info"` + `SIGNAL_UNAVAILABLE` when:
  - No denominator
  - No linkable event streams
  - Window not computable

- `severity = "info"` + confidence near 1.0 when:
  - No sigma events found but denominator is valid → `value_raw = 0.0`
  - This is valid, not "unavailable"

- `severity = "warn"` + `SIGMA_ABOVE_BASELINE` when:
  - Rate exceeds baseline (once baseline exists — Phase A may not have one yet)

### 5.7 Acceptance Criteria

1. Emits windowed `SIGMA_RATE` envelope via Phase A emitter
2. Includes raw counts and denominator type
3. Matching rule is versioned (`match_rule_version` in payload)
4. Uses `EXPOSURE_PROXY` when present, falls back with annotation
5. Distinguishes zero sigma from missing inputs
6. Lag stats included (mean_lag_ms, p95_lag_ms) when pairs exist
7. One replayable golden fixture

**Files:**

- `src/governor/signals/sigma_rate.py` — derivation + pair matching
- `tests/test_signals_sigma_rate.py` — matching, edge cases, denominator fallback
- `tests/fixtures/envelopes/sigma_rate_golden.json` — golden fixture

---

## 6. Phase A Acceptance Gate (Project-Level)

Phase A is "done enough" when all of the following are true:

1. **All three signals emit `SignalEnvelope`** via the shared emitter
2. **No signal performs gating/ratcheting** (observe-only invariant)
3. **Every signal distinguishes unavailable vs zero** (missing ≠ zero invariant)
4. **Every signal includes provenance/versioning** (in envelope fields)
5. **`EXPOSURE_PROXY` denominator is auditable from submetrics** (components +
   weights + version in payload)
6. **`SIGMA_RATE` emits raw counts + denominator type** (never rate-only)
7. **At least one replayable golden fixture exists per signal** (seed data for
   Phase C replay harness)
8. **Cross-cutting invariant tests pass** (clock law, emission contract,
   severity fields — see `GAP_INVARIANTS.md`)
9. **No new CLI commands yet** — signals are emitted to JSONL, surfaceable via
   `governor trace` or daemon RPC later

---

## 7. Module Layout

```
src/governor/signals/
├── __init__.py                  # Public API: SignalEnvelope, emit()
├── envelope.py                  # SignalEnvelope, WindowDescriptor, EventType, ReasonCode
├── emit.py                      # Emitter interface + JSONL sink
├── exposure_proxy.py            # EXPOSURE_PROXY derivation
├── silent_suppression.py        # SILENT_SUPPRESSION derivation
└── sigma_rate.py                # SIGMA_RATE derivation + pair matching

tests/
├── test_signals_envelope.py     # Model, hash, validation tests
├── test_signals_exposure_proxy.py
├── test_signals_silent_suppression.py
├── test_signals_sigma_rate.py
└── fixtures/envelopes/
    ├── exposure_proxy_golden.json
    ├── silent_suppression_golden.json
    └── sigma_rate_golden.json
```

Keep derivation code separate from emission transport. You'll want to replay
derivations later (Phase C) without dragging runtime IO.

---

## 8. Relation to Existing Specs

| Document | Role |
|----------|------|
| `GAP_BUILD_ORDER.md` | SignalEnvelope schema, EventType, ReasonCode, v3 mapping |
| `GAP_INVARIANTS.md` | Cross-cutting contracts (clock, determinism, emission, severity) |
| `SILENT_SUPPRESSION_GAP.md` | Design rationale (retained, not superseded) |
| `EXPOSURE_PROXY_GAP.md` | Design rationale (retained, not superseded) |
| `SIGMA_RATE_GAP.md` | Design rationale (retained, not superseded) |
| This file | Implementation contracts + acceptance criteria |

The gap specs say *why*. This file says *what to build* and *when it's done*.

---

## 9. What NOT to Build in Phase A

- Calibration (Phase C)
- Regime prediction (Phase D)
- v3 promotion logic
- CLI commands for signals
- Dashboard integration
- Policy changes based on signals
- Alert escalation
- NLP-based sigma matching
- Cross-task exposure aggregation

---

## 10. Phase A Status & Downstream

Phase A shipped (A0–A3 all implemented and tested). Downstream:

- **B1** `CAPTURE_SELF_DIAGNOSTIC` — shipped. Advisory diagnostic over A signals.
  See `V2_4B_CAPTURE_SELF_DIAGNOSTIC.md`.
- **B2** `DECISION_EVIDENCE_LAG` — shipped. Per-decision timing classification
  from gate receipts. See `V2_4B_DECISION_EVIDENCE_LAG.md`.
- **B3** `POSTERIOR_SHIFT_ATTRIBUTION` — deferred to post-C. Heuristic
  decomposition (higher risk, needs calibration substrate first).
- **C** Replay/calibration harness — next. Hardens all B thresholds.

### Phase B Layering Note

B1 and B2 have different input substrates by design:

- **B1** (CAPTURE_SELF_DIAGNOSTIC): advisory composition diagnostic over
  **Phase A signal envelopes** (layered — consumes A1/A2/A3 outputs)
- **B2** (DECISION_EVIDENCE_LAG): receipt-native temporal support diagnostic
  over **gate receipt pairs** (parallel — reads receipt store, not A signals)
- **B3** (POSTERIOR_SHIFT_ATTRIBUTION): likely receipt-native + derived mix
  (design pending)

"Phase B consumes Phase A only" is NOT a rule. Each B signal declares its
own input contract. B1 happens to layer on A; B2 is parallel by necessity
(receipt timing ≠ signal timing). Document each signal's input source
explicitly to prevent false refactors.
