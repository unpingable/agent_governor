# SPDX-License-Identifier: Apache-2.0
"""
Gate heartbeat: detect when the evidence gate stops being called.

The governor can be silenced without being captured.  If the evidence gate
stops firing, all indicators read "normal" because nothing is measured —
the "dead thermometer" failure.

This module provides the smoke alarm: a missed-heartbeat model that reads
the gate receipt log and computes how many expected intervals have been
missed since the last receipt.

Phase 1 — on-demand only, no background timer, no starvation detection.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# =============================================================================
# Configuration
# =============================================================================


@dataclass(frozen=True)
class HeartbeatConfig:
    """Tuning knobs for the missed-heartbeat model.

    expected_interval_seconds: how often we expect the gate to fire during
        an active session (default 5 min).
    grace_period_seconds: timing jitter tolerance before counting a miss.
    stale_after_missed: how many consecutive missed intervals trigger stale.
    """

    expected_interval_seconds: float = 300.0  # 5 min
    grace_period_seconds: float = 60.0
    stale_after_missed: int = 3


# =============================================================================
# Status
# =============================================================================


@dataclass(frozen=True)
class HeartbeatStatus:
    """Result of a heartbeat check.

    last_check_timestamp: ISO 8601 UTC of the most recent gate receipt,
        or None if no receipts exist.
    seconds_since_last: elapsed seconds since last receipt, or None.
    expected_interval: the configured interval (echoed for consumers).
    missed_count: max(0, floor((elapsed - grace) / interval)).
    is_stale: True when missed >= threshold AND session is active.
    is_session_active: threaded through from caller.
    gate: gate name from the most recent receipt, or None.
    """

    last_check_timestamp: str | None
    seconds_since_last: float | None
    expected_interval: float
    missed_count: int
    is_stale: bool
    is_session_active: bool
    gate: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_check_timestamp": self.last_check_timestamp,
            "seconds_since_last": self.seconds_since_last,
            "expected_interval": self.expected_interval,
            "missed_count": self.missed_count,
            "is_stale": self.is_stale,
            "is_session_active": self.is_session_active,
            "gate": self.gate,
        }


# =============================================================================
# Core logic
# =============================================================================


def _most_recent_receipt(gov_dir: Path) -> tuple[str, str] | None:
    """Return (timestamp, gate) of the newest gate receipt, or None.

    Reads the JSONL receipt log and returns the last line's timestamp and
    gate name.  Avoids loading the full ReceiptStore to keep this module
    lightweight.
    """
    receipt_path = gov_dir / "receipts" / "gate_receipts.jsonl"
    if not receipt_path.exists():
        return None

    # Read lines in reverse to find the last non-empty line
    last_line: str | None = None
    try:
        text = receipt_path.read_text()
    except OSError:
        return None

    for line in reversed(text.splitlines()):
        line = line.strip()
        if line:
            last_line = line
            break

    if last_line is None:
        return None

    try:
        data = json.loads(last_line)
        return (data["timestamp"], data["gate"])
    except (json.JSONDecodeError, KeyError):
        return None


def _compute_missed(
    elapsed: float,
    grace: float,
    interval: float,
) -> int:
    """Missed heartbeat count: max(0, floor((elapsed - grace) / interval))."""
    if interval <= 0:
        return 0
    effective = elapsed - grace
    if effective <= 0:
        return 0
    return max(0, math.floor(effective / interval))


def gate_heartbeat(
    gov_dir: Path,
    *,
    config: HeartbeatConfig | None = None,
    now: datetime | None = None,
    session_active: bool = True,
) -> HeartbeatStatus:
    """Check the evidence gate heartbeat.

    Args:
        gov_dir: Path to the .governor/ directory.
        config: Override default tuning. None = defaults.
        now: Deterministic time injection (must be UTC-aware).
            None = wall clock (for CLI use only).
        session_active: Whether a session is currently active.
            Caller provides this; default True is conservative.

    Returns:
        HeartbeatStatus with missed count and staleness.
    """
    if config is None:
        config = HeartbeatConfig()

    if now is None:
        now = datetime.now(timezone.utc)

    recent = _most_recent_receipt(gov_dir)

    if recent is None:
        # No receipts at all — first-run, not a failure.
        return HeartbeatStatus(
            last_check_timestamp=None,
            seconds_since_last=None,
            expected_interval=config.expected_interval_seconds,
            missed_count=0,
            is_stale=False,
            is_session_active=session_active,
            gate=None,
        )

    ts_str, gate = recent

    # Parse the receipt timestamp (ISO 8601 UTC)
    try:
        last_ts = datetime.fromisoformat(ts_str)
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        # Unparseable timestamp — treat as no receipts
        return HeartbeatStatus(
            last_check_timestamp=ts_str,
            seconds_since_last=None,
            expected_interval=config.expected_interval_seconds,
            missed_count=0,
            is_stale=False,
            is_session_active=session_active,
            gate=gate,
        )

    elapsed = (now - last_ts).total_seconds()
    missed = _compute_missed(
        elapsed,
        config.grace_period_seconds,
        config.expected_interval_seconds,
    )
    is_stale = session_active and missed >= config.stale_after_missed

    return HeartbeatStatus(
        last_check_timestamp=ts_str,
        seconds_since_last=round(elapsed, 1),
        expected_interval=config.expected_interval_seconds,
        missed_count=missed,
        is_stale=is_stale,
        is_session_active=session_active,
        gate=gate,
    )
