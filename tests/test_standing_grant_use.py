# SPDX-License-Identifier: Apache-2.0
"""Slice 1b — StandingGrantUseClient unit tests (fake runner, no real binary).

Pins the three-way triage of the ``standing.grant_use.v1`` witness packet, the
spendful-once/no-retry invariant, the unknown-custody distinction, binary
resolution order, and argv shape. Contract fixtures mirror the REAL packets
emitted by ``~/git/standing`` ``crates/standing-cli/src/main.rs`` @ ``f101c55``.

AG tests must never be hostage to a sibling repo's build path — every behavioural
test drives a FAKE runner returning canned stdout. The one optional live
specimen lives elsewhere (skipped if the binary is absent).
"""

from __future__ import annotations

import json
import os

import pytest

from governor.standing_grant_use import (
    DEFAULT_STANDING_COMMAND,
    ENV_STANDING_BIN,
    REASON_BINARY_UNRESOLVED,
    REASON_OUTPUT_UNPARSEABLE,
    REASON_RECEIPT_MISSING,
    REASON_REQUEST_MISMATCH,
    REASON_SCHEMA_UNKNOWN,
    REASON_TRANSPORT_FAILED,
    REASON_UNKNOWN_CUSTODY,
    RECOGNIZED_REFUSAL_CLASSES,
    SCHEMA_GRANT_USE_V1,
    GrantRefused,
    GrantUsed,
    NoVerifiedResult,
    ResolvedBinary,
    RunOutcome,
    StandingGrantUseClient,
    resolve_standing_binary,
)


# --------------------------------------------------------------------------
# Fake runner + canned-packet helpers.
# --------------------------------------------------------------------------


class FakeRunner:
    """Returns a preset RunOutcome; records argv + call count (no real process)."""

    def __init__(self, outcome: RunOutcome):
        self._outcome = outcome
        self.calls: list[list[str]] = []

    def run(self, argv, *, timeout):  # noqa: ANN001 - test double
        self.calls.append(list(argv))
        return self._outcome


def _used_packet(action="deploy", target="prod", digest="a" * 64, grant_id="g-1", subject="subj-1"):
    return {
        "schema": SCHEMA_GRANT_USE_V1,
        "result": "used",
        "grant_id": grant_id,
        "subject": subject,
        "attempted": {"action": action, "target": target},
        "granted": {"action": action, "target": target},
        "receipt_digest": digest,
        "receipt_kind": "grant_used",
    }


def _refused_packet(refusal_class="scope_mismatch", action="deploy", target="staging", grant_id="g-1"):
    return {
        "schema": SCHEMA_GRANT_USE_V1,
        "result": "refused",
        "grant_id": grant_id,
        "subject": "subj-1",
        "attempted": {"action": action, "target": target},
        "granted": {"action": "deploy", "target": "prod"},
        "refusal_class": refusal_class,
        "receipt_digest": None,
        "receipt_kind": None,
        "detail": "scope mismatch: granted deploy/prod, attempted deploy/staging",
    }


def _ok(packet: dict, exit_code: int = 0) -> RunOutcome:
    return RunOutcome(dispatched=True, exit_code=exit_code, stdout=json.dumps(packet) + "\n", stderr="")


def _client(outcome: RunOutcome) -> tuple[StandingGrantUseClient, FakeRunner]:
    runner = FakeRunner(outcome)
    client = StandingGrantUseClient(
        runner=runner,
        binary=ResolvedBinary(path="/fake/standing", source="configured"),
        db_path="/tmp/standing.db",
    )
    return client, runner


def _use(client: StandingGrantUseClient, action="deploy", target="prod"):
    return client.use(
        grant_id="g-1",
        action=action,
        target=target,
        identity_path="/fake/id.json",
        secret="s3cr3t",
    )


# --------------------------------------------------------------------------
# 1. used → GrantUsed (the only mintable outcome).
# --------------------------------------------------------------------------


def test_used_with_matching_scope_and_digest_is_grant_used():
    client, runner = _client(_ok(_used_packet(digest="b" * 64)))
    result = _use(client, action="deploy", target="prod")
    assert isinstance(result, GrantUsed)
    assert result.receipt_digest == "b" * 64
    assert result.action == "deploy" and result.target == "prod"
    assert result.subject == "subj-1"
    assert len(runner.calls) == 1  # invoked exactly once


def test_only_grant_used_carries_a_mintable_digest():
    # Type-split discipline: a refusal / no-result has no receipt_digest attribute.
    used = GrantUsed(grant_id="g", receipt_digest="d", action="a", target="t", subject=None, raw={})
    assert hasattr(used, "receipt_digest")
    assert not hasattr(GrantRefused(grant_id="g", refusal_class="expired", detail=None, raw={}), "receipt_digest")
    assert not hasattr(NoVerifiedResult(reason=REASON_TRANSPORT_FAILED), "receipt_digest")


# --------------------------------------------------------------------------
# 2. witness-integrity: used packet must be about THIS request.
# --------------------------------------------------------------------------


def test_used_with_mismatched_attempted_scope_is_request_mismatch():
    # Standing says used for deploy/prod, but we asked for deploy/staging.
    client, _ = _client(_ok(_used_packet(action="deploy", target="prod")))
    result = _use(client, action="deploy", target="staging")
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_REQUEST_MISMATCH
    assert not result.may_have_spent  # we have a clean packet, just the wrong one


def test_used_without_digest_is_receipt_missing():
    pkt = _used_packet()
    pkt["receipt_digest"] = None
    client, _ = _client(_ok(pkt))
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_RECEIPT_MISSING


def test_used_with_empty_digest_is_receipt_missing():
    pkt = _used_packet(digest="")
    client, _ = _client(_ok(pkt))
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_RECEIPT_MISSING


# --------------------------------------------------------------------------
# 3. refused → GrantRefused (inherited cause), all 5 recognized classes.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("klass", sorted(RECOGNIZED_REFUSAL_CLASSES))
def test_refused_recognized_class_is_grant_refused(klass):
    client, runner = _client(RunOutcome(True, 1, json.dumps(_refused_packet(refusal_class=klass)), ""))
    result = _use(client, action="deploy", target="staging")
    assert isinstance(result, GrantRefused)
    assert result.refusal_class == klass
    assert len(runner.calls) == 1  # a refusal is still exactly one invocation


def test_recognized_set_matches_real_standing_mapping():
    # Pins the doc-vs-code finding: grant use emits 5 classes; "replay" is NOT one.
    assert RECOGNIZED_REFUSAL_CLASSES == {
        "scope_mismatch",
        "expired",
        "already_spent",
        "subject_mismatch",
        "not_found",
    }
    assert "replay" not in RECOGNIZED_REFUSAL_CLASSES


def test_refused_unknown_class_is_no_verified_result_not_a_refusal():
    client, _ = _client(RunOutcome(True, 1, json.dumps(_refused_packet(refusal_class="replay")), ""))
    result = _use(client, target="staging")
    # Standing refused, but AG cannot faithfully classify → no_verified_result,
    # NOT a synthesized refusal class.
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_OUTPUT_UNPARSEABLE


def test_refused_missing_class_is_no_verified_result():
    pkt = _refused_packet()
    del pkt["refusal_class"]
    client, _ = _client(RunOutcome(True, 1, json.dumps(pkt), ""))
    result = _use(client, target="staging")
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_OUTPUT_UNPARSEABLE


# --------------------------------------------------------------------------
# 4. transport ≠ refusal: no_verified_result family.
# --------------------------------------------------------------------------


def test_not_dispatched_is_transport_failed_not_spent():
    client, _ = _client(RunOutcome(dispatched=False, exit_code=None, stdout="", stderr="binary not found"))
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_TRANSPORT_FAILED
    assert not result.may_have_spent  # never launched → grant untouched


def test_dispatched_then_died_no_output_is_unknown_custody():
    # exit_code None + no parseable stdout = killed/timeout mid-flight.
    client, _ = _client(RunOutcome(dispatched=True, exit_code=None, stdout="", stderr=""))
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_UNKNOWN_CUSTODY
    assert result.may_have_spent  # THE retry landmine — grant may already be Used


def test_clean_exit_prose_only_is_transport_failed_cannot_verify():
    # Standing's None branch: internal/transport StoreError → prose on stderr, exit 1, no JSON.
    client, _ = _client(RunOutcome(dispatched=True, exit_code=1, stdout="", stderr="error: database is locked"))
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_TRANSPORT_FAILED
    assert not result.may_have_spent  # clean exit reporting an error before/without transition


def test_unknown_schema_is_no_verified_result():
    pkt = _used_packet()
    pkt["schema"] = "standing.grant_use.v2"
    client, _ = _client(_ok(pkt))
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_SCHEMA_UNKNOWN


def test_unknown_result_value_is_unparseable():
    pkt = _used_packet()
    pkt["result"] = "maybe"
    client, _ = _client(_ok(pkt))
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_OUTPUT_UNPARSEABLE


def test_non_json_stdout_clean_exit_is_transport_failed():
    client, _ = _client(RunOutcome(dispatched=True, exit_code=0, stdout="hello not json", stderr=""))
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_TRANSPORT_FAILED


def test_leading_prose_before_json_line_still_parses():
    pkt = _used_packet(digest="c" * 64)
    stdout = "INFO some log line\nWARN another\n" + json.dumps(pkt) + "\n"
    client, _ = _client(RunOutcome(dispatched=True, exit_code=0, stdout=stdout, stderr=""))
    result = _use(client)
    assert isinstance(result, GrantUsed)
    assert result.receipt_digest == "c" * 64


# --------------------------------------------------------------------------
# 5. binary unresolved → no_verified_result, runner NEVER invoked.
# --------------------------------------------------------------------------


def test_unresolved_binary_returns_no_verified_result_without_running():
    runner = FakeRunner(_ok(_used_packet()))
    # No injected binary; empty env so resolution fails.
    client = StandingGrantUseClient(runner=runner, binary=None, env={})
    result = _use(client)
    assert isinstance(result, NoVerifiedResult)
    assert result.reason == REASON_BINARY_UNRESOLVED
    assert runner.calls == []  # the spendful op was never invoked


# --------------------------------------------------------------------------
# 6. spendful-once invariant across every dispatched outcome.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "outcome",
    [
        RunOutcome(True, 0, json.dumps(_used_packet()), ""),
        RunOutcome(True, 1, json.dumps(_refused_packet()), ""),
        RunOutcome(True, None, "", ""),  # unknown custody
        RunOutcome(True, 1, "error: boom", ""),  # transport
    ],
)
def test_invoked_exactly_once_never_retries(outcome):
    client, runner = _client(outcome)
    _use(client, target="staging")
    assert len(runner.calls) == 1


# --------------------------------------------------------------------------
# 7. argv shape — pinned to the real CLI signature.
# --------------------------------------------------------------------------


def test_argv_is_grant_use_json_with_db_path_and_all_args():
    client, runner = _client(_ok(_used_packet()))
    _use(client, action="deploy", target="prod")
    argv = runner.calls[0]
    assert argv[0] == "/fake/standing"
    assert argv[1:3] == ["--db-path", "/tmp/standing.db"]
    assert argv[3:5] == ["grant", "use"]
    assert "--json" in argv
    for flag, val in [
        ("--id", "g-1"),
        ("--identity", "/fake/id.json"),
        ("--secret", "s3cr3t"),
        ("--action", "deploy"),
        ("--target", "prod"),
    ]:
        assert argv[argv.index(flag) + 1] == val


def test_argv_omits_db_path_when_unset():
    runner = FakeRunner(_ok(_used_packet()))
    client = StandingGrantUseClient(runner=runner, binary=ResolvedBinary("/b/standing", "configured"), env={})
    _use(client)
    assert "--db-path" not in runner.calls[0]


# --------------------------------------------------------------------------
# 8. binary resolution order — configured preferred; never the DB.
# --------------------------------------------------------------------------


def test_resolve_prefers_configured_explicit_path(tmp_path):
    binpath = tmp_path / "standing"
    binpath.write_text("#!/bin/sh\n")
    binpath.chmod(0o755)
    rb = resolve_standing_binary(env={ENV_STANDING_BIN: str(binpath)})
    assert rb == ResolvedBinary(path=str(binpath), source="configured")


def test_resolve_explicit_but_bad_path_is_unresolved_not_fallthrough(tmp_path):
    # An explicit-but-broken STANDING_BIN must surface as unresolved, not silently
    # fall through to PATH (which would mask a config error).
    rb = resolve_standing_binary(env={ENV_STANDING_BIN: str(tmp_path / "does-not-exist")})
    assert rb is None


def test_resolve_falls_back_to_path(tmp_path, monkeypatch):
    binpath = tmp_path / DEFAULT_STANDING_COMMAND
    binpath.write_text("#!/bin/sh\n")
    binpath.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    rb = resolve_standing_binary(env={"PATH": str(tmp_path)})
    assert rb is not None
    assert rb.source == "path"


def test_resolve_cargo_lab_fallback(tmp_path):
    lab = tmp_path / "git" / "standing" / "target" / "debug"
    lab.mkdir(parents=True)
    binpath = lab / DEFAULT_STANDING_COMMAND
    binpath.write_text("#!/bin/sh\n")
    binpath.chmod(0o755)
    rb = resolve_standing_binary(env={"HOME": str(tmp_path), "PATH": "/nonexistent-dir-xyz"})
    assert rb is not None
    assert rb.source == "cargo_lab"


def test_resolve_unresolved_returns_none():
    rb = resolve_standing_binary(env={"PATH": "/nonexistent-dir-xyz", "HOME": "/nonexistent-home-xyz"})
    assert rb is None
