# SPDX-License-Identifier: Apache-2.0
"""Contract tests for governor.now and governor.status RPC methods.

Verifies that Maude's GovernorNow model can deserialize Governor
daemon's actual responses, and that status returns a valid dict.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_governor_now_valid(client):
    """governor.now deserializes into GovernorNow without error."""
    now = await client.governor_now()
    assert now.sentence
    assert now.mode


async def test_governor_now_required_fields(client):
    """GovernorNow has all required fields with correct types."""
    now = await client.governor_now()
    assert isinstance(now.status, str)
    assert isinstance(now.sentence, str)
    assert isinstance(now.mode, str)


async def test_governor_now_status_values(client):
    """status is one of the pill values from the daemon."""
    now = await client.governor_now()
    assert now.status in ("OK", "BLOCK", "DRIFT", "UNKNOWN")


async def test_governor_status_returns_dict(client):
    """governor.status returns a dict."""
    status = await client.governor_status()
    assert isinstance(status, dict)
