# SPDX-License-Identifier: Apache-2.0
"""Backend smoke tests: Ollama.

These tests require a running Ollama instance with a model pulled.
Skipped by default.  To run:

    CONTRACT_TEST_OLLAMA=1 OLLAMA_HOST=http://localhost:11434 pytest test_backend_ollama.py -v
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.asyncio

SKIP = os.environ.get("CONTRACT_TEST_OLLAMA", "") != "1"
REASON = "Ollama backend not configured; set CONTRACT_TEST_OLLAMA=1"


@pytest.mark.skipif(SKIP, reason=REASON)
async def test_ollama_health_connected(client):
    """With a reachable Ollama, health shows connected=True."""
    health = await client.health()
    assert health.backend.type == "ollama"
    assert health.backend.connected is True


@pytest.mark.skipif(SKIP, reason=REASON)
async def test_ollama_stream_one_chunk(client):
    """Ollama backend can stream at least one content chunk."""
    chunks = []
    async for chunk in client.chat_stream(
        messages=[{"role": "user", "content": "Reply with exactly: hello"}],
    ):
        assert isinstance(chunk, str)
        chunks.append(chunk)
        if len(chunks) >= 1:
            break
    assert len(chunks) >= 1
