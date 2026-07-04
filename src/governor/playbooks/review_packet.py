# SPDX-License-Identifier: Apache-2.0
"""ReviewPacket — the unit of operator-delayed review (Slice B-11.S3).

> A ReviewPacket is **evidence, not authority**.

This is the central artifact a future overnight harness emits: it *describes*
bounded playbook work — what was requested, granted, used, changed, tested, and
what risks/non-actions/follow-ups remain — so an operator can review it later. It
is pure, inert data + serialization. It knows how to be *read*; it does NOT know
how to run a command, inspect git, apply a patch, invoke an actor, merge, push, or
bless anything. (Schemas love to grow little engines; this one does not.)

Two structural guarantees carried by type, not comment:

- ``used <= granted`` — a packet cannot claim it *used* an authority it was not
  *granted* (``ReviewAuthority.__post_init__`` raises). ``requested`` may exceed
  ``granted``; ``granted`` may exceed ``used``; ``used`` may never exceed ``granted``.
- ``operator_review_required`` defaults **True**. A packet never defaults to
  accepted / merged / blessed / pushed / live-safe / doctrine-valid.

Serialization is deterministic: stable key ordering, list order preserved as
given, NO generated timestamps, NO ambient git or filesystem inspection.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = "review_packet.v0"

# Packet result status (closed vocabulary).
STATUS_PROPOSED_PATCH = "proposed_patch"
STATUS_NO_CHANGE = "no_change"
STATUS_BLOCKED = "blocked"
STATUS_FAILED_TESTS = "failed_tests"
STATUS_STOPPED = "stopped"
STATUS_REJECTED_BY_ACTOR = "rejected_by_actor"
STATUS_NEEDS_OPERATOR = "needs_operator"
REVIEW_PACKET_STATUSES = frozenset(
    {
        STATUS_PROPOSED_PATCH,
        STATUS_NO_CHANGE,
        STATUS_BLOCKED,
        STATUS_FAILED_TESTS,
        STATUS_STOPPED,
        STATUS_REJECTED_BY_ACTOR,
        STATUS_NEEDS_OPERATOR,
    }
)

# Test result status (closed vocabulary).
TEST_PASSED = "passed"
TEST_FAILED = "failed"
TEST_NOT_RUN = "not_run"
TEST_SKIPPED = "skipped"
REVIEW_TEST_STATUSES = frozenset({TEST_PASSED, TEST_FAILED, TEST_NOT_RUN, TEST_SKIPPED})

# The authority axes a packet accounts for. Closed and ordered for stable
# serialization.
AUTHORITY_KEYS = (
    "commit",
    "push",
    "network",
    "subprocess",
    "live_origin",
    "doctrine_write",
    "constellation_write",
)


# --------------------------------------------------------------------------- #
# Authority — requested / granted / used, with used <= granted by construction.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class AuthoritySet:
    """A set of boolean authority flags. Everything defaults False (fail-closed)."""

    commit: bool = False
    push: bool = False
    network: bool = False
    subprocess: bool = False
    live_origin: bool = False
    doctrine_write: bool = False
    constellation_write: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {k: bool(getattr(self, k)) for k in AUTHORITY_KEYS}

    def covers(self, other: "AuthoritySet") -> bool:
        """True iff every flag set in ``other`` is also set in ``self`` — i.e.
        ``self`` is a superset of ``other``'s permissions."""
        return all(
            (not getattr(other, k)) or getattr(self, k) for k in AUTHORITY_KEYS
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuthoritySet":
        return cls(**{k: bool(data.get(k, False)) for k in AUTHORITY_KEYS})


@dataclass(frozen=True)
class ReviewAuthority:
    """The three authority views of a packet. The invariant ``used <= granted`` is
    enforced here — a packet cannot silently claim it used ungranted authority.
    ``requested`` is unconstrained relative to ``granted`` (you may ask for more
    than you get)."""

    requested: AuthoritySet = field(default_factory=AuthoritySet)
    granted: AuthoritySet = field(default_factory=AuthoritySet)
    used: AuthoritySet = field(default_factory=AuthoritySet)

    def __post_init__(self) -> None:
        if not self.granted.covers(self.used):
            overreach = [
                k
                for k in AUTHORITY_KEYS
                if getattr(self.used, k) and not getattr(self.granted, k)
            ]
            raise ValueError(
                f"authority used exceeds granted: {overreach} "
                "(a ReviewPacket cannot claim ungranted authority)"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested.as_dict(),
            "granted": self.granted.as_dict(),
            "used": self.used.as_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewAuthority":
        return cls(
            requested=AuthoritySet.from_dict(data.get("requested", {})),
            granted=AuthoritySet.from_dict(data.get("granted", {})),
            used=AuthoritySet.from_dict(data.get("used", {})),
        )


# --------------------------------------------------------------------------- #
# Sub-records: tests, artifacts (references only), follow-ups (suggestions only).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReviewTestResult:
    """A test command and its observed status. Descriptive — the packet does not
    run anything; this records what a harness already ran."""

    command: str
    status: str
    exit_code: Optional[int] = None
    summary: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in REVIEW_TEST_STATUSES:
            raise ValueError(
                f"test status {self.status!r} not in {sorted(REVIEW_TEST_STATUSES)}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "status": self.status,
            "exit_code": self.exit_code,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewTestResult":
        return cls(
            command=data["command"],
            status=data["status"],
            exit_code=data.get("exit_code"),
            summary=data.get("summary"),
        )


@dataclass(frozen=True)
class ReviewArtifact:
    """A descriptive REFERENCE to an artifact. The packet never reads, validates,
    executes, or applies the referenced content."""

    kind: str
    path: str
    sha256: Optional[str] = None
    description: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "sha256": self.sha256,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewArtifact":
        return cls(
            kind=data["kind"],
            path=data["path"],
            sha256=data.get("sha256"),
            description=data.get("description"),
        )


@dataclass(frozen=True)
class ReviewFollowup:
    """A SUGGESTED next playbook. Non-executing by construction — it is a note for
    the operator, never an approval or a queued action."""

    id: str
    title: str
    reason: str
    suggested_next_gate: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "reason": self.reason,
            "suggested_next_gate": self.suggested_next_gate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewFollowup":
        return cls(
            id=data["id"],
            title=data["title"],
            reason=data["reason"],
            suggested_next_gate=data.get("suggested_next_gate"),
        )


# --------------------------------------------------------------------------- #
# The packet.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ReviewPacket:
    """An inert, reviewable description of bounded playbook work. Evidence, not
    authority — it cannot run, apply, merge, push, or bless. Defaults to requiring
    operator review."""

    packet_id: str
    playbook_id: str
    repo: str
    branch: str
    base_branch: str
    base_sha: str
    status: str
    authority: ReviewAuthority = field(default_factory=ReviewAuthority)
    schema_version: str = SCHEMA_VERSION
    proposed_head_sha: Optional[str] = None
    lane: Optional[str] = None
    allowed_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()
    files_changed: tuple[str, ...] = ()
    tests: tuple[ReviewTestResult, ...] = ()
    artifacts: tuple[ReviewArtifact, ...] = ()
    risks: tuple[str, ...] = ()
    design_notes: tuple[str, ...] = ()
    explicit_non_actions: tuple[str, ...] = ()
    followups: tuple[ReviewFollowup, ...] = ()
    operator_review_required: bool = True

    def __post_init__(self) -> None:
        if self.status not in REVIEW_PACKET_STATUSES:
            raise ValueError(
                f"status {self.status!r} not in {sorted(REVIEW_PACKET_STATUSES)}"
            )

    # -- serialization (deterministic; no timestamps, no IO) ----------------- #

    def to_manifest_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "playbook_id": self.playbook_id,
            "repo": self.repo,
            "branch": self.branch,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
            "proposed_head_sha": self.proposed_head_sha,
            "status": self.status,
            "lane": self.lane,
            "authority": self.authority.as_dict(),
            "allowed_paths": list(self.allowed_paths),
            "forbidden_paths": list(self.forbidden_paths),
            "files_changed": list(self.files_changed),
            "tests": [t.as_dict() for t in self.tests],
            "artifacts": [a.as_dict() for a in self.artifacts],
            "risks": list(self.risks),
            "design_notes": list(self.design_notes),
            "explicit_non_actions": list(self.explicit_non_actions),
            "followups": [f.as_dict() for f in self.followups],
            "operator_review_required": self.operator_review_required,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_manifest_dict(), sort_keys=True, indent=2)

    @classmethod
    def from_manifest_dict(cls, data: dict[str, Any]) -> "ReviewPacket":
        return cls(
            packet_id=data["packet_id"],
            playbook_id=data["playbook_id"],
            repo=data["repo"],
            branch=data["branch"],
            base_branch=data["base_branch"],
            base_sha=data["base_sha"],
            status=data["status"],
            authority=ReviewAuthority.from_dict(data.get("authority", {})),
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            proposed_head_sha=data.get("proposed_head_sha"),
            lane=data.get("lane"),
            allowed_paths=tuple(data.get("allowed_paths", ())),
            forbidden_paths=tuple(data.get("forbidden_paths", ())),
            files_changed=tuple(data.get("files_changed", ())),
            tests=tuple(ReviewTestResult.from_dict(t) for t in data.get("tests", ())),
            artifacts=tuple(
                ReviewArtifact.from_dict(a) for a in data.get("artifacts", ())
            ),
            risks=tuple(data.get("risks", ())),
            design_notes=tuple(data.get("design_notes", ())),
            explicit_non_actions=tuple(data.get("explicit_non_actions", ())),
            followups=tuple(
                ReviewFollowup.from_dict(f) for f in data.get("followups", ())
            ),
            operator_review_required=bool(data.get("operator_review_required", True)),
        )

    @classmethod
    def from_json(cls, text: str) -> "ReviewPacket":
        return cls.from_manifest_dict(json.loads(text))

    # -- human-readable summary (for morning review, NOT machine authority) -- #

    def to_markdown_summary(self) -> str:
        def _bullets(items: tuple[str, ...]) -> str:
            return "\n".join(f"- {i}" for i in items) if items else "- (none)"

        def _auth_line(name: str, s: AuthoritySet) -> str:
            on = [k for k in AUTHORITY_KEYS if getattr(s, k)]
            return f"  - {name}: {', '.join(on) if on else '(none)'}"

        tests = (
            "\n".join(
                f"- `{t.command}` → **{t.status}**"
                + (f" (exit {t.exit_code})" if t.exit_code is not None else "")
                for t in self.tests
            )
            if self.tests
            else "- (none)"
        )
        followups = (
            "\n".join(
                f"- {f.id}: {f.title} — {f.reason}"
                + (f" → {f.suggested_next_gate}" if f.suggested_next_gate else "")
                for f in self.followups
            )
            if self.followups
            else "- (none)"
        )
        review_line = (
            "**operator review REQUIRED**"
            if self.operator_review_required
            else "operator review not flagged"
        )
        return "\n".join(
            [
                f"# ReviewPacket {self.packet_id}",
                "",
                f"- playbook: {self.playbook_id}",
                f"- repo: {self.repo}",
                f"- branch: {self.branch}  (base {self.base_branch} @ {self.base_sha})",
                f"- status: **{self.status}**"
                + (f"  lane={self.lane}" if self.lane else ""),
                "",
                "## Files changed",
                _bullets(self.files_changed),
                "",
                "## Tests",
                tests,
                "",
                "## Authority",
                _auth_line("requested", self.authority.requested),
                _auth_line("granted", self.authority.granted),
                _auth_line("used", self.authority.used),
                "",
                "## Explicit non-actions",
                _bullets(self.explicit_non_actions),
                "",
                "## Risks",
                _bullets(self.risks),
                "",
                "## Follow-ups (suggestions only)",
                followups,
                "",
                "## Review",
                f"- {review_line}",
                "",
            ]
        )

    # -- optional bundle: relative safe filenames → string contents ---------- #

    def to_file_map(self) -> dict[str, str]:
        """A pure mapping of relative, safe filenames to string contents. Returns
        strings only — it does NOT write files. Filenames are hardcoded and
        relative (no caller-supplied paths, so no traversal surface)."""
        return {
            "manifest.json": self.to_json(),
            "summary.md": self.to_markdown_summary(),
            "risks.md": (
                "\n".join(f"- {r}" for r in self.risks) if self.risks else "- (none)"
            )
            + "\n",
            "followups.json": json.dumps(
                [f.as_dict() for f in self.followups], sort_keys=True, indent=2
            ),
        }


__all__ = [
    "SCHEMA_VERSION",
    "STATUS_PROPOSED_PATCH",
    "STATUS_NO_CHANGE",
    "STATUS_BLOCKED",
    "STATUS_FAILED_TESTS",
    "STATUS_STOPPED",
    "STATUS_REJECTED_BY_ACTOR",
    "STATUS_NEEDS_OPERATOR",
    "REVIEW_PACKET_STATUSES",
    "TEST_PASSED",
    "TEST_FAILED",
    "TEST_NOT_RUN",
    "TEST_SKIPPED",
    "REVIEW_TEST_STATUSES",
    "AUTHORITY_KEYS",
    "AuthoritySet",
    "ReviewAuthority",
    "ReviewTestResult",
    "ReviewArtifact",
    "ReviewFollowup",
    "ReviewPacket",
]
