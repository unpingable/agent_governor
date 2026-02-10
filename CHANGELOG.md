# Changelog

## v2.0.0 — 2026-02-10

**Status:** milestone release. Public interfaces are intended to be stable, but
implementation and module layout may continue to evolve. The daemon protocol,
receipt schema, and ViewModel schema are versioned; incompatible changes will
increment the version number.

### Governor Daemon

JSON-RPC 2.0 control plane over stdio or Unix socket. 25 RPC methods across 7
namespaces (governor, sessions, intent, receipts, scars, commit, chat).
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
