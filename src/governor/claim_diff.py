# SPDX-License-Identifier: Apache-2.0
"""
Claim diff: Detect epistemic state changes between turns.

Compares ledger snapshots to catch:
- Confidence drift: gradual confidence increase without evidence addition
- Provenance laundering: ASSUMED -> RETRIEVED without evidence trail
- Evidence erosion: evidence removed without replacement
- Silent retraction: active claims dropped without explicit retraction

Key invariant: Confidence may only increase WITH evidence.
Provenance may only upgrade WITH evidence.
Violations of these rules are structural, not political.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import hashlib


# =============================================================================
# Enums
# =============================================================================


class MutationType(str, Enum):
    """Types of mutations detectable between snapshots."""

    CONFIDENCE_INCREASE = "confidence_increase"
    CONFIDENCE_DECREASE = "confidence_decrease"
    PROVENANCE_UPGRADE = "provenance_upgrade"
    PROVENANCE_DOWNGRADE = "provenance_downgrade"
    EVIDENCE_ADDED = "evidence_added"
    EVIDENCE_REMOVED = "evidence_removed"
    STATUS_CHANGED = "status_changed"
    CONTENT_CHANGED = "content_changed"


class ViolationType(str, Enum):
    """Types of epistemic violations detected across snapshots."""

    CONFIDENCE_DRIFT = "confidence_drift"
    """Confidence increased without evidence addition."""

    PROVENANCE_LAUNDERING = "provenance_laundering"
    """Provenance upgraded without evidence trail."""

    EVIDENCE_EROSION = "evidence_erosion"
    """Evidence removed without replacement."""

    SILENT_RETRACTION = "silent_retraction"
    """Active claim dropped without explicit retraction."""


# Severity scores per mutation type (higher = more suspicious)
MUTATION_SEVERITY: dict[MutationType, float] = {
    MutationType.PROVENANCE_UPGRADE: 1.0,
    MutationType.CONFIDENCE_INCREASE: 0.8,
    MutationType.EVIDENCE_REMOVED: 0.6,
    MutationType.STATUS_CHANGED: 0.4,
    MutationType.CONTENT_CHANGED: 0.3,
    MutationType.CONFIDENCE_DECREASE: 0.2,
    MutationType.PROVENANCE_DOWNGRADE: 0.1,
    MutationType.EVIDENCE_ADDED: 0.0,
}


# =============================================================================
# Snapshot Types
# =============================================================================


@dataclass(frozen=True)
class ClaimSnapshot:
    """
    Frozen snapshot of a single claim's epistemic state at a point in time.

    Captures all fields that matter for diffing: content identity,
    provenance, confidence, evidence, status, and grounding flags.
    """

    claim_id: str
    content: str
    content_hash: str
    provenance: str  # Provenance.value
    confidence: float
    evidence_count: int
    evidence_ref_ids: tuple[str, ...]
    status: str  # GroundedClaimStatus.value
    is_grounded: bool
    is_dangerous: bool
    source_agent_id: str | None = None

    @classmethod
    def from_grounded_claim(cls, claim) -> "ClaimSnapshot":
        """Create snapshot from a GroundedClaim instance."""
        return cls(
            claim_id=claim.claim_id,
            content=claim.content,
            content_hash=claim.content_hash,
            provenance=claim.provenance.value,
            confidence=claim.confidence,
            evidence_count=len(claim.evidence_refs),
            evidence_ref_ids=tuple(e.ref_id for e in claim.evidence_refs),
            status=claim.status.value,
            is_grounded=claim.is_grounded,
            is_dangerous=claim.is_dangerous,
            source_agent_id=claim.source_agent_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "content": self.content,
            "content_hash": self.content_hash,
            "provenance": self.provenance,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "evidence_ref_ids": list(self.evidence_ref_ids),
            "status": self.status,
            "is_grounded": self.is_grounded,
            "is_dangerous": self.is_dangerous,
            "source_agent_id": self.source_agent_id,
        }


@dataclass
class LedgerSnapshot:
    """
    Snapshot of the entire epistemic ledger at a point in time.

    Indexed by both claim_id and content_hash for efficient diffing.
    """

    step: int
    timestamp: datetime
    claims: dict[str, ClaimSnapshot]  # claim_id -> snapshot
    claims_by_hash: dict[str, list[str]]  # content_hash -> [claim_ids]
    total_claims: int
    active_count: int
    dangerous_count: int

    @classmethod
    def from_ledger(cls, ledger) -> "LedgerSnapshot":
        """Create snapshot from an EpistemicLedger instance."""
        claims: dict[str, ClaimSnapshot] = {}
        claims_by_hash: dict[str, list[str]] = {}

        for cid, claim in ledger.claims.items():
            snap = ClaimSnapshot.from_grounded_claim(claim)
            claims[cid] = snap

            if snap.content_hash not in claims_by_hash:
                claims_by_hash[snap.content_hash] = []
            claims_by_hash[snap.content_hash].append(cid)

        active = [c for c in claims.values() if c.status == "active"]
        dangerous = [c for c in active if c.is_dangerous]

        return cls(
            step=ledger.step,
            timestamp=datetime.now(),
            claims=claims,
            claims_by_hash=claims_by_hash,
            total_claims=len(claims),
            active_count=len(active),
            dangerous_count=len(dangerous),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "timestamp": self.timestamp.isoformat(),
            "claims": {cid: s.to_dict() for cid, s in self.claims.items()},
            "total_claims": self.total_claims,
            "active_count": self.active_count,
            "dangerous_count": self.dangerous_count,
        }


# =============================================================================
# Mutation & Violation Events
# =============================================================================


@dataclass
class MutationEvent:
    """A single detected mutation in a claim between snapshots."""

    mutation_type: MutationType
    severity: float
    claim_id: str
    content_hash: str
    field_name: str
    old_value: Any
    new_value: Any
    details: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_type": self.mutation_type.value,
            "severity": self.severity,
            "claim_id": self.claim_id,
            "content_hash": self.content_hash,
            "field_name": self.field_name,
            "old_value": str(self.old_value),
            "new_value": str(self.new_value),
            "details": self.details,
        }


@dataclass
class ClaimPair:
    """A pair of before/after snapshots for the same claim (matched by content_hash)."""

    before: ClaimSnapshot
    after: ClaimSnapshot
    mutations: list[MutationEvent] = field(default_factory=list)

    @property
    def is_preserved(self) -> bool:
        """No mutations detected — claim is identical."""
        return len(self.mutations) == 0

    @property
    def total_severity(self) -> float:
        return sum(m.severity for m in self.mutations)

    @property
    def has_confidence_drift(self) -> bool:
        """Confidence increased without evidence being added."""
        has_increase = any(
            m.mutation_type == MutationType.CONFIDENCE_INCREASE for m in self.mutations
        )
        has_evidence_added = any(
            m.mutation_type == MutationType.EVIDENCE_ADDED for m in self.mutations
        )
        return has_increase and not has_evidence_added

    @property
    def has_provenance_laundering(self) -> bool:
        """Provenance upgraded without evidence being added."""
        has_upgrade = any(
            m.mutation_type == MutationType.PROVENANCE_UPGRADE for m in self.mutations
        )
        has_evidence_added = any(
            m.mutation_type == MutationType.EVIDENCE_ADDED for m in self.mutations
        )
        return has_upgrade and not has_evidence_added


@dataclass
class Violation:
    """An epistemic violation detected between snapshots."""

    violation_type: ViolationType
    severity: float
    claim_id: str
    content_hash: str
    content_summary: str
    details: str
    mutations: list[MutationEvent] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_type": self.violation_type.value,
            "severity": self.severity,
            "claim_id": self.claim_id,
            "content_hash": self.content_hash,
            "content_summary": self.content_summary,
            "details": self.details,
            "mutations": [m.to_dict() for m in self.mutations],
        }


# =============================================================================
# Diff Result
# =============================================================================


@dataclass
class DiffResult:
    """Complete result of diffing two ledger snapshots."""

    before_step: int
    after_step: int
    before_timestamp: datetime
    after_timestamp: datetime

    # Four buckets
    preserved: list[ClaimPair] = field(default_factory=list)
    mutated: list[ClaimPair] = field(default_factory=list)
    added: list[ClaimSnapshot] = field(default_factory=list)
    dropped: list[ClaimSnapshot] = field(default_factory=list)

    # Violations
    violations: list[Violation] = field(default_factory=list)

    @property
    def total_mutations(self) -> int:
        return sum(len(p.mutations) for p in self.mutated)

    @property
    def total_severity(self) -> float:
        return sum(p.total_severity for p in self.mutated)

    @property
    def confidence_drift_count(self) -> int:
        return sum(
            1 for v in self.violations
            if v.violation_type == ViolationType.CONFIDENCE_DRIFT
        )

    @property
    def provenance_laundering_count(self) -> int:
        return sum(
            1 for v in self.violations
            if v.violation_type == ViolationType.PROVENANCE_LAUNDERING
        )

    @property
    def has_violations(self) -> bool:
        return len(self.violations) > 0

    @property
    def summary(self) -> dict[str, Any]:
        return {
            "steps": f"{self.before_step} -> {self.after_step}",
            "preserved": len(self.preserved),
            "mutated": len(self.mutated),
            "added": len(self.added),
            "dropped": len(self.dropped),
            "total_mutations": self.total_mutations,
            "total_severity": round(self.total_severity, 3),
            "violations": len(self.violations),
            "confidence_drift": self.confidence_drift_count,
            "provenance_laundering": self.provenance_laundering_count,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "before_step": self.before_step,
            "after_step": self.after_step,
            "before_timestamp": self.before_timestamp.isoformat(),
            "after_timestamp": self.after_timestamp.isoformat(),
            "summary": self.summary,
            "violations": [v.to_dict() for v in self.violations],
        }


# =============================================================================
# Diff History (multi-turn tracking)
# =============================================================================


@dataclass
class DiffHistory:
    """Tracks diffs across multiple turns for trend analysis."""

    diffs: list[DiffResult] = field(default_factory=list)
    max_history: int = 100

    def add(self, result: DiffResult) -> None:
        """Add a diff result, trimming old entries if needed."""
        self.diffs.append(result)
        if len(self.diffs) > self.max_history:
            self.diffs = self.diffs[-self.max_history:]

    def confidence_drift_trend(self) -> list[int]:
        """Count of confidence drift violations per diff."""
        return [d.confidence_drift_count for d in self.diffs]

    def laundering_trend(self) -> list[int]:
        """Count of provenance laundering violations per diff."""
        return [d.provenance_laundering_count for d in self.diffs]

    def severity_trend(self) -> list[float]:
        """Total severity per diff."""
        return [d.total_severity for d in self.diffs]

    def violation_trend(self) -> list[int]:
        """Total violation count per diff."""
        return [len(d.violations) for d in self.diffs]

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_history": self.max_history,
            "count": len(self.diffs),
            "diffs": [d.to_dict() for d in self.diffs],
        }


# =============================================================================
# Provenance trust ordering (for upgrade/downgrade detection)
# =============================================================================

PROVENANCE_TRUST: dict[str, int] = {
    "observed": 5,
    "retrieved": 4,
    "user_provided": 3,
    "derived": 2,
    "peer_asserted": 1,
    "assumed": 0,
}


def _is_provenance_upgrade(old: str, new: str) -> bool:
    """Check if provenance changed to a more trusted level."""
    return PROVENANCE_TRUST.get(new, -1) > PROVENANCE_TRUST.get(old, -1)


def _is_provenance_downgrade(old: str, new: str) -> bool:
    """Check if provenance changed to a less trusted level."""
    return PROVENANCE_TRUST.get(new, -1) < PROVENANCE_TRUST.get(old, -1)


# =============================================================================
# ClaimDiffer (core diffing engine)
# =============================================================================


@dataclass
class ClaimDiffer:
    """
    Diffs two ledger snapshots to detect epistemic state changes.

    Catches:
    - Confidence drift (increase without evidence)
    - Provenance laundering (upgrade without evidence trail)
    - Evidence erosion (evidence removed without replacement)
    - Silent retraction (active claim dropped without retraction)

    Config:
        confidence_drift_threshold: Minimum confidence delta to flag as drift.
        detect_confidence_drift: Enable/disable confidence drift detection.
        detect_provenance_laundering: Enable/disable laundering detection.
        detect_evidence_erosion: Enable/disable erosion detection.
        detect_silent_retraction: Enable/disable silent retraction detection.
    """

    confidence_drift_threshold: float = 0.05
    detect_confidence_drift: bool = True
    detect_provenance_laundering: bool = True
    detect_evidence_erosion: bool = True
    detect_silent_retraction: bool = True

    def diff(self, before: LedgerSnapshot, after: LedgerSnapshot) -> DiffResult:
        """
        Diff two ledger snapshots.

        Algorithm:
        1. Index both snapshots by content_hash
        2. Set intersection (common), set difference (added/dropped)
        3. Pair claims with matching content_hash
        4. Per pair: detect mutations (confidence, provenance, evidence, status, content)
        5. Classify: preserved (no mutations) vs mutated
        6. Detect violations: confidence drift, provenance laundering, evidence erosion, silent retraction
        """
        result = DiffResult(
            before_step=before.step,
            after_step=after.step,
            before_timestamp=before.timestamp,
            after_timestamp=after.timestamp,
        )

        # Index by content_hash
        before_hashes = set(before.claims_by_hash.keys())
        after_hashes = set(after.claims_by_hash.keys())

        common_hashes = before_hashes & after_hashes
        added_hashes = after_hashes - before_hashes
        dropped_hashes = before_hashes - after_hashes

        # Pair common claims and detect mutations
        for h in common_hashes:
            before_ids = before.claims_by_hash[h]
            after_ids = after.claims_by_hash[h]

            # Greedy pairing: match first before with first after
            paired_count = min(len(before_ids), len(after_ids))

            for i in range(paired_count):
                b_snap = before.claims[before_ids[i]]
                a_snap = after.claims[after_ids[i]]
                pair = self._pair_claims(b_snap, a_snap)

                if pair.is_preserved:
                    result.preserved.append(pair)
                else:
                    result.mutated.append(pair)

            # Excess before claims are dropped
            for i in range(paired_count, len(before_ids)):
                result.dropped.append(before.claims[before_ids[i]])

            # Excess after claims are added
            for i in range(paired_count, len(after_ids)):
                result.added.append(after.claims[after_ids[i]])

        # Added claims (new content_hash in after)
        for h in added_hashes:
            for cid in after.claims_by_hash[h]:
                result.added.append(after.claims[cid])

        # Dropped claims (content_hash gone from after)
        for h in dropped_hashes:
            for cid in before.claims_by_hash[h]:
                result.dropped.append(before.claims[cid])

        # Detect violations
        self._detect_violations(result)

        return result

    def _pair_claims(self, before: ClaimSnapshot, after: ClaimSnapshot) -> ClaimPair:
        """Compare two snapshots and detect mutations."""
        pair = ClaimPair(before=before, after=after)

        # Confidence changes
        delta = after.confidence - before.confidence
        if delta > 0 and abs(delta) >= self.confidence_drift_threshold:
            pair.mutations.append(MutationEvent(
                mutation_type=MutationType.CONFIDENCE_INCREASE,
                severity=MUTATION_SEVERITY[MutationType.CONFIDENCE_INCREASE],
                claim_id=after.claim_id,
                content_hash=after.content_hash,
                field_name="confidence",
                old_value=before.confidence,
                new_value=after.confidence,
                details=f"Confidence increased by {delta:.3f}",
            ))
        elif delta < 0:
            pair.mutations.append(MutationEvent(
                mutation_type=MutationType.CONFIDENCE_DECREASE,
                severity=MUTATION_SEVERITY[MutationType.CONFIDENCE_DECREASE],
                claim_id=after.claim_id,
                content_hash=after.content_hash,
                field_name="confidence",
                old_value=before.confidence,
                new_value=after.confidence,
                details=f"Confidence decreased by {abs(delta):.3f}",
            ))

        # Provenance changes
        if before.provenance != after.provenance:
            if _is_provenance_upgrade(before.provenance, after.provenance):
                pair.mutations.append(MutationEvent(
                    mutation_type=MutationType.PROVENANCE_UPGRADE,
                    severity=MUTATION_SEVERITY[MutationType.PROVENANCE_UPGRADE],
                    claim_id=after.claim_id,
                    content_hash=after.content_hash,
                    field_name="provenance",
                    old_value=before.provenance,
                    new_value=after.provenance,
                    details=f"Provenance upgraded: {before.provenance} -> {after.provenance}",
                ))
            elif _is_provenance_downgrade(before.provenance, after.provenance):
                pair.mutations.append(MutationEvent(
                    mutation_type=MutationType.PROVENANCE_DOWNGRADE,
                    severity=MUTATION_SEVERITY[MutationType.PROVENANCE_DOWNGRADE],
                    claim_id=after.claim_id,
                    content_hash=after.content_hash,
                    field_name="provenance",
                    old_value=before.provenance,
                    new_value=after.provenance,
                    details=f"Provenance downgraded: {before.provenance} -> {after.provenance}",
                ))

        # Evidence changes
        before_ev_set = set(before.evidence_ref_ids)
        after_ev_set = set(after.evidence_ref_ids)

        added_evidence = after_ev_set - before_ev_set
        removed_evidence = before_ev_set - after_ev_set

        if added_evidence:
            pair.mutations.append(MutationEvent(
                mutation_type=MutationType.EVIDENCE_ADDED,
                severity=MUTATION_SEVERITY[MutationType.EVIDENCE_ADDED],
                claim_id=after.claim_id,
                content_hash=after.content_hash,
                field_name="evidence_ref_ids",
                old_value=before.evidence_count,
                new_value=after.evidence_count,
                details=f"Evidence added: {len(added_evidence)} new ref(s)",
            ))

        if removed_evidence:
            pair.mutations.append(MutationEvent(
                mutation_type=MutationType.EVIDENCE_REMOVED,
                severity=MUTATION_SEVERITY[MutationType.EVIDENCE_REMOVED],
                claim_id=after.claim_id,
                content_hash=after.content_hash,
                field_name="evidence_ref_ids",
                old_value=before.evidence_count,
                new_value=after.evidence_count,
                details=f"Evidence removed: {len(removed_evidence)} ref(s)",
            ))

        # Status changes
        if before.status != after.status:
            pair.mutations.append(MutationEvent(
                mutation_type=MutationType.STATUS_CHANGED,
                severity=MUTATION_SEVERITY[MutationType.STATUS_CHANGED],
                claim_id=after.claim_id,
                content_hash=after.content_hash,
                field_name="status",
                old_value=before.status,
                new_value=after.status,
                details=f"Status changed: {before.status} -> {after.status}",
            ))

        # Content changes (claim_id changed but content_hash matched — same semantic content)
        if before.content != after.content:
            pair.mutations.append(MutationEvent(
                mutation_type=MutationType.CONTENT_CHANGED,
                severity=MUTATION_SEVERITY[MutationType.CONTENT_CHANGED],
                claim_id=after.claim_id,
                content_hash=after.content_hash,
                field_name="content",
                old_value=before.content[:50],
                new_value=after.content[:50],
                details="Content text changed (same hash — whitespace/case normalization)",
            ))

        return pair

    def _detect_violations(self, result: DiffResult) -> None:
        """Detect epistemic violations from the diff result."""

        # Confidence drift: increase without evidence addition
        if self.detect_confidence_drift:
            for pair in result.mutated:
                if pair.has_confidence_drift:
                    delta = pair.after.confidence - pair.before.confidence
                    result.violations.append(Violation(
                        violation_type=ViolationType.CONFIDENCE_DRIFT,
                        severity=min(1.0, delta * 2.0),  # Scale: 0.5 delta -> 1.0 severity
                        claim_id=pair.after.claim_id,
                        content_hash=pair.after.content_hash,
                        content_summary=pair.after.content[:80],
                        details=(
                            f"Confidence increased {pair.before.confidence:.2f} -> "
                            f"{pair.after.confidence:.2f} without evidence addition"
                        ),
                        mutations=[
                            m for m in pair.mutations
                            if m.mutation_type == MutationType.CONFIDENCE_INCREASE
                        ],
                    ))

        # Provenance laundering: upgrade without evidence addition
        if self.detect_provenance_laundering:
            for pair in result.mutated:
                if pair.has_provenance_laundering:
                    result.violations.append(Violation(
                        violation_type=ViolationType.PROVENANCE_LAUNDERING,
                        severity=1.0,  # Always maximum severity
                        claim_id=pair.after.claim_id,
                        content_hash=pair.after.content_hash,
                        content_summary=pair.after.content[:80],
                        details=(
                            f"Provenance upgraded {pair.before.provenance} -> "
                            f"{pair.after.provenance} without evidence trail"
                        ),
                        mutations=[
                            m for m in pair.mutations
                            if m.mutation_type == MutationType.PROVENANCE_UPGRADE
                        ],
                    ))

        # Evidence erosion: evidence removed without replacement
        if self.detect_evidence_erosion:
            for pair in result.mutated:
                removed = [
                    m for m in pair.mutations
                    if m.mutation_type == MutationType.EVIDENCE_REMOVED
                ]
                added = [
                    m for m in pair.mutations
                    if m.mutation_type == MutationType.EVIDENCE_ADDED
                ]
                if removed and not added:
                    # Severity proportional to evidence lost
                    lost = pair.before.evidence_count - pair.after.evidence_count
                    severity = min(1.0, lost / max(1, pair.before.evidence_count))
                    result.violations.append(Violation(
                        violation_type=ViolationType.EVIDENCE_EROSION,
                        severity=severity,
                        claim_id=pair.after.claim_id,
                        content_hash=pair.after.content_hash,
                        content_summary=pair.after.content[:80],
                        details=(
                            f"Evidence removed ({pair.before.evidence_count} -> "
                            f"{pair.after.evidence_count}) without replacement"
                        ),
                        mutations=removed,
                    ))

        # Silent retraction: active claim dropped without explicit retraction
        if self.detect_silent_retraction:
            for snap in result.dropped:
                if snap.status == "active":
                    result.violations.append(Violation(
                        violation_type=ViolationType.SILENT_RETRACTION,
                        severity=0.7,
                        claim_id=snap.claim_id,
                        content_hash=snap.content_hash,
                        content_summary=snap.content[:80],
                        details=(
                            f"Active claim '{snap.claim_id}' dropped without "
                            f"explicit retraction (provenance: {snap.provenance})"
                        ),
                    ))


# =============================================================================
# Convenience Functions
# =============================================================================


def snapshot_ledger(ledger) -> LedgerSnapshot:
    """Take a snapshot of an EpistemicLedger."""
    return LedgerSnapshot.from_ledger(ledger)


def diff_snapshots(
    before: LedgerSnapshot,
    after: LedgerSnapshot,
    confidence_drift_threshold: float = 0.05,
) -> DiffResult:
    """Diff two ledger snapshots with default settings."""
    differ = ClaimDiffer(confidence_drift_threshold=confidence_drift_threshold)
    return differ.diff(before, after)


def detect_laundering(
    before: LedgerSnapshot,
    after: LedgerSnapshot,
) -> list[Violation]:
    """Run diff and return only provenance laundering violations."""
    differ = ClaimDiffer(
        detect_confidence_drift=False,
        detect_evidence_erosion=False,
        detect_silent_retraction=False,
    )
    result = differ.diff(before, after)
    return [
        v for v in result.violations
        if v.violation_type == ViolationType.PROVENANCE_LAUNDERING
    ]


def detect_confidence_drift(
    before: LedgerSnapshot,
    after: LedgerSnapshot,
    threshold: float = 0.05,
) -> list[Violation]:
    """Run diff and return only confidence drift violations."""
    differ = ClaimDiffer(
        confidence_drift_threshold=threshold,
        detect_provenance_laundering=False,
        detect_evidence_erosion=False,
        detect_silent_retraction=False,
    )
    result = differ.diff(before, after)
    return [
        v for v in result.violations
        if v.violation_type == ViolationType.CONFIDENCE_DRIFT
    ]
