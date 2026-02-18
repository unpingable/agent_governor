# SPDX-License-Identifier: Apache-2.0
"""
GovernorViewModel: Canonical read-only derivation of governor state (schema v2).

Replaces the ad-hoc state() aggregation with a structured, typed ViewModel
containing 8 top-level sections: Session, Regime, Decisions, Claims, Evidence,
Violations, Execution, Stability.

No new storage — all data derived from existing subsystems.
"""

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "v2"


# =============================================================================
# View dataclasses
# =============================================================================


@dataclass
class SessionView:
    """Current governance session state."""

    mode: str  # "strict" or "exploratory"
    authority_level: str  # from boil preset authority_posture
    active_constraints: list[str]
    jurisdiction: str | None
    active_profile: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "authority_level": self.authority_level,
            "active_constraints": self.active_constraints,
            "jurisdiction": self.jurisdiction,
            "active_profile": self.active_profile,
        }


@dataclass
class RegimeView:
    """Operational regime status."""

    name: str  # ELASTIC, WARM, DUCTILE, UNSTABLE
    setpoints: dict[str, float]
    telemetry: dict[str, float]  # rejection_rate, contradiction_open_rate, claim_churn
    boil_mode: str | None
    transitions: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "setpoints": self.setpoints,
            "telemetry": self.telemetry,
            "boil_mode": self.boil_mode,
            "transitions": self.transitions,
        }


@dataclass
class DecisionView:
    """A governance decision (from proposals or decision ledger)."""

    id: str  # dec_{uuid[:12]}
    status: str  # accepted, rejected, pending
    type: str
    rationale: str
    dependencies: list[str]
    violations: list[str]
    source: str  # "proposal" or "decision_ledger"
    created_at: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "type": self.type,
            "rationale": self.rationale,
            "dependencies": self.dependencies,
            "violations": self.violations,
            "source": self.source,
            "created_at": self.created_at,
            "raw": self.raw,
        }


@dataclass
class ClaimView:
    """An epistemic claim."""

    id: str  # clm_{claim_id}
    state: str  # proposed, stabilized, stale, contradicted
    content: str
    confidence: float
    provenance: str
    evidence_links: list[str]  # ev_{ref_id} references
    conflicting_claims: list[str]
    stability: dict[str, Any]
    created_at: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "state": self.state,
            "content": self.content,
            "confidence": self.confidence,
            "provenance": self.provenance,
            "evidence_links": self.evidence_links,
            "conflicting_claims": self.conflicting_claims,
            "stability": self.stability,
            "created_at": self.created_at,
            "raw": self.raw,
        }


@dataclass
class EvidenceView:
    """A piece of evidence linked to claims."""

    id: str  # ev_{ref_id}
    type: str  # EvidenceType value
    source: str  # locator
    scope: str
    linked_claims: list[str]  # clm_{claim_id} references
    validity: float
    expiry: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "source": self.source,
            "scope": self.scope,
            "linked_claims": self.linked_claims,
            "validity": self.validity,
            "expiry": self.expiry,
        }


@dataclass
class ViolationView:
    """A governance violation."""

    id: str  # vio_audit_{id} or vio_drift_{hash}
    rule_breached: str
    triggering_decision: str
    severity: str  # low, medium, high, critical
    enforced_outcome: str
    resolution: str | None
    source_system: str  # "audit" or "drift"
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "rule_breached": self.rule_breached,
            "triggering_decision": self.triggering_decision,
            "severity": self.severity,
            "enforced_outcome": self.enforced_outcome,
            "resolution": self.resolution,
            "source_system": self.source_system,
            "detail": self.detail,
        }


@dataclass
class ExecutionActionView:
    """A single execution action."""

    id: str
    description: str
    status: str  # pending, blocked, running, completed
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class ExecutionView:
    """Execution state: pending, blocked, running, completed actions."""

    pending: list[ExecutionActionView]
    blocked: list[ExecutionActionView]
    running: list[ExecutionActionView]
    completed: list[ExecutionActionView]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pending": [a.to_dict() for a in self.pending],
            "blocked": [a.to_dict() for a in self.blocked],
            "running": [a.to_dict() for a in self.running],
            "completed": [a.to_dict() for a in self.completed],
        }


@dataclass
class StabilityView:
    """System stability metrics."""

    rejection_rate: float
    claim_churn: float
    contradiction_open_rate: float
    drift_alert: str  # NONE, WATCH, WARN, QUARANTINE
    drift_signals: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rejection_rate": self.rejection_rate,
            "claim_churn": self.claim_churn,
            "contradiction_open_rate": self.contradiction_open_rate,
            "drift_alert": self.drift_alert,
            "drift_signals": self.drift_signals,
        }


@dataclass
class GovernorViewModel:
    """Canonical read-only view of governor state (schema v2)."""

    schema_version: str = SCHEMA_VERSION
    generated_at: str = ""
    session: SessionView | None = None
    regime: RegimeView | None = None
    decisions: list[DecisionView] = field(default_factory=list)
    claims: list[ClaimView] = field(default_factory=list)
    evidence: list[EvidenceView] = field(default_factory=list)
    violations: list[ViolationView] = field(default_factory=list)
    execution: ExecutionView | None = None
    stability: StabilityView | None = None

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "session": self.session.to_dict() if self.session else None,
            "regime": self.regime.to_dict() if self.regime else None,
            "decisions": [d.to_dict() for d in self.decisions],
            "claims": [c.to_dict() for c in self.claims],
            "evidence": [e.to_dict() for e in self.evidence],
            "violations": [v.to_dict() for v in self.violations],
            "execution": self.execution.to_dict() if self.execution else None,
            "stability": self.stability.to_dict() if self.stability else None,
        }


# =============================================================================
# Claim state mapping
# =============================================================================


def _map_epistemic_status(status) -> str:
    """Map ClaimStatus / GroundedClaimStatus to ClaimView state string."""
    if status is None:
        return "proposed"

    s = str(status).upper()

    # ClaimStatus enum values
    if "SUPPORTED" in s:
        return "stabilized"
    if "CONTESTED" in s or "INVALIDATED" in s or "REFUSED" in s:
        return "contradicted"
    if "STALE" in s or "EXPIRED" in s:
        return "stale"
    if "BLOCKED" in s or "RETRACTED" in s:
        return "contradicted"

    return "proposed"


# =============================================================================
# Section builders
# =============================================================================


def build_session(gov_dir: Path, root: Path) -> SessionView | None:
    """Build session view from envelope, boil, jurisdiction, and profile state."""
    try:
        from .envelopes import get_current_envelope

        envelope = get_current_envelope(gov_dir)
        mode = envelope.mode.value if hasattr(envelope.mode, "value") else str(envelope.mode)
    except Exception:
        mode = "unknown"

    authority_level = "Balanced"
    try:
        from .boil import BoilController
        state_path = gov_dir / "boil_state.json"
        if state_path.exists():
            data = json.loads(state_path.read_text())
            controller = BoilController.from_dict(data)
            info = controller.get_preset_info()
            authority_level = info.get("authority_posture", "Balanced")
    except Exception:
        pass

    jurisdiction = None
    try:
        jm_path = gov_dir / "jurisdiction_state.json"
        if jm_path.exists():
            data = json.loads(jm_path.read_text())
            jurisdiction = data.get("current_jurisdiction", None)
    except Exception:
        pass

    active_profile = None
    try:
        profile_path = gov_dir / ".profile"
        if profile_path.exists():
            active_profile = profile_path.read_text().strip()
    except Exception:
        pass

    constraints: list[str] = []
    if mode == "strict":
        constraints.append("strict_envelope")
    if active_profile:
        constraints.append(f"profile:{active_profile}")
    if jurisdiction and jurisdiction != "factual":
        constraints.append(f"jurisdiction:{jurisdiction}")

    return SessionView(
        mode=mode,
        authority_level=authority_level,
        active_constraints=constraints,
        jurisdiction=jurisdiction,
        active_profile=active_profile,
    )


def build_regime(gov_dir: Path) -> RegimeView | None:
    """Build regime view from regime detector and boil controller."""
    from .regime import RegimeDetector
    from .boil import BoilController

    detector = RegimeDetector()
    state_path = gov_dir / "regime_state.json"
    if state_path.exists():
        data = json.loads(state_path.read_text())
        detector = RegimeDetector.from_dict(data)

    regime_name = detector.current_regime.value if hasattr(
        detector.current_regime, "value"
    ) else str(detector.current_regime)

    # Setpoints from thresholds
    setpoints: dict[str, float] = {}
    if detector.thresholds:
        t = detector.thresholds
        setpoints = {
            "hysteresis": getattr(t, "warm_hysteresis", 0.0),
            "tool_gain": getattr(t, "warm_tool_gain", 0.0),
            "relaxation_time": getattr(t, "warm_relaxation_time", 0.0),
        }

    # Telemetry from last signals
    telemetry: dict[str, float] = {}
    if detector.last_signals:
        sig = detector.last_signals
        telemetry = {
            "rejection_rate": getattr(sig, "rejection_rate", 0.0),
            "contradiction_open_rate": getattr(sig, "contradiction_open_rate", 0.0),
            "claim_churn": getattr(sig, "dangerous_claim_rate", 0.0),
        }

    # Boil mode
    boil_mode = None
    try:
        boil_path = gov_dir / "boil_state.json"
        if boil_path.exists():
            bdata = json.loads(boil_path.read_text())
            controller = BoilController.from_dict(bdata)
            boil_mode = controller.mode.value if hasattr(controller.mode, "value") else str(controller.mode)
    except Exception:
        pass

    # Transitions
    transitions: list[dict[str, Any]] = []
    try:
        for t in detector.transition_history[-5:]:
            transitions.append({
                "from": t.from_regime.value if hasattr(t.from_regime, "value") else str(t.from_regime),
                "to": t.to_regime.value if hasattr(t.to_regime, "value") else str(t.to_regime),
                "turn": getattr(t, "turn", None),
            })
    except Exception:
        pass

    return RegimeView(
        name=regime_name,
        setpoints=setpoints,
        telemetry=telemetry,
        boil_mode=boil_mode,
        transitions=transitions,
    )


def build_decisions(gov_dir: Path) -> list[DecisionView]:
    """Build decisions from proposals and decision ledger."""
    from .fsm import Proposal, ProposalState
    from .ledgers import DecisionLedger

    views: list[DecisionView] = []

    # From proposals
    try:
        proposals_path = gov_dir / "proposals.json"
        if proposals_path.exists():
            proposals = json.loads(proposals_path.read_text())
            for pid, data in proposals.items():
                proposal = Proposal.from_dict(data)
                state_val = proposal.state.value if hasattr(proposal.state, "value") else str(proposal.state)

                if state_val == "applied":
                    status = "accepted"
                elif state_val == "rejected":
                    status = "rejected"
                else:
                    status = "pending"

                claim_types = []
                for c in proposal.claims:
                    ct = c.type.value if hasattr(c.type, "value") else str(c.type)
                    claim_types.append(ct)

                rationale = ""
                if proposal.rejection:
                    rationale = getattr(proposal.rejection, "summary", "")

                created = getattr(proposal, "created_at", "")
                if hasattr(created, "isoformat"):
                    created = created.isoformat()

                views.append(DecisionView(
                    id=f"dec_{pid[:12]}",
                    status=status,
                    type=", ".join(claim_types) if claim_types else "unknown",
                    rationale=rationale,
                    dependencies=[],
                    violations=[],
                    source="proposal",
                    created_at=str(created),
                    raw=data,
                ))
    except Exception:
        pass

    # From decision ledger
    try:
        ledger = DecisionLedger(gov_dir)
        for d in ledger.query():
            d_dict = d.to_dict()
            topic = getattr(d, "topic", "")
            choice = getattr(d, "choice", "")

            views.append(DecisionView(
                id=f"dec_{str(d.id)[:12]}",
                status="accepted",
                type=f"{topic}: {choice}" if topic else "decision",
                rationale=d.rationale or "",
                dependencies=[],
                violations=[],
                source="decision_ledger",
                created_at=str(d.created_at),
                raw=d_dict,
            ))
    except Exception:
        pass

    return views


def build_claims(gov_dir: Path) -> list[ClaimView]:
    """Build claims from epistemic ledger."""
    views: list[ClaimView] = []

    try:
        # Re-use the cli helper pattern for loading epistemic ledger
        from .epistemic import EpistemicLedger
        db_path = gov_dir / "governor.db"
        if db_path.exists():
            from .storage import get_storage
            from .evidence_store import EvidenceStore
            storage = get_storage(gov_dir)
            evidence_store = EvidenceStore(storage)
            ledger = EpistemicLedger(storage=storage, evidence_store=evidence_store)
        else:
            ledger_path = gov_dir / "epistemic_ledger.json"
            if ledger_path.exists():
                data = json.loads(ledger_path.read_text())
                ledger = EpistemicLedger.from_dict(data)
            else:
                ledger = EpistemicLedger()

        for claim_id, claim in ledger.claims.items():
            # Map status
            epistemic_status = getattr(claim, "epistemic_status", None)
            grounded_status = getattr(claim, "status", None)
            state = _map_epistemic_status(epistemic_status)
            if state == "proposed" and grounded_status is not None:
                state = _map_epistemic_status(grounded_status)

            # Evidence links
            evidence_links = []
            for ref in claim.evidence_refs:
                evidence_links.append(f"ev_{ref.ref_id}")

            # Provenance
            prov = claim.provenance.value if hasattr(claim.provenance, "value") else str(claim.provenance)

            # Stability
            stability: dict[str, Any] = {}
            if epistemic_status is not None:
                es_val = epistemic_status.value if hasattr(epistemic_status, "value") else str(epistemic_status)
                stability["epistemic_status"] = es_val
            if grounded_status is not None:
                gs_val = grounded_status.value if hasattr(grounded_status, "value") else str(grounded_status)
                stability["grounded_status"] = gs_val

            views.append(ClaimView(
                id=f"clm_{claim_id}",
                state=state,
                content=claim.content,
                confidence=claim.confidence,
                provenance=prov,
                evidence_links=evidence_links,
                conflicting_claims=[],
                stability=stability,
                created_at=str(claim.created_at),
                raw={
                    "claim_id": claim_id,
                    "content": claim.content,
                    "confidence": claim.confidence,
                    "provenance": prov,
                },
            ))
    except Exception:
        pass

    return views


def build_evidence(claims: list[ClaimView], gov_dir: Path) -> list[EvidenceView]:
    """Build evidence views from claim evidence refs. Deduplicate by ref_id."""
    views: list[EvidenceView] = []
    seen: dict[str, EvidenceView] = {}

    try:
        # Load epistemic ledger to get actual evidence refs
        from .epistemic import EpistemicLedger
        db_path = gov_dir / "governor.db"
        if db_path.exists():
            from .storage import get_storage
            from .evidence_store import EvidenceStore
            storage = get_storage(gov_dir)
            evidence_store = EvidenceStore(storage)
            ledger = EpistemicLedger(storage=storage, evidence_store=evidence_store)
        else:
            ledger_path = gov_dir / "epistemic_ledger.json"
            if ledger_path.exists():
                data = json.loads(ledger_path.read_text())
                ledger = EpistemicLedger.from_dict(data)
            else:
                ledger = EpistemicLedger()

        for claim_id, claim in ledger.claims.items():
            clm_id = f"clm_{claim_id}"
            for ref in claim.evidence_refs:
                ev_id = f"ev_{ref.ref_id}"
                if ev_id in seen:
                    # Add claim link
                    if clm_id not in seen[ev_id].linked_claims:
                        seen[ev_id].linked_claims.append(clm_id)
                else:
                    ref_type = ref.ref_type.value if hasattr(ref.ref_type, "value") else str(ref.ref_type)
                    ev = EvidenceView(
                        id=ev_id,
                        type=ref_type,
                        source=ref.locator,
                        scope=ref.scope,
                        linked_claims=[clm_id],
                        validity=ref.confidence,
                        expiry=None,
                    )
                    seen[ev_id] = ev

        views = list(seen.values())
    except Exception:
        pass

    return views


def build_violations(gov_dir: Path) -> list[ViolationView]:
    """Build violations from audit pipeline and drift detector."""
    views: list[ViolationView] = []

    # From audit pipeline (problematic audits)
    try:
        from .audit import AuditPipeline
        pipeline = AuditPipeline()
        # Audit pipeline is in-memory; load from disk if audit history exists
        audit_path = gov_dir / "audit_history.json"
        if audit_path.exists():
            data = json.loads(audit_path.read_text())
            for entry in data:
                if entry.get("status") in ("ungrounded", "contradicted", "weak"):
                    audit_id = entry.get("audit_id", "unknown")
                    modes = entry.get("failure_modes", [])
                    severity = entry.get("severity", "low")
                    views.append(ViolationView(
                        id=f"vio_audit_{audit_id}",
                        rule_breached=", ".join(modes) if modes else "grounding_failure",
                        triggering_decision=entry.get("assertion_id", ""),
                        severity=severity,
                        enforced_outcome=entry.get("decision", "block"),
                        resolution=entry.get("resolution"),
                        source_system="audit",
                        detail=entry.get("notes", ""),
                    ))
    except Exception:
        pass

    # From drift detector (quarantined premises)
    try:
        from .drift import DriftDetector
        drift_path = gov_dir / "drift_detector.json"
        if drift_path.exists():
            ddata = json.loads(drift_path.read_text())
            detector = DriftDetector.from_dict(ddata)
            for rec in detector.quarantine.quarantined_premises():
                content_hash = rec.content_hash[:12]
                views.append(ViolationView(
                    id=f"vio_drift_{content_hash}",
                    rule_breached="premise_quarantine",
                    triggering_decision=rec.content_summary,
                    severity="high",
                    enforced_outcome="quarantined",
                    resolution="resolved" if rec.resolved else None,
                    source_system="drift",
                    detail=f"occurrences={rec.occurrences}, turns_without_evidence={rec.turns_without_evidence}",
                ))
    except Exception:
        pass

    return views


def build_execution(gov_dir: Path, root: Path) -> ExecutionView | None:
    """Build execution view from proposals and session manager."""
    pending: list[ExecutionActionView] = []
    blocked: list[ExecutionActionView] = []
    running: list[ExecutionActionView] = []
    completed: list[ExecutionActionView] = []

    # Proposals → action status
    try:
        from .fsm import Proposal
        proposals_path = gov_dir / "proposals.json"
        if proposals_path.exists():
            proposals = json.loads(proposals_path.read_text())
            for pid, data in proposals.items():
                proposal = Proposal.from_dict(data)
                state_val = proposal.state.value if hasattr(proposal.state, "value") else str(proposal.state)

                claim_desc = f"{len(proposal.claims)} claim(s)"
                action = ExecutionActionView(
                    id=pid[:12],
                    description=claim_desc,
                    status=state_val,
                    detail=f"proposal {pid[:8]}",
                )

                if state_val == "draft":
                    pending.append(action)
                elif state_val == "proposed":
                    pending.append(action)
                elif state_val == "verified":
                    pending.append(action)
                elif state_val == "applied":
                    completed.append(action)
                elif state_val == "rejected":
                    blocked.append(action)
    except Exception:
        pass

    # Autonomous sessions → running
    try:
        from .execution import SessionManager
        manager = SessionManager(root)
        for s in manager.list_sessions():
            s_dict = s.to_dict()
            status_val = s_dict.get("status", "unknown")
            action = ExecutionActionView(
                id=s_dict.get("session_id", "unknown")[:12],
                description=s_dict.get("task", ""),
                status=status_val,
                detail=json.dumps(s_dict.get("used", {})),
            )
            if status_val == "running":
                running.append(action)
            elif status_val in ("completed", "stopped"):
                completed.append(action)
            else:
                pending.append(action)
    except Exception:
        pass

    if not any([pending, blocked, running, completed]):
        return None

    return ExecutionView(
        pending=pending,
        blocked=blocked,
        running=running,
        completed=completed,
    )


def build_stability(gov_dir: Path) -> StabilityView | None:
    """Build stability view from regime and drift signals."""
    rejection_rate = 0.0
    claim_churn = 0.0
    contradiction_open_rate = 0.0
    drift_alert = "NONE"
    drift_signals: dict[str, float] = {}

    # Regime signals
    try:
        from .regime import RegimeDetector
        state_path = gov_dir / "regime_state.json"
        if state_path.exists():
            data = json.loads(state_path.read_text())
            detector = RegimeDetector.from_dict(data)
            if detector.last_signals:
                sig = detector.last_signals
                rejection_rate = getattr(sig, "rejection_rate", 0.0)
                contradiction_open_rate = getattr(sig, "contradiction_open_rate", 0.0)
                claim_churn = getattr(sig, "dangerous_claim_rate", 0.0)
    except Exception:
        pass

    # Drift signals
    try:
        from .drift import DriftDetector
        drift_path = gov_dir / "drift_detector.json"
        if drift_path.exists():
            ddata = json.loads(drift_path.read_text())
            detector = DriftDetector.from_dict(ddata)
            drift_alert = str(detector.current_alert).upper()
            if detector.last_signals:
                ds = detector.last_signals
                drift_signals = {
                    "premise_recurrence_rate": ds.premise_recurrence_rate,
                    "attention_skew": ds.attention_skew,
                    "temporal_coherence_gradient": ds.temporal_coherence_gradient,
                    "quarantined_premises": float(ds.quarantined_premises),
                }
    except Exception:
        pass

    return StabilityView(
        rejection_rate=rejection_rate,
        claim_churn=claim_churn,
        contradiction_open_rate=contradiction_open_rate,
        drift_alert=drift_alert,
        drift_signals=drift_signals,
    )


# =============================================================================
# Top-level builders
# =============================================================================


def build_viewmodel(gov_dir: Path, root: Path) -> GovernorViewModel:
    """Build the full GovernorViewModel from all subsystems.

    Each section is built in a try/except so one failure doesn't break others.
    """
    vm = GovernorViewModel()

    try:
        vm.session = build_session(gov_dir, root)
    except Exception:
        vm.session = None

    try:
        vm.regime = build_regime(gov_dir)
    except Exception:
        vm.regime = None

    try:
        vm.decisions = build_decisions(gov_dir)
    except Exception:
        vm.decisions = []

    try:
        vm.claims = build_claims(gov_dir)
    except Exception:
        vm.claims = []

    try:
        vm.evidence = build_evidence(vm.claims, gov_dir)
    except Exception:
        vm.evidence = []

    try:
        vm.violations = build_violations(gov_dir)
    except Exception:
        vm.violations = []

    try:
        vm.execution = build_execution(gov_dir, root)
    except Exception:
        vm.execution = None

    try:
        vm.stability = build_stability(gov_dir)
    except Exception:
        vm.stability = None

    return vm


def build_v1_state(gov_dir: Path, root: Path) -> dict[str, Any]:
    """Build the v1 state output (backward compat).

    Replicates the original state command output format.
    """
    from .fsm import Proposal
    from .ledgers import FactLedger, DecisionLedger
    from .storage import get_storage

    result: dict[str, Any] = {}

    # Proposals
    try:
        proposals_path = gov_dir / "proposals.json"
        if proposals_path.exists():
            proposals = json.loads(proposals_path.read_text())
            result["proposals"] = [
                Proposal.from_dict(data).to_dict()
                for _pid, data in proposals.items()
            ]
        else:
            result["proposals"] = []
    except Exception:
        result["proposals"] = []

    # Facts
    try:
        ledger = FactLedger(gov_dir)
        result["facts"] = [f.to_dict() for f in ledger.all()]
    except Exception:
        result["facts"] = []

    # Decisions
    try:
        ledger = DecisionLedger(gov_dir)
        result["decisions"] = [d.to_dict() for d in ledger.query()]
    except Exception:
        result["decisions"] = []

    # Tasks (SQLite v2 only)
    try:
        storage = get_storage(gov_dir)
        reservations = storage.query("reservations", order_by="started_at DESC")
        now = datetime.now(timezone.utc)
        tasks = []
        for res in reservations:
            completed = res["completed_at"] is not None
            expires = datetime.fromisoformat(res["expires_at"])
            expired = expires < now
            task_status = "completed" if completed else ("expired" if expired else "active")
            tasks.append({
                "id": res["id"],
                "task": res["task"],
                "agent_id": res["agent_id"],
                "scope": json.loads(res["scope_json"]),
                "status": task_status,
                "started_at": res["started_at"],
                "expires_at": res["expires_at"],
                "completed_at": res["completed_at"],
            })
        result["tasks"] = tasks
    except Exception:
        result["tasks"] = []

    # Regime
    try:
        from .regime import RegimeDetector
        state_path = gov_dir / "regime_state.json"
        detector = RegimeDetector()
        if state_path.exists():
            data = json.loads(state_path.read_text())
            detector = RegimeDetector.from_dict(data)
        result["regime"] = detector.get_state()
    except Exception:
        result["regime"] = None

    # Boil
    try:
        from .boil import BoilController
        boil_path = gov_dir / "boil_state.json"
        controller = BoilController()
        if boil_path.exists():
            data = json.loads(boil_path.read_text())
            controller = BoilController.from_dict(data)
        boil_state = controller.get_state()
        preset_info = controller.get_preset_info()
        result["boil"] = {**boil_state, "preset": preset_info}
    except Exception:
        result["boil"] = None

    # Autonomous sessions
    try:
        from .execution import SessionManager
        manager = SessionManager(root)
        sessions = manager.list_sessions()
        result["autonomous"] = [s.to_dict() for s in sessions]
    except Exception:
        result["autonomous"] = []

    return result
