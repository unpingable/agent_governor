# Changelog

## Unreleased

**Theme:** the governor can see itself. Signal Plane v1 wires the v2.4
instrumentation spine (867 tests, observe-only) into a queryable surface:
persisted JSONL → SQLite projection → CLI + daemon RPC. Verifier gate emits
VERIFY_SUMMARY signals; emission failures are self-diagnosed via
SIGNAL_EMIT_FAILED. Process-scoped session identity enables per-run
correlation. Operational SLA gap spec lays groundwork for 3.x self-monitoring.

### Signal Plane v1

SQLite projection cache over signal JSONL. Byte-offset cursor with
inode/shrink detection, transactional ingest, fcntl.flock write exclusivity.
CLI: `governor signals list|tail|explain|stats|rebuild`. Daemon RPC:
`signals.query|get|tail|stats`. `--poll-ms` enables follow mode:

```bash
governor signals tail --name VERIFY_SUMMARY --poll-ms 1000
governor signals tail --name SIGNAL_EMIT_FAILED --poll-ms 1000
```

Old claim signal extraction moved to `governor claim-signals`.

### VERIFY_SUMMARY Signal

First live signal from a gate. One envelope per verifier suite run.
`value = count_block + count_error`. Timing fragment, source receipt IDs,
quality semantics (ok/partial/unavailable). Fail-open: emission failure
never blocks verification.

### SIGNAL_EMIT_FAILED Self-Diagnostic

When signal emission fails, a best-effort diagnostic envelope is written to
the same JSONL. No recursion — bypasses `emit()` directly. Queryable in the
same plane: `governor signals list --name SIGNAL_EMIT_FAILED`.

### Process Session Identity

Canonical `gov_{uuid12}` session ID per process. Stable within a daemon
lifetime, fresh per CLI invocation. Exposed in `governor.hello` RPC response.
Threads into SIGNAL_EMIT_FAILED envelopes and signal queries (`--session`).

### Operational SLA (Gap Spec)

Two-path availability contracts: decision path (fast, fail-closed/open) vs
evidence path (slower, debt receipts). Per-lane SLO routing. Timing fragment
on gate receipts (`make_timing` with monotonic_ns). See
`specs/gaps/OPERATIONAL_SLA.md`.

### Verifier Gate + Governed Activities

Composition boundary for mechanical verification (124 tests). Drift-gated
retry substrate (110 tests). Both observe-only, not wired to daemon/CLI.

---

## v2.3.1 — 2026-02-19

**Theme:** operator UX. The CLI now has a front door instead of a fire hose.

### Receipt v1 Library + Bridge

Standalone receipt library (`libs/receipt_v1/`): schema, types, builder, 5 sink
backends, verifier with 10 golden examples. Bridge module dual-emits receipt_v1
alongside gate_receipt. ReceiptStore abstraction with JSONL rotation.

### MCP Governor Gateway (Phase 0)

Policy-enforcing MCP proxy (`libs/mcp_governor/`): StdioGateway, PolicyEngine
(allow/deny/allow-warn from denylist regex), ReceiptEmitter with hash-chained
FileSink. 78 tests. Seatbelt v1 shipped: 3 demo configs, echo server.

### Daemon: receipts_v1 RPC + introspection

5 new RPC endpoints for receipt queries (`receipts_v1.*`). Method introspection
(`rpc.list` with classification), mutating gate (rejects writes without both
locks), response contracts. `governor rpc` escape hatch for raw daemon calls.
`governor config effective` shows resolved config with provenance.

### CLI: operator UX rewrite

- **Curated help**: `governor --help` shows 5 categories (21 commands), not 117.
  Everything else lives under `governor advanced --help`.
- **`governor` (bare)**: one-line state + top findings + one next command.
  Built on StatusRollup, not persona-specific code.
- **`governor status`**: findings-first operator dashboard (not BIOS listing).
- **`governor doctor`**: walks 9 subsystems, surfaces non-nominal, suggests
  next commands. `--strict` for CI (exit 1 on warnings).
- **Operator surface contract**: frozen in tests. Categories, curated commands,
  and advanced group existence are asserted. Prevents entropy.

### Stability + Lane Routing Hardening

Glass cannon detection (worst-case perturbation + margin-to-cap). 4 stability
transforms (relocate, repeat, rewrap, distract). Probe-vs-mitigation policy.
Lane routing: dt-aware EMA, regime→risk_class coupling, cooldown store,
capability-based model selection, LLM telemetry for autopilot level 2.

### Versioned Interfaces

| Interface | Version | Change |
|-----------|---------|--------|
| Daemon protocol | 1.0 | +5 receipts_v1 methods, +rpc.list, +config.effective |
| Receipt schema | 2 | No change |
| Receipt v1 schema | 1 | New |
| MCP gateway | 0.1 | New |

---

## v2.0.0 — 2026-02-10

**Status:** milestone release. Public interfaces are intended to be stable, but
implementation and module layout may continue to evolve. The daemon protocol,
receipt schema, and ViewModel schema are versioned; incompatible changes will
increment the version number.

### Governor Daemon

JSON-RPC 2.0 control plane over stdio or Unix socket. 36 RPC methods across 11
namespaces (governor, sessions, intent, receipts, scars, correlator, scope,
stability, commit, chat).
Content-Length framing. Config file support (`daemon.conf`). Backend
auto-detection (Anthropic, Ollama, Claude CLI, Codex CLI). Streaming via
`chat.delta` notifications.

All three clients (Maude, Guvnah, gov-webui) now talk to the daemon. Gov-webui
delegates chat through the daemon via Unix socket RPC (split-brain fix).

### Gate Receipt System

Content-addressed decision receipts for all governor gates. Receipt ID =
`H(schema_version + gate + subject_hash + evidence_hash + policy_hash)`.
Split store: ReceiptStore (JSONL) + EvidenceStore (content-addressed blobs).
All gates wired: evidence_gate, intent_compiler, pre_commit, wrapper,
continuity_checker.

### AG2 Instrument + Control Layers (26 specs)

Full AG2 build: control theory module (R_t = PD/E), slim mode, constraint
compiler, detector integration, commitment transport, spectral stability,
scalar collapse detection, CLI chat, evidence gate rename, document governance,
dashboard UX, WebUI demo system. Plus 12 hardening specs: admissibility gate,
coverage metrics, phase control, measurement integrity, deployment profiles,
risk potential, coherence budget, mode detection, evasion detection, hysteresis,
quorum extensions, temporal attack surface scanner.

### Intent Compiler

Structured hypothesis-collapse for governance sessions. 3 built-in templates,
mode-gated form policy, deterministic compilation with receipt emission.
WebUI modal overlay with dynamic form rendering.

### V2 Hardening

Receipt schema v2: principal_id, tenant_id, auth_method fields.
Exception-receipt linking, selfcheck provenance. VM deployment with systemd
services, Caddy reverse proxy, secrets management.

### Breaking Changes

- WebUI extracted to separate repo (`gov-webui`). No longer ships in
  `src/webui/`.
- `maude_lite` module renamed to `evidence_gate` (NLAI violation in naming).
- All "maude" naming excised from agent_gov codebase.
- Governor daemon is now required for chat (direct ChatBridge use bypasses
  governance pipeline).

### Versioned Interfaces

| Interface | Version | Location |
|-----------|---------|----------|
| Daemon protocol | 1.0 | `daemon.py:PROTOCOL_VERSION` |
| Receipt schema | 2 | `gate_receipt.py:RECEIPT_SCHEMA_VERSION` |
| ViewModel schema | v2 | `viewmodel.py:SCHEMA_VERSION` |

### Migration

No supported upgrade path from 1.x. Treat as clean install. Key differences:
- `src/webui/` no longer exists; use `gov-webui` repo
- `governor serve` must be running for chat via any client
- `GOVERNOR_SOCKET` or `XDG_RUNTIME_DIR` needed for socket resolution

---

## v1.1.0 — 2026-02-09

Naming cleanup, spec expansion, and documentation overhaul.

### Naming

Excised all "maude" references from agent_gov. The governor is the canonical
name; client apps (Maude, Guvnah, gov-webui) are presentation layers.
Backported rename to main branch.

### Specs

- Added 12 AG2 2.1 hardening specs (admissibility gate through temporal scanner)
- Added 3.0 self-governance spec (executor/proposer separation, dual ledger)
- Added AG2 build order with full dependency graph (14 gap specs sequenced)
- Added control theory spec (R_t = PD/E — the Governor as Reynolds number)

### Documentation

- README overhaul: Mermaid architecture diagram, failure modes section, demos
- Added CONTRIBUTING.md and HISTORY_BOUNDARY.md
- Docs reference audit across all specs

---

## v1.0.1 — 2026-02-06

Fix: resolves hanging tests in CI (MCP safety controls deadlock).

---

## v1.0.0 — 2026-02-05

Feature-complete governance engine. 8141 tests, 21 canonical specs, full CLI.
Core: claims, receipts, ledgers, FSM, verification, multi-agent coordination.
Modes: code, fiction, nonfiction, ops. WebUI, VS Code extension, MCP server.
