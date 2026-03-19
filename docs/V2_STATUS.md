# V2 Status

As of 2.8.0. This document is the boundary between "shipped" and "next."

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

### 2.3.1 — Operator UX + Receipt Infrastructure

Receipt v1 library + bridge. MCP Governor Gateway (Phase 0, Seatbelt v1). Daemon:
receipts_v1 RPC, method introspection (`rpc.list`), mutating gate, response contracts,
`config effective`. CLI: curated help (5 categories, 21 commands), `governor advanced`
attic door, bare invocation rollup ("one finger, one button"), findings-first
doctor/status. Operator surface contract frozen in tests. Stability + lane routing
hardening.

### 2.3.2 — Composition Enforcement + Governed Dispatch

Four phases shipped together. These add **within-task composition governance** — the
daemon evaluates tool-call sequences within a single `correlation_id` and can block
dispatch at the membrane.

**Phase 2A — Policy engine substrate.** Capability taxonomy, obligation vocabulary, pure
evaluator. Policy fragment normalization (IDs-only contract, locked by tests). `policy.*`
daemon RPCs. Evidence gate policy adoption (policy can override kernel verdicts with
receipted justification).

**Phase 2B — Composition detection (detect-only).** Chain gate (`chain_gate.py`): pure-
function composition evaluator over action sequences. ActionStep/ActionLog/ActionLogStore
with content-addressed hashing. CompositionRule matches on capability class × trust domain
× data sensitivity (not tool name patterns). Server-owned annotation (`annotate_step`) —
daemon classifies tools, agents never self-label. Dedupe suppresses repeat receipts.
4 daemon RPCs: `chain.evaluate`, `chain.status`, `chain.rules`, `chain.reset`. 56 module
tests + 12 daemon integration tests.

**Phase 2C — Enforcement ratchet + CAS binding.** Three modes: `detect_only` →
`enforce_shadow` → `enforce`. Preflight/record split: `chain.preflight` (pre-dispatch) +
`chain.record` (post-dispatch). CAS binding token `H(log_hash + step_hash)` prevents
TOCTOU drift between preflight and record. Record idempotency via `record_id`. Operator-
readable block reasons. Decision vs verdict separation (`effective_verdict` = what logic
concludes; `decision` = what runtime does in current mode). Preflight owns dedupe mutation;
record owns step-log mutation. `chain.evaluate` restricted to detect_only (deprecated shim).

**Phase 2D — Governed dispatch membrane.** `governed_dispatch()`: single enforcement
function — if preflight returns "blocked", transport never runs. PreflightClient protocol
(transport-agnostic). DaemonPreflightClient adapter. GovernanceError for membrane failures.
`fail_open` mode for graceful degradation. 38 tests including blocked-preflight receipt
audit proof.

**Scope.** Composition enforcement applies to **tool-dispatch paths** (Claude Code hooks,
Codex hooks, governed executor). Daemon-native chat generation (Maude `chat.send`,
Phosphor chat) remains governed by the daemon's existing inline gating (evidence gate +
violation resolver), not by `governed_dispatch`. This is the Lane A (tool composition) vs
Lane B (LLM generation governance) distinction. Cross-task composition (2E) and rule
learning from receipt corpus (2F) are explicitly out of scope.

**Client integration.** Maude: 3 Pydantic models + 3 RPC methods (chain_preflight,
chain_record, chain_status). Guvnah: 6 TypeScript interfaces + 6 GovernorClient methods +
full IPC stack (channels → handlers → preload → renderer). Both are control surfaces with
chain RPC access, not enforcement points.

**README retune.** Problem shape → capabilities → non-goals → adoption ladder → start here.
Explicit "not an AI firewall or MCP gateway" positioning. Renamed WebUI → Phosphor (app
name; repo URL unchanged).

~12,900 tests, all green.

### 2.4.0 — Instrumentation Spine (see below)

### 2.5.0 — Signal Plane (see below)

---

### 2.4.0 — Instrumentation Spine

Observe-only signal substrate for operators. No gating, no policy changes, no enforcement.
All signals emit via `SignalEnvelope` (23-field frozen dataclass, schema v0.4.0). The
envelope is intentionally isomorphic to the eventual v3 schema — v3 promotes and freezes.

**Phase A — Signal Substrate** (`src/governor/signals/`)

| Module | Signal | What It Does |
|--------|--------|-------------|
| `envelope.py` | SignalEnvelope | Typed envelope: identity, quality semantics, canonical JSON, JSONL emission |
| `emit.py` | SignalEmitter + JsonlSink | O_APPEND + flock emission, deterministic ordering |
| `exposure_proxy.py` | EXPOSURE_PROXY | Weighted denominator from tool dispatch, chat gen, evidence checks |
| `silent_suppression.py` | SILENT_SUPPRESSION | In-path health from multi-source indicators |
| `sigma_rate.py` | SIGMA_RATE | Endorsement→invalidation pair matching with lag statistics |

**Phase B — Reflexive Health** (advisory, warn-only)

| Module | Signal | What It Does |
|--------|--------|-------------|
| `capture_self_diagnostic.py` | CAPTURE_SELF_DIAGNOSTIC | Windowed diagnostic consuming Phase A envelopes. 6 classifications. Suppression precedence. |
| `decision_evidence_lag.py` | DECISION_EVIDENCE_LAG | Per-decision timing from gate receipt pairs. 4 classifications. Backfill rate. |

**Phase C — Make It Measurable** (offline replay + calibration)

| Module | Signal | What It Does |
|--------|--------|-------------|
| `replay_harness.py` | REPLAY_HARNESS | Deterministic offline replay under alternative thresholds. Envelope + receipt modes. |
| `replay_sources.py` | — | Window grouping adapters for replay inputs |
| `calibration_layer.py` | CALIBRATION_LAYER | Apply-only normalization to [0,1]. 3 transforms. Frozen versioned param sets. |
| `calibration_methods.py` | — | Transform functions: identity_clip, linear_minmax, log_minmax |
| `calibration_fitting.py` | CALIBRATION_FITTING | Offline param-set fitting from replay corpus. Deterministic sample extraction. |

**Phase D — Preflight as Lint** (pure prediction)

| Module | Signal | What It Does |
|--------|--------|-------------|
| `predict_regime.py` | PREDICT_REGIME_PREFLIGHT | Weighted heuristic over calibrated A/B envelopes → predicted regime + confidence |

**B3 shipped:** POSTERIOR_SHIFT_ATTRIBUTION (9546b33, fb3a469) — LOO influence
at the A-signal level, 41 tests. Wired into sim→signal pipeline. Follow-ons:
C2 calibration integration, dashboard surfacing, threshold tuning via replay.

**Integration lane shipped (post-2.5):** `governor signals preflight` CLI,
`signals.preflight` daemon RPC, sim pipeline wiring (6 signal kinds). D remains a
pure function — integration is observe-only.

**Test counts:** 908 tests across A0-A3 + B1-B3 + C1-C2 + D. All green.

**Governance abuse audit rubric:** `specs/core/GOVERNANCE_ABUSE_AUDIT.md` — recurring
anti-capture review discipline. 8 abuse paths, 7-question per-feature test, 3-bucket
finding classification. First audit record: Phase D (PASS). Verdict field in gate
receipts hardened from bare string to validated vocabulary (`VALID_VERDICTS`).

**Sim harness:** `sim/governor_sim/` — scenario DSL, InprocRunner, typed trace events.
Currently wired to gate/heartbeat layer. Extension to v2.4 signal pipeline is the next
validation lane.

### 2.5.0 — Signal Plane

The governor can see itself. The v2.4 instrumentation spine (867 tests, observe-only)
is now queryable: persisted JSONL → SQLite projection → CLI + daemon RPC.

**Signal Plane v1** — SignalStore SQLite projection cache over signal JSONL. Byte-offset
cursor with inode/shrink detection, transactional ingest, fcntl.flock write exclusivity.
CLI: `governor signals list|tail|explain|stats|rebuild`. Daemon RPC:
`signals.query|get|tail|stats`. `--poll-ms` enables follow mode. Old claim signal
extraction moved to `governor claim-signals`. 104 tests.

**VERIFY_SUMMARY signal** — First live signal from a gate. One envelope per verifier
suite run. `value = count_block + count_error`. Fail-open: emission failure never blocks
verification.

**SIGNAL_EMIT_FAILED self-diagnostic** — When signal emission fails, a best-effort
diagnostic envelope is written. Queryable:
`governor signals list --name SIGNAL_EMIT_FAILED`.

**Process session identity** — Canonical `gov_{uuid12}` session ID per process. Stable
within a daemon lifetime, fresh per CLI invocation. Threads into signal envelopes and
queries (`--session`). 9 tests.

**Sim→signal pipeline** — Proves the instrumentation spine is connected to blood flow.
One fixture → gate receipts → EXPOSURE_PROXY signal → JSONL → SignalStore → queryable.
Deterministic derivation (emitted_at pinned to window_end) enables INSERT OR IGNORE
dedupe. 15 tests.

**Canonical JSON hardening** — `allow_nan=False` added to `gate_receipt.py` and
`signals/envelope.py`. Prevents NaN/Infinity in canonical serialization. 5 tests.

**Verifier gate foundation** — Composition boundary for mechanical verification. 124
tests. Observe-only, not wired to daemon/CLI.

**Governed activity foundation** — Drift-gated retry substrate. Tiered drift detection
(etag → fingerprint), JSONL store. 110 tests. Observe-only, not wired to daemon/CLI.

**Gap specs** — Operational SLA (two-path availability contracts), Verified Kernel
(canonical JSON audit, K1-K6 normative rules for 3.x), Governed Activities (receipted
side-effect capsules).

~14,200 tests, all green.

### Post-2.5.0 (untagged)

**Signal provenance tightening** — `default_source_versions()` across all signal builders.
`source_receipt_ids` monotonic propagation A→B→C→D. `session_id` in Phase D. 22 tests.

**B3 POSTERIOR_SHIFT_ATTRIBUTION** — LOO influence at the A-signal level. Removes each
Phase A signal, recomputes entire B1, measures delta. Non-conservation by design.
Suppression (A2) always highest influence when present. Wired into sim→signal pipeline
(full A→B chain). 41 tests + 25 sim tests.

**Verified Kernel 2.x Hygiene** — HashRef for cross-module hash comparison (gate_receipt
raw hex vs signals/receipt_kernel sha256:<hex>). Non-canonical `content_hash` renamed to
`dedup_fingerprint` in 4 modules. 25 tests.

**Provenance Labels** (GOV_PRIM_PROV_001) — Lightweight taint tracking for tool outputs.
7 source classes, 4 sensitivity hints, max_sensitivity propagation, LabelAssigner with 19
tool mappings. Wired into evidence gate. 53 tests.

**Egress Gate** (GOV_GAP_EGRESS_001) — Outbound data-flow policy gate. Policy bridge:
classify → evaluate → receipt. PayloadClassifier (monotone: label > path > regex),
DestinationClassifier (URL/IP/hostname, internal detection), 6 rules in explicit
precedence. Receipt redaction (hashes + classes only). 66 tests.

v2.x threat hardening track complete: provenance labels → chain gate → egress gate.

**Phase D Integration Lane** — `governor signals preflight` CLI command (local JSONL
scan, no daemon dependency). `signals.preflight` daemon RPC. Sim pipeline wired (full
A→B→D chain, 6 signal kinds). `load_latest_envelopes()` standalone JSONL loader.

**v2 Bake-In Placeholders** — `principal_ref` on GateReceipt (null in v2, validates
`sha256:<hex>` format). `session` block in `governor.hello` response (principal, auth,
token — all null/local in v2). `signals_preflight` capability flag. `[security]` daemon
config section documented.

~14,560 tests, all green.

### 2.6.0 — CI Lane + Context Manifest

**CI Lane** — Receipt-producing CI wrapper and policy verifier. `ci_wrap()` runs commands
via temp-file capture, emits self-contained `CiReceiptBundle` (evidence inlined).
`ci_verify()` checks policy: required kinds, all-pass, SHA consistency, clean state,
conflicting-ID detection. Closed `ci_kind` vocabulary (8 kinds). Fail-open wrap, fail-closed
verify. CLI: `governor wrap --receipt-out --ci-kind`, `governor ci verify`. GitHub Actions
workflow wired. 43 tests.

**Context Manifest (Phase 1)** — Prompt assembly as governed artifact. Instruments system
prompt builds with three identity kinds: `prompt_hash` (content), `manifest_hash` (structure,
excludes volatile fields), `build_id` (event UUID). Region metadata from lookup table (kind,
source_class, sensitivity, mutability, capabilities). JSONL persistence with fcntl.flock.
Gate receipts: `context_build` (verdict=observe) + `context_build_failed` (verdict=warn,
failure-path artifacting). Golden determinism tests (pinned hashes). Hash-only storage by
default — no bodies in Phase 1. Wired into GovernorHooks._build_system_prompt(). CLI:
`governor context manifest [--json] [--limit N] [--id ID]`. 49 tests.

**Scar Fingerprints** — Action-level novelty gate. `failure_kind` and `action_type` added to
scar fingerprint. Different failure modes in the same region create separate scars with
independent stiffness and evidence lifecycles. Broader scars apply to narrower queries, not
vice versa. Most restrictive scar wins. Full backward compatibility (empty fields = legacy
region-only matching). 161 tests (up from 89).

**Gap specs** — Context manifest phases 2-3 (GOV_GAP_CONTEXT_MANIFEST_001: enforcement,
attestation, body store). Disclosure/standing model (GOV_GAP_DISCLOSURE_STANDING_001:
gradients with cliffs, field classification, contestation protocol, retention classes,
SaaS hardening — 17 invariants + 6 tripwires). CI lane gaps (GOV_GAP_CI_LANE_001). SLSA
alignment (GOV_GAP_SLSA_001).

~14,559 tests (main) + 83 sim tests, all green.

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

**Prerequisite:** The instrumentation spine (v2.4) shipped. 3.x now has calibrated
signals, replay, and prediction available as measurement substrate.

Four gap specs are explicitly 3.x:

| Spec | What |
|------|------|
| CROSS_DOMAIN_SCHEMA_GAP | Public API schema versioning, clock semantics, partition keys |
| PAAS_SHARDING_GAP | Multi-daemon roles, epoch roots, ordering guarantees |
| KAPPA_DIAL_GAP | κ as a measurable policy knob (requires calibration) |
| REGIME_CAPTURE_2D_GAP | Regime + capture on same calibrated scale |

---

## Known-Good Bundle (2.8.0)

| Repo | Version | Coupling |
|------|---------|----------|
| [agent_gov](https://github.com/unpingable/agent_governor) | 2.8.0 | — |
| [maude](https://github.com/unpingable/maude) | 2.4.0 | coupled to governor major, independent minor |
| [vscode-governor](https://github.com/unpingable/vscode-governor) | 2.2.0 | hard (mirrors major.minor) |
| [guvnah](https://github.com/unpingable/guvnah) | 2.3.2 | hard (mirrors major.minor) |
| [gov-webui (Phosphor)](https://github.com/unpingable/governor_webui) | 0.4.0 | loose (targets contract v1) |
| [clerk](https://github.com/unpingable/clerk) | 0.1.0 | dependent (uses agent_gov as backend) |

Note: maude/guvnah are still on 2.3.2. CI lane and context manifest add new CLI
commands and daemon capabilities but don't change existing contracts. Clients don't
need to bump unless they want CI verification or manifest inspection. Clerk is a
desktop assistant ("keeps receipts") targeting normie-friendly onboarding; push-button
install is a roadmap item.

**Sanity check** (run these to verify you're not in version hell):

```bash
governor --version                      # should say 2.8.0
governor status --json | python3 -c "import sys,json; print(json.load(sys.stdin)['schema_version'])"  # should say 1
governor doctor                         # walk 9 subsystems, flag non-nominal
make test                               # in each repo
```

See `docs/VERSIONING.md` for the coupling rules and contract version table.

---

## What To Do Next

If you're returning to this codebase:

1. **Run the tests.** `python3 -m pytest tests/ -v` — ~14,500 tests, all should pass.
2. **Read the gate.** `src/governor/evidence_gate.py` is the enforcement surface.
   Everything else feeds into it or reads from it.
3. **Read the daemon.** `src/governor/daemon.py` is the control plane. 60 RPC methods,
   lazy subsystem init, Unix socket or stdio.
4. **Read the receipts.** `src/governor/gate_receipt.py` (decision receipts) and
   `libs/receipt_kernel/` (audit trail). Content-addressed, hash-chained, append-only.
5. **Read the chain gate.** `src/governor/chain_gate.py` is the composition evaluator.
   Preflight/record split, enforcement ratchet, CAS binding.
6. **Read the signals.** `src/governor/signals/` is the v2.4 instrumentation spine.
   Pure derivation, observe-only, typed envelopes. `predict_regime.py` is the capstone.

If you're extending the instrumentation spine:
- Spec files: `specs/gaps/V2_4{A,B,C,D}_*.md` — implementation contracts per phase
- `GAP_BUILD_ORDER.md` defines `SignalEnvelope` schema + cross-cutting contracts
- B3 (posterior shift attribution) shipped — LOO influence, 41 tests, sim wired
- D integration lane shipped — `governor signals preflight`, `signals.preflight` RPC, sim pipeline

If you're starting 3.x:
- v2.4 shipped — calibrated signals, replay, and prediction are available
- Read `specs/core/SELF_GOVERNANCE_SPEC.md`
- Review the 8 hardening items with a human before writing code
