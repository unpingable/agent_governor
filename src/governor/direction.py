"""
Direction tracking for narrative and argumentative coherence.

Provides artificial landmarks that impose orientation constraints:
- Commitments: Promises that must be fulfilled (plot threads, thesis statements)
- Anchors: Immutable facts that constrain everything (world rules, citations)
- Predictions: Claims about future state with later verification
- Trajectory: Current heading, destination, drift detection
- Belief Graph: Logical relationships with triangle detection

Based on the insight that orientation requires:
1. Persistence - landmarks are there tomorrow
2. Resistance - they don't bend to interpretation
3. Detectability - misalignment is observable
4. Consequence - being wrong matters
5. Triangulation - multiple landmarks constrain each other
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from collections import defaultdict


# =============================================================================
# Core Enums
# =============================================================================

class CommitmentType(Enum):
    """Types of commitments that must be fulfilled."""

    PROMISE = "promise"
    """Reader/audience expectation set (implicit contract)."""

    PREDICTION = "prediction"
    """Claim about future state that will be verified."""

    THESIS = "thesis"
    """Argument to be defended (non-fiction)."""

    FORESHADOWING = "foreshadowing"
    """Setup that must pay off (fiction)."""

    DEADLINE = "deadline"
    """Must happen by specific point."""

    CHEKHOV = "chekhov"
    """Gun on the wall that must fire."""

    SETUP = "setup"
    """Foundation for later payoff."""


class AnchorType(Enum):
    """Types of immutable anchors that constrain the space."""

    WORLD_RULE = "world_rule"
    """Fiction invariant (magic system, physics)."""

    CANON_FACT = "canon_fact"
    """Established story fact that cannot change."""

    CITATION = "citation"
    """External source reference (non-fiction)."""

    AXIOM = "axiom"
    """Assumed true without proof."""

    ORACLE = "oracle"
    """Externally verifiable fact."""

    DEFINITION = "definition"
    """Term definition that must be consistent."""

    CONSTRAINT = "constraint"
    """Hard constraint that cannot be violated."""


class RelationType(Enum):
    """Types of logical relationships between nodes."""

    IMPLIES = "implies"
    """A → B (if A then B)."""

    CONTRADICTS = "contradicts"
    """A → ¬B (A and B cannot both be true)."""

    REQUIRES = "requires"
    """A needs B to be true/present."""

    ENABLES = "enables"
    """A makes B possible."""

    BLOCKS = "blocks"
    """A prevents B."""

    SUPPORTS = "supports"
    """A provides evidence for B."""

    UNDERMINES = "undermines"
    """A weakens B."""

    PRECEDES = "precedes"
    """A must come before B."""

    FOLLOWS = "follows"
    """A must come after B."""


class ViolationSeverity(Enum):
    """Severity of anchor violations."""

    CRITICAL = "critical"
    """Fundamental contradiction, story/argument breaks."""

    HIGH = "high"
    """Serious inconsistency, needs immediate fix."""

    MEDIUM = "medium"
    """Noticeable inconsistency, should be addressed."""

    LOW = "low"
    """Minor inconsistency, acceptable in some contexts."""


# =============================================================================
# Core Data Classes
# =============================================================================

@dataclass
class Commitment:
    """A promise that must be fulfilled."""

    id: str
    commitment_type: CommitmentType
    content: str
    created_at: datetime
    deadline: int | datetime | None = None  # Chapter/section number or timestamp
    deadline_type: str = "chapter"  # "chapter", "section", "time", "event"
    fulfilled: bool = False
    fulfilled_at: datetime | None = None
    fulfilled_how: str | None = None
    abandoned: bool = False
    abandoned_reason: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
    predictions: list[str] = field(default_factory=list)  # What this implies will happen

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "commitment_type": self.commitment_type.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "deadline": self.deadline.isoformat() if isinstance(self.deadline, datetime) else self.deadline,
            "deadline_type": self.deadline_type,
            "fulfilled": self.fulfilled,
            "fulfilled_at": self.fulfilled_at.isoformat() if self.fulfilled_at else None,
            "fulfilled_how": self.fulfilled_how,
            "abandoned": self.abandoned,
            "abandoned_reason": self.abandoned_reason,
            "context": self.context,
            "predictions": self.predictions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Commitment":
        deadline = data.get("deadline")
        if deadline and data.get("deadline_type") == "time":
            deadline = datetime.fromisoformat(deadline)

        return cls(
            id=data["id"],
            commitment_type=CommitmentType(data["commitment_type"]),
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
            deadline=deadline,
            deadline_type=data.get("deadline_type", "chapter"),
            fulfilled=data.get("fulfilled", False),
            fulfilled_at=datetime.fromisoformat(data["fulfilled_at"]) if data.get("fulfilled_at") else None,
            fulfilled_how=data.get("fulfilled_how"),
            abandoned=data.get("abandoned", False),
            abandoned_reason=data.get("abandoned_reason"),
            context=data.get("context", {}),
            predictions=data.get("predictions", []),
        )


@dataclass
class Anchor:
    """An immutable fact that constrains everything."""

    id: str
    anchor_type: AnchorType
    content: str
    created_at: datetime
    source: str | None = None  # Citation, chapter, external URL
    confidence: float = 1.0  # Anchors should be high confidence
    scope: str | None = None  # Where this anchor applies
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "anchor_type": self.anchor_type.value,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "source": self.source,
            "confidence": self.confidence,
            "scope": self.scope,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Anchor":
        return cls(
            id=data["id"],
            anchor_type=AnchorType(data["anchor_type"]),
            content=data["content"],
            created_at=datetime.fromisoformat(data["created_at"]),
            source=data.get("source"),
            confidence=data.get("confidence", 1.0),
            scope=data.get("scope"),
            context=data.get("context", {}),
        )


@dataclass
class Relation:
    """A logical relationship between two nodes."""

    source_id: str
    target_id: str
    relation_type: RelationType
    strength: float = 1.0  # How strong is this relationship? [0, 1]
    context: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "strength": self.strength,
            "context": self.context,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Relation":
        return cls(
            source_id=data["source_id"],
            target_id=data["target_id"],
            relation_type=RelationType(data["relation_type"]),
            strength=data.get("strength", 1.0),
            context=data.get("context"),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc),
        )


@dataclass
class Trajectory:
    """Current narrative/argumentative direction."""

    current_position: str  # Where are we now?
    destination: str  # Where are we heading?
    waypoints: list[str] = field(default_factory=list)  # Intermediate points
    completed_waypoints: list[str] = field(default_factory=list)
    drift: float = 0.0  # How far off course? [0, 1]
    heading: str | None = None  # Current direction description
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_position": self.current_position,
            "destination": self.destination,
            "waypoints": self.waypoints,
            "completed_waypoints": self.completed_waypoints,
            "drift": self.drift,
            "heading": self.heading,
            "started_at": self.started_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Trajectory":
        return cls(
            current_position=data["current_position"],
            destination=data["destination"],
            waypoints=data.get("waypoints", []),
            completed_waypoints=data.get("completed_waypoints", []),
            drift=data.get("drift", 0.0),
            heading=data.get("heading"),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else datetime.now(timezone.utc),
        )


# =============================================================================
# Δt Types
# =============================================================================

@dataclass
class DeltaT:
    """A prediction/reality mismatch measurement."""

    commitment_id: str
    predicted: str
    actual: str | None
    delta: float  # 0.0 = perfect match, 1.0 = complete mismatch
    verified_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "commitment_id": self.commitment_id,
            "predicted": self.predicted,
            "actual": self.actual,
            "delta": self.delta,
            "verified_at": self.verified_at.isoformat(),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeltaT":
        return cls(
            commitment_id=data["commitment_id"],
            predicted=data["predicted"],
            actual=data.get("actual"),
            delta=data["delta"],
            verified_at=datetime.fromisoformat(data["verified_at"]) if data.get("verified_at") else datetime.now(timezone.utc),
            notes=data.get("notes"),
        )


@dataclass
class Violation:
    """An anchor violation detected."""

    anchor_id: str
    violating_content: str
    violation_type: str
    severity: ViolationSeverity
    location: str | None = None  # Where the violation occurred
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    resolution: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "violating_content": self.violating_content,
            "violation_type": self.violation_type,
            "severity": self.severity.value,
            "location": self.location,
            "detected_at": self.detected_at.isoformat(),
            "resolved": self.resolved,
            "resolution": self.resolution,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Violation":
        return cls(
            anchor_id=data["anchor_id"],
            violating_content=data["violating_content"],
            violation_type=data["violation_type"],
            severity=ViolationSeverity(data["severity"]),
            location=data.get("location"),
            detected_at=datetime.fromisoformat(data["detected_at"]) if data.get("detected_at") else datetime.now(timezone.utc),
            resolved=data.get("resolved", False),
            resolution=data.get("resolution"),
        )


@dataclass
class Triangle:
    """An impossible logical configuration (contradiction triangle)."""

    nodes: tuple[str, str, str]
    relations: list[Relation]
    explanation: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": list(self.nodes),
            "relations": [r.to_dict() for r in self.relations],
            "explanation": self.explanation,
            "detected_at": self.detected_at.isoformat(),
        }


# =============================================================================
# Belief Graph
# =============================================================================

class BeliefGraph:
    """
    Graph of beliefs/facts with logical relationships.

    Supports:
    - Adding nodes (facts, claims, anchors)
    - Adding relations (implies, contradicts, requires, etc.)
    - Path finding
    - Cycle detection
    - Impossible triangle detection
    """

    def __init__(self):
        self._nodes: dict[str, dict[str, Any]] = {}
        self._relations: list[Relation] = []
        self._adjacency: dict[str, list[tuple[str, Relation]]] = defaultdict(list)
        self._reverse_adjacency: dict[str, list[tuple[str, Relation]]] = defaultdict(list)

    def add_node(
        self,
        node_id: str,
        content: str,
        node_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Add a node to the belief graph."""
        self._nodes[node_id] = {
            "id": node_id,
            "content": content,
            "type": node_type,
            "metadata": metadata or {},
        }

    def get_node(self, node_id: str) -> dict[str, Any] | None:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def add_relation(self, relation: Relation) -> None:
        """Add a relation between nodes."""
        self._relations.append(relation)
        self._adjacency[relation.source_id].append((relation.target_id, relation))
        self._reverse_adjacency[relation.target_id].append((relation.source_id, relation))

    def get_relations_from(self, node_id: str) -> list[Relation]:
        """Get all relations originating from a node."""
        return [r for _, r in self._adjacency.get(node_id, [])]

    def get_relations_to(self, node_id: str) -> list[Relation]:
        """Get all relations pointing to a node."""
        return [r for _, r in self._reverse_adjacency.get(node_id, [])]

    def find_path(
        self,
        source: str,
        target: str,
        relation_types: list[RelationType] | None = None,
    ) -> list[str] | None:
        """Find a path from source to target, optionally filtering by relation types."""
        if source not in self._nodes or target not in self._nodes:
            return None

        visited = set()
        queue = [(source, [source])]

        while queue:
            current, path = queue.pop(0)
            if current == target:
                return path

            if current in visited:
                continue
            visited.add(current)

            for neighbor, relation in self._adjacency.get(current, []):
                if relation_types and relation.relation_type not in relation_types:
                    continue
                if neighbor not in visited:
                    queue.append((neighbor, path + [neighbor]))

        return None

    def detect_cycles(self) -> list[list[str]]:
        """Detect all cycles in the graph."""
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: list[str]) -> None:
            visited.add(node)
            rec_stack.add(node)

            for neighbor, _ in self._adjacency.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path + [neighbor])
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor) if neighbor in path else 0
                    cycles.append(path[cycle_start:] + [neighbor])

            rec_stack.remove(node)

        for node in self._nodes:
            if node not in visited:
                dfs(node, [node])

        return cycles

    def detect_contradictions(self) -> list[tuple[str, str, str]]:
        """
        Detect direct contradictions.

        Returns list of (node_a, node_b, explanation) tuples.
        """
        contradictions = []

        for relation in self._relations:
            if relation.relation_type == RelationType.CONTRADICTS:
                contradictions.append((
                    relation.source_id,
                    relation.target_id,
                    f"{relation.source_id} contradicts {relation.target_id}",
                ))

        return contradictions

    def detect_triangles(self) -> list[Triangle]:
        """
        Detect impossible triangles.

        An impossible triangle is when:
        - A implies B
        - B implies ¬C (contradicts C)
        - A implies C (or A requires C)

        This creates an impossible configuration.
        """
        triangles = []

        # Build implication and contradiction maps
        implies: dict[str, set[str]] = defaultdict(set)
        contradicts: dict[str, set[str]] = defaultdict(set)

        for relation in self._relations:
            if relation.relation_type in (RelationType.IMPLIES, RelationType.REQUIRES, RelationType.SUPPORTS):
                implies[relation.source_id].add(relation.target_id)
            elif relation.relation_type == RelationType.CONTRADICTS:
                contradicts[relation.source_id].add(relation.target_id)
                contradicts[relation.target_id].add(relation.source_id)  # Symmetric

        # Find triangles
        for a in self._nodes:
            for b in implies.get(a, set()):
                for c in implies.get(b, set()):
                    # A → B → C, but does anything contradict?
                    if c in contradicts.get(a, set()):
                        # A implies C through B, but A contradicts C
                        relations = [
                            r for r in self._relations
                            if (r.source_id == a and r.target_id == b) or
                               (r.source_id == b and r.target_id == c) or
                               (r.source_id in (a, c) and r.target_id in (a, c) and r.relation_type == RelationType.CONTRADICTS)
                        ]
                        triangles.append(Triangle(
                            nodes=(a, b, c),
                            relations=relations[:3],
                            explanation=f"{a} implies {b}, {b} implies {c}, but {a} contradicts {c}",
                        ))

        return triangles

    def get_implications(self, node_id: str) -> list[str]:
        """Get all nodes implied by this node (transitive closure)."""
        implied = set()
        queue = [node_id]

        while queue:
            current = queue.pop(0)
            for neighbor, relation in self._adjacency.get(current, []):
                if relation.relation_type in (RelationType.IMPLIES, RelationType.REQUIRES):
                    if neighbor not in implied:
                        implied.add(neighbor)
                        queue.append(neighbor)

        return list(implied)

    def get_contradictions_for(self, node_id: str) -> list[str]:
        """Get all nodes that contradict this node."""
        contradicting = []

        for relation in self._relations:
            if relation.relation_type == RelationType.CONTRADICTS:
                if relation.source_id == node_id:
                    contradicting.append(relation.target_id)
                elif relation.target_id == node_id:
                    contradicting.append(relation.source_id)

        return contradicting

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": self._nodes,
            "relations": [r.to_dict() for r in self._relations],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BeliefGraph":
        graph = cls()
        graph._nodes = data.get("nodes", {})
        graph._relations = [Relation.from_dict(r) for r in data.get("relations", [])]

        # Rebuild adjacency
        for relation in graph._relations:
            graph._adjacency[relation.source_id].append((relation.target_id, relation))
            graph._reverse_adjacency[relation.target_id].append((relation.source_id, relation))

        return graph


# =============================================================================
# Direction Ledger
# =============================================================================

class DirectionLedger:
    """
    Tracks commitments, anchors, and trajectory for narrative/argumentative direction.

    This is the main interface for direction tracking, usable by both
    fiction and non-fiction governors.
    """

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = storage_dir

        self._commitments: dict[str, Commitment] = {}
        self._anchors: dict[str, Anchor] = {}
        self._trajectory: Trajectory | None = None
        self._belief_graph = BeliefGraph()
        self._delta_t_history: list[DeltaT] = []
        self._violations: list[Violation] = []
        self._position_history: list[tuple[str, datetime]] = []

        if storage_dir:
            self._load()

    def _generate_id(self, prefix: str, content: str) -> str:
        """Generate a unique ID."""
        hash_input = f"{prefix}:{content}:{datetime.now(timezone.utc).isoformat()}"
        return f"{prefix}_{hashlib.sha256(hash_input.encode()).hexdigest()[:12]}"

    # -------------------------------------------------------------------------
    # Commitment Management
    # -------------------------------------------------------------------------

    def add_commitment(
        self,
        content: str,
        commitment_type: CommitmentType,
        deadline: int | datetime | None = None,
        deadline_type: str = "chapter",
        context: dict[str, Any] | None = None,
        predictions: list[str] | None = None,
    ) -> str:
        """Add a new commitment."""
        commitment_id = self._generate_id("commit", content)

        commitment = Commitment(
            id=commitment_id,
            commitment_type=commitment_type,
            content=content,
            created_at=datetime.now(timezone.utc),
            deadline=deadline,
            deadline_type=deadline_type,
            context=context or {},
            predictions=predictions or [],
        )

        self._commitments[commitment_id] = commitment

        # Add to belief graph
        self._belief_graph.add_node(
            commitment_id,
            content,
            f"commitment:{commitment_type.value}",
        )

        self._save()
        return commitment_id

    def fulfill_commitment(
        self,
        commitment_id: str,
        how: str,
        actual_outcome: str | None = None,
    ) -> DeltaT | None:
        """Mark a commitment as fulfilled and compute Δt if predictions exist."""
        if commitment_id not in self._commitments:
            raise ValueError(f"Unknown commitment: {commitment_id}")

        commitment = self._commitments[commitment_id]
        commitment.fulfilled = True
        commitment.fulfilled_at = datetime.now(timezone.utc)
        commitment.fulfilled_how = how

        # Compute Δt if there were predictions
        delta_t = None
        if commitment.predictions and actual_outcome:
            # Simple string-based Δt (could be made more sophisticated)
            predicted = " ".join(commitment.predictions)
            delta = self._compute_delta(predicted, actual_outcome)
            delta_t = DeltaT(
                commitment_id=commitment_id,
                predicted=predicted,
                actual=actual_outcome,
                delta=delta,
            )
            self._delta_t_history.append(delta_t)

        self._save()
        return delta_t

    def abandon_commitment(self, commitment_id: str, reason: str) -> None:
        """Mark a commitment as abandoned."""
        if commitment_id not in self._commitments:
            raise ValueError(f"Unknown commitment: {commitment_id}")

        commitment = self._commitments[commitment_id]
        commitment.abandoned = True
        commitment.abandoned_reason = reason

        self._save()

    def check_deadlines(self, current_position: int | datetime) -> list[Commitment]:
        """Check for commitments approaching or past their deadline."""
        overdue = []

        for commitment in self._commitments.values():
            if commitment.fulfilled or commitment.abandoned:
                continue

            if commitment.deadline is None:
                continue

            # Compare based on deadline type
            if isinstance(commitment.deadline, datetime) and isinstance(current_position, datetime):
                if current_position >= commitment.deadline:
                    overdue.append(commitment)
            elif isinstance(commitment.deadline, int) and isinstance(current_position, int):
                if current_position >= commitment.deadline:
                    overdue.append(commitment)

        return overdue

    def get_unfulfilled(self) -> list[Commitment]:
        """Get all unfulfilled, non-abandoned commitments."""
        return [
            c for c in self._commitments.values()
            if not c.fulfilled and not c.abandoned
        ]

    def get_commitment(self, commitment_id: str) -> Commitment | None:
        """Get a commitment by ID."""
        return self._commitments.get(commitment_id)

    # -------------------------------------------------------------------------
    # Anchor Management
    # -------------------------------------------------------------------------

    def add_anchor(
        self,
        content: str,
        anchor_type: AnchorType,
        source: str | None = None,
        confidence: float = 1.0,
        scope: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Add a new anchor (immutable constraint)."""
        anchor_id = self._generate_id("anchor", content)

        anchor = Anchor(
            id=anchor_id,
            anchor_type=anchor_type,
            content=content,
            created_at=datetime.now(timezone.utc),
            source=source,
            confidence=confidence,
            scope=scope,
            context=context or {},
        )

        self._anchors[anchor_id] = anchor

        # Add to belief graph
        self._belief_graph.add_node(
            anchor_id,
            content,
            f"anchor:{anchor_type.value}",
        )

        self._save()
        return anchor_id

    def check_against_anchors(
        self,
        content: str,
        checker: Callable[[str, str], tuple[bool, str]] | None = None,
    ) -> list[Violation]:
        """
        Check content against all anchors for violations.

        If checker is provided, it's called as checker(anchor_content, new_content)
        and should return (is_violation, violation_type).

        Default checker does simple substring contradiction detection.
        """
        violations = []

        for anchor in self._anchors.values():
            if checker:
                is_violation, violation_type = checker(anchor.content, content)
            else:
                # Default: simple negation detection
                is_violation, violation_type = self._default_violation_check(
                    anchor.content, content
                )

            if is_violation:
                violation = Violation(
                    anchor_id=anchor.id,
                    violating_content=content,
                    violation_type=violation_type,
                    severity=ViolationSeverity.HIGH,
                )
                violations.append(violation)
                self._violations.append(violation)

        if violations:
            self._save()

        return violations

    def _default_violation_check(
        self,
        anchor_content: str,
        new_content: str,
    ) -> tuple[bool, str]:
        """Default violation checker using simple heuristics."""
        anchor_lower = anchor_content.lower()
        new_lower = new_content.lower()

        # Extract key words from anchor (skip common words)
        skip_words = {"a", "an", "the", "is", "are", "was", "were", "be", "been", "being"}
        anchor_words = [w for w in anchor_lower.split() if w not in skip_words]

        # Check for direct negation patterns
        negation_patterns = [
            (f"not {anchor_lower}", "direct_negation"),
            (f"never {anchor_lower}", "direct_negation"),
            (f"no {anchor_lower}", "direct_negation"),
            (f"cannot {anchor_lower}", "impossibility_claim"),
            (f"impossible {anchor_lower}", "impossibility_claim"),
        ]

        for pattern, vtype in negation_patterns:
            if pattern in new_lower:
                return True, vtype

        # Check for negations of key anchor words
        # e.g., anchor "Magic requires words" → check for "never requires", "not require", etc.
        for word in anchor_words:
            # Also check base form (remove trailing 's', 'es', 'ed', 'ing')
            word_forms = [word]
            if word.endswith("s"):
                word_forms.append(word[:-1])
            if word.endswith("es"):
                word_forms.append(word[:-2])
            if word.endswith("ed"):
                word_forms.append(word[:-2])
                word_forms.append(word[:-1])  # e.g., "required" -> "requir" and "require"
            if word.endswith("ing"):
                word_forms.append(word[:-3])
                word_forms.append(word[:-3] + "e")  # e.g., "requiring" -> "requir" and "require"

            for wf in word_forms:
                negation_checks = [
                    (f"never {wf}", "direct_negation"),
                    (f"not {wf}", "direct_negation"),
                    (f"no {wf}", "direct_negation"),
                    (f"cannot {wf}", "impossibility_claim"),
                    (f"doesn't {wf}", "direct_negation"),
                    (f"does not {wf}", "direct_negation"),
                    (f"don't {wf}", "direct_negation"),
                    (f"do not {wf}", "direct_negation"),
                ]
                for pattern, vtype in negation_checks:
                    if pattern in new_lower:
                        return True, vtype

        return False, ""

    def get_anchor(self, anchor_id: str) -> Anchor | None:
        """Get an anchor by ID."""
        return self._anchors.get(anchor_id)

    def get_anchors(self, anchor_type: AnchorType | None = None) -> list[Anchor]:
        """Get all anchors, optionally filtered by type."""
        if anchor_type:
            return [a for a in self._anchors.values() if a.anchor_type == anchor_type]
        return list(self._anchors.values())

    # -------------------------------------------------------------------------
    # Trajectory Management
    # -------------------------------------------------------------------------

    def set_trajectory(
        self,
        current_position: str,
        destination: str,
        waypoints: list[str] | None = None,
        heading: str | None = None,
    ) -> None:
        """Set or update the trajectory."""
        self._trajectory = Trajectory(
            current_position=current_position,
            destination=destination,
            waypoints=waypoints or [],
            heading=heading,
        )
        self._position_history.append((current_position, datetime.now(timezone.utc)))
        self._save()

    def update_position(self, new_position: str) -> float:
        """
        Update current position and return drift from intended trajectory.

        Returns drift value [0, 1] where 0 = on track, 1 = completely off.
        """
        if not self._trajectory:
            return 0.0

        self._trajectory.current_position = new_position
        self._position_history.append((new_position, datetime.now(timezone.utc)))

        # Check if we hit a waypoint
        if new_position in self._trajectory.waypoints:
            self._trajectory.waypoints.remove(new_position)
            self._trajectory.completed_waypoints.append(new_position)

        # Compute drift (simple heuristic based on waypoint completion)
        total_waypoints = len(self._trajectory.waypoints) + len(self._trajectory.completed_waypoints)
        if total_waypoints > 0:
            # More remaining waypoints = more drift
            drift = len(self._trajectory.waypoints) / (total_waypoints + 1)
        else:
            drift = 0.0

        self._trajectory.drift = drift
        self._save()

        return drift

    def complete_waypoint(self, waypoint: str) -> None:
        """Mark a waypoint as completed."""
        if self._trajectory and waypoint in self._trajectory.waypoints:
            self._trajectory.waypoints.remove(waypoint)
            self._trajectory.completed_waypoints.append(waypoint)
            self._save()

    def get_trajectory(self) -> Trajectory | None:
        """Get the current trajectory."""
        return self._trajectory

    # -------------------------------------------------------------------------
    # Relation Management
    # -------------------------------------------------------------------------

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation_type: RelationType,
        strength: float = 1.0,
        context: str | None = None,
    ) -> None:
        """Add a relation between two nodes in the belief graph."""
        relation = Relation(
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            strength=strength,
            context=context,
        )
        self._belief_graph.add_relation(relation)
        self._save()

    def check_consistency(self) -> tuple[list[Triangle], list[tuple[str, str, str]]]:
        """
        Check the belief graph for consistency issues.

        Returns (triangles, direct_contradictions).
        """
        triangles = self._belief_graph.detect_triangles()
        contradictions = self._belief_graph.detect_contradictions()
        return triangles, contradictions

    def get_belief_graph(self) -> BeliefGraph:
        """Get the belief graph."""
        return self._belief_graph

    # -------------------------------------------------------------------------
    # Δt Tracking
    # -------------------------------------------------------------------------

    def record_prediction(
        self,
        commitment_id: str,
        prediction: str,
    ) -> None:
        """Record a prediction for later verification."""
        if commitment_id not in self._commitments:
            raise ValueError(f"Unknown commitment: {commitment_id}")

        self._commitments[commitment_id].predictions.append(prediction)
        self._save()

    def verify_prediction(
        self,
        commitment_id: str,
        actual: str,
    ) -> DeltaT:
        """Verify a prediction against actual outcome."""
        if commitment_id not in self._commitments:
            raise ValueError(f"Unknown commitment: {commitment_id}")

        commitment = self._commitments[commitment_id]
        predicted = " ".join(commitment.predictions) if commitment.predictions else ""

        delta = self._compute_delta(predicted, actual)
        delta_t = DeltaT(
            commitment_id=commitment_id,
            predicted=predicted,
            actual=actual,
            delta=delta,
        )

        self._delta_t_history.append(delta_t)
        self._save()

        return delta_t

    def _compute_delta(self, predicted: str, actual: str) -> float:
        """
        Compute Δt between predicted and actual.

        Returns value in [0, 1] where 0 = perfect match, 1 = complete mismatch.

        This is a simple implementation using word overlap.
        Could be enhanced with embeddings or semantic similarity.
        """
        if not predicted or not actual:
            return 1.0

        pred_words = set(predicted.lower().split())
        actual_words = set(actual.lower().split())

        if not pred_words or not actual_words:
            return 1.0

        intersection = pred_words & actual_words
        union = pred_words | actual_words

        jaccard = len(intersection) / len(union)
        return 1.0 - jaccard

    def get_delta_t_history(self) -> list[DeltaT]:
        """Get all Δt measurements."""
        return self._delta_t_history.copy()

    def get_aggregate_delta_t(self) -> float:
        """Get aggregate Δt (average of all measurements)."""
        if not self._delta_t_history:
            return 0.0
        return sum(d.delta for d in self._delta_t_history) / len(self._delta_t_history)

    # -------------------------------------------------------------------------
    # Violations
    # -------------------------------------------------------------------------

    def get_violations(self, resolved: bool | None = None) -> list[Violation]:
        """Get violations, optionally filtered by resolved status."""
        if resolved is None:
            return self._violations.copy()
        return [v for v in self._violations if v.resolved == resolved]

    def resolve_violation(self, violation_index: int, resolution: str) -> None:
        """Mark a violation as resolved."""
        if 0 <= violation_index < len(self._violations):
            self._violations[violation_index].resolved = True
            self._violations[violation_index].resolution = resolution
            self._save()

    # -------------------------------------------------------------------------
    # Summary and Analysis
    # -------------------------------------------------------------------------

    def get_direction_summary(self) -> dict[str, Any]:
        """Get a summary of the current direction state."""
        unfulfilled = self.get_unfulfilled()
        triangles, contradictions = self.check_consistency()
        unresolved_violations = self.get_violations(resolved=False)

        return {
            "commitments": {
                "total": len(self._commitments),
                "fulfilled": sum(1 for c in self._commitments.values() if c.fulfilled),
                "abandoned": sum(1 for c in self._commitments.values() if c.abandoned),
                "pending": len(unfulfilled),
            },
            "anchors": {
                "total": len(self._anchors),
                "by_type": {
                    t.value: sum(1 for a in self._anchors.values() if a.anchor_type == t)
                    for t in AnchorType
                },
            },
            "trajectory": self._trajectory.to_dict() if self._trajectory else None,
            "consistency": {
                "triangles": len(triangles),
                "contradictions": len(contradictions),
                "unresolved_violations": len(unresolved_violations),
            },
            "delta_t": {
                "measurements": len(self._delta_t_history),
                "aggregate": self.get_aggregate_delta_t(),
            },
        }

    def get_coherence_score(self) -> float:
        """
        Compute overall coherence score [0, 1].

        Higher = more coherent.
        """
        triangles, contradictions = self.check_consistency()
        unresolved = self.get_violations(resolved=False)
        unfulfilled = self.get_unfulfilled()

        # Penalties
        triangle_penalty = len(triangles) * 0.2
        contradiction_penalty = len(contradictions) * 0.15
        violation_penalty = len(unresolved) * 0.1
        delta_t_penalty = self.get_aggregate_delta_t() * 0.3

        # Start at 1.0 and subtract penalties
        score = 1.0 - triangle_penalty - contradiction_penalty - violation_penalty - delta_t_penalty

        # Bonus for trajectory progress
        if self._trajectory and self._trajectory.completed_waypoints:
            total = len(self._trajectory.completed_waypoints) + len(self._trajectory.waypoints)
            if total > 0:
                progress_bonus = (len(self._trajectory.completed_waypoints) / total) * 0.1
                score += progress_bonus

        return max(0.0, min(1.0, score))

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _save(self) -> None:
        """Save state to storage."""
        if not self.storage_dir:
            return

        self.storage_dir.mkdir(parents=True, exist_ok=True)

        state = {
            "commitments": {k: v.to_dict() for k, v in self._commitments.items()},
            "anchors": {k: v.to_dict() for k, v in self._anchors.items()},
            "trajectory": self._trajectory.to_dict() if self._trajectory else None,
            "belief_graph": self._belief_graph.to_dict(),
            "delta_t_history": [d.to_dict() for d in self._delta_t_history],
            "violations": [v.to_dict() for v in self._violations],
            "position_history": [
                (pos, ts.isoformat()) for pos, ts in self._position_history
            ],
        }

        (self.storage_dir / "direction.json").write_text(json.dumps(state, indent=2))

    def _load(self) -> None:
        """Load state from storage."""
        if not self.storage_dir:
            return

        state_file = self.storage_dir / "direction.json"
        if not state_file.exists():
            return

        state = json.loads(state_file.read_text())

        self._commitments = {
            k: Commitment.from_dict(v)
            for k, v in state.get("commitments", {}).items()
        }
        self._anchors = {
            k: Anchor.from_dict(v)
            for k, v in state.get("anchors", {}).items()
        }
        if state.get("trajectory"):
            self._trajectory = Trajectory.from_dict(state["trajectory"])
        self._belief_graph = BeliefGraph.from_dict(state.get("belief_graph", {}))
        self._delta_t_history = [
            DeltaT.from_dict(d) for d in state.get("delta_t_history", [])
        ]
        self._violations = [
            Violation.from_dict(v) for v in state.get("violations", [])
        ]
        self._position_history = [
            (pos, datetime.fromisoformat(ts))
            for pos, ts in state.get("position_history", [])
        ]


# =============================================================================
# Convenience Functions
# =============================================================================

def create_direction_ledger(storage_dir: Path | None = None) -> DirectionLedger:
    """Create a direction ledger."""
    return DirectionLedger(storage_dir)


def create_fiction_anchors(ledger: DirectionLedger, world_rules: list[str]) -> list[str]:
    """
    Convenience function to add world rules as anchors.

    Returns list of anchor IDs.
    """
    return [
        ledger.add_anchor(rule, AnchorType.WORLD_RULE)
        for rule in world_rules
    ]


def create_nonfiction_anchors(
    ledger: DirectionLedger,
    citations: list[tuple[str, str]],  # (content, source)
) -> list[str]:
    """
    Convenience function to add citations as anchors.

    Returns list of anchor IDs.
    """
    return [
        ledger.add_anchor(content, AnchorType.CITATION, source=source)
        for content, source in citations
    ]


def create_thesis_commitment(
    ledger: DirectionLedger,
    thesis: str,
    deadline: int | None = None,
) -> str:
    """Create a thesis commitment (non-fiction)."""
    return ledger.add_commitment(
        thesis,
        CommitmentType.THESIS,
        deadline=deadline,
        deadline_type="section",
    )


def create_chekhov_commitment(
    ledger: DirectionLedger,
    setup: str,
    payoff_deadline: int,
) -> str:
    """Create a Chekhov's gun commitment (fiction)."""
    return ledger.add_commitment(
        setup,
        CommitmentType.CHEKHOV,
        deadline=payoff_deadline,
        deadline_type="chapter",
    )
