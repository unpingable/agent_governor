"""
Cooperative redundancy: independence scoring for quorum votes.

Ensures that agreement from multiple agents actually represents diverse
verification paths, not just the same pipeline run N times.

Key invariants:
1. Independence score = 1 - max_pairwise_jaccard over method signatures
2. A vote without hash fields cannot contribute to independence scoring
3. Same source URLs from different agents ≠ independent
4. At least two distinct sources_hash OR different tool+sources required
5. Single signature → score 0.0 (no redundancy)

Method signature features per agent:
- tool_path_hash: tools/pipeline used
- sources_hash: documents/domains consulted
- prompt_hash: prompt template used
- model_tier: model class (local/fast/standard/heavy)
"""

from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Method Signature
# =============================================================================


@dataclass(frozen=True)
class MethodSignature:
    """
    Describes the verification method used by an agent.

    Each field captures a different axis of independence.
    """

    agent_id: str
    tool_path_hash: str
    sources_hash: str
    prompt_hash: str
    model_tier: str = "standard"
    source_urls: frozenset[str] = frozenset()

    @property
    def feature_set(self) -> frozenset[str]:
        """Feature set for Jaccard similarity."""
        return frozenset({
            f"tool:{self.tool_path_hash}",
            f"sources:{self.sources_hash}",
            f"prompt:{self.prompt_hash}",
            f"tier:{self.model_tier}",
        })

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "tool_path_hash": self.tool_path_hash,
            "sources_hash": self.sources_hash,
            "prompt_hash": self.prompt_hash,
            "model_tier": self.model_tier,
            "source_urls": sorted(self.source_urls),
        }

    @classmethod
    def from_vote(cls, vote: Any) -> "MethodSignature | None":
        """
        Create a MethodSignature from a Vote object.

        Returns None if the vote lacks the required hash fields.
        """
        if (vote.tool_path_hash is None
                or vote.sources_hash is None
                or vote.prompt_hash is None):
            return None
        return cls(
            agent_id=vote.agent_id,
            tool_path_hash=vote.tool_path_hash,
            sources_hash=vote.sources_hash,
            prompt_hash=vote.prompt_hash,
        )


# =============================================================================
# Scoring Functions
# =============================================================================


def pairwise_jaccard(sig_a: MethodSignature, sig_b: MethodSignature) -> float:
    """
    Compute Jaccard similarity between two method signatures.

    |A∩B| / |A∪B| over feature sets. Returns 0.0 if both empty.
    """
    a = sig_a.feature_set
    b = sig_b.feature_set
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def independence_score(signatures: list[MethodSignature]) -> float:
    """
    Compute independence score for a set of method signatures.

    Returns 1 - max_pairwise_jaccard.
    Single or empty → 0.0 (no redundancy to measure).
    """
    if len(signatures) < 2:
        return 0.0

    max_jaccard = 0.0
    for i in range(len(signatures)):
        for j in range(i + 1, len(signatures)):
            j_score = pairwise_jaccard(signatures[i], signatures[j])
            if j_score > max_jaccard:
                max_jaccard = j_score

    return 1.0 - max_jaccard


def is_independent_support(sig_a: MethodSignature, sig_b: MethodSignature) -> bool:
    """
    Check if two signatures represent genuinely independent verification.

    Requirements:
    - At least 2 distinct sources_hash OR (tool_path differs AND sources differ)
    - Anti-cheat: same source_urls → not independent
    """
    # Anti-cheat: if both have source_urls and they overlap significantly
    if sig_a.source_urls and sig_b.source_urls:
        overlap = sig_a.source_urls & sig_b.source_urls
        if overlap:
            return False

    # Check for distinct sources
    distinct_sources = sig_a.sources_hash != sig_b.sources_hash

    # Check for different tools AND different sources
    distinct_tools = sig_a.tool_path_hash != sig_b.tool_path_hash

    # At least two distinct sources_hash OR (tool differs AND sources differ)
    return distinct_sources or (distinct_tools and distinct_sources)


# =============================================================================
# Independence Result
# =============================================================================


@dataclass
class IndependenceResult:
    """Result of independence scoring for a set of votes."""

    score: float
    independent_count: int
    total_signatures: int
    violations: list[str]
    pairwise_scores: list[tuple[str, str, float]]
    passes_threshold: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "independent_count": self.independent_count,
            "total_signatures": self.total_signatures,
            "violations": self.violations,
            "pairwise_scores": [
                {"agent_a": a, "agent_b": b, "jaccard": s}
                for a, b, s in self.pairwise_scores
            ],
            "passes_threshold": self.passes_threshold,
        }


# =============================================================================
# Independence Scorer
# =============================================================================


class IndependenceScorer:
    """
    Scores independence of agent votes for quorum validation.

    Extracts method signatures from votes, computes pairwise independence,
    and checks against a threshold.
    """

    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold

    def score_votes(self, votes: list[Any]) -> IndependenceResult:
        """
        Score the independence of a set of votes.

        Extracts MethodSignatures from votes that have hash fields,
        computes pairwise Jaccard scores, and determines if the
        independence threshold is met.
        """
        sigs = self._extract_signatures(votes)
        violations = self.check_anti_cheat(sigs)
        score = independence_score(sigs)
        pairs = self._compute_pairwise(sigs)
        indep_count = self.count_independent_supports(votes)

        return IndependenceResult(
            score=score,
            independent_count=indep_count,
            total_signatures=len(sigs),
            violations=violations,
            pairwise_scores=pairs,
            passes_threshold=score >= self.threshold and len(violations) == 0,
        )

    def count_independent_supports(self, votes: list[Any]) -> int:
        """
        Count the number of genuinely independent support votes.

        Uses is_independent_support pairwise check.
        """
        sigs = self._extract_signatures(votes)
        if len(sigs) < 2:
            return len(sigs)

        # Build independence graph: sig is independent if it's independent
        # from at least one other sig
        independent = set()
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                if is_independent_support(sigs[i], sigs[j]):
                    independent.add(i)
                    independent.add(j)

        return len(independent) if independent else (1 if sigs else 0)

    def check_anti_cheat(self, sigs: list[MethodSignature]) -> list[str]:
        """
        Check for anti-cheat violations (same source URLs across agents).
        """
        violations: list[str] = []
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                if sigs[i].source_urls and sigs[j].source_urls:
                    overlap = sigs[i].source_urls & sigs[j].source_urls
                    if overlap:
                        violations.append(
                            f"Agents {sigs[i].agent_id} and {sigs[j].agent_id} "
                            f"share source URLs: {sorted(overlap)}"
                        )
        return violations

    def _extract_signatures(self, votes: list[Any]) -> list[MethodSignature]:
        """Extract MethodSignatures from votes that have hash fields."""
        sigs = []
        for v in votes:
            sig = MethodSignature.from_vote(v)
            if sig is not None:
                sigs.append(sig)
        return sigs

    def _compute_pairwise(
        self, sigs: list[MethodSignature]
    ) -> list[tuple[str, str, float]]:
        """Compute all pairwise Jaccard scores."""
        pairs: list[tuple[str, str, float]] = []
        for i in range(len(sigs)):
            for j in range(i + 1, len(sigs)):
                score = pairwise_jaccard(sigs[i], sigs[j])
                pairs.append((sigs[i].agent_id, sigs[j].agent_id, score))
        return pairs
