"""Governed Compact — loss-aware context compaction with receipts.

Context compaction is dangerous. Done carelessly, it creates representational
shear — the system believes it knows things it has silently forgotten.

This module implements governed compact: loss-aware summarization that emits
receipts, respects anchors, and never silently drops governance state.

Core principle: If you compact without knowing what you lost, you've created a lie.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol
import yaml


def _utcnow() -> datetime:
    """Get current UTC time."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _sha256(content: str) -> str:
    """Compute SHA-256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()


# =============================================================================
# Types
# =============================================================================


class ItemType(str, Enum):
    """Type of dropped item."""
    TURN = "turn"
    REASONING = "reasoning"
    EXPLORATION = "exploration"
    REJECTED = "rejected"


@dataclass
class DroppedItem:
    """Record of dropped content."""
    item_type: ItemType
    description: str
    content_hash: str
    recoverable: bool = True
    original_index: int | None = None

    def to_dict(self) -> dict:
        return {
            "item_type": self.item_type.value,
            "description": self.description,
            "content_hash": self.content_hash,
            "recoverable": self.recoverable,
            "original_index": self.original_index,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DroppedItem":
        return cls(
            item_type=ItemType(data["item_type"]),
            description=data["description"],
            content_hash=data["content_hash"],
            recoverable=data.get("recoverable", True),
            original_index=data.get("original_index"),
        )


@dataclass
class Turn:
    """A conversation turn."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime | None = None
    token_estimate: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "token_estimate": self.token_estimate,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Turn":
        timestamp = None
        if data.get("timestamp"):
            timestamp = datetime.fromisoformat(data["timestamp"])
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=timestamp,
            token_estimate=data.get("token_estimate", 0),
            metadata=data.get("metadata", {}),
        )

    def content_hash(self) -> str:
        """Compute hash of turn content."""
        return _sha256(f"{self.role}:{self.content}")


@dataclass
class Conversation:
    """A conversation with turns and governance state."""
    turns: list[Turn] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    anchors: list[dict] = field(default_factory=list)
    constraints: list[dict] = field(default_factory=list)
    authority: dict = field(default_factory=dict)
    intent: str | None = None
    context_limit: int = 100000  # Default token limit

    @property
    def token_count(self) -> int:
        """Estimate total token count."""
        return sum(t.token_estimate for t in self.turns)

    def to_dict(self) -> dict:
        return {
            "turns": [t.to_dict() for t in self.turns],
            "decisions": self.decisions,
            "anchors": self.anchors,
            "constraints": self.constraints,
            "authority": self.authority,
            "intent": self.intent,
            "context_limit": self.context_limit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Conversation":
        return cls(
            turns=[Turn.from_dict(t) for t in data.get("turns", [])],
            decisions=data.get("decisions", []),
            anchors=data.get("anchors", []),
            constraints=data.get("constraints", []),
            authority=data.get("authority", {}),
            intent=data.get("intent"),
            context_limit=data.get("context_limit", 100000),
        )


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class CompactionConfig:
    """Configuration for governed compaction."""
    # When to trigger
    context_threshold: float = 0.8  # Trigger at 80% of limit
    min_turns_before_compact: int = 20

    # What must survive (non-negotiable)
    recent_turns_to_keep: int = 10
    always_keep_decisions: bool = True
    always_keep_constraints: bool = True
    always_keep_anchors: bool = True

    # Summary settings
    summary_max_tokens: int = 500
    include_key_facts: bool = True
    include_rejected_summary: bool = True

    # Recovery settings
    store_dropped_content: bool = True
    dropped_content_ttl_hours: int = 24

    def to_dict(self) -> dict:
        return {
            "context_threshold": self.context_threshold,
            "min_turns_before_compact": self.min_turns_before_compact,
            "recent_turns_to_keep": self.recent_turns_to_keep,
            "always_keep_decisions": self.always_keep_decisions,
            "always_keep_constraints": self.always_keep_constraints,
            "always_keep_anchors": self.always_keep_anchors,
            "summary_max_tokens": self.summary_max_tokens,
            "include_key_facts": self.include_key_facts,
            "include_rejected_summary": self.include_rejected_summary,
            "store_dropped_content": self.store_dropped_content,
            "dropped_content_ttl_hours": self.dropped_content_ttl_hours,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompactionConfig":
        return cls(
            context_threshold=data.get("context_threshold", 0.8),
            min_turns_before_compact=data.get("min_turns_before_compact", 20),
            recent_turns_to_keep=data.get("recent_turns_to_keep", 10),
            always_keep_decisions=data.get("always_keep_decisions", True),
            always_keep_constraints=data.get("always_keep_constraints", True),
            always_keep_anchors=data.get("always_keep_anchors", True),
            summary_max_tokens=data.get("summary_max_tokens", 500),
            include_key_facts=data.get("include_key_facts", True),
            include_rejected_summary=data.get("include_rejected_summary", True),
            store_dropped_content=data.get("store_dropped_content", True),
            dropped_content_ttl_hours=data.get("dropped_content_ttl_hours", 24),
        )

    def save(self, path: Path) -> None:
        """Save configuration to YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False)

    @classmethod
    def load(cls, path: Path) -> "CompactionConfig":
        """Load configuration from YAML file."""
        if not path.exists():
            return cls()
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return cls.from_dict(data)


# =============================================================================
# Compaction Receipt
# =============================================================================


@dataclass
class CompactionReceipt:
    """Receipt proving what was preserved vs dropped."""
    receipt_id: str
    compacted_at: datetime

    # What survived (verbatim)
    preserved_decisions: list[dict]
    preserved_anchors: list[dict]
    preserved_constraints: list[dict]
    preserved_authority: dict
    preserved_intent: str | None
    preserved_turns_count: int

    # What was dropped (with hashes for recovery)
    dropped_items: list[DroppedItem]
    total_dropped_tokens: int

    # What was compressed (summary available)
    compressed_summary: str
    compressed_hash: str

    # Recovery info
    recovery_store_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "compacted_at": self.compacted_at.isoformat(),
            "preserved_decisions": self.preserved_decisions,
            "preserved_anchors": self.preserved_anchors,
            "preserved_constraints": self.preserved_constraints,
            "preserved_authority": self.preserved_authority,
            "preserved_intent": self.preserved_intent,
            "preserved_turns_count": self.preserved_turns_count,
            "dropped_items": [d.to_dict() for d in self.dropped_items],
            "total_dropped_tokens": self.total_dropped_tokens,
            "compressed_summary": self.compressed_summary,
            "compressed_hash": self.compressed_hash,
            "recovery_store_path": self.recovery_store_path,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CompactionReceipt":
        return cls(
            receipt_id=data["receipt_id"],
            compacted_at=datetime.fromisoformat(data["compacted_at"]),
            preserved_decisions=data.get("preserved_decisions", []),
            preserved_anchors=data.get("preserved_anchors", []),
            preserved_constraints=data.get("preserved_constraints", []),
            preserved_authority=data.get("preserved_authority", {}),
            preserved_intent=data.get("preserved_intent"),
            preserved_turns_count=data.get("preserved_turns_count", 0),
            dropped_items=[DroppedItem.from_dict(d) for d in data.get("dropped_items", [])],
            total_dropped_tokens=data.get("total_dropped_tokens", 0),
            compressed_summary=data.get("compressed_summary", ""),
            compressed_hash=data.get("compressed_hash", ""),
            recovery_store_path=data.get("recovery_store_path"),
        )

    def save(self, path: Path) -> None:
        """Save receipt to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "CompactionReceipt":
        """Load receipt from JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)


# =============================================================================
# Compacted Conversation
# =============================================================================


@dataclass
class CompactedConversation:
    """Result of compaction."""
    summary: str
    recent_turns: list[Turn]
    preserved_decisions: list[dict]
    preserved_anchors: list[dict]
    preserved_constraints: list[dict]
    preserved_authority: dict
    preserved_intent: str | None
    receipt: CompactionReceipt

    def to_conversation(self) -> Conversation:
        """Convert back to a regular conversation."""
        # Create summary turn
        summary_turn = Turn(
            role="system",
            content=f"[Context Summary]\n{self.summary}",
            timestamp=_utcnow(),
            metadata={"is_summary": True, "receipt_id": self.receipt.receipt_id},
        )
        # Estimate token count for summary
        summary_turn.token_estimate = len(self.summary) // 4

        return Conversation(
            turns=[summary_turn] + self.recent_turns,
            decisions=self.preserved_decisions,
            anchors=self.preserved_anchors,
            constraints=self.preserved_constraints,
            authority=self.preserved_authority,
            intent=self.preserved_intent,
        )

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "recent_turns": [t.to_dict() for t in self.recent_turns],
            "preserved_decisions": self.preserved_decisions,
            "preserved_anchors": self.preserved_anchors,
            "preserved_constraints": self.preserved_constraints,
            "preserved_authority": self.preserved_authority,
            "preserved_intent": self.preserved_intent,
            "receipt": self.receipt.to_dict(),
        }


# =============================================================================
# Summarizer Protocol
# =============================================================================


class Summarizer(Protocol):
    """Protocol for generating summaries."""

    def summarize(
        self,
        turns: list[Turn],
        decisions: list[dict],
        constraints: list[dict],
        max_tokens: int,
    ) -> str:
        """Generate a summary of the conversation."""
        ...


class SimpleSummarizer:
    """Simple summarizer that extracts key information."""

    def summarize(
        self,
        turns: list[Turn],
        decisions: list[dict],
        constraints: list[dict],
        max_tokens: int,
    ) -> str:
        """Generate a simple summary."""
        parts = []

        # Summarize decisions
        if decisions:
            parts.append("DECISIONS:")
            for d in decisions[:10]:  # Cap at 10
                if isinstance(d, dict):
                    parts.append(f"  - {d.get('topic', 'unknown')}: {d.get('choice', d.get('value', '?'))}")
                else:
                    parts.append(f"  - {d}")

        # Summarize constraints
        if constraints:
            parts.append("\nACTIVE CONSTRAINTS:")
            for c in constraints[:10]:
                if isinstance(c, dict):
                    parts.append(f"  - {c.get('description', c.get('id', '?'))}")
                else:
                    parts.append(f"  - {c}")

        # Extract key exchanges (first user message, any marked as important)
        parts.append("\nCONVERSATION CONTEXT:")
        user_turns = [t for t in turns if t.role == "user"]
        if user_turns:
            parts.append(f"  Initial request: {user_turns[0].content[:200]}...")

        # Count turns by role
        role_counts = {}
        for t in turns:
            role_counts[t.role] = role_counts.get(t.role, 0) + 1
        parts.append(f"\n  Total exchanges: {len(turns)} turns ({role_counts})")

        summary = "\n".join(parts)

        # Truncate to max tokens (rough estimate: 4 chars per token)
        max_chars = max_tokens * 4
        if len(summary) > max_chars:
            summary = summary[:max_chars] + "... [truncated]"

        return summary


# =============================================================================
# Recovery Store
# =============================================================================


class RecoveryStore:
    """Store for dropped content, enabling later recovery."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def store(self, receipt_id: str, items: list[tuple[DroppedItem, str]]) -> None:
        """Store dropped items for later recovery."""
        store_path = self.base_path / receipt_id
        store_path.mkdir(exist_ok=True)

        index = []
        for item, content in items:
            # Store content
            content_path = store_path / f"{item.content_hash}.txt"
            content_path.write_text(content)

            # Add to index
            index.append({
                "item": item.to_dict(),
                "content_path": str(content_path.relative_to(store_path)),
            })

        # Store index
        index_path = store_path / "index.json"
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)

    def recover(self, receipt_id: str, content_hash: str) -> str | None:
        """Recover dropped content by hash."""
        content_path = self.base_path / receipt_id / f"{content_hash}.txt"
        if content_path.exists():
            return content_path.read_text()
        return None

    def list_recoverable(self, receipt_id: str) -> list[DroppedItem]:
        """List all recoverable items for a receipt."""
        index_path = self.base_path / receipt_id / "index.json"
        if not index_path.exists():
            return []

        with open(index_path) as f:
            index = json.load(f)

        return [DroppedItem.from_dict(entry["item"]) for entry in index]

    def cleanup_old(self, max_age_hours: int) -> int:
        """Remove recovery stores older than max_age_hours. Returns count removed."""
        removed = 0
        cutoff = _utcnow()
        from datetime import timedelta
        cutoff = cutoff - timedelta(hours=max_age_hours)

        for store_dir in self.base_path.iterdir():
            if not store_dir.is_dir():
                continue

            # Check modification time
            mtime = datetime.fromtimestamp(store_dir.stat().st_mtime)
            if mtime < cutoff:
                import shutil
                shutil.rmtree(store_dir)
                removed += 1

        return removed


# =============================================================================
# Context Compactor
# =============================================================================


class ContextCompactor:
    """Main compactor with governed, loss-aware summarization."""

    def __init__(
        self,
        config: CompactionConfig | None = None,
        summarizer: Summarizer | None = None,
        recovery_store: RecoveryStore | None = None,
    ):
        self.config = config or CompactionConfig()
        self.summarizer = summarizer or SimpleSummarizer()
        self.recovery_store = recovery_store

    def should_compact(self, conversation: Conversation) -> bool:
        """Check if compaction is needed."""
        if len(conversation.turns) < self.config.min_turns_before_compact:
            return False

        usage = conversation.token_count / conversation.context_limit
        return usage >= self.config.context_threshold

    def get_compaction_status(self, conversation: Conversation) -> dict:
        """Get current compaction status."""
        usage = conversation.token_count / conversation.context_limit
        return {
            "token_count": conversation.token_count,
            "context_limit": conversation.context_limit,
            "usage_percent": usage * 100,
            "turn_count": len(conversation.turns),
            "needs_compaction": self.should_compact(conversation),
            "threshold_percent": self.config.context_threshold * 100,
            "min_turns": self.config.min_turns_before_compact,
        }

    def preview_compaction(self, conversation: Conversation) -> dict:
        """Preview what would be compacted without actually doing it."""
        keep_count = self.config.recent_turns_to_keep
        drop_count = len(conversation.turns) - keep_count

        if drop_count <= 0:
            return {
                "would_compact": False,
                "reason": "Not enough turns to compact",
            }

        dropped_turns = conversation.turns[:-keep_count] if keep_count > 0 else conversation.turns
        dropped_tokens = sum(t.token_estimate for t in dropped_turns)

        return {
            "would_compact": True,
            "turns_to_keep": keep_count,
            "turns_to_drop": drop_count,
            "tokens_to_drop": dropped_tokens,
            "decisions_preserved": len(conversation.decisions),
            "anchors_preserved": len(conversation.anchors),
            "constraints_preserved": len(conversation.constraints),
        }

    def compact(self, conversation: Conversation) -> CompactedConversation:
        """Compact conversation with loss-aware summarization."""
        import uuid

        receipt_id = str(uuid.uuid4())[:8]
        compacted_at = _utcnow()

        # Determine what to keep
        keep_count = self.config.recent_turns_to_keep
        recent_turns = conversation.turns[-keep_count:] if keep_count > 0 else []
        dropped_turns = conversation.turns[:-keep_count] if keep_count > 0 else conversation.turns

        # Create dropped items with hashes
        dropped_items: list[DroppedItem] = []
        dropped_content: list[tuple[DroppedItem, str]] = []
        total_dropped_tokens = 0

        for i, turn in enumerate(dropped_turns):
            item = DroppedItem(
                item_type=ItemType.TURN,
                description=f"{turn.role}: {turn.content[:50]}...",
                content_hash=turn.content_hash(),
                recoverable=self.config.store_dropped_content,
                original_index=i,
            )
            dropped_items.append(item)
            dropped_content.append((item, f"{turn.role}: {turn.content}"))
            total_dropped_tokens += turn.token_estimate

        # Generate summary
        summary = self.summarizer.summarize(
            turns=dropped_turns,
            decisions=conversation.decisions,
            constraints=conversation.constraints,
            max_tokens=self.config.summary_max_tokens,
        )
        summary_hash = _sha256(summary)

        # Store dropped content if configured
        recovery_path = None
        if self.config.store_dropped_content and self.recovery_store:
            self.recovery_store.store(receipt_id, dropped_content)
            recovery_path = str(self.recovery_store.base_path / receipt_id)

        # Create receipt
        receipt = CompactionReceipt(
            receipt_id=receipt_id,
            compacted_at=compacted_at,
            preserved_decisions=conversation.decisions.copy() if self.config.always_keep_decisions else [],
            preserved_anchors=conversation.anchors.copy() if self.config.always_keep_anchors else [],
            preserved_constraints=conversation.constraints.copy() if self.config.always_keep_constraints else [],
            preserved_authority=conversation.authority.copy(),
            preserved_intent=conversation.intent,
            preserved_turns_count=len(recent_turns),
            dropped_items=dropped_items,
            total_dropped_tokens=total_dropped_tokens,
            compressed_summary=summary,
            compressed_hash=summary_hash,
            recovery_store_path=recovery_path,
        )

        return CompactedConversation(
            summary=summary,
            recent_turns=recent_turns,
            preserved_decisions=receipt.preserved_decisions,
            preserved_anchors=receipt.preserved_anchors,
            preserved_constraints=receipt.preserved_constraints,
            preserved_authority=receipt.preserved_authority,
            preserved_intent=receipt.preserved_intent,
            receipt=receipt,
        )

    def recover_item(self, receipt: CompactionReceipt, content_hash: str) -> str | None:
        """Recover a dropped item by its content hash."""
        if not self.recovery_store or not receipt.recovery_store_path:
            return None
        return self.recovery_store.recover(receipt.receipt_id, content_hash)


# =============================================================================
# Receipt Store
# =============================================================================


class ReceiptStore:
    """Store for compaction receipts."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def save(self, receipt: CompactionReceipt) -> Path:
        """Save receipt and return path."""
        path = self.base_path / f"{receipt.receipt_id}.json"
        receipt.save(path)
        return path

    def load(self, receipt_id: str) -> CompactionReceipt | None:
        """Load receipt by ID."""
        path = self.base_path / f"{receipt_id}.json"
        if not path.exists():
            return None
        return CompactionReceipt.load(path)

    def list_all(self) -> list[str]:
        """List all receipt IDs."""
        return [p.stem for p in self.base_path.glob("*.json")]

    def get_latest(self) -> CompactionReceipt | None:
        """Get the most recent receipt."""
        receipts = list(self.base_path.glob("*.json"))
        if not receipts:
            return None
        latest = max(receipts, key=lambda p: p.stat().st_mtime)
        return CompactionReceipt.load(latest)


# =============================================================================
# Module-Level Convenience
# =============================================================================


def create_compactor(
    config_path: Path | None = None,
    recovery_path: Path | None = None,
) -> ContextCompactor:
    """Create a configured context compactor."""
    config = CompactionConfig.load(config_path) if config_path else CompactionConfig()
    recovery_store = RecoveryStore(recovery_path) if recovery_path else None
    return ContextCompactor(config=config, recovery_store=recovery_store)


def compact_conversation(
    conversation: Conversation,
    config: CompactionConfig | None = None,
) -> CompactedConversation:
    """Convenience function to compact a conversation."""
    compactor = ContextCompactor(config=config)
    return compactor.compact(conversation)
