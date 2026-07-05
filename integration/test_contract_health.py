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


async def test_health_backend_connected_field_is_bool(client):
    """backend.connected is a bool regardless of whether the backend is reachable.

    In the docker-compose contract setup (BACKEND_TYPE=ollama,
    OLLAMA_URL=http://nowhere:11434) the daemon reports connected=False because
    ollama is intentionally unreachable.  On developer machines with Claude
    CLI authenticated the field is True.  The contract pin is the type, not a
    specific value — the field must be present and boolean.
    """
    health = await client.health()
    assert isinstance(health.backend.connected, bool)
