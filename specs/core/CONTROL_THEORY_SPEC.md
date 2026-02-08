# Control Theory Formalization Specification

## Version 0.1 — The Governor as a Reynolds Number

```yaml
status: implemented
implemented: true
depends_on:
  - regime.py              # RegimeDetector → becomes R̄_t classifier
  - epistemic.py           # EpistemicLedger → E_t computation
  - audit.py               # AuditPipeline → E_t validation
  - scars.py               # ScarLedger → P_t/τ modification
  - strict.py              # StrictModeGate → E_min per tool
  - boil.py                # BoilController → τ adjustment
  - homeostat.py           # Homeostat → τ relaxation
  - security.py            # SecurityVerifier → P_t classification
  - CONSTRAINT_COMPILER_SPEC.md
  - AG2_INSTRUMENT_SPEC.md
blocking: mathematical foundation for all 2.0 specs
estimated_scope: large (foundational)
source: Gemini/ChatGPT derivation, Beck Δt framework
```

### Companion to: All specs. This is the mathematical foundation.

---

## Executive Summary

The Governor can be expressed as a single dimensionless ratio — analogous to the Reynolds number in fluid dynamics, which determines whether flow is laminar or turbulent.

**The Agent Risk Index:**

```
        P_t · D_t
R_t = ───────────
          E_t
```

Where:
- **P_t** = Power (how much damage can this action do?)
- **D_t** = Delay (how long until we know if it worked?)
- **E_t** = Evidence (how much do we actually know?)

**High R = turbulent (dangerous). Low R = laminar (safe).**

The binding policy follows directly:

```
P_t ≤ (τ · E_t) / D_t
```

**"Your allowed power is proportional to your evidence and inversely proportional to your feedback delay."**

That's the entire Governor in one inequality.

---

## 0. Variables

Let an agent operate over discrete steps t = 1..T, making tool calls and emitting claims.

### 0.1 Tool Power (P_t)

For action a_t using tool k:

```
P_t ≡ P(a_t) = π_k · b_k · ι_k
```

Where:
- **π_k**: privilege level / authority scope (normalized 0-1)
- **b_k**: blast radius estimate (normalized 0-1)
- **ι_k**: irreversibility / undo cost (normalized 0-1)

**Implementation:** Lookup table per tool class with multipliers.

| Tool Class | π (privilege) | b (blast) | ι (irreversibility) | P |
|------------|---------------|-----------|---------------------|---|
| read_file | 0.1 | 0.1 | 0.0 | 0.001 |
| write_file | 0.5 | 0.3 | 0.5 | 0.075 |
| execute_shell | 0.8 | 0.7 | 0.8 | 0.448 |
| delete_recursive | 0.9 | 0.9 | 1.0 | 0.810 |
| deploy_production | 1.0 | 1.0 | 0.9 | 0.900 |

### 0.2 Feedback Delay (D_t)

Define effective delay as the time from action to trustworthy verification:

```
D_t ≡ Δt(a_t) = max(D_tool, D_telemetry, D_human)
```

Where:
- **D_tool**: Time for tool to report completion
- **D_telemetry**: Time for monitoring to confirm effect
- **D_human**: Time for human review if required

**"Trustworthy feedback"** = verification signal that is fresh + complete enough to bind decisions.

| Action Type | Typical D_t |
|-------------|-------------|
| Lint check | seconds |
| Unit tests | minutes |
| Integration tests | tens of minutes |
| Canary deploy | hours |
| Human review | hours to days |
| Production metrics | hours to weeks |

### 0.3 Evidence Integrity (E_t)

Define evidence as a bounded score E_t ∈ (0, 1]:

```
E_t = w_r·R_t + w_p·PV_t + w_v·V_t + w_i·I_t
```

Where:
- **R_t**: Receipts coverage (tool outputs, IDs, hashes)
- **PV_t**: Provenance depth / custody links
- **V_t**: Replayability / determinism score
- **I_t**: Independent verification (cross-model agreement, external checks)

Weights w_* sum to 1. Clamp E_t ≥ ε for numeric stability.

| Evidence Component | What It Measures | Example |
|--------------------|------------------|---------|
| Receipts (R) | Did we capture proof? | SHA-256 of test output, exit code, timestamp |
| Provenance (PV) | Can we trace the chain? | Claim → source → verification |
| Verifiability (V) | Can we replay it? | Deterministic build, seeded tests |
| Independence (I) | Did multiple sources agree? | Interferometry consensus |

---

## 1. The Core Scalar: Agent Risk Index

### 1.1 Per-Step Risk

```
        P_t · D_t
R_t = ───────────
          E_t
```

**Interpretation:**
- High power × long delay ÷ weak evidence = HIGH RISK
- Low power × short delay ÷ strong evidence = LOW RISK

This is dimensionally consistent: all terms are normalized, R_t is dimensionless.

### 1.2 Windowed/Rolling Risk

**Exponential Moving Average:**
```
R̄_t = α·R_t + (1-α)·R̄_{t-1}
```

**Simple Moving Average:**
```
R̄_t = (1/W) · Σ R_i  for i ∈ [t-W+1, t]
```

**Worst-Case (Conservative):**
```
R^max_t = max(R_i)  for i ∈ [t-W+1, t]
```

Use worst-case for safety gates; use EMA for regime detection.

---

## 2. Regime Thresholds (Phase Classification)

Define thresholds 0 < τ₁ < τ₂ < τ₃:

```
Regime(R̄_t) =
  SAFE       if R̄_t < τ₁
  ELASTIC    if τ₁ ≤ R̄_t < τ₂
  DANGEROUS  if τ₂ ≤ R̄_t < τ₃
  RUNAWAY    if R̄_t ≥ τ₃
```

| Regime | R̄_t Range | Behavior |
|--------|-----------|----------|
| **SAFE** | < 0.1 | Full autonomy, minimal oversight |
| **ELASTIC** | 0.1 - 0.4 | Normal operation, standard checks |
| **DANGEROUS** | 0.4 - 0.8 | Heightened scrutiny, human review for high-P actions |
| **RUNAWAY** | ≥ 0.8 | Halt, require explicit human intervention |

Thresholds are tunable per deployment context.

### 2.1 Glass Cannon Detection

"Glass Cannon" is not a separate regime — it's a region characterized by:

```
P high, D low, E high — but with high sensitivity ∂R/∂D, ∂R/∂E
```

**Sensitivity (local):**

```
∂R/∂D = P/E
∂R/∂E = -PD/E² = -R/E
```

When P is large, small changes in D or E produce large changes in R.

**Step-function example:**

If E → E/10 and D → 10D:

```
R' = (P · 10D) / (E/10) = 100 · (PD/E) = 100R
```

A 10x evidence degradation + 10x delay spike = **100x risk increase**.

This is why "looks safe" can become "catastrophic" instantly.

---

## 3. The Binding Policy: Dynamic Capability Shaping

### 3.1 The Inequality

To enforce a bound R̄_t ≤ τ, the allowed power is:

```
P_t ≤ P^max_t = (τ · E_t) / D_t
```

**"Your allowed power is proportional to your evidence and inversely proportional to your feedback delay."**

### 3.2 Implementation

Implement as discrete privilege tiers P^(0) < P^(1) < ... < P^(m).

Pick the highest tier satisfying:

```
P^(j) ≤ (τ · E_t) / D_t
```

| Tier | P^(j) | Tools Allowed |
|------|-------|---------------|
| 0 | 0.01 | read_file, list_dir |
| 1 | 0.10 | write_file, run_tests |
| 2 | 0.30 | execute_shell (sandboxed) |
| 3 | 0.50 | execute_shell (full) |
| 4 | 0.80 | delete, deploy_staging |
| 5 | 1.00 | deploy_production, admin |

If current (E_t, D_t) only permits tier 2, the agent cannot access tier 3+ tools regardless of request.

---

## 4. Evidence Minimums (Fail-Closed Gates)

### 4.1 Per-Tool Evidence Requirements

Tool class k has a minimum evidence requirement E_min(k):

```
E_t < E_min(k) → DENY tool k
```

| Tool Class | E_min | Rationale |
|------------|-------|-----------|
| read_file | 0.1 | Low risk, low requirement |
| write_file | 0.3 | Medium risk |
| execute_shell | 0.5 | High risk |
| deploy | 0.7 | Very high risk |
| delete_recursive | 0.8 | Irreversible |

### 4.2 Per-Tool Risk Caps

Tool class k has a maximum allowable risk τ(k):

```
(P_k · D_t) / E_t > τ(k) → DENY tool k
```

This allows different risk tolerances per tool class.

---

## 5. Open-Loop Detection

### 5.1 Actuation vs Verification Throughput

Define:
- **A_t**: high-impact actions per unit time (actuation rate)
- **V_t**: verified actions per unit time (verification rate)

```
Γ_t = A_t / V_t
```

**Open-loop boundary:**

```
Γ_t > 1 → verification lag is growing
```

The system is taking actions faster than it can verify them.

### 5.2 Backlog Integration

Fold verification backlog into delay:

```
D_t := D_t + λ · backlog_t
```

Where backlog_t is the count of unverified actions.

This automatically increases D_t when verification falls behind, which:
1. Increases R_t
2. Reduces P^max_t
3. Forces the system to slow down or use lower-power tools

**Self-regulating feedback loop.**

---

## 6. Multi-Step Composition (Task-Level Risk)

For an episode e (a plan segment), define cumulative risk cost.

### 6.1 Additive

```
J_e = Σ R_t  for t ∈ e
```

Total risk accumulated over the episode.

### 6.2 Discounted

```
J_e = Σ γ^(t-t₀) · R_t  for t ∈ e
```

Future risk is discounted (γ < 1). Useful for planning.

### 6.3 Worst-Step (Safety Conservative)

```
J_e = max(R_t)  for t ∈ e
```

The episode's risk is dominated by its riskiest step.

**Recommendation:** Use worst-step for safety gates, additive for budgeting.

---

## 7. Receipts as Currency

### 7.1 The Formulation

Let each proposed action a_t have required "evidence spend":

```
Cost_t = η · P_t · D_t
```

Let available evidence credit be:

```
Credit_t = κ · E_t
```

**Permission rule:**

```
Credit_t ≥ Cost_t → ALLOW action
Credit_t < Cost_t → DENY / DEMOTE
```

### 7.2 Equivalence

This is equivalent to bounding R_t:

```
κ·E_t ≥ η·P_t·D_t
→ E_t ≥ (η/κ)·P_t·D_t
→ P_t·D_t/E_t ≤ κ/η
→ R_t ≤ τ  where τ = κ/η
```

Same inequality, different framing.

### 7.3 Intuition

**"You pay for powerful actions with evidence."**

- Want to run a high-power tool? Need high-quality receipts.
- Have weak evidence? Can only afford low-power tools.
- No receipts? No capability.

---

## 8. The Governor Loop (Per-Step Algorithm)

Given observed (D_t, E_t) and a requested tool with power P_req:

```python
def governor_check(P_req: float, D_t: float, E_t: float, tool_class: str) -> Decision:

    # 1. Evidence minimum gate
    if E_t < E_MIN[tool_class]:
        return Deny(reason="insufficient_evidence")

    # 2. Compute risk
    R_t = (P_req * D_t) / E_t

    # 3. Per-tool risk cap
    if R_t > TAU[tool_class]:
        # Try to demote to lower tier
        P_max = (TAU[tool_class] * E_t) / D_t
        P_demoted = highest_tier_below(P_max)

        if P_demoted is None:
            return Deny(reason="risk_too_high")
        else:
            return Demote(to_tier=P_demoted, reason="risk_capped")

    # 4. Global regime check
    R_bar = update_ema(R_t)
    regime = classify_regime(R_bar)

    if regime == RUNAWAY:
        return Halt(reason="runaway_regime")

    # 5. Allow
    return Allow(risk=R_t, regime=regime)
```

---

## 9. Mapping to Existing Governor Concepts

| Mathematical Concept | Governor Implementation |
|---------------------|------------------------|
| P_t (Power) | Tool privilege levels, blast radius estimates |
| D_t (Delay) | Δt framework, verification latency |
| E_t (Evidence) | Receipts, provenance, custody scoring |
| R_t (Risk Index) | Regime detection input |
| τ (Threshold) | Profile-specific risk tolerance |
| P^max (Capability Shaping) | Dynamic tool allowlists |
| E_min (Evidence Gate) | Fail-closed verification requirements |
| Γ (Open-Loop Detector) | Actuation/verification rate monitoring |
| J_e (Episode Risk) | Task-level risk budgeting |
| Credit/Cost | "No receipt, no write" policy |

---

## 10. Why This Matters

### 10.1 The Reynolds Analogy

In fluid dynamics, the Reynolds number determines flow regime:

```
Re = (inertial forces) / (viscous forces)

Low Re → laminar (predictable, stable)
High Re → turbulent (chaotic, unpredictable)
```

The Agent Risk Index is the same:

```
R = (action momentum) / (verification friction)

Low R → controlled (safe, auditable)
High R → chaotic (dangerous, opaque)
```

### 10.2 The Single Inequality

Everything the Governor does can be derived from:

```
P_t ≤ (τ · E_t) / D_t
```

- Receipts increase E_t → more capability allowed
- Faster verification decreases D_t → more capability allowed
- Lower risk tolerance τ → less capability allowed
- Higher power tools → need better evidence or faster feedback

### 10.3 Why Evidence is the Denominator

Evidence is the **stabilizing force**. As E_t increases:
- R_t decreases (safer)
- P^max increases (more capability)

This creates the right incentives:
- Want more power? Provide more evidence.
- Have weak evidence? Accept less power.

### 10.4 Why Delay is in the Numerator

Delay is the **destabilizing force**. As D_t increases:
- R_t increases (riskier)
- P^max decreases (less capability)

This captures the Δt framework insight:
- Slow feedback → more uncertainty → more risk
- Fast feedback → quick correction → less risk

---

## 11. Glass Cannon Implications

The sensitivity analysis reveals:

```
∂R/∂E = -R/E
```

If you're at R = 0.1 with E = 0.8, a drop to E = 0.2 gives:

```
R' = R · (E/E') = 0.1 · (0.8/0.2) = 0.4
```

**4x risk increase from evidence degradation alone.**

This is why:
1. Evidence quality must be continuously monitored
2. Receipts have TTLs (evidence decays)
3. "Tests passed yesterday" ≠ "tests pass now"

---

## 12. Temporal Attack Surface Connection

The Δt framework papers identify failures as:

```
T_commit < T_verify → race window exists
```

In this formalization:

```
D_t = T_verify - T_action

If D_t > W (window before damage):
  Damage occurs before verification completes
  → High R_t
  → System should have blocked the action
```

The Governor enforces:

```
P_t ≤ (τ · E_t) / D_t
```

Which means: **high-delay actions require proportionally more evidence or less power.**

---

## 13. Implementation Recommendations

### 13.1 Start Simple

Initial implementation:

```python
# Tool power lookup (static)
POWER = {
    'read': 0.01,
    'write': 0.1,
    'execute': 0.5,
    'delete': 0.8,
    'deploy': 1.0,
}

# Evidence from receipts (count-based approximation)
E_t = min(1.0, 0.2 + 0.1 * receipt_count + 0.3 * has_test_receipt)

# Delay from tool class (static estimate)
DELAY = {
    'read': 0.1,
    'write': 0.2,
    'execute': 0.5,
    'delete': 0.5,
    'deploy': 10.0,  # hours normalized
}

# Risk calculation
R_t = (POWER[tool] * DELAY[tool]) / E_t

# Threshold check
if R_t > 0.5:
    deny()
```

### 13.2 Add Sophistication Later

- Dynamic D_t from actual verification latency measurements
- E_t components weighted by claim type
- Per-tool τ thresholds
- Rolling R̄_t for regime detection
- Backlog integration for open-loop detection

---

## 14. Relationship to 2.0 Specs

| Spec | How R_t Connects |
|------|-----------------|
| CONSTRAINT_COMPILER_SPEC | Compiles current (E_t, D_t, τ) into capability envelope for executor |
| DETECTOR_INTEGRATION_SPEC | Detector signals modulate E_t (coherence → evidence quality) |
| COMMITMENT_TRANSPORT_SPEC | Compression shear reduces E_t (lost commitments = weaker evidence) |
| SPECTRAL_STABILITY_SPEC | ρ(M) instability manifests as coupled R_t oscillation across layers |
| SCALAR_COLLAPSE_SPEC | Collapse = R_t converging to single-metric optimization |
| SLIM_MODE_SPEC | Slim mode uses simplified R_t (static P, E_min gates only) |
| DOC_GOVERNANCE_SPEC | Doc staleness = D_t growth for doc-backed claims |
| AG2_INSTRUMENT_SPEC | Instruments emit (P_t, D_t, E_t) per step for R_t computation |
| AG2_TEMPORAL_ATTACK_SURFACE_SPEC | Race windows = D_t > W (damage window) |

---

## 15. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-06 | Initial spec. Formalized from Gemini/ChatGPT derivation. |

---

## 16. References

- Reynolds number (fluid dynamics) — the original dimensionless regime classifier
- Beck, J. "Temporal Attack Surface" — Δt framework for security analysis
- Beck, J. "Cybernetic Fault Domains" — When commitment outruns verification
- Ashby, W.R. "Introduction to Cybernetics" — Requisite variety, homeostasis

---

*"R_t = (P_t · D_t) / E_t"*

*"Your allowed power is proportional to your evidence and inversely proportional to your feedback delay."*

*"No receipts, no capability."*
