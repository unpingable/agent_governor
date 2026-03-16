# MCP Governor Gateway — Gap Spec

## What This Is

A thin governance proxy that sits between any MCP client (agent runtime) and
any MCP tool server, enforcing policy and emitting Receipt v1 records for
every tool invocation.

**Depends on:** Receipt v1 schema (`libs/receipt_v1/`).

**Design principle:** The gateway does not know or care what agent runtime is
calling it. It speaks MCP on both sides. It interposes policy enforcement and
receipt emission at the tool call boundary. The agent sees "MCP tool server."
The tool server sees "MCP client." The governor sits in between and makes
every transition auditable.

```
  Agent Runtime          Governor Gateway           Tool Server
  (any MCP client)       (policy + receipts)        (any MCP server)
       |                       |                         |
       |--- tools/call ------->|                         |
       |                       |-- policy check          |
       |                       |   (allow/deny/transform)|
       |                       |                         |
       |                       |--- tools/call --------->| (if allowed)
       |                       |<-- result --------------|
       |                       |                         |
       |                       |-- emit receipt -------->| (to sink)
       |                       |-- receipt durable? ---->| (block until yes)
       |<-- result ------------|                         |
```

**Non-goals:** This is not a new protocol. It is not a framework. It is a
proxy that adds governance to an existing protocol boundary. If MCP dies
and something else wins, the gateway pattern stays the same — only the
transport adapter changes. The receipt schema is the invariant.

---

## Phase 0: Proof-of-Life — SHIPPED

**Status:** Implemented in `libs/mcp_governor/`. 78 tests, all green.

**What it proves:** "I can sit in the middle and emit receipts."

### Delivered

- `StdioGateway`: full MCP proxy (initialize → tools/list → tools/call)
- `PolicyEngine`: allow/deny/allow-warn from denylist regex
- `ReceiptEmitter`: wraps ReceiptBuilder + FileSink + ReceiptChain
- Newline-delimited JSON-RPC framing (per MCP stdio spec)
- 4 reason codes: `gov.policy_allow`, `gov.passthrough`, `gov.policy_deny`, `gov.default_deny`
- Receipt on critical path (fail-closed)
- `tools/list` filtering (denied tools never shown to client)
- `ext.gov.mcp.*` namespacing (client/server identity, protocol version, command hash)
- `call_id = str(id)` (handles int/string/null JSON-RPC ids)
- Secret scanning: keys-only args_summary, sanitized error (single-line, 256 chars, scrubbed)
- No `result_hash` (conservative — tool results may contain secrets)
- `effects_confidence = "none"` (gateway doesn't know what tools do)
- Child process hygiene (SIGTERM → timeout → SIGKILL, stderr drained)
- TOML config via stdlib `tomllib`
- 3 demo configs + echo server + 3 demo shell scripts
- Every receipt passes `receipt_v1.verify()` and chains pass `verify_chain()`

### Files

```
libs/mcp_governor/
├── pyproject.toml
├── py.typed
├── config/
│   ├── demo_allow.toml
│   ├── demo_deny_shell.toml
│   └── demo_passthrough.toml
├── src/mcp_governor/
│   ├── __init__.py
│   ├── types.py            # ToolCallEnvelope, PolicyDecision, ActorInfo
│   ├── policy.py           # PolicyEngine: allow/deny from denylist regex
│   ├── config.py           # GatewayConfig: TOML loader
│   ├── framing.py          # Newline-delimited JSON-RPC
│   ├── gateway.py          # StdioGateway: proxy loop + lifecycle
│   ├── receipt_emitter.py  # ReceiptEmitter: ReceiptBuilder + FileSink + chain
│   └── __main__.py         # python -m mcp_governor config.toml
├── demos/
│   ├── echo_server.py      # Trivial MCP server (3 tools)
│   ├── demo_allow.sh
│   ├── demo_deny.sh
│   └── demo_passthrough.sh
└── tests/                  # 78 tests
    ├── conftest.py
    ├── test_types.py
    ├── test_policy.py
    ├── test_config.py
    ├── test_framing.py
    ├── test_gateway.py
    ├── test_receipt_emitter.py
    └── test_demos.py
```

---

## Primacy Invariants

Two rules that prevent the gateway from accidentally becoming a second brain:

### 1. Single policy brain

The gateway never invents governance semantics. It only:
1. Turns protocol events into an internal envelope
2. Calls the governor policy engine
3. Enforces the verdict
4. Emits receipts

This keeps "policy" from forking into two places. Phase 0's `PolicyEngine` (denylist regex) is a bootstrap shim — it lives in the gateway because the governor policy interface isn't wired yet. As that interface stabilizes, the gateway's policy layer becomes a thin caller, not a decision-maker.

When someone asks "why was this denied," the answer points to governor policy provenance, not gateway regexes.

### 2. Receipt format is downstream of governor, not gateway

Receipt v1 stays the shared evidence layer; the governor owns meaning. The gateway just writes what the governor decided. The gateway never defines new receipt fields or reason codes that aren't rooted in governor semantics.

### Practical consequences

- Gateway stays small and replaceable (MCP today, something else tomorrow).
- "Enterprise choke point" becomes a scaling story of the same governor primitives, not a new product with new semantics.
- The gateway can be useful without ever becoming the center of gravity.

---

## Seatbelt v1 — SHIPPED

**Status:** Implemented. Phase 0 + hardening + read-side store + versioned RPC.

Phase 0 plus the minimum stuff that prevents it from looking like a toy.
This is the "local seatbelt" — gets real users without promising enterprise anything.

### Must have (all done)

- [x] **Interposition works:** gateway sits between client and tool server (stdio) and reliably proxies `initialize → tools/list → tools/call`.
- [x] **Receipts always emitted for `tools/call`:** JSONL, chained, verifiable (`verify-chain` passes) with sane defaults (no args/results leaked).
- [x] **Tool visibility control:** `tools/list` filtering so denied tools never appear to the client.
- [x] **Policy v0:** allow-all-warn + denylist regex (explicit reason codes for "default allow" vs "explicit deny").
- [x] **Operational hygiene:** stdout is *only* protocol; logs to stderr; upstream child lifecycle handled (kill on exit, no deadlocks).
- [x] **Safety hygiene:** receipt file is `0600`, rotation exists (size-based), and summary/error strings are single-line + capped.

### Must not have

- **No enterprise theater:** no "foundation," no registry, no dashboards, no SIEM integrations, no promises about compliance.
- **No remote transport yet:** no Streamable HTTP, no auth/OAuth, no multi-tenant identity.
- **No result hashing by default:** omit `result_hash` unless you have a sanitized channel.
- **No smart policy language:** no DSL, no complex transforms, no escalation workflows.

### Nice-to-have (but optional)

- Minimal transforms that are mechanically safe: timeout injection, path clamping.
- A tiny CLI wrapper around verify (`mcp-gov verify receipts.jsonl`), but not required if library verify is easy.

### Seatbelt v1 Delta

- [x] Receipt file permissions: `RotatingFileSink` creates with `0o600` from the start, warns if existing file is too open
- [x] Receipt file rotation: size-based (default 10 MB, keep 5 files), no day-based complexity
- [x] Hardening doc: `HARDENING.md` — stdout/stderr rule, bypass patterns, env var leaks, debug dumps, child process hygiene, policy shim disclaimer
- [x] ReceiptStore read abstraction: `JsonlStore` with `iter_receipts(session_id, since, limit)`, `get_receipt(receipt_id)`, `verify_chain(session_id)`. Handles rotation transparently.
- [x] Daemon RPC versioning: `receipts_v1.{list,detail,verify}` endpoints independent from legacy `receipts.*`. `since` is `timestamp_wall` (ISO 8601 UTC, lexicographic >=). Verify returns structured errors, chain metadata (`count`, `first_receipt_id`, `last_receipt_id`, `gaps`).

---

## Roadmap

After Phase 0 you're at a fork: **demoable proxy** vs **real governance choke point**. Phase 0 proves "I can sit in the middle and emit receipts." Everything after is about making that middle *non-toy* without turning it into a framework.

### Phase 1: Make it operationally real (still small)

Theme: **more coverage at the boundary**, not more ideology.

- [ ] **Multi-upstream + namespacing**
  The first unavoidable "product" decision. Stable tool IDs across servers: `server_id.tool` or `(server_id, tool)` with stamping in `ext`. Phase 0 already has `server_id = "upstream"` internally — expose and stabilize it.

- [ ] **Transform support (tighten-without-breaking)**
  Not fancy rewrites. Just the boring safety ones: inject timeouts, clamp paths, strip network, cap bytes. Crucially: record both hashes (`args_hash` + `transformed_args_hash`).

- [ ] **Budget enforcement**
  Rate / retries / cost units. This becomes the "seatbelt you can feel." Cost can be fake units initially.

- [ ] **Tool metadata packs** (operator-supplied, not marketplace)
  Minimal risk tags / declared side-effect classes so receipts get meaningful `side_effects` without instrumenting every tool.

- [ ] **Verification CLI** (even a tiny one)
  `verify` and `verify-chain` as a stable operator move. Doesn't need dashboards.

**Stop point:** once multi-server + transform + budgets exist, you've got something security teams can pilot.

### Phase 2: Make it adoptable in messy reality

Theme: **deployment and bypass resistance**.

- [ ] **Streamable HTTP transport** (remote tool servers)
  This is where auth, origin validation, localhost binding patterns, and "don't get DNS-rebound" come in.

- [ ] **Identity / tenancy**
  Multiple clients, per-agent capability sets, per-session chains. If you don't do this, it stays "local dev proxy." Which is fine.

- [ ] **Non-bypassable deployment patterns**
  - local: gateway spawns tools (already done in Phase 0)
  - remote: tools bind localhost / mTLS / origin validation

- [ ] **Operational surface**
  - structured logs to stderr (no stdout contamination)
  - metrics (even minimal counters)
  - sane shutdown + child process supervision
  - backpressure/timeout handling that doesn't deadlock

- [ ] **Better sinks**
  Syslog/OCSF mapping, SIEM-friendly structure, rotation, compression. Unsexy. Necessary.

**Stop point:** once HTTP + tenancy exists, it can live in enterprises without hand-holding.

### Phase 3: Ecosystem play (optional, high politics)

Theme: **make others copy the contract**.

- [ ] **Policy as an artifact**
  Versioned policy bundles, signed policies (optional at first), reproducible policy evaluation (same inputs → same decision).

- [ ] **Receipts as evidence**
  Signing becomes real (key mgmt story), chain anchoring / export to SIEM.

- [ ] **Receipt v1 adoption beyond your code**
  TS emitter, conformance vectors, "if you emit this, you're compatible."

- [ ] **Integration surfaces**
  OCSF/CEF mapping (not dual-format receipts; just export), rotation/retention knobs, deployment packaging (container/systemd).

- [ ] **Conformance tests**
  "This gateway implements Receipt v1 correctly" — test suite others can run. This is where the canonical vectors pay off.

- [ ] **Governance of the spec**
  Only if you actually have adopters. Otherwise it's paperwork cosplay.

**Stop point:** if nobody copies the receipt format, don't build a foundation to host your solitude.

---

## Strategic Framing

### What you're building

Not "another agent framework." It's: **turn the tool boundary into an enforceable, portable audit surface** that survives whatever runtime wins.

- Phase 0 is the proof-of-life.
- Phase 1 is "this can prevent incidents."
- Phase 2 is "this can be deployed."
- Phase 3 is "this can outlive you."

Phase 0's value is mostly narrative + demo gravity; Phase 1 is where it starts paying rent.

### The key constraint

**Don't let "sniffing around" drag you into Phase 3 promises.** Seatbelt buyers want: "does it work, can I install it, can I see what happened." Enterprise buyers want: "who is the actor, can I enforce policy centrally, can I prove this in an audit." Different worlds. Same receipt format.

### One strategic move that makes the whole arc easier

Treat the gateway like an **adapter chassis**:
- Receipt v1 stays stable.
- Policy engine evolves.
- MCP transport is just "adapter 1." (If MCP shifts, you swap adapters, not the governance core.)

That keeps you from marrying the protocol.

---

## Architecture

### The protocol/ Seam

The gateway defines internal types (`ToolCallEnvelope`, `PolicyDecision`) that are MCP-independent. The gateway converts MCP messages into these internal types, runs policy against them, and converts back. This seam prevents MCP from infecting the core policy engine.

If MCP is replaced by a future protocol, only the transport layer changes. The policy engine and receipt emitter never see MCP types.

### Identity & Trust Model

**stdio mode (Phase 0, single-tenant):**
- Identity = whoever launched the gateway process.
- `actor.agent_id` configured statically or from `initialize` clientInfo.
- `actor.auth_context` = `"stdio"`
- No authentication. Trust is implicit in process ownership.

**Streamable HTTP mode (Phase 2, multi-tenant):**
- Identity comes from the transport auth layer.
- Gateway terminates authentication — it is the MCP server from the agent's perspective.
- Auth mechanism: OAuth 2.1 client credentials or bearer token.
- Gateway does NOT pass auth through to upstream tool servers.

### Tool Namespacing (Phase 1)

When aggregating tools from multiple upstream servers:
```
Upstream server "filesystem" exposes: read_file, write_file
Upstream server "s3" exposes: read_file, write_file

Agent sees:
  filesystem::read_file
  filesystem::write_file
  s3::read_file
  s3::write_file
```

Single-server mode (Phase 0): tools exposed with native names.

### Receipt Durability

Receipt write is on the critical path. Tool results are returned to the agent only AFTER the receipt is durably written. If sink fails, the tool call result is NOT returned (fail-closed).

### Tool List Filtering

The gateway doesn't just gate calls — it filters the tool list itself. An agent that lacks capability for shell tools never sees shell tools in `tools/list`. This prevents the agent from even *planning* to use tools it can't access.

---

## Open Questions

1. **MCP protocol version pin:** MCP is still evolving. Pin gateway to a specific protocol version and document which features are used. Phase 0 passes through the negotiated version.

2. **Multi-server tool ID format:** `server::tool` vs `server.tool` vs structured tuple. Pick one before Phase 1 and never change it.

3. **Transform expressiveness:** Phase 1 transforms should be mechanical (timeout injection, path clamping). Don't build a transform DSL. If transforms need to be complex, that's a signal the policy is wrong.

4. **Budget units:** What's a "cost unit"? Start with fake units (tool call count), upgrade to real cost models only when needed.

5. **Relationship to agent_gov:** The MCP gateway reuses Receipt v1 directly. It does NOT import from `src/governor/`. It's a standalone library that happens to share the receipt format. This is intentional — the gateway should work without the governor installed.

6. **What if MCP loses?** The `protocol/` seam means the core (policy engine, receipt emitter) is transport-independent. Write a new adapter. Everything else stays.

---

## Cross-Cutting Governance Contracts

Two principles that apply beyond the MCP gateway but must be enforced here first:

### Renderer side-effect contract

Rendering that triggers network fetch or external resource resolution is a tool call and must be mediated by egress policy (or disabled by default). Document preview, markdown image fetch, and font/stylesheet resolution are not passive — they are covert egress channels. Clients must surface these as egress attempts; receipts must include implicit side effects. (Ref: CVE-2026-26144, Excel preview + Copilot exfiltration chain.)

### Composition gating is cross-layer

Composition hazards are not MCP-specific; any pipeline where tool output becomes tool input requires provenance-aware validation and composed-capability policy. The gateway enforces this at the tool boundary, but the same principle applies to RAG ingestion → prompt assembly, serialization/deserialization paths, and any cross-boundary data flow where one component's output becomes another's trusted input. (Ref: CVE-2026-27825, MCP Atlassian RCE; LangChain serialization injection.)
