verdict: contradicted

# Claim checked

Pinned revision: `fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2` (`v2.8.1-492-gfb1535f`, detached HEAD).

The claim under testimony is the status line in `specs/gaps/GOV_GAP_CHAIN_001.md`: composition-aware capability gating was “shipped” in v2.5.0 via `governed_activity.py` and `verifier_gate.py`.

That exact claim is contradicted. The repository does contain composition enforcement, but its code, tests, release history, and canonical status documents place it in v2.3.2 under `chain_gate.py`, `governed_dispatch.py`, `daemon.py`, and `policy_engine.py`. The two claimed v2.5.0 files are different, observe-only foundations. In addition, the current implementation does not satisfy at least two explicit behaviors in the gap text (repeat-receipt deduplication and policy-load-specific verdict reasons), so the gap’s full contract cannot be confirmed shipped merely by substituting the actual module names.

# Named evidence

## The current status annotation postdates v2.5.0

- `specs/gaps/GOV_GAP_CHAIN_001.md:3` contains the claim.
- At the actual local `v2.5.0` tag, that same line still said `Status: deferred`.
- `git blame` and the introducing diff show the current line was added by `cc45aa5` on 2026-03-04, in the v2.6.0 commit, two days after the v2.5.0 tag.
- The local `v2.5.0` tag points to commit `6cee85c1d77b1b8044de7f221110753b43c8b38b`, dated 2026-03-02.

## The two claimed implementation files are unrelated to action-chain gating

- `src/governor/governed_activity.py:3-22` declares a “drift-gated retry substrate” governed by `specs/gaps/GOVERNED_ACTIVITIES.md`. Its primary types are `FactObservation`, `PreconditionBundle`, `AttemptRecord`, and `DriftCheckResult`; it does not maintain per-`correlation_id` tool-action logs or evaluate capability compositions.
- `src/governor/verifier_gate.py:3-16` declares a mechanical verifier-suite composition boundary: suite composition, verifier results, receipt emission, environment hashing, flake handling, and quarantine. “Composition” here means composing mechanical verifiers, not composing tool actions.
- A full static search of both named source files and both named test files found none of the chain-gate contract markers (`ChainGate`, `ActionStep`, `ActionLog`, `CompositionRule`, `correlation_id`, `chain_rules`, `action_log_hash`, `matched_rule_ids`, `history_length`, `secret_candidate`, or `network_egress`).
- `CHANGELOG.md:73-76` and the v2.5.0 copy of `docs/V2_STATUS.md` call these “Verifier gate foundation” and “Governed activity foundation”; both are explicitly “Observe-only, not wired to daemon/CLI.”

Representative tests confirm what the named modules actually cover:

- `tests/test_governed_activity.py::TestOnAttempt::test_retry_etag_diverged`
- `tests/test_governed_activity.py::TestGateReceiptIntegration::test_receipt_gate_name`
- `tests/test_verifier_gate.py::TestRunSuite::test_full_pipeline`
- `tests/test_verifier_gate.py::TestVerifySummarySignal::test_emitted_envelope_ingests_into_signal_store`

Their complete targeted suites pass, but passing them supplies no evidence for chain-gate closure.

## The repository identifies a different implementation and release

- `specs/gaps/GAP_BUILD_ORDER.md:430-435` says `GOV_GAP_CHAIN_001` shipped in 2.3.2 via `chain_gate.py`, `governed_dispatch.py`, and `policy_engine.py`.
- `docs/V2_STATUS.md:59-90` documents v2.3.2 Phase 2B composition detection, Phase 2C enforcement/CAS binding, and Phase 2D governed dispatch.
- `src/governor/chain_gate.py` implements the versioned capability/trust/sensitivity enums, `ActionStep`, `CompositionRule`, `ActionLog`, deterministic hashing, annotation, rule evaluation, modes, persistence, and four policy load states.
- `src/governor/daemon.py:2717-3259` registers `chain.evaluate`, `chain.preflight`, `chain.record`, `chain.status`, `chain.rules`, and `chain.reset`, persists logs, and emits `chain_composition` receipts.
- `src/governor/governed_dispatch.py` provides the dispatch membrane and does not call the transport when preflight returns `blocked`.
- Git history dates Phase 2B (`352324b`) and Phase 2C (`0e44e45`) to 2026-02-23; the named governed-activity (`fdac3fa`) and verifier-gate (`cb58d90`) foundations were added later, on 2026-02-26.

Relevant passing test names include:

- `tests/test_chain_gate.py::TestRuleEvaluation::test_single_step_always_allow`
- `tests/test_chain_gate.py::TestRuleEvaluation::test_secret_then_egress_deny`
- `tests/test_chain_gate.py::TestRuleEvaluation::test_secret_then_egress_with_exception_allow`
- `tests/test_chain_gate.py::TestRuleEvaluation::test_all_rules_evaluated_not_first_match`
- `tests/test_chain_gate.py::TestRuleEvaluation::test_deny_sticky`
- `tests/test_chain_gate.py::TestRuleEvaluation::test_failed_step_match_eligible_as_prior`
- `tests/test_chain_gate.py::TestRuleEvaluation::test_failed_step_not_match_eligible_as_proposed`
- `tests/test_chain_gate.py::TestActionLog::test_log_hash_stable`
- `tests/test_chain_gate.py::TestActionLog::test_log_hash_excludes_timestamps`
- `tests/test_chain_gate.py::TestLoadStates::{test_load_valid_rules,test_load_missing_file,test_load_corrupt_file,test_load_empty_rules}`
- `tests/test_daemon.py::TestChain::test_chain_evaluate_denied_composition`
- `tests/test_daemon.py::TestChain::test_chain_evaluate_emits_receipt`
- `tests/test_daemon.py::TestChainEnforcement::test_preflight_enforce_returns_blocked`
- `tests/test_governed_dispatch.py::TestDaemonIntegration::test_governed_dispatch_blocked_in_enforce_mode`
- `tests/test_governed_dispatch.py::TestDaemonIntegration::test_blocked_preflight_emits_receipt`

# Contract discrepancies found in the actual chain implementation

These are independent of the incorrect v2.5.0/file attribution:

1. **Repeat receipt deduplication is not implemented as specified.** The gap requires the first `(rule_id, correlation_id, edge_key)` match to emit a full receipt and later matches to increment `repeat_count` instead of emitting another full receipt. `src/governor/daemon.py:2785-2793` and `:2905-2908` increment counters, but `:2822-2830` and `:2963-2971` unconditionally emit a full receipt on every evaluation/preflight. Existing dedupe tests exercise counters and round trips, not receipt suppression or a repeat-only receipt.
2. **Missing/corrupt policy reasons collapse to `empty_rules`.** `src/governor/chain_gate.py:1130-1146` correctly distinguishes `loaded`, `loaded_empty`, `missing_policy`, and `corrupt_fallback`, but `_evaluate_rules` at `:749-759` assigns `verdict_reason="empty_rules"` whenever the rule set is empty. This does not produce the gap-required `no_policy` and `corrupt_policy` verdict reasons, although the separate `load_status` remains available in daemon gate configuration.
3. **The implementation-sketch CLI surface is absent.** No `governor chain status` or `governor chain rules` parser/wiring was found in `src/governor/cli.py`; the daemon RPCs do exist.
4. **Future-enum handling conflicts with the prose contract.** `ActionStep.from_dict` at `src/governor/chain_gate.py:243-255` directly constructs enums and raises on an unknown future value rather than mapping it to `unknown` and logging. The gap’s own minimum-test bullet instead says unknown strings should be rejected, so the specification is internally inconsistent on this point.

# Commands run and captured output

Repository identity:

```text
$ git status --short --branch && git rev-parse HEAD && git describe --tags --always --dirty
## HEAD (no branch)
fb1535f2ee6d9526f4de25af71aa5d3c28afa6f2
v2.8.1-492-gfb1535f
exit 0
```

Tag and status-line provenance:

```text
$ git tag --list 'v2.5.0' --format='%(refname:short) %(objecttype) %(objectname) %(creatordate:iso-strict) %(subject)'
v2.5.0 commit 6cee85c1d77b1b8044de7f221110753b43c8b38b 2026-03-02T12:50:27-05:00 Prep v2.5.0 release: version bump, changelog, docs, --version flag
exit 0

$ git show v2.5.0:specs/gaps/GOV_GAP_CHAIN_001.md | sed -n '1,5p'
# GOV-GAP-CHAIN-001: Composition-Aware Capability Gating

Status: `deferred` (v2 hardening — hook point required now, full engine later)

## Problem
exit 0

$ git blame -L 3,3 -- specs/gaps/GOV_GAP_CHAIN_001.md
cc45aa5d (James Beck 2026-03-04 17:25:14 -0500 3) Status: `shipped` (v2.5.0 — composition-aware gating via `governed_activity.py` + `verifier_gate.py`)
exit 0

$ git show --format='%h %ad %s' --date=iso-strict --unified=1 cc45aa5 -- specs/gaps/GOV_GAP_CHAIN_001.md | sed -n '1,30p'
cc45aa5 2026-03-04T17:25:14-05:00 v2.6.0: egress gate, Phase D integration lane, v3 bake-in placeholders

-Status: `deferred` (v2 hardening — hook point required now, full engine later)
+Status: `shipped` (v2.5.0 — composition-aware gating via `governed_activity.py` + `verifier_gate.py`)
exit 0
```

Implementation chronology:

```text
$ git show -s --format='%h %ad %s' --date=short 352324b 0e44e45 fdac3fa cb58d90 cc45aa5
352324b 2026-02-23 Add composition gate (Phase 2B): detect-only chain evaluation
0e44e45 2026-02-23 Add composition enforcement ratchet (Phase 2C): preflight/record split, CAS binding, mode ratchet
fdac3fa 2026-02-26 Add governed activity foundation: drift-gated retry substrate (110 tests)
cb58d90 2026-02-26 Add verifier gate foundation: composition boundary for mechanical verification (112 tests)
cc45aa5 2026-03-04 v2.6.0: egress gate, Phase D integration lane, v3 bake-in placeholders
exit 0
```

Named-file chain-marker search:

```text
$ rg -n "CapabilityClass|TrustDomain|DataSensitivity|AnnotationSource|ActionStep|ActionLog|CompositionRule|ChainGate|correlation_id|chain_rules|action_log_hash|matched_rule_ids|exception_results|history_length|repeat_count|detect_only|secret_candidate|network_egress" src/governor/governed_activity.py src/governor/verifier_gate.py tests/test_governed_activity.py tests/test_verifier_gate.py
<no stdout>
exit 1
```

Named-module tests:

```text
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider tests/test_governed_activity.py tests/test_verifier_gate.py -q
........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 92%]
..................                                                       [100%]
234 passed in 1.36s
exit 0
```

Actual chain implementation tests (initial and expanded runs):

```text
$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider tests/test_chain_gate.py tests/test_governed_dispatch.py tests/test_daemon.py::TestChain -q
........................................................................ [ 54%]
............................................................             [100%]
132 passed in 1.47s
exit 0

$ PYTHONDONTWRITEBYTECODE=1 python3 -m pytest -p no:cacheprovider tests/test_chain_gate.py tests/test_governed_dispatch.py tests/test_daemon.py::TestChain tests/test_daemon.py::TestChainEnforcement -q
........................................................................ [ 47%]
........................................................................ [ 94%]
........                                                                 [100%]
152 passed in 1.54s
exit 0
```

CLI search:

```text
$ rg -n "add_parser\([^\n]*['\"]chain|chain\.status|chain\.rules|chain_preflight|chain_record" src/governor/cli.py
<no stdout>
exit 1
```

Pre-report cleanliness check:

```text
$ git status --short --untracked-files=all
<no stdout>
exit 0
```

# What could not be verified

- No external release publication, artifact, or signature was verified. The local `v2.5.0` ref is a lightweight commit tag, so testimony is limited to this pinned repository history.
- The full repository test suite (~14,500 tests) was not run; only the 234 named-module tests and 152 composition-gate/daemon/dispatch tests were run.
- Extracted client repositories and real external tool transports were outside this pinned worktree, so end-to-end enforcement in Maude, Guvnah, Claude Code hooks, or Codex hooks was not verified here.
- Existing tests do not verify an elevated-approval exception in a daemon receipt, full receipt-schema validation, failed-record eligibility end to end, `mode=detect_only` inside the stored receipt evidence, repeat-only receipt behavior, or load-state-specific receipt reasons. Static inspection directly disproves the latter two behaviors as currently specified.
- The contradictory future-enum requirements (“unknown + logged” versus “reject unknown strings”) cannot both be verified without a specification adjudication.

Conclusion: composition gating is materially present and its targeted implementation tests pass, but the closure statement under testimony is factually wrong about both release and implementation files, and full conformance to the gap text is not present.
