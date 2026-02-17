# SPDX-License-Identifier: Apache-2.0
"""Tests for the SessionStore (chat session persistence)."""

import json
import time
from pathlib import Path

import pytest

from governor.session_store import ChatSession, SessionMessage, SessionStore


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sessions_dir(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


@pytest.fixture
def store(sessions_dir: Path) -> SessionStore:
    return SessionStore(sessions_dir)


# ============================================================================
# TestSessionMessage
# ============================================================================


class TestSessionMessage:
    """Tests for SessionMessage dataclass."""

    def test_create_user_message(self) -> None:
        msg = SessionMessage.create(role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"
        assert msg.model is None
        assert msg.usage is None
        assert len(msg.id) == 12
        assert msg.timestamp  # non-empty

    def test_create_assistant_message_with_model(self) -> None:
        msg = SessionMessage.create(
            role="assistant", content="Hi!", model="gpt-4", usage={"total_tokens": 10}
        )
        assert msg.role == "assistant"
        assert msg.model == "gpt-4"
        assert msg.usage == {"total_tokens": 10}

    def test_to_dict_user(self) -> None:
        msg = SessionMessage.create(role="user", content="Test")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Test"
        assert "model" not in d  # omitted for user messages
        assert "usage" not in d

    def test_to_dict_assistant(self) -> None:
        msg = SessionMessage.create(role="assistant", content="Reply", model="m1")
        d = msg.to_dict()
        assert d["model"] == "m1"

    def test_roundtrip(self) -> None:
        msg = SessionMessage.create(
            role="assistant", content="Data", model="m", usage={"prompt_tokens": 5}
        )
        d = msg.to_dict()
        restored = SessionMessage.from_dict(d)
        assert restored.id == msg.id
        assert restored.role == msg.role
        assert restored.content == msg.content
        assert restored.model == msg.model
        assert restored.usage == msg.usage
        assert restored.timestamp == msg.timestamp

    def test_from_dict_minimal(self) -> None:
        """from_dict works with only required fields."""
        d = {"id": "abc", "role": "user", "content": "Hi", "timestamp": "2024-01-01T00:00:00"}
        msg = SessionMessage.from_dict(d)
        assert msg.model is None
        assert msg.usage is None


# ============================================================================
# TestChatSession
# ============================================================================


class TestChatSession:
    """Tests for ChatSession dataclass."""

    def test_to_dict(self) -> None:
        session = ChatSession(
            id="s1", context_id="ctx1", title="Test",
            created_at="2024-01-01", updated_at="2024-01-01",
            model="m1", message_count=0, messages=[]
        )
        d = session.to_dict()
        assert d["id"] == "s1"
        assert d["messages"] == []
        assert d["message_count"] == 0

    def test_to_summary_excludes_messages(self) -> None:
        msg = SessionMessage.create(role="user", content="Hi")
        session = ChatSession(
            id="s1", context_id="ctx1", title="Test",
            created_at="2024-01-01", updated_at="2024-01-01",
            model="m1", message_count=1, messages=[msg]
        )
        summary = session.to_summary()
        assert "messages" not in summary
        assert summary["message_count"] == 1

    def test_roundtrip(self) -> None:
        msg = SessionMessage.create(role="user", content="Hi")
        session = ChatSession(
            id="s1", context_id="ctx1", title="Hello",
            created_at="2024-01-01", updated_at="2024-01-01",
            model="m1", message_count=1, messages=[msg]
        )
        d = session.to_dict()
        restored = ChatSession.from_dict(d)
        assert restored.id == session.id
        assert len(restored.messages) == 1
        assert restored.messages[0].content == "Hi"

    def test_from_dict_defaults(self) -> None:
        """from_dict fills defaults for optional fields."""
        d = {
            "id": "s1", "context_id": "c", "title": "T",
            "created_at": "now", "updated_at": "now", "model": "m"
        }
        session = ChatSession.from_dict(d)
        assert session.message_count == 0
        assert session.messages == []


# ============================================================================
# TestSessionStore
# ============================================================================


class TestSessionStore:
    """Tests for SessionStore CRUD operations."""

    def test_create_session(self, store: SessionStore) -> None:
        session = store.create(context_id="ctx1", model="m1", title="My chat")
        assert session.context_id == "ctx1"
        assert session.model == "m1"
        assert session.title == "My chat"
        assert session.message_count == 0
        assert len(session.id) == 16

    def test_create_creates_dir(self, store: SessionStore, sessions_dir: Path) -> None:
        assert not sessions_dir.exists()
        store.create(context_id="ctx1")
        assert sessions_dir.exists()

    def test_get_existing(self, store: SessionStore) -> None:
        created = store.create(context_id="ctx1")
        fetched = store.get(created.id)
        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.context_id == "ctx1"

    def test_get_nonexistent(self, store: SessionStore) -> None:
        assert store.get("nonexistent") is None

    def test_list_summaries_empty(self, store: SessionStore) -> None:
        assert store.list_summaries() == []

    def test_list_summaries(self, store: SessionStore) -> None:
        store.create(context_id="ctx1", title="First")
        time.sleep(0.01)  # ensure different timestamps
        store.create(context_id="ctx1", title="Second")
        summaries = store.list_summaries()
        assert len(summaries) == 2
        # Most recent first
        assert summaries[0]["title"] == "Second"
        assert summaries[1]["title"] == "First"
        # No messages in summaries
        assert "messages" not in summaries[0]

    def test_delete_existing(self, store: SessionStore) -> None:
        session = store.create(context_id="ctx1")
        assert store.delete(session.id) is True
        assert store.get(session.id) is None

    def test_delete_nonexistent(self, store: SessionStore) -> None:
        assert store.delete("nonexistent") is False

    def test_update_title(self, store: SessionStore) -> None:
        session = store.create(context_id="ctx1", title="Old")
        assert store.update_title(session.id, "New Title") is True
        fetched = store.get(session.id)
        assert fetched is not None
        assert fetched.title == "New Title"

    def test_update_title_nonexistent(self, store: SessionStore) -> None:
        assert store.update_title("nonexistent", "Title") is False

    def test_update_title_changes_updated_at(self, store: SessionStore) -> None:
        session = store.create(context_id="ctx1")
        old_updated = session.updated_at
        time.sleep(0.01)
        store.update_title(session.id, "Updated")
        fetched = store.get(session.id)
        assert fetched is not None
        assert fetched.updated_at >= old_updated

    def test_append_message(self, store: SessionStore) -> None:
        session = store.create(context_id="ctx1")
        msg = SessionMessage.create(role="user", content="Hello")
        assert store.append_message(session.id, msg) is True
        fetched = store.get(session.id)
        assert fetched is not None
        assert fetched.message_count == 1
        assert fetched.messages[0].content == "Hello"

    def test_append_message_increments_count(self, store: SessionStore) -> None:
        session = store.create(context_id="ctx1")
        for i in range(3):
            msg = SessionMessage.create(role="user", content=f"Msg {i}")
            store.append_message(session.id, msg)
        fetched = store.get(session.id)
        assert fetched is not None
        assert fetched.message_count == 3

    def test_append_message_updates_timestamp(self, store: SessionStore) -> None:
        session = store.create(context_id="ctx1")
        old_ts = session.updated_at
        time.sleep(0.01)
        msg = SessionMessage.create(role="user", content="Hi")
        store.append_message(session.id, msg)
        fetched = store.get(session.id)
        assert fetched is not None
        assert fetched.updated_at >= old_ts

    def test_append_message_nonexistent(self, store: SessionStore) -> None:
        msg = SessionMessage.create(role="user", content="Hi")
        assert store.append_message("nonexistent", msg) is False

    def test_corrupted_json_returns_none(self, store: SessionStore, sessions_dir: Path) -> None:
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "bad.json").write_text("not json{{{")
        assert store.get("bad") is None

    def test_corrupted_json_skipped_in_list(self, store: SessionStore, sessions_dir: Path) -> None:
        store.create(context_id="ctx1", title="Good")
        (sessions_dir / "corrupt.json").write_text("{invalid")
        summaries = store.list_summaries()
        assert len(summaries) == 1
        assert summaries[0]["title"] == "Good"

    def test_filesystem_safety(self, store: SessionStore) -> None:
        """IDs with special characters are sanitized and stay within sessions dir."""
        path = store._session_path("../../etc/passwd")
        # Path must be inside sessions_dir (no traversal)
        assert path.parent == store.sessions_dir
        # Slashes are replaced
        assert "/" not in path.stem

    def test_multiple_sessions_isolation(self, store: SessionStore) -> None:
        s1 = store.create(context_id="ctx1", title="Session 1")
        s2 = store.create(context_id="ctx1", title="Session 2")
        msg1 = SessionMessage.create(role="user", content="In session 1")
        msg2 = SessionMessage.create(role="user", content="In session 2")
        store.append_message(s1.id, msg1)
        store.append_message(s2.id, msg2)
        f1 = store.get(s1.id)
        f2 = store.get(s2.id)
        assert f1 is not None and f2 is not None
        assert f1.messages[0].content == "In session 1"
        assert f2.messages[0].content == "In session 2"
