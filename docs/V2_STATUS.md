# V2 Status

As of 2.3.0. This document is the boundary between "shipped" and "next."

---

## Shipped in 2.x

### 2.0.0 — The Gate

Everything in BUILD_SPEC.md. Typed claims, receipt-producing verification, transactional
ledgers, multi-agent dispatcher, epistemic governance, regime detection, evidence gate,
intent compiler, governor daemon (JSON-RPC over stdio/socket), receipt kernel, scope
governor, semantic stability, lane routing, all four domain governors (code, fiction,
nonfiction, ops), and ~7800 tests.

See `implementation-summary.md` for the full feature list.

### 2.0.1 — Preflight + Codex

Preflight checks (`governor preflight`), Codex hooks (`governor codex-hooks`), agent
integration tests. Post-hoc enforcement for Codex (no pre-tool blocking).

### 2.0.2 — Test Hardening

Fresh-clone smoke tests, adversarial hook bypass tests, upgrade path tests (SQLite
migration), scale/performance tests (10k receipts, 1k claims, 20-thread concurrency).

### 2.1.0 — Receipt Kernel Bridge + Oracle

Receipt kernel bridge wired into evidence gate. CLI `governor kernel verify` and
`governor kernel runs`. Oracle:pytest_log evidence kind. HARD claim + oracle evidence
→ confidence PASS path.

### 2.2.0 — Lane Routing + Stability Probes

Capability-based lane routing (Lane 0-3), cascade executor, artifact reuse store.
Glass cannon detection, 4 stability transforms. Probe vs mitigation policy wired.
Regime→risk_class coupling, cooldown store, LLM telemetry→model selection (autopilot
level 2), probe outcome rate→model penalty. dt-aware EMA (fixed 3 window semantics
mismatches). VS Code extension 2.2.0.

### 2.3.0 — Operator Surface + Clarity Sensor

StatusRollup shared truth object. `governor status` flipped from proposals to operator
dashboard (one-pager). CLUD Clarity Sensor (compression-based precision detection,
contract + harness, no LLM calls). Doc updates: telemetry control map, CLI reference,
security model.

---

## Parked: Instrumentation Spine (v2.4)

Seven gap specs designed but not built. These are the "observe, measure, warn" layer
that precedes any 3.x self-governance work. All are observe-first — no gating, no
policy changes, no new enforcement.

| Phase | Spec | What It Does |
|-------|------|-------------|
| A | SILENT_SUPPRESSION_GAP | Detect when the governor is plugged in but not running |
| A | EXPOSURE_PROXY_GAP | Non-gameable denominator for capture metrics |
| A | SIGMA_RATE_GAP | Endorsement-then-invalidation rate as time series |
| B | CAPTURE_SELF_DIAGNOSTIC_GAP | Advisory warning on declining contradiction rates |
| C | REPLAY_HARNESS_GAP | Replay stored runs with different thresholds |
| C | CALIBRATION_LAYER_GAP | Normalize signals to [0,1] with versioned params |
| D | PREDICT_REGIME_PREFLIGHT_GAP | Predict regime from pre-session metrics |

All emit via SignalEnvelope (defined in `GAP_BUILD_ORDER.md`). The envelope is
intentionally isomorphic to the eventual v3 schema — v3 promotes and freezes; no rewrite.

**Build order:** A→B→C→D. See `specs/gaps/GAP_BUILD_ORDER.md` for dependency graph.

**Why parked:** The core gate works. These are diagnostic tools for operators who want
to understand *why* the gate fired, not *whether* it fires. Ship them when someone needs
them, not before.

---

## Explicit 3.x

The [self-governance spec](../specs/core/SELF_GOVERNANCE_SPEC.md) defines the 3.x
security architecture:

- Executor/proposer separation
- Admissible measurement gating
- Cross-model validation quorum
- Rollback + hysteresis + dwell

8 hardening items require human review before building. The one-liner:

> Any θ update requires: admissible measurement coverage + independent validator
> quorum + no valid veto witness.

**Prerequisite:** The instrumentation spine (v2.4) must ship first — 3.x needs
calibrated signals and replay for validation.

Four gap specs are explicitly 3.x:

| Spec | What |
|------|------|
| CROSS_DOMAIN_SCHEMA_GAP | Public API schema versioning, clock semantics, partition keys |
| PAAS_SHARDING_GAP | Multi-daemon roles, epoch roots, ordering guarantees |
| KAPPA_DIAL_GAP | κ as a measurable policy knob (requires calibration) |
| REGIME_CAPTURE_2D_GAP | Regime + capture on same calibrated scale |

---

## Known-Good Bundle (2.3.0)

| Repo | Version | Coupling |
|------|---------|----------|
| [agent_gov](https://github.com/unpingable/agent_governor) | 2.3.0 | — |
| [maude](https://github.com/unpingable/maude) | 2.3.0 | hard (mirrors major.minor) |
| [vscode-governor](https://github.com/unpingable/vscode-governor) | 2.3.0 | hard (mirrors major.minor) |
| [guvnah](https://github.com/unpingable/guvnah) | 2.3.0 | hard (mirrors major.minor) |
| [gov-webui](https://github.com/unpingable/governor_webui) | 0.3.0 | loose (targets contract v1) |

**Sanity check** (run these to verify you're not in version hell):

```bash
governor --version                      # should say 2.3.0
governor status --json | python3 -c "import sys,json; print(json.load(sys.stdin)['schema_version'])"  # should say 1
governor doctor                         # walk 9 subsystems, flag non-nominal
make test                               # in each repo
```

See `docs/VERSIONING.md` for the coupling rules and contract version table.

---

## What To Do Next

If you're returning to this codebase:

1. **Run the tests.** `python3 -m pytest tests/ -v` — ~11,200 tests, all should pass.
2. **Read the gate.** `src/governor/evidence_gate.py` is the enforcement surface.
   Everything else feeds into it or reads from it.
3. **Read the daemon.** `src/governor/daemon.py` is the control plane. 36 RPC methods,
   lazy subsystem init, Unix socket or stdio.
4. **Read the receipts.** `src/governor/gate_receipt.py` (decision receipts) and
   `libs/receipt_kernel/` (audit trail). Content-addressed, hash-chained, append-only.

If you're building the instrumentation spine (v2.4):
- Start with `specs/gaps/SILENT_SUPPRESSION_GAP.md` (Phase A, spec 1 of 7)
- Follow `specs/gaps/GAP_BUILD_ORDER.md` strictly — dependency order matters
- Every signal emits via `SignalEnvelope` (defined in GAP_BUILD_ORDER.md)

If you're starting 3.x:
- Ship v2.4 first
- Read `specs/core/SELF_GOVERNANCE_SPEC.md`
- Review the 8 hardening items with a human before writing code
