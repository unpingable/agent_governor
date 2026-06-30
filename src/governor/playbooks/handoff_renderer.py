# SPDX-License-Identifier: Apache-2.0
"""Handoff renderer — QueuedPlaybook → sealed actor handoff (Slice B-11.S6).

> A handoff is a *sealed, bounded instruction* to an offline actor. It carries scope
> and prohibitions forward and a tamper-evident seal. It is NOT permission to run, and
> nothing the actor produces by acting on it is admitted by having been requested.

This is the point where the synthetic conveyor's data model becomes a reusable
**handoff machine**: it turns one fail-closed, operator-approved ``QueuedPlaybook``
into a deterministic, content-sealed packet an operator can hand to an offline
Claude or Codex actor. The actor's only licensed output is a ``ReviewPacket``
(evidence) describing a *proposed* patch — never a commit, merge, push, or any live
effect.

What this module does NOT do (schemas love to grow little engines; this one does
not): it does not invoke an actor, spawn a subprocess, touch the network, read or
write the filesystem, inspect git, apply a patch, run a test, or admit anything. It
renders strings. ``to_file_map`` returns ``{filename: contents}`` — it does not write.

Three guarantees carried by type, not comment:

- **Authority is prohibited, not negotiable.** A handoff has NO authority-permitting
  surface at all. The only authority statement it can serialize is "every axis
  prohibited" (``PROHIBITED_AUTHORITY``). You cannot construct a handoff that permits
  commit/push/network/subprocess/live_origin/real_cage_backend/doctrine_write/
  constellation_write — it is unrepresentable, not merely guarded.
- **Sealed.** ``seal = "sha256:" + H(canonical_body)`` over everything except the
  seal itself. ``from_manifest_dict`` recomputes and refuses a manifest whose carried
  seal does not match its body (``HandoffSealError``) — tamper-evident handoff.
- **Inert + deterministic.** Frozen dataclass, validated at construction, stable key
  ordering, NO timestamps, NO ambient state. Same input → same bytes → same seal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from governor.gate_receipt import canonical_json, content_hash

from .playbook_queue import (
    MODE_SYNTHETIC_CONVEYOR,
    OUTPUT_REVIEW_PACKET,
    QUEUE_AUTHORITY_KEYS,
    PlaybookQueue,
    QueuedPlaybook,
)
from .review_packet import SCHEMA_VERSION as REVIEW_PACKET_SCHEMA_VERSION

HANDOFF_SCHEMA_VERSION = "handoff.v0"
SUPPORTED_HANDOFF_SCHEMA_VERSIONS = frozenset({HANDOFF_SCHEMA_VERSION})

# Closed set of actor targets. "Reusable handoff machine": the SAME sealed format
# targets either offline actor; the boundaries it carries are identical.
ACTOR_CLAUDE = "claude"
ACTOR_CODEX = "codex"
ACTOR_KINDS = frozenset({ACTOR_CLAUDE, ACTOR_CODEX})

# The only licensed actor output. The actor returns evidence, never a live effect.
EXPECTED_OUTPUT_KIND = OUTPUT_REVIEW_PACKET

# Every authority axis is prohibited for a synthetic-conveyor handoff. This is a
# derived constant, not a settable field — there is no surface on which a handoff
# could permit an axis. Sorted for stable serialization.
PROHIBITED_AUTHORITY: tuple[str, ...] = tuple(sorted(QUEUE_AUTHORITY_KEYS))

# Closed render-failure vocabulary.
CODE_UNKNOWN_ACTOR_KIND = "unknown_actor_kind"
CODE_UNSUPPORTED_SCHEMA = "unsupported_schema"
CODE_AUTHORITY_NOT_CLOSED = "authority_not_closed"
CODE_OUTPUT_KIND_NOT_REVIEW_PACKET = "output_kind_not_review_packet"
CODE_OPERATOR_APPROVAL_MISSING = "operator_approval_missing"
CODE_UNSUPPORTED_QUEUE_MODE = "unsupported_queue_mode"
HANDOFF_RENDER_CODES = frozenset(
    {
        CODE_UNKNOWN_ACTOR_KIND,
        CODE_UNSUPPORTED_SCHEMA,
        CODE_AUTHORITY_NOT_CLOSED,
        CODE_OUTPUT_KIND_NOT_REVIEW_PACKET,
        CODE_OPERATOR_APPROVAL_MISSING,
        CODE_UNSUPPORTED_QUEUE_MODE,
    }
)


class HandoffRenderError(ValueError):
    """A typed, fail-closed handoff-render rejection. ``code`` is from the closed
    ``HANDOFF_RENDER_CODES`` vocabulary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


class HandoffSealError(ValueError):
    """A carried seal does not match the recomputed seal — the handoff body was
    altered after sealing (tamper-evident refusal)."""


# --------------------------------------------------------------------------- #
# The sealed handoff.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class HandoffPacket:
    """A sealed, bounded instruction for one offline actor. Inert evidence-shaped
    data: it carries scope + prohibitions + a content seal. It cannot permit any
    authority axis (none is representable) and it cannot run anything.

    Validated at construction so a handoff built via ``from_manifest_dict`` is held
    to the same invariants as one built by ``render_handoff``."""

    handoff_id: str
    playbook_id: str
    actor_kind: str
    repo: str
    base_branch: str
    base_sha: str
    objective: str
    title: str
    allowed_paths: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    forbidden_paths: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    lane: Optional[str] = None
    schema_version: str = HANDOFF_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_HANDOFF_SCHEMA_VERSIONS:
            raise HandoffRenderError(
                CODE_UNSUPPORTED_SCHEMA,
                f"schema_version {self.schema_version!r}; supported "
                f"{sorted(SUPPORTED_HANDOFF_SCHEMA_VERSIONS)}",
            )
        if self.actor_kind not in ACTOR_KINDS:
            raise HandoffRenderError(
                CODE_UNKNOWN_ACTOR_KIND,
                f"actor_kind {self.actor_kind!r} not in {sorted(ACTOR_KINDS)}",
            )

    # -- the sealed body (deterministic; no seal, no timestamps, no IO) ------ #

    def _body(self) -> dict[str, Any]:
        """The canonical, sealable body — every field EXCEPT the seal. Authority is
        emitted as the derived all-prohibited constant + the licensed output kind;
        there is no authority-permitting key to set."""
        return {
            "schema_version": self.schema_version,
            "handoff_id": self.handoff_id,
            "playbook_id": self.playbook_id,
            "actor_kind": self.actor_kind,
            "repo": self.repo,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
            "lane": self.lane,
            "title": self.title,
            "objective": self.objective,
            "allowed_paths": list(self.allowed_paths),
            "forbidden_paths": list(self.forbidden_paths),
            "required_tests": list(self.required_tests),
            "stop_conditions": list(self.stop_conditions),
            "prohibited_authority": list(PROHIBITED_AUTHORITY),
            "expected_output_kind": EXPECTED_OUTPUT_KIND,
            "expected_output_schema": REVIEW_PACKET_SCHEMA_VERSION,
        }

    def compute_seal(self) -> str:
        """The content seal: ``sha256:`` + SHA-256 of the canonical body bytes.
        Deterministic and dependent only on the body."""
        return "sha256:" + content_hash(canonical_json(self._body()))

    # -- serialization (deterministic) -------------------------------------- #

    def to_manifest_dict(self) -> dict[str, Any]:
        return {**self._body(), "seal": self.compute_seal()}

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_manifest_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_manifest_dict(cls, data: dict[str, Any]) -> "HandoffPacket":
        packet = cls(
            handoff_id=data["handoff_id"],
            playbook_id=data["playbook_id"],
            actor_kind=data["actor_kind"],
            repo=data["repo"],
            base_branch=data["base_branch"],
            base_sha=data["base_sha"],
            objective=data["objective"],
            title=data["title"],
            allowed_paths=tuple(data.get("allowed_paths", ())),
            stop_conditions=tuple(data.get("stop_conditions", ())),
            forbidden_paths=tuple(data.get("forbidden_paths", ())),
            required_tests=tuple(data.get("required_tests", ())),
            lane=data.get("lane"),
            schema_version=data.get("schema_version", HANDOFF_SCHEMA_VERSION),
        )
        carried = data.get("seal")
        if carried is not None and carried != packet.compute_seal():
            raise HandoffSealError(
                "carried seal does not match recomputed seal "
                "(handoff body was altered after sealing)"
            )
        return packet

    @classmethod
    def from_json(cls, text: str) -> "HandoffPacket":
        import json

        return cls.from_manifest_dict(json.loads(text))

    def verify_seal(self, expected: str) -> bool:
        """True iff ``expected`` equals this handoff's recomputed seal."""
        return expected == self.compute_seal()

    # -- actor-facing prompt (human/actor instruction, NOT machine authority) #

    def to_prompt_markdown(self) -> str:
        def _bullets(items: tuple[str, ...]) -> str:
            return "\n".join(f"- {i}" for i in items) if items else "- (none)"

        addressee = {
            ACTOR_CLAUDE: "Claude Code (offline actor)",
            ACTOR_CODEX: "Codex (offline actor)",
        }[self.actor_kind]
        prohibitions = "\n".join(f"- MUST NOT {a}" for a in PROHIBITED_AUTHORITY)
        return "\n".join(
            [
                f"# Synthetic-conveyor handoff — {self.handoff_id}",
                "",
                f"**Addressee:** {addressee}",
                f"**Seal:** `{self.compute_seal()}`",
                f"**Playbook:** {self.playbook_id}"
                + (f"  ·  lane={self.lane}" if self.lane else ""),
                f"**Repo:** {self.repo}  ·  base {self.base_branch} @ {self.base_sha}",
                "",
                "## Objective",
                self.objective,
                "",
                "## Scope — you may modify ONLY these paths",
                _bullets(self.allowed_paths),
                "",
                "## Never touch these paths",
                _bullets(self.forbidden_paths),
                "",
                "## Hard prohibitions (the handoff grants NO authority)",
                prohibitions,
                "",
                "## Required tests (run in your own sandbox; report results)",
                _bullets(self.required_tests),
                "",
                "## Stop conditions",
                _bullets(self.stop_conditions),
                "",
                "## Your only licensed output",
                f"- Produce a **{EXPECTED_OUTPUT_KIND}** "
                f"(`{REVIEW_PACKET_SCHEMA_VERSION}`) describing a *proposed* patch.",
                "- Include: files changed, the diff as a referenced artifact, the test "
                "results you observed, risks, explicit non-actions, and any follow-ups "
                "(as suggestions only).",
                "- Do NOT apply, commit, merge, push, or claim anything is accepted, "
                "safe, or live. Your output is **evidence, not authority** — the "
                "operator reviews it later. Nothing is admitted by your having produced "
                "it.",
                "",
            ]
        )

    # -- optional bundle: relative safe filenames → string contents ---------- #

    def to_file_map(self) -> dict[str, str]:
        """A pure mapping of relative, safe filenames to string contents. Returns
        strings only — it does NOT write files. Filenames are hardcoded and relative
        (no caller-supplied paths, so no traversal surface)."""
        return {
            "handoff.json": self.to_json(),
            "PROMPT.md": self.to_prompt_markdown(),
        }


# --------------------------------------------------------------------------- #
# Renderers.
# --------------------------------------------------------------------------- #


def _assert_item_admissible(item: QueuedPlaybook) -> None:
    """Re-assert the QueuedPlaybook's fail-closed invariants at the handoff seam —
    the most dangerous boundary (the instruction leaving for an actor). The item
    already enforces these at construction; this is defense in depth against an item
    built through a future looser path."""
    if not item.operator_approved:
        raise HandoffRenderError(
            CODE_OPERATOR_APPROVAL_MISSING,
            f"item {item.playbook_id!r} is not operator_approved; "
            "provenance does not grant approval",
        )
    for k in QUEUE_AUTHORITY_KEYS:
        if getattr(item.authority, k):
            raise HandoffRenderError(
                CODE_AUTHORITY_NOT_CLOSED,
                f"item {item.playbook_id!r} requests {k}=true; a synthetic-conveyor "
                "handoff grants no authority",
            )
    if item.output_kind != OUTPUT_REVIEW_PACKET:
        raise HandoffRenderError(
            CODE_OUTPUT_KIND_NOT_REVIEW_PACKET,
            f"item {item.playbook_id!r} output_kind {item.output_kind!r}; "
            f"a handoff's only licensed output is {OUTPUT_REVIEW_PACKET!r}",
        )


def render_handoff(
    item: QueuedPlaybook,
    *,
    handoff_id: str,
    repo: str,
    base_branch: str,
    base_sha: str,
    actor_kind: str,
    lane: Optional[str] = None,
) -> HandoffPacket:
    """Render one fail-closed ``QueuedPlaybook`` into a sealed ``HandoffPacket`` for
    an offline actor. Pure — no IO, no actor invocation. The item's own base/lane
    override the supplied queue-level context when present.

    Raises ``HandoffRenderError`` (closed code) for an unknown actor, a
    non-review-packet output kind, unclosed authority, or a missing approval."""
    if actor_kind not in ACTOR_KINDS:
        raise HandoffRenderError(
            CODE_UNKNOWN_ACTOR_KIND,
            f"actor_kind {actor_kind!r} not in {sorted(ACTOR_KINDS)}",
        )
    _assert_item_admissible(item)
    return HandoffPacket(
        handoff_id=handoff_id,
        playbook_id=item.playbook_id,
        actor_kind=actor_kind,
        repo=repo,
        base_branch=item.base_branch or base_branch,
        base_sha=item.base_sha or base_sha,
        objective=item.objective,
        title=item.title,
        allowed_paths=item.allowed_paths,
        stop_conditions=item.stop_conditions,
        forbidden_paths=item.forbidden_paths,
        required_tests=item.required_tests,
        lane=lane or item.lane,
    )


def render_queue_handoffs(
    queue: PlaybookQueue,
    *,
    actor_kind: str,
    handoff_id_prefix: str = "handoff",
) -> tuple[HandoffPacket, ...]:
    """Render every item of a synthetic-conveyor queue into sealed handoffs, pulling
    repo/base context from the queue. ``handoff_id`` is derived deterministically as
    ``{prefix}-{queue_id}-{playbook_id}``. Pure — no IO.

    Refuses a non-synthetic-conveyor queue (``CODE_UNSUPPORTED_QUEUE_MODE``) even
    though ``PlaybookQueue`` already enforces it — the handoff seam re-checks."""
    if queue.mode != MODE_SYNTHETIC_CONVEYOR:
        raise HandoffRenderError(
            CODE_UNSUPPORTED_QUEUE_MODE,
            f"queue mode {queue.mode!r}; handoffs are only rendered for "
            f"{MODE_SYNTHETIC_CONVEYOR!r}",
        )
    return tuple(
        render_handoff(
            item,
            handoff_id=f"{handoff_id_prefix}-{queue.queue_id}-{item.playbook_id}",
            repo=queue.repo,
            base_branch=queue.base_branch,
            base_sha=queue.base_sha,
            actor_kind=actor_kind,
        )
        for item in queue.items
    )


__all__ = [
    "HANDOFF_SCHEMA_VERSION",
    "SUPPORTED_HANDOFF_SCHEMA_VERSIONS",
    "ACTOR_CLAUDE",
    "ACTOR_CODEX",
    "ACTOR_KINDS",
    "EXPECTED_OUTPUT_KIND",
    "PROHIBITED_AUTHORITY",
    "CODE_UNKNOWN_ACTOR_KIND",
    "CODE_UNSUPPORTED_SCHEMA",
    "CODE_AUTHORITY_NOT_CLOSED",
    "CODE_OUTPUT_KIND_NOT_REVIEW_PACKET",
    "CODE_OPERATOR_APPROVAL_MISSING",
    "CODE_UNSUPPORTED_QUEUE_MODE",
    "HANDOFF_RENDER_CODES",
    "HandoffRenderError",
    "HandoffSealError",
    "HandoffPacket",
    "render_handoff",
    "render_queue_handoffs",
]
