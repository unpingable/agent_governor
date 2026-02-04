"""
Violation Resolver: Interactive violation resolution for author-friendly chat.

When a governor violation fires, don't just show a footer — present 3 explicit,
bounded choices and block continuation until the user picks one.

The Three Moves:
- FIX: Rewrite last output to comply with current anchor
- REVISE: Update the anchor (with receipt)
- PROCEED: Log as intentional deviation (exception)

State Machine:
    NORMAL → [violation detected] → PENDING_RESOLUTION
    PENDING_RESOLUTION → [maude fix] → FIX_IN_PROGRESS → NORMAL
    PENDING_RESOLUTION → [maude revise] → REVISE_IN_PROGRESS → NORMAL
    PENDING_RESOLUTION → [maude proceed] → EXCEPTION_LOGGED → NORMAL
    PENDING_RESOLUTION → [other input] → RE-PRESENT_CHOICES → PENDING_RESOLUTION
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from .continuity import Anchor, AnchorRegistry, AnchorType, Violation


# =============================================================================
# Enums
# =============================================================================


class ResolutionAction(str, Enum):
    """Actions available to resolve a pending violation."""

    FIX = "fix"         # Rewrite response to comply
    REVISE = "revise"   # Update the anchor
    PROCEED = "proceed" # Log as exception


class ResolutionStatus(str, Enum):
    """Status of a pending violation."""

    PENDING = "pending"
    FIXED = "fixed"
    REVISED = "revised"
    PROCEEDED = "proceeded"
    EXPIRED = "expired"


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class PendingViolation:
    """Violation awaiting user resolution."""

    id: str                            # Hash of violation details
    context_id: str                    # Which governor context
    run_id: str                        # Which generation produced this
    violations: list[dict[str, Any]]   # Serialized Violation objects
    blocked_response: str              # The response that was blocked
    timestamp: str                     # ISO format
    mode: str                          # fiction/code/nonfiction
    status: ResolutionStatus = ResolutionStatus.PENDING

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "context_id": self.context_id,
            "run_id": self.run_id,
            "violations": self.violations,
            "blocked_response": self.blocked_response,
            "timestamp": self.timestamp,
            "mode": self.mode,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PendingViolation:
        return cls(
            id=data["id"],
            context_id=data["context_id"],
            run_id=data["run_id"],
            violations=data["violations"],
            blocked_response=data["blocked_response"],
            timestamp=data["timestamp"],
            mode=data["mode"],
            status=ResolutionStatus(data.get("status", "pending")),
        )


@dataclass
class ResolutionResult:
    """Result of a resolution action."""

    action: ResolutionAction
    success: bool
    message: str
    new_content: str | None = None      # For FIX: the corrected output
    anchor_update: dict[str, Any] | None = None  # For REVISE: the anchor change
    exception_id: str | None = None     # For PROCEED: the logged exception

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "success": self.success,
            "message": self.message,
            "new_content": self.new_content,
            "anchor_update": self.anchor_update,
            "exception_id": self.exception_id,
        }


@dataclass
class ExceptionRecord:
    """Record of an intentional deviation from constraints."""

    id: str
    violations: list[dict[str, Any]]
    blocked_response_preview: str  # Truncated
    scope: str                     # "single_instance", "session", "project"
    expiry: str | None            # ISO timestamp or None for permanent
    created_at: str
    mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "violations": self.violations,
            "blocked_response_preview": self.blocked_response_preview,
            "scope": self.scope,
            "expiry": self.expiry,
            "created_at": self.created_at,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExceptionRecord:
        return cls(
            id=data["id"],
            violations=data["violations"],
            blocked_response_preview=data["blocked_response_preview"],
            scope=data["scope"],
            expiry=data.get("expiry"),
            created_at=data["created_at"],
            mode=data["mode"],
        )


# =============================================================================
# Chat Backend Protocol (for resolve_fix)
# =============================================================================


@runtime_checkable
class ChatBackend(Protocol):
    """Protocol for chat backend (used by resolve_fix)."""

    async def chat(
        self, messages: list[Any], model: str, **kwargs: Any
    ) -> Any: ...


@dataclass
class ChatMessage:
    """A chat message for correction prompts."""

    role: str
    content: str


# =============================================================================
# ViolationResolver
# =============================================================================


class ViolationResolver:
    """
    Handles fix/revise/proceed actions for pending violations.

    State is stored in .governor/pending_violations.json (single pending at a time).
    Exceptions are stored in .governor/exceptions/.
    """

    # Resolution command patterns
    _RESOLUTION_PATTERNS: dict[str, ResolutionAction] = {
        r"^1$": ResolutionAction.FIX,
        r"^2$": ResolutionAction.REVISE,
        r"^3$": ResolutionAction.PROCEED,
        r"^maude\s+fix$": ResolutionAction.FIX,
        r"^maude\s+revise$": ResolutionAction.REVISE,
        r"^maude\s+proceed$": ResolutionAction.PROCEED,
        # Also allow without "maude" prefix
        r"^fix$": ResolutionAction.FIX,
        r"^revise$": ResolutionAction.REVISE,
        r"^proceed$": ResolutionAction.PROCEED,
    }

    def __init__(
        self,
        governor_dir: Path,
        mode: str = "general",
        context_id: str = "default",
    ) -> None:
        self.governor_dir = governor_dir
        self.mode = mode
        self.context_id = context_id
        self._pending_path = governor_dir / "pending_violations.json"
        self._exceptions_dir = governor_dir / "exceptions"

    def create_pending(
        self,
        violations: list[Violation] | list[dict[str, Any]],
        blocked_response: str,
        run_id: str,
    ) -> PendingViolation:
        """
        Create a pending violation from detected violations.

        Args:
            violations: List of Violation objects or dicts
            blocked_response: The response that was blocked
            run_id: Identifier for the generation run

        Returns:
            The created PendingViolation
        """
        # Convert Violation objects to dicts
        violations_dicts: list[dict[str, Any]] = []
        for v in violations:
            if isinstance(v, Violation):
                violations_dicts.append(v.to_dict())
            else:
                violations_dicts.append(v)

        # Generate ID from violation content
        content_hash = hashlib.sha256(
            json.dumps(violations_dicts, sort_keys=True).encode()
        ).hexdigest()[:12]
        pending_id = f"pend_{content_hash}"

        pending = PendingViolation(
            id=pending_id,
            context_id=self.context_id,
            run_id=run_id,
            violations=violations_dicts,
            blocked_response=blocked_response,
            timestamp=datetime.now(timezone.utc).isoformat(),
            mode=self.mode,
            status=ResolutionStatus.PENDING,
        )

        self._save_pending(pending)
        return pending

    def get_pending(self) -> PendingViolation | None:
        """Get the current pending violation, if any."""
        if not self._pending_path.exists():
            return None

        try:
            data = json.loads(self._pending_path.read_text())
            if not data:
                return None
            pending = PendingViolation.from_dict(data)
            # Only return if still pending
            if pending.status == ResolutionStatus.PENDING:
                return pending
            return None
        except (json.JSONDecodeError, KeyError):
            return None

    def clear_pending(self) -> None:
        """Clear the pending violation."""
        if self._pending_path.exists():
            self._pending_path.unlink()

    def is_resolution_command(self, text: str) -> ResolutionAction | None:
        """
        Check if text is a resolution command.

        Args:
            text: User input to check

        Returns:
            ResolutionAction if matched, None otherwise
        """
        normalized = text.strip().lower()
        for pattern, action in self._RESOLUTION_PATTERNS.items():
            if re.match(pattern, normalized, re.IGNORECASE):
                return action
        return None

    async def resolve_fix(
        self,
        pending: PendingViolation,
        backend: ChatBackend,
        model: str = "claude-sonnet-4-20250514",
    ) -> ResolutionResult:
        """
        Resolve by regenerating response to comply with violated anchor.

        Args:
            pending: The pending violation
            backend: Chat backend for regeneration
            model: Model to use for regeneration

        Returns:
            ResolutionResult with corrected content
        """
        # Build correction prompt
        violation_descs = []
        for v in pending.violations:
            desc = v.get("description", str(v))
            anchor_id = v.get("anchor_id", "unknown")
            violation_descs.append(f"- [{anchor_id}] {desc}")

        violation_text = "\n".join(violation_descs)

        # Build messages for correction
        system_prompt = f"""The previous response violated governance constraints:
{violation_text}

Rewrite the response to comply with these constraints. Preserve the intent and useful content, but fix the violations. Do not apologize or mention the constraints — just provide the corrected response."""

        from .chat_bridge import ChatMessage as BridgeChatMessage

        messages = [
            BridgeChatMessage(role="system", content=system_prompt),
            BridgeChatMessage(role="assistant", content=pending.blocked_response),
            BridgeChatMessage(
                role="user",
                content="Please rewrite this response to comply with the constraints."
            ),
        ]

        try:
            response = await backend.chat(messages, model)
            corrected_content = response.content if hasattr(response, 'content') else str(response)

            # Mark as fixed and clear
            pending.status = ResolutionStatus.FIXED
            self._save_pending(pending)
            self.clear_pending()

            return ResolutionResult(
                action=ResolutionAction.FIX,
                success=True,
                message="Response rewritten to comply with constraints.",
                new_content=corrected_content,
            )
        except Exception as e:
            return ResolutionResult(
                action=ResolutionAction.FIX,
                success=False,
                message=f"Failed to regenerate response: {e}",
            )

    def resolve_revise(
        self,
        pending: PendingViolation,
        new_anchor_text: str | None = None,
    ) -> ResolutionResult:
        """
        Resolve by updating the anchor that caused the violation.

        For fiction mode: Updates character constraints, demotes banned tropes, etc.
        For code mode: Updates decision records.

        Args:
            pending: The pending violation
            new_anchor_text: Optional new text for the anchor

        Returns:
            ResolutionResult with anchor update info
        """
        anchor_ids = list({v.get("anchor_id", "unknown") for v in pending.violations})
        updates: list[dict[str, Any]] = []

        for anchor_id in anchor_ids:
            if self.mode == "fiction":
                update = self._revise_fiction_anchor(anchor_id, pending.blocked_response)
            else:
                update = self._revise_code_anchor(anchor_id, pending.blocked_response)
            if update:
                updates.append(update)

        # Mark as revised and clear
        pending.status = ResolutionStatus.REVISED
        self._save_pending(pending)
        self.clear_pending()

        return ResolutionResult(
            action=ResolutionAction.REVISE,
            success=True,
            message=f"Updated {len(updates)} anchor(s). Response now permitted.",
            new_content=pending.blocked_response,  # Original is now OK
            anchor_update={"revised_anchors": anchor_ids, "updates": updates},
        )

    def resolve_proceed(
        self,
        pending: PendingViolation,
        scope: str | None = None,
        expiry: str | None = None,
    ) -> ResolutionResult:
        """
        Resolve by logging as intentional deviation (exception).

        Args:
            pending: The pending violation
            scope: Exception scope ("single_instance", "session", "project")
            expiry: ISO timestamp for expiry, or None for permanent

        Returns:
            ResolutionResult with exception ID
        """
        exception_id = f"exc_{uuid.uuid4().hex[:8]}"

        exception = ExceptionRecord(
            id=exception_id,
            violations=pending.violations,
            blocked_response_preview=pending.blocked_response[:200],
            scope=scope or "single_instance",
            expiry=expiry,
            created_at=datetime.now(timezone.utc).isoformat(),
            mode=pending.mode,
        )

        self._store_exception(exception)

        # Mark as proceeded and clear
        pending.status = ResolutionStatus.PROCEEDED
        self._save_pending(pending)
        self.clear_pending()

        return ResolutionResult(
            action=ResolutionAction.PROCEED,
            success=True,
            message=f"Exception logged: {exception_id}. Response permitted.",
            new_content=pending.blocked_response,
            exception_id=exception_id,
        )

    def list_exceptions(self) -> list[ExceptionRecord]:
        """List all recorded exceptions."""
        exceptions: list[ExceptionRecord] = []
        if not self._exceptions_dir.exists():
            return exceptions

        for f in sorted(self._exceptions_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                exceptions.append(ExceptionRecord.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                continue

        return exceptions

    def get_exception(self, exception_id: str) -> ExceptionRecord | None:
        """Get a specific exception by ID."""
        exc_path = self._exceptions_dir / f"{exception_id}.json"
        if not exc_path.exists():
            return None

        try:
            data = json.loads(exc_path.read_text())
            return ExceptionRecord.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    # =========================================================================
    # Private helpers
    # =========================================================================

    def _save_pending(self, pending: PendingViolation) -> None:
        """Save pending violation to disk."""
        self._pending_path.parent.mkdir(parents=True, exist_ok=True)
        self._pending_path.write_text(json.dumps(pending.to_dict(), indent=2))

    def _store_exception(self, exception: ExceptionRecord) -> None:
        """Store an exception record to disk."""
        self._exceptions_dir.mkdir(parents=True, exist_ok=True)
        exc_path = self._exceptions_dir / f"{exception.id}.json"
        exc_path.write_text(json.dumps(exception.to_dict(), indent=2))

    def _revise_fiction_anchor(
        self,
        anchor_id: str,
        blocked_response: str,
    ) -> dict[str, Any] | None:
        """
        Revise a fiction-mode anchor based on the blocked response.

        Handles:
        - fiction_char_* : Update character constraints
        - fiction_trope_* : Demote from banned
        - fiction_world_* : Update world rules
        - fiction_tone_* : Update tone constraints

        Returns update info or None if not applicable.
        """
        update: dict[str, Any] = {"anchor_id": anchor_id, "action": "revised"}

        # Character anchors - relax anti-patterns
        if anchor_id.startswith("fiction_char_"):
            char_name = anchor_id.replace("fiction_char_", "").replace("_", " ")
            update["type"] = "character"
            update["character"] = char_name
            update["note"] = f"Relaxed constraints for {char_name} based on narrative need"

            # Try to update bible file if it exists
            bible_dir = self.governor_dir.parent / ".fiction-gov" / "bible"
            chars_file = bible_dir / "characters.json"
            if chars_file.exists():
                try:
                    chars = json.loads(chars_file.read_text())
                    for char in chars:
                        if char.get("name", "").lower() == char_name.lower():
                            # Clear anti-patterns
                            char["anti_patterns"] = []
                            update["cleared_anti_patterns"] = True
                    chars_file.write_text(json.dumps(chars, indent=2))
                except (json.JSONDecodeError, OSError):
                    pass

        # Trope anchors - demote from banned
        elif anchor_id.startswith("fiction_trope_"):
            trope_name = anchor_id.replace("fiction_trope_", "").replace("_", " ")
            update["type"] = "trope"
            update["trope"] = trope_name
            update["note"] = f"Demoted trope '{trope_name}' from banned list"

            bible_dir = self.governor_dir.parent / ".fiction-gov" / "bible"
            tropes_file = bible_dir / "banned_tropes.json"
            if tropes_file.exists():
                try:
                    tropes = json.loads(tropes_file.read_text())
                    tropes = [t for t in tropes if t.get("name", "").lower() != trope_name.lower()]
                    tropes_file.write_text(json.dumps(tropes, indent=2))
                    update["removed_from_banned"] = True
                except (json.JSONDecodeError, OSError):
                    pass

        # World rule anchors
        elif anchor_id.startswith("fiction_world_"):
            rule_name = anchor_id.replace("fiction_world_", "").replace("_", " ")
            update["type"] = "world_rule"
            update["rule"] = rule_name
            update["note"] = f"Relaxed world rule '{rule_name}'"

        # Tone anchors
        elif anchor_id.startswith("fiction_tone_"):
            update["type"] = "tone"
            update["note"] = "Relaxed tone constraints"

        # Continuity anchors (user-registered)
        elif anchor_id.startswith("continuity_"):
            update["type"] = "continuity"
            anchors_path = self.governor_dir / "continuity" / "anchors.json"
            if anchors_path.exists():
                try:
                    registry = AnchorRegistry.load(anchors_path)
                    removed = registry.unregister(anchor_id)
                    if removed:
                        registry.save(anchors_path)
                        update["removed_anchor"] = True
                except Exception:
                    pass

        else:
            update["type"] = "unknown"
            update["note"] = f"Could not automatically revise anchor: {anchor_id}"

        return update

    def _revise_code_anchor(
        self,
        anchor_id: str,
        blocked_response: str,
    ) -> dict[str, Any] | None:
        """
        Revise a code-mode anchor based on the blocked response.

        Handles:
        - code_decision_* : Update decision record

        Returns update info or None if not applicable.
        """
        update: dict[str, Any] = {"anchor_id": anchor_id, "action": "revised"}

        if anchor_id.startswith("code_decision_"):
            decision_topic = anchor_id.replace("code_decision_", "").replace("_", " ")
            update["type"] = "decision"
            update["topic"] = decision_topic
            update["note"] = f"Decision '{decision_topic}' marked for revision"

            # Note: Full decision update requires human review
            # We just mark it as needing revision
            update["requires_human_review"] = True

        elif anchor_id.startswith("continuity_"):
            update["type"] = "continuity"
            anchors_path = self.governor_dir / "continuity" / "anchors.json"
            if anchors_path.exists():
                try:
                    registry = AnchorRegistry.load(anchors_path)
                    removed = registry.unregister(anchor_id)
                    if removed:
                        registry.save(anchors_path)
                        update["removed_anchor"] = True
                except Exception:
                    pass

        else:
            update["type"] = "unknown"
            update["note"] = f"Could not automatically revise anchor: {anchor_id}"

        return update


# =============================================================================
# Convenience functions
# =============================================================================


def create_resolver(
    governor_dir: Path,
    mode: str = "general",
    context_id: str = "default",
) -> ViolationResolver:
    """Create a ViolationResolver for a governor directory."""
    return ViolationResolver(governor_dir, mode=mode, context_id=context_id)


def format_violation_prompt(
    violations: list[dict[str, Any]],
    mode: str = "general",
) -> str:
    """
    Format a user-facing prompt for violation resolution.

    Args:
        violations: List of violation dicts
        mode: Context mode (fiction/code/nonfiction)

    Returns:
        Formatted prompt string
    """
    lines = ["[Governor] Blocked — choose an action:"]

    for v in violations:
        desc = v.get("description", v.get("message", str(v)))
        anchor_id = v.get("anchor_id", "")
        if anchor_id:
            lines.append(f"  * [{anchor_id}] {desc}")
        else:
            lines.append(f"  * {desc}")

    lines.append("")

    # Mode-specific choices
    if mode == "fiction":
        lines.extend([
            "1. Fix — Rewrite to comply with canon",
            "2. Revise — Update the canon anchor",
            "3. Proceed — Log as intentional deviation",
        ])
    elif mode == "nonfiction":
        lines.extend([
            "1. Fix — Rewrite to comply with corpus constraints",
            "2. Revise — Update the constraint",
            "3. Proceed — Log as intentional deviation",
        ])
    else:  # code/general
        lines.extend([
            "1. Fix — Generate compliant response",
            "2. Revise — Update decision record",
            "3. Proceed — Record waiver",
        ])

    lines.append("")
    lines.append("Reply with 1, 2, 3 or: fix | revise | proceed")

    return "\n".join(lines)


def get_mode_choices(mode: str) -> list[str]:
    """Get the list of choice descriptions for a mode."""
    if mode == "fiction":
        return [
            "1. Fix — Rewrite to comply with canon",
            "2. Revise — Update the canon anchor",
            "3. Proceed — Log as intentional deviation",
        ]
    elif mode == "nonfiction":
        return [
            "1. Fix — Rewrite to comply with corpus constraints",
            "2. Revise — Update the constraint",
            "3. Proceed — Log as intentional deviation",
        ]
    else:  # code/general
        return [
            "1. Fix — Generate compliant response",
            "2. Revise — Update decision record",
            "3. Proceed — Record waiver",
        ]
