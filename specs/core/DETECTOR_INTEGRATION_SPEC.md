# Detector Integration Specification

## Version 0.1 — Temporal Coherence Signals as Governor Evidence

```yaml
status: implemented
implemented: true
depends_on:
  - CONSTRAINT_COMPILER_SPEC.md
  - EPISTEMIC_STACK_SPEC.md
  - ../../../detector/  # External project: Δt Hallucination Detector
blocking: nothing (future integration)
estimated_scope: small-medium
```

### Companion to: CONSTRAINT_COMPILER_SPEC.md, KERNEL_CONSTRAINTS_SPEC.md

---

## Executive Summary

The [Δt Hallucination Detector](../../../detector/) is a separate project that measures temporal coherence during LLM generation — per-token logprobs, entropy trajectories, confidence acceleration, perturbation robustness. It answers: *"Did the model behave like it knew what it was talking about?"*

The Agent Governor answers a different question: *"Even if it behaved confidently, does it have receipts, and is it allowed to act?"*

These are complementary — runtime instrumentation vs post-hoc governance. This spec defines the integration contract: detector as **sensor**, governor as **controller**, connected via file artifacts with no shared runtime.

**Invariant**: No torch, no token loop, no generation-time code enters the governor. The boundary is a JSON file and a checksum.

---

## 1. The Two Projects

| | Δt Detector | Agent Governor |
|---|-----------|----------------|
| **Layer** | Signal-level (per-token) | Claim-level (per-assertion) |
| **When** | During generation | After generation |
| **Measures** | dC/dt, entropy, perturbation fragility | Evidence, provenance, consistency |
| **Output** | `signal.schema.json` (19 dimensions) | Receipts, ledger mutations |
| **Runtime** | torch, logprobs, GPU | Pure Python, SQLite, no ML |
| **Scope** | Single response | Multi-turn, multi-agent |

Zero mechanism overlap. The detector watches the model think. The governor checks what it claimed.

---

## 2. Integration Contract

### 2.1 The Boundary

```
┌──────────────┐     signal.json      ┌──────────────┐
│   Detector   │ ──────────────────── │   Governor   │
│  (sensor)    │   file artifact +    │ (controller) │
│              │   content hash       │              │
└──────────────┘                      └──────────────┘
```

- Detector produces a `signal.json` per response/span
- Governor consumes it as an `EvidenceRef` of type `DETECTOR_SIGNAL`
- No import of detector code. No shared process. No RPC.
- The artifact is the API.

### 2.2 Signal Collapse

The detector emits 19 raw dimensions. The governor doesn't need 19 knobs. Collapse to 5 control signals:

| Signal | Source Dimensions | Range | What It Means |
|--------|------------------|-------|---------------|
| `coherence_score` | temporal_debt, confidence_slope, acceleration | 0.0–1.0 | Stability of confidence trajectory (1.0 = stable) |
| `instability_spikes` | max_entropy_jump, entropy_recovery_detected | count | Number of entropy spikes above profile threshold |
| `perturbation_fragility` | token_jaccard, perturbation_sensitivity | 0.0–1.0 | How much output changes under temperature perturbation (1.0 = fragile) |
| `overconfidence_signature` | tokens_to_high_conf, confidence_monotonicity, entropy_variance | 0.0–1.0 | High confidence + low grounding proxy (the classic faceplant) |
| `phase_flag` | early/middle/late phase features | enum | Dominant generation phase: `searchy`, `confab`, `deliberate`, `refusal` |

The collapse function lives in the governor (not the detector) so the governor controls its own intake.

### 2.3 Shared Key

Alignment between detector spans and governor claims requires a join key:

```python
@dataclass
class SignalKey:
    """Join key between detector signal and governor claims."""
    run_id: str          # Unique generation run
    turn_id: str         # Conversation turn
    response_hash: str   # SHA-256 of full response text
    model_id: str        # Model that generated the response
    timestamp: datetime  # Generation timestamp
    byte_range: tuple[int, int] | None  # Optional: span within response
```

At minimum: `response_hash + model_id + timestamp` for reliable joining. Without alignment, "signal says risky" but the governor doesn't know *which* claims.

---

## 3. How Signals Modulate Governance

### 3.1 Signal-to-Action Mapping

Collapsed signals map to governor enforcement actions:

| Signal State | Governor Action |
|-------------|----------------|
| `coherence_score < 0.4` | Lower claim acceptance threshold; require TOOL_TRACE evidence |
| `instability_spikes > 3` | Force multi-model quorum before claim acceptance |
| `perturbation_fragility > 0.7` | Mark claims as SOFT regardless of language assertiveness |
| `overconfidence_signature > 0.6` | Require citations / tool verification; cap confidence at 0.5 |
| `phase_flag == confab` | Block ledger writes; mark response as "unsafe to act on" |

These are **policy dials**, not hard-coded rules. The mapping is configurable per risk profile (medical, legal, research, general, creative — mirroring the detector's own profiles).

### 3.2 Where It Plugs In

The constraint compiler's resolution pipeline (CONSTRAINT_COMPILER_SPEC.md, Section 2.3) gains a new input:

```
Resolution order:
1. Envelope
2. Profile
3. Intent
4. Mode
5. Scope
6. Spine
7. Invariants
8. Scars
9. Decisions
10. Anchors
11. Security
12. **Detector signals** ← NEW: modulates evidence requirements and confidence caps
```

Detector signals don't add constraints in the same way as anchors or scars. They **modulate policy thresholds** — but only in one direction (see Section 4.3).

### 3.3 Evidence Integration

Detector signals attach to claims as a new evidence type:

```python
class EvidenceType(Enum):
    # ... existing types ...
    DETECTOR_SIGNAL = "detector_signal"  # Temporal coherence signal from Δt detector
```

The `EvidenceRef` includes:

```python
EvidenceRef(
    type=EvidenceType.DETECTOR_SIGNAL,
    location=signal_key.run_id,
    span="coherence_score=0.72; fragility=0.31; phase=deliberate",
    content_hash=signal_file_hash,
)
```

This means detector signals are:
- Tracked in the epistemic ledger (provenance)
- Included in receipts (auditability)
- Subject to TTL decay (temporal validity)
- Available for claim diff analysis (did signal quality change between turns?)

---

## 4. Deployment Model

### 4.1 Sidecar Pattern

The detector runs as a sidecar — separate process, separate concerns:

```bash
# Option A: Detector wraps the LLM call
delta-t detect --prompt "..." --model ollama:llama3 --output signal.json
# Governor consumes the signal
governor constraints resolve --signal signal.json --scope "src/**"

# Option B: Detector analyzes existing output
delta-t analyze --response response.txt --output signal.json
# Governor consumes the signal
governor verify 42 --signal signal.json

# Option C: Pipeline (future)
# Claude Code → Detector (sidecar) → Governor (gate) → Executor
```

### 4.2 Optional Dependency

The governor MUST work without the detector. Detector signals are **supplementary evidence**, not required inputs. If no signal file is provided:
- All detector-modulated thresholds use their default values
- No evidence of type `DETECTOR_SIGNAL` is attached
- The constraint compiler produces the same output it would without this spec

This preserves the governor's independence — it's a constraint system, not a detector frontend.

### 4.3 Monotonic Influence

Detector signals can only **tighten** constraints, never loosen them. A clean coherence score cannot grant new authority — only a dirty one can revoke permissions or demand more proof.

| Signal Quality | Effect on Constraints |
|---------------|----------------------|
| Clean (coherence > 0.8, fragility < 0.2) | No change — default thresholds apply |
| Uncertain (middle range) | Modest tightening — raise evidence requirements |
| Dirty (coherence < 0.4, overconfidence > 0.6) | Aggressive tightening — require tool traces, force quorum |

This prevents gaming: an adversary who controls the detector output cannot use it to weaken governance. The best a clean signal can do is *not make things harder*. This also prevents Goodharting — optimizing for clean signals doesn't unlock anything.

### 4.4 Failure-Safe Default

If the detector crashes, times out, or emits malformed output:

- Governor **tightens**, not loosens
- Silence from the sensor = uncertainty = higher evidence bar
- The governor logs a `DETECTOR_UNAVAILABLE` event and applies a configurable penalty profile (default: equivalent to `overconfidence_signature = 0.5`)

This is the same principle as the constraint compiler's monotonicity: absence of information is not permission. The system degrades toward caution, never toward trust.

---

## 5. What This Is Not

- **Not a merge.** The detector stays in its own repo with its own dependencies (torch, transformers, etc.).
- **Not a runtime coupling.** No shared process, no RPC, no import. File artifacts only.
- **Not required.** The governor works without detector signals. Detector signals are supplementary.
- **Not truth verification.** The detector measures *behavioral coherence*, not *factual correctness*. The governor enforces *structural constraints*, not *semantic truth*. Neither claims to verify facts — they measure whether the conditions for trust are met.

---

## 6. Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `CONSTRAINT_COMPILER_SPEC.md` | Detector signals become Layer 12 in resolution order |
| `EPISTEMIC_STACK_SPEC.md` | `DETECTOR_SIGNAL` becomes a new `EvidenceType` |
| `KERNEL_CONSTRAINTS_SPEC.md` | Signal thresholds become policy-configurable constraints |
| `SDK_MIDDLEWARE_SPEC.md` | Middleware can optionally invoke detector sidecar |
| `INTERFEROMETRY_SPEC.md` | Per-model detector signals enable per-model coherence comparison |

---

## 7. Open Questions

1. **Signal freshness.** Detector signals are per-response, but the governor operates per-claim. If a response contains 5 claims, do they all inherit the same coherence score? Or should the detector eventually support per-span signals with byte offsets?

2. **Calibration alignment.** The detector has its own baseline calibration (model-specific z-scores). Should the governor trust the detector's calibration, or re-normalize signals against its own thresholds?

3. **Latency budget.** Running the detector adds generation-time latency (perturbation analysis = 2+ extra generations). In the constraint compiler pipeline, should detector invocation be optional/async, with signals attached retroactively?
