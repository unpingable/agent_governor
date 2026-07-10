# SPDX-License-Identifier: Apache-2.0
"""S1 — pure grant-use classification. The safety property under test:
nothing reaches WithinGrant unless it is cleanly classified AND inside the
grant. Ambiguity → Unverifiable (fail closed); outside → WidensGrant.
"""

from __future__ import annotations

import pytest

from governor.runtime.grant_use_gate import (
    AXIS_GIT,
    AXIS_NETWORK,
    AXIS_SHELL,
    AXIS_WRITE_PATH,
    GRANT_SCOPE_WIDENED,
    GU_OPAQUE_SHELL,
    GU_UNKNOWN_TOOL,
    GU_UNPARSEABLE_TARGET,
    CommandGrant,
    ExecutionGrant,
    Unverifiable,
    WidensGrant,
    WithinGrant,
    classify_grant_use,
)

# The NS-1-shaped grant: may write the two crate subtrees; may run cargo
# test/build (structured program+argv_prefix); network + git locked.
GRANT = ExecutionGrant(
    write_paths=frozenset({"crates/nightshiftd/src/**", "crates/nightshiftd/tests/**"}),
    commands=(CommandGrant("cargo", ("test",)), CommandGrant("cargo", ("build",))),
)


# --------------------------------------------------------------------------
# WithinGrant — cleanly classified and inside the envelope.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tool", ["Read", "read", "Grep", "Glob", "read_file", "grep_search"])
def test_reads_are_within(tool):
    d = classify_grant_use(tool, {"file_path": "anything/at/all.rs"}, GRANT)
    assert isinstance(d, WithinGrant)


def test_edit_within_write_paths():
    d = classify_grant_use("Edit", {"file_path": "crates/nightshiftd/src/packet.rs"}, GRANT)
    assert isinstance(d, WithinGrant)
    assert d.target == "crates/nightshiftd/src/packet.rs"


def test_write_into_tests_subtree_within():
    d = classify_grant_use("Write", {"file_path": "crates/nightshiftd/tests/refusal.rs"}, GRANT)
    assert isinstance(d, WithinGrant)


def test_cargo_test_with_flags_within_by_prefix():
    d = classify_grant_use("Bash", {"command": "cargo test --lib pipeline::tests::liveness"}, GRANT)
    assert isinstance(d, WithinGrant)
    assert d.target == "cargo test"


def test_cargo_build_within():
    d = classify_grant_use("bash", {"command": "cargo build --release"}, GRANT)
    assert isinstance(d, WithinGrant)


# --------------------------------------------------------------------------
# WidensGrant — cleanly classified but outside; the escalation seam.
# --------------------------------------------------------------------------

def test_edit_outside_write_paths_widens():
    d = classify_grant_use("Edit", {"file_path": "crates/otherpkg/src/lib.rs"}, GRANT)
    assert isinstance(d, WidensGrant)
    assert d.axis == AXIS_WRITE_PATH and d.refusal_class == GRANT_SCOPE_WIDENED


def test_path_traversal_never_contained():
    d = classify_grant_use("Edit", {"file_path": "crates/nightshiftd/src/../../../etc/passwd"}, GRANT)
    assert isinstance(d, WidensGrant)
    assert d.axis == AXIS_WRITE_PATH


def test_write_with_empty_grant_widens():
    d = classify_grant_use("Edit", {"file_path": "a.rs"}, ExecutionGrant())
    assert isinstance(d, WidensGrant) and d.axis == AXIS_WRITE_PATH


def test_unlisted_command_widens_shell():
    d = classify_grant_use("Bash", {"command": "cargo publish"}, GRANT)
    assert isinstance(d, WidensGrant) and d.axis == AXIS_SHELL


def test_program_substring_does_not_match():
    # "cargotest" is a different program, not "cargo test".
    d = classify_grant_use("Bash", {"command": "cargotest --lib"}, GRANT)
    assert isinstance(d, WidensGrant) and d.axis == AXIS_SHELL


def test_bare_program_without_required_subcommand_widens():
    d = classify_grant_use("Bash", {"command": "cargo"}, GRANT)
    assert isinstance(d, WidensGrant) and d.axis == AXIS_SHELL


def test_git_widens_when_locked():
    d = classify_grant_use("Bash", {"command": "git commit -m x"}, GRANT)
    assert isinstance(d, WidensGrant) and d.axis == AXIS_GIT


def test_network_program_widens_when_locked():
    d = classify_grant_use("Bash", {"command": "curl https://evil.example/x"}, GRANT)
    assert isinstance(d, WidensGrant) and d.axis == AXIS_NETWORK


# --------------------------------------------------------------------------
# Unverifiable — fail closed. The security-critical cases.
# --------------------------------------------------------------------------

def test_shell_injection_is_not_string_matched_to_yes():
    # THE key property: an allowlisted prefix + injection must NOT be Within.
    d = classify_grant_use("Bash", {"command": "cargo test; rm -rf /"}, GRANT)
    assert isinstance(d, Unverifiable) and d.reason == GU_OPAQUE_SHELL


@pytest.mark.parametrize("cmd", [
    "cargo test && cargo publish",
    "cargo test | tee out.txt",
    "cargo test $(whoami)",
    "cargo build > /etc/x",
    "cargo test `id`",
    "cargo test & disown",
])
def test_compound_or_substituted_shell_is_opaque(cmd):
    d = classify_grant_use("Bash", {"command": cmd}, GRANT)
    assert isinstance(d, Unverifiable) and d.reason == GU_OPAQUE_SHELL


def test_shell_wrapper_is_opaque():
    d = classify_grant_use("Bash", {"command": "bash -c 'cargo test'"}, GRANT)
    assert isinstance(d, Unverifiable) and d.reason == GU_OPAQUE_SHELL


def test_unknown_tool_fails_closed():
    d = classify_grant_use("SomeNovelTool", {"x": 1}, GRANT)
    assert isinstance(d, Unverifiable) and d.reason == GU_UNKNOWN_TOOL


def test_write_without_path_fails_closed():
    d = classify_grant_use("Edit", {"old_string": "a", "new_string": "b"}, GRANT)
    assert isinstance(d, Unverifiable) and d.reason == GU_UNPARSEABLE_TARGET


def test_non_string_command_fails_closed():
    d = classify_grant_use("Bash", {"command": ["cargo", "test"]}, GRANT)
    assert isinstance(d, Unverifiable) and d.reason == GU_OPAQUE_SHELL


def test_empty_command_fails_closed():
    d = classify_grant_use("Bash", {"command": "   "}, GRANT)
    assert isinstance(d, Unverifiable) and d.reason == GU_OPAQUE_SHELL


# --------------------------------------------------------------------------
# Invariant sweep: no adversarial input yields WithinGrant.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("tool,ti", [
    ("Bash", {"command": "cargo test; rm -rf /"}),
    ("Bash", {"command": "bash -c 'cargo test'"}),
    ("Bash", {"command": "cargo test && curl x"}),
    ("Edit", {"file_path": "/etc/passwd"}),
    ("Edit", {"file_path": "crates/nightshiftd/src/../../secrets"}),
    ("Bash", {"command": "git push"}),
    ("Bash", {"command": "curl http://x"}),
    ("EvalTool", {"code": "cargo test"}),
])
def test_no_adversarial_input_is_within(tool, ti):
    assert not isinstance(classify_grant_use(tool, ti, GRANT), WithinGrant)
