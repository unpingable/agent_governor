# SPDX-License-Identifier: Apache-2.0
"""ReviewPacket-vs-QueuedPlaybook validator (Slice B-11.S5).

> A ReviewPacket is acceptable evidence only if it stays within the QueuedPlaybook
> that authorized it.

This is a pure, static cross-validator. Given the queue, the queued item, and the
returned packet, it answers: did the packet stay within the item's identity, base,
authority, path fences, output kind, review requirement, and required-test
declarations? It returns a deterministic report — it does NOT raise for ordinary
violations, apply patches, inspect git, touch the filesystem, run tests, invoke
actors, enqueue follow-ups, or mutate anything. It says "valid evidence" or
"violations"; it never says merged / accepted / pushed / live-safe.

Path matching is fnmatch-style (``fnmatch.fnmatchcase``): ``*`` matches across
``/``, so ``src/**`` and ``src/*`` behave alike. This is intentional static hygiene
for scope-fencing; precise segment-aware globbing is a later concern. The validator
never expands a glob against the filesystem — it matches the declared
``files_changed`` strings only.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import Any, Optional

from .playbook_queue import (
    MODE_SYNTHETIC_CONVEYOR,
    OUTPUT_REVIEW_PACKET,
    PlaybookQueue,
    QueuedPlaybook,
)
from .review_packet import (
    AUTHORITY_KEYS,
    STATUS_PROPOSED_PATCH,
    TEST_PASSED,
    ReviewPacket,
)

SEVERITY_ERROR = "error"
SEVERITY_WARNING = "warning"
VALIDATION_SEVERITIES = frozenset({SEVERITY_ERROR, SEVERITY_WARNING})

# Closed issue vocabulary.
CODE_PLAYBOOK_ID_MISMATCH = "playbook_id_mismatch"
CODE_REPO_MISMATCH = "repo_mismatch"
CODE_BASE_BRANCH_MISMATCH = "base_branch_mismatch"
CODE_BASE_SHA_MISMATCH = "base_sha_mismatch"
CODE_UNSUPPORTED_QUEUE_MODE = "unsupported_queue_mode"
CODE_OUTPUT_KIND_NOT_REVIEW_PACKET = "output_kind_not_review_packet"
CODE_OPERATOR_APPROVAL_MISSING = "operator_approval_missing"
CODE_OPERATOR_REVIEW_NOT_REQUIRED = "operator_review_not_required"
CODE_GRANTED_AUTHORITY_EXCEEDS_QUEUE = "granted_authority_exceeds_queue"
CODE_USED_AUTHORITY_EXCEEDS_QUEUE = "used_authority_exceeds_queue"
CODE_REQUESTED_AUTHORITY_EXCEEDS_QUEUE = "requested_authority_exceeds_queue"
CODE_UNSAFE_CHANGED_PATH = "unsafe_changed_path"
CODE_CHANGED_PATH_OUTSIDE_ALLOWED = "changed_path_outside_allowed_paths"
CODE_CHANGED_PATH_MATCHES_FORBIDDEN = "changed_path_matches_forbidden_paths"
CODE_REQUIRED_TEST_MISSING = "required_test_missing"
CODE_REQUIRED_TEST_NOT_PASSING = "required_test_not_passing"
CODE_EXPLICIT_NON_ACTIONS_MISSING = "explicit_non_actions_missing"
CODE_UNSAFE_ARTIFACT_PATH = "unsafe_artifact_path"
VALIDATION_CODES = frozenset(
    {
        CODE_PLAYBOOK_ID_MISMATCH,
        CODE_REPO_MISMATCH,
        CODE_BASE_BRANCH_MISMATCH,
        CODE_BASE_SHA_MISMATCH,
        CODE_UNSUPPORTED_QUEUE_MODE,
        CODE_OUTPUT_KIND_NOT_REVIEW_PACKET,
        CODE_OPERATOR_APPROVAL_MISSING,
        CODE_OPERATOR_REVIEW_NOT_REQUIRED,
        CODE_GRANTED_AUTHORITY_EXCEEDS_QUEUE,
        CODE_USED_AUTHORITY_EXCEEDS_QUEUE,
        CODE_REQUESTED_AUTHORITY_EXCEEDS_QUEUE,
        CODE_UNSAFE_CHANGED_PATH,
        CODE_CHANGED_PATH_OUTSIDE_ALLOWED,
        CODE_CHANGED_PATH_MATCHES_FORBIDDEN,
        CODE_REQUIRED_TEST_MISSING,
        CODE_REQUIRED_TEST_NOT_PASSING,
        CODE_EXPLICIT_NON_ACTIONS_MISSING,
        CODE_UNSAFE_ARTIFACT_PATH,
    }
)


@dataclass(frozen=True)
class ReviewPacketValidationIssue:
    code: str
    severity: str
    message: str
    field: Optional[str] = None

    def __post_init__(self) -> None:
        if self.code not in VALIDATION_CODES:
            raise ValueError(f"unknown validation code {self.code!r}")
        if self.severity not in VALIDATION_SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "field": self.field,
        }


@dataclass(frozen=True)
class ReviewPacketValidation:
    """The pure validation report. ``valid`` is True iff there are no errors;
    warnings do not break validity. ``ready_for_operator_apply`` is a review hint,
    NOT an apply gate."""

    issues: tuple[ReviewPacketValidationIssue, ...]
    ready_for_operator_apply: bool

    @property
    def errors(self) -> tuple[ReviewPacketValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == SEVERITY_ERROR)

    @property
    def warnings(self) -> tuple[ReviewPacketValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity == SEVERITY_WARNING)

    @property
    def valid(self) -> bool:
        return not self.errors

    def codes(self) -> tuple[str, ...]:
        return tuple(i.code for i in self.issues)

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "ready_for_operator_apply": self.ready_for_operator_apply,
            "issues": [i.as_dict() for i in self.issues],
        }


# --------------------------------------------------------------------------- #
# Static helpers (no IO, no glob expansion against a filesystem).
# --------------------------------------------------------------------------- #


def _is_safe_relative_path(p: Any) -> bool:
    if not isinstance(p, str) or p == "":
        return False
    if p.startswith("/"):
        return False
    if "\\" in p:  # POSIX-style paths only; backslash is ambiguous
        return False
    if p == ".":
        return False
    if ".." in p.split("/"):
        return False
    return True


def _matches_any(path: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatchcase(path, pat) for pat in patterns)


# --------------------------------------------------------------------------- #
# The validator.
# --------------------------------------------------------------------------- #


def validate_review_packet_for_queue_item(
    queue: PlaybookQueue,
    item: QueuedPlaybook,
    packet: ReviewPacket,
) -> ReviewPacketValidation:
    """Pure cross-validation. Issues are appended in a deterministic order
    (identity → mode/output/approval → review latch → authority → paths → tests →
    non-actions → artifacts), so repeated validation returns an equal report."""
    issues: list[ReviewPacketValidationIssue] = []

    def err(code: str, message: str, field: Optional[str] = None) -> None:
        issues.append(
            ReviewPacketValidationIssue(code, SEVERITY_ERROR, message, field)
        )

    def warn(code: str, message: str, field: Optional[str] = None) -> None:
        issues.append(
            ReviewPacketValidationIssue(code, SEVERITY_WARNING, message, field)
        )

    # 1. Identity (string comparison only — never inspect whether refs exist).
    eff_base_branch = item.base_branch or queue.base_branch
    eff_base_sha = item.base_sha or queue.base_sha
    if packet.playbook_id != item.playbook_id:
        err(
            CODE_PLAYBOOK_ID_MISMATCH,
            f"packet playbook_id {packet.playbook_id!r} != item {item.playbook_id!r}",
            "playbook_id",
        )
    if packet.repo != queue.repo:
        err(
            CODE_REPO_MISMATCH,
            f"packet repo {packet.repo!r} != queue repo {queue.repo!r}",
            "repo",
        )
    if packet.base_branch != eff_base_branch:
        err(
            CODE_BASE_BRANCH_MISMATCH,
            f"packet base_branch {packet.base_branch!r} != {eff_base_branch!r}",
            "base_branch",
        )
    if packet.base_sha != eff_base_sha:
        err(
            CODE_BASE_SHA_MISMATCH,
            f"packet base_sha {packet.base_sha!r} != {eff_base_sha!r}",
            "base_sha",
        )

    # 2. Queue mode / output kind / approval (defensive — S4 already guarantees
    #    these on parsed objects; fail closed if handed constructed/future types).
    if queue.mode != MODE_SYNTHETIC_CONVEYOR:
        err(CODE_UNSUPPORTED_QUEUE_MODE, f"queue mode {queue.mode!r} not synthetic", "mode")
    if item.output_kind != OUTPUT_REVIEW_PACKET:
        err(
            CODE_OUTPUT_KIND_NOT_REVIEW_PACKET,
            f"item output_kind {item.output_kind!r} not review_packet",
            "output_kind",
        )
    if not item.operator_approved:
        err(CODE_OPERATOR_APPROVAL_MISSING, "queued item is not operator_approved", "operator_approved")

    # 3. Operator-review latch: synthetic conveyor may NOT accept a packet that
    #    declares review-not-required, even though S3 lets one be constructed.
    if not packet.operator_review_required:
        err(
            CODE_OPERATOR_REVIEW_NOT_REQUIRED,
            "packet.operator_review_required is False; synthetic conveyor requires review",
            "operator_review_required",
        )

    # 4. Authority boundary: granted/used must not exceed the queue item's
    #    authority; requested may exceed it (honest "I would need X to continue")
    #    and is only a warning. Compared on the packet's authority axes.
    qa = item.authority
    for k in AUTHORITY_KEYS:
        if getattr(packet.authority.granted, k) and not getattr(qa, k):
            err(
                CODE_GRANTED_AUTHORITY_EXCEEDS_QUEUE,
                f"packet granted authority {k!r} exceeds queued authority",
                k,
            )
    for k in AUTHORITY_KEYS:
        if getattr(packet.authority.used, k) and not getattr(qa, k):
            err(
                CODE_USED_AUTHORITY_EXCEEDS_QUEUE,
                f"packet used authority {k!r} exceeds queued authority",
                k,
            )
    for k in AUTHORITY_KEYS:
        if getattr(packet.authority.requested, k) and not getattr(qa, k):
            warn(
                CODE_REQUESTED_AUTHORITY_EXCEEDS_QUEUE,
                f"packet requests authority {k!r} beyond the queue (evidence only, not granted)",
                k,
            )

    # 5. Path fences over the declared files_changed (static; forbidden wins).
    for path in packet.files_changed:
        if not _is_safe_relative_path(path):
            err(CODE_UNSAFE_CHANGED_PATH, f"unsafe changed path {path!r}", path)
            continue
        if _matches_any(path, item.forbidden_paths):
            err(
                CODE_CHANGED_PATH_MATCHES_FORBIDDEN,
                f"changed path {path!r} matches a forbidden_paths pattern",
                path,
            )
        elif not _matches_any(path, item.allowed_paths):
            err(
                CODE_CHANGED_PATH_OUTSIDE_ALLOWED,
                f"changed path {path!r} is outside allowed_paths",
                path,
            )

    # 6. Required tests must be REPRESENTED in the packet (never executed here).
    packet_tests_by_command: dict[str, list[Any]] = {}
    for t in packet.tests:
        packet_tests_by_command.setdefault(t.command, []).append(t)
    for req in item.required_tests:
        matches = packet_tests_by_command.get(req, [])
        if not matches:
            err(CODE_REQUIRED_TEST_MISSING, f"required test not represented: {req!r}", req)
        elif packet.status == STATUS_PROPOSED_PATCH and any(
            t.status != TEST_PASSED for t in matches
        ):
            err(
                CODE_REQUIRED_TEST_NOT_PASSING,
                f"required test {req!r} is not passing in a proposed_patch packet",
                req,
            )

    # 7. Explicit non-actions must be present (review evidence, not authority).
    if not packet.explicit_non_actions:
        err(
            CODE_EXPLICIT_NON_ACTIONS_MISSING,
            "packet.explicit_non_actions is empty",
            "explicit_non_actions",
        )

    # 8. Artifacts: references only — validate the path, never read the content.
    for art in packet.artifacts:
        if not _is_safe_relative_path(art.path):
            err(CODE_UNSAFE_ARTIFACT_PATH, f"unsafe artifact path {art.path!r}", art.path)

    frozen = tuple(issues)
    has_errors = any(i.severity == SEVERITY_ERROR for i in frozen)
    ready = (not has_errors) and packet.status == STATUS_PROPOSED_PATCH
    return ReviewPacketValidation(issues=frozen, ready_for_operator_apply=ready)


__all__ = [
    "SEVERITY_ERROR",
    "SEVERITY_WARNING",
    "VALIDATION_SEVERITIES",
    "VALIDATION_CODES",
    "CODE_PLAYBOOK_ID_MISMATCH",
    "CODE_REPO_MISMATCH",
    "CODE_BASE_BRANCH_MISMATCH",
    "CODE_BASE_SHA_MISMATCH",
    "CODE_UNSUPPORTED_QUEUE_MODE",
    "CODE_OUTPUT_KIND_NOT_REVIEW_PACKET",
    "CODE_OPERATOR_APPROVAL_MISSING",
    "CODE_OPERATOR_REVIEW_NOT_REQUIRED",
    "CODE_GRANTED_AUTHORITY_EXCEEDS_QUEUE",
    "CODE_USED_AUTHORITY_EXCEEDS_QUEUE",
    "CODE_REQUESTED_AUTHORITY_EXCEEDS_QUEUE",
    "CODE_UNSAFE_CHANGED_PATH",
    "CODE_CHANGED_PATH_OUTSIDE_ALLOWED",
    "CODE_CHANGED_PATH_MATCHES_FORBIDDEN",
    "CODE_REQUIRED_TEST_MISSING",
    "CODE_REQUIRED_TEST_NOT_PASSING",
    "CODE_EXPLICIT_NON_ACTIONS_MISSING",
    "CODE_UNSAFE_ARTIFACT_PATH",
    "ReviewPacketValidationIssue",
    "ReviewPacketValidation",
    "validate_review_packet_for_queue_item",
]
