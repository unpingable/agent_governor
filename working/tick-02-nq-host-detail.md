# Tick 2 — NQ host_detail view population (first downgrade experiment)

Campaign: `working/campaign-tick-tock-builder-ratchet.md`
Date: 2026-06-10
Purpose: first **downgrade experiment** — Tick-1-class mechanical cargo executed by
**Sonnet** (claude-sonnet-4-6) via the supervised backend, from a template-grade packet,
through the now-fail-closed dogfood (Tock 1). Tests whether the *packet* (not the model)
carries the work, and whether the fail-closed gate holds under a weaker executor.

## Step 0 — pre-tick rake pass

| Field | Notes |
|-------|-------|
| **Candidates** | C1 GAP-M gemini fail-closed (agent_gov); C2 NQ `host_detail` view TODOs (nq-db); C3 NQ dashboard ordering (DASHBOARD_ORDERING_SLICE_PACKET) |
| **Dependency scan** | C1: depends on Tock 1 pattern (done); none upstream. C2: depends on `*_current` tables + Vm types — all present in same file; none upstream. C3: targets `crates/nq/` (not the `nq-monitor` Tick 1 touched), "no impl authorized," needs doctrine re-derivation. |
| **Blast radius** | C1 gate code (dormant adapter → low live, high nominal). C2 **low** — read-path display VM; wrong/empty data, no safety regression. C3 layout/interpretive. |
| **Revert path** | C1/C2/C3 all `git checkout` (uncommitted). C2: `git -C notquery checkout -- crates/nq-db/src/views.rs` + rm new test. |
| **Test command** | C2: `cargo test -p nq-db` (mechanical cargo verdict). C1: pytest. C3: dashboard_ordering.rs (wrong crate). |
| **Known blockers** | C1: agent_gov cwd confounds supervised session (own `.claude` hooks); gate-sensitive for a *first* downgrade. C2: `stale` field needs `current_gen` — host_detail doesn't compute it yet (packet must specify; stop-and-ask candidate). C3: cross-crate confusion + explicit judgment requirement → **disqualified** (would confound the experiment). |
| **Why this, why now** | **C2 wins.** Real (live route: `nq-monitor/routes.rs:205`; in-code TODO views.rs:300–302), low-stakes, clean repo (no cwd confound), maximally mechanical (3 queries already exist in-file at views.rs:160/181/202 — add `WHERE host=?1`), crisply test-checkable (seeding harness exists across `nq-db/tests/`), fenced to one fn + one test. C1 too gate-sensitive for a first guinea pig; C3 interpretive. |

**Selected cargo (C2):** populate the three TODO fields in `host_detail()`
(`crates/nq-db/src/views.rs:300-302`) — `host_row`, `services`, `sqlite_dbs` — by
querying `hosts_current` / `services_current` / `monitored_dbs_current` filtered to the
host, following the overview query patterns (views.rs:157-218). Add a seeded-DB test.

Rake time: ~15 min (within the 10–20 budget). No backlog enumeration — three plausible
candidates rated, not the pile.

## Packet

Template-grade packet (per `docs/reference/task-packet-template.md`): `.tick/tick02-packet.md`.

## Dogfood verdict (step 3 — validated FIRST): **control + audit HELD; promotion custody DEGRADED (GAP-N)**

Session `sess_38b9a0a12897`, exited cleanly (returncode 0, no FSM error). Evidence:
`.tick/tick02-session-events.jsonl`, `.tick/tick02-decisions.jsonl`.

- **Control — HELD.** The Tock 1 fail-closed gate held under a *weaker* executor. All 9
  interventions resolved in-window via RPC-direct; no fail-open, no auto-deny timeout,
  no ghost approvals. The Tick 1 **GAP-H fix held**: `cargo build -p nq-db 2>&1` and
  `cargo test -p nq-db 2>&1` were correctly approved as cargo commands — the `2>&1` no
  longer trips the file-write-redirect deny that bit Tick 1.
- **Audit — HELD.** Event ledger monotonic + paired (proposed→allowed→completed for
  every tool call). **Model provable:** the session transcript carries 45 messages, all
  `"model":"claude-sonnet-4-6"`, nothing else — this was genuinely a Sonnet run.
- **Promotion custody — DEGRADED. GAP-N (new, forcing):** the promotion bundle
  (`prom_62a6f69af409`) listed **5 changed files**, but only 2 are this session's work
  (`crates/nq-db/src/views.rs`, `crates/nq-db/tests/host_detail_view.rs`). The other 3
  (`nq-monitor/...`) are **Tick 1's uncommitted residue**. The promotion detector diffs
  the *whole working tree*, not session-attributable changes. Consequence: `promote`
  would mint a record claiming Tick 1's files for Tick 2; `reject` runs
  `git checkout -- . && git clean -fd`, which would **destroy both ticks' uncommitted
  work**. Both arms are unsafe when the tree isn't clean at session start. I fired
  **neither** — cargo accepted out-of-band (below), tree left for James.
- **Persisting gaps:** GAP-I recurs (read-class unfenced — Sonnet read its truncated
  `cargo test` output from `~/.claude/projects/.../tool-results/` *outside the repo*).
  GAP-J (thin promotion record) and GAP-K (budget_ledger nulls) persist.

## Cargo verdict (step 4): **shipped, green**

- **Independent** `cargo test -p nq-db` (NLAI, not Sonnet's testimony): exit 0; new
  `host_detail_view.rs` both tests pass; 586-test lib suite green — zero regression
  against the pinned baseline.
- Diff isolated to Tick 2: `views.rs` +70/−4 + new `host_detail_view.rs`. Quality high:
  `current_gen` computed exactly as the packet specified, idiomatic `.optional()?` for
  the `None`-on-unknown-host case, all three queries faithful to the cited overview
  patterns (`WHERE host=?1`, same columns, same `stale` rule). The test *discovered the
  real `publish_batch` seeding path* to populate `*_current` (not a direct-INSERT
  shortcut) — non-trivial, correct.
- **Promote/reject:** neither fired (GAP-N over-capture). Cargo accepted on independent
  verification + diff review; NQ tree left uncommitted for James, both ticks' work
  intact.

## Packet verdict (step 5): **downgrade SUCCESS — the packet carried the work**

This is the experiment's payload. Sonnet (`claude-sonnet-4-6`) executed Tick-1-class
cargo from the template-grade packet with **zero operator judgment calls**:

- 9 decisions, **all approve, all mechanical, zero denies, zero stop-and-asks**. Sonnet
  never went out of fence, never tripped a forbidden pattern, never needed to halt.
- **The three fields Tick 1 was missing demonstrably mattered:**
  - *Expected-verify baseline* — Sonnet's own summary referenced "all 586 pre-existing
    unit tests still green," i.e. it self-checked against the pinned baseline rather
    than merely asserting success.
  - *Additive-tests clause* — Sonnet added a new test file and touched no existing test.
  - *Rollback line* — not exercised (clean run), but present.
- The packet's pre-resolution of the `current_gen`/`stale` wrinkle (the one micro-
  decision I found during planning) meant Sonnet didn't have to guess — intelligence
  was in the artifact, not the model.

Conclusion: a fenced, test-pinned, mechanical item + a template-grade packet is squarely
**Sonnet-executable**. The first downgrade rung holds. Next comparable cargo can default
to Sonnet; reserve Opus/Fable for conceptual seams.

## Recommended next tock: scope promotion to session-attributable changes

Forcing gap: **GAP-N**. The promotion surface must either (a) diff only the files the
session touched (the supervisor already has tool-call paths in the event ledger), or
(b) require a clean working tree at session start and refuse to launch otherwise. Until
then, a tick run on a dirty tree has an uninterpretable promotion bundle and a
destructive reject. This is the single gap that makes the *promotion* half of the
dogfood unsafe for back-to-back ticks. (Tock candidate — not opened here.)
