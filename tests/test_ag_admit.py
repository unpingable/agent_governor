# SPDX-License-Identifier: Apache-2.0
"""Slice 0 tests for ag-admit: CandidateStep → gate → StepVerdict projection.

Covers the load-bearing invariants from the campaign card:
- four-verdict projection is centralized in ag_admit (never the conductor)
- the gate observes paths from the DIFF, not from CandidateStep.touched_paths
- POSIX path hardening (absolute / .. / empty / escape → CANNOT_TESTIFY)
- unknown / missing source verdict → CANNOT_TESTIFY (never best-effort)
- NEEDS_HUMAN only on an explicit REQUIRE_HUMAN
- no ScopeGovernor / EscalationVerdict coupling
"""

from __future__ import annotations

import asyncio

import pytest

from governor.ag_admit import (
    REASON_CANNOT_OBSERVE,
    REASON_PATH_OUT_OF_SCOPE,
    REASON_PATHS_WITHIN_SCOPE,
    REASON_UNSAFE_PATH,
    SOURCE_BLOCK,
    SOURCE_CANNOT_TESTIFY,
    SOURCE_PROCEED,
    SOURCE_REQUIRE_HUMAN,
    AdmitResult,
    CandidateStep,
    DiffPathScopeGate,
    StepVerdict,
    _FixedVerdictGate,
    _normalize_repo_path,
    _observe_paths_from_diff,
    ag_admit,
    project_source_verdict,
)


# ---------------------------------------------------------------------------
# Diff fixtures
# ---------------------------------------------------------------------------

GRANT = ("toy_repo/allowed/**",)


def _diff_touching(path: str, *, new_file: bool = True) -> str:
    """A minimal unified diff that touches exactly `path`."""
    if new_file:
        return (
            f"diff --git a/{path} b/{path}\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            f"+++ b/{path}\n"
            "@@ -0,0 +1 @@\n"
            "+hello\n"
        )
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )


def _step(diff: str, *, declared=(), scope="toy_repo/allowed/**") -> CandidateStep:
    return CandidateStep(
        step_id="step-1",
        repo="toy_repo",
        base_commit="0" * 40,
        diff=diff,
        declared_intent="touch a file",
        scope=scope,
        touched_paths=tuple(declared),
        tests_to_run=("true",),
    )


def _admit(step: CandidateStep, gate) -> AdmitResult:
    return asyncio.run(ag_admit(step, gate))


# ---------------------------------------------------------------------------
# project_source_verdict — the centralized projection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source,expected",
    [
        ("PROCEED", StepVerdict.ADMIT),
        ("PASS", StepVerdict.ADMIT),
        ("ALLOW", StepVerdict.ADMIT),
        ("BLOCK", StepVerdict.REJECT),
        ("DENY", StepVerdict.REJECT),
        ("REQUIRE_HUMAN", StepVerdict.NEEDS_HUMAN),
        ("CANNOT_TESTIFY", StepVerdict.CANNOT_TESTIFY),
        ("would_block", StepVerdict.CANNOT_TESTIFY),
        ("totally_unknown", StepVerdict.CANNOT_TESTIFY),
        (None, StepVerdict.CANNOT_TESTIFY),
    ],
)
def test_projection_table(source, expected):
    assert project_source_verdict(source) is expected


def test_unknown_never_projects_to_reject_or_needs_human():
    for bogus in ("blocked", "allow", "", "ESCALATE", "maybe"):
        v = project_source_verdict(bogus)
        assert v is StepVerdict.CANNOT_TESTIFY, bogus
        assert v is not StepVerdict.REJECT
        assert v is not StepVerdict.NEEDS_HUMAN


# ---------------------------------------------------------------------------
# DiffPathScopeGate — REJECT / ADMIT on observed paths
# ---------------------------------------------------------------------------


def test_out_of_scope_diff_rejects():
    step = _step(_diff_touching("toy_repo/forbidden/secret.txt"))
    result = _admit(step, DiffPathScopeGate(GRANT))
    assert result.verdict is StepVerdict.REJECT
    assert result.source_verdict == SOURCE_BLOCK
    assert any(r.get("reason") == REASON_PATH_OUT_OF_SCOPE for r in result.reasons) or any(
        r.get("kind") == REASON_PATH_OUT_OF_SCOPE for r in result.reasons
    )
    assert result.observed_paths == ("toy_repo/forbidden/secret.txt",)


def test_in_scope_diff_admits():
    step = _step(_diff_touching("toy_repo/allowed/example.txt"))
    result = _admit(step, DiffPathScopeGate(GRANT))
    assert result.verdict is StepVerdict.ADMIT
    assert result.source_verdict == SOURCE_PROCEED
    assert result.observed_paths == ("toy_repo/allowed/example.txt",)
    assert result.preflight_decision.raw["reason"] == REASON_PATHS_WITHIN_SCOPE


def test_mixed_paths_reject_if_any_escapes():
    diff = _diff_touching("toy_repo/allowed/ok.txt") + _diff_touching(
        "toy_repo/forbidden/bad.txt"
    )
    result = _admit(_step(diff), DiffPathScopeGate(GRANT))
    assert result.verdict is StepVerdict.REJECT


# ---------------------------------------------------------------------------
# Gate observes from the diff, NOT from declared touched_paths
# ---------------------------------------------------------------------------


def test_gate_ignores_declared_touched_paths_for_decision():
    # Diff genuinely touches a forbidden path; declared claims an allowed one.
    # The gate must REJECT on the observed (diff) path, not trust the declaration.
    step = _step(
        _diff_touching("toy_repo/forbidden/secret.txt"),
        declared=("toy_repo/allowed/innocent.txt",),
    )
    result = _admit(step, DiffPathScopeGate(GRANT))
    assert result.verdict is StepVerdict.REJECT
    assert result.observed_paths == ("toy_repo/forbidden/secret.txt",)
    raw = result.preflight_decision.raw
    assert raw["declared_touched_paths"] == ["toy_repo/allowed/innocent.txt"]
    assert raw["declared_observed_mismatch"] is True


def test_declared_matching_observed_no_mismatch():
    step = _step(
        _diff_touching("toy_repo/allowed/example.txt"),
        declared=("toy_repo/allowed/example.txt",),
    )
    result = _admit(step, DiffPathScopeGate(GRANT))
    assert result.verdict is StepVerdict.ADMIT
    assert result.preflight_decision.raw["declared_observed_mismatch"] is False


# ---------------------------------------------------------------------------
# CANNOT_TESTIFY — unobservable / unsafe paths
# ---------------------------------------------------------------------------


def test_unobservable_diff_cannot_testify():
    step = _step("this is not a diff at all\njust prose\n")
    result = _admit(step, DiffPathScopeGate(GRANT))
    assert result.verdict is StepVerdict.CANNOT_TESTIFY
    assert result.source_verdict == SOURCE_CANNOT_TESTIFY
    assert any(
        r.get("reason") == REASON_CANNOT_OBSERVE
        or r.get("kind") == REASON_CANNOT_OBSERVE
        for r in result.reasons
    )


def test_empty_diff_cannot_testify():
    step = _step("   ")
    result = _admit(step, DiffPathScopeGate(GRANT))
    assert result.verdict is StepVerdict.CANNOT_TESTIFY


@pytest.mark.parametrize(
    "bad_path",
    [
        "/etc/passwd",  # absolute
        "toy_repo/../escape.txt",  # .. escape
        "../outside.txt",  # .. escape
    ],
)
def test_unsafe_paths_cannot_testify(bad_path):
    # Build a diff whose header carries the unsafe path verbatim.
    diff = (
        f"--- a/{bad_path}\n"
        f"+++ b/{bad_path}\n"
        "@@ -1 +1 @@\n-x\n+y\n"
    )
    result = _admit(_step(diff), DiffPathScopeGate(GRANT))
    assert result.verdict is StepVerdict.CANNOT_TESTIFY
    assert result.source_verdict == SOURCE_CANNOT_TESTIFY
    assert any(
        r.get("reason") == REASON_UNSAFE_PATH or r.get("kind") == REASON_UNSAFE_PATH
        for r in result.reasons
    )


# ---------------------------------------------------------------------------
# NEEDS_HUMAN — only on explicit REQUIRE_HUMAN
# ---------------------------------------------------------------------------


def test_needs_human_only_on_explicit_require_human():
    step = _step(_diff_touching("toy_repo/allowed/example.txt"))
    result = _admit(step, _FixedVerdictGate(SOURCE_REQUIRE_HUMAN))
    assert result.verdict is StepVerdict.NEEDS_HUMAN


def test_missing_source_verdict_cannot_testify_not_needs_human():
    # A gate that returns decision=blocked but NO source_verdict must NOT be read as a
    # human escalation. The wire 'blocked' is coarse; absence of source → cannot testify.
    step = _step(_diff_touching("toy_repo/allowed/example.txt"))
    result = _admit(step, _FixedVerdictGate(None, decision="blocked"))
    assert result.verdict is StepVerdict.CANNOT_TESTIFY
    assert result.verdict is not StepVerdict.NEEDS_HUMAN
    assert result.verdict is not StepVerdict.REJECT


# ---------------------------------------------------------------------------
# Decoupling + helper unit checks
# ---------------------------------------------------------------------------


def test_no_scope_governor_import():
    """The toy gate must not couple to the SRE scope governor's vocabulary.

    Checked structurally (import statements + bound names), not by scanning prose —
    the module docstring legitimately *names* EscalationVerdict to say it is NOT used.
    """
    import ast

    import governor.ag_admit as mod

    # No EscalationVerdict / ScopeGovernor name is bound in the module namespace.
    assert "EscalationVerdict" not in mod.__dict__
    assert "ScopeGovernor" not in mod.__dict__

    # No import statement pulls from governor.scope.
    with open(mod.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert node.module != "scope", "ag_admit must not import from .scope"
            assert (node.module or "") not in ("governor.scope",)
            for alias in node.names:
                assert alias.name not in ("EscalationVerdict", "ScopeGovernor")
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "scope" not in alias.name.split(".")


def test_observe_paths_dev_null_dropped():
    paths = _observe_paths_from_diff(_diff_touching("toy_repo/allowed/x.txt"))
    assert paths is not None
    norm = sorted({_normalize_repo_path(p) for p in paths})
    assert norm == ["toy_repo/allowed/x.txt"]


def test_normalize_rejects_unsafe():
    assert _normalize_repo_path("/abs") is None
    assert _normalize_repo_path("a/../x") is None
    assert _normalize_repo_path("") is None
    assert _normalize_repo_path("/dev/null") is None
    assert _normalize_repo_path("b/toy_repo/allowed/x.txt") == "toy_repo/allowed/x.txt"
