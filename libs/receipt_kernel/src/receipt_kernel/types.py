"""Core types for receipt_kernel.

All types here are stdlib-only, serializable, and deterministic.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Verdicts
# =============================================================================


class Verdict(enum.Enum):
    """Invariant evaluation outcome.

    No silent downgrade: UNKNOWN/FAIL in required invariants poisons PASS.
    """

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"

    def is_success(self) -> bool:
        return self in (Verdict.PASS, Verdict.WARN)

    def is_failure(self) -> bool:
        return self in (Verdict.FAIL, Verdict.UNKNOWN)


# =============================================================================
# Evidence classes + retention
# =============================================================================


class EvidenceClass(enum.Enum):
    """Classification for evidence blobs (retention axis)."""

    PUBLIC = "public"  # safe-ish, retained longer
    SEALED = "sealed"  # may contain secrets, aggressively expired


class EvidenceStrength(enum.Enum):
    """Epistemic strength of evidence (trust axis, orthogonal to retention).

    Strong: tool outputs, primary sources, structured measurements
    Medium: cached summaries, secondhand extracts
    Weak: model self-report, freeform text with no provenance
    """

    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"


class BlobState(enum.Enum):
    """Lifecycle state for stored blobs."""

    LIVE = "live"  # full blob available
    EXPIRED_HASH_ONLY = "expired_hash_only"  # hash + metadata kept, bytes deleted
    PURGED = "purged"  # hash kept, metadata minimal, bytes gone


@dataclass(frozen=True)
class BlobRef:
    """Reference to a stored evidence blob."""

    ref: str  # blob://sha256:<hex>
    sha256: str
    content_type: str
    bytes_len: int
    evidence_class: str = "public"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "sha256": self.sha256,
            "content_type": self.content_type,
            "bytes_len": self.bytes_len,
            "evidence_class": self.evidence_class,
        }


@dataclass
class RetentionPolicy:
    """Retention configuration for evidence blobs.

    Policy-as-data, not code. Governs how long blobs are kept and when
    they transition from LIVE to EXPIRED_HASH_ONLY to PURGED.
    """

    # How long to keep LIVE blobs (seconds). -1 = forever.
    public_ttl_seconds: int = 30 * 24 * 3600  # 30 days default
    sealed_ttl_seconds: int = 7 * 24 * 3600  # 7 days default

    # How long to keep hash+metadata after blob expiry. -1 = forever.
    hash_retention_seconds: int = -1  # keep hashes forever by default

    # Event envelopes are never deleted (only blobs have TTL)
    # This is intentional: you can always prove what happened, even if
    # you can't retrieve the raw evidence.

    def ttl_for_class(self, evidence_class: EvidenceClass) -> int:
        if evidence_class == EvidenceClass.SEALED:
            return self.sealed_ttl_seconds
        return self.public_ttl_seconds

    def to_dict(self) -> dict[str, Any]:
        return {
            "public_ttl_seconds": self.public_ttl_seconds,
            "sealed_ttl_seconds": self.sealed_ttl_seconds,
            "hash_retention_seconds": self.hash_retention_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetentionPolicy:
        return cls(
            public_ttl_seconds=data.get("public_ttl_seconds", 30 * 24 * 3600),
            sealed_ttl_seconds=data.get("sealed_ttl_seconds", 7 * 24 * 3600),
            hash_retention_seconds=data.get("hash_retention_seconds", -1),
        )


# =============================================================================
# Invariant results
# =============================================================================


@dataclass(frozen=True)
class Reason:
    """A single reason contributing to an invariant verdict."""

    code: str  # machine-readable code, e.g. "MISSING_KEY"
    msg: str  # human-readable message
    pointers: tuple[str, ...] = ()  # references to events/blobs

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "msg": self.msg,
            "pointers": list(self.pointers),
        }


@dataclass
class InvariantResult:
    """Result of evaluating a single invariant."""

    invariant_id: str
    verdict: Verdict
    reasons: list[Reason] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariant_id": self.invariant_id,
            "verdict": self.verdict.value,
            "reasons": [r.to_dict() for r in self.reasons],
            "evidence_refs": list(self.evidence_refs),
            "meta": dict(self.meta),
        }


# =============================================================================
# Event types
# =============================================================================

EVENT_SCHEMA_VERSION = 1

VALID_EVENT_TYPES = frozenset({
    "RUN_START",
    "STAGE_ADVANCE",
    "EVIDENCE_PUT",
    "EVALUATION",
    "DECISION",
    "REMEDIATION",
    "RUN_FINALIZE",
    "BLOB_EXPIRE",
})
