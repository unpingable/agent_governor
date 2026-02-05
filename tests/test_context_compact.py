"""Tests for context compaction module.

Loss-aware context compaction that emits receipts, respects anchors,
and never silently drops governance state.
"""

import pytest
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

from governor.context_compact import (
    # Types
    ItemType,
    DroppedItem,
    Turn,
    Conversation,
    # Configuration
    CompactionConfig,
    # Receipt
    CompactionReceipt,
    CompactedConversation,
    # Summarizer
    SimpleSummarizer,
    # Recovery
    RecoveryStore,
    # Compactor
    ContextCompactor,
    ReceiptStore,
    # Convenience
    create_compactor,
    compact_conversation,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_dir():
    """Create a temporary directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_turns():
    """Create sample conversation turns."""
    return [
        Turn(role="user", content="Hello, can you help me with my project?", token_estimate=10),
        Turn(role="assistant", content="Of course! What are you working on?", token_estimate=10),
        Turn(role="user", content="I need to build a web application with user authentication.", token_estimate=15),
        Turn(role="assistant", content="I can help with that. Let's start with the requirements.", token_estimate=15),
        Turn(role="user", content="It should support OAuth and email/password login.", token_estimate=12),
    ]


@pytest.fixture
def sample_conversation(sample_turns):
    """Create a sample conversation with governance state."""
    return Conversation(
        turns=sample_turns,
        decisions=[
            {"topic": "auth_method", "choice": "OAuth2 + email/password"},
            {"topic": "framework", "choice": "FastAPI"},
        ],
        anchors=[
            {"id": "security-1", "description": "All passwords must be hashed"},
        ],
        constraints=[
            {"id": "c1", "description": "Use HTTPS only"},
        ],
        authority={"approved_by": "user", "scope": "session"},
        intent="Build authentication system",
        context_limit=1000,
    )


# =============================================================================
# Tests: Types
# =============================================================================


class TestItemType:
    """Test ItemType enum."""

    def test_values(self):
        """Test enum values."""
        assert ItemType.TURN.value == "turn"
        assert ItemType.REASONING.value == "reasoning"
        assert ItemType.EXPLORATION.value == "exploration"
        assert ItemType.REJECTED.value == "rejected"


class TestDroppedItem:
    """Test DroppedItem dataclass."""

    def test_creation(self):
        """Test basic creation."""
        item = DroppedItem(
            item_type=ItemType.TURN,
            description="user: Hello...",
            content_hash="abc123",
        )
        assert item.item_type == ItemType.TURN
        assert item.description == "user: Hello..."
        assert item.content_hash == "abc123"
        assert item.recoverable is True

    def test_to_dict(self):
        """Test serialization."""
        item = DroppedItem(
            item_type=ItemType.REASONING,
            description="Analysis of options",
            content_hash="def456",
            recoverable=False,
            original_index=5,
        )
        d = item.to_dict()
        assert d["item_type"] == "reasoning"
        assert d["description"] == "Analysis of options"
        assert d["content_hash"] == "def456"
        assert d["recoverable"] is False
        assert d["original_index"] == 5

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "item_type": "exploration",
            "description": "Tried approach X",
            "content_hash": "ghi789",
            "recoverable": True,
            "original_index": 3,
        }
        item = DroppedItem.from_dict(data)
        assert item.item_type == ItemType.EXPLORATION
        assert item.description == "Tried approach X"
        assert item.content_hash == "ghi789"

    def test_roundtrip(self):
        """Test roundtrip serialization."""
        item1 = DroppedItem(
            item_type=ItemType.REJECTED,
            description="Option B rejected",
            content_hash="xyz",
            original_index=10,
        )
        d = item1.to_dict()
        item2 = DroppedItem.from_dict(d)
        assert item1.item_type == item2.item_type
        assert item1.content_hash == item2.content_hash


class TestTurn:
    """Test Turn dataclass."""

    def test_creation(self):
        """Test basic creation."""
        turn = Turn(role="user", content="Hello!")
        assert turn.role == "user"
        assert turn.content == "Hello!"
        assert turn.timestamp is None
        assert turn.token_estimate == 0

    def test_to_dict(self):
        """Test serialization."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        turn = Turn(
            role="assistant",
            content="Hi there!",
            timestamp=now,
            token_estimate=5,
            metadata={"key": "value"},
        )
        d = turn.to_dict()
        assert d["role"] == "assistant"
        assert d["content"] == "Hi there!"
        assert d["token_estimate"] == 5
        assert d["metadata"] == {"key": "value"}

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "role": "system",
            "content": "You are helpful.",
            "token_estimate": 3,
        }
        turn = Turn.from_dict(data)
        assert turn.role == "system"
        assert turn.content == "You are helpful."

    def test_content_hash(self):
        """Test content hashing."""
        turn1 = Turn(role="user", content="Hello")
        turn2 = Turn(role="user", content="Hello")
        turn3 = Turn(role="assistant", content="Hello")

        assert turn1.content_hash() == turn2.content_hash()
        assert turn1.content_hash() != turn3.content_hash()


class TestConversation:
    """Test Conversation dataclass."""

    def test_creation_empty(self):
        """Test empty creation."""
        conv = Conversation()
        assert conv.turns == []
        assert conv.decisions == []
        assert conv.token_count == 0

    def test_token_count(self):
        """Test token count calculation."""
        conv = Conversation(
            turns=[
                Turn(role="user", content="Hello", token_estimate=10),
                Turn(role="assistant", content="Hi", token_estimate=5),
            ]
        )
        assert conv.token_count == 15

    def test_to_dict(self, sample_conversation):
        """Test serialization."""
        d = sample_conversation.to_dict()
        assert len(d["turns"]) == 5
        assert len(d["decisions"]) == 2
        assert d["intent"] == "Build authentication system"

    def test_from_dict(self, sample_conversation):
        """Test deserialization."""
        d = sample_conversation.to_dict()
        conv = Conversation.from_dict(d)
        assert len(conv.turns) == 5
        assert len(conv.decisions) == 2
        assert conv.intent == "Build authentication system"


# =============================================================================
# Tests: Configuration
# =============================================================================


class TestCompactionConfig:
    """Test CompactionConfig dataclass."""

    def test_defaults(self):
        """Test default values."""
        config = CompactionConfig()
        assert config.context_threshold == 0.8
        assert config.min_turns_before_compact == 20
        assert config.recent_turns_to_keep == 10
        assert config.always_keep_decisions is True
        assert config.always_keep_constraints is True

    def test_to_dict(self):
        """Test serialization."""
        config = CompactionConfig(context_threshold=0.9)
        d = config.to_dict()
        assert d["context_threshold"] == 0.9

    def test_from_dict(self):
        """Test deserialization."""
        data = {"context_threshold": 0.7, "recent_turns_to_keep": 5}
        config = CompactionConfig.from_dict(data)
        assert config.context_threshold == 0.7
        assert config.recent_turns_to_keep == 5

    def test_save_and_load(self, temp_dir):
        """Test save and load."""
        config1 = CompactionConfig(
            context_threshold=0.75,
            min_turns_before_compact=15,
        )
        path = temp_dir / "config.yaml"
        config1.save(path)

        config2 = CompactionConfig.load(path)
        assert config2.context_threshold == 0.75
        assert config2.min_turns_before_compact == 15

    def test_load_nonexistent(self, temp_dir):
        """Test loading nonexistent file returns defaults."""
        config = CompactionConfig.load(temp_dir / "missing.yaml")
        assert config.context_threshold == 0.8


# =============================================================================
# Tests: Receipt
# =============================================================================


class TestCompactionReceipt:
    """Test CompactionReceipt dataclass."""

    def test_creation(self):
        """Test basic creation."""
        receipt = CompactionReceipt(
            receipt_id="abc123",
            compacted_at=datetime(2025, 1, 1, 12, 0, 0),
            preserved_decisions=[{"topic": "test"}],
            preserved_anchors=[],
            preserved_constraints=[],
            preserved_authority={},
            preserved_intent="Test intent",
            preserved_turns_count=5,
            dropped_items=[],
            total_dropped_tokens=100,
            compressed_summary="Summary text",
            compressed_hash="hash123",
        )
        assert receipt.receipt_id == "abc123"
        assert receipt.preserved_turns_count == 5

    def test_to_dict(self):
        """Test serialization."""
        receipt = CompactionReceipt(
            receipt_id="test",
            compacted_at=datetime(2025, 1, 1, 12, 0, 0),
            preserved_decisions=[],
            preserved_anchors=[],
            preserved_constraints=[],
            preserved_authority={},
            preserved_intent=None,
            preserved_turns_count=0,
            dropped_items=[
                DroppedItem(
                    item_type=ItemType.TURN,
                    description="dropped",
                    content_hash="xyz",
                )
            ],
            total_dropped_tokens=50,
            compressed_summary="test",
            compressed_hash="hash",
        )
        d = receipt.to_dict()
        assert d["receipt_id"] == "test"
        assert len(d["dropped_items"]) == 1

    def test_from_dict(self):
        """Test deserialization."""
        data = {
            "receipt_id": "r123",
            "compacted_at": "2025-01-01T12:00:00",
            "preserved_decisions": [{"x": "y"}],
            "preserved_anchors": [],
            "preserved_constraints": [],
            "preserved_authority": {},
            "preserved_intent": "intent",
            "preserved_turns_count": 3,
            "dropped_items": [],
            "total_dropped_tokens": 200,
            "compressed_summary": "sum",
            "compressed_hash": "h",
        }
        receipt = CompactionReceipt.from_dict(data)
        assert receipt.receipt_id == "r123"
        assert receipt.preserved_turns_count == 3

    def test_save_and_load(self, temp_dir):
        """Test save and load."""
        receipt = CompactionReceipt(
            receipt_id="save-test",
            compacted_at=datetime(2025, 1, 1),
            preserved_decisions=[],
            preserved_anchors=[],
            preserved_constraints=[],
            preserved_authority={},
            preserved_intent="test",
            preserved_turns_count=2,
            dropped_items=[],
            total_dropped_tokens=50,
            compressed_summary="summary",
            compressed_hash="hash",
        )
        path = temp_dir / "receipt.json"
        receipt.save(path)

        loaded = CompactionReceipt.load(path)
        assert loaded.receipt_id == "save-test"


# =============================================================================
# Tests: Summarizer
# =============================================================================


class TestSimpleSummarizer:
    """Test SimpleSummarizer."""

    def test_summarize_empty(self):
        """Test summarizing empty inputs."""
        summarizer = SimpleSummarizer()
        summary = summarizer.summarize(
            turns=[],
            decisions=[],
            constraints=[],
            max_tokens=500,
        )
        assert "CONVERSATION CONTEXT" in summary

    def test_summarize_with_decisions(self):
        """Test summarizing with decisions."""
        summarizer = SimpleSummarizer()
        summary = summarizer.summarize(
            turns=[Turn(role="user", content="Start project")],
            decisions=[{"topic": "framework", "choice": "FastAPI"}],
            constraints=[],
            max_tokens=500,
        )
        assert "DECISIONS" in summary
        assert "framework" in summary

    def test_summarize_with_constraints(self):
        """Test summarizing with constraints."""
        summarizer = SimpleSummarizer()
        summary = summarizer.summarize(
            turns=[],
            decisions=[],
            constraints=[{"description": "Use HTTPS only"}],
            max_tokens=500,
        )
        assert "CONSTRAINTS" in summary
        assert "HTTPS" in summary

    def test_summarize_truncation(self):
        """Test that summary is truncated to max tokens."""
        summarizer = SimpleSummarizer()
        summary = summarizer.summarize(
            turns=[Turn(role="user", content="x" * 1000)],
            decisions=[{"topic": f"d{i}", "choice": f"c{i}"} for i in range(100)],
            constraints=[],
            max_tokens=50,
        )
        # 50 tokens ≈ 200 chars
        assert len(summary) <= 250


# =============================================================================
# Tests: Recovery Store
# =============================================================================


class TestRecoveryStore:
    """Test RecoveryStore."""

    def test_store_and_recover(self, temp_dir):
        """Test storing and recovering items."""
        store = RecoveryStore(temp_dir / "recovery")

        item = DroppedItem(
            item_type=ItemType.TURN,
            description="test turn",
            content_hash="hash123",
        )
        store.store("receipt1", [(item, "Full content of the turn")])

        # Recover
        content = store.recover("receipt1", "hash123")
        assert content == "Full content of the turn"

    def test_recover_nonexistent(self, temp_dir):
        """Test recovering nonexistent item returns None."""
        store = RecoveryStore(temp_dir / "recovery")
        content = store.recover("nonexistent", "hash")
        assert content is None

    def test_list_recoverable(self, temp_dir):
        """Test listing recoverable items."""
        store = RecoveryStore(temp_dir / "recovery")

        items = [
            (DroppedItem(ItemType.TURN, "turn 1", "h1"), "content 1"),
            (DroppedItem(ItemType.TURN, "turn 2", "h2"), "content 2"),
        ]
        store.store("receipt2", items)

        recoverable = store.list_recoverable("receipt2")
        assert len(recoverable) == 2

    def test_cleanup_old(self, temp_dir):
        """Test cleanup of old stores."""
        store = RecoveryStore(temp_dir / "recovery")

        # Store something
        item = DroppedItem(ItemType.TURN, "old", "h")
        store.store("old-receipt", [(item, "content")])

        # Should not remove recent stores
        removed = store.cleanup_old(max_age_hours=24)
        assert removed == 0


# =============================================================================
# Tests: Context Compactor
# =============================================================================


class TestContextCompactor:
    """Test ContextCompactor."""

    def test_should_compact_below_threshold(self, sample_conversation):
        """Test should_compact returns False below threshold."""
        config = CompactionConfig(
            context_threshold=0.8,
            min_turns_before_compact=100,  # Too high
        )
        compactor = ContextCompactor(config=config)

        assert compactor.should_compact(sample_conversation) is False

    def test_should_compact_above_threshold(self):
        """Test should_compact returns True above threshold."""
        config = CompactionConfig(
            context_threshold=0.5,
            min_turns_before_compact=5,
        )
        compactor = ContextCompactor(config=config)

        # Create conversation at 60% capacity
        conv = Conversation(
            turns=[Turn(role="user", content="x", token_estimate=60)] * 10,
            context_limit=100,
        )

        assert compactor.should_compact(conv) is True

    def test_get_compaction_status(self, sample_conversation):
        """Test get_compaction_status."""
        compactor = ContextCompactor()
        status = compactor.get_compaction_status(sample_conversation)

        assert "token_count" in status
        assert "usage_percent" in status
        assert "needs_compaction" in status

    def test_preview_compaction(self):
        """Test preview_compaction."""
        config = CompactionConfig(recent_turns_to_keep=3)
        compactor = ContextCompactor(config=config)

        conv = Conversation(
            turns=[Turn(role="user", content=f"Turn {i}", token_estimate=10) for i in range(10)]
        )

        preview = compactor.preview_compaction(conv)
        assert preview["would_compact"] is True
        assert preview["turns_to_keep"] == 3
        assert preview["turns_to_drop"] == 7

    def test_compact_preserves_governance(self, sample_conversation):
        """Test compact preserves governance state."""
        config = CompactionConfig(recent_turns_to_keep=2)
        compactor = ContextCompactor(config=config)

        result = compactor.compact(sample_conversation)

        # Check preservation
        assert len(result.preserved_decisions) == 2
        assert len(result.preserved_anchors) == 1
        assert len(result.preserved_constraints) == 1
        assert result.preserved_intent == "Build authentication system"

    def test_compact_creates_receipt(self, sample_conversation):
        """Test compact creates valid receipt."""
        config = CompactionConfig(recent_turns_to_keep=2)
        compactor = ContextCompactor(config=config)

        result = compactor.compact(sample_conversation)

        assert result.receipt is not None
        assert result.receipt.receipt_id is not None
        assert result.receipt.compacted_at is not None
        assert len(result.receipt.dropped_items) == 3  # 5 - 2 = 3 dropped

    def test_compact_generates_summary(self, sample_conversation):
        """Test compact generates summary."""
        config = CompactionConfig(recent_turns_to_keep=2)
        compactor = ContextCompactor(config=config)

        result = compactor.compact(sample_conversation)

        assert result.summary is not None
        assert len(result.summary) > 0
        assert "DECISIONS" in result.summary

    def test_compact_keeps_recent_turns(self, sample_conversation):
        """Test compact keeps recent turns."""
        config = CompactionConfig(recent_turns_to_keep=3)
        compactor = ContextCompactor(config=config)

        result = compactor.compact(sample_conversation)

        assert len(result.recent_turns) == 3
        # Last 3 turns should be preserved
        assert result.recent_turns[-1].content == sample_conversation.turns[-1].content

    def test_compact_to_conversation(self, sample_conversation):
        """Test converting compacted result back to conversation."""
        config = CompactionConfig(recent_turns_to_keep=2)
        compactor = ContextCompactor(config=config)

        result = compactor.compact(sample_conversation)
        conv = result.to_conversation()

        # Should have summary turn + 2 recent turns
        assert len(conv.turns) == 3
        assert conv.turns[0].role == "system"
        assert "[Context Summary]" in conv.turns[0].content

    def test_compact_with_recovery(self, temp_dir, sample_conversation):
        """Test compact with recovery store."""
        recovery = RecoveryStore(temp_dir / "recovery")
        config = CompactionConfig(
            recent_turns_to_keep=2,
            store_dropped_content=True,
        )
        compactor = ContextCompactor(config=config, recovery_store=recovery)

        result = compactor.compact(sample_conversation)

        # Should be able to recover dropped content
        for item in result.receipt.dropped_items:
            content = compactor.recover_item(result.receipt, item.content_hash)
            assert content is not None


# =============================================================================
# Tests: Receipt Store
# =============================================================================


class TestReceiptStore:
    """Test ReceiptStore."""

    def test_save_and_load(self, temp_dir):
        """Test saving and loading receipts."""
        store = ReceiptStore(temp_dir / "receipts")

        receipt = CompactionReceipt(
            receipt_id="test-receipt",
            compacted_at=datetime(2025, 1, 1),
            preserved_decisions=[],
            preserved_anchors=[],
            preserved_constraints=[],
            preserved_authority={},
            preserved_intent=None,
            preserved_turns_count=0,
            dropped_items=[],
            total_dropped_tokens=0,
            compressed_summary="test",
            compressed_hash="hash",
        )

        store.save(receipt)
        loaded = store.load("test-receipt")

        assert loaded is not None
        assert loaded.receipt_id == "test-receipt"

    def test_list_all(self, temp_dir):
        """Test listing all receipts."""
        store = ReceiptStore(temp_dir / "receipts")

        for i in range(3):
            receipt = CompactionReceipt(
                receipt_id=f"receipt-{i}",
                compacted_at=datetime(2025, 1, 1),
                preserved_decisions=[],
                preserved_anchors=[],
                preserved_constraints=[],
                preserved_authority={},
                preserved_intent=None,
                preserved_turns_count=0,
                dropped_items=[],
                total_dropped_tokens=0,
                compressed_summary="",
                compressed_hash="",
            )
            store.save(receipt)

        all_receipts = store.list_all()
        assert len(all_receipts) == 3

    def test_get_latest(self, temp_dir):
        """Test getting latest receipt."""
        store = ReceiptStore(temp_dir / "receipts")

        for i in range(3):
            receipt = CompactionReceipt(
                receipt_id=f"receipt-{i}",
                compacted_at=datetime(2025, 1, 1, i, 0, 0),
                preserved_decisions=[],
                preserved_anchors=[],
                preserved_constraints=[],
                preserved_authority={},
                preserved_intent=None,
                preserved_turns_count=0,
                dropped_items=[],
                total_dropped_tokens=0,
                compressed_summary="",
                compressed_hash="",
            )
            store.save(receipt)
            import time
            time.sleep(0.01)  # Ensure different mtimes

        latest = store.get_latest()
        assert latest is not None
        # Latest should be receipt-2
        assert latest.receipt_id == "receipt-2"

    def test_load_nonexistent(self, temp_dir):
        """Test loading nonexistent receipt."""
        store = ReceiptStore(temp_dir / "receipts")
        loaded = store.load("nonexistent")
        assert loaded is None


# =============================================================================
# Tests: Convenience Functions
# =============================================================================


class TestConvenienceFunctions:
    """Test module-level convenience functions."""

    def test_create_compactor(self, temp_dir):
        """Test create_compactor."""
        compactor = create_compactor(recovery_path=temp_dir / "recovery")
        assert isinstance(compactor, ContextCompactor)
        assert compactor.recovery_store is not None

    def test_compact_conversation(self, sample_conversation):
        """Test compact_conversation convenience function."""
        result = compact_conversation(sample_conversation)

        assert result is not None
        assert result.receipt is not None
        assert len(result.preserved_decisions) == 2


# =============================================================================
# Tests: Integration
# =============================================================================


class TestIntegration:
    """Integration tests for context compaction."""

    def test_full_compaction_workflow(self, temp_dir):
        """Test complete compaction workflow."""
        # Setup stores
        receipt_store = ReceiptStore(temp_dir / "receipts")
        recovery_store = RecoveryStore(temp_dir / "recovery")

        config = CompactionConfig(
            context_threshold=0.5,
            min_turns_before_compact=5,
            recent_turns_to_keep=3,
            store_dropped_content=True,
        )
        compactor = ContextCompactor(
            config=config,
            recovery_store=recovery_store,
        )

        # Create conversation
        conv = Conversation(
            turns=[Turn(role="user", content=f"Message {i}", token_estimate=10) for i in range(20)],
            decisions=[{"topic": "key", "value": "decision1"}],
            anchors=[{"id": "a1", "desc": "anchor"}],
            constraints=[{"id": "c1", "rule": "constraint"}],
            intent="Test workflow",
            context_limit=100,
        )

        # 1. Check if compaction needed
        assert compactor.should_compact(conv) is True

        # 2. Preview compaction
        preview = compactor.preview_compaction(conv)
        assert preview["turns_to_drop"] == 17

        # 3. Compact
        result = compactor.compact(conv)

        # 4. Save receipt
        receipt_store.save(result.receipt)

        # 5. Verify governance preserved
        assert len(result.preserved_decisions) == 1
        assert len(result.preserved_anchors) == 1
        assert len(result.preserved_constraints) == 1
        assert result.preserved_intent == "Test workflow"

        # 6. Convert back to conversation
        new_conv = result.to_conversation()
        assert len(new_conv.turns) == 4  # summary + 3 recent

        # 7. Recover dropped content
        for item in result.receipt.dropped_items:
            content = compactor.recover_item(result.receipt, item.content_hash)
            assert content is not None

        # 8. List receipts
        receipts = receipt_store.list_all()
        assert len(receipts) == 1

    def test_multiple_compactions(self, temp_dir):
        """Test multiple compaction rounds."""
        receipt_store = ReceiptStore(temp_dir / "receipts")
        config = CompactionConfig(recent_turns_to_keep=3)
        compactor = ContextCompactor(config=config)

        # First compaction
        conv1 = Conversation(
            turns=[Turn(role="user", content=f"Round 1 - {i}", token_estimate=10) for i in range(10)],
            decisions=[{"round": 1}],
        )
        result1 = compactor.compact(conv1)
        receipt_store.save(result1.receipt)

        # Second compaction (simulate continued conversation)
        conv2 = result1.to_conversation()
        for i in range(10):
            conv2.turns.append(Turn(role="user", content=f"Round 2 - {i}", token_estimate=10))
        conv2.decisions.append({"round": 2})

        result2 = compactor.compact(conv2)
        receipt_store.save(result2.receipt)

        # Check both rounds preserved decisions
        assert len(result2.preserved_decisions) == 2

        # Check both receipts stored
        assert len(receipt_store.list_all()) == 2

    def test_compaction_preserves_hash_consistency(self, sample_conversation):
        """Test that same content produces same hash."""
        config = CompactionConfig(recent_turns_to_keep=2)
        compactor = ContextCompactor(config=config)

        # Compact twice
        result1 = compactor.compact(sample_conversation)
        result2 = compactor.compact(sample_conversation)

        # Same summary should produce same hash
        assert result1.receipt.compressed_hash == result2.receipt.compressed_hash

        # But receipt IDs should be different
        assert result1.receipt.receipt_id != result2.receipt.receipt_id
