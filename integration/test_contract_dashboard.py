"""Contract tests for v2 dashboard endpoints.

These endpoints are HTTP-era features that haven't been mapped to
daemon RPC methods yet. The RPC client returns stub/default values.
Tests verify the stubs work without error.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_dashboard_summary_returns_defaults(client):
    """dashboard_summary() returns a DashboardSummary with zero defaults."""
    summary = await client.dashboard_summary()
    assert summary.total_runs == 0
    assert summary.passed == 0
    assert summary.failed == 0


async def test_list_runs_returns_empty(client):
    """list_runs() returns an empty list (stub)."""
    runs = await client.list_runs()
    assert isinstance(runs, list)
    assert len(runs) == 0


async def test_create_run_returns_not_implemented(client):
    """create_run() returns a not_implemented dict (stub)."""
    result = await client.create_run(task="contract-test-task")
    assert result.get("status") == "not_implemented"
