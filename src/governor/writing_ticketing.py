# SPDX-License-Identifier: Apache-2.0
"""
Writing Ticketing — Making Failures First-Class Citizens.

Ticketing is the shared abstraction between discourse and code. It transforms
governance failures, trust collapses, and constraint violations from vibes
into explicit, trackable objects.

Core Insight: If something keeps failing but we never instantiate it as an
object, the system can't learn.

Design Principle: No correction without a ticket. If it isn't worth naming,
it isn't worth fixing.

Default State: Disabled. Ticketing is infrastructure, not mandatory process.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# =============================================================================
# Ticket Types
# =============================================================================


class ProseTicketType(str, Enum):
    """Ticket types for prose/discourse violations."""

    GOV_VISIBILITY_LEAK = "GOV_VISIBILITY_LEAK"       # governance showed in-band
    REGIME_COLLISION = "REGIME_COLLISION"             # incompatible regimes active
    PREMATURE_CLOSURE = "PREMATURE_CLOSURE"           # synthesis before constraint surface
    TONE_GOVERNANCE_LEAK = "TONE_GOVERNANCE_LEAK"     # fear leaked through tone
    COMMITMENT_VIOLATION = "COMMITMENT_VIOLATION"     # asked for more than earned
    AUDIENCE_MISMATCH = "AUDIENCE_MISMATCH"           # wrong model of reader
    EXIT_SHAPE_VIOLATION = "EXIT_SHAPE_VIOLATION"     # bad ending pattern
    PHASE_LOCK_FAILURE = "PHASE_LOCK_FAILURE"         # timing window missed
    UNJUSTIFIED_NORMATIVITY = "UNJUSTIFIED_NORMATIVITY"  # should/must without foundation
    TYPE_ERROR = "TYPE_ERROR"                         # category mismatch in discourse
    AUTHORITY_MISMATCH = "AUTHORITY_MISMATCH"         # claimed vs demonstrated authority
    REPETITION_VIOLATION = "REPETITION_VIOLATION"     # wrong repetition for regime
    LEGIBILITY_OVERRUN = "LEGIBILITY_OVERRUN"         # spent budget on unrequested explanation
    META_INVARIANT_VIOLATION = "META_INVARIANT_VIOLATION"  # solved problem reader hadn't felt


class CodeTicketType(str, Enum):
    """Ticket types for code/SRE violations."""

    UNOWNED_LIABILITY = "UNOWNED_LIABILITY"           # accountability unclear
    MISSING_INVARIANT = "MISSING_INVARIANT"           # constraint not enforced
    HIDDEN_GOVERNANCE = "HIDDEN_GOVERNANCE"           # constraints not visible/local
    FAILURE_SURFACE_HIDDEN = "FAILURE_SURFACE_HIDDEN"  # error handling smeared
    PREMATURE_ABSTRACTION = "PREMATURE_ABSTRACTION"   # generalized before concrete uses
    MAGIC_BEHAVIOR = "MAGIC_BEHAVIOR"                 # implicit config/state
    EXCEPTION_SMEAR = "EXCEPTION_SMEAR"               # broad catch, swallowed errors
    SCOPE_VIOLATION = "SCOPE_VIOLATION"               # output exceeds ticket scope
    ROLLBACK_GAP = "ROLLBACK_GAP"                     # no rollback path defined
    OBSERVABILITY_GAP = "OBSERVABILITY_GAP"           # no signals for failure mode
    PHASE_LOCK_FAILURE = "PHASE_LOCK_FAILURE"         # observability→mitigation timing broken


# Combined type alias
TicketType = ProseTicketType | CodeTicketType


def parse_ticket_type(value: str) -> TicketType:
    """Parse a string into a TicketType."""
    try:
        return ProseTicketType(value)
    except ValueError:
        return CodeTicketType(value)


# =============================================================================
# Ticket Status
# =============================================================================


class TicketStatus(str, Enum):
    """Ticket lifecycle states."""

    OPEN = "open"               # just created
    ACKNOWLEDGED = "acknowledged"  # human saw it
    FIXED = "fixed"             # resolved
    WONT_FIX = "wont_fix"       # intentionally not fixing
    DUPLICATE = "duplicate"     # same as another ticket


class TicketSeverity(str, Enum):
    """Ticket severity levels."""

    INFO = "info"
    WARNING = "warning"
    VIOLATION = "violation"
    CRITICAL = "critical"


# Severity to numeric for comparison
SEVERITY_ORDER = [
    TicketSeverity.INFO,
    TicketSeverity.WARNING,
    TicketSeverity.VIOLATION,
    TicketSeverity.CRITICAL,
]


def severity_level(severity: TicketSeverity) -> int:
    """Get numeric level for severity comparison."""
    return SEVERITY_ORDER.index(severity)


# =============================================================================
# Ticket Domain
# =============================================================================


class TicketDomain(str, Enum):
    """Domain where the ticket applies."""

    PROSE = "prose"
    CODE = "code"


# =============================================================================
# Ticket Schema
# =============================================================================


@dataclass
class Ticket:
    """Core ticket schema.

    Represents a governance failure, trust collapse, or constraint violation
    as an explicit, trackable object.
    """

    # Identity
    id: str
    created_at: float  # timestamp
    updated_at: float  # timestamp

    # Classification
    type: TicketType
    regime: str                    # which regime was active
    domain: TicketDomain
    severity: TicketSeverity

    # Content
    violated_invariant: str        # which rule was broken
    description: str               # human-readable summary
    context_slice: str             # relevant portion of input/output
    reproduction_hint: str = ""    # how to trigger this again

    # Relationships
    parent_ticket: str | None = None   # if this is a recurrence
    related_tickets: list[str] = field(default_factory=list)

    # Resolution
    status: TicketStatus = TicketStatus.OPEN
    resolution: str = ""           # how it was resolved
    closed_at: float | None = None

    # Metadata
    tags: list[str] = field(default_factory=list)
    source: str = "auto"           # "auto" or "manual"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "type": self.type.value if isinstance(self.type, Enum) else self.type,
            "regime": self.regime,
            "domain": self.domain.value,
            "severity": self.severity.value,
            "violated_invariant": self.violated_invariant,
            "description": self.description,
            "context_slice": self.context_slice,
            "reproduction_hint": self.reproduction_hint,
            "parent_ticket": self.parent_ticket,
            "related_tickets": self.related_tickets,
            "status": self.status.value,
            "resolution": self.resolution,
            "closed_at": self.closed_at,
            "tags": self.tags,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Ticket:
        return cls(
            id=d["id"],
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            type=parse_ticket_type(d["type"]),
            regime=d["regime"],
            domain=TicketDomain(d["domain"]),
            severity=TicketSeverity(d["severity"]),
            violated_invariant=d["violated_invariant"],
            description=d["description"],
            context_slice=d["context_slice"],
            reproduction_hint=d.get("reproduction_hint", ""),
            parent_ticket=d.get("parent_ticket"),
            related_tickets=d.get("related_tickets", []),
            status=TicketStatus(d.get("status", "open")),
            resolution=d.get("resolution", ""),
            closed_at=d.get("closed_at"),
            tags=d.get("tags", []),
            source=d.get("source", "auto"),
        )


# =============================================================================
# Ticket Configuration
# =============================================================================


class RetentionPolicy(str, Enum):
    """How long to keep tickets."""

    SESSION = "session"       # discard at session end
    PERSISTENT = "persistent"  # keep across sessions
    EPHEMERAL = "ephemeral"   # discard immediately after routing


@dataclass
class TicketingConfig:
    """Configuration for the ticketing layer."""

    enabled: bool = False                    # default: disabled
    auto_create: bool = True                 # create tickets automatically on violation
    require_ticket_for_fix: bool = True      # no correction without ticket
    link_recurring: bool = True              # detect and link similar violations
    retention_policy: RetentionPolicy = RetentionPolicy.SESSION

    # Thresholds
    similarity_threshold: float = 0.7        # for recurrence detection
    recurrence_escalation_thresholds: dict[str, int] = field(default_factory=lambda: {
        "info": 10,
        "warning": 5,
        "violation": 3,
        "critical": 1,
    })

    # Context limits
    max_context_slice_length: int = 1000

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "auto_create": self.auto_create,
            "require_ticket_for_fix": self.require_ticket_for_fix,
            "link_recurring": self.link_recurring,
            "retention_policy": self.retention_policy.value,
            "similarity_threshold": self.similarity_threshold,
            "recurrence_escalation_thresholds": self.recurrence_escalation_thresholds,
            "max_context_slice_length": self.max_context_slice_length,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TicketingConfig:
        return cls(
            enabled=d.get("enabled", False),
            auto_create=d.get("auto_create", True),
            require_ticket_for_fix=d.get("require_ticket_for_fix", True),
            link_recurring=d.get("link_recurring", True),
            retention_policy=RetentionPolicy(d.get("retention_policy", "session")),
            similarity_threshold=d.get("similarity_threshold", 0.7),
            recurrence_escalation_thresholds=d.get("recurrence_escalation_thresholds", {
                "info": 10, "warning": 5, "violation": 3, "critical": 1,
            }),
            max_context_slice_length=d.get("max_context_slice_length", 1000),
        )


# Default configuration
DEFAULT_TICKETING_CONFIG = TicketingConfig()


# =============================================================================
# Violation Detection Input
# =============================================================================


@dataclass
class ViolationDetection:
    """Input for ticket creation from a detected violation."""

    type: TicketType
    regime: str
    domain: TicketDomain
    invariant: str
    context: str
    severity: float = 0.5  # 0.0 - 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value if isinstance(self.type, Enum) else self.type,
            "regime": self.regime,
            "domain": self.domain.value,
            "invariant": self.invariant,
            "context": self.context,
            "severity": self.severity,
        }


def map_severity(severity_float: float) -> TicketSeverity:
    """Map a float severity (0.0-1.0) to TicketSeverity."""
    if severity_float < 0.25:
        return TicketSeverity.INFO
    elif severity_float < 0.5:
        return TicketSeverity.WARNING
    elif severity_float < 0.75:
        return TicketSeverity.VIOLATION
    else:
        return TicketSeverity.CRITICAL


# =============================================================================
# Routing Actions
# =============================================================================


class RoutingActionType(str, Enum):
    """Types of routing actions."""

    SUPPRESS = "suppress"
    ADJUST = "adjust"
    ESCALATE = "escalate"
    LOG = "log"
    RETRY = "retry"


@dataclass
class RoutingAction:
    """Action to take after ticket creation."""

    action: RoutingActionType
    reason: str = ""
    adjustment: dict[str, Any] | None = None  # for ADJUST
    escalate_to: str = ""  # for ESCALATE: "human" or "review_queue"
    log_for: str = ""  # for LOG: "learning" or "audit"
    retry_strategy: dict[str, Any] | None = None  # for RETRY

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "adjustment": self.adjustment,
            "escalate_to": self.escalate_to,
            "log_for": self.log_for,
            "retry_strategy": self.retry_strategy,
        }


# =============================================================================
# Ticket Transitions
# =============================================================================


@dataclass
class TicketTransition:
    """A valid state transition for tickets."""

    from_status: TicketStatus
    to_status: TicketStatus
    requires: str  # "auto" or "human"


# Valid transitions per the spec
ALLOWED_TRANSITIONS: list[TicketTransition] = [
    TicketTransition(TicketStatus.OPEN, TicketStatus.ACKNOWLEDGED, "human"),
    TicketTransition(TicketStatus.OPEN, TicketStatus.FIXED, "auto"),
    TicketTransition(TicketStatus.OPEN, TicketStatus.DUPLICATE, "auto"),
    TicketTransition(TicketStatus.ACKNOWLEDGED, TicketStatus.FIXED, "auto"),
    TicketTransition(TicketStatus.ACKNOWLEDGED, TicketStatus.WONT_FIX, "human"),
    TicketTransition(TicketStatus.ACKNOWLEDGED, TicketStatus.DUPLICATE, "auto"),
]


def is_valid_transition(
    from_status: TicketStatus,
    to_status: TicketStatus,
    actor: str = "auto",
) -> bool:
    """Check if a status transition is valid."""
    for t in ALLOWED_TRANSITIONS:
        if t.from_status == from_status and t.to_status == to_status:
            # Auto can always transition, human can do anything
            if actor == "human" or t.requires == "auto":
                return True
            return actor == t.requires
    return False


# =============================================================================
# Similarity Matching
# =============================================================================


def tokenize(text: str) -> set[str]:
    """Simple tokenization for similarity matching."""
    # Lowercase, split on non-alphanumeric
    tokens = re.findall(r'\w+', text.lower())
    return set(tokens)


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


@dataclass
class SimilarityResult:
    """Result of similarity comparison."""

    ticket: Ticket
    similarity: float
    same_type: bool
    same_regime: bool
    same_invariant: bool
    context_similarity: float


def calculate_similarity(
    detection: ViolationDetection,
    ticket: Ticket,
) -> SimilarityResult:
    """Calculate similarity between a detection and an existing ticket."""
    same_type = detection.type == ticket.type
    same_regime = detection.regime == ticket.regime
    same_invariant = detection.invariant == ticket.violated_invariant

    context_sim = jaccard_similarity(
        tokenize(detection.context),
        tokenize(ticket.context_slice),
    )

    # Weighted similarity score
    score = 0.0
    if same_type:
        score += 0.4
    if same_regime:
        score += 0.2
    if same_invariant:
        score += 0.3
    score += context_sim * 0.1

    return SimilarityResult(
        ticket=ticket,
        similarity=score,
        same_type=same_type,
        same_regime=same_regime,
        same_invariant=same_invariant,
        context_similarity=context_sim,
    )


def find_similar_tickets(
    detection: ViolationDetection,
    history: list[Ticket],
    threshold: float = 0.7,
) -> list[Ticket]:
    """Find tickets similar to a detection."""
    results = []
    for ticket in history:
        # Skip fixed tickets
        if ticket.status == TicketStatus.FIXED:
            continue

        similarity = calculate_similarity(detection, ticket)
        if similarity.similarity >= threshold:
            results.append((similarity.similarity, ticket))

    # Sort by similarity descending
    results.sort(key=lambda x: x[0], reverse=True)
    return [ticket for _, ticket in results]


# =============================================================================
# Ticket Store
# =============================================================================


class TicketStore:
    """In-memory ticket storage with optional persistence hooks."""

    def __init__(self, retention_policy: RetentionPolicy = RetentionPolicy.SESSION):
        self._tickets: dict[str, Ticket] = {}
        self._retention_policy = retention_policy
        self._persistence_hook: Callable[[Ticket], None] | None = None

    def add(self, ticket: Ticket) -> None:
        """Add a ticket to the store."""
        self._tickets[ticket.id] = ticket
        if self._persistence_hook and self._retention_policy == RetentionPolicy.PERSISTENT:
            self._persistence_hook(ticket)

    def get(self, ticket_id: str) -> Ticket | None:
        """Get a ticket by ID."""
        return self._tickets.get(ticket_id)

    def update(self, ticket: Ticket) -> None:
        """Update a ticket in the store."""
        ticket.updated_at = time.time()
        self._tickets[ticket.id] = ticket
        if self._persistence_hook and self._retention_policy == RetentionPolicy.PERSISTENT:
            self._persistence_hook(ticket)

    def all(self) -> list[Ticket]:
        """Get all tickets."""
        return list(self._tickets.values())

    def open_tickets(self) -> list[Ticket]:
        """Get all open tickets."""
        return [t for t in self._tickets.values() if t.status == TicketStatus.OPEN]

    def by_type(self, ticket_type: TicketType) -> list[Ticket]:
        """Get tickets by type."""
        return [t for t in self._tickets.values() if t.type == ticket_type]

    def by_regime(self, regime: str) -> list[Ticket]:
        """Get tickets by regime."""
        return [t for t in self._tickets.values() if t.regime == regime]

    def count_recurrences(self, ticket: Ticket) -> int:
        """Count how many times this ticket has recurred."""
        count = 0
        for t in self._tickets.values():
            if t.parent_ticket == ticket.id:
                count += 1
        return count

    def clear(self) -> None:
        """Clear all tickets (for ephemeral retention)."""
        self._tickets.clear()

    def set_persistence_hook(self, hook: Callable[[Ticket], None]) -> None:
        """Set a hook for persisting tickets."""
        self._persistence_hook = hook


# =============================================================================
# Default Routing Rules
# =============================================================================


# Auto-fix registry: ticket types that can be automatically fixed
AUTO_FIX_TYPES: dict[TicketType, dict[str, Any]] = {
    ProseTicketType.GOV_VISIBILITY_LEAK: {"action": "suppress_governance_markers"},
    ProseTicketType.REGIME_COLLISION: {"action": "enforce_dominant_regime"},
    ProseTicketType.PREMATURE_CLOSURE: {"action": "delay_synthesis"},
    ProseTicketType.TONE_GOVERNANCE_LEAK: {"action": "filter_institutional_markers"},
    CodeTicketType.MISSING_INVARIANT: {"action": "add_enforcement"},
}


# Types that always escalate
ESCALATE_TYPES: set[TicketType] = {
    CodeTicketType.UNOWNED_LIABILITY,
    CodeTicketType.ROLLBACK_GAP,
}


def has_auto_fix(ticket_type: TicketType) -> bool:
    """Check if a ticket type has an auto-fix."""
    return ticket_type in AUTO_FIX_TYPES


def get_auto_fix(ticket_type: TicketType) -> dict[str, Any] | None:
    """Get the auto-fix for a ticket type."""
    return AUTO_FIX_TYPES.get(ticket_type)


def should_escalate(ticket_type: TicketType) -> bool:
    """Check if a ticket type should always escalate."""
    return ticket_type in ESCALATE_TYPES


# =============================================================================
# Ticketing Layer
# =============================================================================


@dataclass
class TicketingLayerInput:
    """Input to the ticketing layer."""

    violation: ViolationDetection | None
    regime: str
    domain: TicketDomain
    context: str = ""


@dataclass
class TicketingLayerOutput:
    """Output from the ticketing layer."""

    ticket_created: bool
    ticket: Ticket | None = None
    routing: RoutingAction | None = None
    similar_tickets: list[Ticket] = field(default_factory=list)
    recurrence_detected: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_created": self.ticket_created,
            "ticket": self.ticket.to_dict() if self.ticket else None,
            "routing": self.routing.to_dict() if self.routing else None,
            "similar_tickets": [t.to_dict() for t in self.similar_tickets],
            "recurrence_detected": self.recurrence_detected,
        }


@dataclass
class CorrectionResult:
    """Result of attempting a correction."""

    corrected: bool
    ticket: Ticket | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "corrected": self.corrected,
            "ticket": self.ticket.to_dict() if self.ticket else None,
            "reason": self.reason,
        }


class TicketingLayer:
    """Main ticketing layer controller.

    Sits after detection, before correction. Creates tickets,
    routes them, and enforces "no correction without ticket."
    """

    def __init__(self, config: TicketingConfig | None = None):
        self.config = config or DEFAULT_TICKETING_CONFIG
        self._store = TicketStore(self.config.retention_policy)

    def process(self, input: TicketingLayerInput) -> TicketingLayerOutput:
        """Process a potential violation through the ticketing layer."""
        if not self.config.enabled:
            return TicketingLayerOutput(ticket_created=False)

        if input.violation is None:
            return TicketingLayerOutput(ticket_created=False)

        # Find similar tickets
        similar = find_similar_tickets(
            input.violation,
            self._store.all(),
            self.config.similarity_threshold,
        ) if self.config.link_recurring else []

        # Check for recurrence
        recurrence_detected = len(similar) > 0

        # Create ticket if auto_create is enabled
        ticket = None
        if self.config.auto_create:
            ticket = self._create_ticket(input.violation, similar)
            self._store.add(ticket)

        # Route the ticket
        routing = self._route_ticket(ticket) if ticket else None

        return TicketingLayerOutput(
            ticket_created=ticket is not None,
            ticket=ticket,
            routing=routing,
            similar_tickets=similar,
            recurrence_detected=recurrence_detected,
        )

    def attempt_correction(
        self,
        violation: ViolationDetection,
    ) -> CorrectionResult:
        """Attempt to correct a violation.

        If require_ticket_for_fix is True, correction only proceeds
        if a ticket can be created.
        """
        if self.config.enabled and self.config.require_ticket_for_fix:
            # Create ticket first
            similar = find_similar_tickets(
                violation,
                self._store.all(),
                self.config.similarity_threshold,
            ) if self.config.link_recurring else []

            ticket = self._create_ticket(violation, similar)
            if ticket is None:
                return CorrectionResult(
                    corrected=False,
                    reason="ticketing_required_but_failed",
                )

            self._store.add(ticket)
            return CorrectionResult(
                corrected=True,
                ticket=ticket,
                reason="correction_with_ticket",
            )

        # Ticketing disabled or not required: fix without record
        return CorrectionResult(
            corrected=True,
            reason="correction_without_ticket",
        )

    def create_manual_ticket(
        self,
        ticket_type: TicketType,
        description: str,
        regime: str,
        domain: TicketDomain,
        context: str = "",
        tags: list[str] | None = None,
    ) -> Ticket | None:
        """Create a manual ticket for human-identified issues."""
        if not self.config.enabled:
            return None

        ticket = Ticket(
            id=self._generate_id(),
            created_at=time.time(),
            updated_at=time.time(),
            type=ticket_type,
            regime=regime,
            domain=domain,
            severity=TicketSeverity.WARNING,  # manual defaults to warning
            violated_invariant="manual_report",
            description=description,
            context_slice=context[:self.config.max_context_slice_length],
            parent_ticket=None,
            related_tickets=[],
            status=TicketStatus.OPEN,
            tags=tags or [],
            source="manual",
        )

        self._store.add(ticket)
        return ticket

    def acknowledge(self, ticket_id: str) -> bool:
        """Acknowledge a ticket (human action)."""
        ticket = self._store.get(ticket_id)
        if ticket is None:
            return False

        if not is_valid_transition(ticket.status, TicketStatus.ACKNOWLEDGED, "human"):
            return False

        ticket.status = TicketStatus.ACKNOWLEDGED
        self._store.update(ticket)
        return True

    def fix(self, ticket_id: str, resolution: str = "") -> bool:
        """Mark a ticket as fixed."""
        ticket = self._store.get(ticket_id)
        if ticket is None:
            return False

        if not is_valid_transition(ticket.status, TicketStatus.FIXED, "auto"):
            return False

        ticket.status = TicketStatus.FIXED
        ticket.resolution = resolution
        ticket.closed_at = time.time()
        self._store.update(ticket)
        return True

    def wont_fix(self, ticket_id: str, reason: str = "") -> bool:
        """Mark a ticket as won't fix (human action)."""
        ticket = self._store.get(ticket_id)
        if ticket is None:
            return False

        if not is_valid_transition(ticket.status, TicketStatus.WONT_FIX, "human"):
            return False

        ticket.status = TicketStatus.WONT_FIX
        ticket.resolution = reason
        ticket.closed_at = time.time()
        self._store.update(ticket)
        return True

    def mark_duplicate(self, ticket_id: str, duplicate_of: str) -> bool:
        """Mark a ticket as duplicate."""
        ticket = self._store.get(ticket_id)
        if ticket is None:
            return False

        if not is_valid_transition(ticket.status, TicketStatus.DUPLICATE, "auto"):
            return False

        ticket.status = TicketStatus.DUPLICATE
        ticket.resolution = f"Duplicate of {duplicate_of}"
        ticket.closed_at = time.time()
        if duplicate_of not in ticket.related_tickets:
            ticket.related_tickets.append(duplicate_of)
        self._store.update(ticket)
        return True

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        """Get a ticket by ID."""
        return self._store.get(ticket_id)

    def get_all_tickets(self) -> list[Ticket]:
        """Get all tickets."""
        return self._store.all()

    def get_open_tickets(self) -> list[Ticket]:
        """Get all open tickets."""
        return self._store.open_tickets()

    def get_tickets_by_type(self, ticket_type: TicketType) -> list[Ticket]:
        """Get tickets by type."""
        return self._store.by_type(ticket_type)

    def count_recurrences(self, ticket_id: str) -> int:
        """Count recurrences of a ticket."""
        ticket = self._store.get(ticket_id)
        if ticket is None:
            return 0
        return self._store.count_recurrences(ticket)

    def check_recurrence_escalation(self, ticket: Ticket) -> bool:
        """Check if a ticket should escalate due to recurrence."""
        recurrence_count = self._store.count_recurrences(ticket)
        threshold = self.config.recurrence_escalation_thresholds.get(
            ticket.severity.value,
            5,
        )
        return recurrence_count >= threshold

    def _create_ticket(
        self,
        detection: ViolationDetection,
        similar: list[Ticket],
    ) -> Ticket:
        """Create a ticket from a violation detection."""
        parent = similar[0].id if similar else None

        return Ticket(
            id=self._generate_id(),
            created_at=time.time(),
            updated_at=time.time(),
            type=detection.type,
            regime=detection.regime,
            domain=detection.domain,
            severity=map_severity(detection.severity),
            violated_invariant=detection.invariant,
            description=self._generate_description(detection),
            context_slice=detection.context[:self.config.max_context_slice_length],
            reproduction_hint=self._generate_repro_hint(detection),
            parent_ticket=parent,
            related_tickets=[t.id for t in similar],
            status=TicketStatus.OPEN,
            tags=self._infer_tags(detection),
            source="auto",
        )

    def _route_ticket(self, ticket: Ticket) -> RoutingAction:
        """Determine routing action for a ticket."""
        # Critical violations always escalate
        if ticket.severity == TicketSeverity.CRITICAL:
            return RoutingAction(
                action=RoutingActionType.ESCALATE,
                reason="critical_severity",
                escalate_to="human",
            )

        # Recurring violations escalate
        if ticket.parent_ticket and self.check_recurrence_escalation(ticket):
            return RoutingAction(
                action=RoutingActionType.ESCALATE,
                reason="recurrence_threshold_exceeded",
                escalate_to="review_queue",
            )

        # Types that always escalate
        if should_escalate(ticket.type):
            return RoutingAction(
                action=RoutingActionType.ESCALATE,
                reason="type_requires_escalation",
                escalate_to="human",
            )

        # Known fixable violations get auto-adjustment
        if has_auto_fix(ticket.type):
            return RoutingAction(
                action=RoutingActionType.ADJUST,
                reason="auto_fix_available",
                adjustment=get_auto_fix(ticket.type),
            )

        # Scope violations get suppressed
        if ticket.type == CodeTicketType.SCOPE_VIOLATION:
            return RoutingAction(
                action=RoutingActionType.SUPPRESS,
                reason="out_of_scope",
            )

        # Default: log for learning
        return RoutingAction(
            action=RoutingActionType.LOG,
            reason="default_routing",
            log_for="learning",
        )

    def _generate_id(self) -> str:
        """Generate a unique ticket ID."""
        return f"TKT-{uuid.uuid4().hex[:8].upper()}"

    def _generate_description(self, detection: ViolationDetection) -> str:
        """Generate a human-readable description."""
        type_name = detection.type.value.replace("_", " ").lower()
        return f"{type_name} in {detection.regime} regime: {detection.invariant}"

    def _generate_repro_hint(self, detection: ViolationDetection) -> str:
        """Generate a reproduction hint."""
        context_hash = hashlib.md5(detection.context.encode()).hexdigest()[:8]
        return f"Context fingerprint: {context_hash}"

    def _infer_tags(self, detection: ViolationDetection) -> list[str]:
        """Infer tags from detection."""
        tags = [detection.domain.value, detection.regime]
        if detection.severity >= 0.75:
            tags.append("high_severity")
        return tags


# =============================================================================
# Learning Signals
# =============================================================================


@dataclass
class LearningSignal:
    """Learning signal extracted from closed tickets."""

    ticket_type: TicketType
    regime: str
    resolution: str
    recurrence_count: int
    time_to_fix: float  # seconds
    effective: bool  # did the fix prevent recurrence?

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_type": self.ticket_type.value if isinstance(self.ticket_type, Enum) else self.ticket_type,
            "regime": self.regime,
            "resolution": self.resolution,
            "recurrence_count": self.recurrence_count,
            "time_to_fix": self.time_to_fix,
            "effective": self.effective,
        }


def extract_learning_signals(
    layer: TicketingLayer,
    check_recurrence_after_fix: Callable[[Ticket], bool] | None = None,
) -> list[LearningSignal]:
    """Extract learning signals from closed tickets."""
    signals = []

    for ticket in layer.get_all_tickets():
        if ticket.status != TicketStatus.FIXED:
            continue

        # Calculate time to fix
        time_to_fix = 0.0
        if ticket.closed_at:
            time_to_fix = ticket.closed_at - ticket.created_at

        # Check if effective (no recurrence after fix)
        effective = True
        if check_recurrence_after_fix:
            effective = not check_recurrence_after_fix(ticket)

        signals.append(LearningSignal(
            ticket_type=ticket.type,
            regime=ticket.regime,
            resolution=ticket.resolution,
            recurrence_count=layer.count_recurrences(ticket.id),
            time_to_fix=time_to_fix,
            effective=effective,
        ))

    return signals


# =============================================================================
# Metrics
# =============================================================================


@dataclass
class TicketingMetrics:
    """Metrics for the ticketing layer."""

    tickets_created: int
    tickets_fixed: int
    tickets_open: int
    recurrence_rate: float  # tickets with parent / total
    mean_time_to_fix: float
    escalation_rate: float  # escalated / total
    top_violation_types: list[tuple[str, int]]  # [(type, count), ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tickets_created": self.tickets_created,
            "tickets_fixed": self.tickets_fixed,
            "tickets_open": self.tickets_open,
            "recurrence_rate": self.recurrence_rate,
            "mean_time_to_fix": self.mean_time_to_fix,
            "escalation_rate": self.escalation_rate,
            "top_violation_types": self.top_violation_types,
        }


def compute_metrics(layer: TicketingLayer) -> TicketingMetrics:
    """Compute metrics for the ticketing layer."""
    tickets = layer.get_all_tickets()

    if not tickets:
        return TicketingMetrics(
            tickets_created=0,
            tickets_fixed=0,
            tickets_open=0,
            recurrence_rate=0.0,
            mean_time_to_fix=0.0,
            escalation_rate=0.0,
            top_violation_types=[],
        )

    # Counts
    total = len(tickets)
    fixed = sum(1 for t in tickets if t.status == TicketStatus.FIXED)
    open_count = sum(1 for t in tickets if t.status == TicketStatus.OPEN)
    with_parent = sum(1 for t in tickets if t.parent_ticket is not None)

    # Time to fix
    fix_times = []
    for t in tickets:
        if t.status == TicketStatus.FIXED and t.closed_at:
            fix_times.append(t.closed_at - t.created_at)
    mean_ttf = sum(fix_times) / len(fix_times) if fix_times else 0.0

    # Type counts
    type_counts: dict[str, int] = {}
    for t in tickets:
        type_str = t.type.value if isinstance(t.type, Enum) else str(t.type)
        type_counts[type_str] = type_counts.get(type_str, 0) + 1
    top_types = sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:5]

    return TicketingMetrics(
        tickets_created=total,
        tickets_fixed=fixed,
        tickets_open=open_count,
        recurrence_rate=with_parent / total if total > 0 else 0.0,
        mean_time_to_fix=mean_ttf,
        escalation_rate=0.0,  # Would need routing history to compute
        top_violation_types=top_types,
    )


# =============================================================================
# Integration Helpers
# =============================================================================


def create_ticketing_layer(
    enabled: bool = False,
    require_ticket_for_fix: bool = True,
    retention_policy: str = "session",
) -> TicketingLayer:
    """Create a ticketing layer with common configuration."""
    config = TicketingConfig(
        enabled=enabled,
        require_ticket_for_fix=require_ticket_for_fix,
        retention_policy=RetentionPolicy(retention_policy),
    )
    return TicketingLayer(config)


# Default disabled layer
DEFAULT_TICKETING_LAYER = TicketingLayer(DEFAULT_TICKETING_CONFIG)
