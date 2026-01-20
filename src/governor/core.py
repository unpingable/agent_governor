"""
AgentGovernor: Main interface for the epistemic governor.

This is the harness that wraps coding agents, enforcing evidence requirements
and maintaining architectural coherence.
"""

from pathlib import Path
from typing import Optional
from uuid import UUID

from .ledger import CodebaseLedger, Commitment, CommitID
from .validators import Validator, CompositeValidator, FileValidator
from .types import Evidence, ProposalResult, ProposalStatus, Contradiction


class AgentGovernor:
    """
    The epistemic governor for agentic coding.
    
    Sits between the agent and the codebase, enforcing:
    - Evidence requirements (no hallucinated APIs)
    - Architectural coherence (no contradicting past decisions)
    - Provenance tracking (why was this decision made?)
    
    Usage:
        governor = AgentGovernor("/path/to/repo")
        
        # Agent proposes a change
        result = governor.propose(
            claim="Using React for frontend",
            topic="framework",
            paths=["package.json", "src/App.jsx"]
        )
        
        if result.accepted:
            # Proceed with the change
            pass
        else:
            # Handle rejection
            print(f"Rejected: {result.rejection_reason}")
    """
    
    def __init__(
        self,
        git_root: str | Path,
        validators: Optional[list[Validator]] = None,
    ):
        self.git_root = Path(git_root)
        self.ledger = CodebaseLedger(self.git_root)
        
        # Default to file validator if none provided
        if validators is None:
            validators = [FileValidator(self.git_root)]
        
        self.validator = CompositeValidator(validators)
    
    def propose(
        self,
        claim: str,
        topic: str,
        evidence: Optional[Evidence] = None,
        supersedes: Optional[CommitID] = None,
        **validation_kwargs,
    ) -> ProposalResult:
        """
        Propose a change/claim to the governor.
        
        The governor will:
        1. Check for contradictions with existing commitments
        2. Validate evidence (or attempt to gather it)
        3. Either commit to ledger or reject with reason
        
        Args:
            claim: The architectural claim/decision being made
            topic: Category for the claim (framework, api, pattern, etc.)
            evidence: Pre-validated evidence, if available
            supersedes: If this explicitly revises a prior commitment
            **validation_kwargs: Arguments passed to validators (e.g., paths=[...])
        
        Returns:
            ProposalResult with status, evidence, and any contradiction info
        """
        # Step 1: Check for contradictions (unless explicitly superseding)
        if not supersedes:
            contradiction = self.ledger.check_contradiction(claim, topic)
            if contradiction:
                self.ledger.record_rejection(
                    claim=claim,
                    reason=str(contradiction),
                    contradiction=contradiction,
                )
                return ProposalResult(
                    status=ProposalStatus.REJECTED,
                    claim=claim,
                    contradiction=contradiction,
                    rejection_reason=f"Contradicts existing commitment: {contradiction.existing_claim}",
                )
        
        # Step 2: Validate or use provided evidence
        if evidence is None:
            if self.validator.can_handle(claim, **validation_kwargs):
                evidence = self.validator.validate(claim, **validation_kwargs)
        
        # Step 3: Reject if no evidence
        if evidence is None:
            reason = "No evidence provided and validators could not verify claim"
            self.ledger.record_rejection(claim=claim, reason=reason)
            return ProposalResult(
                status=ProposalStatus.REJECTED,
                claim=claim,
                rejection_reason=reason,
            )
        
        # Step 4: Commit to ledger
        commit_id = self.ledger.commit(
            claim=claim,
            evidence=evidence,
            topic=topic,
            supersedes=supersedes,
        )
        
        return ProposalResult(
            status=ProposalStatus.COMMITTED,
            claim=claim,
            evidence=evidence,
            commit_id=commit_id,
        )
    
    def query(self, topic: Optional[str] = None) -> list[Commitment]:
        """
        Query existing commitments for context.
        
        Use this to give agents architectural context before they propose changes.
        
        Args:
            topic: Optional topic filter (framework, api, pattern, etc.)
        
        Returns:
            List of active commitments, newest first
        """
        return self.ledger.query(topic)
    
    def get_context(self, topics: Optional[list[str]] = None) -> str:
        """
        Get a formatted context string for agent prompts.
        
        This returns the architectural decisions an agent should know about
        before making changes.
        
        Args:
            topics: List of topics to include (None = all)
        
        Returns:
            Formatted string suitable for injection into agent prompts
        """
        if topics is None:
            commitments = self.ledger.query()
        else:
            commitments = []
            for topic in topics:
                commitments.extend(self.ledger.query(topic))
        
        if not commitments:
            return "No architectural commitments recorded yet."
        
        lines = ["## Architectural Commitments", ""]
        
        # Group by topic
        by_topic: dict[str, list[Commitment]] = {}
        for c in commitments:
            by_topic.setdefault(c.topic, []).append(c)
        
        for topic, topic_commitments in sorted(by_topic.items()):
            lines.append(f"### {topic.title()}")
            for c in topic_commitments:
                lines.append(f"- {c.claim}")
                lines.append(f"  (evidence: {c.evidence.type} from {c.evidence.source})")
            lines.append("")
        
        return "\n".join(lines)
    
    def check_consistency(self, claims: list[tuple[str, str]]) -> list[Contradiction]:
        """
        Check multiple claims for consistency with existing commitments.
        
        Useful for batch-checking a proposed PR or set of changes.
        
        Args:
            claims: List of (claim, topic) tuples
        
        Returns:
            List of contradictions found (empty if all consistent)
        """
        contradictions = []
        for claim, topic in claims:
            contradiction = self.ledger.check_contradiction(claim, topic)
            if contradiction:
                contradictions.append(contradiction)
        return contradictions
    
    def revise(
        self,
        old_commit_id: CommitID,
        new_claim: str,
        evidence: Evidence,
    ) -> ProposalResult:
        """
        Explicitly revise a prior commitment.
        
        This is the proper way to change an architectural decision -
        not by contradicting silently, but by explicit supersession.
        
        Args:
            old_commit_id: The commitment being revised
            new_claim: The new claim replacing the old one
            evidence: Evidence for the new claim
        
        Returns:
            ProposalResult for the revision
        """
        old_commitment = self.ledger.get_commitment(old_commit_id)
        if old_commitment is None:
            return ProposalResult(
                status=ProposalStatus.REJECTED,
                claim=new_claim,
                rejection_reason=f"Cannot revise: commitment {old_commit_id} not found",
            )
        
        return self.propose(
            claim=new_claim,
            topic=old_commitment.topic,
            evidence=evidence,
            supersedes=old_commit_id,
        )
    
    @property
    def stats(self) -> dict:
        """Get telemetry stats for the governor."""
        return {
            "total_commitments": self.ledger.commitment_count,
            "total_rejections": self.ledger.rejection_count,
            "rejection_rate": (
                self.ledger.rejection_count / 
                (self.ledger.commitment_count + self.ledger.rejection_count)
                if (self.ledger.commitment_count + self.ledger.rejection_count) > 0
                else 0.0
            ),
        }
    
    def get_rejection_log(self, limit: int = 50) -> list[dict]:
        """
        Get recent rejections for debugging.
        
        This is your "47 times Claude Code tried to hallucinate an API" proof.
        """
        rejections = self.ledger.get_rejections(limit)
        return [
            {
                "claim": r.claim,
                "reason": r.reason,
                "timestamp": r.timestamp.isoformat(),
            }
            for r in rejections
        ]
