# Witness: CLI Reachability of Nightshift → Governor Receipt Emission

**Filed:** 2026-06-09. **Scope:** classification only; no code, no tests, no investigation beyond the named files. Follows the prior witness ([witness-2026-06-09-gate-receipt-unsettled-gap.md](witness-2026-06-09-gate-receipt-unsettled-gap.md)) which promoted the lower-pipeline seam to `witnessed` and flagged top-level CLI reachability as the next narrowest ambiguity.

## Verdict

**C. Split** — the lower horizon-aware path can emit `record_receipt` calls, but only when the CLI is invoked with **both** `--horizon-policy` and `--governor-socket` flags. The default invocation is governor-blind by intentional design.

## Evidence

Directly read this pass: `~/git/scheduler/crates/nightshiftd/src/main.rs` (lines 19-22 imports, 84-100 CLI help text, 626-650 `build_horizon_deps`, 652-728 `run_watchbill_cmd`).

### The branching logic (main.rs:683-712)

`run_watchbill_cmd` branches on whether `build_horizon_deps(cli)?` returns `None` or `Some(...)`:

```rust
let packet = match horizon_deps {
    // No horizon configured — original same-generation path.
    None => run_watchbill_with_liveness(
        &agenda, &target, nq.as_ref(), liveness.as_deref(),
        &store, &opts,
    )?,
    // Horizon configured — compose capture + horizon-aware
    // reconcile by hand.
    Some((policy, governor)) => match capture_phase(...)? {
        CaptureOutcome::HeldPacket(packet) => *packet,
        CaptureOutcome::Captured { run_id } => reconcile_phase_with_horizon(
            &run_id,
            nq.as_ref(),
            Some(policy.as_ref()),
            Some(governor.as_ref()),  // ← governor threaded through here only
            &store, &opts,
        )?,
    },
};
```

`run_watchbill_with_liveness` does not take a `governor` parameter; its delegate `reconcile_phase` passes `None` for both `horizon_policy` and `governor` into `reconcile_phase_with_horizon`. So the `None` branch is **structurally governor-blind**.

### The dependency-construction logic (main.rs:636-650)

`build_horizon_deps` is the gate:

```rust
match (&cli.horizon_policy, &cli.governor_socket) {
    (Some(policy_path), Some(socket_path)) => {
        let policy = FileHorizonPolicySource::from_yaml_path(policy_path)?;
        let governor = JsonRpcGovernorClient::new(socket_path.clone());
        Ok(Some((Box::new(policy), Box::new(governor))))
    }
    (Some(_), None) => anyhow::bail!(
        "--horizon-policy requires --governor-socket \
         (horizon receipts are forwarded via Governor)"
    ),
    (None, Some(_)) => anyhow::bail!(
        "--governor-socket requires --horizon-policy \
         (no firing site without a policy source)"
    ),
    (None, None) => Ok(None),
}
```

Both flags must be present together; either alone is a hard error; neither produces `Ok(None)` → governor-blind path.

### Intentional, documented design — not a bug

The CLI `--horizon-policy` help text (main.rs:84-91) makes the design explicit:

> When set, `watchbill run` and `watchbill reconcile` invoke `reconcile_phase_with_horizon`, which writes tolerance records on `Defer`, promotes packet Attention to `WatchUntil`, and forwards declarations to Governor via `record_receipt`. Requires `--governor-socket`.

The seam-crossing path is opt-in. The default path is governor-blind. This is intentional, documented design — not an oversight.

## Per-subcommand summary

| Invocation | Governor reachable? | Path |
|---|---|---|
| `watchbill <agenda> <finding>` (no flags) | **no** | `run_watchbill_with_liveness` → `reconcile_phase` → `reconcile_phase_with_horizon` with `governor=None` |
| `watchbill --horizon-policy=X --governor-socket=Y <agenda> <finding>` | **yes** | `capture_phase` → `reconcile_phase_with_horizon` with `Some(JsonRpcGovernorClient)` |
| `watchbill --horizon-policy=X` (no socket) | error (refused) | `bail!("--horizon-policy requires --governor-socket …")` |
| `watchbill --governor-socket=Y` (no policy) | error (refused) | `bail!("--governor-socket requires --horizon-policy …")` |
| `watchbill capture <agenda> <finding>` | **no** (capture phase is governor-irrelevant by design) | `capture_phase` only — no receipt emission at this phase |
| `watchbill reconcile` (with both flags) | **yes** | Symmetric to `watchbill run` path; uses `reconcile_phase_with_horizon` |
| `watchbill reconcile` (without both flags) | **no** | Uses `reconcile_phase` with `governor=None` |

## What this means for the docket order

The next code-level docket item, *if* one wanted to make the default CLI invocation reach `record_receipt`, would be one of:

1. **Make `run_watchbill_cmd` always try to construct a `JsonRpcGovernorClient`** (with sensible defaults / discovery), so the default invocation crosses the seam.
2. **Thread `governor: Option<&dyn GovernorClient>` through `run_watchbill` and `run_watchbill_with_liveness`** as an optional parameter; let callers pass `None` if they don't have one.
3. **Document that the split is correct and operators MUST pass both flags** to get receipt-emitting behavior — the current behavior is a feature, not a bug.

Option 3 is closest to current intent. Options 1 and 2 would widen the surface.

**Critically: until one of these is decided, `unsettled` population in the watchbill path will only reach `record_receipt` on flag-configured invocations.** Teaching Nightshift to populate `unsettled` on `Defer` outcomes today would already work — but only for the configured-CLI / direct-pipeline-function callers, not for the default `watchbill` invocation.

That's the operationally-fake quadrant the user named: improving a path nobody reaches from the default command. The docket-item ordering should therefore handle CLI reachability *before* `unsettled` population, OR explicitly accept that `unsettled` initially lives on the configured-only path.

## Link to `unsettled` population scope

The split classified above bounds where the next code-level slice — teaching Nightshift to populate `unsettled` on `Defer` outcomes — can land. Specifically:

> **`unsettled` population belongs to the horizon-configured path only**, until/unless option 1 or 2 is taken.

Why: `record_receipt` is only invoked from `apply_horizon_outcomes` inside `reconcile_phase_with_horizon`, which is only reached when both `--horizon-policy` and `--governor-socket` are set (or when a non-CLI caller invokes the pipeline functions directly). The default `watchbill` invocation never reaches `record_receipt`, so any `unsettled` semantics on that path silently route through `reconcile_phase` (governor=None) and disappear into the local run-ledger only.

Concrete scope bound:

| Invocation | Will `unsettled` population be observable? |
|---|---|
| `watchbill --horizon-policy=X --governor-socket=Y <agenda> <finding>` | **yes** (via `record_receipt` → Governor's `GateReceipt v4.unsettled`) |
| `watchbill <agenda> <finding>` (default) | **no** (path never crosses the seam) |
| Direct callers of `capture_phase` + `reconcile_phase_with_horizon(Some(governor))` | **yes** (this is what `horizon_packet_state.rs` / `horizon_cross_run.rs` already witness) |

This is consistent with the project's *no fake universal coverage* principle. Initial `unsettled` population lives on the path that can actually emit receipts; the default path remains governor-blind and emits a packet only.

Whoever does the population slice must:
- Populate `unsettled` only in code paths that already hold a `&dyn GovernorClient` reference (i.e., inside `apply_horizon_outcomes` or downstream of it).
- Not silently widen the default path. If the default path needs to emit `unsettled`, that requires the prior docket decision (Option 1 / 2) — and is a separate slice.
- Reuse the typed `NonDischargeKind` enum from `gate_receipt.py` (`UNSETTLED_AUTHORITY`, `UNSETTLED_EVIDENCE_SUFFICIENCY`, `UNSETTLED_FRESHNESS`, `UNSETTLED_SCOPE`, `UNSETTLED_STANDING`, `UNSETTLED_CONSUMER_RELIANCE`). Closed enum, no ad-hoc strings. Same C4 discipline that gates `Check.basis` in the standing validator.

## Doc changes this slice made

To make the split explicit (Option 3 from the prior decision), this session edited:

- `~/git/scheduler/README.md` — quickstart step 6 corrected: the previous *"Record run events; Governor emits authority receipts"* implied unconditional behavior. Revised to call out that Governor receipts are emitted **only with both `--horizon-policy` and `--governor-socket`**, with a pointer to the existing [Authority model](https://github.com/.../scheduler/blob/main/README.md#authority-model) section that already documents which authority levels can run without Governor.
- `~/git/scheduler/crates/nightshiftd/src/main.rs` — `--horizon-policy` and `--governor-socket` help texts extended with explicit default-behavior statements. The `--horizon-policy` help now states *"Without this flag, the default watchbill path is governor-blind"*; `--governor-socket` help states *"Without this flag (and --horizon-policy), no record_receipt calls are emitted"*. Verified `cargo check -p nightshiftd` passes.
- This witness note — the present "Link to `unsettled` population scope" + "Doc changes" sections.

No behavior changed. No new flags added. No JsonRpcGovernorClient constructed by default. No `unsettled` population. No CLI tests added (no `assert_cmd` / `trycmd` harness exists in `crates/nightshiftd/tests/`; doc-only is the path).

## What this session did NOT do

- **Did not** modify any code.
- **Did not** add any tests. The slice's "no tests unless an existing test already directly answers the question" gate held — the existing tests in `horizon_packet_state.rs` and `horizon_cross_run.rs` already exercise the lower path; the CLI question was answered by reading `main.rs` directly.
- **Did not** investigate whether the CLI's `--horizon-policy` default deployment pattern includes both flags or just the agenda path. Operator-side question, not Nightshift-source-code question. Out of scope.
- **Did not** decide between docket options 1, 2, or 3. Classification, not recommendation.
- **Did not** touch the `unsettled` field. Next-next.

## Provenance

Filed 2026-06-09 immediately after [witness-2026-06-09-gate-receipt-unsettled-gap.md](witness-2026-06-09-gate-receipt-unsettled-gap.md) CORRECTION section promoted the lower seam to `witnessed`. Direct reads:

- `~/git/scheduler/crates/nightshiftd/src/main.rs:19-22` (pipeline imports)
- `~/git/scheduler/crates/nightshiftd/src/main.rs:84-100` (CLI flag definitions and help text)
- `~/git/scheduler/crates/nightshiftd/src/main.rs:626-650` (`build_horizon_deps` gate)
- `~/git/scheduler/crates/nightshiftd/src/main.rs:652-728` (`run_watchbill_cmd` body)

No daemon spin-up. No standing-validator work. No `unsettled` population. No "while we're here."
