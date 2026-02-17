# SPDX-License-Identifier: Apache-2.0
"""
Scope Governor — Locality-first policy with escalation receipts.

Constrains *where* agents can act, not just *what* they do.
Epistemic locality for claims, operational locality for actions.
Locality shouldn't prevent global — it should make global *earned*.

Key invariants:
  1. Absence is restrictive, not permissive — missing axis = locked.
  2. Time axis uses real timestamps (ISO 8601 UTC), not string labels.
  3. One axis, one rung per escalation — widen exactly one axis per call.
  4. Tool contracts bind scope — governor derives+validates requested scope.
  5. Browser never carries authority — grants stored server-side.
  6. Write/execute grants log every usage — read grants reusable within TTL.
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SCOPE_SCHEMA_VERSION = 1

# =============================================================================
# Enums
# =============================================================================


class ScopeAxis(str, Enum):
    TENANT = "tenant"
    ENVIRONMENT = "environment"
    REGION = "region"
    SERVICE = "service"
    RESOURCE = "resource"
    TIME_WINDOW = "time_window"


class AccessMode(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class EscalationVerdict(str, Enum):
    ALLOW = "allow"
    ALLOW_READONLY = "allow_readonly"
    DENY = "deny"


# =============================================================================
# Expanding rings ladder
# =============================================================================

# Most specific → least specific.  Escalation = widen one concrete axis → "*".
SPATIAL_LADDER: list[str] = ["resource", "service", "region", "environment", "tenant"]

# Time ladder labels → minutes (UI guidance only, enforcement via TimeRange).
TEMPORAL_LADDER_MINUTES: dict[str, int] = {
    "5m": 5,
    "1h": 60,
    "24h": 1440,
    "7d": 10080,
    "30d": 43200,
    "all": 525600,
}

# =============================================================================
# TimeRange — real timestamps for the time axis
# =============================================================================


@dataclass(frozen=True)
class TimeRange:
    """Real timestamps for temporal containment.

    Uses ISO 8601 UTC with 'Z' suffix.  Enforcement via interval inclusion,
    not string comparison.
    """

    start: str  # ISO 8601 UTC (Z suffix)
    end: str    # ISO 8601 UTC (Z suffix)

    def __post_init__(self) -> None:
        # Validate parseable
        _parse_iso(self.start)
        _parse_iso(self.end)

    def contains(self, other: "TimeRange") -> bool:
        """True if other's interval is entirely within this interval."""
        s_self = _parse_iso(self.start)
        e_self = _parse_iso(self.end)
        s_other = _parse_iso(other.start)
        e_other = _parse_iso(other.end)
        return s_self <= s_other and e_other <= e_self

    def duration_minutes(self) -> float:
        s = _parse_iso(self.start)
        e = _parse_iso(self.end)
        return (e - s).total_seconds() / 60.0

    def to_scope_value(self) -> str:
        """Canonical scope axis value: 'start/end'."""
        return f"{self.start}/{self.end}"

    @classmethod
    def from_scope_value(cls, value: str) -> "TimeRange":
        parts = value.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid time_window scope value: {value!r}")
        return cls(start=parts[0], end=parts[1])

    @classmethod
    def last_minutes(cls, minutes: int) -> "TimeRange":
        """Convenience: time range ending now, spanning `minutes` back."""
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        start = now - timedelta(minutes=minutes)
        return cls(
            start=start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )


def _parse_iso(s: str) -> datetime:
    """Parse ISO 8601 UTC string.  Accepts 'Z' or '+00:00'."""
    s = s.replace("Z", "+00:00")
    return datetime.fromisoformat(s)


# =============================================================================
# Scope — canonical, hashable, absence-restrictive
# =============================================================================


@dataclass(frozen=True)
class Scope:
    """An immutable scope definition.

    Axes are stored as sorted (axis, value) tuples for deterministic hashing.

    CRITICAL: absent axis = NOT ALLOWED.  Wildcard must be explicit "*".
    Empty scope = nothing allowed.
    """

    axes: tuple[tuple[str, str], ...] = ()

    def scope_hash(self) -> str:
        """Content-addressed hash of this scope."""
        return compute_scope_hash(self)

    def contains(self, other: "Scope") -> bool:
        """True if this scope contains (permits) the other scope.

        Absence-restrictive: any axis in `other` but not in `self` → False.
        Time window uses interval-inclusion, not string compare.
        """
        return check_scope_containment(self, other)

    def widen(self, axis: str, new_value: str) -> "Scope":
        """Return a new Scope with one axis changed."""
        d = self.axes_dict()
        d[axis] = new_value
        return Scope.from_dict(d)

    def axes_dict(self) -> dict[str, str]:
        return dict(self.axes)

    def get(self, axis: str) -> str | None:
        """Return axis value, or None if absent (= locked)."""
        d = self.axes_dict()
        return d.get(axis)

    @classmethod
    def from_dict(cls, d: dict[str, str]) -> "Scope":
        return cls(axes=tuple(sorted(d.items())))

    def to_dict(self) -> dict[str, str]:
        return dict(self.axes)

    def scope_level(self, ladder: list[str] | None = None) -> str:
        """Compute the locality level: most-specific axis still pinned.

        Returns the name of the most-specific axis (highest index in ladder)
        that has a concrete (non-wildcard) value.  If all axes are wildcard
        or absent, returns "global".  If no axes match the ladder, returns
        "custom".

        The 'level' represents how local this scope is — the higher up the
        ladder the pinned axis, the more local the scope.
        """
        if ladder is None:
            ladder = SPATIAL_LADDER
        d = self.axes_dict()
        # Walk from most specific (index 0) to least specific
        most_specific_pinned: str | None = None
        for axis in ladder:
            val = d.get(axis)
            if val is not None and val != "*":
                most_specific_pinned = axis
                break  # first non-wildcard from the specific end = our level
        if most_specific_pinned is not None:
            return most_specific_pinned
        # Check if we have any axes at all from the ladder
        has_ladder_axes = any(d.get(a) is not None for a in ladder)
        if has_ladder_axes:
            return "global"  # all ladder axes are wildcard
        return "custom"


# =============================================================================
# ToolScopeContract — per-tool scope declaration (binding)
# =============================================================================


@dataclass(frozen=True)
class ToolScopeContract:
    """Declares what scope axes a tool requires and may touch.

    Governor rejects requests on axes the tool shouldn't be expressing.
    No axis smuggling.
    """

    tool_id: str
    required_axes: list[str]         # MUST be present in scope
    allowed_axes: list[str]          # MAY be present
    max_default_scope: dict[str, str]  # max scope without escalation
    mutability: AccessMode
    description: str = ""

    def all_permitted_axes(self) -> set[str]:
        return set(self.required_axes) | set(self.allowed_axes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "required_axes": list(self.required_axes),
            "allowed_axes": list(self.allowed_axes),
            "max_default_scope": dict(self.max_default_scope),
            "mutability": self.mutability.value,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ToolScopeContract":
        return cls(
            tool_id=d["tool_id"],
            required_axes=d["required_axes"],
            allowed_axes=d["allowed_axes"],
            max_default_scope=d["max_default_scope"],
            mutability=AccessMode(d["mutability"]),
            description=d.get("description", ""),
        )


# =============================================================================
# ScopeGrant — capability token (server-side authoritative)
# =============================================================================


@dataclass
class ScopeGrant:
    """A server-side grant expanding scope beyond the run default.

    Bound to a run, optionally restricted to specific tools, with TTL.
    Write/execute grants track usage count.
    """

    grant_id: str
    run_id: str
    scope: Scope
    tool_allowlist: list[str] | None  # None = all tools
    access_mode: AccessMode
    expires_at: str     # ISO 8601 UTC
    minted_at: str      # ISO 8601 UTC
    reason: str
    evidence_refs: list[str]
    axis_widened: str    # exactly one axis per grant
    revoked: bool = False
    revoked_at: str | None = None
    use_count: int = 0

    def is_expired(self) -> bool:
        now = datetime.now(timezone.utc)
        return _parse_iso(self.expires_at) <= now

    def is_active(self) -> bool:
        return not self.is_expired() and not self.revoked

    def covers_tool(self, tool_id: str) -> bool:
        if self.tool_allowlist is None:
            return True
        return tool_id in self.tool_allowlist

    def covers_scope(self, requested: Scope) -> bool:
        return self.scope.contains(requested)

    def record_use(self) -> None:
        self.use_count += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "run_id": self.run_id,
            "scope": self.scope.to_dict(),
            "tool_allowlist": self.tool_allowlist,
            "access_mode": self.access_mode.value,
            "expires_at": self.expires_at,
            "minted_at": self.minted_at,
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "axis_widened": self.axis_widened,
            "revoked": self.revoked,
            "revoked_at": self.revoked_at,
            "use_count": self.use_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScopeGrant":
        return cls(
            grant_id=d["grant_id"],
            run_id=d["run_id"],
            scope=Scope.from_dict(d["scope"]),
            tool_allowlist=d.get("tool_allowlist"),
            access_mode=AccessMode(d["access_mode"]),
            expires_at=d["expires_at"],
            minted_at=d["minted_at"],
            reason=d["reason"],
            evidence_refs=d.get("evidence_refs", []),
            axis_widened=d["axis_widened"],
            revoked=d.get("revoked", False),
            revoked_at=d.get("revoked_at"),
            use_count=d.get("use_count", 0),
        )


# =============================================================================
# EscalationRequest / EscalationResult
# =============================================================================


@dataclass(frozen=True)
class EscalationRequest:
    """Request to widen scope on exactly one axis.

    Validated: to_scope must differ from from_scope on EXACTLY ONE axis.
    """

    from_scope: Scope
    to_scope: Scope
    reason: str
    evidence_refs: list[str]
    tool_id: str | None = None
    requested_mode: AccessMode = AccessMode.READ
    ttl_minutes: int = 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_scope": self.from_scope.to_dict(),
            "to_scope": self.to_scope.to_dict(),
            "reason": self.reason,
            "evidence_refs": list(self.evidence_refs),
            "tool_id": self.tool_id,
            "requested_mode": self.requested_mode.value,
            "ttl_minutes": self.ttl_minutes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EscalationRequest":
        return cls(
            from_scope=Scope.from_dict(d["from_scope"]),
            to_scope=Scope.from_dict(d["to_scope"]),
            reason=d["reason"],
            evidence_refs=d.get("evidence_refs", []),
            tool_id=d.get("tool_id"),
            requested_mode=AccessMode(d.get("requested_mode", "read")),
            ttl_minutes=d.get("ttl_minutes", 60),
        )


@dataclass
class EscalationResult:
    verdict: EscalationVerdict
    grant: ScopeGrant | None
    reason: str
    axis_widened: str | None
    bridging_satisfied: bool
    receipt_id: str | None = None
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "grant": self.grant.to_dict() if self.grant else None,
            "reason": self.reason,
            "axis_widened": self.axis_widened,
            "bridging_satisfied": self.bridging_satisfied,
            "receipt_id": self.receipt_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EscalationResult":
        return cls(
            verdict=EscalationVerdict(d["verdict"]),
            grant=ScopeGrant.from_dict(d["grant"]) if d.get("grant") else None,
            reason=d["reason"],
            axis_widened=d.get("axis_widened"),
            bridging_satisfied=d.get("bridging_satisfied", False),
            receipt_id=d.get("receipt_id"),
            timestamp=d.get("timestamp", ""),
        )


# =============================================================================
# BridgingRequirement
# =============================================================================


@dataclass(frozen=True)
class BridgingRequirement:
    """Evidence threshold for widening from one level to the next."""

    from_level: str
    to_level: str
    axis: str
    min_evidence_refs: int = 1
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_level": self.from_level,
            "to_level": self.to_level,
            "axis": self.axis,
            "min_evidence_refs": self.min_evidence_refs,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BridgingRequirement":
        return cls(
            from_level=d["from_level"],
            to_level=d["to_level"],
            axis=d["axis"],
            min_evidence_refs=d.get("min_evidence_refs", 1),
            description=d.get("description", ""),
        )


DEFAULT_BRIDGING: list[BridgingRequirement] = [
    BridgingRequirement(
        "resource", "service", "resource", 1,
        "Show evidence beyond single resource",
    ),
    BridgingRequirement(
        "service", "region", "service", 1,
        "Show cross-service evidence",
    ),
    BridgingRequirement(
        "region", "environment", "region", 2,
        "Show cross-region evidence",
    ),
    BridgingRequirement(
        "environment", "tenant", "environment", 2,
        "Show cross-environment evidence",
    ),
]


# =============================================================================
# GrantUsage — audit log entry for write/execute
# =============================================================================


@dataclass(frozen=True)
class GrantUsage:
    """Audit record: a write/execute grant was exercised."""

    grant_id: str
    tool_id: str
    scope_hash: str
    access_mode: str
    used_at: str  # ISO 8601 UTC

    def to_dict(self) -> dict[str, Any]:
        return {
            "grant_id": self.grant_id,
            "tool_id": self.tool_id,
            "scope_hash": self.scope_hash,
            "access_mode": self.access_mode,
            "used_at": self.used_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GrantUsage":
        return cls(
            grant_id=d["grant_id"],
            tool_id=d["tool_id"],
            scope_hash=d["scope_hash"],
            access_mode=d["access_mode"],
            used_at=d["used_at"],
        )


# =============================================================================
# Pure functions
# =============================================================================


def _canonical_json(obj: dict[str, Any]) -> bytes:
    """Deterministic JSON for hashing.  Same convention as gate_receipt."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def compute_scope_hash(scope: Scope) -> str:
    """SHA-256 of canonical JSON of sorted axes."""
    return hashlib.sha256(_canonical_json(dict(scope.axes))).hexdigest()


def check_scope_containment(container: Scope, contained: Scope) -> bool:
    """True if container permits everything in contained.

    Absence-restrictive: axis in contained but not in container → False.
    Time window axis uses interval-inclusion.
    """
    c_dict = container.axes_dict()
    d_dict = contained.axes_dict()

    for axis, d_val in d_dict.items():
        c_val = c_dict.get(axis)
        if c_val is None:
            # Axis absent in container = locked = DENIED
            return False
        if c_val == "*":
            # Wildcard explicitly allows any value
            continue
        # Special handling for time_window: interval inclusion
        if axis == ScopeAxis.TIME_WINDOW.value:
            try:
                c_range = TimeRange.from_scope_value(c_val)
                d_range = TimeRange.from_scope_value(d_val)
                if not c_range.contains(d_range):
                    return False
            except (ValueError, IndexError):
                # Malformed time — fall back to exact match
                if c_val != d_val:
                    return False
        elif c_val != d_val:
            return False
    return True


def check_time_containment(container: TimeRange, contained: TimeRange) -> bool:
    """True if contained's interval is entirely within container's."""
    return container.contains(contained)


def check_tool_scope(
    tool: ToolScopeContract,
    requested_scope: Scope,
    run_scope: Scope,
    active_grants: list[ScopeGrant],
) -> tuple[bool, str | None]:
    """Check if a tool's requested scope is permitted.

    1. Reject if requested axes not in (required ∪ allowed) — axis smuggling
    2. Reject if required axes missing from requested
    3. Check: requested ⊆ run_scope (containment)
    4. If not, check if any active grant covers the gap

    Returns (allowed, denial_reason).
    """
    req_dict = requested_scope.axes_dict()
    permitted = tool.all_permitted_axes()

    # 1. Axis smuggling check
    for axis in req_dict:
        if axis not in permitted:
            return False, (
                f"Axis smuggling: tool '{tool.tool_id}' does not declare "
                f"axis '{axis}' (permitted: {sorted(permitted)})"
            )

    # 2. Required axes present
    for axis in tool.required_axes:
        if axis not in req_dict:
            return False, (
                f"Required axis '{axis}' missing for tool '{tool.tool_id}'"
            )

    # 3. Containment within run scope
    if run_scope.contains(requested_scope):
        return True, None

    # 4. Check active grants
    for grant in active_grants:
        if not grant.is_active():
            continue
        if not grant.covers_tool(tool.tool_id):
            continue
        if grant.covers_scope(requested_scope):
            return True, None

    return False, (
        f"Scope exceeds run scope and no active grant covers it "
        f"(tool='{tool.tool_id}', Mulder prevention: earn your global)"
    )


def validate_escalation_shape(
    request: EscalationRequest,
    ladder: list[str] | None = None,
) -> str | None:
    """Validate that an escalation request widens exactly one axis by one rung.

    Returns error string or None if valid.

    Escalation = widening one concrete axis to "*" (or widening time window).
    The request must change exactly one axis.
    """
    if ladder is None:
        ladder = SPATIAL_LADDER

    from_dict = request.from_scope.axes_dict()
    to_dict = request.to_scope.axes_dict()

    # Collect all axes mentioned in either scope
    all_axes = set(from_dict.keys()) | set(to_dict.keys())

    changed_axes: list[str] = []
    for axis in all_axes:
        f_val = from_dict.get(axis)
        t_val = to_dict.get(axis)
        if f_val != t_val:
            changed_axes.append(axis)

    if len(changed_axes) == 0:
        return "No axes changed — escalation must widen exactly one axis"

    if len(changed_axes) > 1:
        return (
            f"Multi-axis escalation denied: {sorted(changed_axes)} changed. "
            f"Split this into separate escalations (one axis per request)"
        )

    axis = changed_axes[0]
    f_val = from_dict.get(axis)
    t_val = to_dict.get(axis)

    # Introducing a new axis (absent → value) — this is widening (adding scope)
    if f_val is None and t_val is not None:
        return None  # OK — axis introduction

    # Removing an axis (value → absent) — this is narrowing, not escalation
    if f_val is not None and t_val is None:
        return f"Axis '{axis}' removed — that's narrowing, not escalation"

    # Time window: check that new window is wider
    if axis == ScopeAxis.TIME_WINDOW.value:
        try:
            f_range = TimeRange.from_scope_value(f_val)
            t_range = TimeRange.from_scope_value(t_val)
            if t_range.duration_minutes() <= f_range.duration_minutes():
                return (
                    f"Time window not widened: "
                    f"{f_range.duration_minutes():.0f}m → "
                    f"{t_range.duration_minutes():.0f}m"
                )
        except (ValueError, IndexError):
            pass  # Non-parseable time — allow through, containment will catch
        return None

    # Spatial axis: must be widening (concrete → "*")
    if f_val == "*":
        return f"Axis '{axis}' already wildcard — cannot widen further"

    # Widening must go to "*" — concrete → different concrete is pivoting
    if t_val != "*":
        return (
            f"Axis '{axis}': escalation should widen to '*', "
            f"not pivot from '{f_val}' to '{t_val}'"
        )

    return None  # Valid: concrete → "*"


def find_bridging_requirement(
    from_scope: Scope,
    to_scope: Scope,
    requirements: list[BridgingRequirement],
    ladder: list[str] | None = None,
) -> BridgingRequirement | None:
    """Find the bridging requirement for this escalation.

    Uses scope_level() to determine current and target levels.
    """
    if ladder is None:
        ladder = SPATIAL_LADDER

    from_level = from_scope.scope_level(ladder)
    to_level = to_scope.scope_level(ladder)

    for req in requirements:
        if req.from_level == from_level and req.to_level == to_level:
            return req

    return None


def compute_scope_distance(
    from_value: str, to_value: str, ladder: list[str],
) -> int:
    """Rungs between two positions on the ladder.

    Returns -1 if either value is not on the ladder.
    """
    if from_value not in ladder or to_value not in ladder:
        return -1
    return abs(ladder.index(to_value) - ladder.index(from_value))


def evaluate_escalation(
    request: EscalationRequest,
    bridging_requirements: list[BridgingRequirement] | None = None,
    ladder: list[str] | None = None,
    run_id: str = "",
) -> EscalationResult:
    """Evaluate an escalation request.

    1. Validate shape (one axis, one rung)
    2. Find bridging requirement
    3. Check evidence_refs count >= requirement
    4. Mint grant on ALLOW, downgrade to ALLOW_READONLY for
       write/execute with marginal evidence
    """
    if bridging_requirements is None:
        bridging_requirements = DEFAULT_BRIDGING
    if ladder is None:
        ladder = SPATIAL_LADDER

    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    # 1. Validate shape
    shape_err = validate_escalation_shape(request, ladder)
    if shape_err:
        return EscalationResult(
            verdict=EscalationVerdict.DENY,
            grant=None,
            reason=shape_err,
            axis_widened=None,
            bridging_satisfied=False,
            timestamp=ts,
        )

    # Determine which axis changed
    from_dict = request.from_scope.axes_dict()
    to_dict = request.to_scope.axes_dict()
    axis_widened = None
    for axis in set(from_dict.keys()) | set(to_dict.keys()):
        if from_dict.get(axis) != to_dict.get(axis):
            axis_widened = axis
            break

    # 2. Find bridging requirement
    bridging = find_bridging_requirement(
        request.from_scope, request.to_scope, bridging_requirements, ladder,
    )

    # 3. Check evidence
    evidence_count = len(request.evidence_refs)
    bridging_satisfied = True

    if bridging is not None:
        if evidence_count < bridging.min_evidence_refs:
            bridging_satisfied = False
            # Downgrade or deny based on mode
            if request.requested_mode in (AccessMode.WRITE, AccessMode.EXECUTE):
                # Write/execute with insufficient evidence → read-only fallback
                from datetime import timedelta
                expires = now + timedelta(minutes=request.ttl_minutes)
                grant = ScopeGrant(
                    grant_id=str(uuid.uuid4()),
                    run_id=run_id,
                    scope=request.to_scope,
                    tool_allowlist=[request.tool_id] if request.tool_id else None,
                    access_mode=AccessMode.READ,  # downgraded
                    expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    minted_at=ts,
                    reason=(
                        f"Downgraded to read-only: insufficient evidence "
                        f"({evidence_count}/{bridging.min_evidence_refs}) "
                        f"for {request.requested_mode.value} access"
                    ),
                    evidence_refs=list(request.evidence_refs),
                    axis_widened=axis_widened or "",
                )
                return EscalationResult(
                    verdict=EscalationVerdict.ALLOW_READONLY,
                    grant=grant,
                    reason=grant.reason,
                    axis_widened=axis_widened,
                    bridging_satisfied=False,
                    timestamp=ts,
                )
            else:
                # Read with insufficient evidence → deny
                return EscalationResult(
                    verdict=EscalationVerdict.DENY,
                    grant=None,
                    reason=(
                        f"Bridging requirement not met: need "
                        f"{bridging.min_evidence_refs} evidence refs, "
                        f"got {evidence_count} ({bridging.description})"
                    ),
                    axis_widened=axis_widened,
                    bridging_satisfied=False,
                    timestamp=ts,
                )

    # 4. Mint grant
    from datetime import timedelta
    expires = now + timedelta(minutes=request.ttl_minutes)
    grant = ScopeGrant(
        grant_id=str(uuid.uuid4()),
        run_id=run_id,
        scope=request.to_scope,
        tool_allowlist=[request.tool_id] if request.tool_id else None,
        access_mode=request.requested_mode,
        expires_at=expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        minted_at=ts,
        reason=request.reason,
        evidence_refs=list(request.evidence_refs),
        axis_widened=axis_widened or "",
    )

    return EscalationResult(
        verdict=EscalationVerdict.ALLOW,
        grant=grant,
        reason=f"Escalation granted: {axis_widened} widened",
        axis_widened=axis_widened,
        bridging_satisfied=bridging_satisfied,
        timestamp=ts,
    )


# =============================================================================
# ScopeGovernor — stateful coordinator
# =============================================================================


class ScopeGovernor:
    """Stateful scope governor for a single run.

    Manages run scope, tool contracts, escalation grants, and usage logging.
    Persistence via save/load to {gov_dir}/scope.json.
    """

    def __init__(
        self,
        run_scope: Scope | None = None,
        contracts: list[ToolScopeContract] | None = None,
        bridging: list[BridgingRequirement] | None = None,
        ladder: list[str] | None = None,
        run_id: str = "",
    ) -> None:
        self._run_scope = run_scope
        self._contracts: dict[str, ToolScopeContract] = {}
        self._grants: list[ScopeGrant] = []
        self._history: list[EscalationResult] = []
        self._usages: list[GrantUsage] = []
        self._bridging = bridging or list(DEFAULT_BRIDGING)
        self._ladder = ladder or list(SPATIAL_LADDER)
        self._run_id = run_id or str(uuid.uuid4())

        if contracts:
            for c in contracts:
                self._contracts[c.tool_id] = c

    # --- Core ---

    def set_run_scope(self, scope: Scope) -> None:
        self._run_scope = scope

    def get_run_scope(self) -> Scope | None:
        return self._run_scope

    def register_tool(self, contract: ToolScopeContract) -> None:
        self._contracts[contract.tool_id] = contract

    def check_tool(
        self, tool_id: str, requested_scope: Scope,
    ) -> tuple[bool, str | None]:
        """Check if tool's requested scope is permitted."""
        contract = self._contracts.get(tool_id)
        if contract is None:
            return False, f"No contract registered for tool '{tool_id}'"
        if self._run_scope is None:
            return False, "No run scope set"

        return check_tool_scope(
            contract, requested_scope, self._run_scope,
            [g for g in self._grants if g.is_active()],
        )

    def escalate(
        self,
        request: EscalationRequest,
        receipt_system: Any | None = None,
    ) -> EscalationResult:
        """Evaluate and process an escalation request.

        Optionally emits a gate receipt via the receipt_system.
        """
        result = evaluate_escalation(
            request, self._bridging, self._ladder, self._run_id,
        )
        result.timestamp = result.timestamp or datetime.now(
            timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        if result.grant is not None:
            self._grants.append(result.grant)

        # Emit gate receipt
        if receipt_system is not None:
            try:
                receipt = receipt_system.emit(
                    gate="scope_escalation",
                    verdict=result.verdict.value,
                    subject_kind="escalation_request",
                    subject_bytes=_canonical_json(request.to_dict()),
                    evidence_bundle={
                        "evidence_refs": list(request.evidence_refs),
                        "axis_widened": result.axis_widened,
                        "from_scope": request.from_scope.to_dict(),
                        "to_scope": request.to_scope.to_dict(),
                    },
                    gate_config={
                        "bridging": [b.to_dict() for b in self._bridging],
                        "ladder": self._ladder,
                    },
                )
                result.receipt_id = receipt.receipt_id
            except Exception:
                logger.error(
                    "receipt_emit_failed: scope_escalation gate receipt not "
                    "written — audit linkage degraded",
                    exc_info=True,
                )

        self._history.append(result)
        return result

    def record_grant_usage(
        self,
        grant_id: str,
        tool_id: str,
        scope: Scope,
        mode: AccessMode,
    ) -> None:
        """Log usage of a write/execute grant."""
        for grant in self._grants:
            if grant.grant_id == grant_id:
                grant.record_use()
                break

        usage = GrantUsage(
            grant_id=grant_id,
            tool_id=tool_id,
            scope_hash=scope.scope_hash(),
            access_mode=mode.value,
            used_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        self._usages.append(usage)

    def revoke_grant(self, grant_id: str, reason: str = "") -> bool:
        """Revoke a grant by ID.  Returns True if found and revoked."""
        for grant in self._grants:
            if grant.grant_id == grant_id:
                grant.revoked = True
                grant.revoked_at = datetime.now(
                    timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
                return True
        return False

    # --- Query ---

    def get_active_grants(self) -> list[ScopeGrant]:
        return [g for g in self._grants if g.is_active()]

    def get_all_grants(self) -> list[ScopeGrant]:
        return list(self._grants)

    def get_escalation_history(self) -> list[EscalationResult]:
        return list(self._history)

    def get_grant_usages(
        self, grant_id: str | None = None,
    ) -> list[GrantUsage]:
        if grant_id:
            return [u for u in self._usages if u.grant_id == grant_id]
        return list(self._usages)

    def get_contracts(self) -> list[ToolScopeContract]:
        return list(self._contracts.values())

    def get_metrics(self) -> dict[str, Any]:
        active = self.get_active_grants()
        return {
            "run_scope": self._run_scope.to_dict() if self._run_scope else None,
            "run_scope_level": (
                self._run_scope.scope_level(self._ladder)
                if self._run_scope else None
            ),
            "run_id": self._run_id,
            "contracts_count": len(self._contracts),
            "grants_total": len(self._grants),
            "grants_active": len(active),
            "grants_revoked": sum(1 for g in self._grants if g.revoked),
            "grants_expired": sum(
                1 for g in self._grants
                if g.is_expired() and not g.revoked
            ),
            "escalations_total": len(self._history),
            "escalations_allowed": sum(
                1 for h in self._history
                if h.verdict == EscalationVerdict.ALLOW
            ),
            "escalations_denied": sum(
                1 for h in self._history
                if h.verdict == EscalationVerdict.DENY
            ),
            "escalations_readonly": sum(
                1 for h in self._history
                if h.verdict == EscalationVerdict.ALLOW_READONLY
            ),
            "usages_total": len(self._usages),
        }

    # --- Persistence ---

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCOPE_SCHEMA_VERSION,
            "run_scope": self._run_scope.to_dict() if self._run_scope else None,
            "run_id": self._run_id,
            "contracts": {
                k: v.to_dict() for k, v in self._contracts.items()
            },
            "grants": [g.to_dict() for g in self._grants],
            "history": [h.to_dict() for h in self._history],
            "usages": [u.to_dict() for u in self._usages],
            "bridging": [b.to_dict() for b in self._bridging],
            "ladder": self._ladder,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScopeGovernor":
        v = d.get("schema_version", 1)
        if v > SCOPE_SCHEMA_VERSION:
            raise ValueError(
                f"scope.json schema version {v} is newer than supported "
                f"({SCOPE_SCHEMA_VERSION}). Upgrade governor."
            )
        sg = cls(
            run_scope=(
                Scope.from_dict(d["run_scope"]) if d.get("run_scope") else None
            ),
            bridging=[
                BridgingRequirement.from_dict(b) for b in d.get("bridging", [])
            ] or None,
            ladder=d.get("ladder") or None,
            run_id=d.get("run_id", ""),
        )
        for cdata in d.get("contracts", {}).values():
            sg._contracts[cdata["tool_id"]] = ToolScopeContract.from_dict(cdata)
        sg._grants = [ScopeGrant.from_dict(g) for g in d.get("grants", [])]
        sg._history = [
            EscalationResult.from_dict(h) for h in d.get("history", [])
        ]
        sg._usages = [GrantUsage.from_dict(u) for u in d.get("usages", [])]
        return sg

    def save(self, gov_dir: Path) -> None:
        """Atomic write to {gov_dir}/scope.json."""
        path = gov_dir / "scope.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2))
        tmp.rename(path)

    @classmethod
    def load(cls, gov_dir: Path) -> "ScopeGovernor":
        path = gov_dir / "scope.json"
        if not path.exists():
            return cls()
        try:
            data = json.loads(path.read_text())
            return cls.from_dict(data)
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to load scope.json: %s", e)
            return cls()
        except ValueError:
            # Schema version mismatch — don't silently swallow
            raise

    def reset(self) -> None:
        """Reset all state."""
        self._run_scope = None
        self._contracts.clear()
        self._grants.clear()
        self._history.clear()
        self._usages.clear()
        self._run_id = str(uuid.uuid4())
