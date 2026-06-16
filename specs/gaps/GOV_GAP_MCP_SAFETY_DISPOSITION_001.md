# GOV_GAP_MCP_SAFETY_DISPOSITION_001

**Status: RETIRED-UNUSED (not deferred).** Disposition ruling, 2026-06-16.
Operator-ratified. This gap exists to *close* a surface, not to schedule one.

## What existed

`src/governor/mcp_safety.py` (921 LOC) + `tests/test_mcp_safety.py` (777 LOC),
shipped and listed in `feature-history.md` as the "MCP Safety Controls" 3.x
platform feature: `RateLimiter`/`RateLimitConfig`, `BackpressureController`/
`ShedPolicy`, `CircuitBreaker`/`CircuitBreakerConfig`, `IdempotencyLayer`,
`LatencyEnforcer`/`LatencyBudget`, `FaultHandler` (sensor/actuator
classification), `SafetyController` (unified), plus module-level
`get_safety_controller()` / `execute_with_safety()`.

## Why retired (the evidence)

Surfaced by the operational-authority census
(`working/campaign-operational-authority-census.md`, 2026-06-16). The module
was the one shipped surface in the census with **no governing ruling and no
production consumer**:

- **No production import** — `grep -rn` across `src/` and `libs/` finds zero
  imports of `mcp_safety` or any of its classes outside the module itself.
  `mcp_server.py` does not use it despite the "MCP server self-protection"
  docstring.
- **Not exported** — absent from `src/governor/__init__.py`.
- **No entry point / no config reference** — nothing in `pyproject.toml`,
  `setup.py`, `setup.cfg`.
- **Tests covered algorithms, not production safety** — `test_mcp_safety.py`
  and the `TestMCPSafetyLifecycle` block in `test_qa_lifecycle.py` constructed
  the objects to exercise textbook algorithm behavior; passing them implied a
  protection the running system never received.
- **Suspiciously broad name** — "MCP Safety Controls" implied defense-in-depth
  the daemon/MCP server did not actually have. Dead code cosplaying as
  protection is worse than absence: it reads as covered.

Wiring it to a consumer "because the machinery exists" would have repeated the
P4 dependency-reversal error (architecture by orphan adoption). The capability
ideas (rate limit / backpressure / circuit breaking / idempotency / latency
deadline) are sound and generic; the *orphan implementation* is what is retired.

## Disposition (what was done, 2026-06-16)

1. Verified zero production imports / dynamic imports / entry points / config refs.
2. Classified tests: generic algorithm specimens, not production-safety coverage.
3. Confirmed doc/API claims: `feature-history.md`, `file-structure.md`,
   `docs/TELEMETRY_CONTROL_MAP.md` (Category B "monitoring only" row) — all
   updated to reflect retirement; the telemetry row removed (the signal source
   no longer exists).
4. Deleted `src/governor/mcp_safety.py` and `tests/test_mcp_safety.py`; removed
   the `TestMCPSafetyLifecycle` block from `tests/test_qa_lifecycle.py`.
5. Did **not** preserve a SPEC/drill artifact — the logic is generic CS (token
   bucket, circuit-breaker FSM, idempotency cache, latency deadline) and is
   cheaper to rebuild correctly than to maintain as an unowned specimen.
6. `feature-history.md` entry moved to **Retired** with reason prefix
   `[RETIRED 2026-06-16: REMOVED_UNUSED]`.

## Non-goals

- NOT a deferral. There is no queued work item here.
- NOT a retirement of the capability *class* (self-protection for the daemon /
  MCP server). Only this implementation is retired.
- NOT authorization to rebuild now.

## Resurrection condition

> A measured daemon/MCP failure mode requires bounded rate control,
> backpressure, or circuit breaking; ownership and receipt semantics are
> defined before an implementation is selected.

When that condition is met, build **from the operational seam outward** (the
observed failure mode dictates the control), not from a pre-existing module.
Re-open under a fresh gap spec (forcing-case lane), not by un-deleting this code.

## Cross-references

- `working/campaign-operational-authority-census.md` — the census that found it.
- `memory/campaign_workflow_kernel_annealing.md` (P4 PARKED) — the
  dependency-reversal error this disposition deliberately avoids.
