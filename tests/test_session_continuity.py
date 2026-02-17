# SPDX-License-Identifier: Apache-2.0
"""Tests for session_continuity.py — capsule-based session management.

Three acceptance tests per user request:
1. create → resume → identical ledger/workspace
2. fork → diverge → promote → resume mainline reflects promotion
3. compact no-op when under threshold

Plus comprehensive unit tests for all types and operations.
"""

import json
import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from governor.session_continuity import (
    SessionState,
    SessionMetadata,
    LedgerState,
    WorkspaceState,
    Capsule,
    Checkpoint,
    SessionStore,
    SessionManager,
    _utcnow,
    _generate_id,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_sessions_dir():
    """Create a temporary directory for session storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "sessions"


@pytest.fixture
def store(temp_sessions_dir):
    """Create a SessionStore with temp storage."""
    return SessionStore(temp_sessions_dir)


@pytest.fixture
def manager(store):
    """Create a SessionManager with the temp store."""
    return SessionManager(store)


# =============================================================================
# Acceptance Test 1: create → resume → identical ledger/workspace
# =============================================================================


class TestAcceptanceCreateResume:
    """Verify that resuming a session restores identical ledger/workspace state."""

    def test_create_resume_empty_session(self, manager):
        """Create and resume an empty session."""
        # Create
        capsule = manager.create("test-session", mode="fiction")
        session_id = capsule.metadata.session_id
        original_ledger_hash = capsule.ledger.content_hash()
        original_workspace_hash = capsule.workspace.content_hash()

        # Clear active to simulate new process
        manager._active_session = None

        # Resume
        resumed = manager.resume(session_id)

        assert resumed is not None
        assert resumed.metadata.session_id == session_id
        assert resumed.ledger.content_hash() == original_ledger_hash
        assert resumed.workspace.content_hash() == original_workspace_hash

    def test_create_resume_with_ledger_state(self, manager):
        """Create session with governance state, resume, verify identical."""
        # Create with populated ledger
        capsule = manager.create("governed-session", mode="code")

        # Populate ledger
        manager.update_ledger(
            anchors=[
                {"id": "a1", "type": "invariant", "description": "No SQL injection"},
                {"id": "a2", "type": "invariant", "description": "Auth required"},
            ],
            decisions=[
                {"id": "d1", "topic": "framework", "choice": "fastapi"},
                {"id": "d2", "topic": "auth", "choice": "jwt"},
            ],
            intent="Build REST API with auth",
            constraints=["no-breaking-changes", "test-coverage-80"],
        )

        session_id = capsule.metadata.session_id
        original_ledger = manager.active.ledger.to_dict()
        original_ledger_hash = manager.active.ledger.content_hash()

        # Clear and resume
        manager._active_session = None
        resumed = manager.resume(session_id)

        assert resumed is not None
        assert resumed.ledger.content_hash() == original_ledger_hash
        assert resumed.ledger.to_dict() == original_ledger
        assert len(resumed.ledger.anchors) == 2
        assert len(resumed.ledger.decisions) == 2
        assert resumed.ledger.intent == "Build REST API with auth"
        assert resumed.ledger.constraints == ["no-breaking-changes", "test-coverage-80"]

    def test_create_resume_with_workspace_state(self, manager):
        """Create session with workspace state, resume, verify identical."""
        capsule = manager.create("fiction-session", mode="fiction")

        # Populate workspace
        manager.update_workspace(
            active_thread_ids=["thread-1", "thread-2"],
            active_character_ids=["alice", "bob"],
            current_section="chapter-3",
            context_summary="Alice and Bob are discussing the heist plan.",
        )

        session_id = capsule.metadata.session_id
        original_workspace = manager.active.workspace.to_dict()
        original_workspace_hash = manager.active.workspace.content_hash()

        # Clear and resume
        manager._active_session = None
        resumed = manager.resume(session_id)

        assert resumed is not None
        assert resumed.workspace.content_hash() == original_workspace_hash
        assert resumed.workspace.to_dict() == original_workspace
        assert resumed.workspace.active_thread_ids == ["thread-1", "thread-2"]
        assert resumed.workspace.active_character_ids == ["alice", "bob"]
        assert resumed.workspace.current_section == "chapter-3"

    def test_create_resume_full_capsule(self, manager):
        """Full acceptance test: create with full state, resume, verify byte-identical."""
        capsule = manager.create("full-session", mode="nonfiction")

        # Populate both ledger and workspace
        manager.update_ledger(
            anchors=[{"id": "cite-all", "type": "invariant", "description": "All claims cited"}],
            decisions=[{"id": "style", "topic": "citation", "choice": "APA"}],
            intent="Write literature review",
            constraints=["peer-reviewed-only"],
        )
        manager.update_workspace(
            active_thread_ids=["section-2.1"],
            current_section="methodology",
            context_summary="Reviewing extraction methods.",
        )

        session_id = capsule.metadata.session_id
        original_capsule_dict = manager.active.to_dict()
        original_integrity = manager.active.integrity_hash()

        # Simulate process restart
        manager._active_session = None
        resumed = manager.resume(session_id)

        assert resumed is not None
        assert resumed.integrity_hash() == original_integrity

        # Deep comparison (excluding timestamps which change on resume)
        resumed_dict = resumed.to_dict()
        assert resumed_dict["ledger"] == original_capsule_dict["ledger"]
        assert resumed_dict["workspace"] == original_capsule_dict["workspace"]


# =============================================================================
# Acceptance Test 2: fork → diverge → promote → resume mainline reflects promotion
# =============================================================================


class TestAcceptanceForkDivergePromote:
    """Verify fork/promote semantics work correctly."""

    def test_fork_creates_independent_session(self, manager):
        """Forked session inherits state but diverges independently."""
        # Create mainline with state
        mainline = manager.create("mainline", mode="fiction")
        manager.update_ledger(
            anchors=[{"id": "canon1", "description": "Alice is the protagonist"}],
            intent="Write novel",
        )

        mainline_id = mainline.metadata.session_id
        original_anchor_count = 1

        # Fork
        fork = manager.fork("alternate-ending")
        assert fork is not None
        assert fork.metadata.parent_id == mainline_id
        assert fork.metadata.is_mainline is False

        # Fork should inherit ledger
        assert len(fork.ledger.anchors) == original_anchor_count

        # Now diverge: update mainline
        manager.resume(mainline_id)
        manager.update_ledger(
            anchors=[
                {"id": "canon1", "description": "Alice is the protagonist"},
                {"id": "canon2", "description": "Bob is the antagonist"},
            ]
        )

        # Verify fork is unaffected
        manager.resume(fork.metadata.session_id)
        assert len(manager.active.ledger.anchors) == 1  # Still only original anchor

    def test_promote_fork_becomes_mainline(self, manager):
        """Promoting a fork makes it the new mainline."""
        # Create mainline
        mainline = manager.create("original-mainline", mode="fiction")
        mainline_id = mainline.metadata.session_id
        manager.update_ledger(intent="Original plan")

        # Create fork with different content
        fork = manager.fork("better-version")
        fork_id = fork.metadata.session_id
        manager.resume(fork_id)
        manager.update_ledger(intent="Better plan")

        # Promote fork
        success = manager.promote(fork_id)
        assert success is True

        # Verify fork is now mainline
        promoted = manager.store.load_session(fork_id)
        assert promoted.metadata.is_mainline is True
        assert promoted.metadata.state == SessionState.PROMOTED

        # Verify old mainline is archived
        old_mainline = manager.store.load_session(mainline_id)
        assert old_mainline.metadata.is_mainline is False
        assert old_mainline.metadata.state == SessionState.ARCHIVED

    def test_resume_mainline_reflects_promotion(self, manager):
        """After promotion, resume mainline gives the promoted session."""
        # Create initial mainline
        initial = manager.create("initial-mainline", mode="fiction")
        initial_id = initial.metadata.session_id
        manager.update_ledger(intent="Initial intent")

        # Fork and diverge
        fork = manager.fork("divergent-fork")
        fork_id = fork.metadata.session_id
        manager.resume(fork_id)
        manager.update_ledger(
            intent="Divergent intent",
            anchors=[{"id": "new-anchor", "description": "Added in fork"}],
        )

        # Promote fork
        manager.promote(fork_id)

        # Get mainline - should be the promoted fork
        mainline_id = manager.store.get_mainline(mode="fiction")
        assert mainline_id == fork_id

        # Resume mainline and verify it has fork's state
        manager._active_session = None
        mainline = manager.resume(mainline_id)
        assert mainline.ledger.intent == "Divergent intent"
        assert len(mainline.ledger.anchors) == 1
        assert mainline.ledger.anchors[0]["id"] == "new-anchor"

    def test_full_fork_diverge_promote_cycle(self, manager):
        """Complete acceptance test for fork/promote workflow."""
        # Step 1: Create mainline with governance state
        mainline = manager.create("novel-draft", mode="fiction")
        mainline_id = mainline.metadata.session_id
        manager.update_ledger(
            anchors=[
                {"id": "c1", "description": "Alice survives"},
                {"id": "c2", "description": "The heist fails"},
            ],
            intent="Complete novel draft 1",
        )
        manager.update_workspace(
            current_section="chapter-10",
            context_summary="Climax scene",
        )

        mainline_ledger_hash = manager.active.ledger.content_hash()

        # Step 2: Fork for alternate ending
        fork = manager.fork("alternate-ending")
        fork_id = fork.metadata.session_id

        # Step 3: Diverge in fork - change canon
        manager.resume(fork_id)
        manager.update_ledger(
            anchors=[
                {"id": "c1", "description": "Alice survives"},
                {"id": "c2-alt", "description": "The heist succeeds"},  # Changed!
            ],
            intent="Complete novel draft 1 (alternate)",
        )
        manager.update_workspace(
            current_section="chapter-10-alt",
            context_summary="Triumphant climax scene",
        )

        fork_ledger_hash = manager.active.ledger.content_hash()
        assert fork_ledger_hash != mainline_ledger_hash  # Confirmed divergence

        # Step 4: Decide fork is better, promote it
        manager.promote(fork_id)

        # Step 5: Resume what we call "mainline" - should be the fork's state
        manager._active_session = None
        new_mainline_id = manager.store.get_mainline(mode="fiction")
        new_mainline = manager.resume(new_mainline_id)

        assert new_mainline.metadata.session_id == fork_id
        assert new_mainline.ledger.content_hash() == fork_ledger_hash
        assert new_mainline.ledger.anchors[1]["id"] == "c2-alt"  # The alternate version
        assert new_mainline.workspace.current_section == "chapter-10-alt"


# =============================================================================
# Acceptance Test 3: Compact no-op when under threshold
# =============================================================================


class TestAcceptanceCompactThreshold:
    """Verify that compaction doesn't occur prematurely.

    Note: Full compaction is in GOVERNED_COMPACT_SPEC.md (gap).
    For now, we test that small sessions don't trigger any loss.
    """

    def test_small_session_no_loss(self, manager):
        """Small sessions should preserve all state without loss."""
        capsule = manager.create("small-session", mode="code")

        # Add modest amount of state
        manager.update_ledger(
            anchors=[{"id": f"a{i}", "desc": f"Anchor {i}"} for i in range(5)],
            decisions=[{"id": f"d{i}", "topic": f"Topic {i}"} for i in range(3)],
            intent="Small project",
            constraints=["c1", "c2"],
        )
        manager.update_workspace(
            active_thread_ids=["t1", "t2"],
            current_section="main",
            context_summary="Short context",
        )

        original = manager.active.to_dict()
        session_id = capsule.metadata.session_id

        # Resume multiple times - no loss should occur
        for _ in range(3):
            manager._active_session = None
            resumed = manager.resume(session_id)
            assert resumed.to_dict()["ledger"] == original["ledger"]
            assert resumed.to_dict()["workspace"] == original["workspace"]

    def test_checkpoint_preserves_full_state(self, manager):
        """Checkpoints capture complete state without loss."""
        capsule = manager.create("checkpoint-test", mode="fiction")
        manager.update_ledger(
            anchors=[{"id": "a1", "critical": True}],
            intent="Critical work",
        )

        # Checkpoint
        checkpoint = manager.checkpoint("before-risk")
        assert checkpoint is not None
        assert checkpoint.ledger_hash == manager.active.ledger.content_hash()
        assert checkpoint.workspace_hash == manager.active.workspace.content_hash()

        # Modify state
        manager.update_ledger(
            anchors=[{"id": "a1", "critical": True}, {"id": "a2", "new": True}],
            intent="Modified intent",
        )

        # Checkpoint still has original state
        checkpoints = manager.get_checkpoints()
        assert len(checkpoints) == 1
        assert checkpoints[0]["ledger_hash"] == checkpoint.ledger_hash

    def test_no_silent_shear(self, manager):
        """Verify no representational shear occurs during normal operations."""
        # Create session with known state
        capsule = manager.create("shear-test", mode="code")

        decisions = [
            {"id": "d1", "topic": "framework", "choice": "django", "rationale": "Team knows it"},
            {"id": "d2", "topic": "db", "choice": "postgres", "rationale": "ACID needed"},
        ]
        anchors = [
            {"id": "inv1", "type": "invariant", "rule": "All endpoints require auth"},
            {"id": "inv2", "type": "invariant", "rule": "No raw SQL"},
        ]
        constraints = ["test-first", "pr-review-required", "no-force-push"]

        manager.update_ledger(
            decisions=decisions,
            anchors=anchors,
            constraints=constraints,
            intent="Build secure API",
        )

        session_id = capsule.metadata.session_id
        original_ledger = manager.active.ledger.to_dict()

        # Simulate many resume cycles (e.g., daily work sessions)
        for day in range(7):
            manager._active_session = None
            resumed = manager.resume(session_id)

            # Verify no shear - all governance state intact
            assert resumed.ledger.decisions == original_ledger["decisions"]
            assert resumed.ledger.anchors == original_ledger["anchors"]
            assert resumed.ledger.constraints == original_ledger["constraints"]
            assert resumed.ledger.intent == original_ledger["intent"]

            # Simulate some workspace updates (which should be fine)
            manager.update_workspace(
                context_summary=f"Day {day + 1} work session",
            )


# =============================================================================
# Unit Tests: Types
# =============================================================================


class TestSessionState:
    def test_enum_values(self):
        assert SessionState.ACTIVE.value == "active"
        assert SessionState.CHECKPOINTED.value == "checkpointed"
        assert SessionState.FORKED.value == "forked"
        assert SessionState.PROMOTED.value == "promoted"
        assert SessionState.ARCHIVED.value == "archived"


class TestSessionMetadata:
    def test_create(self):
        now = _utcnow()
        meta = SessionMetadata(
            session_id="sess_abc123",
            name="test-session",
            mode="fiction",
            created_at=now,
            last_active=now,
            state=SessionState.ACTIVE,
        )
        assert meta.session_id == "sess_abc123"
        assert meta.is_mainline is True
        assert meta.parent_id is None

    def test_to_dict_roundtrip(self):
        now = _utcnow()
        original = SessionMetadata(
            session_id="sess_xyz",
            name="roundtrip-test",
            mode="code",
            created_at=now,
            last_active=now,
            state=SessionState.FORKED,
            parent_id="sess_parent",
            is_mainline=False,
            checkpoint_count=3,
            fork_count=1,
        )
        data = original.to_dict()
        restored = SessionMetadata.from_dict(data)

        assert restored.session_id == original.session_id
        assert restored.name == original.name
        assert restored.mode == original.mode
        assert restored.state == original.state
        assert restored.parent_id == original.parent_id
        assert restored.is_mainline == original.is_mainline
        assert restored.checkpoint_count == original.checkpoint_count
        assert restored.fork_count == original.fork_count


class TestLedgerState:
    def test_create_empty(self):
        ledger = LedgerState()
        assert ledger.anchors == []
        assert ledger.decisions == []
        assert ledger.intent is None

    def test_create_with_state(self):
        ledger = LedgerState(
            anchors=[{"id": "a1"}],
            decisions=[{"id": "d1"}],
            intent="Build thing",
            constraints=["c1"],
        )
        assert len(ledger.anchors) == 1
        assert ledger.intent == "Build thing"

    def test_content_hash_deterministic(self):
        ledger = LedgerState(anchors=[{"id": "a1"}], intent="test")
        hash1 = ledger.content_hash()
        hash2 = ledger.content_hash()
        assert hash1 == hash2
        assert len(hash1) == 16  # Truncated SHA256

    def test_content_hash_changes_with_content(self):
        ledger1 = LedgerState(intent="one")
        ledger2 = LedgerState(intent="two")
        assert ledger1.content_hash() != ledger2.content_hash()

    def test_to_dict_roundtrip(self):
        original = LedgerState(
            anchors=[{"id": "a1", "desc": "test"}],
            decisions=[{"id": "d1", "choice": "yes"}],
            canon_events=[{"id": "e1", "what": "happened"}],
            authority={"user": "admin", "scope": "all"},
            intent="Do the thing",
            constraints=["no-bugs"],
        )
        data = original.to_dict()
        restored = LedgerState.from_dict(data)

        assert restored.anchors == original.anchors
        assert restored.decisions == original.decisions
        assert restored.canon_events == original.canon_events
        assert restored.authority == original.authority
        assert restored.intent == original.intent
        assert restored.constraints == original.constraints


class TestWorkspaceState:
    def test_create_empty(self):
        ws = WorkspaceState()
        assert ws.active_thread_ids == []
        assert ws.current_section is None
        assert ws.notes == ""

    def test_create_with_state(self):
        ws = WorkspaceState(
            active_thread_ids=["t1", "t2"],
            active_character_ids=["alice"],
            current_section="chapter-5",
            cursor_position={"file": "draft.md", "line": 42},
            outline=["ch1", "ch2", "ch3"],
            notes="Remember to add foreshadowing",
            context_summary="Alice is about to discover the truth.",
        )
        assert ws.active_thread_ids == ["t1", "t2"]
        assert ws.cursor_position["line"] == 42

    def test_content_hash_deterministic(self):
        ws = WorkspaceState(current_section="test")
        assert ws.content_hash() == ws.content_hash()

    def test_to_dict_roundtrip(self):
        original = WorkspaceState(
            active_thread_ids=["t1"],
            current_section="intro",
            context_summary="Context here",
        )
        restored = WorkspaceState.from_dict(original.to_dict())
        assert restored.active_thread_ids == original.active_thread_ids
        assert restored.current_section == original.current_section


class TestCapsule:
    def test_create(self):
        now = _utcnow()
        meta = SessionMetadata(
            session_id="sess_1",
            name="test",
            mode="fiction",
            created_at=now,
            last_active=now,
            state=SessionState.ACTIVE,
        )
        capsule = Capsule(
            metadata=meta,
            ledger=LedgerState(intent="test"),
            workspace=WorkspaceState(current_section="ch1"),
        )
        assert capsule.metadata.session_id == "sess_1"
        assert capsule.ledger.intent == "test"
        assert capsule.workspace.current_section == "ch1"

    def test_integrity_hash(self):
        now = _utcnow()
        meta = SessionMetadata(
            session_id="sess_1",
            name="test",
            mode="fiction",
            created_at=now,
            last_active=now,
            state=SessionState.ACTIVE,
        )
        capsule = Capsule(
            metadata=meta,
            ledger=LedgerState(intent="test"),
            workspace=WorkspaceState(current_section="ch1"),
        )
        hash1 = capsule.integrity_hash()
        hash2 = capsule.integrity_hash()
        assert hash1 == hash2
        assert len(hash1) == 16

    def test_to_dict_roundtrip(self):
        now = _utcnow()
        original = Capsule(
            metadata=SessionMetadata(
                session_id="sess_1",
                name="test",
                mode="code",
                created_at=now,
                last_active=now,
                state=SessionState.ACTIVE,
            ),
            ledger=LedgerState(
                anchors=[{"id": "a1"}],
                intent="Build API",
            ),
            workspace=WorkspaceState(
                current_section="auth",
            ),
        )
        restored = Capsule.from_dict(original.to_dict())
        assert restored.metadata.session_id == original.metadata.session_id
        assert restored.ledger.anchors == original.ledger.anchors
        assert restored.workspace.current_section == original.workspace.current_section


class TestCheckpoint:
    def test_create(self):
        now = _utcnow()
        capsule = Capsule(
            metadata=SessionMetadata(
                session_id="sess_1",
                name="test",
                mode="fiction",
                created_at=now,
                last_active=now,
                state=SessionState.ACTIVE,
            ),
            ledger=LedgerState(),
            workspace=WorkspaceState(),
        )
        checkpoint = Checkpoint(
            checkpoint_id="cp_1",
            session_id="sess_1",
            name="before-change",
            created_at=now,
            ledger_hash=capsule.ledger.content_hash(),
            workspace_hash=capsule.workspace.content_hash(),
            capsule=capsule,
        )
        assert checkpoint.checkpoint_id == "cp_1"
        assert checkpoint.name == "before-change"

    def test_to_dict_roundtrip(self):
        now = _utcnow()
        capsule = Capsule(
            metadata=SessionMetadata(
                session_id="sess_1",
                name="test",
                mode="fiction",
                created_at=now,
                last_active=now,
                state=SessionState.ACTIVE,
            ),
            ledger=LedgerState(intent="checkpoint test"),
            workspace=WorkspaceState(notes="important note"),
        )
        original = Checkpoint(
            checkpoint_id="cp_2",
            session_id="sess_1",
            name="snapshot",
            created_at=now,
            ledger_hash=capsule.ledger.content_hash(),
            workspace_hash=capsule.workspace.content_hash(),
            capsule=capsule,
        )
        restored = Checkpoint.from_dict(original.to_dict())
        assert restored.checkpoint_id == original.checkpoint_id
        assert restored.capsule.ledger.intent == "checkpoint test"


# =============================================================================
# Unit Tests: SessionStore
# =============================================================================


class TestSessionStore:
    def test_create_session(self, store):
        capsule = store.create_session("test-session", mode="fiction")
        assert capsule.metadata.name == "test-session"
        assert capsule.metadata.mode == "fiction"
        assert capsule.metadata.is_mainline is True

    def test_save_and_load_session(self, store):
        capsule = store.create_session("save-load-test", mode="code")
        capsule.ledger.intent = "Modified intent"
        capsule.workspace.notes = "Some notes"
        store.save_session(capsule)

        loaded = store.load_session(capsule.metadata.session_id)
        assert loaded is not None
        assert loaded.ledger.intent == "Modified intent"
        assert loaded.workspace.notes == "Some notes"

    def test_load_nonexistent_session(self, store):
        loaded = store.load_session("nonexistent_id")
        assert loaded is None

    def test_list_sessions(self, store):
        store.create_session("session-1", mode="fiction")
        store.create_session("session-2", mode="fiction")
        store.create_session("session-3", mode="code")

        all_sessions = store.list_sessions()
        assert len(all_sessions) == 3

        fiction_sessions = store.list_sessions(mode="fiction")
        assert len(fiction_sessions) == 2

        code_sessions = store.list_sessions(mode="code")
        assert len(code_sessions) == 1

    def test_get_mainline(self, store):
        # First session becomes mainline
        first = store.create_session("first", mode="fiction")
        assert store.get_mainline() == first.metadata.session_id

        # Second session is not mainline
        store.create_session("second", mode="fiction")
        assert store.get_mainline() == first.metadata.session_id

    def test_delete_session(self, store):
        capsule = store.create_session("to-delete", mode="fiction")
        session_id = capsule.metadata.session_id

        assert store.load_session(session_id) is not None
        assert store.delete_session(session_id) is True
        assert store.load_session(session_id) is None
        assert store.delete_session(session_id) is False  # Already deleted

    def test_fork_creates_non_mainline(self, store):
        parent = store.create_session("parent", mode="fiction")
        fork = store.create_session("fork", mode="fiction", parent_id=parent.metadata.session_id)

        assert fork.metadata.is_mainline is False
        assert fork.metadata.parent_id == parent.metadata.session_id

    def test_fork_inherits_ledger(self, store):
        parent = store.create_session("parent", mode="fiction")
        parent.ledger.anchors = [{"id": "inherited"}]
        parent.ledger.intent = "Parent intent"
        store.save_session(parent)

        fork = store.create_session("fork", mode="fiction", parent_id=parent.metadata.session_id)
        assert fork.ledger.anchors == [{"id": "inherited"}]
        assert fork.ledger.intent == "Parent intent"

    def test_ledger_saved_as_yaml(self, store):
        capsule = store.create_session("yaml-test", mode="fiction")
        capsule.ledger.intent = "YAML test"
        store.save_session(capsule)

        ledger_path = store._session_dir(capsule.metadata.session_id) / "ledger.yaml"
        assert ledger_path.exists()
        content = ledger_path.read_text()
        assert "intent: YAML test" in content


# =============================================================================
# Unit Tests: SessionManager
# =============================================================================


class TestSessionManager:
    def test_create_makes_active(self, manager):
        capsule = manager.create("active-test", mode="code")
        assert manager.active is not None
        assert manager.active.metadata.session_id == capsule.metadata.session_id

    def test_resume_makes_active(self, manager):
        capsule = manager.create("resume-test", mode="code")
        session_id = capsule.metadata.session_id
        manager._active_session = None

        resumed = manager.resume(session_id)
        assert manager.active is not None
        assert manager.active.metadata.session_id == session_id

    def test_resume_last(self, manager):
        manager.create("session-1", mode="fiction")
        manager.create("session-2", mode="fiction")
        latest = manager.create("session-3", mode="fiction")
        # Update the latest session to ensure it has the most recent last_active
        manager.update_ledger(intent="Make this the most recent")
        latest_id = latest.metadata.session_id
        manager._active_session = None

        resumed = manager.resume_last(mode="fiction")
        assert resumed is not None
        assert resumed.metadata.session_id == latest_id

    def test_checkpoint_creates_snapshot(self, manager):
        capsule = manager.create("checkpoint-test", mode="fiction")
        manager.update_ledger(intent="Before checkpoint")

        checkpoint = manager.checkpoint("before-risky-change")
        assert checkpoint is not None
        assert checkpoint.name == "before-risky-change"
        assert checkpoint.capsule.ledger.intent == "Before checkpoint"
        assert manager.active.metadata.checkpoint_count == 1

    def test_checkpoint_without_active_returns_none(self, manager):
        assert manager.checkpoint() is None

    def test_fork_creates_new_session(self, manager):
        parent = manager.create("parent", mode="fiction")
        manager.update_ledger(intent="Parent's intent")

        fork = manager.fork("my-fork")
        assert fork is not None
        assert fork.metadata.parent_id == parent.metadata.session_id
        assert fork.metadata.is_mainline is False
        assert fork.ledger.intent == "Parent's intent"

    def test_fork_without_active_returns_none(self, manager):
        assert manager.fork() is None

    def test_promote_nonexistent_returns_false(self, manager):
        assert manager.promote("nonexistent") is False

    def test_promote_already_mainline(self, manager):
        mainline = manager.create("mainline", mode="fiction")
        assert manager.promote(mainline.metadata.session_id) is True  # No-op success

    def test_update_ledger(self, manager):
        manager.create("update-test", mode="code")
        success = manager.update_ledger(
            intent="New intent",
            constraints=["c1", "c2"],
        )
        assert success is True
        assert manager.active.ledger.intent == "New intent"
        assert manager.active.ledger.constraints == ["c1", "c2"]

    def test_update_workspace(self, manager):
        manager.create("workspace-test", mode="fiction")
        success = manager.update_workspace(
            active_thread_ids=["t1"],
            current_section="ch3",
        )
        assert success is True
        assert manager.active.workspace.active_thread_ids == ["t1"]
        assert manager.active.workspace.current_section == "ch3"

    def test_update_without_active_returns_false(self, manager):
        assert manager.update_ledger(intent="nope") is False
        assert manager.update_workspace(current_section="nope") is False

    def test_get_checkpoints(self, manager):
        manager.create("checkpoints-test", mode="fiction")
        manager.checkpoint("cp-1")
        manager.checkpoint("cp-2")

        checkpoints = manager.get_checkpoints()
        assert len(checkpoints) == 2
        names = [c["name"] for c in checkpoints]
        assert "cp-1" in names
        assert "cp-2" in names

    def test_restore_checkpoint(self, manager):
        capsule = manager.create("restore-test", mode="fiction")
        manager.update_ledger(intent="Original intent")

        checkpoint = manager.checkpoint("before-mistake")
        manager.update_ledger(intent="Wrong intent")

        restored = manager.restore_checkpoint(checkpoint.checkpoint_id)
        assert restored is not None
        assert restored.ledger.intent == "Original intent"
        assert restored.metadata.parent_id == capsule.metadata.session_id


# =============================================================================
# Unit Tests: Helpers
# =============================================================================


class TestHelpers:
    def test_generate_id_with_prefix(self):
        id1 = _generate_id("sess")
        id2 = _generate_id("sess")
        assert id1.startswith("sess_")
        assert id2.startswith("sess_")
        assert id1 != id2  # Should be unique

    def test_generate_id_length(self):
        id1 = _generate_id("test")
        # prefix + underscore + 12 hex chars
        assert len(id1) == len("test_") + 12

    def test_utcnow_returns_naive_utc(self):
        now = _utcnow()
        assert isinstance(now, datetime)
        assert now.tzinfo is None  # Naive datetime


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    def test_multi_mode_sessions(self, manager):
        """Test that different modes are properly isolated."""
        fiction = manager.create("novel", mode="fiction")
        code = manager.create("api", mode="code")
        nonfiction = manager.create("paper", mode="nonfiction")

        fiction_list = manager.store.list_sessions(mode="fiction")
        assert len(fiction_list) == 1
        assert fiction_list[0]["name"] == "novel"

        code_list = manager.store.list_sessions(mode="code")
        assert len(code_list) == 1
        assert code_list[0]["name"] == "api"

    def test_session_persistence_across_stores(self, temp_sessions_dir):
        """Test that sessions persist across SessionStore instances."""
        # Create and populate with first store
        store1 = SessionStore(temp_sessions_dir)
        manager1 = SessionManager(store1)
        capsule = manager1.create("persistent", mode="fiction")
        manager1.update_ledger(
            anchors=[{"id": "a1", "important": True}],
            intent="Test persistence",
        )
        session_id = capsule.metadata.session_id

        # Create new store instance (simulating process restart)
        store2 = SessionStore(temp_sessions_dir)
        manager2 = SessionManager(store2)

        # Session should be loadable
        resumed = manager2.resume(session_id)
        assert resumed is not None
        assert resumed.ledger.intent == "Test persistence"
        assert resumed.ledger.anchors == [{"id": "a1", "important": True}]

    def test_fork_tree(self, manager):
        """Test creating a tree of forks."""
        # root
        #   ├── fork-1
        #   │   └── fork-1-1
        #   └── fork-2

        root = manager.create("root", mode="fiction")
        root_id = root.metadata.session_id

        fork1 = manager.fork("fork-1")
        fork1_id = fork1.metadata.session_id

        manager.resume(fork1_id)
        fork1_1 = manager.fork("fork-1-1")

        manager.resume(root_id)
        fork2 = manager.fork("fork-2")

        # Verify structure
        assert fork1.metadata.parent_id == root_id
        assert fork1_1.metadata.parent_id == fork1_id
        assert fork2.metadata.parent_id == root_id

        # All should be listed
        all_sessions = manager.store.list_sessions()
        assert len(all_sessions) == 4
