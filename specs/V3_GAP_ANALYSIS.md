# V3 Gap Analysis: What's Missing, What's Foundational

## Executive Summary

v2 is strong on foundations. Receipt system is content-addressed. Regime
detection is observable. Storage is transactional. Evidence gating catches
hallucinations. **No blockers exist** — all v3 gaps are additive.

v3 platform work breaks into three tiers:

- **Tier 0 (v2.0.3):** Stage register + gated invariants. ~300 lines. Unblocks everything.
- **Tier 1 (v3 critical):** Artifact binding, regime hashing, enforcement boundary. Enables "real teeth."
- **Tier 2 (v3 scaling):** Multi-tenancy, auth, cost attribution, hash chaining. Enables "platform."

The uncomfortable ratio: **~30% is plumbing** (add fields, tables, CLI) and
**~70% is architectural** (enforcement boundaries, auth, multi-tenancy).

---

## Tier 0: Ship in v2.0.3 (Unblocks Everything Else)

| What | Where | Size | Why First |
|------|-------|------|-----------|
| Stage register | New `stages.py` | ~250 lines | Every v3 spec assumes stages exist |
| `active_from_stage` on invariants | `invariant_store.py` | ~50 lines | Dormant invariants are the anti-cathedral primitive |
| Stage CLI | `cli.py` additions | ~100 lines | `governor stage {status,list,advance,retreat,history}` |
| Dormancy classification | `invariants.py` | ~20 lines | `details["classification"] = "dormant"` — first-class, not silent |

**Total: ~420 lines + ~50 tests. One person, one week.**

This is the keystone. Phase gating makes every subsequent v3 feature
stage-gatable, preventing the Rome-in-a-day problem on the governor itself.

### Stage Contract (What Makes It Keystone, Not Just a File)

A stage register without semantic rules is a label + history log. These
rules make it a control surface:

**Transition rules:**
- Advancement requires `--reason` and emits a gate receipt
- Retreat requires `--reason`, emits a warning receipt, and logs to scar ledger
- Only humans can advance/retreat (agents cannot self-advance)
- No skip: advancing from `alpha` to `production` requires passing through `beta`
- Concurrent advance attempts: first writer wins (SQLite leases)

**Stage-scoped mutability:**
- Each stage defines a `freeze_set`: fields that become immutable from that
  stage onward
- Example: at `beta`, receipt schema version is frozen. At `production`,
  tool schema allowlist is frozen.
- Mutations to frozen fields require stage retreat first (receipted, logged)

**Stage-scoped invariant precedence:**
- When multiple stage-gated invariants apply to the same subject, **deny
  overrides allow** (same as firewall semantics)
- Most-specific-stage wins for conflicting guidance (a `beta` invariant
  overrides an `alpha` invariant on the same subject)
- Conflicts are logged, not silently resolved

**Provisional stage sequence:**
```
scaffold → alpha → beta → production → hardened
```

**Test surface for Tier 0 (what "~50 tests" actually covers):**
- Transition validity: allowed/disallowed sequences (8 tests)
- History monotonicity: history is append-only, survives restart (4 tests)
- Rollback semantics: retreat emits warning, requires reason (4 tests)
- Concurrency: two callers racing `governor stage advance` (3 tests)
- Persistence: restart daemon, stage stays consistent (3 tests)
- Stage-scoped invariant activation: dormant/active transitions (8 tests)
- Dormancy classification: `details["classification"]` is correct (4 tests)
- CLI smoke: all 5 commands produce expected output (5 tests)
- Gate receipt emission: advance/retreat produce receipts (4 tests)
- Serialization roundtrip: `to_dict`/`from_dict` preserves state (3 tests)
- Edge cases: unknown stage name → ValueError, empty history, etc. (4 tests)

---

## Threat Model

This doc implicitly assumes a cooperative environment. It shouldn't. Who's
the adversary, and what does each tier mitigate?

| Adversary | Description | Mitigated By |
|-----------|-------------|-------------|
| **Agent bypass** | Agent code under user control attempts to skip governor | Tier 1b (enforcement boundary) |
| **Operator misconfig** | Wrong model loaded, wrong policy version, stale config | Tier 1a (artifact binding), Tier 1c (substrate expiry) |
| **Log tampering** | After-the-fact modification of receipts or run history | Tier 2d (hash chaining, append-only audit log) |
| **Substrate drift** | Model/tool/corpus changes silently, receipts become stale | Tier 1a (regime hash), Tier 1c (substrate-conditional expiry) |
| **Cathedral creep** | Agent builds toward gap specs without authorization | Tier 0 (stage register, anti-cathedral guard) |
| **Budget gaming** | Agent consumes resources beyond allocation | Tier 2e (hard-stop enforcement, not advisory) |

**Library wrappers are advisory.** If v3 keeps the library wrapper as the
enforcement boundary, call it "training wheels," not enforcement. Real teeth
require the daemon (sidecar/gateway) between agent and tools.

---

## Tier 1: V3 Critical (Enables "Real Teeth")

### 1a. Artifact Binding (Receipt Schema Evolution)

The single most important v3 change: receipts must bind to the substrate
that produced them.

| Gap | Module | Difficulty | What Exists |
|-----|--------|-----------|-------------|
| `model_artifact_id` field | gate_receipt.py | Moderate | `policy_hash` pattern exists; extend it |
| `regime_hash` field | gate_receipt.py + regime.py | Trivial | RegimeDetector has all signals; just hash them |
| `evidence_digest` (explicit eval provenance) | gate_receipt.py | Trivial | `evidence_hash` exists; add eval manifest binding |
| Model identity generation | chat_bridge.py | Moderate | Backends have model names but no content-addressed IDs |
| Model version tracking | storage.py | Trivial | New table: `model_artifacts(id, hash, config, created_at)` |
| Regime snapshot table | storage.py | Trivial | New table for regime state at key events |

**v2 already has:** Content-addressed receipt identity, canonical JSON
serialization, split store (JSONL + blob), schema versioning (receipt_v1).

**v2 is missing:** Any binding to *which model* or *which regime state*
produced the evidence. A receipt says "evidence_gate passed" but not
"...while running claude-opus-4-6 in ELASTIC regime with these tool schemas."

**Receipt schema v2 (proposed):**
```
Everything from v1, plus:
model_artifact_id   # H(backend_type + model_name + config + provider_revision)
regime_hash         # H(canonical_json(regime_signals + thresholds + tool_schemas))
valid_until         # explicit expiry (substrate-change; separate from freshness)
stale_after         # time-based freshness budget (orthogonal to valid_until)
```

**Honesty about `model_artifact_id`:** For API-served models (Anthropic,
OpenAI), we cannot hash weights. `model_artifact_id` is a **conventional ID**
(`H(backend_type + model_name + config + provider_reported_revision)`), not
cryptographic truth about the substrate. This is acceptable — it catches
model swaps and config changes — but it cannot detect silent provider-side
weight updates. Say so explicitly; don't pretend it's a content hash.

For self-hosted models (Ollama), include the model digest from the Ollama
API, which *is* a content hash.

**`regime_hash` canonicalization:** Must follow the same canonical JSON
pattern as `gate_receipt.py` (`json.dumps(sort_keys=True, separators=(',',':'),
ensure_ascii=True)`). Include a `regime_schema_v` field so hash changes
from schema evolution don't look like regime changes. Included fields:
regime name, all 10 signal values (rounded to 6 decimal places for float
stability), threshold values, tool schema digests, corpus digest. Excluded:
timestamps, transition history (those are metadata, not regime identity).

**Freshness vs validity are separate axes:**
- `valid_until`: receipt becomes invalid when substrate changes (regime hash
  mismatch, model artifact mismatch). This is structural.
- `stale_after`: receipt is "old" even if substrate unchanged. Time-based.
  Orthogonal. Don't blend them in one TTL field.

### 1b. Enforcement Boundary (Daemon as Gatekeeper)

Today the daemon is advisory — it checks pass/fail but doesn't block
file writes. v3 needs the daemon to be the enforcement authority.

| Gap | Module | Difficulty | Notes |
|-----|--------|-----------|-------|
| Daemon as enforcement point | daemon.py | Significant | All reads/writes through daemon gates |
| Receipt emission on all RPC | daemon.py | Moderate | Currently only chat/commit paths emit |
| Concurrency control | daemon.py + storage.py | Moderate | Use existing SQLite leases table |
| Request auth/authz | daemon.py | Significant | Multi-agent/multi-tenant needs caller identity |

**v2 already has:** JSON-RPC 2.0 over stdio/Unix socket, 25 RPC methods,
async dispatcher, DaemonState with lazy init, SQLite leases table.

**v2 is missing:** The daemon doesn't *enforce* — it *advises*. Agents can
still bypass it. v3 needs the daemon between the agent and every tool/file
operation.

**Enforcement boundary decision (must pick one):**

| Model | Bypass resistance | Ops cost | Adoption friction |
|-------|------------------|----------|-------------------|
| Library wrapper | Low (agent imports governor; can skip) | None | None |
| Sidecar / local gateway | Medium (all tool calls via Unix socket) | Moderate | Moderate |
| OS-level mediation (seccomp/AppArmor) | High (kernel enforced) | High | High |

v2 is a library wrapper. That's fine for research (A). For production (B),
the minimum viable enforcement boundary is **sidecar**: the daemon owns the
Unix socket, and all tool calls must traverse it. The agent process has no
direct filesystem/network access except through the daemon.

This is a v3 architectural decision, not a code change. It must be made
before Tier 1b implementation begins.

### 1c. Substrate-Conditional Expiry

Claims should auto-expire when their substrate changes, not just on a timer.

| Gap | Module | Difficulty | Notes |
|-----|--------|-----------|-------|
| Model change → invalidate receipts | gate_receipt.py | Moderate | Compare `model_artifact_id` on each call |
| Tool version change → invalidate | gate_receipt.py | Moderate | `regime_hash` mismatch = stale |
| Corpus change → invalidate truth claims | gate_receipt.py | Moderate | Corpus digest in `regime_hash` |

**v2 already has:** TTL enforcement (`ttl.py`) with volatility classes and
recency decay. The concept of "claims expire" exists.

**v2 is missing:** Expiry is time-based only. No substrate-change trigger.

---

## Tier 2: V3 Scaling (Enables "Platform")

### 2a. Multi-Tenancy

| Gap | Module | Difficulty |
|-----|--------|-----------|
| Per-tenant regime isolation | regime.py | Moderate (thread tenant_id) |
| Per-tenant database partitioning | storage.py | Significant (sharding or partition scheme) |
| Per-tenant stage registers | stages.py (new) | Moderate (if designed in from day 1) |
| Per-tenant budgets | execution.py | Moderate (allocation tracking) |

### 2b. Supply Chain Primitives (Don't Roll Your Own)

| What | Use Instead Of Inventing | When |
|------|------------------------|------|
| Receipt container | DSSE / in-toto attestations | When signing receipts |
| Signatures | Sigstore (or local Ed25519) | When distributed trust needed |
| Policy engine | OPA (if complexity warrants) | When inline Python isn't enough |
| Capability tokens | Biscuit / Macaroons | When tool calls are a trust boundary |
| Artifact allowlists | TUF | When managing promotion across envs |
| Workload identity | SPIFFE/SPIRE | When multi-service deployment |

### 2c. Observability Enrichment

| Gap | Module | Difficulty |
|-----|--------|-----------|
| Model artifact attribution on events | telemetry.py | Trivial (add field) |
| Regime snapshot on events | telemetry.py | Trivial (add field) |
| Receipt linkage on events | telemetry.py | Trivial (add receipt_id field) |
| Sampling for cost control | telemetry.py | Moderate |
| Real-time event streaming | telemetry.py | Significant (pub/sub) |

### 2d. Tamper Evidence

| Gap | Module | Difficulty |
|-----|--------|-----------|
| Hash chaining (Merkle-ish) on ledger | storage.py | Moderate |
| Append-only audit log | storage.py | Moderate (new table + triggers) |
| Backup/recovery | ops | Moderate (mostly ops, not code) |
| Signed attestations | gate_receipt.py | Significant (PKI dependency) |

### 2e. Cost and Budget Enforcement

| Gap | Module | Difficulty |
|-----|--------|-----------|
| Hard-stop on budget exhaustion | execution.py | Moderate |
| Cost attribution (billing API) | execution.py + chat_bridge.py | Significant |
| Cost forecasting | execution.py + routing.py | Moderate |
| Per-task budget allocation | execution.py | Moderate |

---

## Dependency Graph

```
v2.0.3: Stage Register
    │
    ├──> v3 Tier 1a: Artifact Binding (receipt schema v2)
    │        │
    │        ├──> v3 Tier 1c: Substrate-Conditional Expiry
    │        │
    │        └──> v3 Tier 2d: Tamper Evidence (hash chaining)
    │
    ├──> v3 Tier 1b: Enforcement Boundary (daemon as gatekeeper)
    │        │
    │        ├──> v3 Tier 2a: Multi-Tenancy (auth + isolation)
    │        │
    │        └──> v3 Tier 2e: Budget Enforcement (hard limits)
    │
    └──> v3 Tier 2b: Supply Chain Primitives (signing, OPA, Biscuit)
             │
             └──> v3 Tier 2c: Observability (enriched events)
```

Stage register is the root. Everything else builds on it or on the
enforcement boundary.

---

## What v2 Got Right (Don't Touch)

These are load-bearing and v3-ready as-is:

1. **Content-addressed receipt identity.** The `H(schema_v + gate + subject_hash + evidence_hash + policy_hash)` pattern extends cleanly to include `model_artifact_id` and `regime_hash`.

2. **Split receipt store.** JSONL for receipts + content-addressed blob store for evidence. This pattern scales.

3. **SQLite with WAL mode.** Concurrent readers, single writer, leases, epochs. Multi-tenant needs sharding, not replacement.

4. **Regime detection signals.** 10 observables, 4 regimes, transition history with dwell. Just needs a hash function on top.

5. **Evidence gate pattern.** Claim extraction, evidence linking, custody scoring, exit shape checking. Admission control is a policy matrix on top of this, not a rewrite.

6. **MCP safety controls.** RateLimiter, BackpressureController, CircuitBreaker, IdempotencyLayer — all reusable for v3 tool gateway.

7. **Telemetry infrastructure.** TelemetryCollector with pluggable backends, JSONL logging, date-partitioned rotation. Needs enrichment (model/regime/receipt fields), not replacement.

---

## The Three Non-Negotiables (from SELF_GOVERNANCE_SPEC)

Everything above is platform plumbing. The actual v3 governance innovations
are these three, which require stable Tier 1 first:

1. **Executor/Proposer Separation.** Governor (immutable theta in-run) vs
   MetaGovernor (proposes changes, cannot apply). Hard architectural boundary.

2. **Admissible Measurement Gating.** Only certain signals can justify policy
   changes. Model-stated confidence is inadmissible. Requires significance
   testing (Wilson/Clopper-Pearson bounds).

3. **Rollback + Hysteresis + Dwell.** Prevent oscillation and limit cycles.
   Stratified baseline metrics, EWMA updates, separate enter/exit thresholds.

These are the novel governance contributions. The platform plumbing (Tier 1-2)
exists to make them enforceable, not to replace them.

**8 hardening items in SELF_GOVERNANCE_SPEC require human review before any
v3 implementation begins.** See spec for details.

---

## Monday Action Items

If you want to start v2.0.3:

1. Create `src/governor/stages.py` — Stage, StageRegister, StageTransition
2. Define the stage contract (transition rules, freeze sets, precedence)
3. Add `active_from_stage` to `InvariantSpec` with deny-overrides-allow precedence
4. Add dormancy classification to `InvariantResult`
5. CLI: `governor stage {status,list,advance,retreat,history}`
6. Tests: `tests/test_stages.py` (~50 tests, see test surface breakdown above)
7. Smoke: add stage CLI to `tests/test_fresh_clone.py`

If you want to start v3 planning:

1. Review the 8 hardening items in SELF_GOVERNANCE_SPEC
2. **Decide enforcement boundary** (library wrapper vs sidecar vs gateway) —
   this is the most consequential architectural decision for v3
3. Define `regime_hash` canonicalization (fields, rounding, schema version)
4. Define `model_artifact_id` computation (conventional for API models,
   content-addressed for self-hosted)
5. Write receipt schema v2 spec with separate `valid_until` / `stale_after`
6. Write threat model for v3 (expand the table above into adversary scenarios)

Everything else follows from those decisions.
