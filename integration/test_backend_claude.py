# SPDX-License-Identifier: Apache-2.0
"""Backend smoke tests: Claude Code.

These tests require a working claude CLI and ANTHROPIC_API_KEY.
Skipped by default.  To run:

    CONTRACT_TEST_CLAUDE=1 CLAUDE_PATH=/path/to/claude pytest test_backend_claude.py -v
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.asyncio

SKIP = os.environ.get("CONTRACT_TEST_CLAUDE", "") != "1"
REASON = "Claude Code backend not configured; set CONTRACT_TEST_CLAUDE=1"


@pytest.mark.skipif(SKIP, reason=REASON)
async def test_claude_health_connected(client):
    """With claude-code backend, health shows connected=True."""
    health = await client.health()
    assert health.backend.type == "claude-code"
    assert health.backend.connected is True


@pytest.mark.skipif(SKIP, reason=REASON)
async def test_claude_stream_one_chunk(client):
    """Claude Code backend can stream at least one content chunk."""
    chunks = []
    async for chunk in client.chat_stream(
        messages=[{"role": "user", "content": "Reply with exactly: hello"}],
    ):
        assert isinstance(chunk, str)
        chunks.append(chunk)
        if len(chunks) >= 1:
            break
    assert len(chunks) >= 1
