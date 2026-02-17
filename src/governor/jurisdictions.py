# SPDX-License-Identifier: Apache-2.0
"""
Jurisdictions: Context-Aware Epistemic Governance

A jurisdiction defines the epistemic rules for a particular reasoning context.
Different contexts have different:
- Evidence admissibility rules (what counts as evidence)
- Budget profiles (what operations cost)
- Spillover policies (what can cross boundaries)
- Contradiction tolerance (when conflicts matter)
- Closure rules (whether/how claims can be committed)

This is not "adding features" - it's recognizing that human cognition already
operates in mode-separated regimes, and we rely on social context to enforce
boundaries. LLMs collapse all of that into one slurry unless you stop them.

Each jurisdiction is a parameter configuration of the base governor.
The architecture doesn't change; the rules do.

Key insight: The same claim ("X is true") has different epistemic status
depending on whether you're in FACTUAL mode (requires hard evidence),
SPECULATIVE mode (provisional exploration), or ADVERSARIAL mode (stress testing).
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .epistemic import EvidenceType


class SpilloverPolicy(str, Enum):
    """How claims can cross jurisdiction boundaries."""

    BLOCKED = "blocked"
    """No export allowed - claims stay in this jurisdiction."""

    PROMOTED_WITH_EVIDENCE = "promoted_with_evidence"
    """Can export but requires evidence to promote."""

    FLAGGED_EXPORT = "flagged_export"
    """Can export but marked with origin jurisdiction."""

    FREE = "free"
    """No restrictions on export (use with caution)."""


class ContradictionPolicy(str, Enum):
    """How contradictions are handled in this jurisdiction."""

    STRICT = "strict"
    """Contradictions block operations - must be resolved."""

    TOLERANT = "tolerant"
    """Contradictions logged but don't block operations."""

    EXPECTED = "expected"
    """Contradictions are normal (adversarial mode)."""

    SCOPED = "scoped"
    """Only same-scope contradictions matter (counterfactual mode)."""


@dataclass
class BudgetProfile:
    """
    Cost structure for operations in this jurisdiction.

    Budget is a soft constraint - operations consume budget, and when
    budget is depleted, the system pushes back. Different jurisdictions
    have different cost structures to encourage/discourage behaviors.
    """

    claim_cost: float = 1.0
    """Cost to assert a claim."""

    contradiction_cost: float = 2.0
    """Cost to open a contradiction."""

    resolution_cost: float = 5.0
    """Cost to close/resolve a contradiction."""

    export_cost: float = 10.0
    """Cost to export claim to factual jurisdiction."""

    refill_rate: float = 1.0
    """Budget recovery per turn."""

    # Multipliers for operation discounts
    speculative_discount: float = 1.0
    """Multiplier for speculative claims (< 1.0 = cheaper)."""

    adversarial_discount: float = 1.0
    """Multiplier for adversarial claims (< 1.0 = cheaper)."""

    def effective_claim_cost(self, is_speculative: bool = False, is_adversarial: bool = False) -> float:
        """Get effective claim cost with discounts applied."""
        cost = self.claim_cost
        if is_speculative:
            cost *= self.speculative_discount
        if is_adversarial:
            cost *= self.adversarial_discount
        return cost

    def to_dict(self) -> dict[str, float]:
        """Serialize to dictionary."""
        return {
            "claim_cost": self.claim_cost,
            "contradiction_cost": self.contradiction_cost,
            "resolution_cost": self.resolution_cost,
            "export_cost": self.export_cost,
            "refill_rate": self.refill_rate,
            "speculative_discount": self.speculative_discount,
            "adversarial_discount": self.adversarial_discount,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BudgetProfile":
        """Deserialize from dictionary."""
        return cls(
            claim_cost=data.get("claim_cost", 1.0),
            contradiction_cost=data.get("contradiction_cost", 2.0),
            resolution_cost=data.get("resolution_cost", 5.0),
            export_cost=data.get("export_cost", 10.0),
            refill_rate=data.get("refill_rate", 1.0),
            speculative_discount=data.get("speculative_discount", 1.0),
            adversarial_discount=data.get("adversarial_discount", 1.0),
        )


@dataclass
class Jurisdiction:
    """
    Base jurisdiction configuration.

    Each jurisdiction defines the epistemic rules for a reasoning context.
    Different contexts (factual, speculative, adversarial, etc.) have
    different rules about what evidence counts, how contradictions are
    handled, and whether claims can be committed or exported.
    """

    name: str
    """Unique identifier for this jurisdiction."""

    description: str
    """Human-readable description of the jurisdiction's purpose."""

    # Evidence admissibility
    admissible_evidence: set[EvidenceType] = field(default_factory=lambda: {
        EvidenceType.TOOL_TRACE,
        EvidenceType.DOCUMENT,
        EvidenceType.HUMAN_INPUT,
        EvidenceType.RECEIPT,
    })
    """Set of evidence types that are admissible in this jurisdiction."""

    # Budget configuration
    budget: BudgetProfile = field(default_factory=BudgetProfile)
    """Cost structure for operations."""

    # Spillover policy
    spillover: SpilloverPolicy = SpilloverPolicy.BLOCKED
    """How claims can cross jurisdiction boundaries."""

    # Contradiction handling
    contradiction_policy: ContradictionPolicy = ContradictionPolicy.STRICT
    """How contradictions are handled."""

    contradiction_tolerance: float = 0.0
    """Tolerance level: 0 = no tolerance, 1 = full tolerance."""

    # Closure rules
    closure_allowed: bool = True
    """Whether claims can be committed/closed in this jurisdiction."""

    closure_requires_evidence: bool = True
    """Whether closure requires evidence."""

    # Export rules
    export_to_factual_allowed: bool = False
    """Whether claims can be exported to factual jurisdiction."""

    export_requires_promotion: bool = True
    """Whether export requires evidence-based promotion."""

    # Labeling
    output_label: str | None = None
    """Label to apply to outputs (e.g., '[SPECULATIVE]')."""

    def admits(self, evidence_type: EvidenceType) -> bool:
        """Check if this evidence type is admissible."""
        return evidence_type in self.admissible_evidence

    def can_close(self, has_evidence: bool) -> bool:
        """Check if closure is allowed given evidence status."""
        if not self.closure_allowed:
            return False
        if self.closure_requires_evidence and not has_evidence:
            return False
        return True

    def can_export(self, has_promotion_evidence: bool) -> bool:
        """Check if claims can be exported to factual jurisdiction."""
        if not self.export_to_factual_allowed:
            return False
        if self.export_requires_promotion and not has_promotion_evidence:
            return False
        return True

    def tolerates_contradiction(self) -> bool:
        """Check if contradictions are tolerated (not blocked)."""
        return self.contradiction_policy in (
            ContradictionPolicy.TOLERANT,
            ContradictionPolicy.EXPECTED,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "admissible_evidence": [e.value for e in self.admissible_evidence],
            "budget": self.budget.to_dict(),
            "spillover": self.spillover.value,
            "contradiction_policy": self.contradiction_policy.value,
            "contradiction_tolerance": self.contradiction_tolerance,
            "closure_allowed": self.closure_allowed,
            "closure_requires_evidence": self.closure_requires_evidence,
            "export_to_factual_allowed": self.export_to_factual_allowed,
            "export_requires_promotion": self.export_requires_promotion,
            "output_label": self.output_label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Jurisdiction":
        """Deserialize from dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            admissible_evidence={EvidenceType(e) for e in data.get("admissible_evidence", [])},
            budget=BudgetProfile.from_dict(data.get("budget", {})),
            spillover=SpilloverPolicy(data.get("spillover", "blocked")),
            contradiction_policy=ContradictionPolicy(data.get("contradiction_policy", "strict")),
            contradiction_tolerance=data.get("contradiction_tolerance", 0.0),
            closure_allowed=data.get("closure_allowed", True),
            closure_requires_evidence=data.get("closure_requires_evidence", True),
            export_to_factual_allowed=data.get("export_to_factual_allowed", False),
            export_requires_promotion=data.get("export_requires_promotion", True),
            output_label=data.get("output_label"),
        )


# =============================================================================
# Standard Jurisdictions
# =============================================================================


def create_factual_jurisdiction() -> Jurisdiction:
    """
    Factual jurisdiction - strict epistemic mode.

    The default, high-evidence, low-tolerance mode.
    - Only hard evidence admitted
    - Contradictions block operations
    - Closure requires evidence
    - Claims can flow freely (this IS the factual record)
    """
    return Jurisdiction(
        name="factual",
        description="Strict epistemic mode. Evidence required. Contradictions block.",
        admissible_evidence={
            EvidenceType.TOOL_TRACE,
            EvidenceType.SENSOR_DATA,
            EvidenceType.HUMAN_INPUT,
            EvidenceType.DOCUMENT,
            EvidenceType.RECEIPT,
            EvidenceType.CRYPTOGRAPHIC_PROOF,
            EvidenceType.CALC_RESULT,
            EvidenceType.TEST_RESULT,
            EvidenceType.WEB_SOURCE,
            EvidenceType.LIVE_RETRIEVAL,
        },
        budget=BudgetProfile(
            claim_cost=1.0,
            contradiction_cost=2.0,
            resolution_cost=5.0,
            export_cost=0.0,  # Already factual
            refill_rate=1.0,
        ),
        spillover=SpilloverPolicy.FREE,  # Factual claims can go anywhere
        contradiction_policy=ContradictionPolicy.STRICT,
        contradiction_tolerance=0.0,
        closure_allowed=True,
        closure_requires_evidence=True,
        export_to_factual_allowed=True,  # Already factual
        export_requires_promotion=False,
        output_label=None,
    )


def create_speculative_jurisdiction() -> Jurisdiction:
    """
    Speculative jurisdiction - "what if..." mode.

    Provisional exploration without commitment.
    - Claims are explicitly provisional
    - Contradictions tolerated
    - No closure allowed
    - Export requires evidence promotion
    """
    return Jurisdiction(
        name="speculative",
        description="Provisional claims. No closure. Exploration mode.",
        admissible_evidence={
            EvidenceType.TOOL_TRACE,
            EvidenceType.HUMAN_INPUT,
            EvidenceType.URL,
            EvidenceType.WEB_SOURCE,
            # Lower bar - even weak evidence can inform speculation
        },
        budget=BudgetProfile(
            claim_cost=0.5,  # Cheap to speculate
            contradiction_cost=0.5,  # Contradictions are fine
            resolution_cost=0.0,  # Can't resolve anyway
            export_cost=10.0,  # Expensive to promote to factual
            refill_rate=2.0,  # Fast recovery for exploration
            speculative_discount=0.5,
        ),
        spillover=SpilloverPolicy.PROMOTED_WITH_EVIDENCE,
        contradiction_policy=ContradictionPolicy.TOLERANT,
        contradiction_tolerance=0.8,
        closure_allowed=False,  # KEY: Cannot commit in speculation mode
        closure_requires_evidence=True,
        export_to_factual_allowed=True,
        export_requires_promotion=True,
        output_label="[SPECULATIVE]",
    )


def create_counterfactual_jurisdiction() -> Jurisdiction:
    """
    Counterfactual jurisdiction - "assume X, then..." mode.

    Hypothetical reasoning with explicit premises.
    - Claims scoped to a premise
    - Contradictions only matter within same scope
    - Closure allowed within scope
    - Export blocked
    """
    return Jurisdiction(
        name="counterfactual",
        description="Hypothetical reasoning. Premise-scoped. Scoped contradictions.",
        admissible_evidence={
            EvidenceType.TOOL_TRACE,
            EvidenceType.HUMAN_INPUT,
            EvidenceType.DOCUMENT,
        },
        budget=BudgetProfile(
            claim_cost=0.7,
            contradiction_cost=1.0,  # Contradictions matter within scope
            resolution_cost=3.0,
            export_cost=20.0,  # Very expensive to export
            refill_rate=1.5,
        ),
        spillover=SpilloverPolicy.BLOCKED,
        contradiction_policy=ContradictionPolicy.SCOPED,
        contradiction_tolerance=0.5,
        closure_allowed=True,  # Within scope
        closure_requires_evidence=False,  # Premise is the evidence
        export_to_factual_allowed=False,
        export_requires_promotion=True,
        output_label="[COUNTERFACTUAL]",
    )


def create_adversarial_jurisdiction() -> Jurisdiction:
    """
    Adversarial jurisdiction - devil's advocate mode.

    Argue the wrong thing on purpose.
    - Claims marked as adversarial (not endorsed)
    - Contradictions are expected
    - Resolution forbidden
    - Export blocked
    """
    return Jurisdiction(
        name="adversarial",
        description="Devil's advocate. Contradictions expected. Resolution forbidden.",
        admissible_evidence={
            EvidenceType.TOOL_TRACE,
            EvidenceType.HUMAN_INPUT,
            EvidenceType.DOCUMENT,
            EvidenceType.URL,
            EvidenceType.WEB_SOURCE,
            EvidenceType.CALC_RESULT,
            EvidenceType.TEST_RESULT,
        },
        budget=BudgetProfile(
            claim_cost=0.1,  # Nearly free to argue
            contradiction_cost=0.1,  # Contradictions are the point
            resolution_cost=100.0,  # KEY: Resolution blocked by cost
            export_cost=100.0,  # Cannot export
            refill_rate=5.0,  # High throughput for stress testing
            adversarial_discount=0.1,
        ),
        spillover=SpilloverPolicy.BLOCKED,
        contradiction_policy=ContradictionPolicy.EXPECTED,
        contradiction_tolerance=1.0,  # Full tolerance
        closure_allowed=False,  # Cannot resolve in adversarial mode
        closure_requires_evidence=True,
        export_to_factual_allowed=False,
        export_requires_promotion=True,
        output_label="[ADVERSARIAL - NOT ENDORSED]",
    )


def create_narrative_jurisdiction() -> Jurisdiction:
    """
    Narrative jurisdiction - fiction/story mode.

    Story-internal logic where consistency is key.
    - Narrative consistency is admissible evidence
    - Contradictions matter (plot holes)
    - Closure allowed
    - Export blocked
    """
    return Jurisdiction(
        name="narrative",
        description="Fiction mode. Story-internal consistency. Plot holes matter.",
        admissible_evidence={
            EvidenceType.NARRATIVE_CONSISTENCY,
            EvidenceType.HUMAN_INPUT,
            EvidenceType.DOCUMENT,
        },
        budget=BudgetProfile(
            claim_cost=0.3,
            contradiction_cost=3.0,  # Plot holes are expensive
            resolution_cost=2.0,  # But can be fixed
            export_cost=50.0,
            refill_rate=2.0,
        ),
        spillover=SpilloverPolicy.BLOCKED,
        contradiction_policy=ContradictionPolicy.STRICT,  # Plot consistency matters
        contradiction_tolerance=0.1,
        closure_allowed=True,  # Canon can be established
        closure_requires_evidence=True,  # Needs narrative consistency
        export_to_factual_allowed=False,
        export_requires_promotion=True,
        output_label="[FICTION]",
    )


def create_forensic_jurisdiction() -> Jurisdiction:
    """
    Forensic jurisdiction - investigation mode.

    Cross-source corroboration required.
    - Multiple sources needed
    - Contradictions are clues
    - Strict closure requirements
    - Flagged export
    """
    return Jurisdiction(
        name="forensic",
        description="Investigation mode. Cross-source corroboration required.",
        admissible_evidence={
            EvidenceType.TOOL_TRACE,
            EvidenceType.DOCUMENT,
            EvidenceType.CROSS_SOURCE,
            EvidenceType.RECEIPT,
            EvidenceType.SENSOR_DATA,
            EvidenceType.WEB_SOURCE,
            EvidenceType.LIVE_RETRIEVAL,
        },
        budget=BudgetProfile(
            claim_cost=2.0,  # Claims are expensive - need evidence
            contradiction_cost=0.5,  # Contradictions are clues
            resolution_cost=10.0,  # Hard to resolve
            export_cost=5.0,
            refill_rate=0.5,  # Slow - careful work
        ),
        spillover=SpilloverPolicy.FLAGGED_EXPORT,
        contradiction_policy=ContradictionPolicy.TOLERANT,  # Contradictions are data
        contradiction_tolerance=0.6,
        closure_allowed=True,
        closure_requires_evidence=True,  # Cross-source required
        export_to_factual_allowed=True,
        export_requires_promotion=True,
        output_label="[FORENSIC]",
    )


def create_pedagogical_jurisdiction() -> Jurisdiction:
    """
    Pedagogical jurisdiction - teaching mode.

    Known simplifications for learning.
    - Pedagogical framing is valid evidence
    - Contradictions (with deeper truth) tolerated
    - Closure allowed for learning artifacts
    - Flagged export
    """
    return Jurisdiction(
        name="pedagogical",
        description="Teaching mode. Known simplifications. Learning artifacts.",
        admissible_evidence={
            EvidenceType.PEDAGOGICAL_FRAME,
            EvidenceType.HUMAN_INPUT,
            EvidenceType.DOCUMENT,
            EvidenceType.TOOL_TRACE,
        },
        budget=BudgetProfile(
            claim_cost=0.3,
            contradiction_cost=1.0,
            resolution_cost=2.0,
            export_cost=5.0,
            refill_rate=2.0,
        ),
        spillover=SpilloverPolicy.FLAGGED_EXPORT,
        contradiction_policy=ContradictionPolicy.TOLERANT,
        contradiction_tolerance=0.7,  # Simplifications may contradict deeper truth
        closure_allowed=True,
        closure_requires_evidence=True,
        export_to_factual_allowed=True,
        export_requires_promotion=True,
        output_label="[PEDAGOGICAL - SIMPLIFIED]",
    )


def create_audit_jurisdiction() -> Jurisdiction:
    """
    Audit jurisdiction - maximum transparency mode.

    Full trail, everything recorded.
    - All evidence types considered
    - Contradictions must be explained
    - Strict closure
    - Free export (it's the record)
    """
    return Jurisdiction(
        name="audit",
        description="Maximum transparency. Full trail. Everything recorded.",
        admissible_evidence={
            EvidenceType.TOOL_TRACE,
            EvidenceType.SENSOR_DATA,
            EvidenceType.HUMAN_INPUT,
            EvidenceType.DOCUMENT,
            EvidenceType.RECEIPT,
            EvidenceType.CRYPTOGRAPHIC_PROOF,
            EvidenceType.URL,
            EvidenceType.CROSS_SOURCE,
            EvidenceType.CALC_RESULT,
            EvidenceType.TEST_RESULT,
            EvidenceType.WEB_SOURCE,
            EvidenceType.LIVE_RETRIEVAL,
        },
        budget=BudgetProfile(
            claim_cost=2.0,  # Everything costs - creates paper trail
            contradiction_cost=5.0,  # Contradictions are concerning
            resolution_cost=3.0,
            export_cost=0.0,  # Audit is the record
            refill_rate=1.0,
        ),
        spillover=SpilloverPolicy.FREE,
        contradiction_policy=ContradictionPolicy.STRICT,
        contradiction_tolerance=0.0,
        closure_allowed=True,
        closure_requires_evidence=True,
        export_to_factual_allowed=True,
        export_requires_promotion=False,  # Audit IS evidence
        output_label="[AUDIT TRAIL]",
    )


# =============================================================================
# Jurisdiction Registry
# =============================================================================

_JURISDICTIONS: dict[str, Jurisdiction] = {}


def register_jurisdiction(jurisdiction: Jurisdiction) -> None:
    """Register a jurisdiction for use."""
    _JURISDICTIONS[jurisdiction.name] = jurisdiction


def get_jurisdiction(name: str) -> Jurisdiction | None:
    """Get a registered jurisdiction by name."""
    return _JURISDICTIONS.get(name)


def list_jurisdictions() -> list[str]:
    """List all registered jurisdiction names."""
    return list(_JURISDICTIONS.keys())


def get_all_jurisdictions() -> dict[str, Jurisdiction]:
    """Get all registered jurisdictions."""
    return dict(_JURISDICTIONS)


def clear_jurisdictions() -> None:
    """Clear all registered jurisdictions (for testing)."""
    _JURISDICTIONS.clear()


def reset_to_defaults() -> None:
    """Reset registry to default jurisdictions."""
    clear_jurisdictions()
    register_jurisdiction(create_factual_jurisdiction())
    register_jurisdiction(create_speculative_jurisdiction())
    register_jurisdiction(create_counterfactual_jurisdiction())
    register_jurisdiction(create_adversarial_jurisdiction())
    register_jurisdiction(create_narrative_jurisdiction())
    register_jurisdiction(create_forensic_jurisdiction())
    register_jurisdiction(create_pedagogical_jurisdiction())
    register_jurisdiction(create_audit_jurisdiction())


# =============================================================================
# Jurisdiction Manager (for state tracking)
# =============================================================================


@dataclass
class JurisdictionState:
    """Tracks current jurisdiction state including budget."""

    jurisdiction: Jurisdiction
    current_budget: float = 100.0
    claims_made: int = 0
    contradictions_opened: int = 0
    contradictions_resolved: int = 0
    exports_made: int = 0

    def consume_budget(self, amount: float) -> bool:
        """
        Consume budget for an operation.

        Returns True if budget was available, False if depleted.
        """
        if self.current_budget >= amount:
            self.current_budget -= amount
            return True
        return False

    def refill_budget(self) -> float:
        """Refill budget by jurisdiction's refill rate. Returns new budget."""
        self.current_budget += self.jurisdiction.budget.refill_rate
        # Cap at some reasonable maximum
        self.current_budget = min(self.current_budget, 200.0)
        return self.current_budget

    def record_claim(self) -> None:
        """Record a claim made."""
        self.claims_made += 1

    def record_contradiction_opened(self) -> None:
        """Record a contradiction opened."""
        self.contradictions_opened += 1

    def record_contradiction_resolved(self) -> None:
        """Record a contradiction resolved."""
        self.contradictions_resolved += 1

    def record_export(self) -> None:
        """Record an export made."""
        self.exports_made += 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "jurisdiction": self.jurisdiction.name,
            "current_budget": self.current_budget,
            "claims_made": self.claims_made,
            "contradictions_opened": self.contradictions_opened,
            "contradictions_resolved": self.contradictions_resolved,
            "exports_made": self.exports_made,
        }


class JurisdictionManager:
    """
    Manages jurisdiction switching and state tracking.

    Tracks current jurisdiction, maintains budget across transitions,
    and provides hooks for claim/contradiction operations.
    """

    def __init__(self, initial_jurisdiction: str = "factual"):
        # Ensure defaults are registered
        if not _JURISDICTIONS:
            reset_to_defaults()

        jurisdiction = get_jurisdiction(initial_jurisdiction)
        if jurisdiction is None:
            raise ValueError(f"Unknown jurisdiction: {initial_jurisdiction}")

        self.current_state = JurisdictionState(jurisdiction=jurisdiction)
        self.history: list[dict[str, Any]] = []

    @property
    def current_jurisdiction(self) -> Jurisdiction:
        """Get the current jurisdiction."""
        return self.current_state.jurisdiction

    @property
    def current_budget(self) -> float:
        """Get current budget."""
        return self.current_state.current_budget

    def switch_jurisdiction(self, name: str) -> tuple[bool, str]:
        """
        Switch to a different jurisdiction.

        Returns (success, message).
        """
        jurisdiction = get_jurisdiction(name)
        if jurisdiction is None:
            return False, f"Unknown jurisdiction: {name}"

        old_name = self.current_state.jurisdiction.name
        if old_name == name:
            return True, f"Already in {name} jurisdiction"

        # Record transition
        self.history.append({
            "from": old_name,
            "to": name,
            "budget_at_switch": self.current_state.current_budget,
            "claims_made": self.current_state.claims_made,
        })

        # Create new state, preserving some budget
        # (you don't lose all progress when switching)
        preserved_budget = self.current_state.current_budget * 0.5
        self.current_state = JurisdictionState(
            jurisdiction=jurisdiction,
            current_budget=max(preserved_budget, jurisdiction.budget.refill_rate * 10),
        )

        return True, f"Switched from {old_name} to {name}"

    def can_make_claim(self, is_speculative: bool = False, is_adversarial: bool = False) -> tuple[bool, str]:
        """Check if a claim can be made given current budget."""
        cost = self.current_state.jurisdiction.budget.effective_claim_cost(
            is_speculative=is_speculative,
            is_adversarial=is_adversarial,
        )
        if self.current_state.current_budget >= cost:
            return True, f"Claim allowed (cost: {cost:.1f})"
        return False, f"Insufficient budget (need {cost:.1f}, have {self.current_state.current_budget:.1f})"

    def make_claim(self, is_speculative: bool = False, is_adversarial: bool = False) -> tuple[bool, str]:
        """Make a claim, consuming budget."""
        cost = self.current_state.jurisdiction.budget.effective_claim_cost(
            is_speculative=is_speculative,
            is_adversarial=is_adversarial,
        )
        if self.current_state.consume_budget(cost):
            self.current_state.record_claim()
            return True, f"Claim made (cost: {cost:.1f}, remaining: {self.current_state.current_budget:.1f})"
        return False, "Insufficient budget for claim"

    def can_open_contradiction(self) -> tuple[bool, str]:
        """Check if a contradiction can be opened."""
        if not self.current_state.jurisdiction.tolerates_contradiction():
            policy = self.current_state.jurisdiction.contradiction_policy
            if policy == ContradictionPolicy.STRICT:
                return False, "Contradictions block operations in this jurisdiction"
        cost = self.current_state.jurisdiction.budget.contradiction_cost
        if self.current_state.current_budget >= cost:
            return True, f"Contradiction allowed (cost: {cost:.1f})"
        return False, "Insufficient budget for contradiction"

    def open_contradiction(self) -> tuple[bool, str]:
        """Open a contradiction, consuming budget."""
        can, msg = self.can_open_contradiction()
        if not can:
            return False, msg
        cost = self.current_state.jurisdiction.budget.contradiction_cost
        self.current_state.consume_budget(cost)
        self.current_state.record_contradiction_opened()
        return True, f"Contradiction opened (cost: {cost:.1f})"

    def can_resolve_contradiction(self) -> tuple[bool, str]:
        """Check if a contradiction can be resolved."""
        j = self.current_state.jurisdiction
        if not j.closure_allowed:
            return False, "Resolution not allowed in this jurisdiction"
        cost = j.budget.resolution_cost
        if cost > 50.0:  # Effectively blocked by cost
            return False, f"Resolution blocked by cost ({cost:.1f})"
        if self.current_state.current_budget >= cost:
            return True, f"Resolution allowed (cost: {cost:.1f})"
        return False, "Insufficient budget for resolution"

    def resolve_contradiction(self) -> tuple[bool, str]:
        """Resolve a contradiction, consuming budget."""
        can, msg = self.can_resolve_contradiction()
        if not can:
            return False, msg
        cost = self.current_state.jurisdiction.budget.resolution_cost
        self.current_state.consume_budget(cost)
        self.current_state.record_contradiction_resolved()
        return True, f"Contradiction resolved (cost: {cost:.1f})"

    def can_export_to_factual(self, has_evidence: bool) -> tuple[bool, str]:
        """Check if export to factual jurisdiction is allowed."""
        j = self.current_state.jurisdiction
        if not j.export_to_factual_allowed:
            return False, "Export to factual not allowed from this jurisdiction"
        if not j.can_export(has_evidence):
            return False, "Export requires evidence promotion"
        cost = j.budget.export_cost
        if self.current_state.current_budget >= cost:
            return True, f"Export allowed (cost: {cost:.1f})"
        return False, "Insufficient budget for export"

    def export_to_factual(self, has_evidence: bool) -> tuple[bool, str]:
        """Export a claim to factual jurisdiction."""
        can, msg = self.can_export_to_factual(has_evidence)
        if not can:
            return False, msg
        cost = self.current_state.jurisdiction.budget.export_cost
        self.current_state.consume_budget(cost)
        self.current_state.record_export()
        return True, f"Exported to factual (cost: {cost:.1f})"

    def tick(self) -> float:
        """Advance turn, refilling budget. Returns new budget."""
        return self.current_state.refill_budget()

    def get_status(self) -> dict[str, Any]:
        """Get current status."""
        j = self.current_state.jurisdiction
        return {
            "jurisdiction": j.name,
            "description": j.description,
            "output_label": j.output_label,
            "budget": self.current_state.current_budget,
            "refill_rate": j.budget.refill_rate,
            "contradiction_policy": j.contradiction_policy.value,
            "closure_allowed": j.closure_allowed,
            "export_allowed": j.export_to_factual_allowed,
            "stats": {
                "claims_made": self.current_state.claims_made,
                "contradictions_opened": self.current_state.contradictions_opened,
                "contradictions_resolved": self.current_state.contradictions_resolved,
                "exports_made": self.current_state.exports_made,
            },
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize manager state."""
        return {
            "current_state": self.current_state.to_dict(),
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JurisdictionManager":
        """Deserialize manager from dictionary."""
        # Ensure defaults are registered
        if not _JURISDICTIONS:
            reset_to_defaults()

        state_data = data["current_state"]
        jurisdiction = get_jurisdiction(state_data["jurisdiction"])
        if jurisdiction is None:
            jurisdiction = create_factual_jurisdiction()

        manager = cls.__new__(cls)
        manager.current_state = JurisdictionState(
            jurisdiction=jurisdiction,
            current_budget=state_data.get("current_budget", 100.0),
            claims_made=state_data.get("claims_made", 0),
            contradictions_opened=state_data.get("contradictions_opened", 0),
            contradictions_resolved=state_data.get("contradictions_resolved", 0),
            exports_made=state_data.get("exports_made", 0),
        )
        manager.history = data.get("history", [])
        return manager


# Initialize default jurisdictions on module load
reset_to_defaults()
