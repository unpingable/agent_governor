# Gap: Replay Harness — Backtesting Over Stored Runs

**Branch:** v2.x
**Status:** shipped (v2.5.0 — `signals/replay_harness.py` + `signals/replay_sources.py`; retained as design rationale per V2_4A_SPINE.md §8)
**Depends on:** receipt_kernel (Tier A shipped), receipt_bridge.py, telemetry.py, SIGMA_RATE_GAP (data source)
**Build phase:** v2.3 (make it measurable)
**Blocks:** CALIBRATION_LAYER_GAP (validation), KAPPA_DIAL_GAP (cost curve data)

## The Problem

The governor makes decisions in real time, but there's no way to ask "what would have happened if I'd used different thresholds?" The receipt kernel stores everything needed for offline replay, but there's no harness to actually do it.

## What Already Exists

| Component | Location | Status |
|-----------|----------|--------|
| Tier A: re-run invariants | receipt_kernel/invariants/ | SHIPPED — 6 structural + 6 hallucination invariants |
| Tier B: reproduce tool calls | RECEIPT_KERNEL_ROADMAP §9 | Defined, deferred (needs sealed evidence) |
| Tier C: deterministic outputs | RECEIPT_KERNEL_ROADMAP §9 | Defined, deferred (needs temp=0 + seed) |
| Regression farming | RECEIPT_KERNEL_ROADMAP §4 | Defined, deferred (needs 10+ failures) |
| Freeze-to-test | RECEIPT_KERNEL_ROADMAP §11 | Defined, deferred |
| Event log | receipt_kernel store_sqlite.py | Append-only, hash-chained, blob store |

## What Needs Building (v2 Scope)

### 1. Replay Runner (Tier A+)

Tier A already re-runs invariants against stored events. The replay harness extends this to re-run **governor policy** against stored events with different parameters:

```python
@dataclass
class ReplayConfig:
    run_id: str                          # which run to replay
    parameter_overrides: dict[str, Any]  # e.g. {"tau": 0.8, "contradiction_threshold": 0.3}
    policy_overrides: dict[str, Any]     # e.g. {"evidence_gate.hard_threshold": 0.9}

@dataclass
class ReplayResult:
    original_verdicts: list[Verdict]
    replayed_verdicts: list[Verdict]
    differences: list[ReplayDiff]        # where verdicts diverged
    parameter_sensitivity: dict[str, float]  # which params caused most divergence
```

### 2. CLI

```bash
governor replay --run <id> --override tau=0.8 --override contradiction_threshold=0.3
governor replay --run <id> --sweep tau=0.5:0.9:0.1   # sweep parameter range
governor replay list                                    # runs available for replay
```

### 3. Regression Fixture Export

Convert FAIL runs into test fixtures (RECEIPT_KERNEL_ROADMAP §4):

```bash
governor replay export --run <id> --format pytest    # generates test_regression_<id>.py
governor replay export --run <id> --format fixture   # generates JSON fixture
```

This only works once we have 10+ real FAIL runs. The harness should detect "not enough failures" and say so.

### 4. Epoch Roots / Checkpointing

Log compaction without tamper-evidence is how you end up with a religion instead of an audit trail. The replay harness must support checkpointing that preserves verifiability:

```python
@dataclass
class EpochRoot:
    epoch_id: str                        # monotonic
    run_id: str
    event_range: tuple[int, int]         # (first_seq, last_seq) in this epoch
    root_hash: str                       # Merkle root of event hashes in range
    prev_epoch_root: str | None          # chain across epochs
    timestamp: datetime
```

- Events within an epoch can be compacted (blob purge, detail elision) as long as the Merkle root remains verifiable
- Cross-epoch chain provides tamper evidence at compaction boundaries
- This is the v2 foundation for PAAS_SHARDING_GAP (v3), which needs epoch roots for partition-level integrity

```bash
governor replay epochs --run <id>        # list epoch boundaries
governor replay verify-epoch <epoch_id>  # verify Merkle root against stored events
```

## What This Does NOT Do

- **Tier B/C**: No tool call reproduction, no deterministic output replay. Those need sealed evidence and temperature pinning (v3).
- **Online replay**: This is offline-only. No "replay while running" mode.
- **Auto-tuning integration**: The replay harness produces data; it doesn't propose parameter changes. That's convergence_tuning's job.

## Build Estimate

~150 lines (replay runner + CLI) + ~80 tests. Depends on receipt_kernel store API (already stable).

## Acceptance Criteria

1. `governor replay --run <id>` replays governor policy against stored events
2. `--override` accepts key=value parameter changes
3. `--sweep` produces a comparison table across parameter range
4. `governor replay export` generates pytest-compatible fixtures from FAIL runs
5. Clear error when run has no events or insufficient data
