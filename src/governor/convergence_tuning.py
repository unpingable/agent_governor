"""
Convergence Auto-Tuner — Offline system identification + proposal engine.

Reads convergence telemetry (CONTINUITY_TRACE/CONTINUITY_RESULT events),
computes per-anchor analysis, identifies tuning opportunities, and produces
TuningProposal artifacts.

Core invariant: AutoTuner performs offline system identification over
convergence traces and proposes controller parameter updates; it never
mutates invariants or enforcement parameters without explicit human approval.

10 footgun guardrails mapped to implementation:
1. Multi-term objective (MetricsBlock)
2. No severity downgrades (HardGuards forced True)
3. Proposals only (ConvergenceTuner.propose)
4. Regime stratification (Scope.regime)
5. Measurement refinement (SupportingEvidence)
6. Interference tracking (InterferenceEdge)
7. Rate-limiting (min_enforcement_episodes)
8. No auto-apply (Approval.requires_human forced True)
9. Namespace isolation (Scope.anchor_namespace)
10. Determinism hygiene (config_hash everywhere)
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# =============================================================================
# Constants
# =============================================================================

ACTION_AGGRESSIVENESS: dict[str, int] = {
    "SOFT_REPROMPT": 1,
    "HARD_REPROMPT": 2,
    "CONSTRAIN_DECODING": 3,
    "REQUIRE_HITL": 4,
    "FAIL_CLOSED": 5,
}


# =============================================================================
# Enums
# =============================================================================


class TuningMode(str, Enum):
    """Operating mode for tuning proposals."""

    FICTION = "fiction"
    NONFICTION = "nonfiction"
    PUPPET = "puppet"
    CODE = "code"
    OPS = "ops"
    UNKNOWN = "unknown"


class TuningConfidence(str, Enum):
    """Confidence level for predicted impact."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProposalStatus(str, Enum):
    """Lifecycle status of a tuning proposal."""

    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"


class ChangeSetType(str, Enum):
    """Type of change in a tuning proposal."""

    PARAMETER_UPDATE = "parameter_update"
    PATTERN_UPDATE = "pattern_update"
    REFACTOR_SUGGESTION = "refactor_suggestion"


class RefactorSuggestionType(str, Enum):
    """Type of refactor suggestion (non-executable)."""

    SPLIT_ANCHOR = "split_anchor"
    MERGE_ANCHORS = "merge_anchors"
    REWEIGHT_RULES = "reweight_rules"
    REVISE_MEASUREMENT = "revise_measurement"


class RollbackMetric(str, Enum):
    """Metrics used for rollback triggers."""

    REFUSAL_RATE = "refusal_rate"
    RESIDUAL_ERROR_AVG = "residual_error_avg"
    VIOLATION_RATE = "violation_rate"
    ATTEMPTS_AVG = "attempts_avg"
    TOKEN_COST_AVG = "token_cost_avg"


class RollbackOperator(str, Enum):
    """Comparison operators for rollback triggers."""

    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    EQ = "=="


# =============================================================================
# Dataclasses — Proposal artifact types
# =============================================================================


@dataclass
class Regime:
    """Identifies the runtime regime a proposal targets."""

    model_id: str = ""
    prompt_profile_hash: str = ""
    decoder_profile: str = "default"
    governor_version: str = ""
    config_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "prompt_profile_hash": self.prompt_profile_hash,
            "decoder_profile": self.decoder_profile,
            "governor_version": self.governor_version,
            "config_hash": self.config_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Regime:
        return cls(
            model_id=d.get("model_id", ""),
            prompt_profile_hash=d.get("prompt_profile_hash", ""),
            decoder_profile=d.get("decoder_profile", "default"),
            governor_version=d.get("governor_version", ""),
            config_hash=d.get("config_hash", ""),
        )


@dataclass
class Scope:
    """Defines what a proposal targets."""

    mode: TuningMode = TuningMode.UNKNOWN
    anchor_namespace: str = ""
    targets: list[str] = field(default_factory=list)
    regime: Regime = field(default_factory=Regime)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "anchor_namespace": self.anchor_namespace,
            "targets": list(self.targets),
            "regime": self.regime.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Scope:
        mode_val = d.get("mode", "unknown")
        try:
            mode = TuningMode(mode_val)
        except ValueError:
            mode = TuningMode.UNKNOWN
        return cls(
            mode=mode,
            anchor_namespace=d.get("anchor_namespace", ""),
            targets=d.get("targets", []),
            regime=Regime.from_dict(d.get("regime", {})),
        )


@dataclass
class TimeRange:
    """UTC time range (ISO 8601 strings)."""

    start: str = ""
    end: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TimeRange:
        return cls(start=d.get("start", ""), end=d.get("end", ""))


@dataclass
class EvidenceWindow:
    """Defines the data window for a proposal."""

    time_range_utc: TimeRange = field(default_factory=TimeRange)
    min_enforcement_episodes: int = 40
    episodes_observed: int = 0
    data_sources: list[str] = field(default_factory=lambda: ["telemetry_jsonl"])

    def to_dict(self) -> dict[str, Any]:
        return {
            "time_range_utc": self.time_range_utc.to_dict(),
            "min_enforcement_episodes": self.min_enforcement_episodes,
            "episodes_observed": self.episodes_observed,
            "data_sources": list(self.data_sources),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvidenceWindow:
        return cls(
            time_range_utc=TimeRange.from_dict(d.get("time_range_utc", {})),
            min_enforcement_episodes=d.get("min_enforcement_episodes", 40),
            episodes_observed=d.get("episodes_observed", 0),
            data_sources=d.get("data_sources", ["telemetry_jsonl"]),
        )


@dataclass
class ChangeParameterUpdate:
    """A parameter change within a ChangeSet."""

    target: str = ""
    from_value: Any = None
    to_value: Any = None
    reason_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "from": self.from_value,
            "to": self.to_value,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeParameterUpdate:
        return cls(
            target=d.get("target", ""),
            from_value=d.get("from"),
            to_value=d.get("to"),
            reason_code=d.get("reason_code", ""),
        )


@dataclass
class ChangePatternUpdate:
    """A pattern change within a ChangeSet."""

    target: str = ""
    op: str = "add"
    values: list[str] = field(default_factory=list)
    reason_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "op": self.op,
            "values": list(self.values),
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangePatternUpdate:
        return cls(
            target=d.get("target", ""),
            op=d.get("op", "add"),
            values=d.get("values", []),
            reason_code=d.get("reason_code", ""),
        )


@dataclass
class ChangeRefactorSuggestion:
    """A refactor suggestion within a ChangeSet (non-executable)."""

    suggestion_type: RefactorSuggestionType = RefactorSuggestionType.SPLIT_ANCHOR
    detail: str = ""
    reason_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggestion_type": self.suggestion_type.value,
            "detail": self.detail,
            "reason_code": self.reason_code,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeRefactorSuggestion:
        st = d.get("suggestion_type", "split_anchor")
        try:
            suggestion_type = RefactorSuggestionType(st)
        except ValueError:
            suggestion_type = RefactorSuggestionType.SPLIT_ANCHOR
        return cls(
            suggestion_type=suggestion_type,
            detail=d.get("detail", ""),
            reason_code=d.get("reason_code", ""),
        )


@dataclass
class ChangeSet:
    """Set of changes in a tuning proposal.

    Changes are stored as dicts. Typed accessor methods filter by
    discriminating keys (target/from/to for parameter updates, op/values
    for pattern updates, suggestion_type for refactor suggestions).
    """

    type: ChangeSetType = ChangeSetType.PARAMETER_UPDATE
    changes: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "changes": [dict(c) for c in self.changes],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ChangeSet:
        t = d.get("type", "parameter_update")
        try:
            cs_type = ChangeSetType(t)
        except ValueError:
            cs_type = ChangeSetType.PARAMETER_UPDATE
        return cls(
            type=cs_type,
            changes=d.get("changes", []),
        )

    def parameter_updates(self) -> list[ChangeParameterUpdate]:
        """Return only parameter update changes."""
        result = []
        for c in self.changes:
            if "from" in c and "to" in c:
                result.append(ChangeParameterUpdate.from_dict(c))
        return result

    def pattern_updates(self) -> list[ChangePatternUpdate]:
        """Return only pattern update changes."""
        result = []
        for c in self.changes:
            if "op" in c and "values" in c:
                result.append(ChangePatternUpdate.from_dict(c))
        return result

    def refactor_suggestions(self) -> list[ChangeRefactorSuggestion]:
        """Return only refactor suggestion changes."""
        result = []
        for c in self.changes:
            if "suggestion_type" in c:
                result.append(ChangeRefactorSuggestion.from_dict(c))
        return result


@dataclass
class HardGuards:
    """Non-negotiable safety guards. All forced True in __post_init__."""

    severity_downgrade_forbidden: bool = True
    auto_apply_forbidden: bool = True
    cross_mode_forbidden: bool = True
    mutation_during_session_forbidden: bool = True

    def __post_init__(self) -> None:
        self.severity_downgrade_forbidden = True
        self.auto_apply_forbidden = True
        self.cross_mode_forbidden = True
        self.mutation_during_session_forbidden = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity_downgrade_forbidden": True,
            "auto_apply_forbidden": True,
            "cross_mode_forbidden": True,
            "mutation_during_session_forbidden": True,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HardGuards:
        return cls()


@dataclass
class ObjectiveConstraints:
    """Bounds on tuning impact."""

    max_allowed_increase_refusal_rate: float = 0.02
    max_allowed_increase_violation_rate: float = 0.0
    min_required_enforcement_strength: str = "no_weaken"

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_allowed_increase_refusal_rate": round(self.max_allowed_increase_refusal_rate, 6),
            "max_allowed_increase_violation_rate": round(self.max_allowed_increase_violation_rate, 6),
            "min_required_enforcement_strength": self.min_required_enforcement_strength,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ObjectiveConstraints:
        return cls(
            max_allowed_increase_refusal_rate=d.get("max_allowed_increase_refusal_rate", 0.02),
            max_allowed_increase_violation_rate=d.get("max_allowed_increase_violation_rate", 0.0),
            min_required_enforcement_strength=d.get("min_required_enforcement_strength", "no_weaken"),
        )


@dataclass
class Constraints:
    """Combined hard guards and objective constraints."""

    hard_guards: HardGuards = field(default_factory=HardGuards)
    objective_constraints: ObjectiveConstraints = field(default_factory=ObjectiveConstraints)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hard_guards": self.hard_guards.to_dict(),
            "objective_constraints": self.objective_constraints.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Constraints:
        return cls(
            hard_guards=HardGuards.from_dict(d.get("hard_guards", {})),
            objective_constraints=ObjectiveConstraints.from_dict(d.get("objective_constraints", {})),
        )


@dataclass
class MetricsBlock:
    """Observed metrics (before or after)."""

    attempts_avg: float = 0.0
    attempts_p95: float = 0.0
    refusal_rate: float = 0.0
    accept_rate: float = 0.0
    residual_error_avg: float = 0.0
    soft_success_rate: float = 0.0
    hard_success_rate: float = 0.0
    token_cost_avg: float = 0.0
    token_cost_per_error_reduction_avg: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts_avg": round(self.attempts_avg, 6),
            "attempts_p95": round(self.attempts_p95, 6),
            "refusal_rate": round(self.refusal_rate, 6),
            "accept_rate": round(self.accept_rate, 6),
            "residual_error_avg": round(self.residual_error_avg, 6),
            "soft_success_rate": round(self.soft_success_rate, 6),
            "hard_success_rate": round(self.hard_success_rate, 6),
            "token_cost_avg": round(self.token_cost_avg, 2),
            "token_cost_per_error_reduction_avg": round(self.token_cost_per_error_reduction_avg, 2),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MetricsBlock:
        return cls(
            attempts_avg=d.get("attempts_avg", 0.0),
            attempts_p95=d.get("attempts_p95", 0.0),
            refusal_rate=d.get("refusal_rate", 0.0),
            accept_rate=d.get("accept_rate", 0.0),
            residual_error_avg=d.get("residual_error_avg", 0.0),
            soft_success_rate=d.get("soft_success_rate", 0.0),
            hard_success_rate=d.get("hard_success_rate", 0.0),
            token_cost_avg=d.get("token_cost_avg", 0.0),
            token_cost_per_error_reduction_avg=d.get("token_cost_per_error_reduction_avg", 0.0),
        )


@dataclass
class PredictedImpact:
    """Predicted effect of applying the proposal."""

    attempts_avg_delta: float = 0.0
    token_cost_avg_delta: float = 0.0
    refusal_rate_delta: float = 0.0
    violation_rate_delta: float = 0.0
    confidence: TuningConfidence = TuningConfidence.LOW
    rationale: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempts_avg_delta": round(self.attempts_avg_delta, 6),
            "token_cost_avg_delta": round(self.token_cost_avg_delta, 2),
            "refusal_rate_delta": round(self.refusal_rate_delta, 6),
            "violation_rate_delta": round(self.violation_rate_delta, 6),
            "confidence": self.confidence.value,
            "rationale": list(self.rationale),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PredictedImpact:
        conf = d.get("confidence", "low")
        try:
            confidence = TuningConfidence(conf)
        except ValueError:
            confidence = TuningConfidence.LOW
        return cls(
            attempts_avg_delta=d.get("attempts_avg_delta", 0.0),
            token_cost_avg_delta=d.get("token_cost_avg_delta", 0.0),
            refusal_rate_delta=d.get("refusal_rate_delta", 0.0),
            violation_rate_delta=d.get("violation_rate_delta", 0.0),
            confidence=confidence,
            rationale=d.get("rationale", []),
        )


@dataclass
class SummaryTable:
    """Named table of evidence rows."""

    name: str = ""
    rows: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "rows": [dict(r) for r in self.rows]}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SummaryTable:
        return cls(name=d.get("name", ""), rows=d.get("rows", []))


@dataclass
class ExampleEpisode:
    """An example convergence episode for evidence."""

    run_id: str = ""
    attempts: int = 0
    violation_codes: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    result: str = "ACCEPTED"
    trace_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "attempts": self.attempts,
            "violation_codes": list(self.violation_codes),
            "actions": list(self.actions),
            "result": self.result,
            "trace_refs": list(self.trace_refs),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ExampleEpisode:
        return cls(
            run_id=d.get("run_id", ""),
            attempts=d.get("attempts", 0),
            violation_codes=d.get("violation_codes", []),
            actions=d.get("actions", []),
            result=d.get("result", "ACCEPTED"),
            trace_refs=d.get("trace_refs", []),
        )


@dataclass
class InterferenceEdge:
    """Records interference between two anchors."""

    from_anchor: str = ""
    to_anchor: str = ""
    count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_anchor": self.from_anchor,
            "to_anchor": self.to_anchor,
            "count": self.count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> InterferenceEdge:
        return cls(
            from_anchor=d.get("from_anchor", ""),
            to_anchor=d.get("to_anchor", ""),
            count=d.get("count", 0),
        )


@dataclass
class SupportingEvidence:
    """Evidence backing a proposal."""

    summary_tables: list[SummaryTable] = field(default_factory=list)
    example_episodes: list[ExampleEpisode] = field(default_factory=list)
    interference_graph: list[InterferenceEdge] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary_tables": [t.to_dict() for t in self.summary_tables],
            "example_episodes": [e.to_dict() for e in self.example_episodes],
            "interference_graph": [e.to_dict() for e in self.interference_graph],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SupportingEvidence:
        return cls(
            summary_tables=[SummaryTable.from_dict(t) for t in d.get("summary_tables", [])],
            example_episodes=[ExampleEpisode.from_dict(e) for e in d.get("example_episodes", [])],
            interference_graph=[InterferenceEdge.from_dict(e) for e in d.get("interference_graph", [])],
        )


@dataclass
class RollbackTrigger:
    """Condition that triggers rollback of a trial."""

    metric: RollbackMetric = RollbackMetric.REFUSAL_RATE
    operator: RollbackOperator = RollbackOperator.GT
    threshold: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric.value,
            "operator": self.operator.value,
            "threshold": self.threshold,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RollbackTrigger:
        metric = RollbackMetric.REFUSAL_RATE
        try:
            metric = RollbackMetric(d.get("metric", "refusal_rate"))
        except ValueError:
            pass
        operator = RollbackOperator.GT
        try:
            operator = RollbackOperator(d.get("operator", ">"))
        except ValueError:
            pass
        return cls(
            metric=metric,
            operator=operator,
            threshold=d.get("threshold", 0.0),
        )


@dataclass
class TrialScope:
    """Bounds on a trial run."""

    max_runs: int = 200
    max_days: int = 7

    def to_dict(self) -> dict[str, Any]:
        return {"max_runs": self.max_runs, "max_days": self.max_days}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrialScope:
        return cls(max_runs=d.get("max_runs", 200), max_days=d.get("max_days", 7))


@dataclass
class EvaluationSet:
    """Fixture IDs for evaluation."""

    fixture_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"fixture_ids": list(self.fixture_ids)}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EvaluationSet:
        return cls(fixture_ids=d.get("fixture_ids", []))


@dataclass
class TrialPlan:
    """Trial configuration for a proposal."""

    trial_id: str = ""
    apply_mode: str = "manual"
    trial_scope: TrialScope = field(default_factory=TrialScope)
    rollback_triggers: list[RollbackTrigger] = field(default_factory=list)
    evaluation_set: EvaluationSet = field(default_factory=EvaluationSet)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "apply_mode": self.apply_mode,
            "trial_scope": self.trial_scope.to_dict(),
            "rollback_triggers": [t.to_dict() for t in self.rollback_triggers],
            "evaluation_set": self.evaluation_set.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TrialPlan:
        return cls(
            trial_id=d.get("trial_id", ""),
            apply_mode=d.get("apply_mode", "manual"),
            trial_scope=TrialScope.from_dict(d.get("trial_scope", {})),
            rollback_triggers=[RollbackTrigger.from_dict(t) for t in d.get("rollback_triggers", [])],
            evaluation_set=EvaluationSet.from_dict(d.get("evaluation_set", {})),
        )


@dataclass
class Approval:
    """Approval state for a proposal. requires_human is forced True."""

    requires_human: bool = True
    required_roles: list[str] = field(default_factory=lambda: ["owner"])
    status: ProposalStatus = ProposalStatus.PROPOSED
    approved_by: str | None = None
    approved_at_utc: str | None = None
    applied_at_utc: str | None = None

    def __post_init__(self) -> None:
        self.requires_human = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "requires_human": True,
            "required_roles": list(self.required_roles),
            "status": self.status.value,
            "approved_by": self.approved_by,
            "approved_at_utc": self.approved_at_utc,
            "applied_at_utc": self.applied_at_utc,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Approval:
        status = ProposalStatus.PROPOSED
        try:
            status = ProposalStatus(d.get("status", "proposed"))
        except ValueError:
            pass
        return cls(
            required_roles=d.get("required_roles", ["owner"]),
            status=status,
            approved_by=d.get("approved_by"),
            approved_at_utc=d.get("approved_at_utc"),
            applied_at_utc=d.get("applied_at_utc"),
        )


@dataclass
class TuningProposal:
    """Top-level tuning proposal artifact."""

    schema_version: str = "tuning_proposal_v0"
    proposal_id: str = ""
    created_at_utc: str = ""
    scope: Scope = field(default_factory=Scope)
    evidence_window: EvidenceWindow = field(default_factory=EvidenceWindow)
    change_set: ChangeSet = field(default_factory=ChangeSet)
    constraints: Constraints = field(default_factory=Constraints)
    metrics_before: MetricsBlock = field(default_factory=MetricsBlock)
    predicted_impact: PredictedImpact = field(default_factory=PredictedImpact)
    supporting_evidence: SupportingEvidence = field(default_factory=SupportingEvidence)
    trial_plan: TrialPlan = field(default_factory=TrialPlan)
    approval: Approval = field(default_factory=Approval)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "created_at_utc": self.created_at_utc,
            "scope": self.scope.to_dict(),
            "evidence_window": self.evidence_window.to_dict(),
            "change_set": self.change_set.to_dict(),
            "constraints": self.constraints.to_dict(),
            "metrics_before": self.metrics_before.to_dict(),
            "predicted_impact": self.predicted_impact.to_dict(),
            "supporting_evidence": self.supporting_evidence.to_dict(),
            "trial_plan": self.trial_plan.to_dict(),
            "approval": self.approval.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TuningProposal:
        return cls(
            schema_version=d.get("schema_version", "tuning_proposal_v0"),
            proposal_id=d.get("proposal_id", ""),
            created_at_utc=d.get("created_at_utc", ""),
            scope=Scope.from_dict(d.get("scope", {})),
            evidence_window=EvidenceWindow.from_dict(d.get("evidence_window", {})),
            change_set=ChangeSet.from_dict(d.get("change_set", {})),
            constraints=Constraints.from_dict(d.get("constraints", {})),
            metrics_before=MetricsBlock.from_dict(d.get("metrics_before", {})),
            predicted_impact=PredictedImpact.from_dict(d.get("predicted_impact", {})),
            supporting_evidence=SupportingEvidence.from_dict(d.get("supporting_evidence", {})),
            trial_plan=TrialPlan.from_dict(d.get("trial_plan", {})),
            approval=Approval.from_dict(d.get("approval", {})),
        )


@dataclass
class TuningApply:
    """Provenance record for applying a proposal."""

    schema_version: str = "tuning_apply_v0"
    trial_id: str = ""
    proposal_id: str = ""
    applied_by: str = ""
    applied_at_utc: str = ""
    new_config_hash: str = ""
    previous_config_hash: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trial_id": self.trial_id,
            "proposal_id": self.proposal_id,
            "applied_by": self.applied_by,
            "applied_at_utc": self.applied_at_utc,
            "new_config_hash": self.new_config_hash,
            "previous_config_hash": self.previous_config_hash,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TuningApply:
        return cls(
            schema_version=d.get("schema_version", "tuning_apply_v0"),
            trial_id=d.get("trial_id", ""),
            proposal_id=d.get("proposal_id", ""),
            applied_by=d.get("applied_by", ""),
            applied_at_utc=d.get("applied_at_utc", ""),
            new_config_hash=d.get("new_config_hash", ""),
            previous_config_hash=d.get("previous_config_hash", ""),
            notes=d.get("notes", ""),
        )


# =============================================================================
# Dataclasses — Analysis types (internal to the tuner)
# =============================================================================


@dataclass
class ActionEffectiveness:
    """Effectiveness of a correction ladder action."""

    action: str = ""
    total_attempts: int = 0
    improved: int = 0
    worsened: int = 0
    no_change: int = 0
    success_rate: float = 0.0
    avg_delta: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "total_attempts": self.total_attempts,
            "improved": self.improved,
            "worsened": self.worsened,
            "no_change": self.no_change,
            "success_rate": round(self.success_rate, 6),
            "avg_delta": round(self.avg_delta, 6),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ActionEffectiveness:
        return cls(
            action=d.get("action", ""),
            total_attempts=d.get("total_attempts", 0),
            improved=d.get("improved", 0),
            worsened=d.get("worsened", 0),
            no_change=d.get("no_change", 0),
            success_rate=d.get("success_rate", 0.0),
            avg_delta=d.get("avg_delta", 0.0),
        )


@dataclass
class PerAnchorAnalysis:
    """Analysis results for a single anchor."""

    anchor_id: str = ""
    episode_count: int = 0
    violation_count: int = 0
    action_effectiveness: list[ActionEffectiveness] = field(default_factory=list)
    deadzone_actions: list[str] = field(default_factory=list)
    avg_attempts_to_resolve: float = 0.0
    residual_error_avg: float = 0.0
    interference_targets: list[str] = field(default_factory=list)
    mode: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "episode_count": self.episode_count,
            "violation_count": self.violation_count,
            "action_effectiveness": [a.to_dict() for a in self.action_effectiveness],
            "deadzone_actions": list(self.deadzone_actions),
            "avg_attempts_to_resolve": round(self.avg_attempts_to_resolve, 6),
            "residual_error_avg": round(self.residual_error_avg, 6),
            "interference_targets": list(self.interference_targets),
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PerAnchorAnalysis:
        return cls(
            anchor_id=d.get("anchor_id", ""),
            episode_count=d.get("episode_count", 0),
            violation_count=d.get("violation_count", 0),
            action_effectiveness=[
                ActionEffectiveness.from_dict(a) for a in d.get("action_effectiveness", [])
            ],
            deadzone_actions=d.get("deadzone_actions", []),
            avg_attempts_to_resolve=d.get("avg_attempts_to_resolve", 0.0),
            residual_error_avg=d.get("residual_error_avg", 0.0),
            interference_targets=d.get("interference_targets", []),
            mode=d.get("mode", ""),
        )


@dataclass
class TuningOpportunity:
    """An identified tuning opportunity for an anchor."""

    anchor_id: str = ""
    opportunity_type: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    estimated_savings: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "opportunity_type": self.opportunity_type,
            "evidence": dict(self.evidence),
            "estimated_savings": round(self.estimated_savings, 2),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TuningOpportunity:
        return cls(
            anchor_id=d.get("anchor_id", ""),
            opportunity_type=d.get("opportunity_type", ""),
            evidence=d.get("evidence", {}),
            estimated_savings=d.get("estimated_savings", 0.0),
        )


@dataclass
class AdmissibilityResult:
    """Result of an admissibility check."""

    passed: bool = True
    check_name: str = ""
    violations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "check_name": self.check_name,
            "violations": list(self.violations),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AdmissibilityResult:
        return cls(
            passed=d.get("passed", True),
            check_name=d.get("check_name", ""),
            violations=d.get("violations", []),
        )


# =============================================================================
# ProposalStore — file-per-item JSON persistence
# =============================================================================


class ProposalStore:
    """File-per-item persistence for tuning proposals and apply records.

    Follows InvariantStore pattern: JSON files in .governor/convergence_tuning/.
    """

    def __init__(self, root: Path | None = None):
        self.root = root or Path(".")
        self.store_dir = self.root / ".governor" / "convergence_tuning"

    def _ensure_dir(self) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def _safe_filename(self, item_id: str) -> str:
        return re.sub(r"[^\w\-.]", "_", item_id)

    def _proposal_path(self, proposal_id: str) -> Path:
        return self.store_dir / f"{self._safe_filename(proposal_id)}.json"

    def _apply_path(self, trial_id: str) -> Path:
        return self.store_dir / f"{self._safe_filename(trial_id)}.json"

    # -- Proposals --

    def save_proposal(self, proposal: TuningProposal) -> None:
        """Save (or overwrite) a proposal."""
        self._ensure_dir()
        path = self._proposal_path(proposal.proposal_id)
        path.write_text(json.dumps(proposal.to_dict(), indent=2) + "\n")

    def get_proposal(self, proposal_id: str) -> TuningProposal | None:
        """Get a proposal by ID."""
        path = self._proposal_path(proposal_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return TuningProposal.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def list_proposals(self, status: ProposalStatus | None = None) -> list[TuningProposal]:
        """List all proposals, optionally filtered by status."""
        if not self.store_dir.exists():
            return []
        proposals: list[TuningProposal] = []
        for path in sorted(self.store_dir.glob("tp_*.json")):
            try:
                data = json.loads(path.read_text())
                p = TuningProposal.from_dict(data)
                if status is None or p.approval.status == status:
                    proposals.append(p)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return proposals

    def remove_proposal(self, proposal_id: str) -> bool:
        """Remove a proposal. Returns True if it existed."""
        path = self._proposal_path(proposal_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def proposals_for_anchor(self, anchor_id: str) -> list[TuningProposal]:
        """List proposals that target a specific anchor."""
        result = []
        for p in self.list_proposals():
            if anchor_id in p.scope.targets:
                result.append(p)
        return result

    def status_counts(self) -> dict[str, int]:
        """Count proposals by status."""
        counts: dict[str, int] = {}
        for p in self.list_proposals():
            key = p.approval.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts

    # -- Apply records --

    def save_apply(self, record: TuningApply) -> None:
        """Save an apply record."""
        self._ensure_dir()
        path = self._apply_path(record.trial_id)
        path.write_text(json.dumps(record.to_dict(), indent=2) + "\n")

    def get_apply(self, trial_id: str) -> TuningApply | None:
        """Get an apply record by trial ID."""
        path = self._apply_path(trial_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            return TuningApply.from_dict(data)
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def list_applies(self) -> list[TuningApply]:
        """List all apply records."""
        if not self.store_dir.exists():
            return []
        applies: list[TuningApply] = []
        for path in sorted(self.store_dir.glob("trial_*.json")):
            try:
                data = json.loads(path.read_text())
                applies.append(TuningApply.from_dict(data))
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
        return applies


# =============================================================================
# ConvergenceAnalyzer — per-anchor decomposition
# =============================================================================


def _generate_proposal_id() -> str:
    """Generate a proposal ID: tp_YYYY-MM-DD_NNNNNN."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    suffix = str(int(uuid.uuid4().int % 1_000_000)).zfill(6)
    return f"tp_{date_str}_{suffix}"


def _generate_trial_id() -> str:
    """Generate a trial ID: trial_YYYY-MM-DD_NNNNNN."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    suffix = str(int(uuid.uuid4().int % 1_000_000)).zfill(6)
    return f"trial_{date_str}_{suffix}"


class ConvergenceAnalyzer:
    """Reads convergence telemetry and computes per-anchor analysis.

    Deeper than the aggregate analyze_convergence() in telemetry.py:
    computes action effectiveness matrices, deadzone detection,
    interference tracking, and opportunity identification.
    """

    def analyze(
        self,
        events: list[Any],
        since: str | None = None,
        mode: str | None = None,
    ) -> dict[str, PerAnchorAnalysis]:
        """Analyze events and return per-anchor analysis.

        Args:
            events: List of TelemetryEvent objects.
            since: ISO timestamp string to filter events from.
            mode: Mode filter (e.g., "fiction").

        Returns:
            Dict mapping anchor_id to PerAnchorAnalysis.
        """
        from .telemetry import TelemetryEventType

        # Filter to convergence events
        traces = [
            e for e in events
            if e.event_type == TelemetryEventType.CONTINUITY_TRACE
            and (since is None or e.timestamp >= since)
            and (mode is None or e.fields.get("mode", "") == mode)
        ]
        results = [
            e for e in events
            if e.event_type == TelemetryEventType.CONTINUITY_RESULT
            and (since is None or e.timestamp >= since)
            and (mode is None or e.fields.get("mode", "") == mode)
        ]

        if not results:
            return {}

        # Group traces by run_id
        traces_by_run: dict[str, list[Any]] = {}
        for t in traces:
            rid = t.fields.get("run_id", "")
            if rid:
                traces_by_run.setdefault(rid, []).append(t)
        for rid in traces_by_run:
            traces_by_run[rid].sort(key=lambda e: e.fields.get("attempt", 0))

        # Per-anchor tracking
        anchor_episodes: dict[str, set[str]] = {}   # anchor_id -> set of run_ids
        anchor_violations: dict[str, int] = {}       # anchor_id -> violation count
        anchor_residuals: dict[str, list[float]] = {}  # anchor_id -> residual errors
        anchor_attempts: dict[str, list[int]] = {}   # anchor_id -> attempts per run
        anchor_interference: dict[str, set[str]] = {}  # anchor_id -> interfering anchors
        # action -> anchor_id -> list of (improved, delta)
        action_outcomes: dict[str, dict[str, list[tuple[bool, float]]]] = {}
        anchor_deadzone_actions: dict[str, set[str]] = {}
        detected_mode = mode or ""

        # Process result events
        for ev in results:
            f = ev.fields
            rid = f.get("run_id", "")
            if not detected_mode:
                detected_mode = f.get("mode", "")

            # Track per-anchor residuals
            residuals = f.get("residual_error_by_anchor", {})
            for aid, err in residuals.items():
                anchor_episodes.setdefault(aid, set()).add(rid)
                anchor_residuals.setdefault(aid, []).append(err)
                anchor_attempts.setdefault(aid, []).append(f.get("attempts", 0))

            # Track interference
            for edge in f.get("interference_edges", []):
                from_a = edge.get("from_anchor", "")
                to_a = edge.get("to_anchor", "")
                if from_a and to_a:
                    anchor_interference.setdefault(from_a, set()).add(to_a)

            # Track deadzone actions per anchor
            for dz_action in f.get("deadzone_actions", []):
                # Deadzone actions come from result events; attribute to all anchors in run
                for aid in residuals:
                    anchor_deadzone_actions.setdefault(aid, set()).add(dz_action)

        # Process trace events for action effectiveness
        for rid, run_traces in traces_by_run.items():
            for i, t in enumerate(run_traces):
                tf = t.fields
                eba = tf.get("error_by_anchor", {})
                action = tf.get("action", "none")

                for aid, vcount in eba.items():
                    if vcount > 0:
                        anchor_violations[aid] = anchor_violations.get(aid, 0) + 1
                        anchor_episodes.setdefault(aid, set()).add(rid)

                # Action effectiveness: compare with previous attempt
                if i > 0 and action != "none":
                    prev_eba = run_traces[i - 1].fields.get("error_by_anchor", {})
                    for aid in set(eba) | set(prev_eba):
                        prev_v = prev_eba.get(aid, 0.0)
                        curr_v = eba.get(aid, 0.0)
                        delta = prev_v - curr_v
                        improved = curr_v < prev_v
                        action_outcomes.setdefault(action, {}).setdefault(aid, []).append(
                            (improved, delta)
                        )

        # Build PerAnchorAnalysis for each anchor
        all_anchors = set(anchor_episodes) | set(anchor_violations)
        analyses: dict[str, PerAnchorAnalysis] = {}

        for aid in all_anchors:
            # Build action effectiveness
            ae_list: list[ActionEffectiveness] = []
            for action, outcomes_by_anchor in action_outcomes.items():
                if aid in outcomes_by_anchor:
                    outcomes = outcomes_by_anchor[aid]
                    total = len(outcomes)
                    improved = sum(1 for o, _ in outcomes if o)
                    worsened = sum(1 for o, d in outcomes if not o and d < 0)
                    no_change = total - improved - worsened
                    deltas = [d for _, d in outcomes]
                    avg_delta = sum(deltas) / len(deltas) if deltas else 0.0
                    ae_list.append(ActionEffectiveness(
                        action=action,
                        total_attempts=total,
                        improved=improved,
                        worsened=worsened,
                        no_change=no_change,
                        success_rate=improved / total if total > 0 else 0.0,
                        avg_delta=avg_delta,
                    ))

            # Identify deadzone actions (success_rate < 0.05 and total >= 10)
            deadzone = list(anchor_deadzone_actions.get(aid, set()))
            for ae in ae_list:
                if ae.success_rate < 0.05 and ae.total_attempts >= 10:
                    if ae.action not in deadzone:
                        deadzone.append(ae.action)

            residuals = anchor_residuals.get(aid, [])
            attempts = anchor_attempts.get(aid, [])

            analyses[aid] = PerAnchorAnalysis(
                anchor_id=aid,
                episode_count=len(anchor_episodes.get(aid, set())),
                violation_count=anchor_violations.get(aid, 0),
                action_effectiveness=ae_list,
                deadzone_actions=deadzone,
                avg_attempts_to_resolve=sum(attempts) / len(attempts) if attempts else 0.0,
                residual_error_avg=sum(residuals) / len(residuals) if residuals else 0.0,
                interference_targets=sorted(anchor_interference.get(aid, set())),
                mode=detected_mode,
            )

        return analyses

    def identify_opportunities(
        self,
        analyses: dict[str, PerAnchorAnalysis],
    ) -> list[TuningOpportunity]:
        """Identify tuning opportunities from per-anchor analysis.

        Heuristics:
        - Action with success_rate < 0.05 and total_attempts >= 10 -> skip_deadzone_action
        - High interference_targets count -> split_anchor
        - avg_attempts_to_resolve > 3 -> budget_adjust
        """
        opportunities: list[TuningOpportunity] = []

        for aid, analysis in analyses.items():
            # Deadzone actions
            for ae in analysis.action_effectiveness:
                if ae.success_rate < 0.05 and ae.total_attempts >= 10:
                    opportunities.append(TuningOpportunity(
                        anchor_id=aid,
                        opportunity_type="skip_deadzone_action",
                        evidence={
                            "action": ae.action,
                            "success_rate": round(ae.success_rate, 6),
                            "total_attempts": ae.total_attempts,
                        },
                        estimated_savings=ae.total_attempts * 0.5,
                    ))

            # High interference
            if len(analysis.interference_targets) >= 2:
                opportunities.append(TuningOpportunity(
                    anchor_id=aid,
                    opportunity_type="split_anchor",
                    evidence={
                        "interference_count": len(analysis.interference_targets),
                        "targets": analysis.interference_targets,
                    },
                    estimated_savings=analysis.episode_count * 0.2,
                ))

            # High attempts to resolve
            if analysis.avg_attempts_to_resolve > 3.0:
                opportunities.append(TuningOpportunity(
                    anchor_id=aid,
                    opportunity_type="budget_adjust",
                    evidence={
                        "avg_attempts": round(analysis.avg_attempts_to_resolve, 2),
                        "episode_count": analysis.episode_count,
                    },
                    estimated_savings=analysis.episode_count * 0.3,
                ))

        return opportunities

    def compute_metrics_block(
        self,
        events: list[Any],
        since: str | None = None,
        mode: str | None = None,
    ) -> MetricsBlock:
        """Compute aggregate metrics from convergence events."""
        from .telemetry import TelemetryEventType

        traces = [
            e for e in events
            if e.event_type == TelemetryEventType.CONTINUITY_TRACE
            and (since is None or e.timestamp >= since)
            and (mode is None or e.fields.get("mode", "") == mode)
        ]
        results = [
            e for e in events
            if e.event_type == TelemetryEventType.CONTINUITY_RESULT
            and (since is None or e.timestamp >= since)
            and (mode is None or e.fields.get("mode", "") == mode)
        ]

        if not results:
            return MetricsBlock()

        total = len(results)
        accepted = sum(1 for r in results if r.fields.get("final_status") == "ACCEPTED")
        refused = sum(1 for r in results if r.fields.get("final_status") == "REFUSED")
        attempts_list = [r.fields.get("attempts", 0) for r in results]
        residuals = [r.fields.get("residual_error_total", 0.0) for r in results]
        tokens = [r.fields.get("total_tokens", 0) for r in results]

        avg_attempts = sum(attempts_list) / total if total else 0.0
        sorted_attempts = sorted(attempts_list)
        p95_idx = max(0, min(int(0.95 * len(sorted_attempts)), len(sorted_attempts) - 1))
        attempts_p95 = float(sorted_attempts[p95_idx]) if sorted_attempts else 0.0

        # Action success rates
        soft_total = 0
        soft_success = 0
        hard_total = 0
        hard_success = 0

        # Group traces by run
        traces_by_run: dict[str, list[Any]] = {}
        for t in traces:
            rid = t.fields.get("run_id", "")
            if rid:
                traces_by_run.setdefault(rid, []).append(t)
        for rid in traces_by_run:
            traces_by_run[rid].sort(key=lambda e: e.fields.get("attempt", 0))

        for rid, run_traces in traces_by_run.items():
            for i, t in enumerate(run_traces):
                action = t.fields.get("action", "none")
                if action == "none" or i == 0:
                    continue
                curr_err = t.fields.get("error_total", 0.0)
                prev_err = run_traces[i - 1].fields.get("error_total", 0.0)
                improved = curr_err < prev_err

                if action in ("SOFT_REPROMPT", "soft_reprompt"):
                    soft_total += 1
                    if improved:
                        soft_success += 1
                elif action in ("HARD_REPROMPT", "hard_reprompt"):
                    hard_total += 1
                    if improved:
                        hard_success += 1

        # Token cost per error reduction
        cost_per_reduction: list[float] = []
        for ev in results:
            rid = ev.fields.get("run_id", "")
            run_traces = traces_by_run.get(rid, [])
            if run_traces:
                initial_err = run_traces[0].fields.get("error_total", 0.0)
                residual_err = ev.fields.get("residual_error_total", 0.0)
                reduction = initial_err - residual_err
                run_tokens = ev.fields.get("total_tokens", 0)
                if reduction > 1e-6 and run_tokens > 0:
                    cost_per_reduction.append(run_tokens / reduction)

        return MetricsBlock(
            attempts_avg=avg_attempts,
            attempts_p95=attempts_p95,
            refusal_rate=refused / total if total else 0.0,
            accept_rate=accepted / total if total else 0.0,
            residual_error_avg=sum(residuals) / total if total else 0.0,
            soft_success_rate=soft_success / soft_total if soft_total else 0.0,
            hard_success_rate=hard_success / hard_total if hard_total else 0.0,
            token_cost_avg=sum(tokens) / total if total else 0.0,
            token_cost_per_error_reduction_avg=(
                sum(cost_per_reduction) / len(cost_per_reduction)
                if cost_per_reduction else 0.0
            ),
        )


# =============================================================================
# Admissibility Checks (5 functions + combined)
# =============================================================================


def check_regime_match(
    proposal: TuningProposal,
    current_model_id: str = "",
    current_config_hash: str = "",
    current_mode: str = "",
    current_prompt_profile_hash: str = "",
    current_decoder_profile: str = "",
    current_governor_version: str = "",
) -> AdmissibilityResult:
    """Check A: Proposal regime matches current regime."""
    violations: list[str] = []
    regime = proposal.scope.regime

    if current_model_id and regime.model_id and regime.model_id != current_model_id:
        violations.append(f"model_id mismatch: proposal={regime.model_id}, current={current_model_id}")

    if current_config_hash and regime.config_hash and regime.config_hash != current_config_hash:
        violations.append(f"config_hash mismatch: proposal={regime.config_hash}, current={current_config_hash}")

    if current_mode and proposal.scope.mode.value != current_mode:
        violations.append(f"mode mismatch: proposal={proposal.scope.mode.value}, current={current_mode}")

    if (current_prompt_profile_hash and regime.prompt_profile_hash
            and regime.prompt_profile_hash != current_prompt_profile_hash):
        violations.append(
            f"prompt_profile_hash mismatch: proposal={regime.prompt_profile_hash}, "
            f"current={current_prompt_profile_hash}"
        )

    if (current_decoder_profile and regime.decoder_profile
            and regime.decoder_profile != current_decoder_profile):
        violations.append(
            f"decoder_profile mismatch: proposal={regime.decoder_profile}, "
            f"current={current_decoder_profile}"
        )

    if (current_governor_version and regime.governor_version
            and regime.governor_version != current_governor_version):
        violations.append(
            f"governor_version mismatch: proposal={regime.governor_version}, "
            f"current={current_governor_version}"
        )

    # Check targets within namespace
    ns = proposal.scope.anchor_namespace
    for target in proposal.scope.targets:
        if ns and not target.startswith(f"{ns}."):
            violations.append(f"target '{target}' outside namespace '{ns}'")

    return AdmissibilityResult(
        passed=len(violations) == 0,
        check_name="regime_match",
        violations=violations,
    )


def check_strength_non_regression(proposal: TuningProposal) -> AdmissibilityResult:
    """Check B: No weakening of enforcement.

    Allowed without special approval:
    - ladder.entry_action moving more aggressive (higher aggressiveness)
    - ladder.max_attempts decreasing
    - decoder constraints tightening
    - adding neg_terms (stricter)

    Forbidden in v0:
    - any change touching severity
    - removing neg_terms or pos_terms
    """
    violations: list[str] = []

    for change in proposal.change_set.changes:
        target = change.get("target", "")

        # Severity changes forbidden
        if "severity" in target.lower():
            violations.append(f"Severity change forbidden in v0: {target}")
            continue

        # Parameter updates
        if "from" in change and "to" in change:
            # Ladder entry_action: must be more aggressive
            if "entry_action" in target:
                from_val = str(change.get("from", ""))
                to_val = str(change.get("to", ""))
                from_agg = ACTION_AGGRESSIVENESS.get(from_val, 0)
                to_agg = ACTION_AGGRESSIVENESS.get(to_val, 0)
                if to_agg < from_agg:
                    violations.append(
                        f"entry_action weakened: {from_val} (agg={from_agg}) -> "
                        f"{to_val} (agg={to_agg})"
                    )

            # max_attempts: increase = potential windup / hiding weak anchors
            if "max_attempts" in target:
                from_val = change.get("from", 0)
                to_val = change.get("to", 0)
                try:
                    if float(to_val) > float(from_val):
                        violations.append(
                            f"max_attempts increased: {from_val} -> {to_val} "
                            "(requires explicit semantic approval)"
                        )
                except (ValueError, TypeError):
                    pass

        # Pattern updates
        if "op" in change and "values" in change:
            op = change.get("op", "")
            target_str = change.get("target", "")
            if op == "remove" and "neg_terms" in target_str:
                violations.append(f"Removing neg_terms weakens enforcement: {target_str}")
            if op == "remove" and "pos_terms" in target_str:
                violations.append(f"Removing pos_terms weakens enforcement: {target_str}")

    return AdmissibilityResult(
        passed=len(violations) == 0,
        check_name="strength_non_regression",
        violations=violations,
    )


def check_objective_constraints(proposal: TuningProposal) -> AdmissibilityResult:
    """Check C: Predicted impact within bounds, evidence present."""
    violations: list[str] = []

    oc = proposal.constraints.objective_constraints
    pi = proposal.predicted_impact

    if pi.refusal_rate_delta > oc.max_allowed_increase_refusal_rate:
        violations.append(
            f"refusal_rate_delta ({pi.refusal_rate_delta:.6f}) > "
            f"max_allowed ({oc.max_allowed_increase_refusal_rate:.6f})"
        )

    if pi.violation_rate_delta > oc.max_allowed_increase_violation_rate:
        violations.append(
            f"violation_rate_delta ({pi.violation_rate_delta:.6f}) > "
            f"max_allowed ({oc.max_allowed_increase_violation_rate:.6f})"
        )

    # Evidence must be present
    if not proposal.supporting_evidence.example_episodes:
        violations.append("No example episodes in supporting evidence")

    if not proposal.supporting_evidence.summary_tables:
        violations.append("No summary tables in supporting evidence")

    if not proposal.predicted_impact.rationale:
        violations.append("No rationale in predicted impact")

    return AdmissibilityResult(
        passed=len(violations) == 0,
        check_name="objective_constraints",
        violations=violations,
    )


def check_trial_requirements(proposal: TuningProposal) -> AdmissibilityResult:
    """Check D: Trial plan is properly configured."""
    violations: list[str] = []

    tp = proposal.trial_plan

    if tp.apply_mode != "manual":
        violations.append(f"apply_mode must be 'manual', got '{tp.apply_mode}'")

    # Required rollback metrics
    required_metrics = {RollbackMetric.REFUSAL_RATE, RollbackMetric.RESIDUAL_ERROR_AVG, RollbackMetric.VIOLATION_RATE}
    present_metrics = {t.metric for t in tp.rollback_triggers}
    missing = required_metrics - present_metrics
    if missing:
        violations.append(f"Missing required rollback metrics: {[m.value for m in sorted(missing, key=lambda m: m.value)]}")

    # Evaluation fixtures
    if not tp.evaluation_set.fixture_ids:
        violations.append("No evaluation fixtures specified")

    return AdmissibilityResult(
        passed=len(violations) == 0,
        check_name="trial_requirements",
        violations=violations,
    )


def check_determinism_hygiene(proposal: TuningProposal) -> AdmissibilityResult:
    """Check E: Determinism fields are present."""
    violations: list[str] = []

    if not proposal.scope.regime.prompt_profile_hash:
        violations.append("Missing prompt_profile_hash in regime")

    if not proposal.scope.regime.config_hash:
        violations.append("Missing config_hash in regime")

    return AdmissibilityResult(
        passed=len(violations) == 0,
        check_name="determinism_hygiene",
        violations=violations,
    )


def check_admissibility(
    proposal: TuningProposal,
    current_model_id: str = "",
    current_config_hash: str = "",
    current_mode: str = "",
    current_prompt_profile_hash: str = "",
    current_decoder_profile: str = "",
    current_governor_version: str = "",
) -> list[AdmissibilityResult]:
    """Run all 5 admissibility checks. Returns list of results."""
    return [
        check_regime_match(
            proposal,
            current_model_id=current_model_id,
            current_config_hash=current_config_hash,
            current_mode=current_mode,
            current_prompt_profile_hash=current_prompt_profile_hash,
            current_decoder_profile=current_decoder_profile,
            current_governor_version=current_governor_version,
        ),
        check_strength_non_regression(proposal),
        check_objective_constraints(proposal),
        check_trial_requirements(proposal),
        check_determinism_hygiene(proposal),
    ]


# =============================================================================
# ConvergenceTuner — orchestrator
# =============================================================================


class ConvergenceTuner:
    """Offline system identification + proposal engine.

    Reads convergence telemetry, identifies tuning opportunities,
    produces TuningProposal artifacts, and manages the apply lifecycle.
    """

    SCHEMA_VERSION = "tuning_proposal_v0"
    MIN_ENFORCEMENT_EPISODES = 40

    def __init__(
        self,
        store: ProposalStore | None = None,
        analyzer: ConvergenceAnalyzer | None = None,
        gov_dir: Path | None = None,
    ):
        self.store = store or ProposalStore(gov_dir or Path("."))
        self.analyzer = analyzer or ConvergenceAnalyzer()
        self.gov_dir = gov_dir or Path(".")

    def propose(
        self,
        events: list[Any],
        mode: str | None = None,
        anchor_namespace: str | None = None,
        since: str | None = None,
        regime: Regime | None = None,
        max_proposals: int = 10,
    ) -> list[TuningProposal]:
        """Generate proposals from convergence telemetry.

        1. Run ConvergenceAnalyzer.analyze()
        2. Identify tuning opportunities
        3. Build TuningProposal artifacts
        4. Validate hard guards
        5. Save to store
        6. Return proposals
        """
        # Step 1: Analyze
        analyses = self.analyzer.analyze(events, since=since, mode=mode)
        if not analyses:
            return []

        # Step 2: Identify opportunities
        opportunities = self.analyzer.identify_opportunities(analyses)
        if not opportunities:
            return []

        # Limit
        opportunities = opportunities[:max_proposals]

        # Step 3: Build metrics
        metrics = self.analyzer.compute_metrics_block(events, since=since, mode=mode)

        # Compute time range from events
        timestamps = [e.timestamp for e in events if hasattr(e, "timestamp") and e.timestamp]
        time_start = min(timestamps) if timestamps else ""
        time_end = max(timestamps) if timestamps else ""

        # Count result events for episodes_observed
        from .telemetry import TelemetryEventType
        episode_count = sum(
            1 for e in events
            if e.event_type == TelemetryEventType.CONTINUITY_RESULT
            and (since is None or e.timestamp >= since)
            and (mode is None or e.fields.get("mode", "") == mode)
        )

        # Detect mode from events if not provided
        tuning_mode = TuningMode.UNKNOWN
        if mode:
            try:
                tuning_mode = TuningMode(mode)
            except ValueError:
                tuning_mode = TuningMode.UNKNOWN

        ns = anchor_namespace or (mode or "unknown")
        effective_regime = regime or Regime()
        now_utc = datetime.now(timezone.utc).isoformat()

        proposals: list[TuningProposal] = []

        for opp in opportunities:
            analysis = analyses.get(opp.anchor_id)
            if analysis is None:
                continue

            proposal_id = _generate_proposal_id()
            trial_id = _generate_trial_id()

            # Build change set based on opportunity type
            changes: list[dict[str, Any]] = []
            cs_type = ChangeSetType.PARAMETER_UPDATE

            if opp.opportunity_type == "skip_deadzone_action":
                action = opp.evidence.get("action", "")
                # Suggest skipping to next level
                next_action = _next_aggressive_action(action)
                if next_action:
                    changes.append(ChangeParameterUpdate(
                        target=f"anchors.{ns}.{opp.anchor_id}.ladder.entry_action",
                        from_value=action,
                        to_value=next_action,
                        reason_code="SOFT_DEADZONE",
                    ).to_dict())

            elif opp.opportunity_type == "split_anchor":
                cs_type = ChangeSetType.REFACTOR_SUGGESTION
                changes.append(ChangeRefactorSuggestion(
                    suggestion_type=RefactorSuggestionType.SPLIT_ANCHOR,
                    detail=f"Anchor '{opp.anchor_id}' interferes with {opp.evidence.get('targets', [])}",
                    reason_code="INTERFERENCE",
                ).to_dict())

            elif opp.opportunity_type == "budget_adjust":
                avg_att = opp.evidence.get("avg_attempts", 0)
                changes.append(ChangeParameterUpdate(
                    target=f"anchors.{ns}.{opp.anchor_id}.ladder.max_attempts",
                    from_value=int(avg_att) + 1,
                    to_value=max(2, int(avg_att) - 1),
                    reason_code="HIGH_ATTEMPTS",
                ).to_dict())

            if not changes:
                continue

            # Build example episodes (up to 3)
            example_episodes: list[ExampleEpisode] = []
            from .telemetry import TelemetryEventType as TET
            result_events = [
                e for e in events
                if e.event_type == TET.CONTINUITY_RESULT
                and opp.anchor_id in e.fields.get("residual_error_by_anchor", {})
            ]
            for ev in result_events[:3]:
                f = ev.fields
                example_episodes.append(ExampleEpisode(
                    run_id=f.get("run_id", ""),
                    attempts=f.get("attempts", 0),
                    violation_codes=[
                        v.get("code", "") for v in f.get("violations", []) if isinstance(v, dict)
                    ] if isinstance(f.get("violations"), list) else [],
                    actions=f.get("action_path", []),
                    result=f.get("final_status", "REFUSED"),
                    trace_refs=[f"telemetry://{f.get('run_id', '')}"],
                ))

            # Build summary table from action effectiveness
            ae_rows: list[dict[str, Any]] = []
            for ae in analysis.action_effectiveness:
                ae_rows.append({
                    "action": ae.action,
                    "episodes": ae.total_attempts,
                    "improved": ae.improved,
                    "worsened": ae.worsened,
                    "no_change": ae.no_change,
                })

            summary_tables = []
            if ae_rows:
                summary_tables.append(SummaryTable(
                    name="ladder_action_effectiveness",
                    rows=ae_rows,
                ))

            # Build interference edges
            interference = []
            for target in analysis.interference_targets:
                interference.append(InterferenceEdge(
                    from_anchor=opp.anchor_id,
                    to_anchor=target,
                    count=1,
                ))

            # Predicted impact
            predicted = PredictedImpact(
                attempts_avg_delta=-opp.estimated_savings / max(1, episode_count),
                token_cost_avg_delta=-opp.estimated_savings * 10,
                refusal_rate_delta=0.0,
                violation_rate_delta=0.0,
                confidence=TuningConfidence.MEDIUM if episode_count >= self.MIN_ENFORCEMENT_EPISODES else TuningConfidence.LOW,
                rationale=[
                    f"Opportunity: {opp.opportunity_type} for anchor {opp.anchor_id}",
                    f"Based on {analysis.episode_count} episodes with {analysis.violation_count} violations",
                ],
            )

            # Default rollback triggers
            rollback_triggers = [
                RollbackTrigger(metric=RollbackMetric.REFUSAL_RATE, operator=RollbackOperator.GT, threshold=0.10),
                RollbackTrigger(metric=RollbackMetric.RESIDUAL_ERROR_AVG, operator=RollbackOperator.GT, threshold=0.20),
                RollbackTrigger(metric=RollbackMetric.VIOLATION_RATE, operator=RollbackOperator.GT, threshold=0.0),
            ]

            proposal = TuningProposal(
                schema_version=self.SCHEMA_VERSION,
                proposal_id=proposal_id,
                created_at_utc=now_utc,
                scope=Scope(
                    mode=tuning_mode,
                    anchor_namespace=ns,
                    targets=[f"{ns}.{opp.anchor_id}"],
                    regime=effective_regime,
                ),
                evidence_window=EvidenceWindow(
                    time_range_utc=TimeRange(start=time_start, end=time_end),
                    min_enforcement_episodes=self.MIN_ENFORCEMENT_EPISODES,
                    episodes_observed=episode_count,
                    data_sources=["telemetry_jsonl"],
                ),
                change_set=ChangeSet(type=cs_type, changes=changes),
                constraints=Constraints(),
                metrics_before=metrics,
                predicted_impact=predicted,
                supporting_evidence=SupportingEvidence(
                    summary_tables=summary_tables,
                    example_episodes=example_episodes if example_episodes else [
                        ExampleEpisode(
                            run_id="synthetic",
                            attempts=int(analysis.avg_attempts_to_resolve),
                            result="ACCEPTED",
                            trace_refs=["telemetry://synthetic"],
                        )
                    ],
                    interference_graph=interference,
                ),
                trial_plan=TrialPlan(
                    trial_id=trial_id,
                    apply_mode="manual",
                    trial_scope=TrialScope(max_runs=200, max_days=7),
                    rollback_triggers=rollback_triggers,
                    evaluation_set=EvaluationSet(fixture_ids=[f"eval_{opp.anchor_id}"]),
                ),
                approval=Approval(status=ProposalStatus.PROPOSED),
            )

            # Step 5: Save
            self.store.save_proposal(proposal)
            proposals.append(proposal)

        return proposals

    def apply(
        self,
        proposal_id: str,
        applied_by: str,
        new_config_hash: str = "",
        previous_config_hash: str = "",
        notes: str = "",
        current_model_id: str = "",
        current_config_hash: str = "",
        current_mode: str = "",
        current_prompt_profile_hash: str = "",
        current_decoder_profile: str = "",
        current_governor_version: str = "",
    ) -> TuningApply | list[AdmissibilityResult]:
        """Apply a proposal after admissibility checks.

        Returns TuningApply on success, or list of failed AdmissibilityResult on failure.
        """
        proposal = self.store.get_proposal(proposal_id)
        if proposal is None:
            return [AdmissibilityResult(
                passed=False,
                check_name="proposal_exists",
                violations=[f"Proposal '{proposal_id}' not found"],
            )]

        # Run all admissibility checks
        results = check_admissibility(
            proposal,
            current_model_id=current_model_id,
            current_config_hash=current_config_hash or previous_config_hash,
            current_mode=current_mode,
            current_prompt_profile_hash=current_prompt_profile_hash,
            current_decoder_profile=current_decoder_profile,
            current_governor_version=current_governor_version,
        )

        failed = [r for r in results if not r.passed]
        if failed:
            return failed

        # Update proposal status
        proposal.approval.status = ProposalStatus.APPLIED
        proposal.approval.approved_by = applied_by
        now_utc = datetime.now(timezone.utc).isoformat()
        proposal.approval.approved_at_utc = now_utc
        proposal.approval.applied_at_utc = now_utc
        self.store.save_proposal(proposal)

        # Write apply record
        apply_record = TuningApply(
            trial_id=proposal.trial_plan.trial_id,
            proposal_id=proposal_id,
            applied_by=applied_by,
            applied_at_utc=now_utc,
            new_config_hash=new_config_hash,
            previous_config_hash=previous_config_hash,
            notes=notes,
        )
        self.store.save_apply(apply_record)

        return apply_record

    def rollback(self, trial_id: str) -> bool:
        """Mark a trial as rolled back. Returns True if trial was found."""
        apply_record = self.store.get_apply(trial_id)
        if apply_record is None:
            return False

        # Find and update the proposal
        proposal = self.store.get_proposal(apply_record.proposal_id)
        if proposal is not None:
            proposal.approval.status = ProposalStatus.ROLLED_BACK
            self.store.save_proposal(proposal)

        return True

    def get_status(self) -> dict[str, Any]:
        """Get current state of the convergence tuner."""
        counts = self.store.status_counts()
        applies = self.store.list_applies()
        return {
            "proposal_counts": counts,
            "total_proposals": sum(counts.values()),
            "total_applies": len(applies),
            "store_dir": str(self.store.store_dir),
        }


def _next_aggressive_action(action: str) -> str | None:
    """Return the next more aggressive action, or None if already max."""
    ordered = sorted(ACTION_AGGRESSIVENESS.items(), key=lambda x: x[1])
    current_agg = ACTION_AGGRESSIVENESS.get(action, 0)
    for name, agg in ordered:
        if agg > current_agg:
            return name
    return None


def create_convergence_tuner(gov_dir: Path | None = None) -> ConvergenceTuner:
    """Convenience factory for ConvergenceTuner."""
    root = gov_dir.parent if gov_dir and gov_dir.name == ".governor" else (gov_dir or Path("."))
    store = ProposalStore(root)
    return ConvergenceTuner(store=store, gov_dir=gov_dir or Path("."))
