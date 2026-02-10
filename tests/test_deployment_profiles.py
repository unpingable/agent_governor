"""Tests for Deployment Profiles — Authority Classes.

Layer 2.1-B. Invariant B: Action needs capability token.
Invariant E: Irreversible actions need two-phase commit.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from governor.deployment_profiles import (
    AuthorityClass,
    AuditLevel,
    ProposalStatus,
    RateLimit,
    CapabilityToken,
    DeploymentProfile,
    ActionProposal,
    DeploymentStore,
    PUBLIC_PROFILE,
    DELEGATED_PROFILE,
    OPERATOR_PROFILE,
    AUTONOMOUS_PROFILE,
    BUILTIN_PROFILES,
    check_tool_access,
    check_invariant_b,
    check_invariant_e,
    issue_token,
    propose_action,
    make_deployment_event,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------

class TestAuthorityClass:
    def test_values(self):
        assert AuthorityClass.A1_PUBLIC.value == "A1"
        assert AuthorityClass.A2_DELEGATED.value == "A2"
        assert AuthorityClass.A3_OPERATOR.value == "A3"
        assert AuthorityClass.A4_AUTONOMOUS.value == "A4"

    def test_count(self):
        assert len(AuthorityClass) == 4


class TestAuditLevel:
    def test_values(self):
        assert len(AuditLevel) == 4


class TestProposalStatus:
    def test_values(self):
        assert ProposalStatus.PENDING.value == "pending"
        assert ProposalStatus.APPROVED.value == "approved"
        assert ProposalStatus.EXECUTED.value == "executed"


# ---------------------------------------------------------------------------
# RateLimit Tests
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_check_allowed(self):
        rl = RateLimit(max_calls=5, window_seconds=60)
        assert rl.check()

    def test_consume(self):
        rl = RateLimit(max_calls=2, window_seconds=60)
        assert rl.consume()
        assert rl.consume()
        assert not rl.consume()

    def test_window_reset(self):
        rl = RateLimit(max_calls=1, window_seconds=1)
        rl.consume()
        assert not rl.check()
        # Simulate window expiry
        rl.window_start = time.time() - 2
        assert rl.check()

    def test_roundtrip(self):
        rl = RateLimit(max_calls=10, window_seconds=30)
        restored = RateLimit.from_dict(rl.to_dict())
        assert restored.max_calls == 10
        assert restored.window_seconds == 30


# ---------------------------------------------------------------------------
# CapabilityToken Tests
# ---------------------------------------------------------------------------

class TestCapabilityToken:
    def test_create(self):
        t = CapabilityToken(
            id="tok_001", scope={"src/**"}, verbs={"read", "write"},
            ttl_seconds=3600, bound_to="run1",
        )
        assert t.id == "tok_001"
        assert t.issued_at != ""

    def test_permits_valid(self):
        t = CapabilityToken(
            id="tok", scope={"src/**"}, verbs={"read", "write"},
            ttl_seconds=3600, bound_to="run1",
        )
        assert t.permits("read", "src/main.py")
        assert t.permits("write", "src/util.py")

    def test_permits_wrong_verb(self):
        t = CapabilityToken(
            id="tok", scope={"src/**"}, verbs={"read"},
            ttl_seconds=3600, bound_to="run1",
        )
        assert not t.permits("write", "src/main.py")

    def test_permits_wrong_scope(self):
        t = CapabilityToken(
            id="tok", scope={"src/**"}, verbs={"read"},
            ttl_seconds=3600, bound_to="run1",
        )
        assert not t.permits("read", "tests/test.py")

    def test_permits_expired(self):
        t = CapabilityToken(
            id="tok", scope={"*"}, verbs={"read"},
            ttl_seconds=0, bound_to="run1",
            issued_at="2020-01-01T00:00:00+00:00",
        )
        assert t.is_expired
        assert not t.permits("read", "anything")

    def test_consume(self):
        t = CapabilityToken(
            id="tok", scope={"*"}, verbs={"read"},
            ttl_seconds=3600, bound_to="run1",
            rate_limit=RateLimit(2, 60),
        )
        assert t.consume("read", "file1")
        assert t.consume("read", "file2")
        assert not t.consume("read", "file3")  # Rate limited

    def test_glob_scope(self):
        t = CapabilityToken(
            id="tok", scope={"src/*.py", "tests/*.py"}, verbs={"read"},
            ttl_seconds=3600, bound_to="run1",
        )
        assert t.permits("read", "src/main.py")
        assert t.permits("read", "tests/test_main.py")
        assert not t.permits("read", "docs/readme.md")

    def test_to_dict(self):
        t = CapabilityToken(
            id="tok_001", scope={"src/**"}, verbs={"read"},
            ttl_seconds=3600, bound_to="run1",
        )
        d = t.to_dict()
        assert d["id"] == "tok_001"
        assert d["scope"] == ["src/**"]
        assert d["verbs"] == ["read"]

    def test_roundtrip(self):
        t = CapabilityToken(
            id="tok_001", scope={"src/**", "lib/**"}, verbs={"read", "write"},
            ttl_seconds=7200, bound_to="session_abc",
        )
        restored = CapabilityToken.from_dict(t.to_dict())
        assert restored.id == "tok_001"
        assert restored.scope == t.scope
        assert restored.verbs == t.verbs
        assert restored.ttl_seconds == 7200


# ---------------------------------------------------------------------------
# DeploymentProfile Tests
# ---------------------------------------------------------------------------

class TestDeploymentProfile:
    def test_allows_tool_whitelist(self):
        p = DeploymentProfile(
            authority_class=AuthorityClass.A1_PUBLIC,
            tool_whitelist={"read_file", "web_search"},
            tool_blacklist=set(),
            max_budget={"explore": 10, "draft": 5, "verify": 5},
            requires_two_phase={"S3"},
            evidence_threshold=0.8,
            audit_level=AuditLevel.STANDARD,
        )
        assert p.allows_tool("read_file")
        assert not p.allows_tool("execute")

    def test_allows_tool_blacklist(self):
        p = DeploymentProfile(
            authority_class=AuthorityClass.A3_OPERATOR,
            tool_whitelist={"*"},
            tool_blacklist={"deploy"},
            max_budget={}, requires_two_phase=set(),
            evidence_threshold=0.6, audit_level=AuditLevel.HEAVY,
        )
        assert p.allows_tool("read_file")
        assert p.allows_tool("execute")
        assert not p.allows_tool("deploy")

    def test_needs_approval(self):
        p = PUBLIC_PROFILE
        assert p.needs_approval("S2")
        assert p.needs_approval("S3")
        assert not p.needs_approval("S1")

    def test_roundtrip(self):
        p = DELEGATED_PROFILE
        restored = DeploymentProfile.from_dict(p.to_dict())
        assert restored.authority_class == p.authority_class
        assert restored.evidence_threshold == p.evidence_threshold


class TestBuiltinProfiles:
    def test_count(self):
        assert len(BUILTIN_PROFILES) == 4

    def test_public(self):
        p = PUBLIC_PROFILE
        assert p.authority_class == AuthorityClass.A1_PUBLIC
        assert not p.allows_tool("execute")
        assert p.allows_tool("read_file")
        assert p.evidence_threshold == 0.8

    def test_delegated(self):
        p = DELEGATED_PROFILE
        assert p.authority_class == AuthorityClass.A2_DELEGATED
        assert p.allows_tool("write_file")
        assert not p.allows_tool("deploy")

    def test_operator(self):
        p = OPERATOR_PROFILE
        assert p.authority_class == AuthorityClass.A3_OPERATOR
        assert p.allows_tool("execute")

    def test_autonomous(self):
        p = AUTONOMOUS_PROFILE
        assert p.authority_class == AuthorityClass.A4_AUTONOMOUS
        assert p.audit_level == AuditLevel.FULL

    def test_all_serialize(self):
        for name, profile in BUILTIN_PROFILES.items():
            d = profile.to_dict()
            restored = DeploymentProfile.from_dict(d)
            assert restored.authority_class == profile.authority_class


# ---------------------------------------------------------------------------
# ActionProposal Tests
# ---------------------------------------------------------------------------

class TestActionProposal:
    def test_create(self):
        p = ActionProposal(
            proposal_id="", action="write_file",
            args={"path": "/etc/config"}, severity="S3",
            predicted_effects=["modifies system config"],
            proposed_by="agent_1",
        )
        assert p.proposal_id != ""  # Auto-generated
        assert p.status == ProposalStatus.PENDING

    def test_proposal_hash(self):
        p = ActionProposal(
            proposal_id="p1", action="write_file",
            args={"path": "x"}, severity="S3",
            predicted_effects=[], proposed_by="agent",
        )
        h = p.proposal_hash
        assert len(h) == 16

    def test_approve_and_execute(self):
        p = ActionProposal(
            proposal_id="p1", action="deploy",
            args={}, severity="S3",
            predicted_effects=["deploys"], proposed_by="agent",
        )
        p.approve("user_session_xyz")
        assert p.status == ProposalStatus.APPROVED
        assert p.approved_by == "user_session_xyz"

        assert p.execute()
        assert p.status == ProposalStatus.EXECUTED

    def test_execute_without_approval(self):
        p = ActionProposal(
            proposal_id="p1", action="deploy",
            args={}, severity="S3",
            predicted_effects=[], proposed_by="agent",
        )
        assert not p.execute()

    def test_reject(self):
        p = ActionProposal(
            proposal_id="p1", action="delete",
            args={}, severity="S3",
            predicted_effects=[], proposed_by="agent",
        )
        p.reject()
        assert p.status == ProposalStatus.REJECTED

    def test_expired(self):
        p = ActionProposal(
            proposal_id="p1", action="x", args={}, severity="S3",
            predicted_effects=[], proposed_by="agent",
            ttl_seconds=0, created_at="2020-01-01T00:00:00+00:00",
        )
        assert p.is_expired
        p.approve("user")
        assert p.status == ProposalStatus.EXPIRED

    def test_roundtrip(self):
        p = ActionProposal(
            proposal_id="p1", action="deploy",
            args={"target": "prod"}, severity="S3",
            predicted_effects=["deploy to prod"],
            proposed_by="agent_1",
        )
        restored = ActionProposal.from_dict(p.to_dict())
        assert restored.proposal_id == "p1"
        assert restored.action == "deploy"
        assert restored.severity == "S3"


# ---------------------------------------------------------------------------
# Core Function Tests
# ---------------------------------------------------------------------------

class TestCheckToolAccess:
    def test_allowed(self):
        ok, reason = check_tool_access(OPERATOR_PROFILE, "execute")
        assert ok

    def test_blacklisted(self):
        ok, reason = check_tool_access(PUBLIC_PROFILE, "execute")
        assert not ok
        assert "blacklisted" in reason

    def test_not_whitelisted(self):
        ok, reason = check_tool_access(PUBLIC_PROFILE, "custom_tool")
        assert not ok
        assert "whitelist" in reason


class TestCheckInvariantB:
    def test_valid_token(self):
        t = issue_token({"src/**"}, {"read"}, "run1")
        ok, reason = check_invariant_b(t, "read", "src/main.py")
        assert ok

    def test_expired_token(self):
        t = CapabilityToken(
            id="tok", scope={"*"}, verbs={"read"},
            ttl_seconds=0, bound_to="run1",
            issued_at="2020-01-01T00:00:00+00:00",
        )
        ok, reason = check_invariant_b(t, "read", "anything")
        assert not ok
        assert "expired" in reason

    def test_wrong_verb(self):
        t = issue_token({"*"}, {"read"}, "run1")
        ok, reason = check_invariant_b(t, "write", "file.py")
        assert not ok
        assert "not permit" in reason


class TestCheckInvariantE:
    def test_no_approval_needed(self):
        ok, _ = check_invariant_e(OPERATOR_PROFILE, "S1", None)
        assert ok

    def test_approval_needed_no_proposal(self):
        ok, reason = check_invariant_e(PUBLIC_PROFILE, "S3", None)
        assert not ok
        assert "two-phase" in reason

    def test_approval_with_approved_proposal(self):
        p = propose_action("deploy", {}, "S3", ["deploy"], "agent")
        p.approve("user")
        ok, _ = check_invariant_e(PUBLIC_PROFILE, "S3", p)
        assert ok

    def test_approval_with_pending_proposal(self):
        p = propose_action("deploy", {}, "S3", ["deploy"], "agent")
        ok, reason = check_invariant_e(PUBLIC_PROFILE, "S3", p)
        assert not ok
        assert "pending" in reason


class TestIssueToken:
    def test_creates_token(self):
        t = issue_token({"src/**"}, {"read", "write"}, "run_123")
        assert t.id.startswith("tok_")
        assert t.scope == {"src/**"}
        assert t.bound_to == "run_123"

    def test_custom_rate_limit(self):
        rl = RateLimit(5, 30)
        t = issue_token({"*"}, {"read"}, "run1", rate_limit=rl)
        assert t.rate_limit.max_calls == 5


class TestProposeAction:
    def test_creates_proposal(self):
        p = propose_action("deploy", {"target": "prod"}, "S3",
                           ["deploys to production"], "agent_1")
        assert p.proposal_id != ""
        assert p.status == ProposalStatus.PENDING


# ---------------------------------------------------------------------------
# Store Tests
# ---------------------------------------------------------------------------

class TestDeploymentStore:
    def test_create(self, tmp_path):
        store = DeploymentStore(governor_dir=tmp_path / ".governor")
        assert store.deploy_dir == tmp_path / ".governor" / "deployment"

    def test_list_profiles_builtin(self, tmp_path):
        store = DeploymentStore(governor_dir=tmp_path / ".governor")
        profiles = store.list_profiles()
        assert "public" in profiles
        assert "operator" in profiles

    def test_load_builtin_profile(self, tmp_path):
        store = DeploymentStore(governor_dir=tmp_path / ".governor")
        p = store.load_profile("public")
        assert p is not None
        assert p.authority_class == AuthorityClass.A1_PUBLIC

    def test_save_load_custom_profile(self, tmp_path):
        store = DeploymentStore(governor_dir=tmp_path / ".governor")
        custom = DeploymentProfile(
            authority_class=AuthorityClass.A2_DELEGATED,
            tool_whitelist={"read_file"},
            tool_blacklist=set(),
            max_budget={"explore": 5, "draft": 3, "verify": 2},
            requires_two_phase={"S3"},
            evidence_threshold=0.9,
            audit_level=AuditLevel.ENHANCED,
        )
        store.save_profile("custom", custom)
        loaded = store.load_profile("custom")
        assert loaded is not None
        assert loaded.evidence_threshold == 0.9

    def test_save_load_proposal(self, tmp_path):
        store = DeploymentStore(governor_dir=tmp_path / ".governor")
        p = propose_action("deploy", {}, "S3", ["deploy"], "agent")
        store.save_proposal(p)
        loaded = store.load_proposal(p.proposal_id)
        assert loaded is not None
        assert loaded.action == "deploy"

    def test_list_proposals(self, tmp_path):
        store = DeploymentStore(governor_dir=tmp_path / ".governor")
        p1 = propose_action("a", {}, "S1", [], "agent")
        p2 = propose_action("b", {}, "S2", [], "agent")
        store.save_proposal(p1)
        store.save_proposal(p2)
        proposals = store.list_proposals()
        assert len(proposals) >= 2

    def test_load_missing(self, tmp_path):
        store = DeploymentStore(governor_dir=tmp_path / ".governor")
        assert store.load_profile("nonexistent") is None
        assert store.load_proposal("nonexistent") is None


# ---------------------------------------------------------------------------
# Telemetry Event Tests
# ---------------------------------------------------------------------------

class TestEvents:
    def test_create(self):
        evt = make_deployment_event("profile_activated", {"class": "A2"})
        assert evt["type"] == "deployment"

    def test_minimal(self):
        evt = make_deployment_event("check")
        assert evt["details"] == {}


# ---------------------------------------------------------------------------
# Golden Schema Tests
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_token_schema(self):
        t = issue_token({"*"}, {"read"}, "run1")
        d = t.to_dict()
        required = {"id", "scope", "verbs", "ttl_seconds", "bound_to",
                    "rate_limit", "issued_at"}
        assert required == set(d.keys())

    def test_profile_schema(self):
        d = PUBLIC_PROFILE.to_dict()
        required = {"authority_class", "tool_whitelist", "tool_blacklist",
                    "max_budget", "requires_two_phase", "evidence_threshold",
                    "audit_level"}
        assert required == set(d.keys())

    def test_proposal_schema(self):
        p = propose_action("x", {}, "S1", [], "agent")
        d = p.to_dict()
        required = {"proposal_id", "proposal_hash", "action", "args", "severity",
                    "predicted_effects", "proposed_by", "status", "approved_by",
                    "ttl_seconds", "created_at"}
        assert required == set(d.keys())

    def test_event_schema(self):
        evt = make_deployment_event("test")
        assert set(evt.keys()) == {"type", "action", "details", "ts"}


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_two_phase_commit(self, tmp_path):
        """Propose → approve → execute → persist."""
        store = DeploymentStore(governor_dir=tmp_path / ".governor")
        profile = PUBLIC_PROFILE

        # Check tool access
        ok, _ = check_tool_access(profile, "deploy")
        assert not ok  # deploy is blacklisted for PUBLIC

        # Use operator profile for deploy
        profile = OPERATOR_PROFILE
        ok, _ = check_tool_access(profile, "deploy")
        assert ok

        # Propose S3 action
        proposal = propose_action(
            "deploy", {"target": "staging"}, "S3",
            ["deploys to staging environment"], "agent_1",
        )
        store.save_proposal(proposal)

        # Check invariant E before approval
        ok, reason = check_invariant_e(profile, "S3", proposal)
        assert not ok

        # Approve
        proposal.approve("user_admin")
        store.save_proposal(proposal)

        # Check invariant E after approval
        ok, _ = check_invariant_e(profile, "S3", proposal)
        assert ok

        # Execute
        assert proposal.execute()
        store.save_proposal(proposal)

        # Verify final state
        loaded = store.load_proposal(proposal.proposal_id)
        assert loaded is not None
        assert loaded.status == ProposalStatus.EXECUTED

    def test_token_lifecycle(self):
        """Issue → use → exhaust rate limit."""
        token = issue_token(
            scope={"src/**"}, verbs={"read", "write"},
            bound_to="run_test", ttl_seconds=3600,
            rate_limit=RateLimit(3, 60),
        )

        # Valid uses
        ok, _ = check_invariant_b(token, "read", "src/main.py")
        assert ok
        assert token.consume("read", "src/main.py")
        assert token.consume("write", "src/util.py")
        assert token.consume("read", "src/lib.py")

        # Rate limited
        assert not token.consume("read", "src/extra.py")


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_wildcard_scope(self):
        t = issue_token({"*"}, {"read"}, "run1")
        assert t.permits("read", "anything/at/all")

    def test_empty_scope(self):
        t = CapabilityToken(
            id="tok", scope=set(), verbs={"read"},
            ttl_seconds=3600, bound_to="run1",
        )
        assert not t.permits("read", "file.py")

    def test_store_default_dir(self):
        store = DeploymentStore()
        assert store.governor_dir == Path(".governor")

    def test_proposal_double_execute(self):
        p = propose_action("x", {}, "S1", [], "agent")
        p.approve("user")
        assert p.execute()
        assert not p.execute()  # Already executed
