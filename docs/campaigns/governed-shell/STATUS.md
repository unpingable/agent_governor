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

## 2026-07-03 — GS-2b core landed

`operator.decisions.list` read-only RPC on main (`a28d727`): unified feed
over supervised interventions + promotions + pending violation via the
hardened aggregator (`build_feed_from_runtime`). Sandwich MERGE-SAFE.
Deferred (need DaemonState plumbing): docket + admissibility sources +
HELD-launch state = GS-2b remainder. GS-4/5/6/3 not started.

## 2026-07-03 overnight — GS-4/5/6/3 + GS-8 landed

The daemon shell surface is now built out and the client library extracted.
All on main, each slice verify-run-gated + (for mutation/authority surfaces)
codex-exec sandwiched to MERGE-SAFE.

- **GS-4** `operator.watch` (`3fe0acb`) — bounded streaming decision feed;
  emits `operator.watch.update` on the opening snapshot + on content change
  (stable-projection digest excluding display-clock fields); `notify` wrapped
  in a timeout so a stalled client can't outlive the loop bound. Sandwich
  BLOCK→MERGE-SAFE (kinds validation, notify bound, digest churn).
- **GS-5** `runtime.session.send_input` + `OPERATOR_INPUT` event (`a698abd`) —
  operator text into a running session; fail-closed at every gate
  (empty/no-session/no-handle/not-running/no-capability/backend-reject), never
  a silent drop. Sandwich BLOCK×2→MERGE-SAFE.
- **GS-6** exposure batch (`f3294e4`) — `runtime.adapters.list` (declared
  capabilities), `why.chain` (receipt chain-walk over the daemon),
  `session.get` now carries `capabilities`/`input_capable`. Read-only.
- **GS-3** `operator.decisions.resolve` (`cd11091`) — THE one mutation door;
  routes by trusted-feed item kind + option action to the backing handler
  (intervention/promotion/violation); forwards (routed receipt IS the receipt),
  mints nothing, adds no refusal vocabulary. FULL sandwich BLOCK→MERGE-SAFE
  (codex confirmed no privilege escalation via forged args). v0 boundary:
  already-resolved → decision_not_found (richer replay needs a resolution
  ledger, deferred).
- **GS-8** `libs/ag_shell_client/` (`76397d6`) — de-triplicated wire protocol
  (socket path proven byte-identical to the daemon) + typed decision models
  with the safe-defaults idiom. Sandwich MERGE-SAFE.

Daemon method count 91→97. GS-2b remainder (docket + admissibility sources +
HELD-launch state) still deferred on DaemonState plumbing. GS-7 (autopilot RPC)
and GS-9 (maude consumes ag_shell_client — separate-repo UX) not overnight.

## 2026-07-03 — GS-2b docket source landed (remainder partially closed)

`operator.decisions.list` / `operator.watch` now source **docket cases** via
`DaemonState.docket_manager` (mirrors the CLI docket wiring: staleness + on-disk
state, NO violation resolver → a contested violation is not double-surfaced).
`build_feed_from_runtime` gained a `docket_cases` passthrough. Docket items are
listable; their resolve route (`DocketManager.rule_*`) is GS-3-remainder, so the
one door **fails closed** on `docket_case` (structured error, nothing mutates) —
pinned. verify-run receipt `b9cbbebb` [pass], 33 slice tests + 616 in the
operator/docket/watch band green.

Still deferred — filed as an obstruction (`OBSTRUCTION-gs2b-admissibility-held.md`):
**admissibility_question** (no native pending-question accessor — "pending" is a
derived predicate, not a queue object) and **HELD-launch state** (needs a new
`SessionStatus.HELD` + admission consultation on launch = authority-semantics
work, re-tiered out of exposure-only plumbing).

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
