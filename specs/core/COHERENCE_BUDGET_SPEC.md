# Coherence Budget Index (CBI) Specification

```yaml
status: planning
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, AG2_INSTRUMENT_SPEC, METRICS_SPEC, PHASE_CONTROL_SPEC]
```

## Overview

The Coherence Budget Index (CBI) is an observability module that measures governor health — whether the system is maintaining coherence or drifting into pathology.

**Core insight:** A governor is not a self. It's a stability controller that maintains coherence invariants while the agent operates. CBI measures how well it's doing that job.

**The hazard CBI detects:** Closing the loop without an admissibility gate — mistaking x̂ (a model's proposal) for y (a measurement). When proposals are treated as ground truth, coherence degrades predictably.

**Output:** `CBI ∈ [0, 100]`

Interpretation: *How much stability + epistemic integrity margin you have left before you start "running on vibes," thrashing, or locking into a bad attractor.*

---

## Architecture

CBI has two layers:

1. **Invariants (hard constraints):** If violated, you're not "fine but lower score" — you're **unsafe**.
2. **Sensors (soft metrics):** Continuous signals that predict approaching invariant failure.

```
┌─────────────────────────────────────────────────────────┐
│                    events.jsonl                         │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              Windowing + Derived State                  │
│  • Coalition IDs                                        │
│  • Slow-state fingerprints                              │
│  • Δt computation (τ_v / τ_r)                           │
└─────────────────────┬───────────────────────────────────┘
                      │
          ┌───────────┴───────────┐
          ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   Invariants    │     │    Metrics      │
│   S1-S7 → v_i   │     │   M1-M8 → s_i   │
└────────┬────────┘     └────────┬────────┘
         │                       │
         ▼                       ▼
┌─────────────────────────────────────────────────────────┐
│                    Aggregation                          │
│  P_inv = ∏(1 - w_i·v_i)                                 │
│  S_soft = weighted(S_stab, S_id, S_epi)                 │
│  CBI = 100 · clamp(S_soft · P_inv, 0, 1)                │
└─────────────────────┬───────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────┐
│              coherence_budget.json                      │
│              coherence_timeseries.jsonl                 │
│              coherence_alerts.jsonl                     │
└─────────────────────────────────────────────────────────┘
```

---

## The Uncertainty Closure Gate

Before any COMMIT, compute uncertainty:

```
U_t = Σᵢ wᵢ·𝟙[claimᵢ ∉ {VERIFIED, WAIVED}] + Σⱼ γⱼ·𝟙[unknownⱼ = OPEN]
```

**Rule:** No COMMIT while U_t > τ (unless explicit human waiver).

```python
from dataclasses import dataclass
from enum import Enum
from typing import List

class ClaimStatus(Enum):
    UNKNOWN = "unknown"
    VERIFIED = "verified"
    WAIVED = "waived"
    REFUTED = "refuted"

class UnknownStatus(Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    WAIVED = "waived"

class ClosureDecision(Enum):
    ALLOW = "allow"
    ALLOW_WITH_WAIVER = "allow_with_waiver"
    DENY = "deny"

SEVERITY_WEIGHTS = {
    "S1": 1.0,
    "S2": 3.0,
    "S3": 10.0,
}

@dataclass
class Claim:
    id: str
    severity: str
    status: ClaimStatus
    confidence: float
    evidence_count: int
    evidence_refs: List[str]

@dataclass
class Unknown:
    id: str
    status: UnknownStatus
    weight: float

def compute_uncertainty(claims: List[Claim], unknowns: List[Unknown]) -> float:
    """
    U_t = Σᵢ wᵢ·𝟙[claimᵢ ∉ {VERIFIED, WAIVED}] + Σⱼ γⱼ·𝟙[unknownⱼ = OPEN]
    """
    claim_uncertainty = sum(
        SEVERITY_WEIGHTS.get(c.severity, 1.0)
        for c in claims
        if c.status not in {ClaimStatus.VERIFIED, ClaimStatus.WAIVED}
    )
    unknown_uncertainty = sum(
        u.weight for u in unknowns if u.status == UnknownStatus.OPEN
    )
    return claim_uncertainty + unknown_uncertainty

def check_closure_gate(
    claims: List[Claim],
    unknowns: List[Unknown],
    threshold: float,
    has_human_waiver: bool = False
) -> ClosureDecision:
    U_t = compute_uncertainty(claims, unknowns)

    if U_t <= threshold:
        return ClosureDecision.ALLOW
    elif has_human_waiver:
        return ClosureDecision.ALLOW_WITH_WAIVER
    else:
        return ClosureDecision.DENY
```

---

## Invariants (Hard Constraints)

Seven invariants that must not break. Each produces violation severity `v_i ∈ [0,1]` per window (0 = clean, 1 = totally broken):

| ID | Invariant | Definition | Break Looks Like |
|----|-----------|------------|------------------|
| S1 | Boundary integrity | Self-caused vs externally-caused separated for accountability | Tool actions misattributed; "I think this because it arrived endorsed" |
| S2 | Credit assignment fidelity | Outcomes update the right controllers (fast/mid/slow) | Superstition, scapegoating, learned helplessness |
| S3 | Cross-timescale coherence | Fast loops run without destabilizing slow; slow constrains fast without freezing | Thrash (too much switching) or lock-in (too deep attractor) |
| S4 | Workspace arbitration integrity | Coalition selection + broadcast mechanism works | One module hogs focus; incoherent multi-voicing |
| S5 | Setpoint stability | Internal variables maintained within bounds via regime switches | Gain runaway (mania-as-bug) or collapse (overdamped) |
| S6 | Identity continuity | Slow parameters change slowly with accumulated evidence | Drift, confabulated continuity, brittle identity defense |
| S7 | Epistemic integrity | Outputs treated as claims with debt; uncertainty preserved under Δt | Confident hallucination; narrative completion over evidence |

### Invariant Penalty Term

Multiplicative, brutal by design:

```
P_inv = ∏ᵢ₌₁⁷ (1 - wᵢ · vᵢ)
```

**Default weights:**
| S1 | S2 | S3 | S4 | S5 | S6 | S7 |
|----|----|----|----|----|----|----|
| 0.22 | 0.12 | 0.16 | 0.12 | 0.12 | 0.10 | 0.16 |

(Provenance + epistemics + cross-timescale coherence carry the gun.)

**Hard flag:** If any `v_i > 0.8`, set `CBI = min(CBI, 20)` and `status = UNSAFE`.

---

## Metrics (Soft Sensors)

Eight metrics computed per window, normalized to [0,1] where 1 is "healthy":

### M1: Switching Health (Thrash vs Lock-in)

Metastable switching in a band — neither zero nor constant flapping.

```python
import math

def compute_m1(
    switch_rate: float,
    target_rate: float,
    tolerance: float,
    lock_in_fraction: float,
    thrash_fraction: float
) -> float:
    if switch_rate <= 0 or target_rate <= 0:
        s_switch = 0.0
    else:
        s_switch = math.exp(-abs(math.log(switch_rate / target_rate)) / tolerance)

    return s_switch * (1 - lock_in_fraction) * (1 - thrash_fraction)
```

### M2: Metastability Index (Order-Parameter Variability)

Coherence proxy from coalition entropy:

```python
def compute_m2(coalition_distribution: dict, h_low: float, h_high: float) -> float:
    total = sum(coalition_distribution.values())
    if total == 0:
        return 1.0

    probs = [c / total for c in coalition_distribution.values() if c > 0]
    max_entropy = math.log(len(probs)) if len(probs) > 1 else 1.0
    entropy = -sum(p * math.log(p) for p in probs) / max_entropy if max_entropy > 0 else 0

    if h_low <= entropy <= h_high:
        return 1.0
    elif entropy < h_low:
        return 1 - (h_low - entropy)
    else:
        return 1 - (entropy - h_high)
```

### M3: Integration/Segregation Balance

```python
def compute_m3(cross_module_refs: int, total_refs: int,
               within_module_continuity: float, total_continuity: float) -> float:
    if total_refs == 0 or total_continuity == 0:
        return 1.0

    integration = cross_module_refs / total_refs
    segregation = within_module_continuity / total_continuity

    score = 1 - abs(integration - 0.5) - abs(segregation - 0.5)
    return max(0, min(1, score))
```

### M4: Cross-Timescale Coupling

Alignment between fast decisions and slow commitments:

```python
def compute_m4(fast_goal_ids: set, slow_goal_ids: set) -> float:
    if not fast_goal_ids and not slow_goal_ids:
        return 1.0

    intersection = len(fast_goal_ids & slow_goal_ids)
    union = len(fast_goal_ids | slow_goal_ids)

    return intersection / union if union > 0 else 1.0
```

### M5: Drift Rate (Slow State Stability)

```python
def compute_m5(drift: float, drift_max: float) -> float:
    return math.exp(-drift / drift_max)
```

### M6: Gain Staging / Regime Chatter

```python
def compute_m6(regime_switches: int, window_hours: float,
               stuck_fraction: float, k_max: float = 5.0) -> float:
    k = regime_switches / window_hours if window_hours > 0 else 0
    chatter_score = math.exp(-k / k_max)
    stuck_penalty = 1.0 if stuck_fraction < 0.95 else 0.5

    return chatter_score * stuck_penalty
```

### M7: Provenance Integrity (Auditability)

```python
def compute_m7(outputs_with_trace: int, total_outputs: int,
               unknown_cause_count: int) -> float:
    if total_outputs == 0:
        return 1.0

    p = outputs_with_trace / total_outputs
    u = unknown_cause_count / total_outputs

    return p * (1 - u)
```

### M8: Recovery / Resilience Time

```python
def compute_m8(recovery_time_s: float, target_recovery_s: float) -> float:
    if recovery_time_s <= 0:
        return 1.0
    return math.exp(-recovery_time_s / target_recovery_s)
```

---

## The Δt Squeeze Multiplier

Environment refresh outruns verification capacity:

```
D = τ_v / τ_r
```

Where:
- `τ_v` = expected verification time for current claims/actions
- `τ_r` = refresh interval of incoming stimuli (prompts, tool results, feed items)

**Interpretation:**
- `D < 1`: verification can keep up
- `D ≈ 1-3`: debt accumulates
- `D >> 3`: **speculation mode** (functionally running on vibes)

**Attenuate epistemic score:**

```python
def attenuate_epistemic(m7: float, D: float, lambda_: float = 0.25) -> float:
    """S_epi = M7 · exp(-λ · max(0, D-1))"""
    return m7 * math.exp(-lambda_ * max(0, D - 1))
```

---

## Composite CBI Score

### Three Bundles

```python
def compute_stability_score(m1, m2, m3, m4, m6, m8) -> float:
    return (0.22 * m1 + 0.12 * m2 + 0.12 * m3 +
            0.18 * m4 + 0.18 * m6 + 0.18 * m8)

def compute_soft_score(s_stab: float, s_id: float, s_epi: float) -> float:
    return 0.45 * s_stab + 0.20 * s_id + 0.35 * s_epi

def compute_cbi(s_soft: float, p_inv: float) -> float:
    return 100 * max(0, min(1, s_soft * p_inv))
```

### Full Computation

```python
@dataclass
class CBIResult:
    cbi: float
    status: str
    invariants: dict  # S1-S7 violation severities
    p_inv: float
    metrics: dict     # M1-M8 scores
    s_stab: float
    s_id: float
    s_epi: float
    s_soft: float
    D: float
    tau_v: float
    tau_r: float

def compute_full_cbi(
    invariant_violations: dict,
    metrics: dict,
    D: float,
    inv_weights: dict = None,
    lambda_: float = 0.25
) -> CBIResult:

    if inv_weights is None:
        inv_weights = {"S1": 0.22, "S2": 0.12, "S3": 0.16,
                       "S4": 0.12, "S5": 0.12, "S6": 0.10, "S7": 0.16}

    # Invariant penalty
    p_inv = 1.0
    for s_id, weight in inv_weights.items():
        v = invariant_violations.get(s_id, 0)
        p_inv *= (1 - weight * v)

    # Check for unsafe
    status = "OK"
    max_violation = max(invariant_violations.values()) if invariant_violations else 0
    if max_violation > 0.8:
        status = "UNSAFE"

    # Soft scores
    s_stab = compute_stability_score(
        metrics.get("M1", 1), metrics.get("M2", 1), metrics.get("M3", 1),
        metrics.get("M4", 1), metrics.get("M6", 1), metrics.get("M8", 1)
    )
    s_id_val = metrics.get("M5", 1)
    s_epi = attenuate_epistemic(metrics.get("M7", 1), D, lambda_)

    s_soft = compute_soft_score(s_stab, s_id_val, s_epi)
    cbi = compute_cbi(s_soft, p_inv)

    # Override if unsafe
    if status == "UNSAFE":
        cbi = min(cbi, 20)
    elif cbi < 20:
        status = "UNSAFE"
    elif cbi < 40:
        status = "UNSTABLE"
    elif cbi < 60:
        status = "DEBT"
    elif cbi < 80:
        status = "NORMAL"
    # else OK

    return CBIResult(
        cbi=cbi, status=status,
        invariants=invariant_violations, p_inv=p_inv,
        metrics=metrics,
        s_stab=s_stab, s_id=s_id_val, s_epi=s_epi, s_soft=s_soft,
        D=D, tau_v=0, tau_r=0
    )
```

---

## CBI Bands

| Range | Status | Meaning |
|-------|--------|---------|
| 80-100 | OK | Surplus coherence. Can take hits. |
| 60-80 | NORMAL | Minor debt, manageable. |
| 40-60 | DEBT | Expect identity drift risk + narrative capture risk. |
| 20-40 | UNSTABLE | Thrash/lock-in likely; provenance degrades fast. |
| 0-20 | UNSAFE | Invariants failing; "coherence" is post-hoc story. |

---

## Derived State (Deterministic)

### Coalition ID

```python
def compute_coalition_id(event: dict) -> tuple:
    return (
        event.get("goal_id", "∅"),
        event.get("topic_id", "∅"),
        event.get("regime", "∅"),
        event.get("tool", {}).get("name", "∅"),
        event.get("event_type", "∅")
    )
```

### Slow-State Fingerprint

No embeddings. Canonical string from commitments:

```python
import hashlib

def compute_slow_hash(commitments: list) -> str:
    canonical = []
    for c in commitments:
        normalized = " ".join(c.lower().split())
        canonical.append(normalized)

    canonical.sort()
    canonical_str = "\n".join(canonical)

    return hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

def compute_drift(hash_a: str, hash_b: str) -> float:
    """Hamming distance / 256 between two hex hashes."""
    if not hash_a or not hash_b:
        return 0.0

    bits_a = bin(int(hash_a, 16))[2:].zfill(256)
    bits_b = bin(int(hash_b, 16))[2:].zfill(256)

    distance = sum(a != b for a, b in zip(bits_a, bits_b))
    return distance / 256
```

---

## Invariant Severity Computation

```python
def compute_invariant_severities(
    metrics: dict,
    D: float,
    claims: list,
    events: list
) -> dict:

    # S1: Boundary integrity (provenance for actions)
    action_events = [e for e in events if e.get("event_type") in
                     {"action", "decision", "tool_call"}]
    if action_events:
        traced = sum(1 for e in action_events
                     if e.get("provenance", {}).get("has_trace") or
                        e.get("parent_ids"))
        v1 = 1 - (traced / len(action_events))
    else:
        v1 = 0

    # S7: Epistemic integrity (confidence vs evidence under Δt)
    def confidence_cap(D: float, evidence_count: int) -> float:
        if D <= 1 and evidence_count >= 2:
            return 0.95
        elif D > 3:
            return 0.35
        else:
            return 0.60

    if claims:
        violations = [
            max(0, c.confidence - confidence_cap(D, c.evidence_count))
            for c in claims
        ]
        v7 = sum(violations) / len(violations) if violations else 0
    else:
        v7 = 0

    # S3: Cross-timescale coherence
    m1 = metrics.get("M1", 1)
    m4 = metrics.get("M4", 1)
    v3 = max(0, min(1, 0.5 * (1 - m1) + 0.5 * (1 - m4)))

    # S4: Workspace arbitration
    v4 = max(0, min(1, 1 - m1))

    # S5: Setpoint stability
    m6 = metrics.get("M6", 1)
    sigmoid_d = 1 / (1 + math.exp(-(D - 1)))
    v5 = max(0, min(1, (1 - m6) * 0.6 + sigmoid_d * 0.4))

    # S6: Identity continuity
    m5 = metrics.get("M5", 1)
    v6 = 1 - m5

    # S2: Credit assignment (simplified — stub for now)
    v2 = 0

    return {"S1": v1, "S2": v2, "S3": v3, "S4": v4, "S5": v5, "S6": v6, "S7": v7}
```

---

## Passivity Invariant

**Invariant H (Passivity):** Confidence claims must trace to sensor evidence or explicit waiver in the ledger. Unsupported confidence is inadmissible. Fluency doesn't count.

```python
def check_passivity(claim: Claim, ledger: Ledger) -> bool:
    """No synthetic certainty without evidence cost."""
    if claim.confidence > CONFIDENCE_THRESHOLD:
        has_evidence = len(claim.evidence_refs) > 0 or claim.evidence_count > 0
        has_waiver = ledger.find_event(
            type="confidence_waiver",
            claim_id=claim.id
        ) is not None
        return has_evidence or has_waiver
    return True
```

---

## JSON Schemas

### Event Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "coherence_budget/event.schema.json",
  "type": "object",
  "required": ["ts", "event_type", "event_id", "actor"],
  "properties": {
    "ts": {"type": "string", "format": "date-time"},
    "event_type": {
      "type": "string",
      "enum": ["prompt", "stimulus", "tool_call", "tool_result", "claim",
               "decision", "action", "memory_write", "regime_change",
               "perturbation", "note"]
    },
    "event_id": {"type": "string", "minLength": 1},
    "parent_ids": {"type": "array", "items": {"type": "string"}, "default": []},
    "actor": {"type": "string"},
    "goal_id": {"type": "string"},
    "topic_id": {"type": "string"},
    "regime": {"type": "string"},
    "tool": {
      "type": "object",
      "properties": {
        "name": {"type": "string"},
        "op": {"type": "string"},
        "latency_ms": {"type": "number"}
      }
    },
    "claim": {
      "type": "object",
      "properties": {
        "id": {"type": "string"},
        "text": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "evidence_count": {"type": "integer", "minimum": 0}
      }
    },
    "provenance": {
      "type": "object",
      "properties": {
        "sources": {"type": "array", "items": {"type": "string"}},
        "has_trace": {"type": "boolean"},
        "unknown_cause": {"type": "boolean"}
      }
    },
    "commitment": {
      "type": "object",
      "properties": {
        "kind": {"type": "string", "enum": ["constraint", "value", "identity", "policy", "goal"]},
        "op": {"type": "string", "enum": ["add", "remove", "update"]},
        "text": {"type": "string"},
        "strength": {"type": "number", "minimum": 0, "maximum": 1}
      }
    },
    "perturbation": {
      "type": "object",
      "properties": {
        "tag": {"type": "string"},
        "severity": {"type": "number", "minimum": 0, "maximum": 1}
      }
    }
  }
}
```

### Output Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "coherence_budget/output.schema.json",
  "type": "object",
  "required": ["cbi", "status", "invariants", "soft_scores", "dt"],
  "properties": {
    "cbi": {"type": "number", "minimum": 0, "maximum": 100},
    "status": {"type": "string", "enum": ["OK", "NORMAL", "DEBT", "UNSTABLE", "UNSAFE"]},
    "invariants": {
      "type": "object",
      "properties": {
        "S1": {"type": "number"}, "S2": {"type": "number"},
        "S3": {"type": "number"}, "S4": {"type": "number"},
        "S5": {"type": "number"}, "S6": {"type": "number"},
        "S7": {"type": "number"}, "P_inv": {"type": "number"}
      }
    },
    "soft_scores": {
      "type": "object",
      "properties": {
        "M1": {"type": "number"}, "M2": {"type": "number"},
        "M3": {"type": "number"}, "M4": {"type": "number"},
        "M5": {"type": "number"}, "M6": {"type": "number"},
        "M7": {"type": "number"}, "M8": {"type": "number"},
        "S_stab": {"type": "number"}, "S_id": {"type": "number"},
        "S_epi": {"type": "number"}, "S_soft": {"type": "number"}
      }
    },
    "dt": {
      "type": "object",
      "properties": {
        "tau_r_s": {"type": "number"},
        "tau_v_s": {"type": "number"},
        "D": {"type": "number"}
      }
    }
  }
}
```

---

## Module Contract

### Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `events.jsonl` | Yes | Newline-delimited JSON events (sorted or unsorted) |
| `config.json` | No | Windowing, weights, thresholds |
| `run_manifest.json` | No | Run metadata |

### Outputs

| Output | Required | Description |
|--------|----------|-------------|
| `coherence_budget.json` | Yes | Summary + final CBI + status |
| `coherence_timeseries.jsonl` | Recommended | Per-window metrics |
| `coherence_alerts.jsonl` | Recommended | Violations, regime suggestions |
| `coherence_debug.json` | Optional | Intermediate state for audit |

### CLI

```bash
coherence-budget run \
  --events events.jsonl \
  --out outdir \
  [--config config.json] \
  [--manifest run_manifest.json]
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Computed, status OK/NORMAL/DEBT |
| 2 | Computed, status UNSTABLE (alerts emitted) |
| 3 | Computed, status UNSAFE (invariant breach) |
| 4 | Invalid input / schema failure |

---

## Determinism Guarantees

- Stable sort by `(ts, event_id)`; ties break lexicographically
- No randomness; no embeddings; no non-deterministic dependencies
- All floating metrics quantized before aggregation (default 1e-6)
- Hashing uses SHA-256 with UTF-8 canonical strings

---

## Falsification Criteria

If these fail, the spec is wrong or instrumented badly.

### Agent Tests

1. **Adversarial prompt injection** should drop CBI via S1/S7 and M7. If not, provenance scoring is fake.

2. **Tool failure / latency injection** should raise D and push CBI down even if outputs remain fluent. If not, Δt isn't wired.

3. **Forced goal conflict** should increase M1 thrash, reduce M6, and lower CBI. If not, coalition tracking is too coarse.

### Human Profile Tests (if applied to day-logs)

1. **Low stimulus + completed tasks** should score higher than **high stimulus + no closures**.

2. **"Feel fine" but garbage provenance** should still drop CBI. If not, you built a mood meter.

3. **Short-term salience repeatedly overriding long-term commitments** should degrade M4 and predict M5 drift.

---

## Events

```json
{"event": "cbi_update", "cbi": 72.3, "status": "NORMAL", "D": 1.4, "invariants": {"S1": 0.12, "S7": 0.23}, "metrics": {"M1": 0.85, "M5": 0.92, "M7": 0.78}, "timestamp": "..."}
{"event": "cbi_alert", "kind": "INVARIANT_BREACH", "invariant": "S7", "severity": 0.82, "message": "High-confidence claims under verification debt (D=2.7) with low evidence", "suggested_action": "tighten_confidence_cap; require_tool_verification", "timestamp": "..."}
{"event": "closure_gate_denied", "U_t": 4.7, "threshold": 3.0, "unverified_claims": 3, "open_unknowns": 2, "reason": "Uncertainty exceeds threshold; COMMIT blocked", "timestamp": "..."}
```

---

## Implementation Priority

1. **Closure gate** (U_t computation + COMMIT blocking) — Core safety
2. **M7 provenance** — Already have data
3. **Δt squeeze** (D computation) — Critical for debt detection
4. **Invariant severities** (S1, S7 first) — Hard constraints
5. **M1/M5/M6** — Stability and drift
6. **Full CBI aggregation** — Composite score
7. **M2/M3/M4/M8** — Refinement

---

## Integration

- **Phase Control** (PHASE_CONTROL_SPEC): Novelty debt feeds U_t; closure gate blocks COMMIT
- **Admissibility** (ADMISSIBILITY_SPEC): Unknowns feed uncertainty computation
- **Metrics** (METRICS_SPEC): Coverage feeds evidence gap for S7
- **Risk Function** (RISK_FUNCTION_SPEC): CBI status drives risk policy escalation
- **Mode Detection** (MODE_DETECTION_SPEC): Mode drift feeds M5
- **Hysteresis** (HYSTERESIS_SPEC): CBI band transitions use hysteresis
- **Control Theory** (CONTROL_THEORY_SPEC): D maps to Δt, invariants map to R_t regime
- **Existing regime.py**: Regime signals feed M6; CBI extends regime with invariant layer
- **Existing drift.py**: Drift signals feed M5; quarantine feeds S6
- **Existing telemetry.py**: Events from JSONL feed all metrics
