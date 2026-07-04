# SPDX-License-Identifier: Apache-2.0
"""Overnight playbook queue parser (Slice B-11.S4).

> A queue item is permission to *attempt* offline/synthetic work later. It is NOT
> permission to merge, push, bless, recurse, or expand authority.

This is an inert parser + static validator. It normalizes a queue of bounded,
operator-approved synthetic-conveyor items into typed data a future harness can
consume. It does NOT run the queue, schedule actors, create worktrees, inspect git,
apply patches, invoke Claude/Codex, or execute tests. It is a clipboard, not an
engine — "queue" must not quietly become "scheduler".

Fail-closed by construction:

- **mode** must be ``synthetic_conveyor`` (live/autopilot refused).
- **operator_approved** must be explicitly True on every item — missing or False is
  refused. This is the anti-recursion latch: a ReviewPacket follow-up does NOT
  enter the queue on its own; it needs its own explicit approval. Provenance never
  grants approval.
- **authority** must be fully closed (every axis False) for the synthetic conveyor.
- **output_kind** must be ``review_packet`` (merge/push/commit/doctrine/etc refused).
- **paths** are validated as relative + safe (no absolute, no ``.``, no ``..``) and
  NOT expanded — static hygiene only, no filesystem touch.
- **required_tests** / **stop_conditions** are inert text declarations, never run.

Static validation only — it does not check whether a sha/branch/path exists,
whether tests pass, or whether a ReviewPacket matches. Those are later slices.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

QUEUE_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = frozenset({1})

# Accepted mode — this parser is the SYNTHETIC conveyor. Live/autopilot refused.
MODE_SYNTHETIC_CONVEYOR = "synthetic_conveyor"
SUPPORTED_QUEUE_MODES = frozenset({MODE_SYNTHETIC_CONVEYOR})

# Accepted output kind — queued work produces a ReviewPacket, never a commit/merge.
OUTPUT_REVIEW_PACKET = "review_packet"
ACCEPTED_OUTPUT_KINDS = frozenset({OUTPUT_REVIEW_PACKET})

# Provenance kinds (descriptive only — provenance never grants approval).
SOURCE_OPERATOR_SEEDED = "operator_seeded"
SOURCE_REVIEWPACKET_FOLLOWUP = "reviewpacket_followup"
KNOWN_SOURCE_KINDS = frozenset({SOURCE_OPERATOR_SEEDED, SOURCE_REVIEWPACKET_FOLLOWUP})

# Authority axes a queue item accounts for. For the synthetic conveyor EVERY axis
# must be False (fail-closed) — the future harness emits ReviewPackets, not commits.
QUEUE_AUTHORITY_KEYS = (
    "commit",
    "push",
    "network",
    "subprocess",
    "live_origin",
    "real_cage_backend",
    "doctrine_write",
    "constellation_write",
)

# Closed validation-failure vocabulary.
CODE_UNSUPPORTED_SCHEMA = "unsupported_schema"
CODE_UNSUPPORTED_MODE = "unsupported_mode"
CODE_NOT_OPERATOR_APPROVED = "not_operator_approved"
CODE_AUTHORITY_NOT_CLOSED = "authority_not_closed"
CODE_UNSUPPORTED_OUTPUT_KIND = "unsupported_output_kind"
CODE_DUPLICATE_PLAYBOOK_ID = "duplicate_playbook_id"
CODE_EMPTY_ALLOWED_PATHS = "empty_allowed_paths"
CODE_UNSAFE_PATH = "unsafe_path"
CODE_EMPTY_TEST_COMMAND = "empty_test_command"
CODE_EMPTY_STOP_CONDITIONS = "empty_stop_conditions"
CODE_UNKNOWN_SOURCE_KIND = "unknown_source_kind"
CODE_MISSING_REQUIRED_FIELD = "missing_required_field"
QUEUE_VALIDATION_CODES = frozenset(
    {
        CODE_UNSUPPORTED_SCHEMA,
        CODE_UNSUPPORTED_MODE,
        CODE_NOT_OPERATOR_APPROVED,
        CODE_AUTHORITY_NOT_CLOSED,
        CODE_UNSUPPORTED_OUTPUT_KIND,
        CODE_DUPLICATE_PLAYBOOK_ID,
        CODE_EMPTY_ALLOWED_PATHS,
        CODE_UNSAFE_PATH,
        CODE_EMPTY_TEST_COMMAND,
        CODE_EMPTY_STOP_CONDITIONS,
        CODE_UNKNOWN_SOURCE_KIND,
        CODE_MISSING_REQUIRED_FIELD,
    }
)


class QueueValidationError(ValueError):
    """A typed, fail-closed queue rejection. ``code`` is from the closed
    ``QUEUE_VALIDATION_CODES`` vocabulary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


def _require(data: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in data:
        raise QueueValidationError(
            CODE_MISSING_REQUIRED_FIELD, f"{ctx}: missing required field {key!r}"
        )
    return data[key]


def _validate_path_entry(entry: Any, field_name: str, item_id: str) -> None:
    if not isinstance(entry, str) or entry == "":
        raise QueueValidationError(
            CODE_UNSAFE_PATH, f"item {item_id!r} {field_name}: empty path entry"
        )
    if entry.startswith("/"):
        raise QueueValidationError(
            CODE_UNSAFE_PATH, f"item {item_id!r} {field_name}: absolute path {entry!r}"
        )
    if entry == ".":
        raise QueueValidationError(
            CODE_UNSAFE_PATH,
            f"item {item_id!r} {field_name}: '.' is a whole-repo grant, refused",
        )
    if ".." in entry.split("/"):
        raise QueueValidationError(
            CODE_UNSAFE_PATH, f"item {item_id!r} {field_name}: path traversal {entry!r}"
        )


# --------------------------------------------------------------------------- #
# Models.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class QueuedPlaybookAuthority:
    """The maximum authority available to future execution of a queue item. For the
    synthetic conveyor every axis must be False; the item validator enforces it."""

    commit: bool = False
    push: bool = False
    network: bool = False
    subprocess: bool = False
    live_origin: bool = False
    real_cage_backend: bool = False
    doctrine_write: bool = False
    constellation_write: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {k: bool(getattr(self, k)) for k in QUEUE_AUTHORITY_KEYS}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueuedPlaybookAuthority":
        return cls(**{k: bool(data.get(k, False)) for k in QUEUE_AUTHORITY_KEYS})


@dataclass(frozen=True)
class QueueItemSource:
    """Provenance of a queue item. Descriptive ONLY — it never grants approval. A
    ``reviewpacket_followup`` item still needs its own explicit operator_approved."""

    kind: str
    packet_id: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in KNOWN_SOURCE_KINDS:
            raise QueueValidationError(
                CODE_UNKNOWN_SOURCE_KIND,
                f"source kind {self.kind!r} not in {sorted(KNOWN_SOURCE_KINDS)}",
            )

    def as_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "packet_id": self.packet_id}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueueItemSource":
        return cls(kind=data.get("kind", ""), packet_id=data.get("packet_id"))


@dataclass(frozen=True)
class QueuedPlaybook:
    """One bounded, operator-approved synthetic-conveyor work item. Validated at
    construction — fail-closed on approval, authority, output kind, and path
    hygiene."""

    playbook_id: str
    title: str
    objective: str
    output_kind: str
    allowed_paths: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    operator_approved: bool = False
    authority: QueuedPlaybookAuthority = field(
        default_factory=QueuedPlaybookAuthority
    )
    lane: Optional[str] = None
    base_branch: Optional[str] = None
    base_sha: Optional[str] = None
    forbidden_paths: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    source: Optional[QueueItemSource] = None

    def __post_init__(self) -> None:
        # Anti-recursion latch: explicit approval, no matter the provenance.
        if not self.operator_approved:
            raise QueueValidationError(
                CODE_NOT_OPERATOR_APPROVED,
                f"item {self.playbook_id!r} is not operator_approved "
                "(missing or false); provenance does not grant approval",
            )
        # Authority must be fully closed for the synthetic conveyor.
        for k in QUEUE_AUTHORITY_KEYS:
            if getattr(self.authority, k):
                raise QueueValidationError(
                    CODE_AUTHORITY_NOT_CLOSED,
                    f"item {self.playbook_id!r} requests {k}=true; synthetic-conveyor "
                    "authority must be fully closed (review packets, not commits)",
                )
        if self.output_kind not in ACCEPTED_OUTPUT_KINDS:
            raise QueueValidationError(
                CODE_UNSUPPORTED_OUTPUT_KIND,
                f"item {self.playbook_id!r} output_kind {self.output_kind!r}; "
                f"only {sorted(ACCEPTED_OUTPUT_KINDS)}",
            )
        if not self.allowed_paths:
            raise QueueValidationError(
                CODE_EMPTY_ALLOWED_PATHS,
                f"item {self.playbook_id!r} has empty allowed_paths "
                "(a bounded item must declare where it may work)",
            )
        for p in self.allowed_paths:
            _validate_path_entry(p, "allowed_paths", self.playbook_id)
        for p in self.forbidden_paths:
            _validate_path_entry(p, "forbidden_paths", self.playbook_id)
        for t in self.required_tests:
            if not isinstance(t, str) or t.strip() == "":
                raise QueueValidationError(
                    CODE_EMPTY_TEST_COMMAND,
                    f"item {self.playbook_id!r} has an empty required_tests entry",
                )
        if not self.stop_conditions:
            raise QueueValidationError(
                CODE_EMPTY_STOP_CONDITIONS,
                f"item {self.playbook_id!r} must declare non-empty stop_conditions",
            )
        for s in self.stop_conditions:
            if not isinstance(s, str) or s.strip() == "":
                raise QueueValidationError(
                    CODE_EMPTY_STOP_CONDITIONS,
                    f"item {self.playbook_id!r} has an empty stop_condition",
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "title": self.title,
            "objective": self.objective,
            "lane": self.lane,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
            "authority": self.authority.as_dict(),
            "allowed_paths": list(self.allowed_paths),
            "forbidden_paths": list(self.forbidden_paths),
            "required_tests": list(self.required_tests),
            "stop_conditions": list(self.stop_conditions),
            "output_kind": self.output_kind,
            "operator_approved": self.operator_approved,
            "source": self.source.as_dict() if self.source is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueuedPlaybook":
        ctx = f"item {data.get('playbook_id', '<unknown>')!r}"
        source_data = data.get("source")
        return cls(
            playbook_id=_require(data, "playbook_id", ctx),
            title=_require(data, "title", ctx),
            objective=_require(data, "objective", ctx),
            output_kind=_require(data, "output_kind", ctx),
            allowed_paths=tuple(_require(data, "allowed_paths", ctx)),
            stop_conditions=tuple(_require(data, "stop_conditions", ctx)),
            operator_approved=bool(data.get("operator_approved", False)),
            authority=QueuedPlaybookAuthority.from_dict(data.get("authority", {})),
            lane=data.get("lane"),
            base_branch=data.get("base_branch"),
            base_sha=data.get("base_sha"),
            forbidden_paths=tuple(data.get("forbidden_paths", ())),
            required_tests=tuple(data.get("required_tests", ())),
            source=(
                QueueItemSource.from_dict(source_data)
                if source_data is not None
                else None
            ),
        )


@dataclass(frozen=True)
class PlaybookQueue:
    """A queue of operator-approved synthetic-conveyor items. Validated at
    construction: supported schema + mode, and no duplicate playbook ids."""

    queue_id: str
    repo: str
    base_branch: str
    base_sha: str
    mode: str
    items: tuple[QueuedPlaybook, ...] = ()
    schema_version: int = QUEUE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise QueueValidationError(
                CODE_UNSUPPORTED_SCHEMA,
                f"schema_version {self.schema_version!r}; "
                f"supported {sorted(SUPPORTED_SCHEMA_VERSIONS)}",
            )
        if self.mode not in SUPPORTED_QUEUE_MODES:
            raise QueueValidationError(
                CODE_UNSUPPORTED_MODE,
                f"mode {self.mode!r}; this parser accepts only "
                f"{sorted(SUPPORTED_QUEUE_MODES)} (live/autopilot refused)",
            )
        ids = [it.playbook_id for it in self.items]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise QueueValidationError(
                CODE_DUPLICATE_PLAYBOOK_ID, f"duplicate playbook_id(s): {dupes}"
            )

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "queue_id": self.queue_id,
            "repo": self.repo,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
            "mode": self.mode,
            "items": [it.as_dict() for it in self.items],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_manifest_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_manifest_dict(cls, data: dict[str, Any]) -> "PlaybookQueue":
        return cls(
            queue_id=_require(data, "queue_id", "queue"),
            repo=_require(data, "repo", "queue"),
            base_branch=_require(data, "base_branch", "queue"),
            base_sha=_require(data, "base_sha", "queue"),
            mode=_require(data, "mode", "queue"),
            items=tuple(
                QueuedPlaybook.from_dict(it) for it in data.get("items", ())
            ),
            schema_version=int(data.get("schema_version", QUEUE_SCHEMA_VERSION)),
        )

    @classmethod
    def from_json(cls, text: str) -> "PlaybookQueue":
        return cls.from_manifest_dict(json.loads(text))


__all__ = [
    "QUEUE_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "MODE_SYNTHETIC_CONVEYOR",
    "SUPPORTED_QUEUE_MODES",
    "OUTPUT_REVIEW_PACKET",
    "ACCEPTED_OUTPUT_KINDS",
    "SOURCE_OPERATOR_SEEDED",
    "SOURCE_REVIEWPACKET_FOLLOWUP",
    "KNOWN_SOURCE_KINDS",
    "QUEUE_AUTHORITY_KEYS",
    "QUEUE_VALIDATION_CODES",
    "CODE_UNSUPPORTED_SCHEMA",
    "CODE_UNSUPPORTED_MODE",
    "CODE_NOT_OPERATOR_APPROVED",
    "CODE_AUTHORITY_NOT_CLOSED",
    "CODE_UNSUPPORTED_OUTPUT_KIND",
    "CODE_DUPLICATE_PLAYBOOK_ID",
    "CODE_EMPTY_ALLOWED_PATHS",
    "CODE_UNSAFE_PATH",
    "CODE_EMPTY_TEST_COMMAND",
    "CODE_EMPTY_STOP_CONDITIONS",
    "CODE_UNKNOWN_SOURCE_KIND",
    "CODE_MISSING_REQUIRED_FIELD",
    "QueueValidationError",
    "QueuedPlaybookAuthority",
    "QueueItemSource",
    "QueuedPlaybook",
    "PlaybookQueue",
]
