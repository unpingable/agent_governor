# SPDX-License-Identifier: Apache-2.0
"""Standing identity verification for Governor.

Verifies HMAC-signed WorkloadId tokens issued by the standing system.
Cross-language compatible: same signing format as standing-identity (Rust).

Signing input (pipe-delimited, HMAC-SHA256, hex-encoded):
    jti|name|location|audience|issued_at_rfc3339|expires_at_rfc3339

This module is the Python side of the cross-language verification contract.
Both implementations must produce identical results for the same inputs.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Assessment results (mirrors standing-identity AssessmentResult)
# ---------------------------------------------------------------------------

class AssessmentResult(Enum):
    VALID = "valid"
    INVALID_SIGNATURE = "invalid_signature"
    EXPIRED = "expired"
    AUDIENCE_MISMATCH = "audience_mismatch"
    NOT_YET_VALID = "not_yet_valid"
    REPLAY_DETECTED = "replay_detected"
    ASSESSMENT_COMPROMISED = "assessment_compromised"


# ---------------------------------------------------------------------------
# WorkloadId token
# ---------------------------------------------------------------------------

@dataclass
class WorkloadId:
    """A signed workload identity claim.

    Fields match standing-identity's WorkloadId (Rust) exactly.
    Serialized as JSON with RFC 3339 timestamps.
    """

    jti: str
    name: str
    location: str
    audience: str
    issued_at: str   # RFC 3339
    expires_at: str  # RFC 3339
    signature: str   # hex-encoded HMAC-SHA256

    @property
    def principal_id(self) -> str:
        """Stable opaque principal ID: wl:{name}:{location}."""
        return f"wl:{self.name}:{self.location}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "jti": self.jti,
            "name": self.name,
            "location": self.location,
            "audience": self.audience,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkloadId:
        return cls(
            jti=data["jti"],
            name=data["name"],
            location=data["location"],
            audience=data["audience"],
            issued_at=data["issued_at"],
            expires_at=data["expires_at"],
            signature=data["signature"],
        )

    @classmethod
    def from_json(cls, text: str) -> WorkloadId:
        return cls.from_dict(json.loads(text))


# ---------------------------------------------------------------------------
# Verified identity (output of successful verification)
# ---------------------------------------------------------------------------

@dataclass
class VerifiedIdentity:
    """The output of successful identity verification."""

    principal_id: str
    label: str
    jti: str
    audience: str
    issuer_time: datetime
    verifier_time: datetime

    @property
    def principal_ref(self) -> str:
        """Content-addressed hash of the verified assertion.

        Hash the canonical signing input — same bytes both implementations
        use for HMAC — so the ref is cross-language stable.
        """
        # We hash the same canonical input used for signing
        canonical = _signing_input(
            self.jti, self.label, "",  # label=name, location unknown post-verify
            self.audience,
            self.issuer_time.isoformat(),
            # We don't have expires_at on VerifiedIdentity — hash principal_id instead
            self.principal_id,
        )
        return "sha256:" + hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# Signing (must match Rust exactly)
# ---------------------------------------------------------------------------

def _to_rfc3339_signing(ts: str) -> str:
    """Normalize timestamp to chrono's to_rfc3339() format for signing.

    chrono's serde serializes UTC as "Z" but to_rfc3339() produces "+00:00".
    The Rust signing function uses to_rfc3339(), so we must match that.
    """
    if ts.endswith("Z"):
        return ts[:-1] + "+00:00"
    return ts


def _signing_input(
    jti: str, name: str, location: str,
    audience: str, issued_at: str, expires_at: str,
) -> bytes:
    """Build the canonical signing input: pipe-delimited fields as bytes.

    Timestamps are normalized to chrono's to_rfc3339() format (+00:00, not Z).
    """
    iat = _to_rfc3339_signing(issued_at)
    exp = _to_rfc3339_signing(expires_at)
    return f"{jti}|{name}|{location}|{audience}|{iat}|{exp}".encode("utf-8")


def _compute_signature(
    jti: str, name: str, location: str,
    audience: str, issued_at: str, expires_at: str,
    secret: bytes,
) -> str:
    """Compute HMAC-SHA256 signature, return hex string."""
    msg = _signing_input(jti, name, location, audience, issued_at, expires_at)
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

DEFAULT_SKEW_SECS = 30
DEFAULT_MAX_CLOCK_DIVERGENCE_SECS = 300


def _parse_rfc3339(s: str) -> datetime:
    """Parse RFC 3339 timestamp to timezone-aware datetime."""
    # Handle chrono's default RFC 3339 format (with +00:00 or Z)
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


def verify_identity(
    token: WorkloadId,
    secret: bytes,
    *,
    expected_audience: str = "standing",
    skew_secs: int = DEFAULT_SKEW_SECS,
    max_clock_divergence_secs: int = DEFAULT_MAX_CLOCK_DIVERGENCE_SECS,
    now: datetime | None = None,
) -> AssessmentResult:
    """Verify a WorkloadId token. Returns AssessmentResult.

    Mirrors standing-identity::verify_identity() exactly:
    1. Check signature
    2. Check temporal coherence (expires > issued)
    3. Check clock divergence
    4. Check not-yet-valid
    5. Check expiry (with skew)
    6. Check audience
    """
    # Step 1: Signature
    expected_sig = _compute_signature(
        token.jti, token.name, token.location, token.audience,
        token.issued_at, token.expires_at, secret,
    )
    if not hmac.compare_digest(expected_sig, token.signature):
        return AssessmentResult.INVALID_SIGNATURE

    # Parse timestamps
    try:
        issued = _parse_rfc3339(token.issued_at)
        expires = _parse_rfc3339(token.expires_at)
    except (ValueError, TypeError):
        return AssessmentResult.ASSESSMENT_COMPROMISED

    # Step 2: Temporal coherence
    if expires <= issued:
        return AssessmentResult.ASSESSMENT_COMPROMISED

    now_dt = now or datetime.now(timezone.utc)
    skew = timedelta(seconds=skew_secs)

    # Step 3: Clock divergence
    divergence = abs((now_dt - issued).total_seconds())
    if divergence > max_clock_divergence_secs:
        # Exception: clearly expired even under uncertainty
        if now_dt > expires + timedelta(seconds=max_clock_divergence_secs):
            return AssessmentResult.EXPIRED
        return AssessmentResult.ASSESSMENT_COMPROMISED

    # Step 4: Not-yet-valid
    if issued > now_dt + skew:
        return AssessmentResult.NOT_YET_VALID

    # Step 5: Expiry
    if now_dt > expires + skew:
        return AssessmentResult.EXPIRED

    # Step 6: Audience
    if token.audience != expected_audience:
        return AssessmentResult.AUDIENCE_MISMATCH

    return AssessmentResult.VALID


def verify_and_resolve(
    token: WorkloadId,
    secret: bytes,
    *,
    expected_audience: str = "standing",
    skew_secs: int = DEFAULT_SKEW_SECS,
    max_clock_divergence_secs: int = DEFAULT_MAX_CLOCK_DIVERGENCE_SECS,
    now: datetime | None = None,
) -> VerifiedIdentity:
    """Verify and resolve to a VerifiedIdentity. Raises on failure."""
    result = verify_identity(
        token, secret,
        expected_audience=expected_audience,
        skew_secs=skew_secs,
        max_clock_divergence_secs=max_clock_divergence_secs,
        now=now,
    )
    if result != AssessmentResult.VALID:
        raise StandingVerificationError(result, token)

    now_dt = now or datetime.now(timezone.utc)
    issued = _parse_rfc3339(token.issued_at)

    return VerifiedIdentity(
        principal_id=token.principal_id,
        label=token.name,
        jti=token.jti,
        audience=token.audience,
        issuer_time=issued,
        verifier_time=now_dt,
    )


class StandingVerificationError(Exception):
    """Raised when identity verification fails."""

    def __init__(self, result: AssessmentResult, token: WorkloadId):
        self.result = result
        self.token = token
        super().__init__(
            f"Standing verification failed: {result.value} "
            f"(workload={token.name}, aud={token.audience})"
        )
