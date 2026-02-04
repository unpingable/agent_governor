"""
Session store: persistent chat session management.

SessionMessage and ChatSession dataclasses with file-per-session JSON persistence.
Follows the InvariantStore pattern (file-per-item in a sessions directory).

Sessions are stored as JSON files at {context_root}/sessions/{session_id}.json.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class SessionMessage:
    """A single message in a chat session."""

    id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: str  # ISO 8601
    model: str | None = None  # assistant messages only
    usage: dict[str, int] | None = None  # assistant messages only

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
        }
        if self.model is not None:
            d["model"] = self.model
        if self.usage is not None:
            d["usage"] = self.usage
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionMessage:
        return cls(
            id=data["id"],
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"],
            model=data.get("model"),
            usage=data.get("usage"),
        )

    @classmethod
    def create(
        cls,
        role: str,
        content: str,
        model: str | None = None,
        usage: dict[str, int] | None = None,
    ) -> SessionMessage:
        return cls(
            id=uuid.uuid4().hex[:12],
            role=role,
            content=content,
            timestamp=datetime.now(timezone.utc).isoformat(),
            model=model,
            usage=usage,
        )


@dataclass
class ChatSession:
    """A persistent chat session with message history."""

    id: str
    context_id: str
    title: str
    created_at: str  # ISO 8601
    updated_at: str  # ISO 8601
    model: str
    message_count: int = 0
    messages: list[SessionMessage] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "context_id": self.context_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "message_count": self.message_count,
            "messages": [m.to_dict() for m in self.messages],
        }

    def to_summary(self) -> dict[str, Any]:
        """Summary without messages (for list endpoints)."""
        return {
            "id": self.id,
            "context_id": self.context_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "model": self.model,
            "message_count": self.message_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChatSession:
        return cls(
            id=data["id"],
            context_id=data["context_id"],
            title=data["title"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            model=data["model"],
            message_count=data.get("message_count", 0),
            messages=[
                SessionMessage.from_dict(m) for m in data.get("messages", [])
            ],
        )


class SessionStore:
    """
    File-per-session persistence for chat sessions.

    Sessions are stored as JSON in {sessions_dir}/{session_id}.json.
    Follows the InvariantStore pattern.
    """

    def __init__(self, sessions_dir: Path):
        self.sessions_dir = sessions_dir

    def _ensure_dir(self) -> None:
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        safe_id = re.sub(r"[^\w\-.]", "_", session_id)
        return self.sessions_dir / f"{safe_id}.json"

    def _write_session(self, session: ChatSession) -> None:
        """Write session to disk."""
        self._ensure_dir()
        path = self._session_path(session.id)
        path.write_text(json.dumps(session.to_dict(), indent=2) + "\n")

    def _read_session(self, session_id: str) -> ChatSession | None:
        """Read session from disk. Returns None if not found or corrupted."""
        path = self._session_path(session_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return ChatSession.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def create(
        self,
        context_id: str,
        model: str = "",
        title: str = "New conversation",
    ) -> ChatSession:
        """Create a new session."""
        now = datetime.now(timezone.utc).isoformat()
        session = ChatSession(
            id=uuid.uuid4().hex[:16],
            context_id=context_id,
            title=title,
            created_at=now,
            updated_at=now,
            model=model,
            message_count=0,
            messages=[],
        )
        self._write_session(session)
        return session

    def get(self, session_id: str) -> ChatSession | None:
        """Get a session by ID (includes messages)."""
        return self._read_session(session_id)

    def list_summaries(self) -> list[dict[str, Any]]:
        """List all sessions as summaries (no messages), sorted by updated_at desc."""
        if not self.sessions_dir.exists():
            return []
        summaries: list[dict[str, Any]] = []
        for path in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                session = ChatSession.from_dict(data)
                summaries.append(session.to_summary())
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        summaries.sort(key=lambda s: s["updated_at"], reverse=True)
        return summaries

    def delete(self, session_id: str) -> bool:
        """Delete a session. Returns True if it existed."""
        path = self._session_path(session_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def update_title(self, session_id: str, title: str) -> bool:
        """Update a session's title. Returns True if session existed."""
        session = self._read_session(session_id)
        if session is None:
            return False
        session.title = title
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._write_session(session)
        return True

    def append_message(self, session_id: str, msg: SessionMessage) -> bool:
        """Append a message to a session. Returns True if session existed."""
        session = self._read_session(session_id)
        if session is None:
            return False
        session.messages.append(msg)
        session.message_count = len(session.messages)
        session.updated_at = datetime.now(timezone.utc).isoformat()
        self._write_session(session)
        return True
