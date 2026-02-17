# SPDX-License-Identifier: Apache-2.0
"""Tests for the agent governor."""

import tempfile
from pathlib import Path

import pytest

from governor import AgentGovernor, Evidence
from governor.types import ProposalStatus


@pytest.fixture
def project_dir():
    """Create a temporary project directory with some files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create basic project structure
        (root / "package.json").write_text('{"dependencies": {"react": "^18.0.0"}}')
        (root / "src").mkdir()
        (root / "src" / "App.jsx").write_text("export default function App() {}")
        (root / "src" / "api.ts").write_text("export const API_URL = '/api/v1';")
        
        yield root


@pytest.fixture
def governor(project_dir):
    """Create a governor for the test project."""
    return AgentGovernor(project_dir)


class TestBasicProposals:
    """Test basic propose/commit flow."""
    
    def test_valid_proposal_with_existing_files(self, governor, project_dir):
        """Proposal with valid file evidence should be committed."""
        result = governor.propose(
            claim="Using React for frontend",
            topic="framework",
            paths=["package.json", "src/App.jsx"],
        )
        
        assert result.accepted
        assert result.status == ProposalStatus.COMMITTED
        assert result.evidence is not None
        assert result.evidence.type == "file_exists"
        assert result.commit_id is not None
    
    def test_invalid_proposal_missing_file(self, governor):
        """Proposal citing non-existent file should be rejected."""
        result = governor.propose(
            claim="API defined in api/users.py",
            topic="api",
            paths=["api/users.py"],  # Does not exist
        )
        
        assert result.rejected
        assert result.status == ProposalStatus.REJECTED
        assert "validators could not verify" in result.rejection_reason
    
    def test_proposal_with_explicit_evidence(self, governor):
        """Proposal with pre-validated evidence should be committed."""
        evidence = Evidence(
            type="manual_verification",
            source="human confirmed",
        )
        
        result = governor.propose(
            claim="Database schema is finalized",
            topic="database",
            evidence=evidence,
        )
        
        assert result.accepted
        assert result.evidence == evidence


class TestContradictionDetection:
    """Test that contradictions are properly caught."""
    
    def test_framework_contradiction(self, governor, project_dir):
        """Can't commit to Vue after committing to React."""
        # First, commit to React
        result1 = governor.propose(
            claim="Using React for frontend",
            topic="framework",
            paths=["package.json"],
        )
        assert result1.accepted
        
        # Create a Vue file so file validation passes
        (project_dir / "src" / "App.vue").write_text("<template></template>")
        
        # Try to commit to Vue
        result2 = governor.propose(
            claim="Using Vue for frontend",
            topic="framework",
            paths=["src/App.vue"],
        )
        
        assert result2.rejected
        assert result2.contradiction is not None
        assert "React" in result2.contradiction.existing_claim
    
    def test_explicit_revision_allowed(self, governor, project_dir):
        """Explicit revision of prior commitment should work."""
        # Commit to React
        result1 = governor.propose(
            claim="Using React for frontend",
            topic="framework",
            paths=["package.json"],
        )
        assert result1.accepted
        
        # Create Vue file
        (project_dir / "src" / "App.vue").write_text("<template></template>")
        
        # Explicitly revise
        result2 = governor.revise(
            old_commit_id=result1.commit_id,
            new_claim="Migrating to Vue for frontend",
            evidence=Evidence(
                type="file_exists",
                source="src/App.vue",
            ),
        )
        
        assert result2.accepted


class TestLedgerQueries:
    """Test querying the ledger for context."""
    
    def test_query_by_topic(self, governor, project_dir):
        """Can query commitments by topic."""
        # Make some commitments
        governor.propose(
            claim="Using React",
            topic="framework",
            paths=["package.json"],
        )
        governor.propose(
            claim="API uses REST",
            topic="api",
            paths=["src/api.ts"],
        )
        
        # Query by topic
        framework_commits = governor.query(topic="framework")
        assert len(framework_commits) == 1
        assert "React" in framework_commits[0].claim
        
        api_commits = governor.query(topic="api")
        assert len(api_commits) == 1
        assert "REST" in api_commits[0].claim
    
    def test_get_context_formats_nicely(self, governor, project_dir):
        """Context string should be formatted for agent prompts."""
        governor.propose(
            claim="Using React for UI",
            topic="framework",
            paths=["package.json"],
        )
        
        context = governor.get_context()
        
        assert "## Architectural Commitments" in context
        assert "### Framework" in context
        assert "React" in context


class TestRejectionLogging:
    """Test that rejections are properly logged."""
    
    def test_rejections_are_logged(self, governor):
        """Rejected proposals should appear in rejection log."""
        # Make some failed proposals
        governor.propose(
            claim="File X exists",
            topic="api",
            paths=["nonexistent.py"],
        )
        governor.propose(
            claim="File Y exists",
            topic="api",
            paths=["also_nonexistent.py"],
        )
        
        rejections = governor.get_rejection_log()
        
        assert len(rejections) == 2
        assert "File X" in rejections[0]["claim"] or "File X" in rejections[1]["claim"]
    
    def test_stats_track_rejection_rate(self, governor, project_dir):
        """Stats should accurately track rejection rate."""
        # One success
        governor.propose(
            claim="React is used",
            topic="framework",
            paths=["package.json"],
        )
        
        # Two failures
        governor.propose(claim="X", topic="api", paths=["x.py"])
        governor.propose(claim="Y", topic="api", paths=["y.py"])
        
        stats = governor.stats
        
        assert stats["total_commitments"] == 1
        assert stats["total_rejections"] == 2
        assert 0.6 < stats["rejection_rate"] < 0.7  # ~66%


class TestNLAIEnforcement:
    """Test that NLAI is enforced - model output can't be evidence."""
    
    def test_model_output_rejected_as_evidence(self):
        """Evidence type 'model_output' should raise error."""
        with pytest.raises(ValueError, match="violates NLAI"):
            Evidence(
                type="model_output",
                source="Claude said so",
            )
    
    def test_self_consistency_rejected_as_evidence(self):
        """Evidence type 'self_consistency' should raise error."""
        with pytest.raises(ValueError, match="violates NLAI"):
            Evidence(
                type="self_consistency",
                source="Model agreed with itself",
            )
