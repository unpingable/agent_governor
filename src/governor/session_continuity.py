# SPDX-License-Identifier: Apache-2.0
"""Session Continuity — capsule-based session management.

This is NOT chat replay. It is restoration of intent, constraints, and authority state.

Core distinction:
- Chat replay: Resume conversation
- Capsule resume: Resume intent + constraints + authority

Structure:
- Ledger (small, durable): anchors, invariants, canon, decisions
- Workspace (medium): current draft state, active threads, cursor
- Transcript (optional): raw history, load on demand
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import json
import yaml
import hashlib
import shutil


def _utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _generate_id(prefix: str) -> str:
    """Generate a stable unique ID."""
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# -----------------------------------------------------------------------------
# Types
# -----------------------------------------------------------------------------


class SessionState(str, Enum):
    """State of a session."""
    ACTIVE = "active"
    CHECKPOINTED = "checkpointed"
    FORKED = "forked"
    PROMOTED = "promoted"
    ARCHIVED = "archived"


@dataclass
class SessionMetadata:
    """Metadata for a session."""
    session_id: str
    name: str
    mode: str  # "fiction" | "nonfiction" | "code"
    created_at: datetime
    last_active: datetime
    state: SessionState
    parent_id: str | None = None  # For forks
    is_mainline: bool = True
    checkpoint_count: int = 0
    fork_count: int = 0

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "name": self.name,
            "mode": self.mode,
            "created_at": self.created_at.isoformat(),
            "last_active": self.last_active.isoformat(),
            "state": self.state.value,
            "parent_id": self.parent_id,
            "is_mainline": self.is_mainline,
            "checkpoint_count": self.checkpoint_count,
            "fork_count": self.fork_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionMetadata":
        return cls(
            session_id=data["session_id"],
            name=data["name"],
            mode=data["mode"],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_active=datetime.fromisoformat(data["last_active"]),
            state=SessionState(data["state"]),
            parent_id=data.get("parent_id"),
            is_mainline=data.get("is_mainline", True),
            checkpoint_count=data.get("checkpoint_count", 0),
            fork_count=data.get("fork_count", 0),
        )


@dataclass
class LedgerState:
    """Layer 1: Durable governance state.

    This MUST survive. It cannot be reconstructed from conversation.
    """
    # Anchors (continuity constraints)
    anchors: list[dict] = field(default_factory=list)

    # Decisions (normative choices)
    decisions: list[dict] = field(default_factory=list)

    # Canon (for fiction mode)
    canon_events: list[dict] = field(default_factory=list)

    # Authority state (who approved what)
    authority: dict = field(default_factory=dict)

    # Intent (what we're trying to accomplish)
    intent: str | None = None

    # Active constraints
    constraints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "anchors": self.anchors,
            "decisions": self.decisions,
            "canon_events": self.canon_events,
            "authority": self.authority,
            "intent": self.intent,
            "constraints": self.constraints,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LedgerState":
        return cls(
            anchors=data.get("anchors", []),
            decisions=data.get("decisions", []),
            canon_events=data.get("canon_events", []),
            authority=data.get("authority", {}),
            intent=data.get("intent"),
            constraints=data.get("constraints", []),
        )

    def content_hash(self) -> str:
        """Hash of ledger content for integrity checking."""
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class WorkspaceState:
    """Layer 2: Current working state.

    This should survive resume. It represents "where we are" in the work.
    """
    # Active threads/characters (fiction)
    active_thread_ids: list[str] = field(default_factory=list)
    active_character_ids: list[str] = field(default_factory=list)

    # Current work state
    current_section: str | None = None
    cursor_position: dict | None = None  # {"file": "...", "line": N}

    # Draft state (outline, notes)
    outline: list[str] = field(default_factory=list)
    notes: str = ""

    # Working context
    context_summary: str = ""

    def to_dict(self) -> dict:
        return {
            "active_thread_ids": self.active_thread_ids,
            "active_character_ids": self.active_character_ids,
            "current_section": self.current_section,
            "cursor_position": self.cursor_position,
            "outline": self.outline,
            "notes": self.notes,
            "context_summary": self.context_summary,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceState":
        return cls(
            active_thread_ids=data.get("active_thread_ids", []),
            active_character_ids=data.get("active_character_ids", []),
            current_section=data.get("current_section"),
            cursor_position=data.get("cursor_position"),
            outline=data.get("outline", []),
            notes=data.get("notes", ""),
            context_summary=data.get("context_summary", ""),
        )

    def content_hash(self) -> str:
        """Hash of workspace content."""
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Capsule:
    """A complete session capsule: metadata + ledger + workspace.

    This is what gets saved and restored on resume.
    Transcript is NOT part of the capsule — it's loaded on demand.
    """
    metadata: SessionMetadata
    ledger: LedgerState
    workspace: WorkspaceState

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata.to_dict(),
            "ledger": self.ledger.to_dict(),
            "workspace": self.workspace.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Capsule":
        return cls(
            metadata=SessionMetadata.from_dict(data["metadata"]),
            ledger=LedgerState.from_dict(data["ledger"]),
            workspace=WorkspaceState.from_dict(data["workspace"]),
        )

    def integrity_hash(self) -> str:
        """Combined hash for integrity verification."""
        combined = f"{self.ledger.content_hash()}:{self.workspace.content_hash()}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]


@dataclass
class Checkpoint:
    """A named checkpoint within a session."""
    checkpoint_id: str
    session_id: str
    name: str
    created_at: datetime
    ledger_hash: str
    workspace_hash: str
    capsule: Capsule

    def to_dict(self) -> dict:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "ledger_hash": self.ledger_hash,
            "workspace_hash": self.workspace_hash,
            "capsule": self.capsule.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Checkpoint":
        return cls(
            checkpoint_id=data["checkpoint_id"],
            session_id=data["session_id"],
            name=data["name"],
            created_at=datetime.fromisoformat(data["created_at"]),
            ledger_hash=data["ledger_hash"],
            workspace_hash=data["workspace_hash"],
            capsule=Capsule.from_dict(data["capsule"]),
        )


# -----------------------------------------------------------------------------
# Session Store
# -----------------------------------------------------------------------------


class SessionStore:
    """Persistent storage for sessions.

    Directory structure:
    .governor/sessions/
    ├── index.json           # Session index
    ├── {session_id}/
    │   ├── meta.json        # Session metadata
    │   ├── ledger.yaml      # Layer 1 state
    │   ├── workspace.json   # Layer 2 state
    │   ├── checkpoints/
    │   │   ├── {checkpoint_id}.json
    │   │   └── ...
    │   └── transcript/      # Optional, lazy-loaded
    │       └── ...
    └── ...
    """

    def __init__(self, base_path: Path | str = ".governor/sessions"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._index_path = self.base_path / "index.json"
        self._index: dict[str, dict] = self._load_index()

    def _load_index(self) -> dict:
        """Load session index."""
        if self._index_path.exists():
            with open(self._index_path) as f:
                return json.load(f)
        return {"sessions": {}, "mainline": None}

    def _save_index(self) -> None:
        """Save session index."""
        with open(self._index_path, "w") as f:
            json.dump(self._index, f, indent=2)

    def _session_dir(self, session_id: str) -> Path:
        """Get session directory."""
        return self.base_path / session_id

    def create_session(
        self,
        name: str,
        mode: str = "fiction",
        parent_id: str | None = None,
    ) -> Capsule:
        """Create a new session."""
        session_id = _generate_id("sess")
        now = _utcnow()

        metadata = SessionMetadata(
            session_id=session_id,
            name=name,
            mode=mode,
            created_at=now,
            last_active=now,
            state=SessionState.ACTIVE,
            parent_id=parent_id,
            is_mainline=parent_id is None,
        )

        ledger = LedgerState()
        workspace = WorkspaceState()

        # If forking, copy parent's ledger
        if parent_id:
            parent = self.load_session(parent_id)
            if parent:
                ledger = LedgerState.from_dict(parent.ledger.to_dict())
                workspace = WorkspaceState.from_dict(parent.workspace.to_dict())
                metadata.is_mainline = False

        capsule = Capsule(metadata=metadata, ledger=ledger, workspace=workspace)
        self.save_session(capsule)

        # Update index
        self._index["sessions"][session_id] = {
            "name": name,
            "mode": mode,
            "created_at": now.isoformat(),
            "parent_id": parent_id,
            "is_mainline": metadata.is_mainline,
        }
        if metadata.is_mainline and self._index["mainline"] is None:
            self._index["mainline"] = session_id
        self._save_index()

        return capsule

    def save_session(self, capsule: Capsule) -> None:
        """Save a session capsule."""
        session_dir = self._session_dir(capsule.metadata.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        meta_path = session_dir / "meta.json"
        with open(meta_path, "w") as f:
            json.dump(capsule.metadata.to_dict(), f, indent=2)

        # Save ledger as YAML (human-readable for anchors/decisions)
        ledger_path = session_dir / "ledger.yaml"
        with open(ledger_path, "w") as f:
            yaml.dump(capsule.ledger.to_dict(), f, default_flow_style=False)

        # Save workspace as JSON
        workspace_path = session_dir / "workspace.json"
        with open(workspace_path, "w") as f:
            json.dump(capsule.workspace.to_dict(), f, indent=2)

        # Update index
        self._index["sessions"][capsule.metadata.session_id] = {
            "name": capsule.metadata.name,
            "mode": capsule.metadata.mode,
            "created_at": capsule.metadata.created_at.isoformat(),
            "last_active": capsule.metadata.last_active.isoformat(),
            "parent_id": capsule.metadata.parent_id,
            "is_mainline": capsule.metadata.is_mainline,
        }
        self._save_index()

    def load_session(self, session_id: str) -> Capsule | None:
        """Load a session capsule."""
        session_dir = self._session_dir(session_id)
        if not session_dir.exists():
            return None

        # Load metadata
        meta_path = session_dir / "meta.json"
        if not meta_path.exists():
            return None
        with open(meta_path) as f:
            metadata = SessionMetadata.from_dict(json.load(f))

        # Load ledger
        ledger_path = session_dir / "ledger.yaml"
        if ledger_path.exists():
            with open(ledger_path) as f:
                ledger = LedgerState.from_dict(yaml.safe_load(f) or {})
        else:
            ledger = LedgerState()

        # Load workspace
        workspace_path = session_dir / "workspace.json"
        if workspace_path.exists():
            with open(workspace_path) as f:
                workspace = WorkspaceState.from_dict(json.load(f))
        else:
            workspace = WorkspaceState()

        return Capsule(metadata=metadata, ledger=ledger, workspace=workspace)

    def list_sessions(self, mode: str | None = None) -> list[dict]:
        """List all sessions."""
        sessions = []
        for session_id, info in self._index.get("sessions", {}).items():
            if mode is None or info.get("mode") == mode:
                sessions.append({
                    "session_id": session_id,
                    **info,
                })
        return sorted(sessions, key=lambda s: s.get("last_active", ""), reverse=True)

    def get_mainline(self, mode: str | None = None) -> str | None:
        """Get the mainline session ID."""
        if mode is None:
            return self._index.get("mainline")

        for session_id, info in self._index.get("sessions", {}).items():
            if info.get("is_mainline") and (mode is None or info.get("mode") == mode):
                return session_id
        return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        session_dir = self._session_dir(session_id)
        if session_dir.exists():
            shutil.rmtree(session_dir)

        if session_id in self._index.get("sessions", {}):
            del self._index["sessions"][session_id]
            if self._index.get("mainline") == session_id:
                self._index["mainline"] = None
            self._save_index()
            return True
        return False


# -----------------------------------------------------------------------------
# Session Manager
# -----------------------------------------------------------------------------


class SessionManager:
    """High-level session management operations.

    This is the main interface for session continuity.
    """

    def __init__(self, store: SessionStore | None = None):
        self.store = store or SessionStore()
        self._active_session: Capsule | None = None

    @property
    def active(self) -> Capsule | None:
        """Get the currently active session."""
        return self._active_session

    def create(self, name: str, mode: str = "fiction") -> Capsule:
        """Create a new session and make it active."""
        capsule = self.store.create_session(name, mode)
        self._active_session = capsule
        return capsule

    def resume(self, session_id: str) -> Capsule | None:
        """Resume a session by ID.

        This loads the capsule (ledger + workspace) and makes it active.
        Transcript is NOT loaded — it's available on demand.
        """
        capsule = self.store.load_session(session_id)
        if capsule:
            # Update last_active
            capsule.metadata.last_active = _utcnow()
            capsule.metadata.state = SessionState.ACTIVE
            self.store.save_session(capsule)
            self._active_session = capsule
        return capsule

    def resume_last(self, mode: str | None = None) -> Capsule | None:
        """Resume the most recently active session."""
        sessions = self.store.list_sessions(mode)
        if sessions:
            return self.resume(sessions[0]["session_id"])
        return None

    def checkpoint(self, name: str | None = None) -> Checkpoint | None:
        """Create a checkpoint of the active session.

        A checkpoint captures the current capsule state for later reference.
        """
        if not self._active_session:
            return None

        session_id = self._active_session.metadata.session_id
        checkpoint_id = _generate_id("cp")
        now = _utcnow()

        checkpoint = Checkpoint(
            checkpoint_id=checkpoint_id,
            session_id=session_id,
            name=name or f"checkpoint-{self._active_session.metadata.checkpoint_count + 1}",
            created_at=now,
            ledger_hash=self._active_session.ledger.content_hash(),
            workspace_hash=self._active_session.workspace.content_hash(),
            capsule=Capsule.from_dict(self._active_session.to_dict()),  # Deep copy
        )

        # Save checkpoint
        session_dir = self.store._session_dir(session_id)
        checkpoints_dir = session_dir / "checkpoints"
        checkpoints_dir.mkdir(exist_ok=True)

        checkpoint_path = checkpoints_dir / f"{checkpoint_id}.json"
        with open(checkpoint_path, "w") as f:
            json.dump(checkpoint.to_dict(), f, indent=2)

        # Update session
        self._active_session.metadata.checkpoint_count += 1
        self._active_session.metadata.state = SessionState.CHECKPOINTED
        self.store.save_session(self._active_session)

        return checkpoint

    def fork(self, name: str | None = None) -> Capsule | None:
        """Fork the active session.

        Creates a new session branching from the current state.
        The fork inherits ledger and workspace but is independent going forward.
        """
        if not self._active_session:
            return None

        parent_id = self._active_session.metadata.session_id
        fork_name = name or f"{self._active_session.metadata.name}-fork-{self._active_session.metadata.fork_count + 1}"

        # Create fork
        fork_capsule = self.store.create_session(
            name=fork_name,
            mode=self._active_session.metadata.mode,
            parent_id=parent_id,
        )

        # Update parent
        self._active_session.metadata.fork_count += 1
        self._active_session.metadata.state = SessionState.FORKED
        self.store.save_session(self._active_session)

        return fork_capsule

    def promote(self, session_id: str) -> bool:
        """Promote a fork to mainline.

        The promoted session becomes the new mainline.
        The old mainline is archived (not deleted).

        Returns True if promotion succeeded.
        """
        fork = self.store.load_session(session_id)
        if not fork:
            return False

        if fork.metadata.is_mainline:
            return True  # Already mainline

        # Find current mainline
        old_mainline_id = self.store.get_mainline(fork.metadata.mode)

        # Archive old mainline
        if old_mainline_id:
            old_mainline = self.store.load_session(old_mainline_id)
            if old_mainline:
                old_mainline.metadata.is_mainline = False
                old_mainline.metadata.state = SessionState.ARCHIVED
                self.store.save_session(old_mainline)

        # Promote fork
        fork.metadata.is_mainline = True
        fork.metadata.state = SessionState.PROMOTED
        self.store.save_session(fork)

        # Update index
        self.store._index["mainline"] = session_id
        self.store._save_index()

        return True

    def update_ledger(
        self,
        anchors: list[dict] | None = None,
        decisions: list[dict] | None = None,
        intent: str | None = None,
        constraints: list[str] | None = None,
    ) -> bool:
        """Update the active session's ledger.

        This is how governance state gets persisted.
        """
        if not self._active_session:
            return False

        if anchors is not None:
            self._active_session.ledger.anchors = anchors
        if decisions is not None:
            self._active_session.ledger.decisions = decisions
        if intent is not None:
            self._active_session.ledger.intent = intent
        if constraints is not None:
            self._active_session.ledger.constraints = constraints

        self._active_session.metadata.last_active = _utcnow()
        self.store.save_session(self._active_session)
        return True

    def update_workspace(
        self,
        active_thread_ids: list[str] | None = None,
        active_character_ids: list[str] | None = None,
        current_section: str | None = None,
        context_summary: str | None = None,
    ) -> bool:
        """Update the active session's workspace."""
        if not self._active_session:
            return False

        if active_thread_ids is not None:
            self._active_session.workspace.active_thread_ids = active_thread_ids
        if active_character_ids is not None:
            self._active_session.workspace.active_character_ids = active_character_ids
        if current_section is not None:
            self._active_session.workspace.current_section = current_section
        if context_summary is not None:
            self._active_session.workspace.context_summary = context_summary

        self._active_session.metadata.last_active = _utcnow()
        self.store.save_session(self._active_session)
        return True

    def get_checkpoints(self, session_id: str | None = None) -> list[dict]:
        """Get checkpoints for a session."""
        sid = session_id or (self._active_session.metadata.session_id if self._active_session else None)
        if not sid:
            return []

        session_dir = self.store._session_dir(sid)
        checkpoints_dir = session_dir / "checkpoints"
        if not checkpoints_dir.exists():
            return []

        checkpoints = []
        for cp_file in checkpoints_dir.glob("*.json"):
            with open(cp_file) as f:
                data = json.load(f)
                checkpoints.append({
                    "checkpoint_id": data["checkpoint_id"],
                    "name": data["name"],
                    "created_at": data["created_at"],
                    "ledger_hash": data["ledger_hash"],
                    "workspace_hash": data["workspace_hash"],
                })

        return sorted(checkpoints, key=lambda c: c["created_at"], reverse=True)

    def restore_checkpoint(self, checkpoint_id: str) -> Capsule | None:
        """Restore from a checkpoint.

        This creates a new fork from the checkpoint state.
        """
        if not self._active_session:
            return None

        session_dir = self.store._session_dir(self._active_session.metadata.session_id)
        checkpoint_path = session_dir / "checkpoints" / f"{checkpoint_id}.json"

        if not checkpoint_path.exists():
            return None

        with open(checkpoint_path) as f:
            checkpoint = Checkpoint.from_dict(json.load(f))

        # Create a new session from checkpoint
        restored = self.store.create_session(
            name=f"restored-from-{checkpoint.name}",
            mode=self._active_session.metadata.mode,
            parent_id=self._active_session.metadata.session_id,
        )

        # Copy checkpoint state
        restored.ledger = LedgerState.from_dict(checkpoint.capsule.ledger.to_dict())
        restored.workspace = WorkspaceState.from_dict(checkpoint.capsule.workspace.to_dict())
        self.store.save_session(restored)

        return restored


# -----------------------------------------------------------------------------
# Module-level convenience
# -----------------------------------------------------------------------------


_default_manager: SessionManager | None = None


def get_session_manager() -> SessionManager:
    """Get or create the default session manager."""
    global _default_manager
    if _default_manager is None:
        _default_manager = SessionManager()
    return _default_manager
