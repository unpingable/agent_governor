# Status — governed shell

As of 2026-07-02.

## Done

- **GS-0** — campaign filed; four design docs landed
  (`docs/design/governed-shell/`): loop-ux (the desk, four screens,
  interrupt/accumulate, refusal routes, day-in-the-life), shell-contract-v0
  (CANDIDATE), maude-boundary (executes R-MAUDE-3), phosphor-lanes (LaneSpec
  machinery for R-PHOS-2).
- **GS-1** — decision envelope + watch vocabulary minted in
  shell-contract-v0.md (CANDIDATE until GS-2/3 implement against it).
- Operator ratifications D-GS-1..4 recorded; R-MAUDE-2 narrowed (D-GS-8).

## 2026-07-02 night — GS-2a landed

`src/governor/operator_decisions.py` + 15 tests on main (commit caaa036):
the pure decision-feed aggregator per shell-contract §1-2. Authored by codex
as generator (read-only scribe protocol — codex sandbox cannot write in this
environment; scribe extracts, fixes, verifies). governor verify-run receipt
f00a7f11 [pass]. Remaining for GS-2: daemon registration + docket/
admissibility read RPC + HELD-launch state (GS-2b). GS-3/4/5/6 unstarted.

## Current next

Daemon slices unblocked: **GS-2** (decisions.list + docket/admissibility
reads), then GS-3 (resolve, sandwich); GS-4 (watch), GS-5 (send_input,
sandwich), GS-6 (exposure batch) independent. GS-7 (autopilot RPC) deferrable.
GS-8 (ag_shell_client extraction) after GS-1 → unlocks both shell tracks.

## Blocked / waiting

- GS-16/17 (phosphor) wait on R-PHOS-1 compat audit (reconciliation campaign
  A7-adjacent) in addition to their GS prereqs.
- D-GS-7 (reattach) needs its verify-first probe before anything depends on it.

## Not touched (deferred, named)

AG-minted widening offers (D-GS-4, successor campaign). Existing phosphor mode
conversion (D-GS-3, separable slice). Ops-casework lane content (operator's
R-PHOS-2 half). Notifier consuming operator.watch (out of scope).
