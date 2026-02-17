# SPDX-License-Identifier: Apache-2.0
"""Contract tests for governor.hello (health).

Verifies that Maude's HealthResponse model can deserialize
Governor daemon's actual governor.hello response via the RPC client.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_health_returns_valid_response(client):
    """governor.hello deserializes into HealthResponse without error."""
    health = await client.health()
    assert health.status in ("ok", "degraded")


async def test_health_has_all_required_fields(client):
    """HealthResponse contains backend and governor sub-objects."""
    health = await client.health()
    # BackendInfo
    assert isinstance(health.backend.type, str)
    assert isinstance(health.backend.connected, bool)
    # GovernorInfo
    assert isinstance(health.governor.context_id, str)
    assert isinstance(health.governor.mode, str)
    assert isinstance(health.governor.initialized, bool)


async def test_health_degraded_without_backend(client):
    """Without a reachable chat backend, governor reports degraded."""
    health = await client.health()
    # Daemon with unreachable ollama → backend not connected
    assert health.backend.connected is False
