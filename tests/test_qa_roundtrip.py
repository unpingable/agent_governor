"""QA Harness: Serialization Roundtrip Tests.

Every serializable type must survive to_dict() → from_dict() → to_dict().
This catches bugs that show up 6 months from now when someone loads old data.

"If it can't roundtrip, it can't persist."
"""

import pytest
from datetime import datetime, timezone, timedelta
from dataclasses import fields, is_dataclass


# =============================================================================
# Type Discovery
# =============================================================================

# All serializable types with to_dict/from_dict methods
SERIALIZABLE_TYPES = []

# Session continuity types
try:
    from governor.session_continuity import (
        SessionMetadata, LedgerState, WorkspaceState, Capsule, Checkpoint,
        SessionState, _utcnow,
    )
    SERIALIZABLE_TYPES.extend([
        ("SessionMetadata", SessionMetadata, lambda: SessionMetadata(
            session_id="sess_test123",
            name="test-session",
            mode="fiction",
            created_at=_utcnow(),
            last_active=_utcnow(),
            state=SessionState.ACTIVE,
            parent_id="sess_parent",
            is_mainline=False,
            checkpoint_count=3,
            fork_count=1,
        )),
        ("LedgerState", LedgerState, lambda: LedgerState(
            anchors=[{"id": "a1", "desc": "test anchor"}],
            decisions=[{"id": "d1", "choice": "yes"}],
            canon_events=[{"id": "e1", "what": "happened"}],
            authority={"user": "admin"},
            intent="Test intent",
            constraints=["c1", "c2"],
        )),
        ("WorkspaceState", WorkspaceState, lambda: WorkspaceState(
            active_thread_ids=["t1", "t2"],
            active_character_ids=["alice", "bob"],
            current_section="chapter-5",
            cursor_position={"file": "draft.md", "line": 42},
            outline=["ch1", "ch2"],
            notes="Test notes",
            context_summary="Test context",
        )),
    ])
except ImportError:
    pass

# Epistemic types - skip for now due to API variations
# These are tested in the main test_epistemic.py file

# Quorum types - tested in test_quorum.py

# Dissent, TTL, Tone, Regime types - tested in their respective test files

# Continuity anchor types
try:
    from governor.continuity import Anchor, AnchorType, Severity, ConstraintClass
    SERIALIZABLE_TYPES.extend([
        ("Anchor", Anchor, lambda: Anchor(
            id="anchor-123",
            anchor_type=AnchorType.REQUIREMENT,
            description="Test anchor description",
            required_patterns=["must", "should"],
            forbidden_patterns=["never", "don't"],
            severity=Severity.CORRECT,
            constraint_class=ConstraintClass.PREFERENCE,
        )),
    ])
except ImportError:
    pass

# External, MCP safety, Check types - tested in their respective test files
# API variations make generic roundtrip testing fragile; specific tests are more valuable


# =============================================================================
# Roundtrip Test Infrastructure
# =============================================================================


def roundtrip_test(cls, factory):
    """Test that a type survives serialization roundtrip.

    Args:
        cls: The class to test
        factory: A callable that creates a valid instance
    """
    # Create instance
    instance = factory()

    # First serialization
    try:
        serialized = instance.to_dict()
    except AttributeError:
        pytest.skip(f"{cls.__name__} has no to_dict method")
        return

    # Deserialize
    try:
        deserialized = cls.from_dict(serialized)
    except AttributeError:
        pytest.skip(f"{cls.__name__} has no from_dict method")
        return
    except Exception as e:
        pytest.fail(f"{cls.__name__}.from_dict failed: {e}")

    # Second serialization
    try:
        reserialized = deserialized.to_dict()
    except Exception as e:
        pytest.fail(f"{cls.__name__} reserialization failed: {e}")

    # Compare
    assert serialized == reserialized, (
        f"{cls.__name__} roundtrip mismatch:\n"
        f"Original: {serialized}\n"
        f"After roundtrip: {reserialized}"
    )


# =============================================================================
# Parametrized Roundtrip Tests
# =============================================================================


@pytest.mark.parametrize("name,cls,factory", SERIALIZABLE_TYPES)
def test_roundtrip(name, cls, factory):
    """Every serializable type must survive roundtrip."""
    roundtrip_test(cls, factory)


# =============================================================================
# Type-Specific Deep Tests
# =============================================================================


class TestSessionContinuityRoundtrip:
    """Deep roundtrip tests for session continuity types."""

    def test_capsule_roundtrip(self):
        """Full capsule with nested types survives roundtrip."""
        try:
            from governor.session_continuity import (
                Capsule, SessionMetadata, LedgerState, WorkspaceState,
                SessionState, _utcnow,
            )
        except ImportError:
            pytest.skip("session_continuity not available")

        now = _utcnow()
        capsule = Capsule(
            metadata=SessionMetadata(
                session_id="sess_deep_test",
                name="deep-test-session",
                mode="fiction",
                created_at=now,
                last_active=now,
                state=SessionState.CHECKPOINTED,
                parent_id="sess_parent",
                is_mainline=False,
                checkpoint_count=5,
                fork_count=2,
            ),
            ledger=LedgerState(
                anchors=[
                    {"id": "a1", "type": "invariant", "desc": "First anchor"},
                    {"id": "a2", "type": "preference", "desc": "Second anchor"},
                ],
                decisions=[
                    {"id": "d1", "topic": "framework", "choice": "fastapi"},
                ],
                canon_events=[
                    {"id": "e1", "chapter": 1, "event": "Hero introduced"},
                ],
                authority={"admin": True, "scope": "all"},
                intent="Complete the novel draft",
                constraints=["no-breaking-changes", "test-coverage"],
            ),
            workspace=WorkspaceState(
                active_thread_ids=["thread-1", "thread-2", "thread-3"],
                active_character_ids=["alice", "bob", "charlie"],
                current_section="chapter-10",
                cursor_position={"file": "chapter10.md", "line": 150, "col": 0},
                outline=["ch1", "ch2", "ch3", "ch4", "ch5"],
                notes="Remember the twist reveal",
                context_summary="Alice is confronting Bob about the heist.",
            ),
        )

        serialized = capsule.to_dict()
        deserialized = Capsule.from_dict(serialized)
        reserialized = deserialized.to_dict()

        assert serialized == reserialized

    def test_checkpoint_roundtrip(self):
        """Checkpoint with embedded capsule survives roundtrip."""
        try:
            from governor.session_continuity import (
                Capsule, Checkpoint, SessionMetadata, LedgerState, WorkspaceState,
                SessionState, _utcnow,
            )
        except ImportError:
            pytest.skip("session_continuity not available")

        now = _utcnow()
        capsule = Capsule(
            metadata=SessionMetadata(
                session_id="sess_cp_test",
                name="checkpoint-test",
                mode="code",
                created_at=now,
                last_active=now,
                state=SessionState.ACTIVE,
            ),
            ledger=LedgerState(intent="Test checkpoint"),
            workspace=WorkspaceState(current_section="main"),
        )

        checkpoint = Checkpoint(
            checkpoint_id="cp_test123",
            session_id="sess_cp_test",
            name="before-risky-change",
            created_at=now,
            ledger_hash=capsule.ledger.content_hash(),
            workspace_hash=capsule.workspace.content_hash(),
            capsule=capsule,
        )

        serialized = checkpoint.to_dict()
        deserialized = Checkpoint.from_dict(serialized)
        reserialized = deserialized.to_dict()

        assert serialized == reserialized


class TestEpistemicRoundtrip:
    """Deep roundtrip tests for epistemic types."""

    def test_grounded_claim_with_evidence(self):
        """Claim with multiple evidence refs survives roundtrip.

        Note: Epistemic API details are tested in test_epistemic.py.
        This is a placeholder for future integration.
        """
        pytest.skip("Epistemic API roundtrip tested in test_epistemic.py")


# =============================================================================
# Edge Cases
# =============================================================================


class TestRoundtripEdgeCases:
    """Test edge cases in serialization."""

    def test_empty_collections(self):
        """Types with empty collections survive roundtrip."""
        try:
            from governor.session_continuity import LedgerState
        except ImportError:
            pytest.skip("session_continuity not available")

        empty_ledger = LedgerState()

        serialized = empty_ledger.to_dict()
        deserialized = LedgerState.from_dict(serialized)
        reserialized = deserialized.to_dict()

        assert serialized == reserialized

    def test_none_values(self):
        """Types with None values survive roundtrip."""
        try:
            from governor.session_continuity import (
                SessionMetadata, SessionState, _utcnow,
            )
        except ImportError:
            pytest.skip("session_continuity not available")

        now = _utcnow()
        meta = SessionMetadata(
            session_id="sess_none_test",
            name="none-test",
            mode="fiction",
            created_at=now,
            last_active=now,
            state=SessionState.ACTIVE,
            parent_id=None,  # Explicit None
        )

        serialized = meta.to_dict()
        deserialized = SessionMetadata.from_dict(serialized)
        reserialized = deserialized.to_dict()

        assert serialized == reserialized
        assert deserialized.parent_id is None

    def test_unicode_content(self):
        """Types with unicode content survive roundtrip."""
        try:
            from governor.session_continuity import LedgerState
        except ImportError:
            pytest.skip("session_continuity not available")

        ledger = LedgerState(
            intent="测试中文内容 🎉 émojis et accénts",
            anchors=[{"id": "日本語", "desc": "Ελληνικά κείμενο"}],
        )

        serialized = ledger.to_dict()
        deserialized = LedgerState.from_dict(serialized)
        reserialized = deserialized.to_dict()

        assert serialized == reserialized
        assert deserialized.intent == "测试中文内容 🎉 émojis et accénts"
