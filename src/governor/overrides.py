# SPDX-License-Identifier: Apache-2.0
"""
Override mechanism for Code Autopilot.

Overrides provide scoped, expiring, receipted exceptions to invariant constraints.
Unlike profile changes (which affect all constraints), overrides:
- Are scoped: only apply to declared paths
- Are expiring: must have a timebox
- Are receipted: logged with full context
- Are not deletions: the invariant still exists, violation is still recorded

This allows emergency bypasses while maintaining audit trail and temporal bounds.

Storage: .governor/overrides/<id>.json (one file per override)
"""

from __future__ import annotations

import fnmatch
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .continuity import Violation


# =============================================================================
# Override Receipt
# =============================================================================


@dataclass
class OverrideReceipt:
    """
    A receipted exception to an invariant constraint.

    Overrides are:
    - Scoped: only apply to paths matching the scope patterns
    - Expiring: have an explicit expiry time
    - Receipted: logged with full context including violation snapshot
    """

    id: str
    anchor_id: str
    reason: str
    operator: str
    scope: list[str]              # glob patterns for covered paths
    created_at: str               # ISO datetime
    expires_at: str               # ISO datetime
    violation_snapshot: dict[str, Any]  # snapshot of violation at time of override
    revoked: bool = False
    revoked_at: str | None = None
    revoked_reason: str | None = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    @property
    def is_expired(self) -> bool:
        """Check if this override has expired."""
        if self.revoked:
            return True
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expires
        except (ValueError, TypeError):
            return True  # Invalid expiry = expired

    @property
    def remaining_minutes(self) -> int:
        """Get remaining minutes, or 0 if expired."""
        if self.is_expired:
            return 0
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            delta = expires - datetime.now(timezone.utc)
            if delta.total_seconds() <= 0:
                return 0
            return int(delta.total_seconds() / 60)
        except (ValueError, TypeError):
            return 0

    def is_valid_for(self, path: str) -> bool:
        """Check if override covers this path and hasn't expired."""
        if self.is_expired:
            return False
        for pattern in self.scope:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "anchor_id": self.anchor_id,
            "reason": self.reason,
            "operator": self.operator,
            "scope": self.scope,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "violation_snapshot": self.violation_snapshot,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at,
            "revoked_reason": self.revoked_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OverrideReceipt:
        return cls(
            id=data.get("id", ""),
            anchor_id=data["anchor_id"],
            reason=data["reason"],
            operator=data.get("operator", "unknown"),
            scope=data.get("scope", []),
            created_at=data.get("created_at", ""),
            expires_at=data["expires_at"],
            violation_snapshot=data.get("violation_snapshot", {}),
            revoked=data.get("revoked", False),
            revoked_at=data.get("revoked_at"),
            revoked_reason=data.get("revoked_reason"),
        )

    def to_status_string(self) -> str:
        """Format for status display."""
        if self.revoked:
            return f"{self.id} | {self.anchor_id} | REVOKED"
        if self.is_expired:
            return f"{self.id} | {self.anchor_id} | EXPIRED"
        remaining = self.remaining_minutes
        if remaining < 60:
            time_str = f"{remaining}m"
        else:
            hours = remaining // 60
            mins = remaining % 60
            time_str = f"{hours}h{mins}m" if mins else f"{hours}h"
        return f"{self.id} | {self.anchor_id} | {time_str} | {', '.join(self.scope)}"


# =============================================================================
# Override Manager
# =============================================================================


def parse_duration(duration_str: str) -> timedelta:
    """
    Parse duration string like '2h', '90m', '1d' into timedelta.

    Supported formats:
    - '30m' -> 30 minutes
    - '2h' -> 2 hours
    - '1d' -> 1 day
    - '2h30m' -> 2 hours 30 minutes
    """
    import re

    total = timedelta()

    # Days
    days_match = re.search(r'(\d+)d', duration_str)
    if days_match:
        total += timedelta(days=int(days_match.group(1)))

    # Hours
    hours_match = re.search(r'(\d+)h', duration_str)
    if hours_match:
        total += timedelta(hours=int(hours_match.group(1)))

    # Minutes
    mins_match = re.search(r'(\d+)m', duration_str)
    if mins_match:
        total += timedelta(minutes=int(mins_match.group(1)))

    # If no matches and it's a number, treat as hours
    if total == timedelta():
        try:
            hours = float(duration_str)
            total = timedelta(hours=hours)
        except ValueError:
            raise ValueError(f"Invalid duration format: {duration_str}")

    return total


@dataclass
class OverrideManager:
    """
    Manages scoped overrides for invariant constraints.

    Overrides are stored as individual JSON files in .governor/overrides/.
    """

    gov_dir: Path
    _overrides: dict[str, OverrideReceipt] = field(default_factory=dict)

    def __post_init__(self):
        self._overrides_dir.mkdir(parents=True, exist_ok=True)
        self._load_overrides()

    @property
    def _overrides_dir(self) -> Path:
        return self.gov_dir / "overrides"

    def _load_overrides(self) -> None:
        """Load all overrides from disk."""
        self._overrides.clear()
        if not self._overrides_dir.exists():
            return

        for path in self._overrides_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                override = OverrideReceipt.from_dict(data)
                self._overrides[override.id] = override
            except (json.JSONDecodeError, KeyError):
                continue

    def _save_override(self, override: OverrideReceipt) -> None:
        """Save a single override to disk."""
        path = self._overrides_dir / f"{override.id}.json"
        path.write_text(json.dumps(override.to_dict(), indent=2))

    def _delete_override_file(self, override_id: str) -> None:
        """Delete an override file from disk."""
        path = self._overrides_dir / f"{override_id}.json"
        if path.exists():
            path.unlink()

    def create(
        self,
        anchor_id: str,
        reason: str,
        operator: str,
        scope: list[str],
        expires_hours: float | None = None,
        expires_duration: str | None = None,
        violation: Violation | None = None,
    ) -> OverrideReceipt:
        """
        Create a new override receipt.

        Args:
            anchor_id: ID of the anchor being overridden
            reason: Why this override is needed
            operator: Who created the override
            scope: Glob patterns for paths covered by override
            expires_hours: Hours until expiry (deprecated, use expires_duration)
            expires_duration: Duration string like '2h', '90m', '1d'
            violation: Optional violation snapshot

        Returns:
            The created OverrideReceipt
        """
        # Calculate expiry
        now = datetime.now(timezone.utc)
        if expires_duration:
            delta = parse_duration(expires_duration)
        elif expires_hours:
            delta = timedelta(hours=expires_hours)
        else:
            # Default to 2 hours
            delta = timedelta(hours=2)

        expires_at = (now + delta).isoformat()

        # Create override
        override = OverrideReceipt(
            id="",  # Will be auto-generated
            anchor_id=anchor_id,
            reason=reason,
            operator=operator,
            scope=scope,
            created_at=now.isoformat(),
            expires_at=expires_at,
            violation_snapshot=violation.to_dict() if violation else {},
        )

        self._overrides[override.id] = override
        self._save_override(override)

        return override

    def get(self, override_id: str) -> OverrideReceipt | None:
        """Get an override by ID."""
        return self._overrides.get(override_id)

    def list_all(self) -> list[OverrideReceipt]:
        """List all overrides (including expired/revoked)."""
        return list(self._overrides.values())

    def list_active(self) -> list[OverrideReceipt]:
        """List only active (non-expired, non-revoked) overrides."""
        return [o for o in self._overrides.values() if not o.is_expired]

    def list_for_anchor(self, anchor_id: str) -> list[OverrideReceipt]:
        """List overrides for a specific anchor."""
        return [o for o in self._overrides.values() if o.anchor_id == anchor_id]

    def revoke(self, override_id: str, reason: str) -> bool:
        """
        Revoke an override early.

        Returns True if revoked, False if not found.
        """
        override = self._overrides.get(override_id)
        if not override:
            return False

        override.revoked = True
        override.revoked_at = datetime.now(timezone.utc).isoformat()
        override.revoked_reason = reason
        self._save_override(override)

        return True

    def check(self, anchor_id: str, path: str) -> OverrideReceipt | None:
        """
        Check if there's an active override for this anchor+path.

        Returns the override if found and valid, None otherwise.
        """
        for override in self._overrides.values():
            if override.anchor_id == anchor_id and override.is_valid_for(path):
                return override
        return None

    def pressure(self, **kwargs) -> list[PressureRecord]:
        """Compute exception pressure across all overrides."""
        return compute_pressure(list(self._overrides.values()), **kwargs)

    def cleanup_expired(self) -> int:
        """
        Remove expired override files from disk.

        Returns count of removed files.
        """
        count = 0
        for override_id, override in list(self._overrides.items()):
            if override.is_expired:
                self._delete_override_file(override_id)
                del self._overrides[override_id]
                count += 1
        return count


# =============================================================================
# Exception Pressure (Δr→Δw detection)
# =============================================================================


@dataclass(frozen=True)
class PressureRecord:
    """Override accumulation pressure for a (scope_key, anchor_id) pair."""

    scope_key: str      # normalized scope (sorted, joined)
    anchor_id: str
    override_count: int
    unique_sessions: int
    unique_operators: int
    renewal_rate: float  # fraction of overrides that were renewed (0.0-1.0)
    pressure: str        # "low", "medium", "high"
    window_days: int


def _normalize_scope(scope: list[str]) -> str:
    """Canonical scope key for grouping."""
    return "|".join(sorted(scope))


def compute_pressure(
    overrides: list[OverrideReceipt],
    window_days: int = 7,
    medium_count: int = 3,
    medium_sessions: int = 3,
    high_count: int = 6,
    high_renewal_rate: float = 0.5,
) -> list[PressureRecord]:
    """Compute exception pressure per (scope, anchor) from override history.

    Thresholds:
    - low: count <= medium_count - 1 and sessions < medium_sessions
    - medium: count >= medium_count, or sessions >= medium_sessions
    - high: count >= high_count, or renewal_rate > high_renewal_rate
    """
    from collections import defaultdict

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)

    # Filter to window (include expired/revoked — they still count as override events)
    in_window: list[OverrideReceipt] = []
    for o in overrides:
        try:
            created = datetime.fromisoformat(o.created_at.replace("Z", "+00:00"))
            if created >= cutoff:
                in_window.append(o)
        except (ValueError, TypeError):
            continue

    # Group by (scope_key, anchor_id)
    groups: dict[tuple[str, str], list[OverrideReceipt]] = defaultdict(list)
    for o in in_window:
        key = (_normalize_scope(o.scope), o.anchor_id)
        groups[key].append(o)

    records: list[PressureRecord] = []
    for (scope_key, anchor_id), group in sorted(groups.items()):
        count = len(group)
        sessions = len({getattr(o, "session_id", None) or o.created_at for o in group})
        operators = len({o.operator for o in group})

        # Renewal rate: fraction that expired and were followed by another override
        # for the same scope+anchor (approximation: count > 1 and most are expired)
        expired_count = sum(1 for o in group if o.is_expired)
        renewal_rate = expired_count / count if count > 1 else 0.0

        if count >= high_count or (count > 1 and renewal_rate > high_renewal_rate):
            pressure = "high"
        elif count >= medium_count or sessions >= medium_sessions:
            pressure = "medium"
        else:
            pressure = "low"

        records.append(PressureRecord(
            scope_key=scope_key,
            anchor_id=anchor_id,
            override_count=count,
            unique_sessions=sessions,
            unique_operators=operators,
            renewal_rate=round(renewal_rate, 2),
            pressure=pressure,
            window_days=window_days,
        ))

    return records


# =============================================================================
# Convenience functions
# =============================================================================


def create_override_manager(gov_dir: Path) -> OverrideManager:
    """Create an OverrideManager for the given governor directory."""
    return OverrideManager(gov_dir=gov_dir)


def check_override(
    gov_dir: Path,
    anchor_id: str,
    path: str,
) -> OverrideReceipt | None:
    """
    One-shot convenience: check if there's an active override.

    Returns the override if found and valid, None otherwise.
    """
    manager = OverrideManager(gov_dir=gov_dir)
    return manager.check(anchor_id, path)
