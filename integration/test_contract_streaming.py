"""Contract test for SSE streaming via /v1/chat/completions.

Skipped by default — requires a live chat backend.
Set CONTRACT_SKIP_STREAMING=0 to enable.
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.asyncio

SKIP = os.environ.get("CONTRACT_SKIP_STREAMING", "1") != "0"


@pytest.mark.skipif(SKIP, reason="No live chat backend; set CONTRACT_SKIP_STREAMING=0")
async def test_chat_stream_yields_strings(client):
    """chat_stream() yields string chunks when a backend is available."""
    chunks = []
    async for chunk in client.chat_stream(
        messages=[{"role": "user", "content": "Say hello in exactly one word."}],
    ):
        assert isinstance(chunk, str)
        chunks.append(chunk)
        if len(chunks) >= 3:
            break  # don't drain the whole response
    assert len(chunks) > 0
