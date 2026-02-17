# SPDX-License-Identifier: Apache-2.0
"""Tests for SQLite storage backend."""

import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from governor.storage import Storage, Lease, get_storage, SCHEMA_VERSION


class TestStorageInit:
    """Tests for storage initialization."""

    def test_creates_database(self, tmp_path):
        """Test that storage creates the database file."""
        db_path = tmp_path / "test.db"
        storage = Storage(db_path)

        assert db_path.exists()
        storage.close()

    def test_creates_parent_directories(self, tmp_path):
        """Test that storage creates parent directories."""
        db_path = tmp_path / "nested" / "path" / "test.db"
        storage = Storage(db_path)

        assert db_path.exists()
        storage.close()

    def test_wal_mode_enabled(self, tmp_path):
        """Test that WAL mode is enabled."""
        db_path = tmp_path / "test.db"
        storage = Storage(db_path)

        cursor = storage.conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]

        assert mode.lower() == "wal"
        storage.close()

    def test_schema_version_set(self, tmp_path):
        """Test that schema version is tracked."""
        db_path = tmp_path / "test.db"
        storage = Storage(db_path)

        cursor = storage.conn.cursor()
        cursor.execute("SELECT version FROM schema_version")
        version = cursor.fetchone()[0]

        assert version == SCHEMA_VERSION
        storage.close()

    def test_creates_all_tables(self, tmp_path):
        """Test that all required tables are created."""
        db_path = tmp_path / "test.db"
        storage = Storage(db_path)

        cursor = storage.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}

        expected = {
            "schema_version",
            "facts",
            "decisions",
            "leases",
            "reservations",
            "epoch_counter",
            "proposals",
            "agents",
            "rejections",
        }
        assert expected.issubset(tables)
        storage.close()


class TestEpochs:
    """Tests for epoch counter."""

    def test_initial_epoch_is_zero(self, tmp_path):
        """Test that initial epoch is 0."""
        storage = Storage(tmp_path / "test.db")

        assert storage.current_epoch() == 0
        storage.close()

    def test_next_epoch_increments(self, tmp_path):
        """Test that next_epoch increments the counter."""
        storage = Storage(tmp_path / "test.db")

        epoch1 = storage.next_epoch()
        epoch2 = storage.next_epoch()
        epoch3 = storage.next_epoch()

        assert epoch1 == 1
        assert epoch2 == 2
        assert epoch3 == 3
        storage.close()

    def test_current_epoch_does_not_increment(self, tmp_path):
        """Test that current_epoch doesn't change the counter."""
        storage = Storage(tmp_path / "test.db")

        storage.next_epoch()  # Set to 1
        current1 = storage.current_epoch()
        current2 = storage.current_epoch()

        assert current1 == 1
        assert current2 == 1
        storage.close()


class TestTransactions:
    """Tests for transaction handling."""

    def test_transaction_commits(self, tmp_path):
        """Test that transactions commit on success."""
        storage = Storage(tmp_path / "test.db")

        with storage.transaction() as cursor:
            cursor.execute(
                "INSERT INTO agents (id, agent_class, registered_at, last_heartbeat) "
                "VALUES (?, ?, ?, ?)",
                ("test-1", "worker", datetime.now(timezone.utc).isoformat(),
                 datetime.now(timezone.utc).isoformat())
            )

        # Verify committed
        cursor = storage.conn.cursor()
        cursor.execute("SELECT id FROM agents WHERE id = ?", ("test-1",))
        assert cursor.fetchone() is not None
        storage.close()

    def test_transaction_rollback_on_error(self, tmp_path):
        """Test that transactions rollback on error."""
        storage = Storage(tmp_path / "test.db")

        try:
            with storage.transaction() as cursor:
                cursor.execute(
                    "INSERT INTO agents (id, agent_class, registered_at, last_heartbeat) "
                    "VALUES (?, ?, ?, ?)",
                    ("test-1", "worker", datetime.now(timezone.utc).isoformat(),
                     datetime.now(timezone.utc).isoformat())
                )
                raise ValueError("Simulated error")
        except ValueError:
            pass

        # Verify rolled back
        cursor = storage.conn.cursor()
        cursor.execute("SELECT id FROM agents WHERE id = ?", ("test-1",))
        assert cursor.fetchone() is None
        storage.close()


class TestLeases:
    """Tests for lease management."""

    def test_acquire_lease(self, tmp_path):
        """Test acquiring a lease."""
        storage = Storage(tmp_path / "test.db")

        lease = storage.acquire_lease("facts/files/test.py", "agent-1")

        assert lease is not None
        assert lease.scope == "facts/files/test.py"
        assert lease.agent_id == "agent-1"
        assert not lease.is_expired()
        storage.close()

    def test_lease_blocks_other_agents(self, tmp_path):
        """Test that lease blocks other agents."""
        storage = Storage(tmp_path / "test.db")

        lease1 = storage.acquire_lease("facts/files/test.py", "agent-1")
        lease2 = storage.acquire_lease("facts/files/test.py", "agent-2")

        assert lease1 is not None
        assert lease2 is None  # Blocked
        storage.close()

    def test_same_agent_can_extend_lease(self, tmp_path):
        """Test that same agent can extend their lease."""
        storage = Storage(tmp_path / "test.db")

        lease1 = storage.acquire_lease("facts/files/test.py", "agent-1")
        lease2 = storage.acquire_lease("facts/files/test.py", "agent-1")

        assert lease1 is not None
        assert lease2 is not None  # Extended, not blocked
        storage.close()

    def test_release_lease(self, tmp_path):
        """Test releasing a lease."""
        storage = Storage(tmp_path / "test.db")

        storage.acquire_lease("facts/files/test.py", "agent-1")
        released = storage.release_lease("facts/files/test.py", "agent-1")

        assert released

        # Now another agent can acquire
        lease = storage.acquire_lease("facts/files/test.py", "agent-2")
        assert lease is not None
        storage.close()

    def test_cannot_release_others_lease(self, tmp_path):
        """Test that you can't release another agent's lease."""
        storage = Storage(tmp_path / "test.db")

        storage.acquire_lease("facts/files/test.py", "agent-1")
        released = storage.release_lease("facts/files/test.py", "agent-2")

        assert not released
        storage.close()

    def test_get_lease(self, tmp_path):
        """Test getting a lease."""
        storage = Storage(tmp_path / "test.db")

        storage.acquire_lease("facts/files/test.py", "agent-1")
        lease = storage.get_lease("facts/files/test.py")

        assert lease is not None
        assert lease.agent_id == "agent-1"
        storage.close()

    def test_get_nonexistent_lease(self, tmp_path):
        """Test getting a lease that doesn't exist."""
        storage = Storage(tmp_path / "test.db")

        lease = storage.get_lease("facts/files/test.py")

        assert lease is None
        storage.close()

    def test_lease_ttl(self, tmp_path):
        """Test lease TTL."""
        storage = Storage(tmp_path / "test.db")

        lease = storage.acquire_lease("facts/files/test.py", "agent-1", ttl_seconds=1)

        assert lease is not None
        assert not lease.is_expired()

        # Wait for expiry
        time.sleep(1.1)

        assert lease.is_expired()

        # Another agent can now acquire
        lease2 = storage.acquire_lease("facts/files/test.py", "agent-2")
        assert lease2 is not None
        storage.close()

    def test_cleanup_expired_leases(self, tmp_path):
        """Test cleaning up expired leases."""
        storage = Storage(tmp_path / "test.db")

        # Create short-lived lease
        storage.acquire_lease("scope-1", "agent-1", ttl_seconds=1)
        storage.acquire_lease("scope-2", "agent-1", ttl_seconds=100)

        time.sleep(1.1)

        count = storage.cleanup_expired_leases()

        assert count == 1  # Only scope-1 expired

        # Verify scope-2 still exists
        assert storage.get_lease("scope-2") is not None
        storage.close()


class TestCRUDHelpers:
    """Tests for generic CRUD operations."""

    def test_insert(self, tmp_path):
        """Test insert helper."""
        storage = Storage(tmp_path / "test.db")

        now = datetime.now(timezone.utc).isoformat()
        storage.insert("agents", {
            "id": "test-agent",
            "agent_class": "worker",
            "capabilities_json": "[]",
            "registered_at": now,
            "last_heartbeat": now,
            "permissions_json": "{}",
        })

        row = storage.get_by_id("agents", "test-agent")
        assert row is not None
        assert row["agent_class"] == "worker"
        storage.close()

    def test_update(self, tmp_path):
        """Test update helper."""
        storage = Storage(tmp_path / "test.db")

        now = datetime.now(timezone.utc).isoformat()
        storage.insert("agents", {
            "id": "test-agent",
            "agent_class": "worker",
            "capabilities_json": "[]",
            "registered_at": now,
            "last_heartbeat": now,
            "permissions_json": "{}",
        })

        updated = storage.update("agents", "id", "test-agent", {
            "agent_class": "architect"
        })

        assert updated
        row = storage.get_by_id("agents", "test-agent")
        assert row["agent_class"] == "architect"
        storage.close()

    def test_delete(self, tmp_path):
        """Test delete helper."""
        storage = Storage(tmp_path / "test.db")

        now = datetime.now(timezone.utc).isoformat()
        storage.insert("agents", {
            "id": "test-agent",
            "agent_class": "worker",
            "capabilities_json": "[]",
            "registered_at": now,
            "last_heartbeat": now,
            "permissions_json": "{}",
        })

        deleted = storage.delete("agents", "id", "test-agent")

        assert deleted
        assert storage.get_by_id("agents", "test-agent") is None
        storage.close()

    def test_query(self, tmp_path):
        """Test query helper."""
        storage = Storage(tmp_path / "test.db")

        now = datetime.now(timezone.utc).isoformat()
        for i in range(3):
            storage.insert("agents", {
                "id": f"agent-{i}",
                "agent_class": "worker" if i < 2 else "architect",
                "capabilities_json": "[]",
                "registered_at": now,
                "last_heartbeat": now,
                "permissions_json": "{}",
            })

        # Query all
        all_rows = storage.query("agents")
        assert len(all_rows) == 3

        # Query with filter
        workers = storage.query("agents", where={"agent_class": "worker"})
        assert len(workers) == 2

        # Query with limit
        limited = storage.query("agents", limit=1)
        assert len(limited) == 1
        storage.close()


class TestConcurrency:
    """Tests for concurrent access."""

    def test_concurrent_epoch_increments(self, tmp_path):
        """Test that concurrent epoch increments are safe."""
        storage = Storage(tmp_path / "test.db")
        results = []
        errors = []

        def increment():
            try:
                for _ in range(10):
                    epoch = storage.next_epoch()
                    results.append(epoch)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=increment) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 50
        # All epochs should be unique
        assert len(set(results)) == 50
        storage.close()

    def test_concurrent_lease_acquisition(self, tmp_path):
        """Test that concurrent lease acquisition is safe."""
        storage = Storage(tmp_path / "test.db")
        results = []

        def try_acquire(agent_id):
            lease = storage.acquire_lease("shared-scope", agent_id)
            results.append((agent_id, lease is not None))

        threads = [
            threading.Thread(target=try_acquire, args=(f"agent-{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly one agent should have acquired the lease
        acquired = [r for r in results if r[1]]
        assert len(acquired) == 1
        storage.close()


class TestGetStorage:
    """Tests for get_storage helper."""

    def test_get_storage_creates_db(self, tmp_path):
        """Test that get_storage creates the database."""
        governor_dir = tmp_path / ".governor"
        governor_dir.mkdir()

        storage = get_storage(governor_dir)

        assert (governor_dir / "governor.db").exists()
        storage.close()
