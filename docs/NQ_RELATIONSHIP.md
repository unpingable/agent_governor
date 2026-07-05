# AG ↔ NQ Relationship

STATUS: CANDIDATE (public-mvp S3) — not minted

---

## What NQ is

NQ ([github.com/unpingable/nq](https://github.com/unpingable/nq)) is a local-first
diagnostic monitor that classifies operational findings into typed failure domains
and emits structured `nq.witness_packet.v1` / `nq.receipt.v1` envelopes over a
minimal HTTP API backed by SQLite. It is independently deployable by SREs today,
with no dependency on AG.

---

## What AG consumes from NQ, and where

AG does not import NQ's Rust crates. The coupling is wire-only: AG reads
`nq.finding_snapshot.v1` JSON dicts that NQ emits and that Night Shift passes
across the boundary via `--finding-json`.

| What AG reads | Where in AG source |
|---|---|
| `FindingSnapshot` wire DTO, schema `nq.finding_snapshot.v1` | `src/governor/drill_runner.py` — `build_drill_finding_snapshot()`, `load_finding_snapshot_from_json()` |
| `origin_mode` discriminator from `FindingSnapshot` | `src/governor/cooked_context_orchestrator.py` — `NQ_ORIGIN_MODES = frozenset({observed, drill, replay, synthetic})` |
| Origin-mode operational fence | `cooked_context_orchestrator.py` — `operational_admission()`, `OPERATIONAL_ORIGIN_MODES = frozenset({observed})` |
| Type-split spend wall | `cooked_context_orchestrator.py` — `OperationalConsumed` vs `DemonstratedConsumed`; `confer_operational_effect()` accepts only `OperationalConsumed` |
| Monotonic-gap clock witnesses | `src/governor/clock_witness.py` — `MonotonicReading`, `WallWitness`, `elapsed_ns()` |
| Night Shift RPC → policy engine | `src/governor/nightshift_adapter.py` — `AuthorityLevel`, verdict mapping, `GateReceiptSystem.emit` |

The `origin_mode` field is the load-bearing discriminator. Recognized modes:
`{observed, drill, replay, synthetic}` (NQ-emitted) and `{cli_origin, stub_origin}`
(AG-internal). A novel string is refused at the fence with `origin_unrecognized`;
absent mode is refused with `origin_missing`; non-string is a `MalformedOriginError`.

---

## The optionality rule

**AG runs standalone. NQ is not a requirement.**

When NQ observations are absent, the witness seam yields honest absence — the
chain does not fail open. Concretely: if no `FindingSnapshot` is supplied, the
drill runner falls back to `build_drill_finding_snapshot()` (a deterministic
fixture). If the fixture or wire DTO is absent in a non-drill path, the governed
chain refuses before the standing seam rather than synthesizing a synthetic claim.
The operational fence (`confer_operational_effect`) accepts only `OperationalConsumed`
outcomes carrying `origin_mode=observed`; every non-observed mode, including absent
mode, routes to `DemonstratedConsumed`, which the spend wall refuses by type.

There is no "degrade to advisory" fallback when NQ is absent. The chain refuses
consequence by classifying the absence as a non-operational origin.

---

## The illustrative composition lane

The following describes a potential integration topology. It is illustrative,
not a deployment requirement.

```
NQ witnesses host state
  → nq.witness_packet.v1 / nq.finding_snapshot.v1
     ↓
Night Shift (earlier-stage deferred-work runner; github.com/unpingable — repo `nightshift`)
  defers / reconciles scheduling decisions against NQ observations
  calls AG's policy engine via nightshift_adapter.py
     ↓
AG governs
  evaluates proposed actions, emits gate receipts
  operational fence: origin_mode=observed admits; drill/replay/synthetic demonstrate
```

Night Shift is an earlier-stage constellation member than NQ in current development.
Its `nightshift_adapter.py` shim in AG is a translation layer, not a production
operational dependency.

---

## What this note does NOT claim

- No bundling. AG and NQ ship independently. NQ is not a prerequisite for AG
  installs, and NQ has no runtime dependency on AG.
- No NQ endorsement of AG verdicts. NQ witnesses observations. NQ does not authorize
  AG to take action, and AG gate receipts are not NQ artifacts.
- Testimony is not admission. An NQ `verified` receipt for `disk_state` is witnessed
  testimony scoped to its `observed_at`. AG's operational fence decides whether that
  testimony may confer operational effect; NQ does not make that decision.
- No Night Shift production readiness claim. Night Shift is an illustrative consumer,
  not a shipped integration.
- Synthetic compatibility is not live testimony. Drill and synthetic origin modes
  (`origin_mode ∈ {drill, replay, synthetic}`) demonstrate the chain mechanics
  against lab substrate. They cannot confer operational effect. The cage label
  must stay on the cage.

---

## NQ standalone usability (Part 1 run evidence, 2026-07-05)

Run from `/home/jbeck/git/nq-root/nq` as a cold SRE:

| Command | Exit | Outcome |
|---|---|---|
| `cargo build --release` | 0 | Both `nq-monitor` + `nq-witness` built in ~41s |
| `nq-witness --config publisher.json` (port 9847) | 1 | Address in use — existing instance running |
| `curl http://127.0.0.1:9847/state` | 0 | Full `nq.witness_packet.v1` envelope; host metrics, services, Prometheus data |
| `nq-monitor serve -c aggregator.json` (port 9858) | 0 | 63 migrations applied; auto-polled witness at startup |
| `curl "http://127.0.0.1:9858/api/query?sql=SELECT ..."` | 0 | `v_hosts` returned: disk 97.1%, mem 33.2%, cpu 3.17 |
| `curl "http://127.0.0.1:9858/api/query?sql=SELECT * FROM v_warnings"` | 0 | Two findings: `disk_pressure` (info, 97.1% disk) + `check_failed` |
| `nq-monitor preflight disk-state --host local --format human` | 0 | `cannot_testify` list with 7 explicit refusals (physical disk death, data loss, future failure probability, replacement workflow, etc.) |

Friction observed: ports 9847/9848 already in use by existing deployment (quickstart
silent on this); SQL API is `/api/query?sql=...` GET, not `/api/sql` POST (404);
`receipt check --db` is wrong flag (requires receipt file, not db path); hostname
WARN fires when config `name` mismatches machine hostname (benign, undocumented).

**Verdict: usable by a normal SRE today.** Build is clean; wire format is legible JSON;
`preflight disk-state` verifies disk occupancy and explicitly refuses seven consequence
claims in the same receipt. Friction points are documentation gaps, not capability gaps.
