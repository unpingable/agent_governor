# Obstruction — GS-2b remainder: admissibility_question source + HELD-launch state

**Filed:** 2026-07-03 · **Slice:** GS-2b (daemon DaemonState plumbing)
**Status:** BLOCKED — re-tier as authority-semantics work (not exposure-only plumbing).

## What landed in this slice

The `docket_case` source is now wired into the unified operator feed
(`_gather_operator_feed` in `daemon.py`, via `DaemonState.docket_manager` and
`build_feed_from_runtime(docket_cases=...)`). It mirrors the CLI docket idiom
(`cli.py` docket_list): a staleness detector over an epistemic ledger + the
on-disk docket state, bound **without** a violation resolver so a live contested
violation is not double-surfaced (it stays a `violation` item; the docket
contributes only stale/persisted `docket_case` items).

The other two GS-2b remainder items — `admissibility_question` source and
**HELD-launch state** — are NOT wired. Each hits a documented stop condition.

## Why admissibility_question is blocked (no native pending-queue object)

The decision envelope's `admissibility_question` kind expects a native pending
object with a `native_id` per item (mints-nothing discipline). The
admissibility subsystem does not expose one:

- `admissibility.assess_task(...)` is a **pure function** returning an
  `AdmissibilityAssessment` with a list of `Unknown`s. It is not a live queue.
- `AdmissibilityStore` (admissibility.py) persists per-`run_id` blobs:
  `{run_id}_unknowns.json`, `{run_id}_assumptions.json`, `{run_id}_waivers.json`,
  `{run_id}_assessment.json`. It has `load_unknowns(run_id)` but **no accessor
  for "questions still pending an operator answer."**
- "Pending question" = "an `Unknown` with no covering `Assumption`/`Waiver`" is a
  **derived predicate** that does not exist as a native method. Exposing it means
  *defining* what "pending admissibility question" means at the daemon — that is
  new semantics, not plumbing.
- There is no session→run_id linkage on `DaemonState`, and no `AdmissibilityStore`
  instance on the daemon. Nothing currently makes an admissibility question
  "pending for session X."

Building the pending-question accessor is the forcing-case work that must precede
any feed wiring. Until an admissibility *question queue* exists as a native
object, the aggregator has nothing faithful to mirror.

## Why HELD-launch state is blocked (changes an admission decision)

Shell-contract §6 ("HELD launch state, new, GS-2"): *"a session created while
admissibility questions pend reports `status: "held"`; answering the last
question (via the door) transitions it to launchable. Exposure alone was
insufficient — something must hold the launch."*

That last sentence is the tell: HELD-launch is **not exposure**. It requires:

1. A new `SessionStatus` member `HELD`. The current closed enum
   (`runtime/supervisor.py`) is `{created, launching, attaching, running,
   paused, exited, failed}` with a fixed transition table — no `held`.
   → **Stop condition: "If a missing field requires new vocabulary, STOP."**
2. `runtime.session.create` / `runtime.session.launch` consulting pending
   admissibility questions and *withholding* the launch. Today `create` returns
   `record.status.value` and `launch` calls `sup.launch_session` unconditionally
   — neither consults admissibility.
   → **Stop condition: "If wiring changes a refusal/admission decision, STOP and
   re-tier as authority-semantics work."** Holding a launch IS an admission
   decision.
3. A release transition wired to the resolve door's admissibility-answer path
   (shell-contract §3: "releases HELD launch when last question answered") —
   which itself depends on (the missing) admissibility question queue.

HELD-launch is a genuine admission gate, not a rendering surface. It belongs in
an authority-semantics slice with its own review, not in GS-2b plumbing.

## Resolve interaction (recorded, not fixed here)

Because `docket_case` items now appear in the shared feed, they are reachable by
`operator.decisions.resolve` (which re-derives `_gather_operator_feed`). The
resolve route for docket rulings (`DocketManager.rule_*`, shell-contract §3) is
**GS-3-remainder** — a mutation/authority sandwich, deliberately not wired here.
The door therefore **fails closed** on a `docket_case`: it raises a structured
error, mutating nothing. Docket rulings continue to go through `governor rule` /
the docket surface until GS-3 opens the route. This is intentional fail-closed
behavior, pinned by `test_operator_decisions_rpc.py`.

## Re-tier

- `admissibility_question` source → blocked on a **native pending-question
  accessor** (admissibility subsystem work; define "pending" before wiring).
- HELD-launch → **authority-semantics slice** (new `SessionStatus.HELD` +
  admission consultation on launch + release-on-last-answer). Own forcing case,
  own review; depends on the admissibility question queue above.
- docket_case resolve route → **GS-3-remainder** (mutation sandwich).

No new vocabulary was invented in GS-2b to paper over these. The envelope already
reserves both kinds; they stay empty until their native sources exist.
