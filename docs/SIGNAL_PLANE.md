# Signal Plane — Operator Guide

Shipped in v2.5.0. The signal plane makes the v2.4 instrumentation spine queryable.
Signals are observe-only — they never gate or block.

## Architecture

```
  Derivation functions          JSONL append log           SQLite projection
  (pure, no IO)                 (source of truth)          (disposable cache)
       │                             │                          │
  SignalEnvelope ──▶ JsonlSink ──▶ signals.jsonl ──▶ SignalStore ──▶ queries
                                                    (byte-offset cursor,
                                                     incremental ingest)
```

The SQLite index can be nuked and rebuilt from JSONL at any time:
`governor signals rebuild --confirm`

## Watching verifier runs live

```bash
# All signals, newest 20
governor signals tail

# Filter to verifier summaries, poll every second
governor signals tail --name VERIFY_SUMMARY --poll-ms 1000

# Watch for emission failures
governor signals tail --name SIGNAL_EMIT_FAILED --poll-ms 1000
```

## Querying

```bash
# List with filters
governor signals list --name VERIFY_SUMMARY --quality ok --limit 50

# Filter by session
governor signals list --session gov_abc123def456

# Full envelope details
governor signals explain sha256:abc123...

# Index health
governor signals stats
```

## Key signals

| Signal | Source | Value | What it tells you |
|--------|--------|-------|-------------------|
| VERIFY_SUMMARY | verifier_gate | count_block + count_error | "How annoyed should I be about this run" |
| SIGNAL_EMIT_FAILED | emit.py | None (always partial) | "Signal emission broke — check the sink" |
| EXPOSURE_PROXY | Phase A | weighted denominator | Tool dispatch + generation activity |
| SILENT_SUPPRESSION | Phase A | in-path health | Multi-source suppression indicators |
| SIGMA_RATE | Phase A | endorsement rate | Endorsement→invalidation matching |

## Session correlation

Every daemon instance and CLI invocation gets a process-scoped session ID
(`gov_{uuid12}` format). Use `--session` to scope queries:

```bash
governor signals list --session gov_abc123def456
```

The daemon reports its session ID in the `governor.hello` RPC response
(`result.governor.session_id`).

## Daemon RPC

```
signals.query   {signal_name?, phase?, quality?, session_id?, since?, until?, limit?, after_seq?}
signals.get     {signal_hash}
signals.tail    {limit?, after_seq?, signal_name?}
signals.stats   {}
```
