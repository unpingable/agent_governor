# GOV_GAP_BUDGETED_EXECUTION_001

## Title
Budgeted Execution & Hybrid Routing Receipts

## Status
Gap spec (no code yet)

## Problem Statement

Governor sits where model choice, remote/local boundary, and tool spend become policy. But it doesn't record the spend. The runtime supervisor approves tool calls without knowing their cost. The lane router picks models without emitting a receipt for why. There's no budget enforcement, no spend ledger, and no overrun detection.

When a governed session costs $47 instead of $2, the operator can't answer:
- How much did each step cost?
- Why was a remote model used instead of local?
- Was the budget exceeded, and when?
- What was the estimated cost vs actual?

This matters now, not in some future with exotic inference backends. Every supervised session already makes routing and spend decisions that go unreceipted.

## What Already Exists

| Module | What it has | What's missing |
|--------|------------|----------------|
| `lanes.py` | Lane contracts, complexity estimation, model selection | No spend receipts, no budget enforcement |
| `routing.py` | ModelRegistry, adaptive routing | No cost tracking, no local/remote distinction |
| `execution.py` | ExecutionBudget with token/step caps | No per-step spend recording, no receipts |
| `supervisor.py` | Session lifecycle, tool interception | No cost awareness at all |
| `gate_receipt.py` | Content-addressed receipts with timing | No spend dimensions |

## Design

### Core Receipts

Five receipt types, phased:

#### BudgetPolicy (what's allowed)

```python
@dataclass(frozen=True)
class BudgetPolicy:
    policy_id: str
    lane: str
    dimensions: list[BudgetDimension]  # each has name, limit, severity (hard/soft)
    max_steps: int | None
    max_remote_hops: int | None
    trust_zone: str  # local_only | local_preferred | remote_allowed
    borrow_policy: str  # forbid | allow_with_receipt
```

#### BudgetDecisionReceipt (preflight routing choice)

Emitted when the router picks a model/backend for a step.

```python
@dataclass
class BudgetDecisionReceipt:
    receipt_id: str
    run_id: str
    policy_id: str
    task_class: str
    candidates: list[BudgetCandidate]  # each with model, provider, estimated_spend, accepted
    selected_candidate_id: str
    decision_reasons: list[str]
    estimated_run_spend: Spend
    remaining_budget_before: Spend | None
```

#### ExecutionSpendReceipt (per-step actual spend)

One per tool call or model invocation.

```python
@dataclass
class ExecutionSpendReceipt:
    receipt_id: str
    run_id: str
    step_index: int
    step_kind: str  # model | tool | retrieval | router
    model: str | None
    provider_kind: str  # local | remote | hybrid
    trust_zone: str
    execution_mode: str  # linear | hybrid | looped | tool_augmented
    estimated_spend: Spend | None
    actual_spend: Spend
    budget_remaining_after: Spend | None
    # Escape hatch for future backends
    backend_telemetry: dict[str, Any] | None
```

#### RunBudgetLedger (aggregate rollup)

One per session/run.

```python
@dataclass
class RunBudgetLedger:
    receipt_id: str
    run_id: str
    policy_id: str
    estimated_total: Spend | None
    actual_total: Spend
    total_steps: int
    total_remote_hops: int
    overruns: list[BudgetOverrun]  # dimension, limit, actual, severity
    remaining_budget_after: Spend | None
```

#### BudgetViolationReceipt (explicit overrun)

Emitted when a limit is exceeded.

```python
@dataclass
class BudgetViolationReceipt:
    receipt_id: str
    run_id: str
    policy_id: str
    violation_kind: str  # hard_limit_exceeded | soft_limit_exceeded | unapproved_remote_use | forbidden_model
    dimension: str | None
    allowed: float | None
    actual: float | None
    step_index: int | None
    auto_remediated: bool
    remediation_action: str | None
```

### Budget Dimensions

Multidimensional. Not just dollars.

| Dimension | Unit | Why |
|-----------|------|-----|
| `usd_micros` | int | Cost |
| `latency_ms` | int | Wall-clock time |
| `total_tokens` | int | Token spend |
| `remote_calls` | int | Off-box hops |
| `tool_calls` | int | Tool invocations |
| `privacy_points` | int | Privacy exposure (local=0, remote+raw=10) |

Phase 1 needs: `usd_micros`, `latency_ms`, `total_tokens`, `remote_calls`, `tool_calls`. The rest are opt-in.

### Trust Zones

Every step has a trust zone:

- **local_only** — inference runs on operator's machine
- **local_preferred** — local first, remote on failure/escalation
- **remote_allowed** — remote is fine
- **remote_required** — task requires a capability only available remotely

Trust zone is a policy constraint, not just metadata. A `local_only` policy that produces a remote hop is a violation.

### Estimated vs Actual

Both exist on every step receipt. The delta between them is a first-class signal:

- Router consistently underestimates → routing quality problem
- Router consistently overestimates → wasted budget headroom
- Single step wildly over estimate → unexpected model behavior

The `actual_vs_estimated_within_tolerance` invariant catches these.

### Borrowing

When a step exceeds its budget but the run continues:

- `borrow_policy: forbid` → hard stop, violation receipt
- `borrow_policy: allow_with_receipt` → continues, debt recorded in ledger

Debt is explicit. "Went over a bit" is how systems become theology.

## Integration Points

### Supervisor

The supervisor's `_handle_tool_proposed` should consult budget before creating an intervention. If the budget is exhausted, deny without asking the operator.

### Lane Router

`lanes.py` and `routing.py` should emit `BudgetDecisionReceipt` when selecting a model. The candidate list shows what was considered and why.

### Canonical Events

New event kinds:
- `budget_decision` — routing choice made
- `budget_overrun` — limit exceeded
- `budget_exhausted` — session stopped due to budget

### Gate Receipts

Existing gate receipts gain optional `spend` field in the timing fragment.

## Phase Plan

### Phase 1: Spend Tracking

- `BudgetPolicy` as a config object (JSON, per-session or per-profile)
- `ExecutionSpendReceipt` emitted per step
- `RunBudgetLedger` emitted at session end
- Hard budget cap enforcement (deny tool calls when exhausted)
- CLI: `governor runtime budget <session_id>`

### Phase 2: Routing Receipts

- `BudgetDecisionReceipt` from lane router
- Candidate comparison with estimated spend
- Estimated vs actual delta tracking
- Trust zone enforcement

### Phase 3: Violations and Borrowing

- `BudgetViolationReceipt` for overruns
- Borrow policy with explicit debt
- Violation integration with scar system (budget overruns create scars)

## Invariants

1. **Hard limits are hard.** A hard budget dimension cannot be exceeded without a violation receipt.
2. **Every remote hop is receipted.** No silent off-box calls.
3. **Estimates exist before actuals.** The router must estimate before the step runs.
4. **Borrowing is explicit.** Debt appears in the ledger, not as a silent overrun.
5. **Trust zone violations are violations.** A `local_only` policy that produces a remote call is a policy breach, not a degradation.

## Deferred Extension: Adaptive Inference Telemetry

When governor runs local models with looped/recurrent inference (future), the `ExecutionSpendReceipt.backend_telemetry` field gains structured subfields:

```python
@dataclass
class RecursionTelemetry:
    requested_recursions: int | None
    executed_recursions: int | None
    halted_early: bool | None
    halt_reason: str | None
    repeated_layer_range: tuple[int, int] | None
    effective_depth_multiplier: float | None
    token_level_depth_histogram: dict[str, int] | None
    kv_cache_reuse: bool | None
    loop_divergence_score: float | None
```

Plus policy extensions:
- `max_recursions_per_step`
- `max_total_recursions`
- `max_effective_depth_multiplier`

And invariants:
- `recursion_cap_respected`
- `actual_vs_estimated_within_tolerance` (applies to depth too)

This extension is **not part of the 3.x scope**. It's parked here so the schema doesn't need repainting when it becomes relevant.

## Open Questions

1. **Where do spend estimates come from?** Model registries with per-token pricing? Hardcoded tables? API response headers? Probably: a simple lookup table in the model registry, upgraded to API-reported costs when available.

2. **How granular is per-step tracking?** Every tool call? Every model inference? Both? Probably: both, since they have different cost profiles.

3. **Does budget policy live on the session or the profile?** Probably: profile provides defaults, session can override within profile bounds.
