"""Backend smoke tests: Codex.

These tests require a working codex binary and OPENAI_API_KEY.
Skipped by default.  To run:

    CONTRACT_TEST_CODEX=1 CODEX_PATH=/path/to/codex pytest test_backend_codex.py -v
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.asyncio

SKIP = os.environ.get("CONTRACT_TEST_CODEX", "") != "1"
REASON = "Codex backend not configured; set CONTRACT_TEST_CODEX=1"


@pytest.mark.skipif(SKIP, reason=REASON)
async def test_codex_health_connected(client):
    """With codex backend, health shows connected=True."""
    health = await client.health()
    assert health.backend.type == "codex"
    assert health.backend.connected is True


@pytest.mark.skipif(SKIP, reason=REASON)
async def test_codex_stream_one_chunk(client):
    """Codex backend can stream at least one content chunk."""
    chunks = []
    async for chunk in client.chat_stream(
        messages=[{"role": "user", "content": "Reply with exactly: hello"}],
    ):
        assert isinstance(chunk, str)
        chunks.append(chunk)
        if len(chunks) >= 1:
            break
    assert len(chunks) >= 1
