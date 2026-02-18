# Telemetry → Control Surface Map

Audit date: 2026-02-18. Methodology: static analysis (emitter + consumer + window semantics).

## Executive Summary

**Emitters**: 19 gate receipt points, 11 structured telemetry event types, 7 kernel event types, 25+ domain events.

**Consumers**: 5 active control loops, 6 CLI/dashboard display endpoints, 17+ subsystem `status()/stats()` methods.

**Gap**: Most telemetry is emitted but consumed only for display. The routing loop reads `success_rate` but ignores probe outcomes, validator fail rates, and escalation frequency. The lane routing system (`lanes.py`) emits cascade results but nobody reads them back into routing policy.

**Window inconsistency**: 3 critical mismatches (regime.py mixes turn-count with 60s hardcoded; research.py decays per undefined period; correlator turn-step has unknown frequency).

---

## Telemetry Control Map

### Category A: Immediate Routing Constraints (Hard Gates)

These signals already feed into control decisions.

| Signal | Emitted At | Labels | Consumer | Autopilot Use |
|--------|-----------|--------|----------|---------------|
| Stability probe decision | semantic_stability.py:2138 | kind (PROCEED/MITIGATE/BLOCK/HUMAN_GATE), stiffness, anisotropy | lanes.py CascadeExecutor (probe_fn) | **WIRED** — drives mitigate/escalate/block |
| Validator pass/fail | lanes.py:1456 (stub) | validator_name, output | CascadeExecutor | **WIRED** — failure triggers escalation |
| Risk class | Caller-provided | standard/elevated/critical | LaneRouter.route() | **WIRED** — hard override to min lane |
| Side effects flag | Caller-provided | bool | LaneRouter.route() | **WIRED** — forces Lane 3 |
| ClaimType complexity | routing.py:160 CLAIM_COMPLEXITY | claim_type → score | ComplexityEstimator, LaneRouter | **WIRED** — drives initial lane |
| Budget exhaustion | lanes.py:1233 | budget_spent, budget_total | CascadeExecutor | **WIRED** — stops cascade |

### Category B: Provider/Model Health (Soft Gates + Scorecard)

These signals exist but are NOT consumed for routing. **Free autopilot fuel.**

| Signal | Emitted At | Labels | Current Consumer | Autopilot Potential |
|--------|-----------|--------|-----------------|-------------------|
| **LLM call success/fail** | telemetry.py:948 record_llm_call | model, provider, success, duration_ms, cost_usd | CLI `telemetry analyze` (display only) | **HIGH** — feed into per-model success_rate for lane selection |
| **success_rate by model** | routing.py:550 (EMA α=0.1) | model_name, tier | Router.route() tier escalation | **PARTIAL** — used for tier escalation but NOT for within-lane selection in lanes.py |
| **Probe instability rate** | semantic_stability.py:2185 record_stability_probe | stiffness, anisotropy, model, mode | CLI `conditioning history` (display only) | **HIGH** — per-model probe fail rate → "ban model from Lane 2 for strict-format" |
| **Fallback chain usage** | lanes.py CascadeResult.escalation_chain | lane_from, lane_to, model, reason | Nowhere (returned to caller, not persisted) | **HIGH** — becomes provider reliability score + negative result store |
| **Validator fail reasons** | lanes.py CascadeResult.validators_failed | validator_name, lane, model | Nowhere (returned to caller) | **HIGH** — "model X fails schema validator 40% → banned from Lane 2 strict" |
| **MCP rate limit / circuit breaker** | mcp_safety.py:127 | client_id, tool, p95_ms | mcp_safety.py get_stats() (monitoring only) | MEDIUM — feed latency into model selection |
| **Error rate by operation** | telemetry.py:1018 record_error | error_code, context | CLI display | MEDIUM — per-model error rate for cooldown |

### Category C: Cost/Budget Dynamics (Budgeted Control)

| Signal | Emitted At | Labels | Current Consumer | Autopilot Potential |
|--------|-----------|--------|-----------------|-------------------|
| **LLM call cost** | telemetry.py:948 | model, cost_usd, input_tokens, output_tokens | telemetry analyze costs (display) | **HIGH** — actual cost vs budget_per_call_usd for level-2 cheapest-within-lane |
| **Budget record_usage** | routing.py:855 | cost_usd, input_tokens, output_tokens | BudgetManager internal | PARTIAL — BudgetManager tracks spend but lanes.py doesn't read it |
| **Cascade budget_spent** | lanes.py CascadeResult | budget_spent_usd, budget_exhausted | Nowhere (returned to caller) | **HIGH** — feed back into per-request budget enforcement |
| **Per-scope budget** | scope.py grants | grant_id, usage_count | scope.py internal | MEDIUM — scope budget → lane budget coordination |

### Category D: Drift / Regression Detection (Canaries + Rollback)

| Signal | Emitted At | Labels | Current Consumer | Autopilot Potential |
|--------|-----------|--------|-----------------|-------------------|
| **Regime transitions** | regime.py:436-456 | ELASTIC/WARM/DUCTILE/UNSTABLE, rejection_rate | regime.py internal (recommendations) | **HIGH** — regime → lane policy (DUCTILE → min Lane 2, UNSTABLE → min Lane 3) |
| **Correlator K-vector** | correlator_telemetry.py:963 | T, F, A, C, capture regime | Dashboard display, VS Code status bar | MEDIUM — capture detection → freeze lane policy changes |
| **Escalation frequency** | lanes.py escalation_chain | lane, model, reason | Nowhere | **HIGH** — sudden spike in escalations = model regression canary |
| **Probe outcome rate shift** | semantic_stability.py (per audit) | stiffness_by_kind, model | CLI history display | **HIGH** — if MITIGATE rate jumps 30% for a model → cooldown |
| **Scar creation rate** | scars.py:1201 | region, failure_mode | CLI scar list (display) | MEDIUM — scar burst → routing avoidance |
| **Convergence metrics** | convergence_tuning.py:1252 | success_rate, violation_rate_delta | Admissibility check (convergence proposals only) | MEDIUM — convergence failure rate → probe policy tightening |

---

## "Emitted but Not Consumed" — The Shelfware List

These are signals we already emit that nobody reads for control decisions:

| Signal | Emit Site | What It Could Do |
|--------|----------|-----------------|
| **CascadeResult.escalation_chain** | lanes.py | Persist → compute provider reliability score → negative result store (v3 deferred) |
| **CascadeResult.validators_failed** | lanes.py | Persist → per-model+validator fail rate → "model X banned from strict-format 6h" |
| **record_llm_call() success/duration** | telemetry.py:948 | Already logged to JSONL → aggregate per-model latency_p95 → within-lane preference |
| **record_stability_probe() stiffness** | telemetry.py:1194 | Already logged → per-model stiffness_p90 → probe policy escalation per model |
| **Regime transition events** | regime.py get_history() | Already persisted → feed regime into lane contracts (DUCTILE → tighten) |
| **Scar ledger get_summary()** | scars.py:1201 | Already has active_scars count → feed into risk_class estimation |
| **BudgetManager scope tracking** | routing.py:855 | Already records cost → feed actual spend into per-request total enforcement |
| **DashboardStore pass_rate** | dashboard_ux.py:667 | Already aggregated → trend detection for regression canary |

---

## Window Semantics Issues

### Critical (Aggregation Unsafe) — ALL FIXED

| Module | Line | Issue | Fix |
|--------|------|-------|-----|
| **regime.py** | 630 | ~~Hardcoded `window_time = 60.0` seconds mixed with `window_size = 10` proposal counts~~ | **FIXED**: contradiction rates now use `events / window_time_s` (events-per-second). Denominator independent of `window_size`. 3 tests in TestWindowSemantics. |
| **research.py** | 192 | ~~`lambda_decay = 0.05` per undefined period~~ | **FIXED**: Added `decay_half_life_s` config (wall-clock half-life). `tick()` computes `dt = monotonic() - last_tick_time` and decays `C(t) = C(t-1) * 2^(-dt/half_life)`. Legacy per-tick mode preserved when `decay_half_life_s=0`. 5 tests. |
| **correlator_telemetry.py** | 885 | ~~`_window_step` frequency unknown~~ | **FIXED**: Added `window_elapsed_s` to KVector (monotonic dt between observations). Enables time-normalised rate comparison across deployments. 4 tests in TestWindowElapsedTime. |

### High Risk (Likely Apples-to-Oranges)

| Module | Line | Issue |
|--------|------|-------|
| **homeostat.py** | 617 | EMA α=0.3 constant regardless of observation interval. If turns vary 100x, EMA decay is wrong |
| **routing.py** | 552 | EMA α=0.1 hardcoded. No time-awareness |
| **dashboard.py** | 54 | Window sizes (30, 60, 12) hardcoded. Duration = frequency × count, but frequency unknown |

### Well-Defined (No Action Needed)

| Module | Line | Status |
|--------|------|--------|
| ttl.py | 38-129 | Time-based with per-volatility policies. Excellent docs |
| hysteresis.py | 61 | Explicit 300s window. Clear |
| ultrastability.py | 322 | Turn-based epochs. Documented |
| staleness.py | 38 | `default_freshness_window = timedelta(days=7)`. Clear |

---

## Minimal Autopilot Unlocks (No New Sensors Required)

### 1. Within-Lane Provider Selection (Level 2) — Highest Leverage

**What exists**: `record_llm_call()` logs model, success, duration_ms, cost_usd to JSONL.
**What's missing**: Nobody reads it back for lane selection.
**Wire**: In `LaneRouter._select_model()`, query last N `LLM_CALL` events for candidate models. Exclude models below quality floor (success_rate < 0.7). Among remaining, prefer cheaper/faster.

```
Effort: ~50 lines in lanes.py + telemetry query helper
Impact: Autopilot Level 2 becomes meaningful (currently just sorts by cost_input)
```

### 2. Cooldown / Negative Result Store — Second Highest

**What exists**: `CascadeResult.validators_failed` and `escalation_chain` are returned but never persisted.
**What's missing**: No persistence → no memory of "model X fails at Lane 2".
**Wire**: After each cascade, persist `(model, lane, validator_failures, timestamp)` tuples. On next route, skip models with recent failures for that lane.

```
Effort: ~80 lines (small JSONL store + lookup in _select_model)
Impact: "provider X + contract Y fails validators → don't pick for N minutes"
```

### 3. Regime → Lane Policy Coupling — Third

**What exists**: `RegimeDetector.classify()` produces ELASTIC/WARM/DUCTILE/UNSTABLE. `LaneRouter.route()` accepts `risk_class`.
**What's missing**: No bridge. Regime classification is never fed into lane routing.
**Wire**: In daemon.py `_handle_chat_send()`, when `use_lanes=True`, read `regime.status()` and map: DUCTILE→elevated, UNSTABLE→critical. Pass as `risk_class` to `LaneRouter.route()`.

```
Effort: ~15 lines in daemon.py
Impact: System auto-tightens routing when operational health degrades
```

### 4. Probe Outcome Rate → Model Cooldown — Fourth

**What exists**: `record_stability_probe()` logs stiffness, recommendation per model. `CascadeResult` includes `probe_decision`.
**What's missing**: No aggregation of probe failure rate per model.
**Wire**: After probe MITIGATE/BLOCK, increment per-model counter. If model's MITIGATE rate exceeds threshold (e.g. 30% over last 20 calls), mark as "probed-unreliable" and prefer alternatives in `_select_model()`.

```
Effort: ~60 lines (counter + threshold check)
Impact: Automatically routes away from models that are unstable under perturbation
```

---

## Naming Drift (Chatty's Observation)

| Current Name | Location | Issue | Fix |
|-------------|----------|-------|-----|
| `contradiction_density` | viewmodel.py | Sources from `contradiction_open_rate` — that's a rate, not density | Rename to `contradiction_open_rate` |
| `status()` vs `stats()` vs `get_summary()` | 17+ modules | Inconsistent vocabulary | Document: `status()` = state snapshot, `stats()` = counters/rates, `get_summary()` = human rollup |

---

## Next Steps (Priority Order)

1. **Wire regime → risk_class** (15 lines, highest ROI)
2. **Persist cascade outcomes** for cooldown store (80 lines)
3. **Read LLM_CALL telemetry** back into model selection (50 lines)
4. **Fix regime.py window_time** hardcoded 60s (rename/document)
5. **Add WindowDescriptor** to all window definitions (documentation pass)
6. Consider `StatusRollup` module (chatty's suggestion) as single truth object for CLI/MCP/WebUI
