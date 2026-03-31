# SPDX-License-Identifier: Apache-2.0
"""Tests for override accumulation / exception pressure (Δr→Δw detection)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from governor.overrides import (
    OverrideReceipt,
    PressureRecord,
    compute_pressure,
)


def _make_override(
    anchor_id: str = "no-eval",
    scope: list[str] | None = None,
    operator: str = "jbeck",
    hours_ago: float = 1.0,
    duration_hours: float = 2.0,
    revoked: bool = False,
) -> OverrideReceipt:
    now = datetime.now(timezone.utc)
    created = now - timedelta(hours=hours_ago)
    expires = created + timedelta(hours=duration_hours)
    return OverrideReceipt(
        id="",
        anchor_id=anchor_id,
        reason="test",
        operator=operator,
        scope=scope or ["src/**"],
        created_at=created.isoformat(),
        expires_at=expires.isoformat(),
        violation_snapshot={},
        revoked=revoked,
    )


class TestComputePressure:
    def test_empty_returns_empty(self):
        assert compute_pressure([]) == []

    def test_single_override_is_low(self):
        records = compute_pressure([_make_override()])
        assert len(records) == 1
        assert records[0].pressure == "low"
        assert records[0].override_count == 1

    def test_three_active_overrides_is_medium(self):
        # All still active (not expired) → renewal_rate is low → medium
        overrides = [_make_override(hours_ago=0.5, duration_hours=4) for _ in range(3)]
        records = compute_pressure(overrides)
        assert len(records) == 1
        assert records[0].pressure == "medium"
        assert records[0].override_count == 3

    def test_three_expired_overrides_is_high(self):
        # All expired → high renewal rate → high pressure
        overrides = [_make_override(hours_ago=i, duration_hours=0.1) for i in range(1, 4)]
        records = compute_pressure(overrides)
        assert len(records) == 1
        assert records[0].pressure == "high"

    def test_six_overrides_is_high(self):
        overrides = [_make_override(hours_ago=i) for i in range(1, 7)]
        records = compute_pressure(overrides)
        assert len(records) == 1
        assert records[0].pressure == "high"
        assert records[0].override_count == 6

    def test_high_renewal_rate_is_high(self):
        # 3 overrides, all expired (duration_hours=0.1, hours_ago=2+)
        overrides = [
            _make_override(hours_ago=h, duration_hours=0.1)
            for h in [48, 24, 12]
        ]
        records = compute_pressure(overrides)
        assert len(records) == 1
        assert records[0].pressure == "high"
        assert records[0].renewal_rate > 0.5

    def test_different_anchors_separate(self):
        overrides = [
            _make_override(anchor_id="no-eval"),
            _make_override(anchor_id="no-force-push"),
        ]
        records = compute_pressure(overrides)
        assert len(records) == 2
        anchors = {r.anchor_id for r in records}
        assert anchors == {"no-eval", "no-force-push"}

    def test_different_scopes_separate(self):
        overrides = [
            _make_override(scope=["src/**"]),
            _make_override(scope=["tests/**"]),
        ]
        records = compute_pressure(overrides)
        assert len(records) == 2

    def test_same_scope_different_order_groups(self):
        overrides = [
            _make_override(scope=["src/**", "lib/**"]),
            _make_override(scope=["lib/**", "src/**"]),
        ]
        records = compute_pressure(overrides)
        # Should group together (normalized scope)
        assert len(records) == 1
        assert records[0].override_count == 2

    def test_outside_window_excluded(self):
        overrides = [
            _make_override(hours_ago=24 * 10),  # 10 days ago
        ]
        records = compute_pressure(overrides, window_days=7)
        assert len(records) == 0

    def test_unique_operators_tracked(self):
        overrides = [
            _make_override(operator="alice"),
            _make_override(operator="bob"),
            _make_override(operator="alice"),
        ]
        records = compute_pressure(overrides)
        assert records[0].unique_operators == 2

    def test_multiple_sessions_triggers_medium(self):
        # 3 active overrides from different times → 3 sessions → medium
        overrides = [
            _make_override(hours_ago=1, duration_hours=100),
            _make_override(hours_ago=24, duration_hours=100),
            _make_override(hours_ago=48, duration_hours=100),
        ]
        records = compute_pressure(overrides, medium_sessions=3)
        assert records[0].pressure == "medium"

    def test_custom_thresholds(self):
        overrides = [_make_override(hours_ago=i) for i in range(1, 3)]
        # Default: 2 = low. With medium_count=2: medium.
        records = compute_pressure(overrides, medium_count=2)
        assert records[0].pressure == "medium"

    def test_revoked_overrides_still_count(self):
        # Revoked = expired for pressure purposes → high renewal rate → high
        overrides = [
            _make_override(revoked=True),
            _make_override(revoked=True),
            _make_override(revoked=True),
        ]
        records = compute_pressure(overrides)
        assert records[0].override_count == 3
        assert records[0].pressure == "high"  # all expired/revoked → high renewal rate

    def test_pressure_record_is_frozen(self):
        records = compute_pressure([_make_override()])
        with pytest.raises(AttributeError):
            records[0].pressure = "high"  # type: ignore[misc]

    def test_window_days_in_record(self):
        records = compute_pressure([_make_override()], window_days=14)
        assert records[0].window_days == 14


class TestOverrideManagerPressure:
    def test_pressure_method_exists(self, tmp_path):
        from governor.overrides import OverrideManager

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        mgr = OverrideManager(gov_dir=gov_dir)

        # Create a few overrides
        mgr.create(
            anchor_id="no-eval",
            reason="testing",
            operator="jbeck",
            scope=["src/**"],
            expires_duration="2h",
        )
        mgr.create(
            anchor_id="no-eval",
            reason="still testing",
            operator="jbeck",
            scope=["src/**"],
            expires_duration="2h",
        )

        records = mgr.pressure()
        assert len(records) == 1
        assert records[0].anchor_id == "no-eval"
        assert records[0].override_count == 2
