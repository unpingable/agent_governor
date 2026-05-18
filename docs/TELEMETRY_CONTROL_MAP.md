# Telemetry → Control Surface Map

Audit date: 2026-02-18 (updated). Methodology: static analysis (emitter + consumer + window semantics).

## Executive Summary

**Emitters**: 19 gate receipt points, 11 structured telemetry event types, 7 kernel event types, 25+ domain events.

**Consumers**: 5 active control loops, 6 CLI/dashboard display endpoints, 17+ subsystem `status()/stats()` methods.

**Wired (2.x)**: Regime → risk_class coupling, LLM telemetry → within-lane model selection (autopilot level 2), probe outcome rate → model penalty, cooldown store (keyed failures + compaction), StatusRollup single truth object.

**Remaining gap**: Escalation frequency not aggregated, scar burst rate not fed into routing, BudgetManager spend not coordinated with lane budgets.

**Window semantics**: 3 critical mismatches — ALL FIXED. dt-aware EMA in homeostat.py and routing.py. See "Window Semantics Issues" section.

---

## Telemetry Control Map

### Category A: Immediate Routing Constraints (Hard Gates)

These signals feed into control decisions.

| Signal | Emitted At | Labels | Consumer | Autopilot Use |
|--------|-----------|--------|----------|---------------|
| Stability probe decision | semantic_stability.py:2138 | kind (PROCEED/MITIGATE/BLOCK/HUMAN_GATE), stiffness, anisotropy | lanes.py CascadeExecutor (probe_fn) | **WIRED** — drives mitigate/escalate/block |
| Validator pass/fail | lanes.py:1456 (stub) | validator_name, output | CascadeExecutor | **WIRED** — failure triggers escalation |
| Risk class | Caller-provided | standard/elevated/critical | LaneRouter.route() | **WIRED** — hard override to min lane |
| Side effects flag | Caller-provided | bool | LaneRouter.route() | **WIRED** — forces Lane 3 |
| ClaimType complexity | routing.py:160 CLAIM_COMPLEXITY | claim_type → score | ComplexityEstimator, LaneRouter | **WIRED** — drives initial lane |
| Budget exhaustion | lanes.py:1233 | budget_spent, budget_total | CascadeExecutor | **WIRED** — stops cascade |
| **Regime → risk_class** | regime.py:436-456, daemon.py | ELASTIC/WARM/DUCTILE/UNSTABLE → standard/elevated/critical | daemon.py `_handle_chat_send()` → LaneRouter.route() | **WIRED** — DUCTILE→elevated, UNSTABLE→critical (commit 00e5243) |
| **LLM call success/fail** | telemetry.py:948 record_llm_call | model, provider, success, duration_ms, cost_usd | lanes.py `_select_model()` via telemetry query | **WIRED** — per-model success_rate fed into within-lane selection (commit 6d76882) |
| **Probe instability rate** | semantic_stability.py:2185 record_stability_probe | stiffness, anisotropy, model, mode | lanes.py `_select_model()` penalty | **WIRED** — per-model probe fail rate → selection penalty (commit 049ccf7) |
| **Cooldown store** | lanes.py CooldownStore | model, lane, validator_failures, timestamp | LaneRouter `_select_model()` | **WIRED** — keyed failures persisted, models with recent failures skipped (commit 00e5243) |

### Category B: Provider/Model Health (Soft Gates + Scorecard)

Signals that exist but are NOT yet consumed for routing.

| Signal | Emitted At | Labels | Current Consumer | Autopilot Potential |
|--------|-----------|--------|-----------------|-------------------|
| **success_rate by model** | routing.py:550 (dt-aware EMA) | model_name, tier | Router.route() tier escalation | **PARTIAL** — used for tier escalation; lane selection reads telemetry directly |
| **Validator fail reasons** | lanes.py CascadeResult.validators_failed | validator_name, lane, model | CooldownStore (keyed by model+lane) | **PARTIAL** — stored for cooldown, not yet used for per-validator banning |
| **MCP rate limit / circuit breaker** | mcp_safety.py:127 | client_id, tool, p95_ms | mcp_safety.py get_stats() (monitoring only) | MEDIUM — feed latency into model selection |
| **Error rate by operation** | telemetry.py:1018 record_error | error_code, context | CLI display | MEDIUM — per-model error rate for cooldown |

### Category C: Cost/Budget Dynamics (Budgeted Control)

| Signal | Emitted At | Labels | Current Consumer | Autopilot Potential |
|--------|-----------|--------|-----------------|-------------------|
| **LLM call cost** | telemetry.py:948 | model, cost_usd, input_tokens, output_tokens | telemetry analyze costs (display) + lanes.py level-2 within-lane preference | **WIRED** — cheapest-within-lane at autopilot level 2 |
| **Budget record_usage** | routing.py:855 | cost_usd, input_tokens, output_tokens | BudgetManager internal | PARTIAL — BudgetManager tracks spend but lanes.py doesn't read it |
| **Cascade budget_spent** | lanes.py CascadeResult | budget_spent_usd, budget_exhausted | CascadeExecutor (stops cascade) | **WIRED** — per-request budget enforcement |
| **Per-scope budget** | scope.py grants | grant_id, usage_count | scope.py internal | MEDIUM — scope budget → lane budget coordination |

### Category D: Drift / Regression Detection (Canaries + Rollback)

| Signal | Emitted At | Labels | Current Consumer | Autopilot Potential |
|--------|-----------|--------|-----------------|-------------------|
| **Correlator K-vector** | correlator_telemetry.py:963 | T, F, A, C, capture regime | Dashboard display, VS Code status bar | MEDIUM — capture detection → freeze lane policy changes |
| **Escalation frequency** | lanes.py escalation_chain | lane, model, reason | Nowhere (returned to caller) | **HIGH** — sudden spike in escalations = model regression canary |
| **Scar creation rate** | scars.py:1201 | region, failure_mode | CLI scar list (display) | MEDIUM — scar burst → routing avoidance |
| **Convergence metrics** | convergence_tuning.py:1252 | success_rate, violation_rate_delta | Admissibility check (convergence proposals only) | MEDIUM — convergence failure rate → probe policy tightening |

---

## "Emitted but Not Consumed" — Remaining Shelfware

Signals we emit that nobody reads for control decisions:

| Signal | Emit Site | What It Could Do |
|--------|----------|-----------------|
| **Escalation frequency** | lanes.py escalation_chain | Aggregate → spike detection → model regression canary |
| **Scar ledger get_summary()** | scars.py:1201 | Already has active_scars count → feed into risk_class estimation |
| **BudgetManager scope tracking** | routing.py:855 | Already records cost → feed actual spend into per-request total enforcement |
| **DashboardStore pass_rate** | dashboard_ux.py:667 | Already aggregated → trend detection for regression canary |

Items previously on this list that have been **SHIPPED**:

| Signal | Shipped In | Where |
|--------|-----------|-------|
| ~~CascadeResult.escalation_chain~~ | CooldownStore (commit 00e5243) | `lanes.py` CooldownStore persists keyed failures |
| ~~CascadeResult.validators_failed~~ | CooldownStore (commit 00e5243) | `lanes.py` CooldownStore records validator failures per model+lane |
| ~~record_llm_call() success/duration~~ | Autopilot level 2 (commit 6d76882) | `lanes.py _select_model()` queries telemetry for candidate models |
| ~~record_stability_probe() stiffness~~ | Probe penalty (commit 049ccf7) | `lanes.py _select_model()` applies selection penalty |
| ~~Regime transition events~~ | Regime → risk_class (commit 00e5243) | `daemon.py` maps regime → risk_class for lane routing |
| ~~StatusRollup (suggestion)~~ | StatusRollup module (commit 5f4f3a4) | `src/governor/status_rollup.py` — frozen dataclass, schema v1 |

---

## Window Semantics Issues

### Critical (Aggregation Unsafe) — ALL FIXED

| Module | Line | Issue | Fix |
|--------|------|-------|-----|
| **regime.py** | 630 | ~~Hardcoded `window_time = 60.0` seconds mixed with `window_size = 10` proposal counts~~ | **FIXED**: contradiction rates now use `events / window_time_s` (events-per-second). Denominator independent of `window_size`. 3 tests in TestWindowSemantics. |
| **research.py** | 192 | ~~`lambda_decay = 0.05` per undefined period~~ | **FIXED**: Added `decay_half_life_s` config (wall-clock half-life). `tick()` computes `dt = monotonic() - last_tick_time` and decays `C(t) = C(t-1) * 2^(-dt/half_life)`. Legacy per-tick mode preserved when `decay_half_life_s=0`. 5 tests. |
| **correlator_telemetry.py** | 885 | ~~`_window_step` frequency unknown~~ | **FIXED**: Added `window_elapsed_s` to KVector (monotonic dt between observations). Enables time-normalised rate comparison across deployments. 4 tests in TestWindowElapsedTime. |

### High Risk — FIXED (dt-aware EMA)

| Module | Line | Issue | Fix |
|--------|------|-------|-----|
| **homeostat.py** | 617 | ~~EMA α=0.3 constant regardless of observation interval~~ | **FIXED**: `dt_ema_alpha()` from `control_theory.py` computes time-aware α from `dt` and `half_life_s`. Urgency smoothing now dt-aware. (commit 83ae082) |
| **routing.py** | 552 | ~~EMA α=0.1 hardcoded. No time-awareness~~ | **FIXED**: Model success rate EMA now uses `dt_ema_alpha()` with configurable half-life. (commit 83ae082) |
| **dashboard.py** | 54 | Window sizes (30, 60, 12) hardcoded | Low risk — display-only, not used for control decisions. Documenting as accepted. |

### Well-Defined (No Action Needed)

| Module | Line | Status |
|--------|------|--------|
| ttl.py | 38-129 | Time-based with per-volatility policies. Excellent docs |
| hysteresis.py | 61 | Explicit 300s window. Clear |
| ultrastability.py | 322 | Turn-based epochs. Documented |
| staleness.py | 38 | `default_freshness_window = timedelta(days=7)`. Clear |

---

## Autopilot Unlocks — Status

### 1. Within-Lane Provider Selection (Level 2) — SHIPPED

`lanes.py _select_model()` queries last N `LLM_CALL` events for candidate models. Models below quality floor excluded; among remaining, prefers cheaper/faster. Commit 6d76882.

### 2. Cooldown / Negative Result Store — SHIPPED

`lanes.py CooldownStore` persists `(model, lane, validator_failures, timestamp)` tuples with thread-safe locking and configurable compaction. On next route, models with recent failures for that lane are skipped. Commit 00e5243.

### 3. Regime → Lane Policy Coupling — SHIPPED

`daemon.py _handle_chat_send()` reads regime status when `use_lanes=True` and maps DUCTILE→elevated, UNSTABLE→critical. Passed as `risk_class` to `LaneRouter.route()`. Commit 00e5243.

### 4. Probe Outcome Rate → Model Cooldown — SHIPPED

After probe MITIGATE/BLOCK, per-model penalty is applied in `_select_model()`. Models with high MITIGATE rate are deprioritized in lane selection. Commit 049ccf7.

### 5. StatusRollup — SHIPPED

`src/governor/status_rollup.py`: frozen `StatusRollup` dataclass (schema v1), `build_status_rollup()` builder, dumb `render_text()` / `render_json()` formatters. Single truth object for CLI, WebUI, and VS Code. `governor status` defaults to one-pager dashboard. Commit 5f4f3a4.

---

## Naming Drift (ChatGPT's Observation)

| Current Name | Location | Issue | Fix |
|-------------|----------|-------|-----|
| ~~`contradiction_density`~~ | viewmodel.py | ~~Sources from `contradiction_open_rate` — that's a rate, not density~~ | **FIXED** — renamed to `contradiction_open_rate` (commit 83ae082) |
| `status()` vs `stats()` vs `get_summary()` | 17+ modules | Inconsistent vocabulary | Document: `status()` = state snapshot, `stats()` = counters/rates, `get_summary()` = human rollup |

---

## Remaining Work (Priority Order)

1. **Aggregate escalation frequency** for model regression canary (HIGH, ~40 lines)
2. **Feed scar burst rate** into risk_class estimation (MEDIUM, ~30 lines)
3. **Coordinate BudgetManager** spend with lane budgets (MEDIUM, ~50 lines)
4. **Add WindowDescriptor** to all window definitions (documentation pass)
