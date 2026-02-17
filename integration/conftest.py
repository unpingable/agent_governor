# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures for Maude <-> Governor daemon contract tests."""

from __future__ import annotations

import asyncio
import os
import time

import pytest_asyncio


GOVERNOR_SOCKET = os.environ.get("GOVERNOR_SOCKET", "/run/governor.sock")


@pytest_asyncio.fixture(scope="session")
async def wait_for_governor():
    """Block until the governor daemon socket is connectable (max 30s)."""
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            reader, writer = await asyncio.open_unix_connection(GOVERNOR_SOCKET)
            writer.close()
            await writer.wait_closed()
            return
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            pass
        await asyncio.sleep(0.5)
    raise RuntimeError(f"Governor socket at {GOVERNOR_SOCKET} not connectable in 30s")


@pytest_asyncio.fixture
async def client(wait_for_governor):
    """Yield a GovernorClient connected to the live governor daemon."""
    from maude.client.rpc import GovernorClient

    c = GovernorClient(socket_path=GOVERNOR_SOCKET)
    await c.connect()
    yield c
    await c.close()
