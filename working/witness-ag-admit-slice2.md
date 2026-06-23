# Witness — ag-admit Slices 0–2 (governed self-build loop)

Date: 2026-06-23. Campaign: `working/campaign-ag-admit-self-build.md`. Plan:
`~/.claude/plans/abstract-brewing-hippo.md` (operator-approved).

## Two verdicts

### DOGFOOD verdict: **HELD**

A dumb step runner carried a `CandidateStep` through AG's existing admission seam
(`governed_dispatch.PreflightClient` Protocol, in-process) and produced a witnessed
`refuse → repair → admit → execute → commit` cycle on a real throwaway git repo, with the
whole trace **reconstructed from receipts alone** and the final commit **causally linked**
to the admission receipt (`admission_receipt_id` in the commit receipt + an
`Admitted-By-Receipt:` commit-message trailer).

Evidence: `tests/test_ag_admit_conductor.py::test_slice2_toy_trace_refuse_repair_admit_commit`
asserts the receipt sequence
`step_admission(block) → step_repair(observe) → step_admission(proceed) →
step_execution(pass) → step_commit(pass)`, the causal link, and the trailer.

The refusal was an **authority** refusal (an observed forbidden path), not hygiene — the
gate derived the touched path from the diff and refused `path_out_of_scope`; the conductor
only obeyed the verdict.

### CARGO verdict: **PASS** (for this campaign's deliverables)

- Slice 0: `tests/test_ag_admit.py` — **26 passed**.
- Slice 1+2: `tests/test_ag_admit_conductor.py` — **5 passed**.
- Full suite: **16032 passed, 62 skipped, 1 failed**. The single failure is
  `test_qa_self_governance.py::...::test_pyproject_version_matches_latest_git_tag`
  — **pre-existing version/tag drift** (`pyproject 2.8.1` vs latest tag
  `stage3b2-first-effect`), unrelated to this work (no edit to `pyproject.toml` or tags).
  Not a regression introduced here.

Verifier-discipline note (a live instance of the scar): the background run's reported
"exit code 0" was the trailing `echo`, not pytest — `PIPESTATUS[0]` exposed the real `1`.
Pass/fail was decided by the observed pytest status, never by eyeballing the tail.

## Acceptance scorecard (operator's conditions, this session)

1. Toy gate = path-authority on touched paths, **observed from the diff, not from
   `CandidateStep.touched_paths`** — ✅ (`test_gate_ignores_declared_touched_paths_for_decision`).
2. `ScopeGovernor` untouched; no `EscalationVerdict` import; local source verdicts — ✅
   (`test_no_scope_governor_import`, AST-checked).
3. `StepVerdict` typed enum now; projection centralized in `ag_admit`, not the conductor
   — ✅ (`project_source_verdict`; `test_slice1_conductor_has_no_diff_parsing`).
4. Unknown/unmapped source verdict → `CANNOT_TESTIFY` (never best-effort) — ✅
   (`test_unknown_never_projects_to_reject_or_needs_human`).
5. `NEEDS_HUMAN` only on explicit `REQUIRE_HUMAN`; conductor never rewrites
   `CANNOT_TESTIFY` → `NEEDS_HUMAN` — ✅ (`test_needs_human_only_on_explicit_require_human`,
   `test_missing_source_verdict_cannot_testify_not_needs_human`,
   `test_slice1_cannot_testify_does_not_mutate_or_escalate`).
6. POSIX path hardening (absolute / `..` / empty / escape → `CANNOT_TESTIFY`) — ✅
   (`test_unsafe_paths_cannot_testify`).
7. Source-verdict rides in `raw.source_verdict`; projection never reads the coarse wire
   `decision` — ✅ (BLOCK vs CANNOT_TESTIFY both `decision="blocked"`, project distinctly).
8. No "best effort" commit after refusal; zero mutation receipts on refusal — ✅
   (`test_slice2_no_mutation_receipts_when_refused`).

## Disposition / open decision

- Slices 0–2 complete and green. Ready to commit on the operator's signal (no push —
  work-hours rule; and `main` already carries ~11 unpushed commits from the AG-on-AG
  campaign — see `.governor/loop.json`).
- **`.governor/loop.json` deliberately NOT touched** — it carries another campaign's
  WIP-1 state (AG-on-AG self-hosting). Folding an ag-admit slice entry into it is an
  operator call (WIP-1 discipline), not a silent edit.
- Slice 3 (waiver-completeness dogfood) PARKED behind a witnessed promotion note.
