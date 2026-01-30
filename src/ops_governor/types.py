"""
Core types for the SRE/Ops Governor.

The key abstraction: Policy Packs with Claim Gating.

A claim (e.g., "service_restored") requires proof types to be satisfied.
Proof is mechanical and verifiable - not vibes.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable
from uuid import UUID, uuid4


class ProofType(Enum):
    """Types of proof that can satisfy a claim requirement."""

    HEALTHCHECK = "healthcheck"
    """URL/command executed with successful response."""

    METRIC_THRESHOLD = "metric_threshold"
    """Query result meets threshold (e.g., error_rate < 0.01)."""

    COMMAND_OUTPUT = "command_output"
    """Command executed, output captured and hashed."""

    FILE_EXISTS = "file_exists"
    """File exists at path with expected hash."""

    APPROVAL = "approval"
    """Human approval with identity and timestamp."""

    WAIVER = "waiver"
    """Explicit waiver with approver identity and reason."""

    ROLLBACK_PLAN = "rollback_plan"
    """Documented rollback procedure exists."""

    DIFF_REVIEW = "diff_review"
    """Diff was reviewed (by human or automated check)."""

    SMOKE_TEST = "smoke_test"
    """Post-deploy smoke test passed."""

    DEPENDENCY_CHECK = "dependency_check"
    """Upstream/downstream dependencies verified."""

    TIME_WINDOW = "time_window"
    """Action occurred within allowed time window."""

    PRECONDITION = "precondition"
    """Another claim was already satisfied."""


@dataclass
class ProofRequirement:
    """A single proof requirement for a claim."""

    id: UUID = field(default_factory=uuid4)
    proof_type: ProofType = ProofType.COMMAND_OUTPUT
    description: str = ""

    # Type-specific parameters
    command: str | None = None
    """For COMMAND_OUTPUT, HEALTHCHECK: the command/URL to execute."""

    expected_pattern: str | None = None
    """Regex pattern the output must match."""

    expected_exit_code: int | None = None
    """Expected exit code (default 0)."""

    metric_query: str | None = None
    """For METRIC_THRESHOLD: the query to run."""

    threshold: float | None = None
    """For METRIC_THRESHOLD: the threshold value."""

    threshold_op: str = "lt"
    """Comparison operator: lt, lte, gt, gte, eq."""

    file_path: str | None = None
    """For FILE_EXISTS, ROLLBACK_PLAN: path to check."""

    expected_hash: str | None = None
    """For FILE_EXISTS: expected content hash."""

    approver_role: str | None = None
    """For APPROVAL, WAIVER: required approver role."""

    precondition_claim: str | None = None
    """For PRECONDITION: claim that must be satisfied first."""

    time_window_start: str | None = None
    """For TIME_WINDOW: cron expression or time for window start."""

    time_window_end: str | None = None
    """For TIME_WINDOW: cron expression or time for window end."""

    time_window_duration_minutes: int | None = None
    """For TIME_WINDOW: duration in minutes (for bake time checks)."""

    optional: bool = False
    """If true, this proof is recommended but not required."""

    alternatives: list[str] = field(default_factory=list)
    """IDs of alternative proofs (satisfy any one)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "proof_type": self.proof_type.value,
            "description": self.description,
            "command": self.command,
            "expected_pattern": self.expected_pattern,
            "expected_exit_code": self.expected_exit_code,
            "metric_query": self.metric_query,
            "threshold": self.threshold,
            "threshold_op": self.threshold_op,
            "file_path": self.file_path,
            "expected_hash": self.expected_hash,
            "approver_role": self.approver_role,
            "precondition_claim": self.precondition_claim,
            "time_window_start": self.time_window_start,
            "time_window_end": self.time_window_end,
            "time_window_duration_minutes": self.time_window_duration_minutes,
            "optional": self.optional,
            "alternatives": self.alternatives,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProofRequirement":
        return cls(
            id=UUID(data["id"]) if "id" in data else uuid4(),
            proof_type=ProofType(data["proof_type"]),
            description=data.get("description", ""),
            command=data.get("command"),
            expected_pattern=data.get("expected_pattern"),
            expected_exit_code=data.get("expected_exit_code"),
            metric_query=data.get("metric_query"),
            threshold=data.get("threshold"),
            threshold_op=data.get("threshold_op", "lt"),
            file_path=data.get("file_path"),
            expected_hash=data.get("expected_hash"),
            approver_role=data.get("approver_role"),
            precondition_claim=data.get("precondition_claim"),
            time_window_start=data.get("time_window_start"),
            time_window_end=data.get("time_window_end"),
            time_window_duration_minutes=data.get("time_window_duration_minutes"),
            optional=data.get("optional", False),
            alternatives=data.get("alternatives", []),
        )


@dataclass
class ClaimDefinition:
    """
    A claim that can be made, with its proof requirements.

    Example:
        claim: service_restored
        requires:
          - healthcheck evidence (URL + output hash)
          - error rate below threshold
          - rollback plan present OR waiver
    """

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    """Claim identifier (e.g., 'service_restored', 'deploy_complete')."""

    description: str = ""
    """Human-readable description of what this claim means."""

    requirements: list[ProofRequirement] = field(default_factory=list)
    """Proof requirements that must be satisfied."""

    severity: str = "error"
    """What happens if claim is made without proof: 'error', 'warning', 'info'."""

    tags: list[str] = field(default_factory=list)
    """Tags for categorization (e.g., ['deploy', 'incident'])."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "requirements": [r.to_dict() for r in self.requirements],
            "severity": self.severity,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClaimDefinition":
        return cls(
            id=UUID(data["id"]) if "id" in data else uuid4(),
            name=data["name"],
            description=data.get("description", ""),
            requirements=[ProofRequirement.from_dict(r) for r in data.get("requirements", [])],
            severity=data.get("severity", "error"),
            tags=data.get("tags", []),
        )


@dataclass
class ProofEvidence:
    """
    Evidence that satisfies a proof requirement.

    This is the receipt - the mechanical verification.
    """

    id: UUID = field(default_factory=uuid4)
    requirement_id: UUID | None = None
    """The requirement this evidence satisfies."""

    proof_type: ProofType = ProofType.COMMAND_OUTPUT
    collected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Evidence data
    command_executed: str | None = None
    exit_code: int | None = None
    output: str | None = None
    output_hash: str | None = None

    metric_value: float | None = None
    metric_query_executed: str | None = None

    file_path_checked: str | None = None
    file_hash: str | None = None
    file_exists: bool | None = None

    approver_id: str | None = None
    approver_role: str | None = None
    approval_timestamp: datetime | None = None
    approval_reason: str | None = None

    waiver_reason: str | None = None

    satisfied: bool = False
    """Whether this evidence satisfies the requirement."""

    failure_reason: str | None = None
    """If not satisfied, why."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "requirement_id": str(self.requirement_id) if self.requirement_id else None,
            "proof_type": self.proof_type.value,
            "collected_at": self.collected_at.isoformat(),
            "command_executed": self.command_executed,
            "exit_code": self.exit_code,
            "output": self.output,
            "output_hash": self.output_hash,
            "metric_value": self.metric_value,
            "metric_query_executed": self.metric_query_executed,
            "file_path_checked": self.file_path_checked,
            "file_hash": self.file_hash,
            "file_exists": self.file_exists,
            "approver_id": self.approver_id,
            "approver_role": self.approver_role,
            "approval_timestamp": self.approval_timestamp.isoformat() if self.approval_timestamp else None,
            "approval_reason": self.approval_reason,
            "waiver_reason": self.waiver_reason,
            "satisfied": self.satisfied,
            "failure_reason": self.failure_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProofEvidence":
        return cls(
            id=UUID(data["id"]),
            requirement_id=UUID(data["requirement_id"]) if data.get("requirement_id") else None,
            proof_type=ProofType(data["proof_type"]),
            collected_at=datetime.fromisoformat(data["collected_at"]),
            command_executed=data.get("command_executed"),
            exit_code=data.get("exit_code"),
            output=data.get("output"),
            output_hash=data.get("output_hash"),
            metric_value=data.get("metric_value"),
            metric_query_executed=data.get("metric_query_executed"),
            file_path_checked=data.get("file_path_checked"),
            file_hash=data.get("file_hash"),
            file_exists=data.get("file_exists"),
            approver_id=data.get("approver_id"),
            approver_role=data.get("approver_role"),
            approval_timestamp=datetime.fromisoformat(data["approval_timestamp"]) if data.get("approval_timestamp") else None,
            approval_reason=data.get("approval_reason"),
            waiver_reason=data.get("waiver_reason"),
            satisfied=data.get("satisfied", False),
            failure_reason=data.get("failure_reason"),
        )


@dataclass
class ClaimAttempt:
    """
    An attempt to make a claim with evidence.

    This is the audit record of someone trying to assert something.
    """

    id: UUID = field(default_factory=uuid4)
    claim_name: str = ""
    attempted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    attempted_by: str = ""
    """Identity of who/what made the claim."""

    evidence: list[ProofEvidence] = field(default_factory=list)
    """Evidence provided for the claim."""

    satisfied: bool = False
    """Whether all requirements were satisfied."""

    missing_requirements: list[str] = field(default_factory=list)
    """IDs of requirements that weren't satisfied."""

    policy_pack: str | None = None
    """Which policy pack was used for verification."""

    context: dict[str, Any] = field(default_factory=dict)
    """Additional context (service, environment, incident ID, etc.)."""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "claim_name": self.claim_name,
            "attempted_at": self.attempted_at.isoformat(),
            "attempted_by": self.attempted_by,
            "evidence": [e.to_dict() for e in self.evidence],
            "satisfied": self.satisfied,
            "missing_requirements": self.missing_requirements,
            "policy_pack": self.policy_pack,
            "context": self.context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ClaimAttempt":
        return cls(
            id=UUID(data["id"]),
            claim_name=data["claim_name"],
            attempted_at=datetime.fromisoformat(data["attempted_at"]),
            attempted_by=data["attempted_by"],
            evidence=[ProofEvidence.from_dict(e) for e in data.get("evidence", [])],
            satisfied=data.get("satisfied", False),
            missing_requirements=data.get("missing_requirements", []),
            policy_pack=data.get("policy_pack"),
            context=data.get("context", {}),
        )


@dataclass
class PolicyPack:
    """
    A collection of claim definitions that can be enabled per environment.

    Examples:
        policy:change_mgmt/basic
        policy:incident/strict
        policy:deploy/safe_rollout
        policy:runbook/<service>
    """

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    """Pack identifier (e.g., 'change_mgmt/basic', 'incident/strict')."""

    description: str = ""
    version: str = "1.0.0"

    claims: list[ClaimDefinition] = field(default_factory=list)
    """Claim definitions in this pack."""

    enabled: bool = True
    """Whether this pack is currently active."""

    environments: list[str] = field(default_factory=list)
    """Environments where this pack applies (empty = all)."""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def get_claim(self, name: str) -> ClaimDefinition | None:
        """Get a claim definition by name."""
        for claim in self.claims:
            if claim.name == name:
                return claim
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "claims": [c.to_dict() for c in self.claims],
            "enabled": self.enabled,
            "environments": self.environments,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PolicyPack":
        return cls(
            id=UUID(data["id"]) if "id" in data else uuid4(),
            name=data["name"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            claims=[ClaimDefinition.from_dict(c) for c in data.get("claims", [])],
            enabled=data.get("enabled", True),
            environments=data.get("environments", []),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(timezone.utc),
        )


# ============================================================================
# INCIDENT TYPES
# ============================================================================


class IncidentSeverity(Enum):
    """Incident severity levels."""
    SEV1 = "sev1"  # Critical - all hands
    SEV2 = "sev2"  # Major - immediate response
    SEV3 = "sev3"  # Minor - next business day
    SEV4 = "sev4"  # Low - when convenient


class IncidentStatus(Enum):
    """Incident lifecycle status."""
    DETECTED = "detected"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    IDENTIFIED = "identified"  # Root cause identified
    MITIGATING = "mitigating"
    RESOLVED = "resolved"
    POSTMORTEM = "postmortem"
    CLOSED = "closed"


@dataclass
class IncidentEvent:
    """A single event in an incident timeline."""

    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = ""
    """Type: 'status_change', 'claim', 'escalation', 'action', 'note'."""

    actor: str = ""
    """Who/what triggered this event."""

    description: str = ""

    # For status changes
    old_status: IncidentStatus | None = None
    new_status: IncidentStatus | None = None

    # For claims
    claim_attempt_id: UUID | None = None

    # For escalations
    escalated_to: str | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "actor": self.actor,
            "description": self.description,
            "old_status": self.old_status.value if self.old_status else None,
            "new_status": self.new_status.value if self.new_status else None,
            "claim_attempt_id": str(self.claim_attempt_id) if self.claim_attempt_id else None,
            "escalated_to": self.escalated_to,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IncidentEvent":
        return cls(
            id=UUID(data["id"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            event_type=data["event_type"],
            actor=data["actor"],
            description=data.get("description", ""),
            old_status=IncidentStatus(data["old_status"]) if data.get("old_status") else None,
            new_status=IncidentStatus(data["new_status"]) if data.get("new_status") else None,
            claim_attempt_id=UUID(data["claim_attempt_id"]) if data.get("claim_attempt_id") else None,
            escalated_to=data.get("escalated_to"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class Incident:
    """
    An incident with timeline integrity.

    Events must be temporally consistent. Claims require proof.
    """

    id: UUID = field(default_factory=uuid4)
    title: str = ""
    severity: IncidentSeverity = IncidentSeverity.SEV3
    status: IncidentStatus = IncidentStatus.DETECTED

    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None

    service: str = ""
    """Affected service/system."""

    environment: str = ""
    """Affected environment (prod, staging, etc.)."""

    timeline: list[IncidentEvent] = field(default_factory=list)
    """Ordered list of events."""

    claims: list[ClaimAttempt] = field(default_factory=list)
    """Claims made during incident (service_restored, etc.)."""

    commander: str | None = None
    """Incident commander."""

    participants: list[str] = field(default_factory=list)
    """People involved in response."""

    postmortem_url: str | None = None

    def add_event(
        self,
        event_type: str,
        actor: str,
        description: str,
        **kwargs,
    ) -> IncidentEvent:
        """Add an event to the timeline."""
        event = IncidentEvent(
            event_type=event_type,
            actor=actor,
            description=description,
            **kwargs,
        )
        self.timeline.append(event)
        return event

    def change_status(self, new_status: IncidentStatus, actor: str) -> IncidentEvent:
        """Change incident status with audit trail."""
        old_status = self.status
        self.status = new_status

        if new_status == IncidentStatus.RESOLVED:
            self.resolved_at = datetime.now(timezone.utc)

        return self.add_event(
            event_type="status_change",
            actor=actor,
            description=f"Status changed from {old_status.value} to {new_status.value}",
            old_status=old_status,
            new_status=new_status,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "title": self.title,
            "severity": self.severity.value,
            "status": self.status.value,
            "detected_at": self.detected_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "service": self.service,
            "environment": self.environment,
            "timeline": [e.to_dict() for e in self.timeline],
            "claims": [c.to_dict() for c in self.claims],
            "commander": self.commander,
            "participants": self.participants,
            "postmortem_url": self.postmortem_url,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Incident":
        return cls(
            id=UUID(data["id"]),
            title=data["title"],
            severity=IncidentSeverity(data["severity"]),
            status=IncidentStatus(data["status"]),
            detected_at=datetime.fromisoformat(data["detected_at"]),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            service=data.get("service", ""),
            environment=data.get("environment", ""),
            timeline=[IncidentEvent.from_dict(e) for e in data.get("timeline", [])],
            claims=[ClaimAttempt.from_dict(c) for c in data.get("claims", [])],
            commander=data.get("commander"),
            participants=data.get("participants", []),
            postmortem_url=data.get("postmortem_url"),
        )
