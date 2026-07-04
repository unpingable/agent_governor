# SPDX-License-Identifier: Apache-2.0
"""Actor-output → ReviewPacket normalizer (Slice B-11.S7).

> An actor's reply is testimony, not a receipt. S7 turns what an offline actor *says*
> happened into the inert evidence artifact (an S3 ReviewPacket) the conveyor already
> knows how to validate (S5) and review — **without** converting any actor claim into a
> passing test, validator satisfaction, admission, or authority. (Model B, ratified
> 2026-06-30. See ``docs/playbooks/synthetic-conveyor-s7-contract.md``.)

This is a pure, inert normalizer. There is NO live actor here — AG never runs Claude or
Codex. The external H-series harness runs the actor OUTSIDE AG and captures a static
``ActorOutput`` record; S7 maps that record + the S6 ``HandoffPacket`` into a
``ReviewPacket``. It does not run a test, spawn a subprocess, touch the network, read or
apply a diff, inspect git, mutate the repo, or admit anything.

Model B, carried by construction:

- **Claimed test results are claims, not verifier receipts.** Each required test from
  the handoff is REPRESENTED in the packet as ``not_run`` (the actor's claim is carried
  only as advisory ``summary`` text). Because the packet is a ``proposed_patch``, S5's
  ``required_test_not_passing`` fires on actor testimony — the actor's word cannot green
  its own gate. A required test only becomes ``passed`` when an **independent verifier
  receipt** (``verifier_results`` from an existing verifier path) is supplied.
- **Actor authority claims are stripped and refused.** They are preserved only as
  *evidence of an attempted claim* (in ``risks``), never propagated to
  ``ReviewAuthority.used`` (which stays fully closed). The emitted packet fails the
  authority-admission predicate.
- **Review stays required.** ``operator_review_required`` is always True.
- **Handoff binding preserved.** The packet carries the handoff seal (provenance); an
  ``ActorOutput`` whose ``handoff_packet_id`` (or ``actor_kind``) does not match the
  handoff is refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .handoff_renderer import ACTOR_KINDS, HandoffPacket
from .review_packet import (
    STATUS_PROPOSED_PATCH,
    TEST_NOT_RUN,
    AuthoritySet,
    ReviewAuthority,
    ReviewPacket,
    ReviewTestResult,
)

ACTOR_OUTPUT_SCHEMA_VERSION = "actor_output.v0"
SUPPORTED_ACTOR_OUTPUT_SCHEMA_VERSIONS = frozenset({ACTOR_OUTPUT_SCHEMA_VERSION})

# Claimed test status (closed vocabulary). These are the ACTOR'S CLAIMS — distinct from
# the verified REVIEW_TEST_STATUSES the ReviewPacket records. A claim never becomes a
# verified status without an independent verifier receipt.
CLAIMED_PASSED = "passed"
CLAIMED_FAILED = "failed"
CLAIMED_UNKNOWN = "unknown"
CLAIMED_TEST_STATUSES = frozenset({CLAIMED_PASSED, CLAIMED_FAILED, CLAIMED_UNKNOWN})

# Closed parse-failure vocabulary (hostile-input discipline).
CODE_UNSUPPORTED_SCHEMA = "unsupported_schema"
CODE_UNKNOWN_ACTOR_KIND = "unknown_actor_kind"
CODE_MISSING_REQUIRED_FIELD = "missing_required_field"
CODE_UNKNOWN_FIELD = "unknown_field"
CODE_INVALID_FIELD_TYPE = "invalid_field_type"
CODE_INVALID_CLAIMED_STATUS = "invalid_claimed_status"
ACTOR_OUTPUT_PARSE_CODES = frozenset(
    {
        CODE_UNSUPPORTED_SCHEMA,
        CODE_UNKNOWN_ACTOR_KIND,
        CODE_MISSING_REQUIRED_FIELD,
        CODE_UNKNOWN_FIELD,
        CODE_INVALID_FIELD_TYPE,
        CODE_INVALID_CLAIMED_STATUS,
    }
)

# Closed normalize-failure vocabulary.
CODE_HANDOFF_BINDING_MISMATCH = "handoff_binding_mismatch"
CODE_ACTOR_KIND_MISMATCH = "actor_kind_mismatch"
NORMALIZE_CODES = frozenset(
    {CODE_HANDOFF_BINDING_MISMATCH, CODE_ACTOR_KIND_MISMATCH}
)


class ActorOutputParseError(ValueError):
    """A typed, fail-closed ActorOutput parse rejection (closed
    ``ACTOR_OUTPUT_PARSE_CODES``)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


class ActorOutputNormalizeError(ValueError):
    """A typed normalize rejection — the ActorOutput does not bind to the handoff
    (closed ``NORMALIZE_CODES``)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


# --------------------------------------------------------------------------- #
# Inert input records.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ClaimedTestResult:
    """One test the actor CLAIMS it ran. A claim, not a verifier receipt — S7 never
    converts ``claimed_status`` into a verified test status."""

    command: str
    claimed_status: str
    exit_code: Optional[int] = None
    summary: Optional[str] = None

    def __post_init__(self) -> None:
        if self.claimed_status not in CLAIMED_TEST_STATUSES:
            raise ActorOutputParseError(
                CODE_INVALID_CLAIMED_STATUS,
                f"claimed_status {self.claimed_status!r} not in "
                f"{sorted(CLAIMED_TEST_STATUSES)}",
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "claimed_status": self.claimed_status,
            "exit_code": self.exit_code,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClaimedTestResult":
        if not isinstance(data, dict):
            raise ActorOutputParseError(
                CODE_INVALID_FIELD_TYPE, "claimed_test_results entry must be an object"
            )
        for k in ("command", "claimed_status"):
            if k not in data:
                raise ActorOutputParseError(
                    CODE_MISSING_REQUIRED_FIELD,
                    f"claimed_test_results entry missing {k!r}",
                )
        return cls(
            command=str(data["command"]),
            claimed_status=str(data["claimed_status"]),
            exit_code=data.get("exit_code"),
            summary=data.get("summary"),
        )


_ACTOR_OUTPUT_KEYS = frozenset(
    {
        "schema_version",
        "actor_output_id",
        "handoff_packet_id",
        "actor_kind",
        "captured_text",
        "claimed_files_touched",
        "claimed_commands_run",
        "claimed_test_results",
        "authority_claims",
        "captured_at",
        "capture_origin",
    }
)
_ACTOR_OUTPUT_REQUIRED = (
    "actor_output_id",
    "handoff_packet_id",
    "actor_kind",
    "captured_text",
    "captured_at",
    "capture_origin",
)


@dataclass(frozen=True)
class ActorOutput:
    """A static, inert capture of what an offline actor returned. NOT a live actor and
    NOT a transcript stream — the H-harness produces this OUTSIDE AG and hands it in.

    Everything here is the actor's testimony: ``claimed_*`` and ``authority_claims`` are
    claims, ``captured_text`` is advisory evidence, and ``capture_origin`` /
    ``captured_at`` are descriptive strings (``capture_origin`` is NOT a typed origin
    enum and never gates admission)."""

    actor_output_id: str
    handoff_packet_id: str
    actor_kind: str
    captured_text: str
    captured_at: str
    capture_origin: str
    claimed_files_touched: tuple[str, ...] = ()
    claimed_commands_run: tuple[str, ...] = ()
    claimed_test_results: tuple[ClaimedTestResult, ...] = ()
    authority_claims: tuple[str, ...] = ()
    schema_version: str = ACTOR_OUTPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_ACTOR_OUTPUT_SCHEMA_VERSIONS:
            raise ActorOutputParseError(
                CODE_UNSUPPORTED_SCHEMA,
                f"schema_version {self.schema_version!r}; supported "
                f"{sorted(SUPPORTED_ACTOR_OUTPUT_SCHEMA_VERSIONS)}",
            )
        if self.actor_kind not in ACTOR_KINDS:
            raise ActorOutputParseError(
                CODE_UNKNOWN_ACTOR_KIND,
                f"actor_kind {self.actor_kind!r} not in {sorted(ACTOR_KINDS)}",
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "actor_output_id": self.actor_output_id,
            "handoff_packet_id": self.handoff_packet_id,
            "actor_kind": self.actor_kind,
            "captured_text": self.captured_text,
            "captured_at": self.captured_at,
            "capture_origin": self.capture_origin,
            "claimed_files_touched": list(self.claimed_files_touched),
            "claimed_commands_run": list(self.claimed_commands_run),
            "claimed_test_results": [t.as_dict() for t in self.claimed_test_results],
            "authority_claims": list(self.authority_claims),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActorOutput":
        if not isinstance(data, dict):
            raise ActorOutputParseError(
                CODE_INVALID_FIELD_TYPE, "ActorOutput must be a JSON object"
            )
        unknown = set(data) - _ACTOR_OUTPUT_KEYS
        if unknown:
            raise ActorOutputParseError(
                CODE_UNKNOWN_FIELD,
                f"unknown field(s) {sorted(unknown)} (closed envelope)",
            )
        for k in _ACTOR_OUTPUT_REQUIRED:
            if k not in data:
                raise ActorOutputParseError(
                    CODE_MISSING_REQUIRED_FIELD, f"missing required field {k!r}"
                )

        def _str_tuple(key: str) -> tuple[str, ...]:
            raw = data.get(key, ())
            if isinstance(raw, str) or not isinstance(raw, (list, tuple)):
                raise ActorOutputParseError(
                    CODE_INVALID_FIELD_TYPE, f"{key!r} must be a list of strings"
                )
            if not all(isinstance(x, str) for x in raw):
                raise ActorOutputParseError(
                    CODE_INVALID_FIELD_TYPE, f"{key!r} must be a list of strings"
                )
            return tuple(raw)

        for k in ("actor_output_id", "handoff_packet_id", "captured_text",
                  "captured_at", "capture_origin"):
            if not isinstance(data[k], str):
                raise ActorOutputParseError(
                    CODE_INVALID_FIELD_TYPE, f"{k!r} must be a string"
                )
        ctr_raw = data.get("claimed_test_results", ())
        if isinstance(ctr_raw, str) or not isinstance(ctr_raw, (list, tuple)):
            raise ActorOutputParseError(
                CODE_INVALID_FIELD_TYPE, "claimed_test_results must be a list"
            )
        return cls(
            actor_output_id=data["actor_output_id"],
            handoff_packet_id=data["handoff_packet_id"],
            actor_kind=str(data["actor_kind"]),
            captured_text=data["captured_text"],
            captured_at=data["captured_at"],
            capture_origin=data["capture_origin"],
            claimed_files_touched=_str_tuple("claimed_files_touched"),
            claimed_commands_run=_str_tuple("claimed_commands_run"),
            claimed_test_results=tuple(
                ClaimedTestResult.from_dict(t) for t in ctr_raw
            ),
            authority_claims=_str_tuple("authority_claims"),
            schema_version=str(data.get("schema_version", ACTOR_OUTPUT_SCHEMA_VERSION)),
        )


# --------------------------------------------------------------------------- #
# The normalizer.
# --------------------------------------------------------------------------- #


def _claimed_index(actor_output: ActorOutput) -> dict[str, ClaimedTestResult]:
    # Last claim wins for a given command (deterministic over input order).
    idx: dict[str, ClaimedTestResult] = {}
    for c in actor_output.claimed_test_results:
        idx[c.command] = c
    return idx


def normalize_actor_output_to_review_packet(
    actor_output: ActorOutput,
    handoff_packet: HandoffPacket,
    *,
    verifier_results: tuple[ReviewTestResult, ...] = (),
) -> ReviewPacket:
    """Map an ``ActorOutput`` + its ``HandoffPacket`` into an inert S3 ``ReviewPacket``
    (schema unchanged), ready for the S5 validator.

    Pure — no IO, no actor run, no test execution, no git/patch/network. Model B: each
    handoff required test is represented as ``not_run`` (actor claim → advisory summary)
    unless an **independent** ``verifier_results`` entry matches its command. Actor
    authority claims are stripped and recorded only as evidence of attempted claim.

    Refuses (``ActorOutputNormalizeError``) when the actor output does not bind to the
    handoff (``handoff_packet_id`` or ``actor_kind`` mismatch)."""
    if actor_output.handoff_packet_id != handoff_packet.handoff_id:
        raise ActorOutputNormalizeError(
            CODE_HANDOFF_BINDING_MISMATCH,
            f"actor_output.handoff_packet_id {actor_output.handoff_packet_id!r} "
            f"!= handoff_id {handoff_packet.handoff_id!r}",
        )
    if actor_output.actor_kind != handoff_packet.actor_kind:
        raise ActorOutputNormalizeError(
            CODE_ACTOR_KIND_MISMATCH,
            f"actor_output.actor_kind {actor_output.actor_kind!r} "
            f"!= handoff actor_kind {handoff_packet.actor_kind!r}",
        )

    seal = handoff_packet.compute_seal()
    claims = _claimed_index(actor_output)
    verified_by_command = {v.command: v for v in verifier_results}

    # Required tests: represented but not_run, unless an independent verifier result
    # covers the command. The actor's claim rides only in the advisory summary.
    tests: list[ReviewTestResult] = []
    for req in handoff_packet.required_tests:
        if req in verified_by_command:
            tests.append(verified_by_command[req])
            continue
        claim = claims.get(req)
        summary = (
            f"actor-claimed: {claim.claimed_status} (UNVERIFIED — not a verifier receipt)"
            if claim is not None
            else "no actor claim; no verifier receipt"
        )
        tests.append(
            ReviewTestResult(command=req, status=TEST_NOT_RUN, summary=summary)
        )

    # Actor authority claims: stripped from authority, preserved as risk evidence only.
    risks = tuple(
        f"actor asserted authority claim {c!r} — REFUSED, not admitted"
        for c in actor_output.authority_claims
    ) + (
        ("actor-claimed test results are unverified (Model B): not a passing basis",)
        if actor_output.claimed_test_results
        else ()
    )

    design_notes = (
        f"bound to handoff {handoff_packet.handoff_id} (seal {seal})",
        f"actor_output_id: {actor_output.actor_output_id}",
        f"actor_kind: {actor_output.actor_kind}",
        f"capture_origin: {actor_output.capture_origin} (descriptive only)",
        f"captured_at: {actor_output.captured_at}",
        "captured_text (advisory evidence):",
        actor_output.captured_text,
    ) + tuple(
        f"actor claims command run: {c}" for c in actor_output.claimed_commands_run
    )

    explicit_non_actions = (
        "normalizer ran no tests; required tests are represented as not_run "
        "(actor claims are advisory only)",
        "no patch applied, no git, no network, no subprocess, no actor executed",
        "actor authority claims refused, not admitted",
    )

    return ReviewPacket(
        packet_id=f"rp-{actor_output.actor_output_id}",
        playbook_id=handoff_packet.playbook_id,
        repo=handoff_packet.repo,
        branch=handoff_packet.lane or f"synthetic/{handoff_packet.handoff_id}",
        base_branch=handoff_packet.base_branch,
        base_sha=handoff_packet.base_sha,
        status=STATUS_PROPOSED_PATCH,
        authority=ReviewAuthority(
            requested=AuthoritySet(),
            granted=AuthoritySet(),
            used=AuthoritySet(),
        ),
        lane=handoff_packet.lane,
        allowed_paths=handoff_packet.allowed_paths,
        forbidden_paths=handoff_packet.forbidden_paths,
        files_changed=actor_output.claimed_files_touched,
        tests=tuple(tests),
        risks=risks,
        design_notes=design_notes,
        explicit_non_actions=explicit_non_actions,
        operator_review_required=True,
    )


__all__ = [
    "ACTOR_OUTPUT_SCHEMA_VERSION",
    "SUPPORTED_ACTOR_OUTPUT_SCHEMA_VERSIONS",
    "CLAIMED_PASSED",
    "CLAIMED_FAILED",
    "CLAIMED_UNKNOWN",
    "CLAIMED_TEST_STATUSES",
    "ACTOR_OUTPUT_PARSE_CODES",
    "CODE_UNSUPPORTED_SCHEMA",
    "CODE_UNKNOWN_ACTOR_KIND",
    "CODE_MISSING_REQUIRED_FIELD",
    "CODE_UNKNOWN_FIELD",
    "CODE_INVALID_FIELD_TYPE",
    "CODE_INVALID_CLAIMED_STATUS",
    "NORMALIZE_CODES",
    "CODE_HANDOFF_BINDING_MISMATCH",
    "CODE_ACTOR_KIND_MISMATCH",
    "ActorOutputParseError",
    "ActorOutputNormalizeError",
    "ClaimedTestResult",
    "ActorOutput",
    "normalize_actor_output_to_review_packet",
]
