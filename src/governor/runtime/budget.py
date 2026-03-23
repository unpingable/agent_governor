# SPDX-License-Identifier: Apache-2.0
"""Budgeted execution: per-step spend tracking, run ledger, hard limits.

Phase 1: actual spend recording, aggregate ledger, violation detection.
No routing optimization, no estimated-vs-actual scoring, no recurrence.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Spend:
    """Multidimensional spend for one step or an entire run.

    Fields use None for "adapter cannot report this" and 0 for "measured zero."
    The distinction matters: 0 tokens means no tokens were used,
    None tokens means the adapter doesn't expose token counts.
    """

    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    usd_micros: int | None = None
    remote_calls: int = 0
    tool_calls: int = 0

    def __add__(self, other: Spend) -> Spend:
        def _add(a: int | None, b: int | None) -> int | None:
            if a is None and b is None:
                return None
            return (a or 0) + (b or 0)

        return Spend(
            latency_ms=_add(self.latency_ms, other.latency_ms),
            prompt_tokens=_add(self.prompt_tokens, other.prompt_tokens),
            completion_tokens=_add(self.completion_tokens, other.completion_tokens),
            total_tokens=_add(self.total_tokens, other.total_tokens),
            usd_micros=_add(self.usd_micros, other.usd_micros),
            remote_calls=self.remote_calls + other.remote_calls,
            tool_calls=self.tool_calls + other.tool_calls,
        )

    def to_dict(self) -> dict[str, int | None]:
        return {
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "usd_micros": self.usd_micros,
            "remote_calls": self.remote_calls,
            "tool_calls": self.tool_calls,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Spend:
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__})


@dataclass
class BudgetLimit:
    """One dimension limit."""

    dimension: str  # matches Spend field name
    limit: int
    hard: bool = True  # hard = deny on breach, soft = warn

    def to_dict(self) -> dict[str, Any]:
        return {"dimension": self.dimension, "limit": self.limit, "hard": self.hard}


@dataclass
class BudgetPolicy:
    """Budget constraints for a session/run."""

    policy_id: str = ""
    limits: list[BudgetLimit] = field(default_factory=list)
    max_steps: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "limits": [l.to_dict() for l in self.limits],
            "max_steps": self.max_steps,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BudgetPolicy:
        return cls(
            policy_id=d.get("policy_id", ""),
            limits=[BudgetLimit(**l) for l in d.get("limits", [])],
            max_steps=d.get("max_steps"),
        )

    def check(self, total: Spend, step_count: int) -> list[BudgetViolation]:
        """Check spend against limits. Returns violations."""
        violations = []
        for limit in self.limits:
            actual = getattr(total, limit.dimension, None)
            if actual is None:
                continue  # Can't enforce what we can't measure
            if actual > limit.limit:
                violations.append(BudgetViolation(
                    dimension=limit.dimension,
                    limit=limit.limit,
                    actual=actual,
                    hard=limit.hard,
                ))
        if self.max_steps is not None and step_count > self.max_steps:
            violations.append(BudgetViolation(
                dimension="steps",
                limit=self.max_steps,
                actual=step_count,
                hard=True,
            ))
        return violations

    def would_breach_hard(self, total: Spend, step_count: int) -> BudgetViolation | None:
        """Return the first hard violation, or None if within budget."""
        for v in self.check(total, step_count):
            if v.hard:
                return v
        return None


@dataclass
class BudgetViolation:
    """A budget limit was exceeded."""

    dimension: str
    limit: int
    actual: int
    hard: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "limit": self.limit,
            "actual": self.actual,
            "hard": self.hard,
        }


@dataclass
class StepSpend:
    """Spend record for one step (tool call or model invocation)."""

    step_index: int
    step_kind: str  # model | tool | retrieval
    tool_name: str | None = None
    model: str | None = None
    provider_kind: str = "local"  # local | remote | hybrid
    spend: Spend = field(default_factory=Spend)
    started_at: str = ""
    ended_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "step_kind": self.step_kind,
            "tool_name": self.tool_name,
            "model": self.model,
            "provider_kind": self.provider_kind,
            "spend": self.spend.to_dict(),
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }


@dataclass
class RunBudgetLedger:
    """Aggregate spend for an entire run/session."""

    session_id: str
    policy_id: str = ""
    total_spend: Spend = field(default_factory=Spend)
    total_steps: int = 0
    total_remote_hops: int = 0
    violations: list[BudgetViolation] = field(default_factory=list)
    steps: list[StepSpend] = field(default_factory=list)

    def record_step(self, step: StepSpend) -> BudgetViolation | None:
        """Record a step's spend. Returns hard violation if budget breached."""
        self.steps.append(step)
        self.total_spend = self.total_spend + step.spend
        self.total_steps += 1
        if step.provider_kind == "remote":
            self.total_remote_hops += 1
        return None  # Caller checks policy separately

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "policy_id": self.policy_id,
            "total_spend": self.total_spend.to_dict(),
            "total_steps": self.total_steps,
            "total_remote_hops": self.total_remote_hops,
            "violations": [v.to_dict() for v in self.violations],
        }


def default_budget_policy() -> BudgetPolicy:
    """Reasonable defaults for a supervised session."""
    return BudgetPolicy(
        policy_id="default",
        limits=[
            BudgetLimit(dimension="total_tokens", limit=500_000, hard=True),
            BudgetLimit(dimension="tool_calls", limit=100, hard=True),
            BudgetLimit(dimension="remote_calls", limit=50, hard=True),
        ],
        max_steps=200,
    )
