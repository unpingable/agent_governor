"""Contract tests for v2 dashboard endpoints.

Verifies that Maude's DashboardSummary and RunSummary models can
deserialize Governor's actual /v2/ responses.  All backend-free.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


# -- /v2/dashboard/summary --------------------------------------------------

async def test_dashboard_summary_valid(client):
    """GET /v2/dashboard/summary deserializes into DashboardSummary."""
    summary = await client.dashboard_summary()
    assert isinstance(summary.total_runs, int)
    assert isinstance(summary.pass_rate, float)


async def test_dashboard_summary_fields(client):
    """DashboardSummary has all expected numeric fields."""
    summary = await client.dashboard_summary()
    for field in ("total_runs", "passed", "failed", "cancelled",
                  "total_claims", "total_violations"):
        assert isinstance(getattr(summary, field), int), f"{field} should be int"
    assert isinstance(summary.pass_rate, float)
    # active_run is Optional[str]
    assert summary.active_run is None or isinstance(summary.active_run, str)


async def test_dashboard_summary_zero_on_fresh_instance(client):
    """Fresh governor has no runs — all counters zero."""
    summary = await client.dashboard_summary()
    assert summary.total_runs == 0
    assert summary.passed == 0
    assert summary.failed == 0


# -- /v2/runs ----------------------------------------------------------------

async def test_list_runs_empty(client):
    """GET /v2/runs returns an empty list on a fresh instance."""
    runs = await client.list_runs()
    assert isinstance(runs, list)
    assert len(runs) == 0


async def test_list_runs_returns_run_summaries(client):
    """After creating a run, list_runs returns RunSummary objects."""
    # Create a run via the raw API (client.create_run returns dict)
    result = await client.create_run(task="contract-test-task", profile="greenfield")
    assert "run_id" in result

    runs = await client.list_runs()
    assert len(runs) >= 1
    run = next(r for r in runs if r.run_id == result["run_id"])
    assert run.task == "contract-test-task"
    assert run.profile == "greenfield"
    assert isinstance(run.claim_count, int)
    assert isinstance(run.violation_count, int)


async def test_run_summary_verdict_is_string(client):
    """RunSummary.verdict is a string (e.g. 'pending')."""
    result = await client.create_run(task="verdict-check")
    runs = await client.list_runs()
    run = next(r for r in runs if r.run_id == result["run_id"])
    assert isinstance(run.verdict, str)
    assert run.verdict  # not empty
