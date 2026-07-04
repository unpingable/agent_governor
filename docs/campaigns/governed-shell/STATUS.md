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

## 2026-07-03 — maude repositioning pass (maude repo) + GS-8b filed

Operator ruling executed in the maude repo (commits 9e20d4b..ae17ffd): maude
reframed as the plan-only executor — docs Phase 0 landed (README/pyproject/
architecture/commands/COMPAT reframe, chat marked unsupported legacy per
D-GS-2, chat-era docs archived, dead http.py deleted, roadmap rewritten with
the plan-executor spine M-1..M-5 and the two-ingress tail M-6/M-7). New
operator law recorded there: synthetic agent-led maude is a first-class
**submitter** path, not a separate authority path (maude
docs/REPOSITIONING.md).

**GS-8b filed** (this file's NEXT.md): ag_shell_client needs a live-socket
client class (lib is codec + models only) before GS-9 can consume it; GS-9
prereq updated to [GS-8b]. Also: roadmaps/tools/maude.md §0 adapter-ownership
line corrected to match the ratified boundary (D-GS-5).

## 2026-07-03 — GS-7 landed (autopilot RPC; daemon shell surface complete)

`runtime.autopilot.get` (read-only envelope strip) + `runtime.autopilot.set`
(workspace-default profile switch) on main. `get` mirrors `governor intent show`
truth; `set` reuses the existing `set_intent` + `apply_autopilot_profile`
machinery (same operation as `governor code --profile`), emits a profile-change
gate receipt (`gate="autopilot"`) citing the operator via the canonical
`resolve_principal` path, and refuses an unknown profile with the closed
`unknown_profile` vocab. Method count 99.

Stop condition (no per-RUNNING-session envelope mutation) proven, not asserted:
grep confirmed the runtime supervisor never reads the autopilot/intent/envelope
files, pinned by a booby-trap test that raises on any supervisor access. `set`
is workspace-scoped only — a `session_id` key (any value) is rejected at the
mechanism layer.

FULL SANDWICH: codex-exec BLOCK (receipt swallowed after write → a change could
succeed unreceipted) → fixed (emission no longer swallowed; success requires the
receipt; workspace write is idempotent so a receipt failure is loud + retryable)
→ WARNs folded (key-presence session_id guard; `changed` reflects the actual
delta; fail-closed-when-standing-required test proving the operator isn't
forgeable) → MERGE-SAFE. verify-run receipt `8316dec3` [pass]; 10 slice tests +
324 in the daemon band green.

GS-7 was the last buildable AG-daemon governed-shell slice. Remaining AG-side:
GS-2b re-tiered items (admissibility/HELD — authority-semantics) and GS-3 docket
resolve route (mutation sandwich). Maude track (GS-8b→GS-9..15) is the sibling
session's; phosphor (GS-16/17) waits on R-PHOS-1.

## 2026-07-03 — GS-8b landed (ag_shell_client live-socket client — GS-9 UNBLOCKED)

`AsyncDaemonClient` (`libs/ag_shell_client/src/ag_shell_client/client.py`): the
missing connection layer over the GS-8 codec. `connect`/`call`/`stream`/`aclose`
+ `async with`; `StreamItem` (notification|result terminal); one-in-flight-per-
connection busy guard (a second concurrent request fails fast, never interleaves
frames — matches the daemon's sequential-per-connection service and the
contract's "dedicated second connection for watch"); `-32001 → DaemonAuthError`.
Async (`asyncio.open_unix_connection`) — what maude (Textual) and phosphor
(FastAPI) both need; the in-repo sync `cli_backend` still covers the CLI.

Wire proven against the real daemon: 31 tests (fake-reader unit for id-match /
notification-skip / typed-error mapping / stream / busy-guard / poisoning /
verbatim-params, + live `serve_unix` smoke: `governor.hello` round-trip and
`operator.watch` stream). Package tests made self-contained (`pyproject`
`pythonpath=["src"]`) so the bare command runs from repo root. Codex wire-review
(3 passes): BLOCK (id-less error frame skipped → hang) + 5 WARN → fixed
(surface-not-skip errors, fail-closed desync, connection poisoning on
timeout/cancel/foreign-error/early-stream-close, gen-guarded deterministic
release, optional stream read-timeout, verbatim params) → MERGE-SAFE. verify-run
`29620c95` [pass].

**This unblocks GS-9** (maude replaces its hand-rolled client with the package)
for the sibling maude session.

## 2026-07-03 — GS-3 docket resolve route landed (the one door now covers docket)

Closed the completeness gap GS-2b opened: docket cases were listable but the one
mutation door failed closed on them. Now `operator.decisions.resolve` routes a
`docket_case` to `DocketManager.rule_*` — the returned precedent IS the record,
the door mints nothing. Options are gated on case_type in the aggregator
(CONTESTED → sustain/amend/grant_exception; STALE → reverify/dismiss; unknown →
none), so the door never receives a ruling the case type would reject — that
pairing is unrepresentable in the feed, not merely guarded. Idempotence (v0): a
ruled case drops from the re-derived feed → re-resolve is `decision_not_found`.
No privilege escalation: the case number is the source native_id (not a caller
field), and `grant_exception` scope is fixed at the narrowest `single_instance`
(forged `args.scope` cannot broaden the exception). FULL SANDWICH (mutation
door): codex BLOCK (caller-controlled scope) + WARN + NIT → all RESOLVED →
MERGE-SAFE. verify-run `cdd283ce` [pass]; 386 in the operator/docket/daemon band
green. The one door now covers all four sourced kinds (intervention/violation/
promotion/docket_case); only GS-2b's re-tiered admissibility/HELD remain AG-side.

## Current next

Daemon slices unblocked: **GS-2** (decisions.list + docket/admissibility
reads), then GS-3 (resolve, sandwich); GS-4 (watch), GS-5 (send_input,
sandwich), GS-6 (exposure batch) independent. GS-7 (autopilot RPC) deferrable.
GS-8 (ag_shell_client extraction) after GS-1 → unlocks both shell tracks.

## Blocked / waiting

- GS-16/17 (phosphor) wait on R-PHOS-1 compat audit (reconciliation campaign
  A7-adjacent) in addition to their GS prereqs.
- D-GS-7 (reattach) needs its verify-first probe before anything depends on it.

## 2026-07-03 — GS-9 landed (maude repo; GS-10 unblocked)

Maude now consumes `ag_shell_client` (maude `f143efc`). Deleted maude's
duplicated `client/transport.py` (Content-Length framing + socket-path
derivation); rewrote `client/rpc.py` as a thin typed surface over
`AsyncDaemonClient`. Kept maude's Pydantic rendering models + the typed
method surface (one module naming every RPC method maude calls — the record
R-MAUDE-1 wants; not scattered into the untested app.py monolith). Handles
the one-in-flight contract: unary calls lock-serialized on one connection so
the 5s poll can't trip the busy guard; `chat.stream` on a dedicated
connection; poisoned connection dropped + reconnected. Verify: bare pytest
156 passed / 24 skipped exit 0; ruff clean; live degraded-daemon smoke 22/24.

The 2 non-passes are NOT transport regressions: 1 pre-existing chat-stream
skip; 1 **daemon-behavior drift** — `intent.compile` returns
`escape_classification=None` where maude's integration test expects
`waiver_candidate` (the full result deserializes; only a daemon-side field
value differs). Filed to **R-MAUDE-1** (RPC surface-diff): decide whether the
daemon regressed or the test expectation is stale. Left failing under
`test-with-governor.sh`, not silently re-asserted.

Maude track now at GS-10 (ScreenManager + CommandRegistry; chat/PLAN/BUILD
quarantine to `commands/legacy.py`).

## Not touched (deferred, named)

AG-minted widening offers (D-GS-4, successor campaign). Existing phosphor mode
conversion (D-GS-3, separable slice). Ops-casework lane content (operator's
R-PHOS-2 half). Notifier consuming operator.watch (out of scope).
