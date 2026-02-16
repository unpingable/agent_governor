# Receipt Kernel Roadmap

## Purpose

This document captures what we're building, what we're deferring, and why.
It exists so architectural decisions don't get lost between sessions.

status: canonical

---

## What's Being Built NOW (v0.1 — `libs/receipt_kernel/`)

### A) Redaction Hook + Retention Policy
- Pre-write redaction in `put_blob()` using pattern-based secret detection
- Two evidence classes: `public` (retained longer) and `sealed` (aggressively expired)
- `RetentionPolicy` as data: TTLs per blob class, hash-only retention after expiry
- `BLOB_EXPIRE` event when transitioning state (purge is itself receipted)
- Blob states: `LIVE → EXPIRED_HASH_ONLY → PURGED`

### B) Event Envelope v1 (Hash-Chained)
- Stable envelope schema with 12 fields
- `prev_event_hash` continuity (tamper-evident within trust boundary)
- 7 event types: `RUN_START`, `STAGE_ADVANCE`, `EVIDENCE_PUT`, `EVALUATION`, `DECISION`, `REMEDIATION`, `RUN_FINALIZE`
- Canonical JSON serialization (sorted keys, compact separators, ASCII-safe)

### C) SQLite Receipt Store
- Append-only (no UPDATE/DELETE, enforced by triggers)
- Hash chain verification (`verify_run_chain()`)
- Contiguous seq enforcement per run
- Blob storage with content addressing and retention state

### D) StageGraph
- Explicit stage definitions with allowed transitions
- Illegal transitions are hard errors (not warnings)
- Default graph: `START → COLLECT → EVALUATE → DECIDE → FINALIZE`

### E) 6 Constitutional Invariants
- `ledger.chain_valid` — hash chain verification (seq contiguity, prev_hash continuity, event_hash integrity)
- `receipt.completeness` — required evidence keys present, blobs retrievable
- `evaluation.completeness` — attested evaluation with no silent downgrade
- `finalization.completeness` — no invisible endings, decision ref required
- `run.single_finalize` — exactly one RUN_FINALIZE per run
- `run.stage_required_path` — required stages appear in order

### F) Bridge Adapter
- `src/governor/adapters/receipt_kernel_bridge.py`
- Emit events in parallel with existing JSONL receipts
- No refactor of existing paths — additive only

---

## What's Deferred (with reasoning)

### 1. External Anchoring (Tamper-Resistant)
**What**: Anchor hashes outside the DB (e.g., append-only remote log, signed timestamps)
**Why deferred**: Hash chain gives tamper-evidence within trust boundary. External anchoring adds cross-boundary tamper-resistance but requires external infrastructure.
**When**: 3.x — when multi-tenancy makes trust boundaries matter
**Gap risk**: Low. Single-operator deployment doesn't need cross-boundary proofs yet.

### 2. Bounded Remediation Runner
**What**: Automated remediation actions with preconditions, apply, rollback, budget
**Why deferred**: Current `violation_resolver.py` handles interactive fix/revise/proceed. Automated remediation needs the event envelope to receipt its own actions.
**When**: After envelope is stable — remediation events need `REMEDIATION` event type
**Gap risk**: Medium. Manual remediation works but doesn't scale.
**Depends on**: Event envelope (building now), policy profiles

### 3. Multi-Tenancy Enforcement
**What**: Full tenant isolation (not just `tenant_id` field in receipts)
**Why deferred**: Current deployment is single-operator. Fields exist in GateReceipt for future use.
**When**: 3.x — when the daemon serves multiple isolated principals
**Gap risk**: Low for current use cases.

### 4. Regression Farming (FAIL → Test Vectors)
**What**: Convert failed runs into replayable test fixtures automatically
**Why deferred**: Needs stable event envelope + enough real failure data to be useful
**When**: After 10+ real FAIL runs are recorded with the new envelope
**Gap risk**: Medium. Currently scars.py remembers failures but doesn't replay them.
**Depends on**: Event envelope, receipt store

### 5. Cost Governance as Native Evidence
**What**: Attach cost/latency as evidence; invariants can enforce budgets
**Why deferred**: Telemetry module already tracks costs. Wiring it as evidence in the kernel is incremental.
**When**: Shortly after envelope ships — small integration task
**Gap risk**: Low. Cost data exists, just not receipted.

### 6. Storage Compression Tiers
**What**: Compress blobs after M days, archive after N days
**Why deferred**: Retention policy (building now) handles TTL and hash-only. Compression is optimization.
**When**: When blob storage exceeds ~1GB
**Gap risk**: Low. Delete is more important than compress at current scale.

### 7. Multi-Writer Concurrency
**What**: Multiple appenders per run with sequencing authority
**Why deferred**: Explicitly NOT in 2.x. Single writer per run is correct for current architecture.
**When**: 3.x if multi-agent runs need shared event streams (unlikely — prefer per-agent runs)
**Gap risk**: None. Per-run leases already exist in storage.py.

### 8. Receipt-Kernel Extraction to Separate Repo
**What**: Move `libs/receipt_kernel/` to its own GitHub repo and publish
**Why deferred**: Extract-first (in-repo) lets us iterate without premature API surface decisions
**When**: When the interface stabilizes and a second consumer (beyond agent_gov) exists
**Gap risk**: None. In-repo extraction gives the same module boundary.

### 9. Replay Tiers
**What**: Three tiers of replay fidelity:
  - Tier A: Re-run invariants against stored events (cheapest)
  - Tier B: Reproduce tool/model calls (needs sealed evidence)
  - Tier C: Deterministic outputs (needs temperature=0 + seed pinning)
**Why deferred**: Tier A falls out of the envelope naturally. B and C need tool trace capture design.
**When**: After event envelope is stable and we have real runs to replay
**Gap risk**: Medium for B/C. Tier A is essentially free with the current design.

### 10. Policy Distribution
**What**: Central policy server pushing profiles to edge governors
**Why deferred**: Single-operator deployment. Profiles are local files.
**When**: 3.x — when multi-site deployment exists
**Gap risk**: None for current scale.

### 11. Freeze-to-Test Pipeline
**What**: Take a running governor, freeze its state, and spin up a test harness against the frozen snapshot
**Why deferred**: Needs stable serialization of all governor state (partially exists via viewmodel.py)
**When**: After receipt kernel stabilizes — useful for CI integration
**Gap risk**: Low. Manual testing works for now.

### 12. Remediation Budget Model
**What**: Max retries, allowed actions, max cost/time, quarantine-after-N-failures
**Why deferred**: Coupled with bounded remediation runner (#2)
**When**: Same timeline as remediation runner
**Gap risk**: Same as #2. Manual remediation doesn't need budgets.

### 13. External Anchoring (Minimal, Non-Infrastructure)
**What**: Write head hash to a second location: `anchors/<run_id>.json` with `{run_id, ts, head_event_hash, policy_id}`. Optional `anchor.matches_head` invariant.
**Why deferred**: Hash chain gives tamper-evidence within trust boundary. External anchor adds tamper-resistance without requiring external services. Minimal: just a second file.
**When**: After envelope is stable. Small addition.
**Gap risk**: Low-medium. Single-operator doesn't need cross-boundary proofs yet, but this is cheap insurance.

### 14. Executor Swap Topology (Kernel/Executor Split)
**What**: Split daemon into kernel (stable: receipts, routing, stage legality) vs executors (replaceable: policy eval, model calls, scoring). Executors run as separate processes, kernel routes by capabilities. Live update = start new worker, route new jobs, drain old workers.
**Why deferred**: Current daemon is monolithic. Split requires protocol definition and process management.
**When**: 3.0 — after receipt kernel proves the boundary. 2.x prep: add `executor_build_id`, `executor_api_version`, `capabilities_used` to stage results.
**Gap risk**: Low for current single-process deployment. Medium for production multi-agent.
**Design constraints**:
  - Upgrade at stage boundaries only (stage graph = quiescence mechanism)
  - State lives in receipts, not RAM (replay from store, don't migrate)
  - No importlib.reload — process replacement, not code patching
  - Daemon options: systemd socket activation (cleanest), supervisor+child, SO_REUSEPORT

### 15. Gating Flip (Parallel → Enforcement)
**What**: CLI "success" requires receipt + evaluation + finalization completeness PASS, or else UNKNOWN/FAIL. Remediation/autopilot requires the quartet PASS. Currently receipt kernel runs in parallel (additive audit trail).
**Why deferred**: Need confidence the kernel doesn't false-positive before gating.
**When**: After 20+ real runs pass without false invariant failures.
**Gap risk**: Medium. Without this, the kernel is advisory (same thing we built the governor to prevent).

### 16. `governor receipt verify` CLI Command
**What**: `governor receipt verify --run <id>` — runs the 6 invariants, prints single-line verdict + pointers. Makes the kernel touchable without full integration.
**Why deferred**: Kernel needs to be wired first. Small feature.
**When**: Shortly after bridge is wired to a real workflow.
**Gap risk**: Low. Invariants can be run programmatically today.

---

## Design Constraints (Non-Negotiable)

These are not deferred — they're permanent guardrails:

1. **No daemons, schedulers, watchers, reconciliation loops** in the kernel
2. **No universal object model / remote protocol** (no Plan9 creep)
3. **No dynamic plugin marketplace** — invariants are code modules, not remote discovery
4. **No auth/tenancy/cost platform in v0** — wrappers add later
5. **No LLM / tool runner abstractions in the kernel** — adapters do that
6. **Profiles are data, invariants are code** — never the reverse
7. **Availability is not correctness** — a green status with missing evidence is a lie

---

## Build Order

```
DONE: redaction + retention + envelope + store + invariants + bridge + BLOB_EXPIRE events
      + silent-green prevention (KernelStatus, verdict_ceiling)
      + redaction proof tests (secret not in DB, not in report)
NEXT: wire bridge to one real workflow (evidence_gate or daemon chat)
      + governor receipt verify CLI command
      + external anchoring (minimal anchor file)
THEN: gating flip (parallel → enforcement), remediation runner, cost evidence
LATER: regression farming, replay tiers, executor swap prep (build_id in envelopes)
3.x:  full executor split, multi-tenancy, policy distribution
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-15 | Initial roadmap. Redaction + retention + envelope as first build. |
