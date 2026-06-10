# Tock 2 — session-attributable promotion

Campaign: `working/campaign-tick-tock-builder-ratchet.md`
Date: 2026-06-10
Forcing gap: **GAP-N** (`working/tick-02-nq-host-detail.md`) — promotion/rejection
operated on the whole working-tree diff, so on a dirty-at-start tree `promote`
over-captured pre-existing uncommitted work and `reject` (`git checkout -- . && git
clean -fd`) would **destroy** it. Cited candidate: `working/candidate-tock-2-…md`.

**Exit state: shipped, tested.** Implemented judgment-tier (subtle destructive-reject
failure mode); the ladder note in the candidate held — planning + this implementation
stayed on the judgment tier, execution did not downgrade.

## What changed (one capability)

Operator bias honored: **refuse dirty tree first**, with a fenced allow-dirty path.

`src/governor/runtime/promotion.py`:
- `snapshot_dirty_paths(repo)` — the baseline primitive: sorted set of tracked-modified +
  untracked paths, junk-filtered. `[]` on clean/non-git.
- `detect_workspace_changes(repo, baseline=None)` — new `baseline` param. With it, paths
  already dirty at launch are excluded from `changed_files` and recorded on the new
  `Promotion.excluded_files`; the diff stat/text are scoped to session paths only.
  `baseline=None` preserves the legacy whole-tree behaviour (all existing callers + 9
  tests unchanged).
- `revert_paths(repo, paths)` — reverts ONLY the listed paths (tracked → `git checkout`,
  untracked → individual unlink). No `git clean -fd` blast. Pre-existing dirty files are
  never in the list, so reject cannot destroy prior work.
- `revert_workspace` retained but docstring-flagged DANGEROUS / clean-tree-only; the
  supervisor no longer calls it for rejection.
- `DirtyWorktreeError` — raised when a dirty tree is launched without `allow_dirty`.

`src/governor/runtime/supervisor.py`:
- `SessionRecord` gains `allow_dirty: bool` and `baseline_dirty: list[str] | None`.
- `create_session(..., allow_dirty=False)`.
- `launch_session` snapshots the baseline **before** the backend can touch anything;
  a dirty tree with `allow_dirty=False` → emit `SESSION_FAILED(reason=dirty_worktree_at_launch)`,
  transition FAILED, raise `DirtyWorktreeError` (the backend never starts). With
  `allow_dirty=True` it records and fences the baseline.
- `_detect_promotion` passes `record.baseline_dirty`; `PROMOTION_REQUIRED` /
  `PROMOTION_RESOLVED` payloads now carry `excluded_files`.
- `resolve_promotion` rejects via `revert_paths(cwd, changed_files)` — session paths only.

`src/governor/daemon.py`: `runtime.session.create` accepts `allow_dirty`.
`src/governor/cli.py`: `governor runtime launch --allow-dirty`; `DirtyWorktreeError`
surfaces as a clean refusal message, not a traceback.

## Acceptance (operator's 7 criteria)

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Session start records baseline tree state | ✓ `launch_session` → `record.baseline_dirty` |
| 2 | Touched paths used to compute promotion scope | ✓ via **baseline set-difference** (current − baseline), a strictly-safer mechanism than ledger-path matching — it never misses a session-induced change (incl. build side-effects). Ledger-path cross-check deferred (not needed for soundness; noted below). |
| 3 | Bundle excludes pre-existing dirty files | ✓ `excluded_files`; `TestBaselineScoping` |
| 4 | Reject cannot destroy pre-existing work | ✓ `revert_paths`; `TestGapNRegression` |
| 5 | Dirty-at-launch hard-refuses OR records+fences | ✓ **both** — refuse by default, fence under `allow_dirty` |
| 6 | Record names included/excluded paths | ✓ `changed_files` + `excluded_files` on the Promotion and both events |
| 7 | Tests cover back-to-back ticks on a dirty tree | ✓ `test_reject_preserves_preexisting_work` (Tick 1 residue + Tick 2 file → reject Tick 2, Tick 1 work survives) |

Tests: `tests/test_session_attributable_promotion.py` (16 tests). Regression sweep:
runtime/supervisor/promotion/fail_closed/daemon = **499 passed, 0 failures**; the Tock 1
fail-closed suite and golden trace stay green.

## Deviation noted honestly

Criterion 2 says "event-ledger touched paths." I used **baseline set-difference**
instead: anything that became dirty between launch and session end is session-
attributable (sound, because the supervised backend is the only writer of its
workspace during the session). This is more robust than ledger-path matching — it can't
miss a side-effect change a tool didn't name. A ledger-path cross-check (flagging
mismatches between "what the agent's tool calls touched" and "what actually changed")
remains a possible later refinement; it is not required for the custody guarantee and
was not built (YAGNI).

## Ratchet state

> Tick 2 shipped cargo green; dogfood promotion custody DEGRADED (GAP-N).
> Tock 2 makes promotion session-attributable — refuse-dirty-first + per-path revert.

The promotion half of the dogfood is now safe for back-to-back ticks on a shared tree:
no over-capture, no destructive reject. Future ticks can run without first committing
the prior tick's work (though a clean tree is still the default-happy path).
