# SPDX-License-Identifier: Apache-2.0
"""Tests for Code Autopilot override mechanism."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from governor.overrides import (
    OverrideReceipt,
    OverrideManager,
    parse_duration,
    create_override_manager,
    check_override,
)
from governor.continuity import Violation, AnchorType, Severity


class TestParseDuration:
    """Tests for duration parsing."""

    def test_parse_minutes(self):
        """Test parsing minutes."""
        delta = parse_duration("30m")
        assert delta == timedelta(minutes=30)

    def test_parse_hours(self):
        """Test parsing hours."""
        delta = parse_duration("2h")
        assert delta == timedelta(hours=2)

    def test_parse_days(self):
        """Test parsing days."""
        delta = parse_duration("1d")
        assert delta == timedelta(days=1)

    def test_parse_combined(self):
        """Test parsing combined duration."""
        delta = parse_duration("2h30m")
        assert delta == timedelta(hours=2, minutes=30)

    def test_parse_number_as_hours(self):
        """Test parsing bare number as hours."""
        delta = parse_duration("3")
        assert delta == timedelta(hours=3)

    def test_parse_invalid(self):
        """Test parsing invalid duration."""
        with pytest.raises(ValueError):
            parse_duration("invalid")


class TestOverrideReceipt:
    """Tests for OverrideReceipt dataclass."""

    def test_creation(self):
        """Test override receipt creation."""
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        receipt = OverrideReceipt(
            id="test123",
            anchor_id="no-sql-injection",
            reason="Legacy migration",
            operator="jbeck",
            scope=["migrations/**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=future,
            violation_snapshot={},
        )
        assert receipt.id == "test123"
        assert receipt.anchor_id == "no-sql-injection"
        assert not receipt.revoked

    def test_auto_id_generation(self):
        """Test auto ID generation when empty."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        receipt = OverrideReceipt(
            id="",
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["**"],
            created_at="",
            expires_at=future,
            violation_snapshot={},
        )
        assert receipt.id  # Should be auto-generated
        assert receipt.created_at  # Should be auto-set

    def test_is_expired_false(self):
        """Test is_expired when not expired."""
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        receipt = OverrideReceipt(
            id="test",
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=future,
            violation_snapshot={},
        )
        assert not receipt.is_expired

    def test_is_expired_true(self):
        """Test is_expired when expired."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        receipt = OverrideReceipt(
            id="test",
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=past,
            violation_snapshot={},
        )
        assert receipt.is_expired

    def test_is_expired_when_revoked(self):
        """Test is_expired returns True when revoked."""
        future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        receipt = OverrideReceipt(
            id="test",
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=future,
            violation_snapshot={},
            revoked=True,
        )
        assert receipt.is_expired

    def test_remaining_minutes(self):
        """Test remaining_minutes calculation."""
        future = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
        receipt = OverrideReceipt(
            id="test",
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=future,
            violation_snapshot={},
        )
        remaining = receipt.remaining_minutes
        assert 40 <= remaining <= 45

    def test_is_valid_for_matching_path(self):
        """Test is_valid_for with matching path."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        receipt = OverrideReceipt(
            id="test",
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["src/**", "tests/**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=future,
            violation_snapshot={},
        )
        assert receipt.is_valid_for("src/api.py")
        assert receipt.is_valid_for("tests/test_api.py")
        assert not receipt.is_valid_for("docs/readme.md")

    def test_is_valid_for_expired(self):
        """Test is_valid_for when expired."""
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        receipt = OverrideReceipt(
            id="test",
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["src/**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=past,
            violation_snapshot={},
        )
        assert not receipt.is_valid_for("src/api.py")

    def test_to_dict(self):
        """Test serialization."""
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        receipt = OverrideReceipt(
            id="test123",
            anchor_id="no-sql",
            reason="Legacy code",
            operator="jbeck",
            scope=["migrations/**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=future,
            violation_snapshot={"description": "test violation"},
        )
        d = receipt.to_dict()
        assert d["id"] == "test123"
        assert d["anchor_id"] == "no-sql"
        assert d["scope"] == ["migrations/**"]
        assert d["violation_snapshot"]["description"] == "test violation"

    def test_from_dict(self):
        """Test deserialization."""
        d = {
            "id": "abc123",
            "anchor_id": "no-eval",
            "reason": "Testing",
            "operator": "test",
            "scope": ["test/**"],
            "created_at": "2025-01-01T00:00:00+00:00",
            "expires_at": "2025-01-01T02:00:00+00:00",
            "violation_snapshot": {},
        }
        receipt = OverrideReceipt.from_dict(d)
        assert receipt.id == "abc123"
        assert receipt.anchor_id == "no-eval"

    def test_to_status_string(self):
        """Test status string formatting."""
        future = (datetime.now(timezone.utc) + timedelta(minutes=90)).isoformat()
        receipt = OverrideReceipt(
            id="abc",
            anchor_id="no-sql",
            reason="test",
            operator="test",
            scope=["src/**"],
            created_at=datetime.now(timezone.utc).isoformat(),
            expires_at=future,
            violation_snapshot={},
        )
        status = receipt.to_status_string()
        assert "abc" in status
        assert "no-sql" in status
        assert "1h" in status or "m" in status


class TestOverrideManager:
    """Tests for OverrideManager."""

    def test_create_override(self, tmp_path):
        """Test creating an override."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)
        receipt = manager.create(
            anchor_id="no-sql",
            reason="Legacy migration",
            operator="test",
            scope=["migrations/**"],
            expires_duration="2h",
        )

        assert receipt.id
        assert receipt.anchor_id == "no-sql"
        assert receipt.remaining_minutes > 0

    def test_get_override(self, tmp_path):
        """Test getting an override by ID."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)
        created = manager.create(
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )

        retrieved = manager.get(created.id)
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_override_not_found(self, tmp_path):
        """Test getting non-existent override."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)
        assert manager.get("nonexistent") is None

    def test_list_active(self, tmp_path):
        """Test listing active overrides."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)

        # Create active override
        manager.create(
            anchor_id="active",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )

        active = manager.list_active()
        assert len(active) == 1
        assert active[0].anchor_id == "active"

    def test_list_all(self, tmp_path):
        """Test listing all overrides."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)
        manager.create(
            anchor_id="one",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )
        manager.create(
            anchor_id="two",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )

        all_overrides = manager.list_all()
        assert len(all_overrides) == 2

    def test_revoke(self, tmp_path):
        """Test revoking an override."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)
        receipt = manager.create(
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )

        assert manager.revoke(receipt.id, "Fixed the issue")

        # Should now be expired (revoked)
        retrieved = manager.get(receipt.id)
        assert retrieved.revoked
        assert retrieved.is_expired

    def test_revoke_not_found(self, tmp_path):
        """Test revoking non-existent override."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)
        assert not manager.revoke("nonexistent", "reason")

    def test_check_active_override(self, tmp_path):
        """Test checking for active override."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)
        manager.create(
            anchor_id="no-sql",
            reason="test",
            operator="test",
            scope=["migrations/**"],
            expires_hours=1,
        )

        # Should find override
        found = manager.check("no-sql", "migrations/001.py")
        assert found is not None
        assert found.anchor_id == "no-sql"

        # Should not find for different path
        not_found = manager.check("no-sql", "src/api.py")
        assert not_found is None

        # Should not find for different anchor
        not_found = manager.check("other-anchor", "migrations/001.py")
        assert not_found is None

    def test_cleanup_expired(self, tmp_path):
        """Test cleaning up expired overrides."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)

        # Create and immediately revoke
        receipt = manager.create(
            anchor_id="test",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )
        manager.revoke(receipt.id, "done")

        # Cleanup should remove it
        count = manager.cleanup_expired()
        assert count == 1

        # Should be gone
        assert manager.get(receipt.id) is None

    def test_persistence(self, tmp_path):
        """Test override persistence across manager instances."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create with first manager
        manager1 = OverrideManager(gov_dir=gov_dir)
        receipt = manager1.create(
            anchor_id="persistent",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )

        # Load with second manager
        manager2 = OverrideManager(gov_dir=gov_dir)
        loaded = manager2.get(receipt.id)

        assert loaded is not None
        assert loaded.anchor_id == "persistent"

    def test_list_for_anchor(self, tmp_path):
        """Test listing overrides for specific anchor."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = OverrideManager(gov_dir=gov_dir)
        manager.create(
            anchor_id="anchor-a",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )
        manager.create(
            anchor_id="anchor-b",
            reason="test",
            operator="test",
            scope=["**"],
            expires_hours=1,
        )
        manager.create(
            anchor_id="anchor-a",
            reason="another",
            operator="test",
            scope=["src/**"],
            expires_hours=2,
        )

        anchor_a_overrides = manager.list_for_anchor("anchor-a")
        assert len(anchor_a_overrides) == 2

        anchor_b_overrides = manager.list_for_anchor("anchor-b")
        assert len(anchor_b_overrides) == 1


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_override_manager(self, tmp_path):
        """Test factory function."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        manager = create_override_manager(gov_dir)
        assert isinstance(manager, OverrideManager)

    def test_check_override_function(self, tmp_path):
        """Test one-shot check function."""
        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        # Create an override first
        manager = OverrideManager(gov_dir=gov_dir)
        manager.create(
            anchor_id="test-anchor",
            reason="test",
            operator="test",
            scope=["src/**"],
            expires_hours=1,
        )

        # Use convenience function
        found = check_override(gov_dir, "test-anchor", "src/api.py")
        assert found is not None

        not_found = check_override(gov_dir, "test-anchor", "docs/readme.md")
        assert not_found is None
