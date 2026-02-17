# SPDX-License-Identifier: Apache-2.0
"""
Slim Mode — Single-developer governance for high-iteration workflows.

Keeps the guardrails that prevent real drift (decisions, anchors, structure
locks, test gates) and drops the adversarial ceremony (proposals, receipts,
quorum, leases, epochs).

Spec: SLIM_MODE_SPEC.md (Layer 0, Item #2 of AG2 build order)

Design principle: The governor should be as easy to use on itself as it is
to build. Zero new data structures — CLI sugar over existing subsystems.

Integration points:
  - ledgers.py — DecisionLedger for `governor decide`
  - continuity.py — AnchorRegistry for `governor anchor`
  - spine.py — SpineManager for `governor lock/unlock`
  - invariant_store.py — InvariantStore for `governor must-pass/must-exist`
  - envelopes.py — SLIM envelope mode
  - check.py — existing check infrastructure
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .claims import Claim, ClaimType, decision as make_decision_claim
from .continuity import (
    Anchor,
    AnchorType,
    Severity as AnchorSeverity,
    AnchorRegistry,
)
from .invariant_store import InvariantSpec, InvariantStore, VALID_KINDS
from .ledgers import DecisionLedger, Decision
from .spine import Spine, SpineManager


# ---------------------------------------------------------------------------
# Slim Status View
# ---------------------------------------------------------------------------


@dataclass
class SlimStatus:
    """One-screen status view for slim mode."""

    envelope: str
    decisions: list[dict[str, Any]]
    anchors: list[dict[str, Any]]
    invariants: list[dict[str, Any]]
    spine_locked: list[str]
    last_check: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope": self.envelope,
            "decisions": self.decisions,
            "anchors": self.anchors,
            "invariants": self.invariants,
            "spine_locked": self.spine_locked,
            "last_check": self.last_check,
        }

    def to_oneliner(self) -> str:
        """Compact one-liner for system prompts (Codex integration)."""
        parts = []
        if self.decisions:
            topics = [d.get("choice", d.get("topic", "?")) for d in self.decisions]
            parts.append(f"DECISIONS: {', '.join(topics)} ({len(self.decisions)} active)")
        if self.anchors:
            descs = [a.get("description", "?")[:30] for a in self.anchors]
            reject_count = sum(1 for a in self.anchors if a.get("severity") == "reject")
            parts.append(f"ANCHORS: {', '.join(descs)} ({reject_count} reject-severity)")
        if self.invariants:
            kinds = [i.get("kind", "?") for i in self.invariants]
            parts.append(f"INVARIANTS: {', '.join(kinds)}")
        if self.spine_locked:
            parts.append(f"SPINE: {', '.join(self.spine_locked)} locked")
        return "\n".join(parts) if parts else "No constraints active."

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SlimStatus:
        return cls(
            envelope=d.get("envelope", "slim"),
            decisions=d.get("decisions", []),
            anchors=d.get("anchors", []),
            invariants=d.get("invariants", []),
            spine_locked=d.get("spine_locked", []),
            last_check=d.get("last_check", ""),
        )


# ---------------------------------------------------------------------------
# Contradiction Detection
# ---------------------------------------------------------------------------


class ContradictionError(Exception):
    """Raised when a new decision contradicts an existing one."""

    def __init__(self, new_text: str, existing: Decision, topic: str):
        self.new_text = new_text
        self.existing = existing
        self.topic = topic
        super().__init__(
            f"Contradicts existing decision on '{topic}': "
            f'"{existing.choice}" (recorded {existing.created_at.isoformat()[:10]})'
        )


# ---------------------------------------------------------------------------
# Facade: SlimMode
# ---------------------------------------------------------------------------


class SlimMode:
    """Top-level facade for slim-mode governance.

    Wraps existing subsystems with zero-ceremony APIs:
    - decide() — direct DecisionLedger write with contradiction check
    - anchor() — direct AnchorRegistry write
    - lock()/unlock() — SpineManager shortcuts
    - must_pass()/must_exist() — InvariantStore shortcuts
    - status() — one-screen view
    - check() — delegates to check.run_check

    All state is upgrade-safe: everything in slim mode is valid strict-mode state.
    """

    def __init__(self, gov_dir: Path) -> None:
        self.gov_dir = gov_dir
        self._decision_ledger = DecisionLedger(gov_dir)
        self._anchor_registry = self._load_anchor_registry()
        self._spine_manager = SpineManager(gov_dir.parent)
        self._invariant_store = InvariantStore(gov_dir.parent)

    def _load_anchor_registry(self) -> AnchorRegistry:
        path = self.gov_dir / "continuity" / "anchors.json"
        if path.exists():
            return AnchorRegistry.load(path)
        return AnchorRegistry()

    def _save_anchor_registry(self) -> None:
        path = self.gov_dir / "continuity" / "anchors.json"
        self._anchor_registry.save(path)

    # ----- Decisions -----

    def decide(
        self,
        text: str,
        topic: str | None = None,
        force: bool = False,
    ) -> Decision:
        """Record a decision. Checks for contradictions unless --force.

        Args:
            text: The decision text (becomes the 'choice' field).
            topic: Optional topic for grouping / contradiction detection.
            force: Skip contradiction check.

        Returns:
            The created Decision.

        Raises:
            ContradictionError: If an existing decision on the same topic exists.
        """
        effective_topic = topic or _infer_topic(text)

        if not force and effective_topic:
            existing = self._decision_ledger.query(topic=effective_topic)
            # Skip retracted decisions — they don't block new ones
            existing = [d for d in existing if not d.choice.startswith("[RETRACTED]")]
            if existing:
                raise ContradictionError(text, existing[0], effective_topic)

        claim = make_decision_claim(topic=effective_topic, choice=text)
        return self._decision_ledger.add(claim, rationale=f"slim: {text}")

    def retract(self, text: str, topic: str | None = None) -> Decision | None:
        """Retract a decision by superseding it.

        Finds the matching decision and supersedes it with a retraction.
        Returns the superseding decision, or None if nothing matched.
        """
        effective_topic = topic or _infer_topic(text)
        existing = self._find_decision(text, effective_topic)
        if not existing:
            return None

        claim = make_decision_claim(
            topic=effective_topic or existing.topic,
            choice=f"[RETRACTED] {existing.choice}",
        )
        return self._decision_ledger.add(
            claim,
            rationale=f"slim retract: {text}",
            supersedes=existing.id,
        )

    def _find_decision(self, text: str, topic: str | None) -> Decision | None:
        """Find a decision by topic or text match."""
        if topic:
            matches = self._decision_ledger.query(topic=topic)
            if matches:
                return matches[0]

        # Fall back to text matching
        for d in self._decision_ledger.query():
            if d.choice.lower() == text.lower() or text.lower() in d.choice.lower():
                return d
        return None

    def list_decisions(self) -> list[Decision]:
        """List active (non-superseded) decisions."""
        return self._decision_ledger.query()

    # ----- Anchors -----

    def add_anchor(
        self,
        description: str,
        anchor_type: str = "canon",
        severity: str = "reject",
        scope: str = "",
        anchor_id: str | None = None,
    ) -> Anchor:
        """Create and register a continuity anchor.

        Args:
            description: What this anchor constrains.
            anchor_type: One of AnchorType values.
            severity: One of 'warn', 'correct', 'reject'.
            scope: Glob pattern for file scope (empty = global).
            anchor_id: Optional ID (auto-generated if not provided).

        Returns:
            The created Anchor.
        """
        aid = anchor_id or _make_anchor_id(description)
        atype = AnchorType(anchor_type)
        sev = AnchorSeverity(severity)

        # Parse description into required/forbidden patterns
        required_patterns: list[str] = []
        forbidden_patterns: list[str] = []

        if atype == AnchorType.PROHIBITION:
            forbidden_patterns = _extract_patterns(description)
        elif atype == AnchorType.REQUIREMENT:
            required_patterns = _extract_patterns(description)
        elif atype == AnchorType.CANON:
            required_patterns = _extract_patterns(description)

        anchor = Anchor(
            id=aid,
            anchor_type=atype,
            description=description,
            required_patterns=required_patterns,
            forbidden_patterns=forbidden_patterns,
            severity=sev,
            source="slim",
        )
        self._anchor_registry.register(anchor)
        self._save_anchor_registry()
        return anchor

    def remove_anchor(self, anchor_id: str) -> Anchor | None:
        """Remove an anchor by ID."""
        anchor = self._anchor_registry.unregister(anchor_id)
        if anchor:
            self._save_anchor_registry()
        return anchor

    def list_anchors(self) -> list[Anchor]:
        """List all registered anchors."""
        return self._anchor_registry.all()

    # ----- Structure Locks (Spine) -----

    def lock(
        self,
        path: str,
        description: str = "",
        forbidden_patterns: list[str] | None = None,
    ) -> Spine:
        """Lock a directory via spine. Creates and activates a spine.

        Args:
            path: Directory path to lock (e.g., 'src/governor/').
            description: Optional description.
            forbidden_patterns: Glob patterns for files that must not be created.

        Returns:
            The created Spine.
        """
        spine_id = _make_spine_id(path)
        structure: dict[str, Any] = {
            "directories": {path: "required"},
        }
        if forbidden_patterns:
            structure["forbidden_paths"] = forbidden_patterns

        spine = Spine(
            id=spine_id,
            structure=structure,
            description=description or f"Locked: {path}",
            locked_by="slim",
        )
        self._spine_manager.lock(spine)
        self._spine_manager.set_active(spine_id)
        return spine

    def unlock(self, path: str) -> bool:
        """Unlock a directory by removing its spine."""
        spine_id = _make_spine_id(path)
        return self._spine_manager.unlock(spine_id)

    def list_locks(self) -> list[Spine]:
        """List all active spines."""
        return self._spine_manager.list_spines()

    # ----- Invariants (must-pass, must-exist) -----

    def must_pass(self, command: str, spec_id: str | None = None) -> InvariantSpec:
        """Register a test command that must pass.

        Args:
            command: Shell command (e.g., 'python3 -m pytest tests/ -x').
            spec_id: Optional ID (auto-generated from command).

        Returns:
            The created InvariantSpec.
        """
        sid = spec_id or _make_invariant_id("test", command)
        spec = InvariantSpec(
            id=sid,
            kind="test",
            params={"command": command},
            on_violation="block",
        )
        self._invariant_store.add(spec)
        return spec

    def must_exist(self, path: str, spec_id: str | None = None) -> InvariantSpec:
        """Register a file that must exist.

        Args:
            path: File path (e.g., 'src/governor/__init__.py').
            spec_id: Optional ID (auto-generated from path).

        Returns:
            The created InvariantSpec.
        """
        sid = spec_id or _make_invariant_id("file-exists", path)
        spec = InvariantSpec(
            id=sid,
            kind="file-exists",
            params={"path": path},
            on_violation="block",
        )
        self._invariant_store.add(spec)
        return spec

    def remove_invariant(self, spec_id: str) -> bool:
        """Remove an invariant by ID."""
        return self._invariant_store.remove(spec_id)

    def list_invariants(self) -> list[InvariantSpec]:
        """List all invariant specs."""
        return self._invariant_store.list_all()

    # ----- Status -----

    def status(self) -> SlimStatus:
        """Get the one-screen slim status view."""
        decisions = []
        for d in self.list_decisions():
            decisions.append({
                "topic": d.topic,
                "choice": d.choice,
                "created_at": d.created_at.isoformat()[:10],
            })

        anchors = []
        for a in self.list_anchors():
            anchors.append({
                "id": a.id,
                "type": a.anchor_type.value,
                "severity": a.severity.value,
                "description": a.description,
            })

        invariants = []
        for i in self.list_invariants():
            invariants.append({
                "id": i.id,
                "kind": i.kind,
                "params": i.params,
            })

        spine_locked = []
        for s in self.list_locks():
            dirs = list(s.structure.get("directories", {}).keys())
            spine_locked.extend(dirs)

        # Last check timestamp
        last_check = ""
        check_path = self.gov_dir / "slim" / "last_check.txt"
        if check_path.exists():
            last_check = check_path.read_text().strip()

        return SlimStatus(
            envelope="slim",
            decisions=decisions,
            anchors=anchors,
            invariants=invariants,
            spine_locked=spine_locked,
            last_check=last_check,
        )

    def record_check(self) -> None:
        """Record that a check was performed."""
        check_dir = self.gov_dir / "slim"
        check_dir.mkdir(parents=True, exist_ok=True)
        (check_dir / "last_check.txt").write_text(
            datetime.now(timezone.utc).isoformat()
        )


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _infer_topic(text: str) -> str:
    """Try to infer a topic from decision text.

    Looks for patterns like "use X for Y", "X uses Y", "no X".
    Returns empty string if no topic found.
    """
    text_lower = text.lower().strip()

    # "Use React for frontend" → topic: frontend
    m = re.match(r"use\s+\w+\s+for\s+(\w[\w\s]*)", text_lower)
    if m:
        return m.group(1).strip().replace(" ", "_")

    # "Authentication uses JWT" → topic: authentication
    m = re.match(r"(\w[\w\s]*?)\s+(?:uses?|via|with|for)\s+", text_lower)
    if m:
        return m.group(1).strip().replace(" ", "_")

    # "No ORM" → topic: orm
    m = re.match(r"no\s+(\w[\w\s]*?)(?:\s*[-—]|$)", text_lower)
    if m:
        return m.group(1).strip().replace(" ", "_")

    return ""


def _make_anchor_id(description: str) -> str:
    """Generate a slug-style anchor ID from description."""
    slug = re.sub(r"[^a-z0-9]+", "-", description.lower().strip())
    slug = slug.strip("-")[:40]
    return slug or uuid.uuid4().hex[:8]


def _make_spine_id(path: str) -> str:
    """Generate a spine ID from a path."""
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower().strip("/"))
    return f"lock-{slug}" if slug else f"lock-{uuid.uuid4().hex[:8]}"


def _make_invariant_id(kind: str, value: str) -> str:
    """Generate an invariant ID from kind and value."""
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip())
    slug = slug.strip("-")[:30]
    return f"{kind}-{slug}" if slug else f"{kind}-{uuid.uuid4().hex[:8]}"


def _extract_patterns(description: str) -> list[str]:
    """Extract quoted strings or significant phrases from description.

    For simple descriptions like "Elena has green eyes", the whole
    description becomes the pattern. For "No eval() calls", extract "eval()".
    """
    # Try to find quoted strings first
    quoted = re.findall(r'"([^"]+)"|\'([^\']+)\'', description)
    if quoted:
        return [q[0] or q[1] for q in quoted]

    # For prohibitions, extract the key phrase
    m = re.match(r"[Nn]o\s+(.+?)(?:\s+calls?)?(?:\s+in\s+.*)?$", description)
    if m:
        return [m.group(1).strip()]

    # Return the whole description as a loose match
    return [description]


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------


def create_slim_mode(gov_dir: Path) -> SlimMode:
    """Create a SlimMode instance for the given governor directory."""
    return SlimMode(gov_dir)
