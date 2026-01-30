"""Tests for the SRE/Ops Governor."""

import json
import pytest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from ops_governor import (
    ProofType,
    ProofRequirement,
    ProofEvidence,
    ClaimDefinition,
    ClaimAttempt,
    PolicyPack,
    PolicyRegistry,
    ProofCollector,
    ClaimVerifier,
    BUILTIN_PACKS,
    install_builtin_pack,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentEvent,
    RunbookVerifier,
    TimeWindowVerifier,
    BlastRadiusVerifier,
    PreconditionChainVerifier,
)


# ============================================================================
# Type Tests
# ============================================================================


class TestProofRequirement:
    """Tests for ProofRequirement type."""

    def test_create_command_requirement(self):
        """Test creating a command output requirement."""
        req = ProofRequirement(
            proof_type=ProofType.COMMAND_OUTPUT,
            description="Tests pass",
            command="pytest",
            expected_exit_code=0,
        )

        assert req.proof_type == ProofType.COMMAND_OUTPUT
        assert req.command == "pytest"
        assert req.expected_exit_code == 0

    def test_create_healthcheck_requirement(self):
        """Test creating a healthcheck requirement."""
        req = ProofRequirement(
            proof_type=ProofType.HEALTHCHECK,
            description="Service is healthy",
            command="curl -sf http://localhost:8080/health",
            expected_exit_code=0,
        )

        assert req.proof_type == ProofType.HEALTHCHECK

    def test_create_metric_requirement(self):
        """Test creating a metric threshold requirement."""
        req = ProofRequirement(
            proof_type=ProofType.METRIC_THRESHOLD,
            description="Error rate below 1%",
            metric_query="rate(errors[5m])",
            threshold=0.01,
            threshold_op="lt",
        )

        assert req.proof_type == ProofType.METRIC_THRESHOLD
        assert req.threshold == 0.01

    def test_serialization_roundtrip(self):
        """Test requirement serialization."""
        req = ProofRequirement(
            proof_type=ProofType.COMMAND_OUTPUT,
            description="Tests pass",
            command="pytest",
            expected_exit_code=0,
            expected_pattern="passed",
        )

        data = req.to_dict()
        restored = ProofRequirement.from_dict(data)

        assert restored.proof_type == req.proof_type
        assert restored.command == req.command
        assert restored.expected_pattern == req.expected_pattern


class TestClaimDefinition:
    """Tests for ClaimDefinition type."""

    def test_create_claim(self):
        """Test creating a claim definition."""
        claim = ClaimDefinition(
            name="service_restored",
            description="Service has been restored",
            requirements=[
                ProofRequirement(
                    proof_type=ProofType.HEALTHCHECK,
                    command="curl -sf http://localhost/health",
                ),
            ],
        )

        assert claim.name == "service_restored"
        assert len(claim.requirements) == 1

    def test_serialization_roundtrip(self):
        """Test claim serialization."""
        claim = ClaimDefinition(
            name="deploy_complete",
            description="Deployment finished",
            requirements=[
                ProofRequirement(
                    proof_type=ProofType.COMMAND_OUTPUT,
                    command="echo 'deployed'",
                ),
            ],
            tags=["deploy", "production"],
        )

        data = claim.to_dict()
        restored = ClaimDefinition.from_dict(data)

        assert restored.name == claim.name
        assert len(restored.requirements) == 1
        assert restored.tags == ["deploy", "production"]


class TestPolicyPack:
    """Tests for PolicyPack type."""

    def test_create_pack(self):
        """Test creating a policy pack."""
        pack = PolicyPack(
            name="deploy/safe_rollout",
            description="Safe deployment policy",
            claims=[
                ClaimDefinition(name="deploy_ready", description="Ready to deploy"),
            ],
        )

        assert pack.name == "deploy/safe_rollout"
        assert len(pack.claims) == 1

    def test_get_claim(self):
        """Test getting a claim from a pack."""
        pack = PolicyPack(
            name="test/pack",
            claims=[
                ClaimDefinition(name="claim_a", description="A"),
                ClaimDefinition(name="claim_b", description="B"),
            ],
        )

        claim = pack.get_claim("claim_a")
        assert claim is not None
        assert claim.name == "claim_a"

        missing = pack.get_claim("nonexistent")
        assert missing is None

    def test_serialization_roundtrip(self):
        """Test pack serialization."""
        pack = PolicyPack(
            name="incident/strict",
            version="2.0.0",
            claims=[
                ClaimDefinition(name="resolved", description="Incident resolved"),
            ],
            environments=["production"],
        )

        data = pack.to_dict()
        restored = PolicyPack.from_dict(data)

        assert restored.name == pack.name
        assert restored.version == "2.0.0"
        assert restored.environments == ["production"]


# ============================================================================
# Policy Registry Tests
# ============================================================================


class TestPolicyRegistry:
    """Tests for PolicyRegistry."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create a fresh registry."""
        return PolicyRegistry(tmp_path)

    def test_register_and_get(self, registry):
        """Test registering and retrieving a pack."""
        pack = PolicyPack(
            name="test/pack",
            claims=[ClaimDefinition(name="test_claim")],
        )

        registry.register(pack)

        retrieved = registry.get("test/pack")
        assert retrieved is not None
        assert retrieved.name == "test/pack"

    def test_persistence(self, tmp_path):
        """Test that packs persist across instances."""
        reg1 = PolicyRegistry(tmp_path)
        reg1.register(PolicyPack(name="persistent/pack"))

        # Create new instance
        reg2 = PolicyRegistry(tmp_path)
        pack = reg2.get("persistent/pack")

        assert pack is not None
        assert pack.name == "persistent/pack"

    def test_enabled_packs(self, registry):
        """Test filtering enabled packs."""
        registry.register(PolicyPack(name="enabled", enabled=True))
        registry.register(PolicyPack(name="disabled", enabled=False))

        enabled = registry.enabled_packs()

        assert len(enabled) == 1
        assert enabled[0].name == "enabled"

    def test_environment_filtering(self, registry):
        """Test filtering by environment."""
        registry.register(PolicyPack(name="prod_only", environments=["production"]))
        registry.register(PolicyPack(name="all_envs", environments=[]))

        prod = registry.enabled_packs(environment="production")
        staging = registry.enabled_packs(environment="staging")

        assert len(prod) == 2
        assert len(staging) == 1
        assert staging[0].name == "all_envs"

    def test_get_claim(self, registry):
        """Test finding a claim across packs."""
        registry.register(PolicyPack(
            name="pack_a",
            claims=[ClaimDefinition(name="claim_1")],
        ))
        registry.register(PolicyPack(
            name="pack_b",
            claims=[ClaimDefinition(name="claim_2")],
        ))

        claim, pack = registry.get_claim("claim_2")

        assert claim is not None
        assert claim.name == "claim_2"
        assert pack.name == "pack_b"


# ============================================================================
# Proof Collection Tests
# ============================================================================


class TestProofCollector:
    """Tests for ProofCollector."""

    @pytest.fixture
    def collector(self, tmp_path):
        """Create a proof collector."""
        return ProofCollector(tmp_path)

    def test_collect_command_success(self, collector):
        """Test collecting successful command output."""
        req = ProofRequirement(
            proof_type=ProofType.COMMAND_OUTPUT,
            command="echo 'hello world'",
            expected_exit_code=0,
        )

        evidence = collector.collect(req)

        assert evidence.satisfied
        assert evidence.exit_code == 0
        assert "hello world" in evidence.output

    def test_collect_command_failure(self, collector):
        """Test collecting failed command output."""
        req = ProofRequirement(
            proof_type=ProofType.COMMAND_OUTPUT,
            command="exit 1",
            expected_exit_code=0,
        )

        evidence = collector.collect(req)

        assert not evidence.satisfied
        assert evidence.exit_code == 1
        assert "Exit code 1" in evidence.failure_reason

    def test_collect_command_pattern_match(self, collector):
        """Test pattern matching in command output."""
        req = ProofRequirement(
            proof_type=ProofType.COMMAND_OUTPUT,
            command="echo 'tests passed: 42'",
            expected_pattern=r"passed: \d+",
        )

        evidence = collector.collect(req)

        assert evidence.satisfied

    def test_collect_command_pattern_fail(self, collector):
        """Test pattern mismatch."""
        req = ProofRequirement(
            proof_type=ProofType.COMMAND_OUTPUT,
            command="echo 'tests failed'",
            expected_pattern=r"passed: \d+",
        )

        evidence = collector.collect(req)

        assert not evidence.satisfied
        assert "did not match pattern" in evidence.failure_reason

    def test_collect_file_exists(self, collector, tmp_path):
        """Test file existence check."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        req = ProofRequirement(
            proof_type=ProofType.FILE_EXISTS,
            file_path=str(test_file),
        )

        evidence = collector.collect(req)

        assert evidence.satisfied
        assert evidence.file_exists
        assert evidence.file_hash is not None

    def test_collect_file_not_exists(self, collector, tmp_path):
        """Test missing file."""
        req = ProofRequirement(
            proof_type=ProofType.FILE_EXISTS,
            file_path=str(tmp_path / "nonexistent.txt"),
        )

        evidence = collector.collect(req)

        assert not evidence.satisfied
        assert "not found" in evidence.failure_reason

    def test_collect_file_hash_match(self, collector, tmp_path):
        """Test file hash verification."""
        import hashlib
        test_file = tmp_path / "test.txt"
        content = "specific content"
        test_file.write_text(content)
        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        req = ProofRequirement(
            proof_type=ProofType.FILE_EXISTS,
            file_path=str(test_file),
            expected_hash=expected_hash,
        )

        evidence = collector.collect(req)

        assert evidence.satisfied

    def test_collect_approval_requires_manual(self, collector):
        """Test that approval requires manual input."""
        req = ProofRequirement(
            proof_type=ProofType.APPROVAL,
            approver_role="admin",
        )

        evidence = collector.collect(req)

        assert not evidence.satisfied
        assert "manual input" in evidence.failure_reason


# ============================================================================
# Claim Verification Tests
# ============================================================================


class TestClaimVerifier:
    """Tests for ClaimVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a claim verifier with test policy."""
        verifier = ClaimVerifier(tmp_path)

        # Register a test policy
        verifier.registry.register(PolicyPack(
            name="test/policy",
            claims=[
                ClaimDefinition(
                    name="simple_claim",
                    requirements=[
                        ProofRequirement(
                            proof_type=ProofType.COMMAND_OUTPUT,
                            command="echo 'ok'",
                            expected_exit_code=0,
                        ),
                    ],
                ),
                ClaimDefinition(
                    name="multi_req_claim",
                    requirements=[
                        ProofRequirement(
                            proof_type=ProofType.COMMAND_OUTPUT,
                            command="echo 'first'",
                        ),
                        ProofRequirement(
                            proof_type=ProofType.COMMAND_OUTPUT,
                            command="echo 'second'",
                        ),
                    ],
                ),
                ClaimDefinition(
                    name="optional_req_claim",
                    requirements=[
                        ProofRequirement(
                            proof_type=ProofType.COMMAND_OUTPUT,
                            command="echo 'required'",
                        ),
                        ProofRequirement(
                            proof_type=ProofType.APPROVAL,
                            optional=True,
                        ),
                    ],
                ),
            ],
        ))

        return verifier

    def test_verify_simple_claim(self, verifier):
        """Test verifying a simple claim."""
        attempt = verifier.verify_claim("simple_claim", actor="test_user")

        assert attempt.satisfied
        assert len(attempt.evidence) == 1
        assert attempt.evidence[0].satisfied

    def test_verify_unknown_claim(self, verifier):
        """Test verifying unknown claim."""
        attempt = verifier.verify_claim("nonexistent", actor="test_user")

        assert not attempt.satisfied
        assert "claim_not_found" in attempt.missing_requirements

    def test_verify_multi_requirement(self, verifier):
        """Test claim with multiple requirements."""
        attempt = verifier.verify_claim("multi_req_claim", actor="test_user")

        assert attempt.satisfied
        assert len(attempt.evidence) == 2

    def test_verify_with_optional(self, verifier):
        """Test that optional requirements don't block satisfaction."""
        attempt = verifier.verify_claim("optional_req_claim", actor="test_user")

        # Should satisfy because approval is optional
        assert attempt.satisfied
        assert len(attempt.evidence) == 2
        # One satisfied (command), one not (approval)
        satisfied_count = sum(1 for e in attempt.evidence if e.satisfied)
        assert satisfied_count == 1


# ============================================================================
# Built-in Policy Pack Tests
# ============================================================================


class TestBuiltinPacks:
    """Tests for built-in policy packs."""

    def test_all_builtin_packs_exist(self):
        """Test that all expected built-in packs are defined."""
        expected = [
            "deploy/safe_rollout",
            "incident/strict",
            "change_mgmt/basic",
            "database/migration",
            "security/access",
            "oncall/handoff",
            "feature/rollout",
            "infra/scaling",
        ]

        for name in expected:
            assert name in BUILTIN_PACKS

    def test_install_builtin_pack(self, tmp_path):
        """Test installing a built-in pack."""
        registry = PolicyRegistry(tmp_path)

        pack = install_builtin_pack(registry, "incident/strict")

        assert pack is not None
        assert pack.name == "incident/strict"
        assert registry.get("incident/strict") is not None

    def test_incident_strict_has_service_restored(self, tmp_path):
        """Test that incident/strict has service_restored claim."""
        registry = PolicyRegistry(tmp_path)
        pack = install_builtin_pack(registry, "incident/strict")

        claim = pack.get_claim("service_restored")

        assert claim is not None
        assert len(claim.requirements) >= 2  # healthcheck + rollback at minimum

    def test_database_migration_pack(self, tmp_path):
        """Test database/migration pack structure."""
        registry = PolicyRegistry(tmp_path)
        pack = install_builtin_pack(registry, "database/migration")

        assert pack is not None
        assert pack.name == "database/migration"

        # Should have migration-related claims
        assert pack.get_claim("migration_ready") is not None
        assert pack.get_claim("migration_tested") is not None
        assert pack.get_claim("migration_complete") is not None

    def test_security_access_pack(self, tmp_path):
        """Test security/access pack structure."""
        registry = PolicyRegistry(tmp_path)
        pack = install_builtin_pack(registry, "security/access")

        assert pack is not None
        assert pack.name == "security/access"

        # Should have access control claims
        assert pack.get_claim("access_granted") is not None
        assert pack.get_claim("access_revoked") is not None
        assert pack.get_claim("secrets_rotated") is not None

    def test_oncall_handoff_pack(self, tmp_path):
        """Test oncall/handoff pack structure."""
        registry = PolicyRegistry(tmp_path)
        pack = install_builtin_pack(registry, "oncall/handoff")

        assert pack is not None

        # Should require both outgoing and incoming approval
        handoff_complete = pack.get_claim("handoff_complete")
        assert handoff_complete is not None

        approval_reqs = [r for r in handoff_complete.requirements if r.proof_type == ProofType.APPROVAL]
        assert len(approval_reqs) >= 2  # outgoing + incoming

    def test_feature_rollout_pack(self, tmp_path):
        """Test feature/rollout pack structure."""
        registry = PolicyRegistry(tmp_path)
        pack = install_builtin_pack(registry, "feature/rollout")

        assert pack is not None

        # Should have staged rollout claims
        assert pack.get_claim("feature_canary") is not None
        assert pack.get_claim("feature_staged") is not None
        assert pack.get_claim("feature_ga") is not None

    def test_infra_scaling_pack(self, tmp_path):
        """Test infra/scaling pack structure."""
        registry = PolicyRegistry(tmp_path)
        pack = install_builtin_pack(registry, "infra/scaling")

        assert pack is not None

        # Should have scale up and scale down claims
        assert pack.get_claim("scale_up_ready") is not None
        assert pack.get_claim("scale_down_safe") is not None


# ============================================================================
# Incident Tests
# ============================================================================


class TestIncident:
    """Tests for Incident type."""

    def test_create_incident(self):
        """Test creating an incident."""
        incident = Incident(
            title="Database outage",
            severity=IncidentSeverity.SEV2,
            service="postgres",
            environment="production",
        )

        assert incident.title == "Database outage"
        assert incident.severity == IncidentSeverity.SEV2
        assert incident.status == IncidentStatus.DETECTED

    def test_add_event(self):
        """Test adding events to timeline."""
        incident = Incident(title="Test incident")

        event = incident.add_event(
            event_type="note",
            actor="oncall",
            description="Investigating...",
        )

        assert len(incident.timeline) == 1
        assert incident.timeline[0].event_type == "note"

    def test_change_status(self):
        """Test changing incident status."""
        incident = Incident(title="Test incident")

        event = incident.change_status(IncidentStatus.INVESTIGATING, actor="oncall")

        assert incident.status == IncidentStatus.INVESTIGATING
        assert event.old_status == IncidentStatus.DETECTED
        assert event.new_status == IncidentStatus.INVESTIGATING

    def test_resolved_sets_timestamp(self):
        """Test that resolving sets resolved_at."""
        incident = Incident(title="Test incident")

        assert incident.resolved_at is None

        incident.change_status(IncidentStatus.RESOLVED, actor="oncall")

        assert incident.resolved_at is not None

    def test_serialization_roundtrip(self):
        """Test incident serialization."""
        incident = Incident(
            title="Test incident",
            severity=IncidentSeverity.SEV1,
            service="api",
            commander="lead",
        )
        incident.add_event("note", "user", "Initial report")
        incident.change_status(IncidentStatus.INVESTIGATING, "oncall")

        data = incident.to_dict()
        restored = Incident.from_dict(data)

        assert restored.title == incident.title
        assert restored.severity == IncidentSeverity.SEV1
        assert len(restored.timeline) == 2
        assert restored.status == IncidentStatus.INVESTIGATING


# ============================================================================
# Runbook Verifier Tests
# ============================================================================


class TestRunbookVerifier:
    """Tests for RunbookVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a runbook verifier."""
        return RunbookVerifier(tmp_path)

    def test_create_runbook(self, verifier):
        """Test creating a runbook."""
        runbook = verifier.create_runbook(
            name="deploy_service",
            description="Deploy a service",
            steps=[
                {"description": "Run tests", "command": "make test"},
                {"description": "Build image", "command": "make build"},
                {"description": "Deploy", "command": "make deploy"},
            ],
            rollback_steps=[
                {"description": "Rollback", "command": "make rollback"},
            ],
        )

        assert runbook["name"] == "deploy_service"
        assert len(runbook["steps"]) == 3
        assert len(runbook["rollback_steps"]) == 1

    def test_load_runbook(self, verifier):
        """Test loading a runbook."""
        verifier.create_runbook(
            name="test_runbook",
            description="Test",
            steps=[{"description": "Step 1", "command": "echo 1"}],
        )

        loaded = verifier.load_runbook("test_runbook")

        assert loaded is not None
        assert loaded["name"] == "test_runbook"

    def test_verify_step_success(self, verifier):
        """Test verifying a successful step."""
        verifier.create_runbook(
            name="simple",
            description="Simple runbook",
            steps=[
                {
                    "description": "Check",
                    "command": "echo ok",
                    "expected_evidence": [
                        {"type": "command_exit_code", "value": 0}
                    ],
                }
            ],
        )

        success, msg = verifier.verify_step(
            "simple",
            step_index=0,
            evidence={"exit_code": 0},
        )

        assert success

    def test_verify_step_failure(self, verifier):
        """Test verifying a failed step."""
        verifier.create_runbook(
            name="strict",
            description="Strict runbook",
            steps=[
                {
                    "description": "Must succeed",
                    "expected_evidence": [
                        {"type": "command_exit_code", "value": 0}
                    ],
                }
            ],
        )

        success, msg = verifier.verify_step(
            "strict",
            step_index=0,
            evidence={"exit_code": 1},
        )

        assert not success
        assert "exit code" in msg.lower()

    def test_generate_claim_requirements(self, verifier):
        """Test generating claim requirements from runbook."""
        verifier.create_runbook(
            name="with_commands",
            description="Commands runbook",
            steps=[
                {"description": "Test", "command": "make test"},
                {"description": "Build", "command": "make build"},
            ],
        )

        requirements = verifier.generate_claim_requirements("with_commands")

        assert len(requirements) == 2
        assert all(r.proof_type == ProofType.COMMAND_OUTPUT for r in requirements)


# ============================================================================
# Time Window Verifier Tests
# ============================================================================


class TestTimeWindowVerifier:
    """Tests for TimeWindowVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a time window verifier."""
        return TimeWindowVerifier(tmp_path)

    def test_define_window(self, verifier):
        """Test defining a change window."""
        verifier.define_window(
            name="business_hours",
            start_time="09:00",
            end_time="17:00",
            days=["monday", "tuesday", "wednesday", "thursday", "friday"],
            description="Business hours only",
        )

        allowed, _ = verifier.is_within_window("business_hours")
        # Result depends on current time, just check it runs
        assert isinstance(allowed, bool)

    def test_define_blackout(self, verifier):
        """Test defining a blackout period."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        verifier.define_blackout(
            name="holiday_freeze",
            start=now - timedelta(hours=1),
            end=now + timedelta(hours=1),
            reason="Holiday code freeze",
        )

        allowed, name = verifier.check_blackouts()

        assert not allowed
        assert name == "blackout:holiday_freeze"

    def test_outside_blackout(self, verifier):
        """Test time outside blackout."""
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        verifier.define_blackout(
            name="past_freeze",
            start=now - timedelta(days=10),
            end=now - timedelta(days=5),
            reason="Old freeze",
        )

        allowed, name = verifier.check_blackouts()

        assert allowed
        assert name is None

    def test_create_requirement(self, verifier):
        """Test creating a proof requirement from window."""
        verifier.define_window(
            name="maintenance",
            start_time="02:00",
            end_time="06:00",
        )

        req = verifier.create_requirement("maintenance")

        assert req.proof_type == ProofType.TIME_WINDOW
        assert req.time_window_start == "02:00"
        assert req.time_window_end == "06:00"


# ============================================================================
# Blast Radius Verifier Tests
# ============================================================================


class TestBlastRadiusVerifier:
    """Tests for BlastRadiusVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a blast radius verifier."""
        return BlastRadiusVerifier(tmp_path)

    def test_define_limit(self, verifier):
        """Test defining blast radius limits."""
        verifier.define_limit(
            name="standard",
            max_services=3,
            max_traffic_percent=10.0,
            max_regions=1,
        )

        within, violations, _ = verifier.check_blast_radius(
            "standard",
            affected_services=["svc1", "svc2"],
            traffic_percent=5.0,
        )

        assert within
        assert len(violations) == 0

    def test_exceeds_service_limit(self, verifier):
        """Test exceeding service limit."""
        verifier.define_limit(
            name="strict",
            max_services=2,
        )

        within, violations, _ = verifier.check_blast_radius(
            "strict",
            affected_services=["svc1", "svc2", "svc3", "svc4"],
        )

        assert not within
        assert len(violations) == 1
        assert "4 services" in violations[0]

    def test_exceeds_traffic_limit(self, verifier):
        """Test exceeding traffic limit."""
        verifier.define_limit(
            name="traffic_limit",
            max_traffic_percent=5.0,
        )

        within, violations, _ = verifier.check_blast_radius(
            "traffic_limit",
            traffic_percent=15.0,
        )

        assert not within
        assert "15.0%" in violations[0]

    def test_requires_approval(self, verifier):
        """Test that large changes require approval."""
        verifier.define_limit(
            name="approval_needed",
            requires_approval_above={"traffic_percent": 5.0},
        )

        within, violations, requires_approval = verifier.check_blast_radius(
            "approval_needed",
            traffic_percent=10.0,
        )

        assert within  # Within limits
        assert requires_approval  # But needs approval

    def test_region_restrictions(self, verifier):
        """Test region restrictions."""
        verifier.define_limit(
            name="region_limited",
            allowed_regions=["us-east-1", "us-west-2"],
        )

        within, violations, _ = verifier.check_blast_radius(
            "region_limited",
            regions=["us-east-1", "eu-west-1"],
        )

        assert not within
        assert "eu-west-1" in str(violations)


# ============================================================================
# Precondition Chain Verifier Tests
# ============================================================================


class TestPreconditionChainVerifier:
    """Tests for PreconditionChainVerifier."""

    @pytest.fixture
    def verifier(self, tmp_path):
        """Create a precondition chain verifier."""
        return PreconditionChainVerifier(tmp_path)

    def test_define_chain(self, verifier):
        """Test defining a precondition chain."""
        verifier.define_chain(
            "deploy_complete",
            ["tests_pass", "build_complete", "deploy_approved"],
        )

        all_satisfied, missing = verifier.check_prerequisites(
            "deploy_complete",
            context_id="deploy-123",
        )

        assert not all_satisfied
        assert len(missing) == 3

    def test_mark_satisfied(self, verifier):
        """Test marking prerequisites as satisfied."""
        verifier.define_chain("final", ["step1", "step2"])

        verifier.mark_satisfied("step1", "ctx-1", {"evidence": "passed"})

        all_satisfied, missing = verifier.check_prerequisites("final", "ctx-1")

        assert not all_satisfied
        assert missing == ["step2"]

    def test_all_prerequisites_satisfied(self, verifier):
        """Test when all prerequisites are satisfied."""
        verifier.define_chain("goal", ["prereq1", "prereq2"])

        verifier.mark_satisfied("prereq1", "ctx", {})
        verifier.mark_satisfied("prereq2", "ctx", {})

        all_satisfied, missing = verifier.check_prerequisites("goal", "ctx")

        assert all_satisfied
        assert missing == []

    def test_chain_status(self, verifier):
        """Test getting chain status."""
        verifier.define_chain("target", ["a", "b", "c"])
        verifier.mark_satisfied("a", "context", {})
        verifier.mark_satisfied("c", "context", {})

        status = verifier.get_chain_status("target", "context")

        assert status["a"]["satisfied"]
        assert not status["b"]["satisfied"]
        assert status["c"]["satisfied"]

    def test_context_isolation(self, verifier):
        """Test that different contexts are isolated."""
        verifier.define_chain("claim", ["prereq"])

        verifier.mark_satisfied("prereq", "context-a", {})

        # Context A should be satisfied
        satisfied_a, _ = verifier.check_prerequisites("claim", "context-a")
        assert satisfied_a

        # Context B should not be
        satisfied_b, _ = verifier.check_prerequisites("claim", "context-b")
        assert not satisfied_b
