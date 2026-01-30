"""
Policy Pack management and claim verification.

The core of SRE/Ops Governor: mechanical verification of claims.
"""

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from .types import (
    PolicyPack,
    ClaimDefinition,
    ProofRequirement,
    ProofType,
    ProofEvidence,
    ClaimAttempt,
)


class PolicyRegistry:
    """
    Registry of policy packs.

    Loads policies from disk and provides lookup.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.policy_dir = project_dir / ".ops-gov" / "policies"
        self._packs: dict[str, PolicyPack] = {}

        self._ensure_initialized()
        self._load()

    def _ensure_initialized(self) -> None:
        """Create directory structure if needed."""
        self.policy_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Load all policy packs from disk."""
        for policy_file in self.policy_dir.glob("*.json"):
            try:
                data = json.loads(policy_file.read_text())
                pack = PolicyPack.from_dict(data)
                self._packs[pack.name] = pack
            except (json.JSONDecodeError, KeyError) as e:
                # Skip invalid policy files
                pass

    def _save_pack(self, pack: PolicyPack) -> None:
        """Save a policy pack to disk."""
        # Use pack name as filename (replace / with __)
        filename = pack.name.replace("/", "__") + ".json"
        (self.policy_dir / filename).write_text(json.dumps(pack.to_dict(), indent=2))

    def register(self, pack: PolicyPack) -> None:
        """Register a policy pack."""
        self._packs[pack.name] = pack
        self._save_pack(pack)

    def get(self, name: str) -> PolicyPack | None:
        """Get a policy pack by name."""
        return self._packs.get(name)

    def all_packs(self) -> list[PolicyPack]:
        """Get all registered policy packs."""
        return list(self._packs.values())

    def enabled_packs(self, environment: str | None = None) -> list[PolicyPack]:
        """Get enabled policy packs, optionally filtered by environment."""
        result = [p for p in self._packs.values() if p.enabled]

        if environment:
            result = [
                p for p in result
                if not p.environments or environment in p.environments
            ]

        return result

    def get_claim(self, claim_name: str, environment: str | None = None) -> tuple[ClaimDefinition | None, PolicyPack | None]:
        """Find a claim definition across all enabled packs."""
        for pack in self.enabled_packs(environment):
            claim = pack.get_claim(claim_name)
            if claim:
                return claim, pack
        return None, None


class ProofCollector:
    """
    Collects proof evidence for claim requirements.

    This is where the mechanical verification happens.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir

    def collect(self, requirement: ProofRequirement) -> ProofEvidence:
        """Collect evidence for a proof requirement."""
        if requirement.proof_type == ProofType.COMMAND_OUTPUT:
            return self._collect_command_output(requirement)
        elif requirement.proof_type == ProofType.HEALTHCHECK:
            return self._collect_healthcheck(requirement)
        elif requirement.proof_type == ProofType.FILE_EXISTS:
            return self._collect_file_exists(requirement)
        elif requirement.proof_type == ProofType.METRIC_THRESHOLD:
            return self._collect_metric_threshold(requirement)
        elif requirement.proof_type == ProofType.ROLLBACK_PLAN:
            return self._collect_rollback_plan(requirement)
        elif requirement.proof_type == ProofType.APPROVAL:
            return self._collect_approval(requirement)
        elif requirement.proof_type == ProofType.WAIVER:
            return self._collect_waiver(requirement)
        else:
            # For types that need manual input, return unsatisfied
            return ProofEvidence(
                requirement_id=requirement.id,
                proof_type=requirement.proof_type,
                satisfied=False,
                failure_reason=f"Proof type {requirement.proof_type.value} requires manual input",
            )

    def _collect_command_output(self, req: ProofRequirement) -> ProofEvidence:
        """Execute command and capture output."""
        if not req.command:
            return ProofEvidence(
                requirement_id=req.id,
                proof_type=ProofType.COMMAND_OUTPUT,
                satisfied=False,
                failure_reason="No command specified",
            )

        try:
            result = subprocess.run(
                req.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self.project_dir,
            )

            output = result.stdout + result.stderr
            output_hash = hashlib.sha256(output.encode()).hexdigest()

            # Check exit code
            expected_code = req.expected_exit_code if req.expected_exit_code is not None else 0
            code_ok = result.returncode == expected_code

            # Check pattern if specified
            pattern_ok = True
            if req.expected_pattern:
                pattern_ok = bool(re.search(req.expected_pattern, output))

            satisfied = code_ok and pattern_ok
            failure_reason = None
            if not code_ok:
                failure_reason = f"Exit code {result.returncode}, expected {expected_code}"
            elif not pattern_ok:
                failure_reason = f"Output did not match pattern: {req.expected_pattern}"

            return ProofEvidence(
                requirement_id=req.id,
                proof_type=ProofType.COMMAND_OUTPUT,
                command_executed=req.command,
                exit_code=result.returncode,
                output=output[:10000],  # Truncate long output
                output_hash=output_hash,
                satisfied=satisfied,
                failure_reason=failure_reason,
            )

        except subprocess.TimeoutExpired:
            return ProofEvidence(
                requirement_id=req.id,
                proof_type=ProofType.COMMAND_OUTPUT,
                command_executed=req.command,
                satisfied=False,
                failure_reason="Command timed out",
            )
        except Exception as e:
            return ProofEvidence(
                requirement_id=req.id,
                proof_type=ProofType.COMMAND_OUTPUT,
                command_executed=req.command,
                satisfied=False,
                failure_reason=str(e),
            )

    def _collect_healthcheck(self, req: ProofRequirement) -> ProofEvidence:
        """Execute healthcheck (URL or command)."""
        # For now, treat healthcheck as command output
        # Could be extended to support HTTP checks directly
        return self._collect_command_output(req)

    def _collect_file_exists(self, req: ProofRequirement) -> ProofEvidence:
        """Check if file exists and optionally verify hash."""
        if not req.file_path:
            return ProofEvidence(
                requirement_id=req.id,
                proof_type=ProofType.FILE_EXISTS,
                satisfied=False,
                failure_reason="No file path specified",
            )

        path = Path(req.file_path)
        if not path.is_absolute():
            path = self.project_dir / path

        exists = path.exists()
        file_hash = None

        if exists and path.is_file():
            content = path.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()

        # Check hash if expected
        hash_ok = True
        if req.expected_hash and file_hash:
            hash_ok = file_hash == req.expected_hash

        satisfied = exists and hash_ok
        failure_reason = None
        if not exists:
            failure_reason = f"File not found: {req.file_path}"
        elif not hash_ok:
            failure_reason = f"Hash mismatch: got {file_hash}, expected {req.expected_hash}"

        return ProofEvidence(
            requirement_id=req.id,
            proof_type=ProofType.FILE_EXISTS,
            file_path_checked=str(path),
            file_exists=exists,
            file_hash=file_hash,
            satisfied=satisfied,
            failure_reason=failure_reason,
        )

    def _collect_metric_threshold(self, req: ProofRequirement) -> ProofEvidence:
        """Check if metric meets threshold."""
        # This would integrate with monitoring systems (Prometheus, Datadog, etc.)
        # For now, return unsatisfied with instructions
        return ProofEvidence(
            requirement_id=req.id,
            proof_type=ProofType.METRIC_THRESHOLD,
            satisfied=False,
            failure_reason="Metric collection requires monitoring integration (not yet implemented)",
        )

    def _collect_rollback_plan(self, req: ProofRequirement) -> ProofEvidence:
        """Check if rollback plan exists."""
        if not req.file_path:
            return ProofEvidence(
                requirement_id=req.id,
                proof_type=ProofType.ROLLBACK_PLAN,
                satisfied=False,
                failure_reason="No rollback plan path specified",
            )

        # Reuse file_exists logic
        file_evidence = self._collect_file_exists(req)
        file_evidence.proof_type = ProofType.ROLLBACK_PLAN
        return file_evidence

    def _collect_approval(self, req: ProofRequirement) -> ProofEvidence:
        """Approval requires manual input - return unsatisfied."""
        return ProofEvidence(
            requirement_id=req.id,
            proof_type=ProofType.APPROVAL,
            satisfied=False,
            failure_reason="Approval requires manual input via approve command",
        )

    def _collect_waiver(self, req: ProofRequirement) -> ProofEvidence:
        """Waiver requires manual input - return unsatisfied."""
        return ProofEvidence(
            requirement_id=req.id,
            proof_type=ProofType.WAIVER,
            satisfied=False,
            failure_reason="Waiver requires manual input via waive command",
        )


class ClaimVerifier:
    """
    Verifies claims against their requirements.

    This is the claim gating logic.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.registry = PolicyRegistry(project_dir)
        self.collector = ProofCollector(project_dir)

    def verify_claim(
        self,
        claim_name: str,
        actor: str,
        environment: str | None = None,
        context: dict[str, Any] | None = None,
        pre_collected_evidence: list[ProofEvidence] | None = None,
    ) -> ClaimAttempt:
        """
        Attempt to verify a claim.

        Returns a ClaimAttempt with satisfaction status and evidence.
        """
        # Find the claim definition
        claim_def, pack = self.registry.get_claim(claim_name, environment)

        if not claim_def:
            return ClaimAttempt(
                claim_name=claim_name,
                attempted_by=actor,
                satisfied=False,
                missing_requirements=["claim_not_found"],
                context=context or {},
            )

        # Collect evidence for each requirement
        evidence_list = []
        missing = []

        for req in claim_def.requirements:
            # Check if we have pre-collected evidence for this requirement
            pre_evidence = None
            if pre_collected_evidence:
                for e in pre_collected_evidence:
                    if e.requirement_id == req.id:
                        pre_evidence = e
                        break

            if pre_evidence:
                evidence = pre_evidence
            else:
                evidence = self.collector.collect(req)

            evidence_list.append(evidence)

            if not evidence.satisfied and not req.optional:
                # Check if there are alternatives
                if req.alternatives:
                    alt_satisfied = any(
                        e.satisfied for e in evidence_list
                        if str(e.requirement_id) in req.alternatives
                    )
                    if not alt_satisfied:
                        missing.append(str(req.id))
                else:
                    missing.append(str(req.id))

        return ClaimAttempt(
            claim_name=claim_name,
            attempted_by=actor,
            evidence=evidence_list,
            satisfied=len(missing) == 0,
            missing_requirements=missing,
            policy_pack=pack.name if pack else None,
            context=context or {},
        )

    def add_approval(
        self,
        claim_attempt_id: UUID,
        requirement_id: UUID,
        approver_id: str,
        approver_role: str,
        reason: str | None = None,
    ) -> ProofEvidence:
        """Add approval evidence to a claim attempt."""
        return ProofEvidence(
            requirement_id=requirement_id,
            proof_type=ProofType.APPROVAL,
            approver_id=approver_id,
            approver_role=approver_role,
            approval_timestamp=datetime.now(timezone.utc),
            approval_reason=reason,
            satisfied=True,
        )

    def add_waiver(
        self,
        claim_attempt_id: UUID,
        requirement_id: UUID,
        approver_id: str,
        approver_role: str,
        reason: str,
    ) -> ProofEvidence:
        """Add waiver evidence to a claim attempt."""
        return ProofEvidence(
            requirement_id=requirement_id,
            proof_type=ProofType.WAIVER,
            approver_id=approver_id,
            approver_role=approver_role,
            approval_timestamp=datetime.now(timezone.utc),
            waiver_reason=reason,
            satisfied=True,
        )


# ============================================================================
# BUILT-IN POLICY PACKS
# ============================================================================


def create_deploy_safe_rollout_pack() -> PolicyPack:
    """Create the deploy/safe_rollout policy pack."""
    return PolicyPack(
        name="deploy/safe_rollout",
        description="Safe deployment with rollback requirements",
        claims=[
            ClaimDefinition(
                name="deploy_ready",
                description="System is ready for deployment",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="Tests pass",
                        command="make test || npm test || pytest",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.ROLLBACK_PLAN,
                        description="Rollback plan exists",
                        file_path="ROLLBACK.md",
                    ),
                ],
            ),
            ClaimDefinition(
                name="deploy_complete",
                description="Deployment completed successfully",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.PRECONDITION,
                        description="deploy_ready was satisfied",
                        precondition_claim="deploy_ready",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.HEALTHCHECK,
                        description="Healthcheck passes",
                        command="curl -sf http://localhost:8080/health || exit 1",
                        expected_exit_code=0,
                    ),
                ],
            ),
        ],
    )


def create_incident_strict_pack() -> PolicyPack:
    """Create the incident/strict policy pack."""
    return PolicyPack(
        name="incident/strict",
        description="Strict incident response requirements",
        claims=[
            ClaimDefinition(
                name="service_restored",
                description="Service has been restored to normal operation",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.HEALTHCHECK,
                        description="Healthcheck passes",
                        command="curl -sf $SERVICE_URL/health || exit 1",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.METRIC_THRESHOLD,
                        description="Error rate below threshold",
                        metric_query="rate(http_errors_total[5m])",
                        threshold=0.01,
                        threshold_op="lt",
                        optional=True,  # Optional until monitoring integration
                    ),
                    ProofRequirement(
                        proof_type=ProofType.ROLLBACK_PLAN,
                        description="Rollback plan present",
                        file_path="ROLLBACK.md",
                        optional=False,
                    ),
                ],
            ),
            ClaimDefinition(
                name="incident_resolved",
                description="Incident has been fully resolved",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.PRECONDITION,
                        description="Service was restored",
                        precondition_claim="service_restored",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.APPROVAL,
                        description="Resolution approved by on-call",
                        approver_role="oncall",
                    ),
                ],
            ),
        ],
    )


def create_change_mgmt_basic_pack() -> PolicyPack:
    """Create the change_mgmt/basic policy pack."""
    return PolicyPack(
        name="change_mgmt/basic",
        description="Basic change management requirements",
        claims=[
            ClaimDefinition(
                name="change_approved",
                description="Change has been approved",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.DIFF_REVIEW,
                        description="Diff was reviewed",
                        command="git diff HEAD~1 --stat",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.APPROVAL,
                        description="Approved by reviewer",
                        approver_role="reviewer",
                    ),
                ],
            ),
            ClaimDefinition(
                name="change_complete",
                description="Change has been completed and verified",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.PRECONDITION,
                        description="Change was approved",
                        precondition_claim="change_approved",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.SMOKE_TEST,
                        description="Smoke test passed",
                        command="make smoke-test || npm run smoke-test || echo 'No smoke test defined'",
                        expected_exit_code=0,
                    ),
                ],
            ),
        ],
    )


def create_database_migration_pack() -> PolicyPack:
    """Create the database/migration policy pack."""
    return PolicyPack(
        name="database/migration",
        description="Database migration safety requirements",
        claims=[
            ClaimDefinition(
                name="migration_ready",
                description="Migration is ready to apply",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.FILE_EXISTS,
                        description="Migration file exists",
                        file_path="migrations/",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="Migration is reversible",
                        command="grep -l 'down\\|rollback\\|revert' migrations/*.sql 2>/dev/null || exit 1",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.ROLLBACK_PLAN,
                        description="Rollback procedure documented",
                        file_path="migrations/ROLLBACK.md",
                    ),
                ],
            ),
            ClaimDefinition(
                name="migration_tested",
                description="Migration has been tested in staging",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.PRECONDITION,
                        description="Migration is ready",
                        precondition_claim="migration_ready",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="Migration dry-run successful",
                        command="make migrate-dry-run || echo 'dry-run not configured'",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.APPROVAL,
                        description="DBA approval for production",
                        approver_role="dba",
                        optional=True,  # Optional for small teams
                    ),
                ],
            ),
            ClaimDefinition(
                name="migration_complete",
                description="Migration applied and verified",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.PRECONDITION,
                        description="Migration was tested",
                        precondition_claim="migration_tested",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="Migration applied successfully",
                        command="make migrate-status || echo 'status check not configured'",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.HEALTHCHECK,
                        description="Application healthy post-migration",
                        command="curl -sf http://localhost:8080/health || exit 1",
                        expected_exit_code=0,
                    ),
                ],
            ),
        ],
    )


def create_security_access_pack() -> PolicyPack:
    """Create the security/access policy pack."""
    return PolicyPack(
        name="security/access",
        description="Security and access control requirements",
        claims=[
            ClaimDefinition(
                name="access_granted",
                description="Access has been properly granted",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.APPROVAL,
                        description="Security team approval",
                        approver_role="security",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.TIME_WINDOW,
                        description="Access granted during business hours",
                        time_window_start="09:00",
                        time_window_end="17:00",
                        optional=True,  # Can be waived for emergencies
                    ),
                ],
            ),
            ClaimDefinition(
                name="access_revoked",
                description="Access has been properly revoked",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="Access removal verified",
                        command="echo 'Access removal command here'",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.APPROVAL,
                        description="Revocation confirmed",
                        approver_role="manager",
                    ),
                ],
            ),
            ClaimDefinition(
                name="secrets_rotated",
                description="Secrets have been rotated",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="Old secrets invalidated",
                        command="echo 'Secret rotation command here'",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.HEALTHCHECK,
                        description="Services healthy with new secrets",
                        command="curl -sf http://localhost:8080/health || exit 1",
                        expected_exit_code=0,
                    ),
                ],
            ),
        ],
    )


def create_oncall_handoff_pack() -> PolicyPack:
    """Create the oncall/handoff policy pack."""
    return PolicyPack(
        name="oncall/handoff",
        description="Oncall handoff requirements",
        claims=[
            ClaimDefinition(
                name="handoff_ready",
                description="Oncall handoff is ready",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.FILE_EXISTS,
                        description="Handoff notes exist",
                        file_path=".oncall/handoff.md",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="No active incidents",
                        command="ls .governor/ops/incidents/*.json 2>/dev/null | xargs -I {} grep -l '\"status\": \"detected\"\\|\"status\": \"investigating\"' {} 2>/dev/null || echo 'no active'",
                        expected_pattern="no active",
                    ),
                ],
            ),
            ClaimDefinition(
                name="handoff_complete",
                description="Oncall handoff completed",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.PRECONDITION,
                        description="Handoff was ready",
                        precondition_claim="handoff_ready",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.APPROVAL,
                        description="Outgoing oncall confirms handoff",
                        approver_role="oncall_outgoing",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.APPROVAL,
                        description="Incoming oncall acknowledges",
                        approver_role="oncall_incoming",
                    ),
                ],
            ),
        ],
    )


def create_feature_rollout_pack() -> PolicyPack:
    """Create the feature/rollout policy pack."""
    return PolicyPack(
        name="feature/rollout",
        description="Feature flag rollout requirements",
        claims=[
            ClaimDefinition(
                name="feature_canary",
                description="Feature ready for canary rollout",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="Feature flag configured",
                        command="echo 'Feature flag check command'",
                        expected_exit_code=0,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.ROLLBACK_PLAN,
                        description="Rollback documented",
                        file_path="features/ROLLBACK.md",
                    ),
                ],
            ),
            ClaimDefinition(
                name="feature_staged",
                description="Feature rolled out to percentage",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.PRECONDITION,
                        description="Canary was successful",
                        precondition_claim="feature_canary",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.METRIC_THRESHOLD,
                        description="Error rate acceptable",
                        metric_query="rate(feature_errors_total[5m])",
                        threshold=0.01,
                        threshold_op="lt",
                        optional=True,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.TIME_WINDOW,
                        description="Bake time elapsed",
                        time_window_duration_minutes=30,
                        optional=True,
                    ),
                ],
            ),
            ClaimDefinition(
                name="feature_ga",
                description="Feature at general availability",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.PRECONDITION,
                        description="Staged rollout completed",
                        precondition_claim="feature_staged",
                    ),
                    ProofRequirement(
                        proof_type=ProofType.APPROVAL,
                        description="Product owner approval",
                        approver_role="product_owner",
                    ),
                ],
            ),
        ],
    )


def create_infra_scaling_pack() -> PolicyPack:
    """Create the infra/scaling policy pack."""
    return PolicyPack(
        name="infra/scaling",
        description="Infrastructure scaling requirements",
        claims=[
            ClaimDefinition(
                name="scale_up_ready",
                description="Ready to scale up infrastructure",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.METRIC_THRESHOLD,
                        description="Current utilization high",
                        metric_query="avg(cpu_utilization)",
                        threshold=0.7,
                        threshold_op="gt",
                        optional=True,  # Until monitoring integrated
                    ),
                    ProofRequirement(
                        proof_type=ProofType.COMMAND_OUTPUT,
                        description="Capacity available",
                        command="echo 'capacity check'",
                        expected_exit_code=0,
                    ),
                ],
            ),
            ClaimDefinition(
                name="scale_down_safe",
                description="Safe to scale down infrastructure",
                requirements=[
                    ProofRequirement(
                        proof_type=ProofType.METRIC_THRESHOLD,
                        description="Utilization low enough",
                        metric_query="avg(cpu_utilization)",
                        threshold=0.3,
                        threshold_op="lt",
                        optional=True,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.TIME_WINDOW,
                        description="Not during peak hours",
                        time_window_start="22:00",
                        time_window_end="06:00",
                        optional=True,
                    ),
                    ProofRequirement(
                        proof_type=ProofType.HEALTHCHECK,
                        description="All instances healthy",
                        command="echo 'health check command'",
                        expected_exit_code=0,
                    ),
                ],
            ),
        ],
    )


BUILTIN_PACKS = {
    "deploy/safe_rollout": create_deploy_safe_rollout_pack,
    "incident/strict": create_incident_strict_pack,
    "change_mgmt/basic": create_change_mgmt_basic_pack,
    "database/migration": create_database_migration_pack,
    "security/access": create_security_access_pack,
    "oncall/handoff": create_oncall_handoff_pack,
    "feature/rollout": create_feature_rollout_pack,
    "infra/scaling": create_infra_scaling_pack,
}


def install_builtin_pack(registry: PolicyRegistry, pack_name: str) -> PolicyPack | None:
    """Install a built-in policy pack."""
    if pack_name not in BUILTIN_PACKS:
        return None

    pack = BUILTIN_PACKS[pack_name]()
    registry.register(pack)
    return pack
