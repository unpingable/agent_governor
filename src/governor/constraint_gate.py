# SPDX-License-Identifier: Apache-2.0
"""Constraint gate: formal admissibility checking via Z3 verifier sidecar.

Wraps the external `verifier` package (z3-verifier) as an optional gate
in the Governor pipeline.  When the verifier is installed, this gate
compiles upstream facts (Standing grants, Continuity memories, etc.)
and constraint rules into Z3, checks admissibility, and emits a gate
receipt with the verdict.

When the verifier is NOT installed, all operations gracefully degrade:
no import errors, no silent passes, just an explicit "unavailable" status.

Design:
- Governor never imports verifier internals directly
- Adapters in the verifier package normalize upstream state into typed IR
- This module maps verifier Verdicts into Governor gate receipts
- Fail-open: verifier errors are logged, never block the pipeline
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Optional import guard
# =============================================================================

try:
    # Try package import first (pip install -e), then flat import (PYTHONPATH)
    try:
        from verifier.models import (
            ConstraintAtom,
            ConstraintRule,
            Fact,
            FactContradiction,
            FailedRule,
            MissingFact,
            Proposal,
            Verdict,
        )
        from verifier.verifier import verify as _z3_verify
        from verifier.adapters import (
            make_proposal,
            memory_to_facts,
            standing_grant_to_facts,
        )
    except ImportError:
        from models import (  # type: ignore[no-redef]
            ConstraintAtom,
            ConstraintRule,
            Fact,
            FactContradiction,
            FailedRule,
            MissingFact,
            Proposal,
            Verdict,
        )
        from verifier import verify as _z3_verify  # type: ignore[no-redef]
        from adapters import (  # type: ignore[no-redef]
            make_proposal,
            memory_to_facts,
            standing_grant_to_facts,
        )

    VERIFIER_AVAILABLE = True
except ImportError:
    VERIFIER_AVAILABLE = False
    # Stubs for type checking when verifier not installed
    ConstraintAtom = None  # type: ignore[assignment,misc]
    ConstraintRule = None  # type: ignore[assignment,misc]
    Fact = None  # type: ignore[assignment,misc]
    FactContradiction = None  # type: ignore[assignment,misc]
    FailedRule = None  # type: ignore[assignment,misc]
    MissingFact = None  # type: ignore[assignment,misc]
    Proposal = None  # type: ignore[assignment,misc]
    Verdict = None  # type: ignore[assignment,misc]
    _z3_verify = None  # type: ignore[assignment]
    make_proposal = None  # type: ignore[assignment]
    memory_to_facts = None  # type: ignore[assignment]
    standing_grant_to_facts = None  # type: ignore[assignment]


# =============================================================================
# Status (prevents silent green when verifier unavailable)
# =============================================================================

@dataclass
class ConstraintGateStatus:
    """Machine-checkable availability status.

    When the verifier is not installed, verdict_ceiling is "observe" —
    the best the gate can claim is "I looked but couldn't check."
    """

    available: bool
    reason: str  # "ok", "verifier_not_installed", "error"

    def to_dict(self) -> dict[str, Any]:
        return {"available": self.available, "reason": self.reason}

    @property
    def verdict_ceiling(self) -> str:
        return "pass" if self.available else "observe"


# =============================================================================
# Gate result
# =============================================================================

@dataclass
class ConstraintGateResult:
    """Result of a constraint gate check.

    Maps verifier Verdict into Governor's vocabulary:
    - allowed → pass
    - denied → block
    - invalid_input → block (contradictory upstream state)
    - unavailable → observe (verifier not installed)
    - error → observe (verifier threw an exception)
    """

    verdict: str  # "pass" | "warn" | "block" | "observe"
    status: str  # verifier status: "allowed" | "denied" | "invalid_input" | "unavailable" | "error"
    schema_version: str | None = None  # verifier schema version, preserved for drift detection
    failed_rules: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    missing_facts: list[dict[str, Any]] = field(default_factory=list)
    contradictions: list[dict[str, Any]] = field(default_factory=list)
    used_facts: list[dict[str, Any]] = field(default_factory=list)
    timing_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "verdict": self.verdict,
            "status": self.status,
        }
        if self.schema_version is not None:
            d["verifier_schema_version"] = self.schema_version
        if self.failed_rules:
            d["failed_rules"] = self.failed_rules
        if self.warnings:
            d["warnings"] = self.warnings
        if self.missing_facts:
            d["missing_facts"] = self.missing_facts
        if self.contradictions:
            d["contradictions"] = self.contradictions
        if self.timing_ms is not None:
            d["timing_ms"] = self.timing_ms
        # used_facts deliberately excluded from default serialization
        # (potentially large, available on request)
        return d


# =============================================================================
# Verdict mapping
# =============================================================================

_VERIFIER_TO_GATE_VERDICT = {
    "allowed": "pass",
    "denied": "block",
    "invalid_input": "block",
}


# =============================================================================
# Constraint gate
# =============================================================================

GATE_NAME = "constraint_gate"


class ConstraintGate:
    """Formal constraint checking gate for Governor.

    Consumes upstream state via verifier adapters, runs Z3 constraint
    solving, and emits gate receipts.  Gracefully degrades when the
    verifier package is not installed.
    """

    def __init__(
        self,
        receipt_system: Any | None = None,
        rules: list[Any] | None = None,
    ):
        self._receipt_system = receipt_system
        self._rules: list[Any] = rules or []
        self._status = ConstraintGateStatus(
            available=VERIFIER_AVAILABLE,
            reason="ok" if VERIFIER_AVAILABLE else "verifier_not_installed",
        )

    @property
    def available(self) -> bool:
        return self._status.available

    @property
    def status(self) -> ConstraintGateStatus:
        return self._status

    def add_rule(self, rule: Any) -> None:
        """Add a constraint rule.  No-op if verifier unavailable."""
        self._rules.append(rule)

    def check(
        self,
        action: str,
        actor: str,
        target: str,
        scope: str,
        standing_grants: list[dict[str, Any]] | None = None,
        continuity_memories: list[dict[str, Any]] | None = None,
        extra_facts: list[Any] | None = None,
    ) -> ConstraintGateResult:
        """Check admissibility of a proposed action.

        Gathers facts from Standing grants and Continuity memories via
        verifier adapters, adds any extra facts, and runs Z3 constraint
        solving against the configured rules.

        Returns ConstraintGateResult with gate verdict and details.
        Emits a gate receipt if receipt_system is configured.
        """
        if not self.available:
            result = ConstraintGateResult(
                verdict="observe",
                status="unavailable",
            )
            self._try_emit_receipt(result, action, actor, target, scope)
            return result

        t0 = time.monotonic_ns()

        try:
            # Build proposal
            proposal = make_proposal(
                action=action,
                actor_principal_id=actor,
                target=target,
                scope=scope,
            )

            # Gather facts from upstream adapters
            facts: list = []

            for grant in (standing_grants or []):
                try:
                    facts.extend(standing_grant_to_facts(grant))
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning(
                        "constraint_gate: bad standing grant, skipping: %s", exc
                    )

            for memory in (continuity_memories or []):
                try:
                    facts.extend(memory_to_facts(memory))
                except (KeyError, TypeError, ValueError) as exc:
                    logger.warning(
                        "constraint_gate: bad continuity memory, skipping: %s", exc
                    )

            if extra_facts:
                facts.extend(extra_facts)

            # Run verifier
            verdict_obj = _z3_verify(proposal, facts, self._rules)

            t1 = time.monotonic_ns()
            timing_ms = (t1 - t0) / 1_000_000

            # Map to gate result
            gate_verdict = _VERIFIER_TO_GATE_VERDICT.get(
                verdict_obj.status, "observe"
            )

            # Promote to "warn" if only warnings (no deny-severity failures)
            if verdict_obj.status == "allowed" and verdict_obj.warnings:
                gate_verdict = "warn"

            result = ConstraintGateResult(
                verdict=gate_verdict,
                status=verdict_obj.status,
                schema_version=getattr(verdict_obj, "schema_version", None),
                failed_rules=[r.model_dump() for r in verdict_obj.failed_rules],
                warnings=[r.model_dump() for r in verdict_obj.warnings],
                missing_facts=[m.model_dump() for m in verdict_obj.missing_facts],
                contradictions=[c.model_dump() for c in verdict_obj.contradictions],
                used_facts=[f.model_dump() for f in verdict_obj.used_facts],
                timing_ms=round(timing_ms, 2),
            )

        except Exception as exc:
            t1 = time.monotonic_ns()
            timing_ms = (t1 - t0) / 1_000_000
            logger.warning(
                "constraint_gate: verifier error: %s", exc, exc_info=True
            )
            result = ConstraintGateResult(
                verdict="observe",
                status="error",
                timing_ms=round(timing_ms, 2),
            )

        self._try_emit_receipt(result, action, actor, target, scope)
        return result

    def _try_emit_receipt(
        self,
        result: ConstraintGateResult,
        action: str,
        actor: str,
        target: str,
        scope: str,
    ) -> None:
        """Emit gate receipt.  Fail-open: errors logged, never raised."""
        if self._receipt_system is None:
            return

        try:
            subject_bytes = f"{action}:{actor}:{target}:{scope}".encode("utf-8")

            # Evidence bundle: structured verdict, no raw content
            evidence: dict[str, Any] = {
                "verifier_status": result.status,
                "gate_verdict": result.verdict,
            }
            if result.schema_version is not None:
                evidence["verifier_schema_version"] = result.schema_version
            if result.failed_rules:
                evidence["failed_rules"] = result.failed_rules
            if result.warnings:
                evidence["warnings"] = result.warnings
            if result.missing_facts:
                evidence["missing_facts"] = result.missing_facts
            if result.contradictions:
                evidence["contradictions"] = result.contradictions
            if result.timing_ms is not None:
                evidence["timing_ms"] = result.timing_ms

            # Policy: rule IDs + gate config (not rule content)
            policy: dict[str, Any] = {
                "gate": GATE_NAME,
                "rule_count": len(self._rules),
                "verifier_available": self.available,
            }
            if self.available and self._rules:
                policy["rule_ids"] = [r.rule_id for r in self._rules]

            from governor.gate_receipt import make_timing

            timing = None
            if result.timing_ms is not None:
                # Approximate ns from ms for receipt timing
                timing = {"wall_ms": result.timing_ms}

            self._receipt_system.emit(
                gate=GATE_NAME,
                verdict=result.verdict,
                subject_kind="constraint_check",
                subject_bytes=subject_bytes,
                evidence_bundle=evidence,
                gate_config=policy,
                timing=timing,
            )
        except Exception as exc:
            logger.warning(
                "constraint_gate: receipt emission failed: %s", exc,
                exc_info=True,
            )
