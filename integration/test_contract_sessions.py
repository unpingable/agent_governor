"""Contract tests for /sessions/ endpoints.

Verifies that Maude's session models (SessionSummary, ChatSession,
SessionMessage) can deserialize Governor's actual responses.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_list_sessions_empty_or_valid(client):
    """GET /sessions/ returns a list (possibly empty) of SessionSummary."""
    sessions = await client.list_sessions()
    assert isinstance(sessions, list)


async def test_create_session(client):
    """POST /sessions/ returns a valid ChatSession."""
    session = await client.create_session(title="contract-test")
    assert session.id
    assert session.title == "contract-test"
    assert session.context_id
    # Cleanup
    await client.delete_session(session.id)


async def test_get_session_by_id(client):
    """GET /sessions/{id} returns a ChatSession matching the created one."""
    created = await client.create_session(title="get-by-id")
    fetched = await client.get_session(created.id)
    assert fetched.id == created.id
    assert fetched.title == "get-by-id"
    assert isinstance(fetched.messages, list)
    await client.delete_session(created.id)


async def test_list_includes_created_session(client):
    """After creating a session, list_sessions includes it."""
    created = await client.create_session(title="list-check")
    sessions = await client.list_sessions()
    ids = [s.id for s in sessions]
    assert created.id in ids
    await client.delete_session(created.id)


async def test_delete_existing_session(client):
    """DELETE an existing session returns True."""
    created = await client.create_session(title="to-delete")
    result = await client.delete_session(created.id)
    assert result is True


async def test_delete_nonexistent_session(client):
    """DELETE a nonexistent session returns False (404 → status != 200)."""
    result = await client.delete_session("nonexistent-id-00000")
    assert result is False


async def test_append_message(client):
    """POST /sessions/{id}/messages returns a valid SessionMessage."""
    session = await client.create_session(title="msg-test")
    msg = await client.append_message(
        session_id=session.id,
        role="user",
        content="Hello from contract test",
    )
    assert msg.id
    assert msg.role == "user"
    assert msg.content == "Hello from contract test"
    assert msg.timestamp
    await client.delete_session(session.id)
