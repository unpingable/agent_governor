"""
Epistemic governance: Provenance, confidence, and evidence tracking.

Ported from the non-agentic epistemic governor. These features add:
- Provenance tracking: HOW claims were established (not just WHAT)
- Confidence modeling: Bounded [0,1] with "The Money Rule"
- Dangerous claims detection: High confidence + ungrounded = flagged
- Evidence references: Structured pointers to supporting evidence

Key invariants:
1. Provenance NEVER upgrades without evidence
2. Confidence can ONLY increase with evidence (not repetition, elaboration, peer agreement)
3. PEER_ASSERTED claims start at low confidence and cannot increase without evidence

Toggle via config.toml:
    [epistemic]
    provenance_tracking = true
    confidence_modeling = true
    dangerous_claim_detection = true
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import hashlib
import sqlite3
import uuid


# =============================================================================
# Provenance Types (The Spine)
# =============================================================================


class Provenance(str, Enum):
    """
    Provenance types for claims - tracks HOW information was established.

    This is the spine of epistemic governance.
    Provenance NEVER upgrades without evidence.

    The hierarchy (most to least trusted):
    - OBSERVED: Direct observation (rare in agent context)
    - RETRIEVED: From tool with trace (verifiable)
    - USER_PROVIDED: Human supplied (trusted source)
    - DERIVED: Logically inferred from grounded claims
    - PEER_ASSERTED: From another agent (NEVER trust without evidence)
    - ASSUMED: Hypothetical/conditional (lowest trust)
    """

    OBSERVED = "observed"
    """Direct observation - rare, requires sensor/direct access."""

    RETRIEVED = "retrieved"
    """From tool execution with trace - verifiable computation."""

    USER_PROVIDED = "user_provided"
    """User supplied source/content - trusted human input."""

    DERIVED = "derived"
    """Logically inferred from other grounded claims."""

    PEER_ASSERTED = "peer_asserted"
    """From another agent - NEVER trust without independent evidence."""

    ASSUMED = "assumed"
    """Hypothetical or conditional - lowest trust level."""

    @property
    def is_grounded(self) -> bool:
        """Is this provenance inherently grounded (has external support)?"""
        return self in {Provenance.OBSERVED, Provenance.RETRIEVED, Provenance.USER_PROVIDED}

    @property
    def requires_evidence_for_confidence(self) -> bool:
        """Does this provenance require evidence to increase confidence?"""
        return self in {Provenance.ASSUMED, Provenance.PEER_ASSERTED}

    @property
    def trust_level(self) -> int:
        """Numeric trust level for comparison (higher = more trusted)."""
        levels = {
            Provenance.OBSERVED: 5,
            Provenance.RETRIEVED: 4,
            Provenance.USER_PROVIDED: 3,
            Provenance.DERIVED: 2,
            Provenance.PEER_ASSERTED: 1,
            Provenance.ASSUMED: 0,
        }
        return levels[self]


# Forbidden provenance promotions - these can NEVER happen
FORBIDDEN_PROMOTIONS: set[tuple[Provenance, Provenance]] = {
    # Cannot promote anything to OBSERVED (that's sacred)
    (Provenance.ASSUMED, Provenance.OBSERVED),
    (Provenance.PEER_ASSERTED, Provenance.OBSERVED),
    (Provenance.DERIVED, Provenance.OBSERVED),
    (Provenance.RETRIEVED, Provenance.OBSERVED),
    (Provenance.USER_PROVIDED, Provenance.OBSERVED),
}

# Promotions that REQUIRE evidence (but are allowed with it)
PROMOTIONS_REQUIRING_EVIDENCE: set[tuple[Provenance, Provenance]] = {
    (Provenance.ASSUMED, Provenance.DERIVED),
    (Provenance.ASSUMED, Provenance.RETRIEVED),
    (Provenance.ASSUMED, Provenance.USER_PROVIDED),
    (Provenance.PEER_ASSERTED, Provenance.DERIVED),
    (Provenance.PEER_ASSERTED, Provenance.RETRIEVED),
    (Provenance.PEER_ASSERTED, Provenance.USER_PROVIDED),
}


# =============================================================================
# Evidence References
# =============================================================================


class EvidenceType(str, Enum):
    """Types of evidence that can support claims."""

    TOOL_TRACE = "tool_trace"
    """Output from tool execution with verifiable trace."""

    URL = "url"
    """External URL reference."""

    DOCUMENT = "document"
    """Document reference with hash/locator."""

    HUMAN_INPUT = "human_input"
    """Explicit human confirmation/input."""

    RECEIPT = "receipt"
    """Governor receipt (FileSnapshot, CmdRun, etc.)."""

    # Extended types for jurisdictions
    SENSOR_DATA = "sensor_data"
    """Physical measurement from sensors."""

    CRYPTOGRAPHIC_PROOF = "cryptographic_proof"
    """Verifiable computation or signature."""

    SUBJECTIVE_REPORT = "subjective_report"
    """First-person experience report (therapy/introspection mode)."""

    NARRATIVE_CONSISTENCY = "narrative_consistency"
    """Story-internal logic (fiction mode)."""

    PEDAGOGICAL_FRAME = "pedagogical_frame"
    """Known simplification for teaching purposes."""

    CROSS_SOURCE = "cross_source"
    """Corroboration from multiple independent sources (forensic mode)."""

    # Layer 3: Specialized evidence types for type validation
    CALC_RESULT = "calc_result"
    """Calculator or formal derivation output."""

    TEST_RESULT = "test_result"
    """Test suite, compiler, or linter execution result."""

    WEB_SOURCE = "web_source"
    """Web page reference with fetch timestamp."""

    LIVE_RETRIEVAL = "live_retrieval"
    """Live API or data fetch with recency guarantee."""


@dataclass
class EvidenceRef:
    """
    Reference to evidence supporting a claim.

    Evidence is opaque to the ledger - the governor just needs to know
    it exists, what type it is, and what aspect of the claim it supports.
    """

    ref_id: str
    ref_type: EvidenceType
    locator: str  # URL, hash, trace ID, etc.
    scope: str  # What aspect of the claim this supports

    # Optional metadata
    retrieved_at: datetime | None = None
    confidence: float = 1.0  # How reliable is this evidence? [0, 1]

    # Persistence fields (populated when stored in SQLite)
    evidence_id: str | None = None       # SQLite PK
    claim_id: str | None = None          # Which claim this evidence supports
    collected_by: str | None = None      # Agent that collected this evidence
    run_id: str | None = None            # FK to run_provenance
    content_hash: str | None = None      # SHA-256 of ref_type:locator:scope
    persisted_at: datetime | None = None # When written to DB

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "ref_id": self.ref_id,
            "ref_type": self.ref_type.value,
            "locator": self.locator,
            "scope": self.scope,
            "confidence": self.confidence,
            "retrieved_at": self.retrieved_at.isoformat() if self.retrieved_at else None,
        }
        # Include persistence fields only when set (no JSON bloat on existing data)
        if self.evidence_id is not None:
            d["evidence_id"] = self.evidence_id
        if self.claim_id is not None:
            d["claim_id"] = self.claim_id
        if self.collected_by is not None:
            d["collected_by"] = self.collected_by
        if self.run_id is not None:
            d["run_id"] = self.run_id
        if self.content_hash is not None:
            d["content_hash"] = self.content_hash
        if self.persisted_at is not None:
            d["persisted_at"] = self.persisted_at.isoformat()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRef":
        return cls(
            ref_id=data["ref_id"],
            ref_type=EvidenceType(data["ref_type"]),
            locator=data["locator"],
            scope=data["scope"],
            confidence=data.get("confidence", 1.0),
            retrieved_at=(
                datetime.fromisoformat(data["retrieved_at"])
                if data.get("retrieved_at")
                else None
            ),
            evidence_id=data.get("evidence_id"),
            claim_id=data.get("claim_id"),
            collected_by=data.get("collected_by"),
            run_id=data.get("run_id"),
            content_hash=data.get("content_hash"),
            persisted_at=(
                datetime.fromisoformat(data["persisted_at"])
                if data.get("persisted_at")
                else None
            ),
        )

    @classmethod
    def from_tool_trace(cls, trace_id: str, scope: str) -> "EvidenceRef":
        """Create evidence ref from a tool trace."""
        return cls(
            ref_id=f"ev_{uuid.uuid4().hex[:8]}",
            ref_type=EvidenceType.TOOL_TRACE,
            locator=trace_id,
            scope=scope,
            retrieved_at=datetime.now(),
        )

    @classmethod
    def from_url(cls, url: str, scope: str) -> "EvidenceRef":
        """Create evidence ref from a URL."""
        return cls(
            ref_id=f"ev_{uuid.uuid4().hex[:8]}",
            ref_type=EvidenceType.URL,
            locator=url,
            scope=scope,
            retrieved_at=datetime.now(),
        )

    @classmethod
    def from_receipt(cls, receipt_hash: str, scope: str) -> "EvidenceRef":
        """Create evidence ref from a governor receipt."""
        return cls(
            ref_id=f"ev_{uuid.uuid4().hex[:8]}",
            ref_type=EvidenceType.RECEIPT,
            locator=receipt_hash,
            scope=scope,
            retrieved_at=datetime.now(),
        )

    @classmethod
    def from_human(cls, description: str, scope: str) -> "EvidenceRef":
        """Create evidence ref from human input."""
        return cls(
            ref_id=f"ev_{uuid.uuid4().hex[:8]}",
            ref_type=EvidenceType.HUMAN_INPUT,
            locator=description,
            scope=scope,
            retrieved_at=datetime.now(),
        )

    @classmethod
    def from_calc_result(cls, trace_id: str, scope: str) -> "EvidenceRef":
        """Create evidence ref from a calculator or formal derivation output."""
        return cls(
            ref_id=f"ev_{uuid.uuid4().hex[:8]}",
            ref_type=EvidenceType.CALC_RESULT,
            locator=trace_id,
            scope=scope,
            retrieved_at=datetime.now(),
        )

    @classmethod
    def from_test_result(cls, trace_id: str, scope: str) -> "EvidenceRef":
        """Create evidence ref from a test suite, compiler, or linter result."""
        return cls(
            ref_id=f"ev_{uuid.uuid4().hex[:8]}",
            ref_type=EvidenceType.TEST_RESULT,
            locator=trace_id,
            scope=scope,
            retrieved_at=datetime.now(),
        )

    @classmethod
    def from_web_source(cls, url: str, scope: str) -> "EvidenceRef":
        """Create evidence ref from a web page reference."""
        return cls(
            ref_id=f"ev_{uuid.uuid4().hex[:8]}",
            ref_type=EvidenceType.WEB_SOURCE,
            locator=url,
            scope=scope,
            retrieved_at=datetime.now(),
        )

    @classmethod
    def from_live_retrieval(cls, locator: str, scope: str) -> "EvidenceRef":
        """Create evidence ref from a live API or data fetch."""
        return cls(
            ref_id=f"ev_{uuid.uuid4().hex[:8]}",
            ref_type=EvidenceType.LIVE_RETRIEVAL,
            locator=locator,
            scope=scope,
            retrieved_at=datetime.now(),
        )

    def compute_content_hash(self) -> str:
        """SHA-256 of ref_type:locator:scope, first 16 chars."""
        data = f"{self.ref_type.value}:{self.locator}:{self.scope}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "EvidenceRef":
        """Create from SQLite row. Maps evidence_id and kind→ref_type."""
        return cls(
            ref_id=row["evidence_id"],
            ref_type=EvidenceType(row["kind"]),
            locator=row["locator"],
            scope=row["scope"],
            confidence=row["confidence"],
            retrieved_at=None,
            evidence_id=row["evidence_id"],
            claim_id=row["claim_id"],
            collected_by=row["collected_by"],
            run_id=row["run_id"],
            content_hash=row["content_hash"],
            persisted_at=datetime.fromisoformat(row["created_at"]),
        )


# =============================================================================
# Grounded Claim (Claim with Epistemic Metadata)
# =============================================================================


class GroundedClaimStatus(str, Enum):
    """Status of a grounded claim."""

    ACTIVE = "active"
    """Currently asserted."""

    BLOCKED = "blocked"
    """Cannot be asserted due to missing grounding."""

    RETRACTED = "retracted"
    """Explicitly withdrawn (SUCCESS, not failure)."""

    PROMOTED = "promoted"
    """Promoted to commitment."""


class ClaimStatus(str, Enum):
    """Epistemic lifecycle status — separate from GroundedClaimStatus (governance)
    and QuorumStatus (process). Shape defined in L2, FSM enforcement in L6."""

    PROPOSED = "proposed"
    SUPPORTED = "supported"
    CONTESTED = "contested"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"
    REFUSED = "refused"
    STALE = "stale"


# QuorumStatus → ClaimStatus projection
# QuorumStatus is process state, ClaimStatus is epistemic lifecycle.
QUORUM_TO_CLAIM_STATUS: dict[str, ClaimStatus] = {
    "collecting": ClaimStatus.PROPOSED,
    "stabilizing": ClaimStatus.PROPOSED,
    "reached": ClaimStatus.SUPPORTED,
    "failed": ClaimStatus.REFUSED,
    "expired": ClaimStatus.EXPIRED,
    "contested": ClaimStatus.CONTESTED,
    "escalated": ClaimStatus.CONTESTED,
    "resolved_commit": ClaimStatus.SUPPORTED,
    "resolved_reject": ClaimStatus.INVALIDATED,
}


def project_quorum_status(quorum_status_value: str) -> ClaimStatus | None:
    """Project QuorumStatus to ClaimStatus. Returns None if unmapped."""
    return QUORUM_TO_CLAIM_STATUS.get(quorum_status_value)


class PromotionResult(str, Enum):
    """Result of a provenance promotion attempt."""

    SUCCESS = "success"
    FORBIDDEN = "forbidden"
    NEEDS_EVIDENCE = "needs_evidence"


# Default confidence levels by provenance
DEFAULT_CONFIDENCE: dict[Provenance, float] = {
    Provenance.OBSERVED: 0.95,
    Provenance.RETRIEVED: 0.85,
    Provenance.USER_PROVIDED: 0.80,
    Provenance.DERIVED: 0.70,
    Provenance.PEER_ASSERTED: 0.20,  # Low - multi-agent resonance killer
    Provenance.ASSUMED: 0.30,
}

# Maximum confidence for peer-asserted claims without evidence
MAX_PEER_CONFIDENCE = 0.30

# Threshold for "high confidence" (used in dangerous claim detection)
HIGH_CONFIDENCE_THRESHOLD = 0.70


@dataclass
class GroundedClaim:
    """
    A claim with epistemic metadata: provenance, confidence, and evidence.

    This wraps or extends the base Claim with tracking for:
    - How the claim was established (provenance)
    - How confident we are (bounded [0, 1])
    - What evidence supports it
    - Whether it's dangerous (high confidence + ungrounded)

    Key invariants:
    1. Provenance never upgrades without evidence
    2. Confidence cannot increase on ASSUMED/PEER_ASSERTED without evidence
    3. High confidence + ungrounded = dangerous (flagged)
    """

    claim_id: str
    content: str  # Normalized assertion text or claim description
    provenance: Provenance
    confidence: float  # Bounded [0, 1]

    # Evidence
    evidence_refs: list[EvidenceRef] = field(default_factory=list)

    # Status
    status: GroundedClaimStatus = GroundedClaimStatus.ACTIVE

    # Temporal tracking
    created_at: datetime = field(default_factory=datetime.now)
    created_at_step: int = 0
    last_updated_at: datetime = field(default_factory=datetime.now)
    last_updated_step: int = 0

    # Retraction tracking
    retracted_at_step: int | None = None
    retraction_reason: str | None = None

    # Source tracking (for multi-agent)
    source_agent_id: str | None = None

    # Commit level (from strict mode evaluation, Layer 2)
    commit_level: str | None = None  # "hard", "soft", "refused", or None (unclassified)

    # Explicit assumptions (ungrounded dependencies, Layer 2)
    assumptions: list[str] = field(default_factory=list)

    # Epistemic lifecycle status (Layer 2 shape, Layer 6 enforcement)
    # Separate from GroundedClaimStatus (governance) and QuorumStatus (process)
    epistemic_status: ClaimStatus | None = None  # None = legacy/unclassified

    def __post_init__(self):
        """Clamp confidence to valid range."""
        self.confidence = max(0.0, min(1.0, self.confidence))

        # Enforce max confidence for peer assertions
        if self.provenance == Provenance.PEER_ASSERTED:
            self.confidence = min(self.confidence, MAX_PEER_CONFIDENCE)

    @property
    def content_hash(self) -> str:
        """Content hash for deduplication."""
        return hashlib.sha256(self.content.lower().strip().encode()).hexdigest()[:16]

    @property
    def is_grounded(self) -> bool:
        """Is this claim grounded (has evidence or grounded provenance)?"""
        return self.provenance.is_grounded or len(self.evidence_refs) > 0

    @property
    def is_active(self) -> bool:
        return self.status == GroundedClaimStatus.ACTIVE

    @property
    def is_high_confidence(self) -> bool:
        return self.confidence >= HIGH_CONFIDENCE_THRESHOLD

    @property
    def is_dangerous(self) -> bool:
        """
        Is this claim dangerous?

        Dangerous = high confidence WITHOUT grounding.
        These claims are asserted strongly but have no evidence.
        """
        return self.is_high_confidence and not self.is_grounded

    @property
    def is_hard(self) -> bool:
        """Is this claim committed at HARD level?"""
        return self.commit_level == "hard"

    @property
    def is_soft(self) -> bool:
        """Is this claim committed at SOFT level?"""
        return self.commit_level == "soft"

    @property
    def is_refused(self) -> bool:
        """Was this claim refused by strict mode?"""
        return self.commit_level == "refused"

    @property
    def has_assumptions(self) -> bool:
        """Does this claim have explicit ungrounded assumptions?"""
        return len(self.assumptions) > 0

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "claim_id": self.claim_id,
            "content": self.content,
            "provenance": self.provenance.value,
            "confidence": self.confidence,
            "evidence_refs": [e.to_dict() for e in self.evidence_refs],
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "created_at_step": self.created_at_step,
            "last_updated_at": self.last_updated_at.isoformat(),
            "last_updated_step": self.last_updated_step,
            "is_grounded": self.is_grounded,
            "is_dangerous": self.is_dangerous,
            "source_agent_id": self.source_agent_id,
        }
        if self.commit_level is not None:
            d["commit_level"] = self.commit_level
        if self.assumptions:
            d["assumptions"] = list(self.assumptions)
        if self.epistemic_status is not None:
            d["epistemic_status"] = self.epistemic_status.value
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GroundedClaim":
        epistemic_status_raw = data.get("epistemic_status")
        epistemic_status = ClaimStatus(epistemic_status_raw) if epistemic_status_raw else None
        return cls(
            claim_id=data["claim_id"],
            content=data["content"],
            provenance=Provenance(data["provenance"]),
            confidence=data["confidence"],
            evidence_refs=[EvidenceRef.from_dict(e) for e in data.get("evidence_refs", [])],
            status=GroundedClaimStatus(data.get("status", "active")),
            created_at=datetime.fromisoformat(data["created_at"]),
            created_at_step=data.get("created_at_step", 0),
            last_updated_at=datetime.fromisoformat(data.get("last_updated_at", data["created_at"])),
            last_updated_step=data.get("last_updated_step", 0),
            source_agent_id=data.get("source_agent_id"),
            commit_level=data.get("commit_level"),
            assumptions=data.get("assumptions", []),
            epistemic_status=epistemic_status,
        )


# =============================================================================
# Epistemic Ledger
# =============================================================================


@dataclass
class PromotionAttempt:
    """Record of a provenance promotion attempt."""

    claim_id: str
    from_provenance: Provenance
    to_provenance: Provenance
    result: PromotionResult
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)


class EpistemicLedger:
    """
    Ledger for tracking grounded claims with epistemic metadata.

    Enforces key invariants:
    1. Provenance never upgrades without evidence
    2. Confidence cannot increase on ASSUMED/PEER_ASSERTED without evidence
    3. Tracks dangerous claims (high confidence + ungrounded)

    This is the instrumentation that makes epistemic governance real.

    Optionally backed by SQLite storage (write-through on mutations).
    When storage is None, operates purely in-memory (backward compatible).
    """

    def __init__(self, storage=None, evidence_store=None):
        self.storage = storage  # Optional Storage instance
        self.evidence_store = evidence_store  # Optional EvidenceStore instance
        self.claims: dict[str, GroundedClaim] = {}
        self.step: int = 0

        # History
        self.promotion_history: list[PromotionAttempt] = []

        # Metrics
        self.total_claims_created: int = 0
        self.total_promotions_attempted: int = 0
        self.total_promotions_forbidden: int = 0
        self.total_retractions: int = 0

        # Load from storage if available
        if self.storage:
            self._load_from_storage()

    # =========================================================================
    # Storage Helpers (write-through persistence)
    # =========================================================================

    def _load_from_storage(self) -> None:
        """Load claims and meta from SQLite storage."""
        if not self.storage:
            return

        cursor = self.storage.conn.cursor()

        # Load meta
        cursor.execute("SELECT * FROM epistemic_ledger_meta WHERE id = 1")
        meta_row = cursor.fetchone()
        if meta_row:
            self.step = meta_row["step"]
            self.total_claims_created = meta_row["total_claims_created"]
            self.total_promotions_attempted = meta_row["total_promotions_attempted"]
            self.total_promotions_forbidden = meta_row["total_promotions_forbidden"]
            self.total_retractions = meta_row["total_retractions"]
        else:
            # Initialize meta row
            with self.storage.transaction() as cur:
                cur.execute(
                    "INSERT INTO epistemic_ledger_meta "
                    "(id, step, total_claims_created, total_promotions_attempted, "
                    "total_promotions_forbidden, total_retractions) "
                    "VALUES (1, 0, 0, 0, 0, 0)"
                )

        # Load claims
        cursor.execute("SELECT * FROM epistemic_claims")
        for row in cursor.fetchall():
            claim = self._from_row(row)
            self.claims[claim.claim_id] = claim

    def _persist_claim(self, claim: GroundedClaim) -> None:
        """UPSERT a claim into SQLite storage."""
        if not self.storage:
            return

        row = self._to_row(claim)
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        values = list(row.values())

        with self.storage.transaction() as cursor:
            cursor.execute(
                f"INSERT OR REPLACE INTO epistemic_claims ({columns}) "
                f"VALUES ({placeholders})",
                values,
            )

    def _persist_meta(self) -> None:
        """Update the ledger meta row in SQLite."""
        if not self.storage:
            return

        with self.storage.transaction() as cursor:
            cursor.execute(
                "UPDATE epistemic_ledger_meta SET "
                "step = ?, total_claims_created = ?, "
                "total_promotions_attempted = ?, total_promotions_forbidden = ?, "
                "total_retractions = ? WHERE id = 1",
                (
                    self.step,
                    self.total_claims_created,
                    self.total_promotions_attempted,
                    self.total_promotions_forbidden,
                    self.total_retractions,
                ),
            )

    @staticmethod
    def _to_row(claim: GroundedClaim) -> dict[str, Any]:
        """Convert GroundedClaim to SQLite row dict."""
        import json as _json

        return {
            "claim_id": claim.claim_id,
            "content": claim.content,
            "content_hash": claim.content_hash,
            "provenance": claim.provenance.value,
            "confidence": claim.confidence,
            "governance_status": claim.status.value,
            "epistemic_status": claim.epistemic_status.value if claim.epistemic_status else None,
            "commit_level": claim.commit_level,
            "assumptions_json": _json.dumps(claim.assumptions),
            "source_agent_id": claim.source_agent_id,
            "created_at": claim.created_at.isoformat(),
            "created_at_step": claim.created_at_step,
            "last_updated_at": claim.last_updated_at.isoformat(),
            "last_updated_step": claim.last_updated_step,
            "retracted_at_step": claim.retracted_at_step,
            "retraction_reason": claim.retraction_reason,
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> GroundedClaim:
        """Convert SQLite row to GroundedClaim."""
        import json as _json

        epistemic_status_raw = row["epistemic_status"]
        epistemic_status = ClaimStatus(epistemic_status_raw) if epistemic_status_raw else None
        assumptions_raw = row["assumptions_json"]
        assumptions = _json.loads(assumptions_raw) if assumptions_raw else []

        return GroundedClaim(
            claim_id=row["claim_id"],
            content=row["content"],
            provenance=Provenance(row["provenance"]),
            confidence=row["confidence"],
            evidence_refs=[],  # Evidence loaded separately via EvidenceStore
            status=GroundedClaimStatus(row["governance_status"]),
            epistemic_status=epistemic_status,
            commit_level=row["commit_level"],
            assumptions=assumptions,
            source_agent_id=row["source_agent_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            created_at_step=row["created_at_step"],
            last_updated_at=datetime.fromisoformat(row["last_updated_at"]),
            last_updated_step=row["last_updated_step"],
            retracted_at_step=row["retracted_at_step"],
            retraction_reason=row["retraction_reason"],
        )

    def tick(self) -> None:
        """Advance the step counter."""
        self.step += 1
        if self.storage:
            self._persist_meta()

    # =========================================================================
    # Claim Creation
    # =========================================================================

    def new_claim(
        self,
        content: str,
        provenance: Provenance,
        confidence: float | None = None,
        source_agent_id: str | None = None,
    ) -> GroundedClaim:
        """
        Create a new grounded claim.

        If confidence is not provided, uses default for the provenance type.
        """
        if confidence is None:
            confidence = DEFAULT_CONFIDENCE.get(provenance, 0.5)

        claim = GroundedClaim(
            claim_id=f"gc_{uuid.uuid4().hex[:12]}",
            content=content.strip(),
            provenance=provenance,
            confidence=confidence,
            created_at_step=self.step,
            last_updated_step=self.step,
            source_agent_id=source_agent_id,
        )

        self.claims[claim.claim_id] = claim
        self.total_claims_created += 1

        if self.storage:
            self._persist_claim(claim)
            self._persist_meta()

        return claim

    def new_assumed_claim(
        self,
        content: str,
        confidence: float = 0.30,
    ) -> GroundedClaim:
        """Create an ASSUMED claim (default for model assertions)."""
        return self.new_claim(content, Provenance.ASSUMED, confidence)

    def new_retrieved_claim(
        self,
        content: str,
        evidence: EvidenceRef,
        confidence: float = 0.85,
    ) -> GroundedClaim:
        """Create a RETRIEVED claim with evidence."""
        claim = self.new_claim(content, Provenance.RETRIEVED, confidence)
        claim.evidence_refs.append(evidence)
        return claim

    def new_peer_claim(
        self,
        content: str,
        peer_agent_id: str,
        confidence: float = 0.20,
    ) -> GroundedClaim:
        """
        Create a claim from a peer agent.

        Peer claims start at LOW confidence and CANNOT increase without evidence.
        This is the multi-agent resonance killer.
        """
        # Cap peer confidence
        confidence = min(MAX_PEER_CONFIDENCE, confidence)

        return self.new_claim(
            content,
            Provenance.PEER_ASSERTED,
            confidence,
            source_agent_id=peer_agent_id,
        )

    # =========================================================================
    # Evidence Attachment
    # =========================================================================

    def attach_evidence(self, claim_id: str, ref: EvidenceRef) -> bool:
        """
        Attach evidence to a claim.

        Returns True if evidence was attached.
        Also persists via EvidenceStore if available.
        """
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]
        claim.evidence_refs.append(ref)
        claim.last_updated_at = datetime.now()
        claim.last_updated_step = self.step

        if self.evidence_store:
            self.evidence_store.persist_evidence(claim_id, ref)
        if self.storage:
            self._persist_claim(claim)

        return True

    def has_evidence(self, claim_id: str) -> bool:
        """Check if a claim has any evidence."""
        if claim_id not in self.claims:
            return False
        return len(self.claims[claim_id].evidence_refs) > 0

    # =========================================================================
    # Provenance Promotion (The Hard Part)
    # =========================================================================

    def can_promote(
        self,
        claim_id: str,
        new_provenance: Provenance,
    ) -> tuple[bool, str]:
        """
        Check if a provenance promotion is allowed.

        Returns (allowed, reason).
        """
        if claim_id not in self.claims:
            return False, "Claim not found"

        claim = self.claims[claim_id]
        old_prov = claim.provenance

        # Same provenance is always allowed
        if old_prov == new_provenance:
            return True, "No change"

        # Check forbidden promotions
        if (old_prov, new_provenance) in FORBIDDEN_PROMOTIONS:
            return False, f"Forbidden: {old_prov.value} -> {new_provenance.value}"

        # Check evidence requirements
        if (old_prov, new_provenance) in PROMOTIONS_REQUIRING_EVIDENCE:
            if not claim.evidence_refs:
                return False, f"Requires evidence: {old_prov.value} -> {new_provenance.value}"

        # Promotion to grounded types from risky provenances requires evidence
        if new_provenance.is_grounded and old_prov.requires_evidence_for_confidence:
            if not claim.evidence_refs:
                return False, "Grounded promotion requires evidence"

        return True, "OK"

    def promote(
        self,
        claim_id: str,
        new_provenance: Provenance,
    ) -> PromotionResult:
        """
        Attempt to promote a claim to a new provenance level.

        Enforces "no promotion without evidence" for risky upgrades.
        """
        self.total_promotions_attempted += 1

        allowed, reason = self.can_promote(claim_id, new_provenance)

        claim = self.claims.get(claim_id)
        old_prov = claim.provenance if claim else Provenance.ASSUMED

        if not allowed:
            self.total_promotions_forbidden += 1
            result = (
                PromotionResult.FORBIDDEN
                if "Forbidden" in reason
                else PromotionResult.NEEDS_EVIDENCE
            )

            self.promotion_history.append(
                PromotionAttempt(
                    claim_id=claim_id,
                    from_provenance=old_prov,
                    to_provenance=new_provenance,
                    result=result,
                    reason=reason,
                )
            )

            return result

        # Perform promotion
        claim.provenance = new_provenance
        claim.last_updated_at = datetime.now()
        claim.last_updated_step = self.step

        self.promotion_history.append(
            PromotionAttempt(
                claim_id=claim_id,
                from_provenance=old_prov,
                to_provenance=new_provenance,
                result=PromotionResult.SUCCESS,
                reason="OK",
            )
        )

        if self.storage:
            self._persist_claim(claim)
            self._persist_meta()

        return PromotionResult.SUCCESS

    # =========================================================================
    # Confidence Updates (The Money Rule)
    # =========================================================================

    def update_confidence(
        self,
        claim_id: str,
        delta: float,
        requires_evidence: bool = True,
    ) -> bool:
        """
        Update claim confidence.

        THE MONEY RULE:
        - Confidence can ONLY increase with evidence
        - NOT increased by: repetition, elaboration, peer agreement, self-consistency
        - For ASSUMED/PEER_ASSERTED: confidence cannot increase without evidence

        Returns True if the update was applied, False if blocked.
        """
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]

        # Key rule: no confidence increase without evidence for risky provenances
        if requires_evidence and delta > 0:
            if claim.provenance.requires_evidence_for_confidence:
                if not claim.evidence_refs:
                    # Silently refuse to increase confidence
                    return False

        # Apply update
        old_confidence = claim.confidence
        new_confidence = max(0.0, min(1.0, claim.confidence + delta))

        # Enforce peer confidence cap
        if claim.provenance == Provenance.PEER_ASSERTED:
            new_confidence = min(new_confidence, MAX_PEER_CONFIDENCE)

        claim.confidence = new_confidence
        claim.last_updated_at = datetime.now()
        claim.last_updated_step = self.step

        if self.storage:
            self._persist_claim(claim)

        return True

    def decay_ungrounded_confidence(self, decay: float = 0.1) -> int:
        """
        Decay confidence on all ungrounded claims.

        Returns count of claims affected.
        """
        count = 0
        for claim in self.active_claims():
            if not claim.is_grounded:
                claim.confidence = max(0.0, claim.confidence - decay)
                claim.last_updated_at = datetime.now()
                claim.last_updated_step = self.step
                count += 1
        return count

    # =========================================================================
    # Status Changes
    # =========================================================================

    def block(self, claim_id: str, reason: str = "Missing grounding") -> bool:
        """Block a claim (cannot be asserted due to missing grounding)."""
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]
        claim.status = GroundedClaimStatus.BLOCKED
        claim.last_updated_at = datetime.now()
        claim.last_updated_step = self.step

        if self.storage:
            self._persist_claim(claim)

        return True

    def retract(self, claim_id: str, reason: str = "Explicit retraction") -> bool:
        """
        Retract a claim.

        Retraction is NOT failure. Retraction is SUCCESSFUL RECOVERY.
        """
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]
        claim.status = GroundedClaimStatus.RETRACTED
        claim.retracted_at_step = self.step
        claim.retraction_reason = reason
        claim.last_updated_at = datetime.now()
        claim.last_updated_step = self.step

        self.total_retractions += 1

        if self.storage:
            self._persist_claim(claim)
            self._persist_meta()

        return True

    def unblock(self, claim_id: str) -> bool:
        """Unblock a claim (after evidence is attached)."""
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]
        if claim.status != GroundedClaimStatus.BLOCKED:
            return False

        # Can only unblock if now grounded
        if not claim.is_grounded:
            return False

        claim.status = GroundedClaimStatus.ACTIVE
        claim.last_updated_at = datetime.now()
        claim.last_updated_step = self.step

        if self.storage:
            self._persist_claim(claim)

        return True

    # =========================================================================
    # Commit Level (Layer 2 — wiring to strict.py)
    # =========================================================================

    def set_commit_level(self, claim_id: str, level: str) -> bool:
        """
        Set the commit level on a claim.

        Level must be one of: "hard", "soft", "refused".
        Returns True if set, False if claim not found or invalid level.
        """
        if level not in {"hard", "soft", "refused"}:
            return False
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]
        claim.commit_level = level
        claim.last_updated_at = datetime.now()
        claim.last_updated_step = self.step

        if self.storage:
            self._persist_claim(claim)

        return True

    def add_assumption(self, claim_id: str, assumption: str) -> bool:
        """
        Add an explicit assumption to a claim.

        Assumptions are ungrounded dependencies that the claim relies on.
        Returns True if added, False if claim not found.
        """
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]
        if assumption not in claim.assumptions:
            claim.assumptions.append(assumption)
            claim.last_updated_at = datetime.now()
            claim.last_updated_step = self.step

            if self.storage:
                self._persist_claim(claim)

        return True

    def hard_claims(self) -> list[GroundedClaim]:
        """Get all active claims with HARD commit level."""
        return [c for c in self.active_claims() if c.is_hard]

    def soft_claims(self) -> list[GroundedClaim]:
        """Get all active claims with SOFT commit level."""
        return [c for c in self.active_claims() if c.is_soft]

    def refused_claims(self) -> list[GroundedClaim]:
        """Get all claims with REFUSED commit level."""
        return [c for c in self.claims.values() if c.is_refused]

    def claims_with_assumptions(self) -> list[GroundedClaim]:
        """Get all active claims that have explicit assumptions."""
        return [c for c in self.active_claims() if c.has_assumptions]

    # =========================================================================
    # Epistemic Status (Layer 2 shape, Layer 6 enforcement)
    # =========================================================================

    def set_epistemic_status(self, claim_id: str, status: ClaimStatus) -> bool:
        """
        Set the epistemic lifecycle status on a claim.

        No FSM enforcement yet (that's Layer 6). For now, simple setter.
        Returns True if set, False if claim not found.
        """
        if claim_id not in self.claims:
            return False

        claim = self.claims[claim_id]
        claim.epistemic_status = status
        claim.last_updated_at = datetime.now()
        claim.last_updated_step = self.step

        if self.storage:
            self._persist_claim(claim)

        return True

    def claims_by_epistemic_status(self, status: ClaimStatus) -> list[GroundedClaim]:
        """Get all claims with a specific epistemic lifecycle status."""
        return [c for c in self.claims.values() if c.epistemic_status == status]

    # =========================================================================
    # Queries
    # =========================================================================

    def get(self, claim_id: str) -> GroundedClaim | None:
        """Get a claim by ID."""
        return self.claims.get(claim_id)

    def active_claims(self) -> list[GroundedClaim]:
        """Get all active claims."""
        return [c for c in self.claims.values() if c.status == GroundedClaimStatus.ACTIVE]

    def blocked_claims(self) -> list[GroundedClaim]:
        """Get all blocked claims."""
        return [c for c in self.claims.values() if c.status == GroundedClaimStatus.BLOCKED]

    def retracted_claims(self) -> list[GroundedClaim]:
        """Get all retracted claims."""
        return [c for c in self.claims.values() if c.status == GroundedClaimStatus.RETRACTED]

    def ungrounded_claims(self) -> list[GroundedClaim]:
        """Get all active ungrounded claims."""
        return [c for c in self.active_claims() if not c.is_grounded]

    def dangerous_claims(self) -> list[GroundedClaim]:
        """Get all dangerous claims (high confidence + ungrounded)."""
        return [c for c in self.active_claims() if c.is_dangerous]

    def claims_by_provenance(self, provenance: Provenance) -> list[GroundedClaim]:
        """Get all active claims with a specific provenance."""
        return [c for c in self.active_claims() if c.provenance == provenance]

    def claims_by_agent(self, agent_id: str) -> list[GroundedClaim]:
        """Get all claims from a specific agent."""
        return [c for c in self.claims.values() if c.source_agent_id == agent_id]

    def find_by_content(self, content: str) -> GroundedClaim | None:
        """Find a claim by content (approximate match via hash)."""
        content_hash = hashlib.sha256(content.lower().strip().encode()).hexdigest()[:16]
        for claim in self.claims.values():
            if claim.content_hash == content_hash:
                return claim
        return None

    # =========================================================================
    # Metrics
    # =========================================================================

    def get_metrics(self) -> dict[str, Any]:
        """Get ledger metrics."""
        active = self.active_claims()

        # Provenance distribution
        prov_dist = {}
        for p in Provenance:
            count = len([c for c in active if c.provenance == p])
            prov_dist[p.value] = count

        # Confidence distribution
        high_conf = len([c for c in active if c.confidence >= 0.7])
        med_conf = len([c for c in active if 0.3 <= c.confidence < 0.7])
        low_conf = len([c for c in active if c.confidence < 0.3])

        return {
            "step": self.step,
            "total_claims": len(self.claims),
            "active_claims": len(active),
            "blocked_claims": len(self.blocked_claims()),
            "retracted_claims": len(self.retracted_claims()),
            "ungrounded_claims": len(self.ungrounded_claims()),
            "dangerous_claims": len(self.dangerous_claims()),
            "provenance_distribution": prov_dist,
            "confidence_distribution": {
                "high": high_conf,
                "medium": med_conf,
                "low": low_conf,
            },
            "commit_level_distribution": {
                "hard": len(self.hard_claims()),
                "soft": len(self.soft_claims()),
                "refused": len(self.refused_claims()),
                "unclassified": len([c for c in active if c.commit_level is None]),
            },
            "claims_with_assumptions": len(self.claims_with_assumptions()),
            "total_promotions_attempted": self.total_promotions_attempted,
            "total_promotions_forbidden": self.total_promotions_forbidden,
            "total_retractions": self.total_retractions,
            "forbidden_promotion_rate": (
                self.total_promotions_forbidden / self.total_promotions_attempted
                if self.total_promotions_attempted > 0
                else 0.0
            ),
        }

    def get_provenance_entropy(self) -> float:
        """
        Get provenance entropy (diversity of provenance types).

        A healthy system should shift toward RETRIEVED under factual pressure.
        Low entropy = concentrated in few provenance types.
        """
        import math

        active = self.active_claims()
        if not active:
            return 0.0

        counts: dict[Provenance, int] = {}
        for c in active:
            counts[c.provenance] = counts.get(c.provenance, 0) + 1

        total = len(active)
        entropy = 0.0
        for count in counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)

        return entropy

    # =========================================================================
    # Serialization
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Serialize ledger state."""
        return {
            "step": self.step,
            "claims": {cid: c.to_dict() for cid, c in self.claims.items()},
            "total_claims_created": self.total_claims_created,
            "total_promotions_attempted": self.total_promotions_attempted,
            "total_promotions_forbidden": self.total_promotions_forbidden,
            "total_retractions": self.total_retractions,
            "metrics": self.get_metrics(),
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        import json

        return json.dumps(self.to_dict(), indent=2, default=str)

    @classmethod
    def from_dict(cls, data: dict) -> "EpistemicLedger":
        """Deserialize ledger from dict. Round-trips with to_dict()."""
        ledger = cls()
        ledger.step = data.get("step", 0)
        for cid, cdata in data.get("claims", {}).items():
            ledger.claims[cid] = GroundedClaim.from_dict(cdata)
        # Restore metric counters for round-trip fidelity
        ledger.total_claims_created = data.get(
            "total_claims_created", len(ledger.claims)
        )
        ledger.total_promotions_attempted = data.get("total_promotions_attempted", 0)
        ledger.total_promotions_forbidden = data.get("total_promotions_forbidden", 0)
        ledger.total_retractions = data.get("total_retractions", 0)
        return ledger

    @classmethod
    def from_json(cls, json_str: str) -> "EpistemicLedger":
        """Deserialize ledger from JSON string. Round-trips with to_json()."""
        import json

        return cls.from_dict(json.loads(json_str))
