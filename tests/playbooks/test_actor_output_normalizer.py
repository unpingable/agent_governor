# SPDX-License-Identifier: Apache-2.0
"""Tests for the S7 actor-output → ReviewPacket normalizer (Model B)."""

from __future__ import annotations

import pytest

from governor.playbooks.actor_output_normalizer import (
    CLAIMED_PASSED,
    CODE_ACTOR_KIND_MISMATCH,
    CODE_HANDOFF_BINDING_MISMATCH,
    CODE_INVALID_CLAIMED_STATUS,
    CODE_MISSING_REQUIRED_FIELD,
    CODE_UNKNOWN_ACTOR_KIND,
    CODE_UNKNOWN_FIELD,
    ActorOutput,
    ActorOutputNormalizeError,
    ActorOutputParseError,
    ClaimedTestResult,
    normalize_actor_output_to_review_packet,
)
from governor.playbooks.handoff_renderer import ACTOR_CLAUDE, ACTOR_CODEX, render_handoff
from governor.playbooks.playbook_queue import (
    OUTPUT_REVIEW_PACKET,
    PlaybookQueue,
    QueuedPlaybook,
)
from governor.playbooks.review_packet import (
    SCHEMA_VERSION as RP_SCHEMA,
    STATUS_PROPOSED_PATCH,
    TEST_NOT_RUN,
    TEST_PASSED,
    ReviewPacket,
    ReviewTestResult,
)
from governor.playbooks.review_packet_validator import (
    CODE_REQUIRED_TEST_NOT_PASSING,
    validate_review_packet_for_queue_item,
)

REQ_TEST = "pytest tests/widget -q"


def _item(**over) -> QueuedPlaybook:
    kw = dict(
        playbook_id="pb-1",
        title="Tidy the widget",
        objective="Refactor widget for clarity.",
        output_kind=OUTPUT_REVIEW_PACKET,
        allowed_paths=("src/widget/",),
        forbidden_paths=("src/secret/",),
        required_tests=(REQ_TEST,),
        stop_conditions=("any test fails",),
        operator_approved=True,
        lane="feat/widget",
        base_branch="main",
        base_sha="cafef00d",
    )
    kw.update(over)
    return QueuedPlaybook(**kw)


def _queue(item) -> PlaybookQueue:
    return PlaybookQueue(
        queue_id="q-1",
        repo="agent_gov",
        base_branch="main",
        base_sha="cafef00d",
        mode="synthetic_conveyor",
        items=(item,),
    )


def _handoff(item=None):
    item = item or _item()
    return render_handoff(
        item,
        handoff_id="h-1",
        repo="agent_gov",
        base_branch="main",
        base_sha="cafef00d",
        actor_kind=ACTOR_CLAUDE,
    )


def _actor_output(**over) -> ActorOutput:
    kw = dict(
        actor_output_id="ao-1",
        handoff_packet_id="h-1",
        actor_kind=ACTOR_CLAUDE,
        captured_text="I refactored the widget and ran the tests; all green.",
        captured_at="2026-06-30T12:00:00Z",
        capture_origin="offline_h_harness",
        claimed_files_touched=("src/widget/core.py",),
        claimed_commands_run=(REQ_TEST,),
        claimed_test_results=(
            ClaimedTestResult(command=REQ_TEST, claimed_status=CLAIMED_PASSED),
        ),
        authority_claims=(),
    )
    kw.update(over)
    return ActorOutput(**kw)


def _normalize(ao=None, ho=None, **kw):
    return normalize_actor_output_to_review_packet(
        ao or _actor_output(), ho or _handoff(), **kw
    )


# --------------------------------------------------------------------------- #
# THE required fence: actor claims all tests passed → S5 still fails.
# --------------------------------------------------------------------------- #


def test_actor_claimed_pass_still_fails_s5_required_test_not_passing():
    item = _item()
    queue = _queue(item)
    handoff = _handoff(item)
    ao = _actor_output()  # claims REQ_TEST passed
    packet = normalize_actor_output_to_review_packet(ao, handoff)

    # The required test is REPRESENTED (not "missing") but not_run, in a proposed_patch.
    assert packet.status == STATUS_PROPOSED_PATCH
    rep = [t for t in packet.tests if t.command == REQ_TEST]
    assert rep and all(t.status == TEST_NOT_RUN for t in rep)

    report = validate_review_packet_for_queue_item(queue, item, packet)
    assert not report.valid
    assert CODE_REQUIRED_TEST_NOT_PASSING in report.codes()


def test_independent_verifier_receipt_can_make_a_required_test_pass():
    item = _item()
    queue = _queue(item)
    handoff = _handoff(item)
    verified = (ReviewTestResult(command=REQ_TEST, status=TEST_PASSED, exit_code=0),)
    packet = normalize_actor_output_to_review_packet(
        _actor_output(), handoff, verifier_results=verified
    )
    rep = [t for t in packet.tests if t.command == REQ_TEST]
    assert rep and all(t.status == TEST_PASSED for t in rep)
    report = validate_review_packet_for_queue_item(queue, item, packet)
    assert CODE_REQUIRED_TEST_NOT_PASSING not in report.codes()


# --------------------------------------------------------------------------- #
# Authority claims do not survive as authority.
# --------------------------------------------------------------------------- #


def test_actor_authority_claims_are_stripped_and_recorded_as_evidence():
    ao = _actor_output(authority_claims=("tests_pass", "safe_to_commit"))
    packet = _normalize(ao=ao)
    # never propagated to used/granted authority
    for k in ("commit", "push", "subprocess", "live_origin"):
        assert not getattr(packet.authority.used, k)
        assert not getattr(packet.authority.granted, k)
    # preserved only as evidence of attempted claim
    blob = "\n".join(packet.risks)
    assert "tests_pass" in blob and "REFUSED" in blob


def test_emitted_packet_is_not_an_authority_admission():
    # The packet defaults to requiring review and grants/uses nothing.
    packet = _normalize()
    assert packet.operator_review_required is True
    assert packet.authority.granted.as_dict() == {
        k: False for k in packet.authority.granted.as_dict()
    }
    assert packet.authority.used.as_dict() == {
        k: False for k in packet.authority.used.as_dict()
    }


# --------------------------------------------------------------------------- #
# Handoff binding preserved.
# --------------------------------------------------------------------------- #


def test_handoff_seal_binding_preserved_in_packet():
    handoff = _handoff()
    packet = _normalize(ho=handoff)
    notes = "\n".join(packet.design_notes)
    assert handoff.compute_seal() in notes
    assert handoff.handoff_id in notes


def test_binding_mismatch_refused():
    ao = _actor_output(handoff_packet_id="not-h-1")
    with pytest.raises(ActorOutputNormalizeError) as ei:
        _normalize(ao=ao)
    assert ei.value.code == CODE_HANDOFF_BINDING_MISMATCH


def test_actor_kind_mismatch_refused():
    handoff = render_handoff(
        _item(),
        handoff_id="h-1",
        repo="agent_gov",
        base_branch="main",
        base_sha="cafef00d",
        actor_kind=ACTOR_CODEX,
    )
    ao = _actor_output(actor_kind=ACTOR_CLAUDE)  # handoff is codex
    with pytest.raises(ActorOutputNormalizeError) as ei:
        _normalize(ao=ao, ho=handoff)
    assert ei.value.code == CODE_ACTOR_KIND_MISMATCH


# --------------------------------------------------------------------------- #
# Captured text carried as advisory evidence; scope honesty.
# --------------------------------------------------------------------------- #


def test_captured_text_carried_as_advisory_evidence():
    ao = _actor_output(captured_text="UNIQUE-MARKER-12345 did the thing")
    packet = _normalize(ao=ao)
    assert "UNIQUE-MARKER-12345 did the thing" in "\n".join(packet.design_notes)


def test_claimed_files_surface_to_s5_path_fence_not_dropped():
    item = _item()
    queue = _queue(item)
    handoff = _handoff(item)
    ao = _actor_output(claimed_files_touched=("src/secret/leak.py",))  # forbidden
    packet = normalize_actor_output_to_review_packet(ao, handoff)
    assert "src/secret/leak.py" in packet.files_changed  # not silently dropped
    report = validate_review_packet_for_queue_item(queue, item, packet)
    assert not report.valid  # forbidden path surfaces as an S5 error


# --------------------------------------------------------------------------- #
# Schema-invalid ActorOutput refuses (hostile-input discipline).
# --------------------------------------------------------------------------- #


def _good_dict() -> dict:
    return _actor_output().as_dict()


def test_from_dict_round_trip():
    ao = _actor_output()
    assert ActorOutput.from_dict(ao.as_dict()).as_dict() == ao.as_dict()


def test_from_dict_unknown_field_refused():
    d = _good_dict()
    d["sneaky"] = "x"
    with pytest.raises(ActorOutputParseError) as ei:
        ActorOutput.from_dict(d)
    assert ei.value.code == CODE_UNKNOWN_FIELD


def test_from_dict_missing_required_field_refused():
    d = _good_dict()
    del d["capture_origin"]
    with pytest.raises(ActorOutputParseError) as ei:
        ActorOutput.from_dict(d)
    assert ei.value.code == CODE_MISSING_REQUIRED_FIELD


def test_from_dict_unknown_actor_kind_refused():
    d = _good_dict()
    d["actor_kind"] = "gpt5"
    with pytest.raises(ActorOutputParseError) as ei:
        ActorOutput.from_dict(d)
    assert ei.value.code == CODE_UNKNOWN_ACTOR_KIND


def test_claimed_test_invalid_status_refused():
    with pytest.raises(ActorOutputParseError) as ei:
        ClaimedTestResult(command="x", claimed_status="green")
    assert ei.value.code == CODE_INVALID_CLAIMED_STATUS


# --------------------------------------------------------------------------- #
# S3 ReviewPacket schema unchanged + round-trips.
# --------------------------------------------------------------------------- #


def test_emitted_packet_uses_unchanged_s3_schema_and_round_trips():
    packet = _normalize()
    assert packet.schema_version == RP_SCHEMA
    rt = ReviewPacket.from_json(packet.to_json())
    assert rt.to_manifest_dict() == packet.to_manifest_dict()


def test_normalize_is_deterministic():
    a = _normalize()
    b = _normalize()
    assert a.to_json() == b.to_json()
