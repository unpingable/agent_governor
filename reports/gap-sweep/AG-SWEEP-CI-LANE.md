verdict: contradicted

# AG-SWEEP-CI-LANE closure testimony

## Scope and conclusion

The claim under review is `specs/gaps/GOV_GAP_CI_LANE_001.md:3`:

> `shipped` (v2.6.0 — 43 tests, `governor wrap --receipt-out --ci-kind`, `governor ci verify`)

At the pinned revision, both CLI surfaces are implemented and the focused 43-test module passes. The versioned closure claim is nevertheless contradicted: the repository's `v2.6.0` tag does not contain the CI-lane implementation or its tests. The implementation commit is the immediate child of the tagged commit and is first contained in the `v2.7.0` release tag. Several stated closure contracts also remain different from the implementation, including the documented `--receipts` option, the CI policy pack/default required kinds, duplicate-ID rejection, default meta-receipt persistence, and the production git-governance/branch-protection lane.

Pinned revision examined: `fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2` (`v2.8.1-492-gfb1535f`).

## Named repository evidence

- `specs/gaps/GOV_GAP_CI_LANE_001.md:3` makes the shipped-v2.6.0/43-tests/CLI claim.
- `specs/gaps/GOV_GAP_CI_LANE_001.md:41-71` specifies wrapper receipt behavior; `:73-87` specifies the CI policy pack; `:89-110` specifies `ci verify`; `:112-124` specifies production `git-gov`; `:155-189` gives the reference workflow and branch-protection requirement.
- `docs/V2_STATUS.md:253-260` repeats that the CI lane, workflow, and 43 tests shipped as 2.6.0.
- `docs/VERSIONING.md:32-35` says the Governor CLI uses semantic versioning, tags, and GitHub releases.
- `src/governor/cli.py:2034-2071` defines `governor wrap`, `--receipt-out`, `--ci-kind`, the missing-kind error, receipt dispatch, and child exit-code propagation.
- `src/governor/cli.py:19516-19567` defines `governor ci verify`. Its receipt input is positional `RECEIPT_PATH`; `--policy` loads JSON.
- `src/governor/ci.py:160-198` implements JSONL/file/directory output; `:201-318` implements `ci_wrap`; `:326-372` loads one file or directory; `:380-405` defines `CiPolicy`; `:476-632` implements policy checks and the meta-receipt.
- `tests/test_ci.py:37-526` contains exactly 43 test functions. The command-level tests are `TestCli::test_wrap_pass`, `TestCli::test_wrap_fail`, `TestCli::test_wrap_missing_ci_kind`, and `TestCli::test_ci_verify_pass` (`:455-513`).
- `.github/workflows/ci.yml:49-70` wraps and verifies tests, and `:94-108` wraps and verifies lint at the pinned revision. Neither job loads a required-kinds policy or runs the specified production `git-gov` gate.

## Release-history evidence

Command and output:

```text
$ git rev-parse HEAD
fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2
$ git describe --tags --always
v2.8.1-492-gfb1535f
$ git rev-parse v2.6.0
92cc8abcf18236473174170c510a8912cb51b5f2
$ git show --no-patch --format='%H%n%P%n%s' a56e586
a56e586c418ec4b394945ae46cf1d7f94b62466f
92cc8abcf18236473174170c510a8912cb51b5f2
Add CI lane: governor wrap --receipt-out + governor ci verify (43 tests)
$ git merge-base --is-ancestor a56e586 v2.6.0; echo $?
1
$ git merge-base --is-ancestor a56e586 v2.7.0; echo $?
0
```

Thus `a56e586` is immediately after, not within, `v2.6.0`; it is contained in `v2.7.0`.

The claimed implementation and test module are absent from the 2.6.0 tag:

```text
$ git cat-file -e v2.6.0:src/governor/ci.py; echo $?
fatal: path 'src/governor/ci.py' exists on disk, but not in 'v2.6.0'
128
$ git cat-file -e v2.6.0:tests/test_ci.py; echo $?
fatal: path 'tests/test_ci.py' exists on disk, but not in 'v2.6.0'
128
```

The tagged workflow ran ungoverned test/lint commands:

```text
$ git show v2.6.0:.github/workflows/ci.yml | sed -n '40,75p'
      - name: Run tests
        run: |
          pytest tests/ -v --tb=short -q
...
      - name: Run ruff check
        run: ruff check src/ tests/ libs/ --output-format=github
```

The subsequent history identifies when the pieces landed:

```text
$ git log --format='%h %s' --reverse v2.6.0.. -- src/governor/ci.py .github/workflows/ci.yml docs/V2_STATUS.md specs/gaps/GOV_GAP_CI_LANE_001.md | head
a56e586 Add CI lane: governor wrap --receipt-out + governor ci verify (43 tests)
ef05c09 Wire CI lane into GitHub Actions workflow
eafe874 Update docs for 2.6.0: test counts, V2_STATUS, known-good bundle
3590184 Bump version to 2.7.0, regenerate golden fixtures, register schema
e14d276 Front door pass, gap spec updates, implicit side-effect spec
```

## Test evidence

The focused suite was run from the pinned tree with bytecode and pytest cache writes disabled:

```text
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_ci.py -q -p no:cacheprovider
...........................................                              [100%]
43 passed in 3.09s
```

Collection independently confirmed the exact count:

```text
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest tests/test_ci.py --collect-only -q -p no:cacheprovider
...
43 tests collected in 0.77s
```

Named tests, grouped exactly as collected:

- `TestGitState` (3): `test_git_repo_returns_sha`, `test_non_repo_returns_empty`, `test_dirty_catches_untracked`.
- `TestCiWrap` (14): `test_pass_verdict`, `test_fail_verdict`, `test_json_file_output`, `test_dir_output_auto_created`, `test_evidence_keys`, `test_subject_deterministic`, `test_evidence_hash_excludes_duration`, `test_command_stored_as_list`, `test_command_display_truncated`, `test_stdout_cap_truncation_flag`, `test_fail_open_on_bad_path`, `test_exit_code_passthrough`, `test_invalid_ci_kind_raises`, `test_timestamps_utc_z`.
- `TestLoadCiReceipts` (5): `test_jsonl_file`, `test_directory_individual_json`, `test_mixed_dir`, `test_gate_filter`, `test_empty`.
- `TestCiPolicy` (3): `test_roundtrip`, `test_defaults`, `test_file_load`.
- `TestCiVerify` (13): `test_all_pass`, `test_missing_kind`, `test_failed_verdict`, `test_mixed_sha`, `test_missing_sha_fail_closed`, `test_dirty_flag`, `test_identical_bundle_dedupe_ok`, `test_conflicting_id_block`, `test_meta_receipt_structure`, `test_no_receipts`, `test_custom_policy`, `test_receipt_out_writes_meta_receipt`, `test_sha_known_in_checks`.
- `TestCli` (4): `test_wrap_pass`, `test_wrap_fail`, `test_wrap_missing_ci_kind`, `test_ci_verify_pass`.
- `TestUtcNow` (1): `test_z_suffix`.

This confirms 43 passing tests at the pinned revision and in the post-tag implementation commit; it does not place those tests in the `v2.6.0` tag, where the test file is absent.

## Runtime CLI evidence at the pinned revision

The repository entry point is `governor = "governor.cli:main"` (`pyproject.toml:56-57`). Runtime checks invoked that same pinned module with `PYTHONPATH="$PWD/src"`; all generated artifacts were under a temporary `/tmp` directory and were removed.

Passing wrapped command:

```text
$ PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 python3 -m governor.cli wrap --receipt-out "$TMP/receipts/" --ci-kind lint -- python3 -c "print('wrapped-ok')"
Receipt: 27598a4675f4389d9b66ea037892ab180be404200f454adeb8e21d125d643f9b [pass]
exit=0
$ jq -c '{gate:.receipt.gate,verdict:.receipt.verdict,ci_kind:.evidence.ci_kind,exit_code:.evidence.exit_code,git_sha:.evidence.git_sha,dirty:.evidence.dirty}' "$TMP"/receipts/*.json
{"gate":"ci_wrap","verdict":"pass","ci_kind":"lint","exit_code":0,"git_sha":"fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2","dirty":false}
```

The exact `ci verify` syntax specified at `specs/gaps/GOV_GAP_CI_LANE_001.md:94,175-177` fails:

```text
$ PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 python3 -m governor.cli ci verify --receipts "$TMP/receipts/" --receipt-out "$TMP/meta-spec.json" --json
Usage: python -m governor.cli ci verify [OPTIONS] RECEIPT_PATH
Try 'python -m governor.cli ci verify --help' for help.

Error: No such option: --receipts Did you mean --receipt-out?
exit=2
```

The implemented positional syntax passes and emits a meta-receipt when explicitly requested:

```text
$ PYTHONPATH="$PWD/src" PYTHONDONTWRITEBYTECODE=1 python3 -m governor.cli ci verify "$TMP/receipts/" --receipt-out "$TMP/meta.json" --json | jq -c '{ok,verdict,receipts_loaded,kinds_found,git_sha,checks,meta_gate:.receipt.gate}'
{"ok":true,"verdict":"pass","receipts_loaded":1,"kinds_found":["lint"],"git_sha":"fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2","checks":{"receipts_loaded":true,"required_kinds_present":true,"all_pass":true,"sha_known":true,"same_sha":true,"clean":true,"no_conflicting_ids":true},"meta_gate":"ci_verify"}
exit=0
$ jq -c '{gate:.receipt.gate,verdict:.receipt.verdict}' "$TMP/meta.json"
{"gate":"ci_verify","verdict":"pass"}
```

## Remaining closure contradictions at the pinned revision

1. **Receipt input syntax and globbing.** The gap specifies `--receipts <dir-or-glob>` (`:94`), but `src/governor/cli.py:19523-19529` requires one positional existing path. `src/governor/ci.py:326-372` handles a file or directory, not an arbitrary glob. The exact documented command exits 2 above.
2. **CI policy pack/required evidence.** The gap specifies `.governor/ci.conf` or a daemon-config section with production `required_kinds` (`:73-87`). No `ci.conf` is present. The CLI accepts only an optional JSON policy (`src/governor/cli.py:19524-19546`), and no policy means `required_kinds=frozenset()` (`src/governor/ci.py:488-520`). The checked-in workflow invokes no policy, so its `required_kinds_present` check is vacuously true.
3. **Duplicate replay behavior.** The gap says no duplicate receipt IDs (`:101`). `src/governor/ci.py:576-591` permits byte-identical duplicate IDs and blocks only conflicting payloads; the passing test is explicitly named `TestCiVerify::test_identical_bundle_dedupe_ok`.
4. **Default meta-receipt persistence.** The gap says omission of `--receipt-out` writes the meta-receipt to the receipts directory (`:106-110`). `src/governor/ci.py:601-623` constructs one in memory but writes it only when `receipt_out is not None`.
5. **Directory filename contract.** The gap specifies `ci_wrap_<kind>_<timestamp>_<uuid>.json` (`:66-68`). `src/governor/ci.py:188-197` emits `ci_wrap_<kind>_<8-char-uuid>.json`, without a timestamp.
6. **Governed-lane enforcement.** The gap requires a production `git-gov` check and documented branch protection (`:112-124,187-189`). The current `.github/workflows/ci.yml` has receipt wrapping/verifying but no production `git-gov` step, no required-kinds policy, and no adjacent branch-protection documentation. Repository searches found `governor-ci` branch-protection language only in the gap itself.

These are contract differences, not merely absent test coverage. Together with the tag history, they preclude `confirmed-shipped` for the stated closure claim.

## What could not be verified

- Published PyPI/GitHub release artifacts for version 2.6.0 were not accessed; testimony is limited to the pinned repository and its local tags/history.
- Remote CI run history, repository status-check configuration, and whether branch protection actually requires a Governor check are external state and cannot be established from this worktree.
- The operational claim "no receipt, no merge" cannot be verified without that external branch-protection state.
- The full repository suite was not run. Only the claim-specific `tests/test_ci.py` suite was run: 43 collected and 43 passed.
- No historical v2.6.0 binary was built or executed. The tag-tree inspection is decisive for repository contents, while runtime behavior was checked only at the pinned revision.

Before this report was created, `git status --short` produced no output. The gap file was not modified.
