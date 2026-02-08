"""
Deployment Profiles — Authority Classes with Capability Tokens.

User ≠ Operator. Authority classes (PUBLIC/DELEGATED/OPERATOR/AUTONOMOUS) define
trust model, tool access, commit rules, and audit level.
Two-phase commit protocol for irreversible actions.
Capability tokens with scope/verbs/TTL.

Spec: DEPLOYMENT_PROFILES_SPEC (Layer 2.1-B)
Invariant B: Action admissible iff ∃ token k such that k.permits(u).
Invariant E: Irreversible actions require approval (two-phase commit).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class AuthorityClass(str, Enum):
    """Authority classes for deployment contexts."""
    A1_PUBLIC = "A1"       # Untrusted user, untrusted intent
    A2_DELEGATED = "A2"    # Trusted identity, untrusted intent
    A3_OPERATOR = "A3"     # Trusted identity, trusted intent
    A4_AUTONOMOUS = "A4"   # Automated pipeline


class AuditLevel(str, Enum):
    """Audit verbosity level."""
    STANDARD = "standard"
    ENHANCED = "enhanced"
    HEAVY = "heavy"
    FULL = "full"


class ProposalStatus(str, Enum):
    """Status of a two-phase commit proposal."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXPIRED = "expired"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default proposal TTL (how long an approval is valid)
DEFAULT_PROPOSAL_TTL_SECONDS = 300  # 5 minutes

# Default capability token TTL
DEFAULT_TOKEN_TTL_SECONDS = 3600  # 1 hour


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RateLimit:
    """Rate limit for capability tokens."""
    max_calls: int
    window_seconds: int
    calls_made: int = 0
    window_start: float = 0.0

    def check(self) -> bool:
        now = time.time()
        if now - self.window_start > self.window_seconds:
            self.calls_made = 0
            self.window_start = now
        return self.calls_made < self.max_calls

    def consume(self) -> bool:
        if not self.check():
            return False
        self.calls_made += 1
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_calls": self.max_calls,
            "window_seconds": self.window_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RateLimit:
        return cls(
            max_calls=d.get("max_calls", 100),
            window_seconds=d.get("window_seconds", 60),
        )


@dataclass
class CapabilityToken:
    """Capability token binding actions to scope/verbs/TTL."""
    id: str
    scope: set[str]       # Resource patterns (glob)
    verbs: set[str]       # read, write, execute, delete
    ttl_seconds: int
    bound_to: str          # run_id or session_id
    rate_limit: RateLimit = field(default_factory=lambda: RateLimit(100, 60))
    issued_at: str = ""

    def __post_init__(self) -> None:
        if not self.issued_at:
            self.issued_at = datetime.now(timezone.utc).isoformat()

    @property
    def is_expired(self) -> bool:
        issued = datetime.fromisoformat(self.issued_at)
        return datetime.now(timezone.utc) > issued + timedelta(seconds=self.ttl_seconds)

    def permits(self, verb: str, resource: str) -> bool:
        """Check if this token permits the given action."""
        if self.is_expired:
            return False
        if verb not in self.verbs:
            return False
        if not any(fnmatch(resource, pattern) for pattern in self.scope):
            return False
        if not self.rate_limit.check():
            return False
        return True

    def consume(self, verb: str, resource: str) -> bool:
        """Check and consume a rate-limited action."""
        if not self.permits(verb, resource):
            return False
        return self.rate_limit.consume()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scope": sorted(self.scope),
            "verbs": sorted(self.verbs),
            "ttl_seconds": self.ttl_seconds,
            "bound_to": self.bound_to,
            "rate_limit": self.rate_limit.to_dict(),
            "issued_at": self.issued_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CapabilityToken:
        return cls(
            id=d["id"],
            scope=set(d.get("scope", [])),
            verbs=set(d.get("verbs", [])),
            ttl_seconds=d.get("ttl_seconds", DEFAULT_TOKEN_TTL_SECONDS),
            bound_to=d.get("bound_to", ""),
            rate_limit=RateLimit.from_dict(d.get("rate_limit", {})),
            issued_at=d.get("issued_at", ""),
        )


@dataclass
class DeploymentProfile:
    """A deployment profile defining authority constraints."""
    authority_class: AuthorityClass
    tool_whitelist: set[str]
    tool_blacklist: set[str]
    max_budget: dict[str, int]       # {explore, draft, verify}
    requires_two_phase: set[str]     # severity levels needing approval
    evidence_threshold: float
    audit_level: AuditLevel

    def allows_tool(self, tool_id: str) -> bool:
        """Check if a tool is allowed by this profile."""
        if tool_id in self.tool_blacklist:
            return False
        if "*" in self.tool_whitelist:
            return True
        return tool_id in self.tool_whitelist

    def needs_approval(self, severity: str) -> bool:
        """Check if an action at this severity needs two-phase commit."""
        return severity in self.requires_two_phase

    def to_dict(self) -> dict[str, Any]:
        return {
            "authority_class": self.authority_class.value,
            "tool_whitelist": sorted(self.tool_whitelist),
            "tool_blacklist": sorted(self.tool_blacklist),
            "max_budget": self.max_budget,
            "requires_two_phase": sorted(self.requires_two_phase),
            "evidence_threshold": self.evidence_threshold,
            "audit_level": self.audit_level.value,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeploymentProfile:
        return cls(
            authority_class=AuthorityClass(d["authority_class"]),
            tool_whitelist=set(d.get("tool_whitelist", [])),
            tool_blacklist=set(d.get("tool_blacklist", [])),
            max_budget=d.get("max_budget", {"explore": 20, "draft": 15, "verify": 10}),
            requires_two_phase=set(d.get("requires_two_phase", [])),
            evidence_threshold=d.get("evidence_threshold", 0.7),
            audit_level=AuditLevel(d.get("audit_level", "standard")),
        )


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

PUBLIC_PROFILE = DeploymentProfile(
    authority_class=AuthorityClass.A1_PUBLIC,
    tool_whitelist={"web_search", "read_file"},
    tool_blacklist={"write_file", "execute", "send_email", "deploy", "delete"},
    max_budget={"explore": 10, "draft": 5, "verify": 5},
    requires_two_phase={"S2", "S3"},
    evidence_threshold=0.8,
    audit_level=AuditLevel.STANDARD,
)

DELEGATED_PROFILE = DeploymentProfile(
    authority_class=AuthorityClass.A2_DELEGATED,
    tool_whitelist={"web_search", "read_file", "write_file", "execute_sandboxed"},
    tool_blacklist={"send_email", "deploy", "delete"},
    max_budget={"explore": 20, "draft": 15, "verify": 10},
    requires_two_phase={"S3"},
    evidence_threshold=0.7,
    audit_level=AuditLevel.ENHANCED,
)

OPERATOR_PROFILE = DeploymentProfile(
    authority_class=AuthorityClass.A3_OPERATOR,
    tool_whitelist={"*"},
    tool_blacklist=set(),
    max_budget={"explore": 50, "draft": 30, "verify": 20},
    requires_two_phase={"S3"},
    evidence_threshold=0.6,
    audit_level=AuditLevel.HEAVY,
)

AUTONOMOUS_PROFILE = DeploymentProfile(
    authority_class=AuthorityClass.A4_AUTONOMOUS,
    tool_whitelist={"read_file", "write_file", "execute_sandboxed", "web_search"},
    tool_blacklist={"deploy", "delete", "send_email"},
    max_budget={"explore": 30, "draft": 20, "verify": 15},
    requires_two_phase={"S2", "S3"},
    evidence_threshold=0.75,
    audit_level=AuditLevel.FULL,
)

BUILTIN_PROFILES: dict[str, DeploymentProfile] = {
    "public": PUBLIC_PROFILE,
    "delegated": DELEGATED_PROFILE,
    "operator": OPERATOR_PROFILE,
    "autonomous": AUTONOMOUS_PROFILE,
}


# ---------------------------------------------------------------------------
# Two-Phase Commit
# ---------------------------------------------------------------------------

@dataclass
class ActionProposal:
    """A proposed action requiring approval (two-phase commit)."""
    proposal_id: str
    action: str
    args: dict[str, Any]
    severity: str
    predicted_effects: list[str]
    proposed_by: str
    status: ProposalStatus = ProposalStatus.PENDING
    approved_by: str = ""
    ttl_seconds: int = DEFAULT_PROPOSAL_TTL_SECONDS
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if not self.proposal_id:
            self.proposal_id = uuid.uuid4().hex[:12]

    @property
    def proposal_hash(self) -> str:
        content = json.dumps({
            "action": self.action, "args": self.args,
            "severity": self.severity,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    @property
    def is_expired(self) -> bool:
        created = datetime.fromisoformat(self.created_at)
        return datetime.now(timezone.utc) > created + timedelta(seconds=self.ttl_seconds)

    def approve(self, approved_by: str) -> None:
        if self.is_expired:
            self.status = ProposalStatus.EXPIRED
            return
        self.status = ProposalStatus.APPROVED
        self.approved_by = approved_by

    def reject(self) -> None:
        self.status = ProposalStatus.REJECTED

    def execute(self) -> bool:
        """Mark as executed. Returns True if valid (approved + not expired)."""
        if self.status != ProposalStatus.APPROVED:
            return False
        if self.is_expired:
            self.status = ProposalStatus.EXPIRED
            return False
        self.status = ProposalStatus.EXECUTED
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "proposal_hash": self.proposal_hash,
            "action": self.action,
            "args": self.args,
            "severity": self.severity,
            "predicted_effects": self.predicted_effects,
            "proposed_by": self.proposed_by,
            "status": self.status.value,
            "approved_by": self.approved_by,
            "ttl_seconds": self.ttl_seconds,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ActionProposal:
        return cls(
            proposal_id=d.get("proposal_id", ""),
            action=d["action"],
            args=d.get("args", {}),
            severity=d.get("severity", "S1"),
            predicted_effects=d.get("predicted_effects", []),
            proposed_by=d.get("proposed_by", ""),
            status=ProposalStatus(d.get("status", "pending")),
            approved_by=d.get("approved_by", ""),
            ttl_seconds=d.get("ttl_seconds", DEFAULT_PROPOSAL_TTL_SECONDS),
            created_at=d.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def check_tool_access(profile: DeploymentProfile, tool_id: str) -> tuple[bool, str]:
    """Check if a tool is allowed under the profile."""
    if not profile.allows_tool(tool_id):
        if tool_id in profile.tool_blacklist:
            return False, f"tool {tool_id} is blacklisted"
        return False, f"tool {tool_id} not in whitelist"
    return True, "allowed"


def check_invariant_b(token: CapabilityToken, verb: str, resource: str) -> tuple[bool, str]:
    """Check Invariant B: action requires valid capability token."""
    if token.is_expired:
        return False, "token expired"
    if not token.permits(verb, resource):
        return False, f"token does not permit {verb} on {resource}"
    return True, "permitted"


def check_invariant_e(
    profile: DeploymentProfile, severity: str, proposal: ActionProposal | None
) -> tuple[bool, str]:
    """Check Invariant E: irreversible actions need approval."""
    if not profile.needs_approval(severity):
        return True, "no approval needed"
    if proposal is None:
        return False, f"S{severity} action requires two-phase commit approval"
    if proposal.status != ProposalStatus.APPROVED:
        return False, f"proposal status is {proposal.status.value}, not approved"
    if proposal.is_expired:
        return False, "approval has expired"
    return True, "approved"


def issue_token(
    scope: set[str],
    verbs: set[str],
    bound_to: str,
    ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
    rate_limit: RateLimit | None = None,
) -> CapabilityToken:
    """Issue a new capability token."""
    return CapabilityToken(
        id=f"tok_{uuid.uuid4().hex[:8]}",
        scope=scope,
        verbs=verbs,
        ttl_seconds=ttl_seconds,
        bound_to=bound_to,
        rate_limit=rate_limit or RateLimit(100, 60),
    )


def propose_action(
    action: str,
    args: dict[str, Any],
    severity: str,
    predicted_effects: list[str],
    proposed_by: str,
) -> ActionProposal:
    """Create a new action proposal for two-phase commit."""
    return ActionProposal(
        proposal_id="",
        action=action,
        args=args,
        severity=severity,
        predicted_effects=predicted_effects,
        proposed_by=proposed_by,
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class DeploymentStore:
    """Persistent store for deployment profiles and tokens."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.deploy_dir = self.governor_dir / "deployment"

    def _ensure_dirs(self) -> None:
        self.deploy_dir.mkdir(parents=True, exist_ok=True)

    def save_profile(self, name: str, profile: DeploymentProfile) -> Path:
        self._ensure_dirs()
        path = self.deploy_dir / f"profile_{name}.json"
        path.write_text(json.dumps(profile.to_dict(), indent=2) + "\n")
        return path

    def load_profile(self, name: str) -> DeploymentProfile | None:
        # Check built-in first
        if name in BUILTIN_PROFILES:
            return BUILTIN_PROFILES[name]
        path = self.deploy_dir / f"profile_{name}.json"
        if not path.exists():
            return None
        try:
            return DeploymentProfile.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None

    def list_profiles(self) -> list[str]:
        names = list(BUILTIN_PROFILES.keys())
        if self.deploy_dir.exists():
            for f in self.deploy_dir.glob("profile_*.json"):
                name = f.stem.replace("profile_", "")
                if name not in names:
                    names.append(name)
        return sorted(names)

    def save_proposal(self, proposal: ActionProposal) -> Path:
        self._ensure_dirs()
        path = self.deploy_dir / f"proposal_{proposal.proposal_id}.json"
        path.write_text(json.dumps(proposal.to_dict(), indent=2) + "\n")
        return path

    def load_proposal(self, proposal_id: str) -> ActionProposal | None:
        path = self.deploy_dir / f"proposal_{proposal_id}.json"
        if not path.exists():
            return None
        try:
            return ActionProposal.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None

    def list_proposals(self) -> list[str]:
        if not self.deploy_dir.exists():
            return []
        return sorted(
            f.stem.replace("proposal_", "")
            for f in self.deploy_dir.glob("proposal_*.json")
        )


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

def make_deployment_event(
    action: str, details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "deployment",
        "action": action,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
