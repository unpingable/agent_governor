# Agent Governor Roadmap

Last updated: 2026-02-16

## Shipped

### Core Kernel
- Evidence gate, receipt chain, claim extraction, custody scoring
- Receipt kernel (hash-chained SQLite, 6 constitutional invariants, redaction, retention)
- Typed claims, FSM lifecycle, fact/decision ledgers with decay
- Operating envelopes (strict/exploratory), pre-commit hooks, MCP server

### Multi-Agent Coordination
- SQLite WAL backend, agent leases, epochs, permissions
- Task dispatcher protocol, quorum consensus, independence scoring
- Sybil resistance (bloc detection, effective voter count)

### Evidence Pipeline
- Provenance tracking, confidence modeling, premise dependencies
- Drift detection, claim diffing, taint similarity, dissent ledger
- TTL enforcement, agent roles, revalidation orchestrator
- Oracle evidence classes (pytest_log)

### Adaptive Control
- Regime detection (ELASTIC/WARM/DUCTILE/UNSTABLE)
- Boil control presets, homeostat with exploration budgets
- Ultrastability (S1 adaptation), failure provenance with scars/shields
- Auto-tuning with Pareto analysis, convergence auto-tuning

### Autonomous Execution
- Spine locking, invariant specs, execution budgets
- Session manager, step-function executor with checkpoint/resume

### Domain Governors
- **Fiction** — Plot threads, canon ledger, manuscript scanning, context drift, consent tracking, narrative guardrails (DSI, AII)
- **Nonfiction** — Corpus management, DOI fetching, citation verification, contextual frame intrusion (12-frame taxonomy)
- **Ops** — Runbook verification, time window enforcement, blast radius limits, precondition chains
- **Writing** — 11 modules: tone vectors, affect regimes, governance visibility, intent classification, structural constraints, ticketing, puppet mode

### Integrations
- [VS Code extension](https://github.com/unpingable/vscode-governor) (V7.0 — preflight, correlator K-vector, capture hysteresis, workspace trust)
- [WebUI + dashboard](https://github.com/unpingable/governor_webui) (FastAPI, chat bridge, interferometry compare, intent compiler modal)
- [Guvnah desktop cockpit](https://github.com/unpingable/guvnah) (Electron, daemon RPC)
- [Maude TUI client](https://github.com/unpingable/maude) (Textual, daemon RPC via Unix socket)
- Governor daemon (JSON-RPC 2.0 over stdio/Unix socket, 36 RPC methods)
- Claude Code hooks, Codex hooks (post-hoc enforcement)
- SDK middleware (drop-in Anthropic SDK wrapper)
- MCP safety controls (rate limiting, backpressure, circuit breaker)
- External constraint attachment (Wikidata/Wikipedia/Scholar)
- Git governance, Perforce governance
- Session continuity (capsule-based, fork/promote)
- Interferometry (multi-model claim comparison, code risk markers)

### Infrastructure
- Structured telemetry (JSONL, cost/performance/convergence analysis)
- Prometheus metrics, telemetry dashboard (Rich TUI)
- Config profiles, context compaction with receipts
- Intent compiler (structured hypothesis-collapse)
- Correlator telemetry (capture detection, K-vector)
- Scope governor (locality-first policy, escalation receipts)
- Semantic stability (perturbation-based conditioning audit)

## Active / Next

### 3.x Self-Governance Architecture
Spec written (`specs/core/SELF_GOVERNANCE_SPEC.md`). Eight hardening items pending human review before building. Core: executor/proposer separation, admissible measurement gating, rollback + hysteresis + dwell. See spec for math tiers and capability discipline model.

### Client Wiring Gaps
Correlator views, scope views, and stability views not yet wired into Guvnah, Maude, or VS Code V7.1+. The daemon exposes the RPC methods; clients need UI.

### Receipt Kernel v2
12 deferred items documented in `specs/gaps/RECEIPT_KERNEL_ROADMAP.md`. Includes cross-store federation, remote attestation, and retention policy UI.

### Problem-Solving Mode
10 items deferred to late v2. See `specs/gaps/PROBLEM_SOLVING_MODE.md`.

### Ethical Hardening
5 enforceable invariants deferred to v3. See `specs/gaps/ETHICAL_HARDENING.md`.

## Not Planned

- **PyPI packaging** — Install from source for now. No distribution pipeline.
- **Obsidian plugin** — Original roadmap item, not pursued.
- **Slack/Discord bot** — Noise kills adoption.
- **GitHub bidirectional sync** — Complexity without clear value.
