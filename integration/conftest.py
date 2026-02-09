"""Shared fixtures for Maude ↔ Governor contract tests."""

from __future__ import annotations

import asyncio
import os
import time

import httpx
import pytest_asyncio


GOVERNOR_URL = os.environ.get("GOVERNOR_URL", "http://127.0.0.1:8000")


@pytest_asyncio.fixture(scope="session")
async def wait_for_governor():
    """Block until the governor health endpoint responds (max 30s)."""
    deadline = time.monotonic() + 30
    async with httpx.AsyncClient() as c:
        while time.monotonic() < deadline:
            try:
                resp = await c.get(f"{GOVERNOR_URL}/health", timeout=2.0)
                if resp.status_code == 200:
                    return
            except (httpx.ConnectError, httpx.ReadError, httpx.TimeoutException):
                pass
            await asyncio.sleep(0.5)
    raise RuntimeError(f"Governor at {GOVERNOR_URL} did not become healthy in 30s")


@pytest_asyncio.fixture
async def client(wait_for_governor):
    """Yield a GovernorClient connected to the live governor."""
    from maude.client.http import GovernorClient

    c = GovernorClient(base_url=GOVERNOR_URL)
    yield c
    await c.close()
