# Replay — ag-admit self-build

Copy-paste executable from the repo root (`/home/jbeck/git/agent_gov`). Verifier
discipline: run bare so the **observed exit code is the verdict**; never pipe the runner
through `tail`/`grep` (a pipeline returns the last command's exit code). Use `python3`,
not `python`, on this system.

## Slices 0–2 (toy loop)

```bash
python3 -m pytest tests/test_ag_admit.py tests/test_ag_admit_conductor.py -q
```
Expect: all green, exit 0. (`test_ag_admit.py` = 26, `test_ag_admit_conductor.py` = 5 at
time of capsule; counts may grow, exit code is the verdict.)

## Slice 3 / 3b (waiver-completeness — packet §4 command)

```bash
pytest tests/test_overrides.py tests/test_admissibility.py tests/test_waiver_admission_completeness.py -q ; echo "EXIT=$?"
```
Expect: `EXIT=0`. Includes criteria 1/2/4 (emission + anti-laundering) and criterion 3
(the five `ci_verify` consumer rows). To also exercise the pre-existing CI suite:

```bash
python3 -m pytest tests/test_ci.py -q
```

## Full suite (with the known red)

```bash
python3 -m pytest tests/ -q -p no:cacheprovider 2>&1 | tail -3 ; echo "EXIT=${PIPESTATUS[0]}"
```
Expect: **`1 failed, 16051 passed, 62 skipped`** and `EXIT=1`. The single failure is the
**known pre-existing** version/tag drift, NOT a regression:
`tests/test_qa_self_governance.py::TestSelfGovernanceDocQuality::test_pyproject_version_matches_latest_git_tag`
(`pyproject 2.8.1` vs latest tag `stage3b2-first-effect`). Confirm it is the only red:

```bash
python3 -m pytest "tests/test_qa_self_governance.py::TestSelfGovernanceDocQuality::test_pyproject_version_matches_latest_git_tag" -q ; echo "EXIT=$?"
```
(The wrapper `echo` exit can mask pytest's — read `PIPESTATUS[0]`. A live instance of the
scar `governor verify-run` exists to prevent.)

## Regenerate the Slice-3 dogfood receipts

```bash
python3 working/ag_admit_slice3_waiver.py ; echo "EXIT=$?"
```
Expect: `EXIT=2` (by design = "stopped for human"; criteria 1/2/4 resolved, the printed
NEEDS_HUMAN line is the historical criterion-3 boundary, since resolved by Slice 3b).
Writes `working/slice3_receipts/receipts/gate_receipts.jsonl`.

## Expected worktree state / regenerable vs dirty

After a clean checkout of the campaign commits, the tree is **clean**. The **only**
expected untracked artifact — and only if you run the dogfood above — is:

```
working/slice3_receipts/        # regenerable, nondeterministic timestamps; NOT committed
```

Anything else showing in `git status --short` is a real change, not a replay artifact.
Tracked campaign artifacts (committed) live under `docs/campaigns/ag-admit-self-build/`,
`.governor/campaigns/`, `src/governor/ag_admit.py`, `working/ag_admit_*`, and the
`tests/test_ag_admit*.py` / `tests/test_waiver_admission_completeness.py` files.
