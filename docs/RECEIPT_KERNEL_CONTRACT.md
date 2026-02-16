# Receipt Kernel Contract (v0)

## Purpose

`receipt_kernel` is a small, boring library that makes delegated execution auditable and bounded.

It provides:
- A run ledger (append-only, hash-chained events)
- A stage machine (legal transitions)
- An evidence store (content-addressed blobs with redaction and retention)
- Invariant evaluation primitives (PASS/WARN/FAIL/UNKNOWN)

**It does not orchestrate, schedule, reconcile, or "manage systems".**

status: canonical

## Non-Goals (Hard No)

- No daemons, watchers, schedulers, reconciliation loops
- No remote filesystem/protocols (no Plan9 cosplay)
- No plugin marketplace / dynamic remote invariant execution
- No auth/tenancy/cost platform in v0 (wrappers can add later)
- No LLM / tool runner abstractions in the kernel

## Invariant Semantics

Verdicts are:
- **PASS**: verified and satisfied
- **WARN**: verified but degraded / soft failure
- **FAIL**: verified and violated
- **UNKNOWN**: cannot verify (missing evidence / read failure / unsupported schema)

**No silent downgrade:**
- Any UNKNOWN/FAIL in required invariants poisons "success".
- If evidence is incomplete, `overall_verdict` cannot be PASS.

## Event Ledger Contract

All events share a stable envelope schema.

Required properties:
- `event_schema_version` (int)
- `run_id` (str)
- `seq` (monotonic per run, contiguous)
- `ts` (ISO 8601 Z)
- `event_type` (str)
- `stage` (str)
- `policy` block: `{policy_id, policy_version, stage_graph_id}`
- `actor` block: `{kind, id}`
- `prev_event_hash` (str | null)
- `event_hash` (sha256 over canonical JSON of envelope without event_hash)
- `payload` (dict)
- `refs`: `{blobs: [...], events: [...]}`

The store MUST:
- Append only (no UPDATE/DELETE)
- Enforce contiguous seq and prev_hash continuity
- Reject unknown future schema versions (hard-fail)

## Evidence Contract

Evidence is stored as blobs addressed by sha256:
- Blob ref format: `blob://sha256:<hex>`
- Evidence is referenced from events, not embedded
- Evidence keys are logical labels (e.g. `model_output`, `tool_trace`)

The kernel MUST support an optional redaction hook before persistence.

Two evidence classes:
- `public`: safe-ish, retained longer
- `sealed`: encrypted-at-rest or aggressively expired

## StageGraph Contract

Stages are explicit.
- A StageGraph defines allowed transitions.
- Illegal transitions are hard errors (not warnings).

## Dependency Rules (Constitutional)

Kernel code:
- MUST be import-clean (no imports from agent_gov subsystems)
- MUST only depend on stdlib (no third-party deps in v0)
- MUST accept inputs as dicts/dataclasses, not live subsystem objects
- MUST expose typed, deterministic serialization/hash behavior

Adapters belong in the consuming app, not the kernel.

## Versioning and Compatibility

- Event envelope schema is versioned independently (`event_schema_version`)
- Library uses semver
- Kernel rejects future `event_schema_version` by default
- Adding new event_type/payload keys is allowed if envelope stays stable

## Testing Requirements

Kernel ships:
- Canonicalization + hash determinism tests
- Ledger chain verification tests
- No-silent-downgrade tests (UNKNOWN propagates)
- Schema compatibility tests (reject future versions)
- Redaction hook coverage
- Retention lifecycle tests
