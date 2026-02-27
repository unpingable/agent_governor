# SPDX-License-Identifier: Apache-2.0
"""
Process-scoped session identity for signal/receipt correlation.

This is NOT a session lifecycle manager (see session_continuity.py for that).
It's a single, stable correlation ID per process, suitable for threading
through signals, gate receipts, and RPC calls so you can answer "what
happened during this daemon run / CLI invocation?"

Design:
  - One session_id per process, generated on first access (lazy)
  - Format: "gov_{uuid_hex[:12]}" — short enough to be human-friendly
  - Callers can override with an explicit ID (library usage)
  - The daemon holds one for its lifetime; CLI gets a fresh one per command
"""

from __future__ import annotations

import uuid

_process_session_id: str | None = None


def get_session_id() -> str:
    """Return the process-scoped session ID, generating on first call.

    Stable within a single process. Not persisted — intentionally
    ephemeral. Use session_continuity.py for durable sessions.
    """
    global _process_session_id
    if _process_session_id is None:
        _process_session_id = f"gov_{uuid.uuid4().hex[:12]}"
    return _process_session_id


def set_session_id(session_id: str) -> None:
    """Override the process session ID. Call early (e.g. daemon startup).

    Allows callers to pin a known ID for testing or for bridging
    to an existing session_continuity capsule.
    """
    global _process_session_id
    _process_session_id = session_id


def new_session_id() -> str:
    """Generate a fresh session ID without setting the process global.

    Useful for CLI commands that want per-invocation IDs without
    affecting other callers in the same process (e.g. tests).
    """
    return f"gov_{uuid.uuid4().hex[:12]}"
