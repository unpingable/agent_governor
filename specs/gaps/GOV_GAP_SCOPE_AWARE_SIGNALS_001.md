# Gap Spec: Scope-Aware Signal Emission (Δb→Δo Pipeline)

**Status:** proposed (v3 — do not build now)
**Affects:** scope governor, signal plane, telemetry
**Date:** 2026-03-31
**Origin:** cybernetic failure taxonomy — Δb→Δo pipeline (wrong boundary → observability failure)

## Problem

If scope is misconfigured, signals and telemetry may measure the wrong things. Scope Governor constrains where agents *act* but doesn't constrain where signals *observe*. A scope misconfiguration could mean the governor is monitoring region A while the agent is drifting in region B.

## Proposed (v3)

Signal emission should be scope-aware: signals emitted for a governed activity should carry the scope context of the activity, not just the global governor state.

- Signals carry `scope_axes` from the active run scope
- Dashboard/telemetry can filter signals by scope
- Mismatched scope (signal from outside declared scope) is surfaced as anomalous

## Why Not Now

Scope governor and signal plane are stable but loosely coupled. Tightening this coupling is a cross-cutting change that touches many emission sites. Not appropriate for the current vertical slice.

## Dependencies

- `scope.py` (ScopeGovernor)
- `signals/emit.py` (SignalEmitter)
