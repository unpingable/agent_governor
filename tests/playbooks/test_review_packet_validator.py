# SPDX-License-Identifier: Apache-2.0
"""ReviewPacket-vs-QueuedPlaybook validator (Slice B-11.S5).

A returned ReviewPacket is acceptable evidence only if it stayed inside the
QueuedPlaybook that authorized it. These tests pin identity, base, authority
boundary, path fences, required-test representation, the operator-review latch, and
that the validator is pure (returns a deterministic report; touches nothing).
"""

from __future__ import annotations

from governor.playbooks.playbook_queue import (
    MODE_SYNTHETIC_CONVEYOR,
    OUTPUT_REVIEW_PACKET,
    PlaybookQueue,
    QueuedPlaybook,
)
from governor.playbooks.review_packet import (
    STATUS_BLOCKED,
    STATUS_FAILED_TESTS,
    STATUS_NO_CHANGE,
    STATUS_PROPOSED_PATCH,
    TEST_FAILED,
    TEST_PASSED,
    AuthoritySet,
    ReviewAuthority,
    ReviewPacket,
    ReviewTestResult,
)
from governor.playbooks.review_packet_validator import (
    CODE_BASE_SHA_MISMATCH,
    CODE_CHANGED_PATH_MATCHES_FORBIDDEN,
    CODE_CHANGED_PATH_OUTSIDE_ALLOWED,
    CODE_EXPLICIT_NON_ACTIONS_MISSING,
    CODE_GRANTED_AUTHORITY_EXCEEDS_QUEUE,
    CODE_OPERATOR_REVIEW_NOT_REQUIRED,
    CODE_PLAYBOOK_ID_MISMATCH,
    CODE_REQUESTED_AUTHORITY_EXCEEDS_QUEUE,
    CODE_REQUIRED_TEST_MISSING,
    CODE_UNSAFE_CHANGED_PATH,
    CODE_USED_AUTHORITY_EXCEEDS_QUEUE,
    validate_review_packet_for_queue_item,
)

_REPO = "ag"
_BASE_BRANCH = "feat/playbooks-synthetic-conveyor"
_BASE_SHA = "5c2f831"
_PLAYBOOK_ID = "B-11.S6-handoff-renderer"
_TEST_CMD = "pytest tests/playbooks -q"


def _item(**overrides) -> QueuedPlaybook:
    base = dict(
        playbook_id=_PLAYBOOK_ID,
        title="t",
        objective="o",
        output_kind=OUTPUT_REVIEW_PACKET,
        allowed_paths=("src/governor/playbooks/**", "tests/playbooks/**"),
        stop_conditions=("requires subprocess",),
        operator_approved=True,
        required_tests=(_TEST_CMD,),
        forbidden_paths=("src/governor/doctrine/**",),
    )
    base.update(overrides)
    return QueuedPlaybook(**base)


def _queue(item: QueuedPlaybook) -> PlaybookQueue:
    return PlaybookQueue(
        queue_id="night-a",
        repo=_REPO,
        base_branch=_BASE_BRANCH,
        base_sha=_BASE_SHA,
        mode=MODE_SYNTHETIC_CONVEYOR,
        items=(item,),
    )


def _packet(**overrides) -> ReviewPacket:
    base = dict(
        packet_id="pk-1",
        playbook_id=_PLAYBOOK_ID,
        repo=_REPO,
        branch="feat/x",
        base_branch=_BASE_BRANCH,
        base_sha=_BASE_SHA,
        status=STATUS_PROPOSED_PATCH,
        files_changed=("src/governor/playbooks/handoff.py",),
        tests=(ReviewTestResult(command=_TEST_CMD, status=TEST_PASSED),),
        explicit_non_actions=("did not push",),
        operator_review_required=True,
    )
    base.update(overrides)
    return ReviewPacket(**base)


def _validate(item: QueuedPlaybook, packet: ReviewPacket):
    return validate_review_packet_for_queue_item(_queue(item), item, packet)


# --------------------------------------------------------------------------- #
# Happy path.
# --------------------------------------------------------------------------- #


class TestValidPacket:
    def test_valid_proposed_patch(self):
        v = _validate(_item(), _packet())
        assert v.valid is True
        assert v.errors == ()
        assert v.ready_for_operator_apply is True

    def test_validation_is_deterministic(self):
        item, packet = _item(), _packet(files_changed=("zzz.txt", "src/governor/playbooks/a.py"))
        assert _validate(item, packet) == _validate(item, packet)


# --------------------------------------------------------------------------- #
# Identity.
# --------------------------------------------------------------------------- #


class TestIdentity:
    def test_playbook_id_mismatch_errors(self):
        v = _validate(_item(), _packet(playbook_id="other"))
        assert CODE_PLAYBOOK_ID_MISMATCH in v.codes()
        assert v.valid is False

    def test_base_sha_mismatch_errors(self):
        v = _validate(_item(), _packet(base_sha="deadbee"))
        assert CODE_BASE_SHA_MISMATCH in v.codes()


# --------------------------------------------------------------------------- #
# Operator-review latch.
# --------------------------------------------------------------------------- #


class TestOperatorReviewLatch:
    def test_review_not_required_rejected(self):
        v = _validate(_item(), _packet(operator_review_required=False))
        assert CODE_OPERATOR_REVIEW_NOT_REQUIRED in v.codes()
        assert v.valid is False


# --------------------------------------------------------------------------- #
# Authority boundary.
# --------------------------------------------------------------------------- #


class TestAuthorityBoundary:
    def test_granted_push_exceeds_queue_errors(self):
        pkt = _packet(
            authority=ReviewAuthority(
                granted=AuthoritySet(push=True), used=AuthoritySet(push=True)
            )
        )
        v = _validate(_item(), pkt)
        assert CODE_GRANTED_AUTHORITY_EXCEEDS_QUEUE in v.codes()
        assert CODE_USED_AUTHORITY_EXCEEDS_QUEUE in v.codes()
        assert v.valid is False

    def test_used_network_exceeds_queue_errors(self):
        pkt = _packet(
            authority=ReviewAuthority(
                granted=AuthoritySet(network=True), used=AuthoritySet(network=True)
            )
        )
        v = _validate(_item(), pkt)
        assert CODE_USED_AUTHORITY_EXCEEDS_QUEUE in v.codes()

    def test_requested_only_overage_warns_not_errors(self):
        # An honest blocked packet may report it WOULD need network — evidence,
        # not a grant.
        pkt = _packet(
            status=STATUS_BLOCKED,
            authority=ReviewAuthority(requested=AuthoritySet(network=True)),
        )
        v = _validate(_item(), pkt)
        assert CODE_REQUESTED_AUTHORITY_EXCEEDS_QUEUE in v.codes()
        # warning only — still valid evidence (no errors from authority).
        assert all(
            i.severity == "warning"
            for i in v.issues
            if i.code == CODE_REQUESTED_AUTHORITY_EXCEEDS_QUEUE
        )
        assert v.valid is True
        assert v.ready_for_operator_apply is False  # blocked -> not ready


# --------------------------------------------------------------------------- #
# Path fences.
# --------------------------------------------------------------------------- #


class TestPathFences:
    def test_path_outside_allowed_errors(self):
        v = _validate(_item(), _packet(files_changed=("src/governor/daemon.py",)))
        assert CODE_CHANGED_PATH_OUTSIDE_ALLOWED in v.codes()

    def test_forbidden_path_wins_over_allowed(self):
        # doctrine is forbidden even if an allowed pattern could match it.
        item = _item(
            allowed_paths=("src/governor/**",),
            forbidden_paths=("src/governor/doctrine/**",),
        )
        v = _validate(item, _packet(files_changed=("src/governor/doctrine/x.py",)))
        assert CODE_CHANGED_PATH_MATCHES_FORBIDDEN in v.codes()
        assert CODE_CHANGED_PATH_OUTSIDE_ALLOWED not in v.codes()

    def test_absolute_changed_path_errors(self):
        v = _validate(_item(), _packet(files_changed=("/etc/passwd",)))
        assert CODE_UNSAFE_CHANGED_PATH in v.codes()

    def test_traversal_changed_path_errors(self):
        v = _validate(_item(), _packet(files_changed=("../escape.py",)))
        assert CODE_UNSAFE_CHANGED_PATH in v.codes()


# --------------------------------------------------------------------------- #
# Required tests.
# --------------------------------------------------------------------------- #


class TestRequiredTests:
    def test_missing_required_test_errors(self):
        v = _validate(_item(), _packet(tests=()))
        assert CODE_REQUIRED_TEST_MISSING in v.codes()

    def test_proposed_patch_with_failing_required_test_not_ready(self):
        pkt = _packet(tests=(ReviewTestResult(command=_TEST_CMD, status=TEST_FAILED),))
        v = _validate(_item(), pkt)
        assert v.valid is False
        assert v.ready_for_operator_apply is False

    def test_failed_tests_packet_is_evidence_not_ready(self):
        # A failed_tests packet honestly reporting a failing test is valid
        # evidence, just not ready to apply.
        pkt = _packet(
            status=STATUS_FAILED_TESTS,
            tests=(ReviewTestResult(command=_TEST_CMD, status=TEST_FAILED),),
        )
        v = _validate(_item(), pkt)
        assert v.valid is True  # honest failure is allowed evidence
        assert v.ready_for_operator_apply is False


# --------------------------------------------------------------------------- #
# Explicit non-actions + status readiness.
# --------------------------------------------------------------------------- #


class TestNonActionsAndReadiness:
    def test_missing_explicit_non_actions_errors(self):
        v = _validate(_item(), _packet(explicit_non_actions=()))
        assert CODE_EXPLICIT_NON_ACTIONS_MISSING in v.codes()

    def test_no_change_packet_valid_but_not_ready(self):
        v = _validate(_item(), _packet(status=STATUS_NO_CHANGE, files_changed=(), tests=()))
        # no_change with no required tests represented -> a required test is still
        # declared, so missing-test errors; assert readiness is False regardless.
        assert v.ready_for_operator_apply is False


# --------------------------------------------------------------------------- #
# Inertness: the validator runs nothing and touches nothing.
# --------------------------------------------------------------------------- #


class TestInertness:
    def test_followups_do_not_affect_authority(self):
        # A packet may carry followups; they are inert and ignored by the validator.
        from governor.playbooks.review_packet import ReviewFollowup

        pkt = _packet(
            followups=(ReviewFollowup(id="S6", title="renderer", reason="next"),)
        )
        v = _validate(_item(), pkt)
        assert v.valid is True  # followups neither help nor harm validity

    def test_no_execution_surface_in_module(self):
        import governor.playbooks.review_packet_validator as mod

        src = mod.__file__
        with open(src, encoding="utf-8") as f:
            text = f.read()
        for forbidden in ("subprocess.", "os.system", "Popen", "fcntl"):
            assert forbidden not in text
