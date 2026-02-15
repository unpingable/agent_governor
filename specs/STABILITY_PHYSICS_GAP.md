# Stability Physics: Deferred Features

Gap spec for physics-inspired metrics not yet implemented in `semantic_stability.py`.
Filed alongside escape rate implementation (v2 schema).

## Status

| Feature | Status | Blocker | Priority |
|---------|--------|---------|----------|
| Escape rate | **Shipped** (v2) | — | — |
| Hysteresis | Deferred | Canonicalizer | High |
| Susceptibility curve | Deferred | None | Medium |
| Effective temperature (T_eff) | Partial (~30%) | None | Medium |
| Critical slowing down | Deferred | Time-series stats | Low |
| Fluctuation-dissipation | Deferred | None | Low |
| Lyapunov divergence rate | Deferred | Streaming API | Low |

## 1. Hysteresis (path dependence)

**What it measures**: Does the model return to baseline after perturbation is removed?
Regime transitions with memory ("once refusal, always refusal" grooves).

**Why deferred**: Perturbations are not invertible. "Ramp down" is undefined without a canonicalizer.
Implementing without canonicalization measures "path dependence of random seeds" — not physics.

**Prerequisite**: `canonicalize_prompt(prompt)` that:
- Normalizes whitespace, bullets, indentation
- Normalizes role wrapper to a canonical form
- Strips inserted hedges (only the ones we add)
- Preserves atomic segments verbatim
- Clause order canonicalization is the hardest part (can punt initially)

**Clean implementation plan**:
1. Ramp protocol: `P0 → P1 → ... → PS` (progressive perturbation)
2. Generate outputs `O0 ... OS`
3. Ramp down: canonicalize and reapply weaker perturbations (or just canonicalize)
4. Metric: basin membership on up vs down at matched magnitudes
5. Simpler version: "did we return to baseline basin after canonicalization?" (binary + time-to-return)

**Fingerprint fields**: `hysteresis_lag: float`, `returned_to_baseline: bool`

**Call budget**: ~2S additional generate calls (S ramp steps up + S down). Budget-gated.

## 2. Susceptibility Curve (nonlinear response)

**What it measures**: Stiffness across multiple magnitudes. Detects "looks stable at tiny nudges
but snaps at a threshold" — proximity to phase boundaries / seams.

**Implementation**:
- Run same perturbation family at magnitudes ~0.01, 0.05, 0.1, 0.2
- Record (magnitude_bin, stiffness) pairs
- Detect nonlinearity: quadratic fit residual, or just slope change between bins

**Cheap version**: Apply same perturbation generator 1x, 2x, 3x (repeated application increases
effective magnitude). No new perturbation types needed.

**Fingerprint fields**: `susceptibility_curve: dict[str, float]` (magnitude_bin → stiffness)

**Call budget**: 3-4 extra generate calls per perturbation kind tested.

## 3. Effective Temperature (T_eff formalization)

**What exists**: `noise_floor` is computed and stored. `decoding_params` config field exists but unused.

**What's missing**:
- Link `config.decoding_params` (temperature, top_p) to noise_floor measurement
- Sweep decoding temps, measure noise_floor at each point
- Fit `noise_floor(temperature)` curve
- Calibrated thresholds that adapt with T_eff

**Implementation**: `TemperatureSweeper` class or extend `audit()` to optionally sweep temperature.
Requires generate_fn to accept decoding params (currently `Callable[[str], str]`).

## 4. Critical Slowing Down (early warning)

**What it measures**: Rising variance / autocorrelation near phase transitions.
"Pre-cliff wobble" as an early warning signal.

**Proxy signals**:
- Increased variance in divergence as magnitude increases slightly
- Longer "runs" of similar-but-wrong modes
- Slower return to baseline basin

**Implementation**: `CriticalSlowingAnalyzer` operating over `StabilityStore` history.
Computes variance trend and lag-1 autocorrelation over rolling window.

**Blocker**: Needs time-series ordering across audits. Timestamps exist but aren't used for trending.

## 5. Fluctuation-Dissipation Check (sanity diagnostic)

**What it measures**: Correlation between noise_floor and stiffness across audit history.
If higher noise_floor predicts higher stiffness after subtraction, the subtraction isn't
fully decoupling temperature from conditioning.

**Implementation**: Pearson correlation over `StabilityStore.query()` results.
Fit: `stiffness = k * noise_floor + b`. Report residual.

**Not a feature** — a diagnostic. Run it as a health check, not per-audit.

## 6. Lyapunov Divergence Rate (trajectory sensitivity)

**What it measures**: Exponential divergence growth over "token time" between two nearby prompts.

**Blocker**: Current `generate_fn: Callable[[str], str]` returns final text, not a token stream.
Would need streaming generate_fn to capture intermediate states.

**If unblocked**: Generate stepwise/chunkwise, compute divergence at each step,
fit growth rate. Exponential = chaotic-ish territory.

**Verdict**: Not worth the API change now. Revisit if streaming audit becomes a requirement.

## Design Principles (from review)

- **Same divergence channel**: Escape rate uses stripped divergence (same as stiffness).
  New metrics should too, unless they explicitly need raw.
- **Absolute vs excess**: Basin membership uses absolute divergence (semantics boundary).
  Stiffness uses excess (temperature-corrected). Don't mix.
- **Negation exclusion**: Consistent everywhere. Negation probe is a positive control,
  not a data point for stability metrics.
- **Call budget**: Every new metric must respect `max_generate_calls`. Return partial results
  on budget exceeded — never raise.
- **Schema version**: Adding new fingerprint fields → bump `STABILITY_SCHEMA_VERSION`.
  Old records load with `.get()` defaults for new optional fields.
