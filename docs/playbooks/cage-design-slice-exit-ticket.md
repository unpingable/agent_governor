# H-series cage-design slice — exit ticket

**Done 2026-06-30** (branch `feat/playbooks-synthetic-conveyor`). The contract-first cage
slice authorized by the harness-cage review (operator pass, 2026-06-30). Lives in the
external `harness/` lane, **outside the governor package**. Refuse-live only — **no live
actor, no real cage backend, no H2.**

> The cage gets a constitution before it gets a keycard.

## Files

- `harness/cage.py` (new) — cage contract + `RefusingCage`/`NoLiveCage` + typed refusals
  + audit-store layout + one-artifact boundary. **Stdlib only; no `import governor`.**
- `tests/harness/test_cage_contract.py` (new, 29 tests) — refuse-live, XDG audit layout,
  one-artifact boundary, no-AG-crawl.
- `tests/harness/conftest.py` (new) — adds repo root to `sys.path` for `tests/harness/`
  only (the harness is not an installed package); no global config change.
- `harness/README.md` — cage section added.

Harness + playbooks regression: **263 passed, exit 0** (229 playbooks + 34 harness).
Full collection 16451, exit 0.

## What the slice fixes (the three ratified terms)

### 1. Refuse-live by attestation, not by hardcode
`HarnessCage` is a `Protocol` with **no execution method** (no `run`/`spawn`/`stream`) —
admission is a decision, not an invocation. A cage may admit a live actor only if its
`CageAttestation` *confirms isolation* in `live` scope. `RefusingCage` attests nothing
(`confirms_isolation=False`, `scope=none`), so `evaluate_live_admission` refuses with a
typed `refusal_code` (`live_admission_refused_no_isolation_attested`).

Live admission is **structurally unreachable**, not special-cased:
- `CageAttestation.__post_init__` forbids `confirms_isolation=True` outside `live` scope
  (no half-confirmed cages) — `test_live_admission_is_structurally_unreachable`.
- No shipped backend attests live isolation, so no `LiveAdmission(admitted=True)` is
  reachable in this slice (the admit branch is `# pragma: no cover`).

`require_live_admission()` is the fail-closed wrapper: it **raises** the typed
`LiveAdmissionRefused(code=...)` for callers wanting a hard gate.

### 2. Audit-store layout, outside AG
`audit_store_root()` → `$XDG_STATE_HOME/agent-gov/harness-runs/` (fallback
`~/.local/state/agent-gov/harness-runs/`); `run_dir(run_id)` is a per-run dir under it.
**Pure path computation — writes nothing** (`test_run_dir_is_under_the_store_and_pure`).
`run_id` must be a single safe segment — traversal / separators / dotfiles refused
(`AuditPathError`), so a run dir can never escape the store into AG. The store resolves
outside the repo (`test_audit_store_is_outside_the_ag_repo`).

### 3. One-artifact AG-ingest boundary
`assert_ag_ingestible()` admits only `actor_output.v0` and refuses everything else —
diff / diff_reference / review_test_result / verifier_result / bundle / `actor_output.v1`
— with typed `NonIngestibleArtifact`. Absence-restrictive: anything not on the one-item
allowlist is refused.

## No AG crawl / import (the wall from AG's side)
`test_ag_governor_does_not_reference_the_audit_store_or_harness` statically scans
`src/governor/**.py` for `harness-runs` / `import harness` / `from harness` /
`harness.cage` — **none.** AG cannot crawl a store it has no name for, and ingests only
an explicit `actor_output.v0` (H1's fail-closed `ActorOutput.from_dict`, file-scoped —
never a directory).

## Acceptance — all met

| Criterion | Evidence |
|-----------|----------|
| Live admission through `RefusingCage` refused with a typed refusal | `test_refusing_cage_refuses_live_admission_typed`, `test_require_live_admission_raises_typed_refusal` |
| Refusal is test-covered | 9 refuse-live tests |
| Harness computes the audit-store path without writing into AG | `test_audit_store_root_uses_xdg_state_home`, `..._falls_back_to_home`, `test_run_dir_is_under_the_store_and_pure` |
| No AG crawl/import of the audit store | `test_ag_governor_does_not_reference_the_audit_store_or_harness` |
| No artifact besides `actor_output.v0` AG-ingestible | `test_only_actor_output_v0_is_ag_ingestible`, `test_non_envelope_artifacts_are_refused` |
| Full relevant tests pass | 263 passed, exit 0; collection 16451 |

## Intentionally NOT done (stop line held)

- No live actor execution; no subprocess runner that executes an actor; no transcript
  streaming; no `runtime.adapters.claude_code`.
- **No Docker/Podman/bubblewrap backend** — only the refusing backend ships. bubblewrap
  remains the *named, not authorized* first real Linux backend to evaluate later.
- No verifier results, no `ReviewTestResult`, no diff-reference field, no auxiliary
  bundle imported into AG (enforced by the existing AST scans + the one-artifact guard).
- No loop / autopilot. No H2.

## Next possible work (do NOT start without operator go)

A **real cage backend** (bubblewrap first to evaluate) is a separate, later,
separately-ratified gate — it must *truthfully* attest isolation before any
`LiveAdmission(admitted=True)` is even reachable, and even then live actor execution (H2)
is yet another gate. The contract is now in place to receive such a backend; the keycard
is not issued.
