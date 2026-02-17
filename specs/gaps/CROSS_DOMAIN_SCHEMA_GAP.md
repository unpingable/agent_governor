# Gap: Cross-Domain Schema — Wire Contract for Multi-System Integration

**Branch:** v3.x
**Status:** gap (architectural)
**Depends on:** DETECTOR_INTEGRATION_SPEC.md (SignalKey), receipt_kernel (event envelope), daemon.py (RPC schema)
**Build phase:** v3.0 (contract first — all v3 downstream of this)
**Blocks:** PAAS_SHARDING_GAP (hard)

## The Problem

The governor, receipt kernel, correlator, detector (Δt), and any future external system all emit structured data — but each uses its own schema. There's no shared wire contract. Integration requires bespoke adapters for every pair of systems.

Current state:
- Receipt kernel: `EventEnvelope` with hash chain
- Daemon: JSON-RPC 2.0 method-specific schemas
- Detector: `SignalKey` + 5 collapsed dimensions
- Telemetry: `TelemetryEvent` with typed fields
- Correlator: K-vector + regime flags

Each of these is internally consistent but there's no common envelope that lets them interoperate without per-pair glue code.

## What Already Exists

| Component | Schema | Format |
|-----------|--------|--------|
| SignalKey | DETECTOR_INTEGRATION_SPEC §2.2 | Dataclass: run_id, turn_id, response_hash, model_id, timestamp, byte_range |
| EventEnvelope | receipt_kernel/envelope.py | Dict: event_type, run_id, seq, timestamp, prev_event_hash, event_hash, payload |
| TelemetryEvent | telemetry.py | Dataclass: event_type, timestamp, data, level, tags |
| ThetaSnapshot | SELF_GOVERNANCE_SPEC §2 | Dataclass: parameter values + hash |
| DaemonState | daemon.py | JSON-RPC response shapes per method |

## What Needs Building

### 1. TemplateInst — The Universal Observation

Every system emits observations. A `TemplateInst` is the minimal shared envelope:

```python
@dataclass
class TemplateInst:
    schema_version: str              # "v1"
    source: str                      # "governor.evidence_gate", "detector.delta_t", etc.
    run_id: str                      # ties to receipt kernel run
    turn_id: str | None              # ties to conversation turn
    timestamp: datetime
    observation_type: str            # "signal", "decision", "event", "measurement"
    payload: dict                    # source-specific data
    content_hash: str                # H(canonical_json(payload))
```

This doesn't replace internal schemas — it wraps them for cross-system consumption.

### 2. RunSummary — Aggregated Execution Record

A `RunSummary` collects all `TemplateInst` observations for a single execution run:

```python
@dataclass
class RunSummary:
    run_id: str
    schema_version: str
    start_time: datetime
    end_time: datetime | None
    source_systems: list[str]        # which systems contributed
    observation_count: int
    verdict: str                     # overall run verdict
    template_insts: list[TemplateInst]
    integrity_hash: str              # H(chain of content_hashes)
```

### 3. Schema Registry

Systems register their payload schemas so consumers can validate without importing source code:

```python
@dataclass
class SchemaRegistration:
    source: str
    observation_type: str
    payload_schema: dict             # JSON Schema for the payload field
    version: str
```

### 4. Serialization Contract

- Wire format: canonical JSON (same `sort_keys=True, separators=(',',':')` as receipt kernel)
- Content addressing: same SHA-256 scheme as gate receipts
- Versioning: `schema_version` field, no implicit upgrades
- Backward compat: unknown fields ignored, missing optional fields use defaults

## Why v3

This is architectural plumbing that only matters when multiple systems need to talk to each other. v2 systems work fine with bespoke adapters. v3 (cross-model validation, distributed deployment) needs a shared contract to avoid O(n²) adapter growth.

## Relationship to Existing Specs

- **DETECTOR_INTEGRATION_SPEC**: SignalKey becomes a field within TemplateInst (not replaced)
- **Receipt kernel EventEnvelope**: TemplateInst wraps kernel events for external consumption; the kernel's internal schema stays as-is
- **Daemon JSON-RPC**: RPC responses can include TemplateInst observations as a standard field

## Build Estimate

~200 lines (schema types + registry + serialization) + ~100 tests. The hard part is getting all systems to emit TemplateInst without breaking their internal schemas — that's integration work, not new code.

## Acceptance Criteria

1. `TemplateInst` and `RunSummary` defined with canonical JSON serialization
2. Schema registry with JSON Schema validation
3. Receipt kernel, evidence gate, and correlator emit TemplateInst wrappers
4. Content addressing compatible with existing gate receipt scheme
5. `governor schema list` CLI shows registered schemas
6. No breaking changes to internal system schemas
