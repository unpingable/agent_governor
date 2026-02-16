"""
Evidence Gate: Evidence-gated coding harness — kernel-only surface.
(Formerly maude_lite.py — renamed per MAUDE_RENAME_SPEC.md)

The minimal surface over the governor kernel. Activates only non-negotiable
constraints for code contexts, with no personality, no philosophy, no worldview.

**What it is**: An evidence-gated coding harness. A structural hallucination brake.
A claim validator for agent outputs.

**Tagline**: "Claims need evidence. Contradictions persist. Failures are loud."

Active constraints (kernel, non-negotiable):
- claim_evidence_coupling: HARD claims require evidence
- contradiction_persistence: Conflicts recorded, not erased
- accountability_clarity: Who owns this? What are the assumptions?
- failure_surface_explicitness: How does this fail?
- governance_locality: Constraints visible and local
- exit_shape: No bad endings
- meta_invariant: Don't solve unfelt problems

Disabled features (surface, opt-in):
- puppet_mode: No character voice
- persona: No persona
- tone_modulation: No tone envelope
- regime_detection: Custody only, always
- ticketing: No ticket creation
- journal: No knowledge base

Reference: ingest/maude-lite.md
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

logger = logging.getLogger(__name__)


# =============================================================================
# Evidence Gate → Kernel Verdict Mapping (single source of truth)
# =============================================================================

# Maps application-layer status to kernel Verdict vocabulary.
# BLOCKED → "fail" (not "unknown"): the gate made a definitive rejection.
# This mapping is used by kernel run emission and CLI verify output.
# Do not create parallel truth tables — use this constant everywhere.
STATUS_TO_KERNEL_VERDICT: dict[str, str] = {
    "OK": "pass",
    "WARN": "warn",
    "BLOCKED": "fail",
}


# =============================================================================
# Canonical JSON (matches receipt_kernel.envelope.canonical_json)
# =============================================================================


def _canonical_json(obj: Any) -> bytes:
    """Deterministic JSON for kernel evidence blobs."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


# =============================================================================
# Status Codes
# =============================================================================


class EvidenceGateStatus(str, Enum):
    """Status codes for Evidence Gate output validation."""

    OK = "OK"
    """Output passes all checks."""

    WARN = "WARN"
    """Output produced, but with concerns."""

    BLOCKED = "BLOCKED"
    """Output suppressed, cannot proceed."""


# =============================================================================
# Claim Types
# =============================================================================


class ClaimLevel(str, Enum):
    """Claim commitment levels."""

    SOFT = "SOFT"
    """Tentative claim — acknowledged uncertainty."""

    HARD = "HARD"
    """Committed claim — requires evidence."""


@dataclass
class EvidenceGateClaim:
    """A claim extracted from agent output."""

    id: str
    text: str
    level: ClaimLevel
    evidence: str | None = None
    conflicts_with: list[str] = field(default_factory=list)
    source_span: tuple[int, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "level": self.level.value,
            "evidence": self.evidence,
            "conflicts_with": self.conflicts_with,
            "source_span": list(self.source_span) if self.source_span else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceGateClaim:
        return cls(
            id=data["id"],
            text=data["text"],
            level=ClaimLevel(data["level"]),
            evidence=data.get("evidence"),
            conflicts_with=data.get("conflicts_with", []),
            source_span=tuple(data["source_span"]) if data.get("source_span") else None,
        )


@dataclass
class EvidenceGateCitation:
    """A citation/source reference."""

    source: str
    relevance: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "relevance": self.relevance}


# =============================================================================
# Input/Output Types
# =============================================================================


@dataclass
class EvidenceGateInput:
    """Input for Evidence Gate validation."""

    task: str
    context: str
    constraints: list[str] = field(default_factory=list)
    prior_claims: list[EvidenceGateClaim] = field(default_factory=list)
    strict: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "context": self.context,
            "constraints": self.constraints,
            "prior_claims": [c.to_dict() for c in self.prior_claims],
            "strict": self.strict,
        }


@dataclass
class EvidenceGateOutput:
    """Output from Evidence Gate validation."""

    # The work
    patch: str | None = None
    response: str | None = None

    # The accountability
    rationale: str = ""
    claims: list[EvidenceGateClaim] = field(default_factory=list)
    citations: list[EvidenceGateCitation] = field(default_factory=list)

    # The status
    status: EvidenceGateStatus = EvidenceGateStatus.OK
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # For contradiction tracking
    claim_ids: list[str] = field(default_factory=list)

    # Receipt kernel integration
    kernel_run_id: str | None = None
    kernel_ok: bool | None = None  # None = no bridge, True = success, False = write failed

    # Release taint (computed after kernel run, dict form of RunTaint)
    release_taint: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "patch": self.patch,
            "response": self.response,
            "rationale": self.rationale,
            "claims": [c.to_dict() for c in self.claims],
            "citations": [c.to_dict() for c in self.citations],
            "status": self.status.value,
            "blocking_reasons": self.blocking_reasons,
            "warnings": self.warnings,
            "claim_ids": self.claim_ids,
        }
        if self.kernel_run_id is not None:
            d["kernel_run_id"] = self.kernel_run_id
            d["kernel_ok"] = self.kernel_ok
        if self.release_taint is not None:
            d["release_taint"] = self.release_taint
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# =============================================================================
# Custody Scoring (from CODE_SRE_CONTROLLER spec)
# =============================================================================


@dataclass
class CustodyScore:
    """Custody scoring for code output."""

    ap: float  # Accountability perception
    ip: float  # Invariant coupling
    fp: float  # Failure explicitness

    @property
    def total(self) -> float:
        """Combined custody score (average of components)."""
        return (self.ap + self.ip + self.fp) / 3

    @property
    def passed(self) -> bool:
        """Does this score pass the custody threshold?"""
        return self.total >= CUSTODY_THRESHOLD

    @property
    def blocking_reasons(self) -> list[str]:
        """Get reasons for failing custody check."""
        reasons = []
        if self.ap < CUSTODY_THRESHOLD:
            reasons.append(f"accountability unclear (Ap={self.ap:.2f})")
        if self.ip < CUSTODY_THRESHOLD:
            reasons.append(f"invariant coupling weak (Ip={self.ip:.2f})")
        if self.fp < CUSTODY_THRESHOLD:
            reasons.append(f"failure modes not explicit (Fp={self.fp:.2f})")
        return reasons

    def to_dict(self) -> dict[str, Any]:
        return {
            "ap": self.ap,
            "ip": self.ip,
            "fp": self.fp,
            "total": self.total,
            "passed": self.passed,
        }


# Threshold for custody checks
CUSTODY_THRESHOLD = 0.5


# =============================================================================
# Configuration
# =============================================================================


@dataclass
class EvidenceGateConfig:
    """Configuration for Evidence Gate."""

    # Operating mode
    strict: bool = True
    """If True, HARD claims without evidence → BLOCKED. If False, → WARN."""

    # Thresholds
    custody_threshold: float = CUSTODY_THRESHOLD
    """Minimum custody score to pass."""

    evidence_required_for_hard: bool = True
    """Whether HARD claims require evidence."""

    contradiction_action: str = "warn"
    """Action on contradiction: 'warn' or 'block'."""

    # Kernel constraints (cannot be disabled)
    _kernel_constraints: list[str] = field(default_factory=lambda: [
        "claim_evidence_coupling",
        "contradiction_persistence",
        "accountability_clarity",
        "failure_surface_explicitness",
        "governance_locality",
        "exit_shape",
        "meta_invariant",
    ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "strict": self.strict,
            "custody_threshold": self.custody_threshold,
            "evidence_required_for_hard": self.evidence_required_for_hard,
            "contradiction_action": self.contradiction_action,
            "kernel_constraints": self._kernel_constraints,
        }


# =============================================================================
# Kernel Functions (the non-negotiable core)
# =============================================================================


# Patterns for claim extraction
HARD_CLAIM_PATTERNS = [
    re.compile(r"\bimproves?\s+(?:performance|speed|efficiency)\s+by\s+\d+", re.IGNORECASE),
    re.compile(r"\breduces?\s+(?:latency|time|cost)\s+by\s+\d+", re.IGNORECASE),
    re.compile(r"\bis\s+(?:faster|slower|better|worse)\s+than\b", re.IGNORECASE),
    re.compile(r"\bguarantees?\b", re.IGNORECASE),
    re.compile(r"\balways\s+(?:works?|succeeds?|fails?)\b", re.IGNORECASE),
    re.compile(r"\bnever\s+(?:fails?|crashes?|errors?)\b", re.IGNORECASE),
    re.compile(r"\bwill\s+(?:fix|solve|resolve)\b", re.IGNORECASE),
    re.compile(r"\bis\s+(?:safe|secure|thread-?safe)\b", re.IGNORECASE),
    re.compile(r"\bO\([^)]+\)\s+complexity\b", re.IGNORECASE),
]

SOFT_CLAIM_PATTERNS = [
    re.compile(r"\bmight\s+(?:improve|help|fix)\b", re.IGNORECASE),
    re.compile(r"\bshould\s+(?:improve|work|help)\b", re.IGNORECASE),
    re.compile(r"\bcould\s+(?:improve|help|fix)\b", re.IGNORECASE),
    re.compile(r"\bprobably\s+(?:works?|helps?|fixes?)\b", re.IGNORECASE),
    re.compile(r"\blikely\s+(?:to\s+)?(?:improve|help|fix)\b", re.IGNORECASE),
]

# Patterns for evidence detection
EVIDENCE_PATTERNS = [
    re.compile(r"\bbenchmark\s+(?:shows?|results?)\b", re.IGNORECASE),
    re.compile(r"\bprofil(?:er?|ing)\s+(?:shows?|output)\b", re.IGNORECASE),
    re.compile(r"\btests?\s+(?:pass|show|confirm)\b", re.IGNORECASE),
    re.compile(r"\baccording\s+to\s+(?:the\s+)?(?:docs?|documentation)\b", re.IGNORECASE),
    re.compile(r"\bper\s+(?:the\s+)?(?:spec|documentation|docs?)\b", re.IGNORECASE),
    re.compile(r"\btraceback\s+shows?\b", re.IGNORECASE),
    re.compile(r"\berror\s+message\s+(?:says?|shows?)\b", re.IGNORECASE),
    re.compile(r"\bquery\s+plan\s+(?:shows?|indicates?)\b", re.IGNORECASE),
]

# Patterns for accountability issues
ACCOUNTABILITY_PATTERNS = [
    re.compile(r"\bsomehow\b", re.IGNORECASE),
    re.compile(r"\bmagically\b", re.IGNORECASE),
    re.compile(r"\bautomatically\b.*\bhandles?\b", re.IGNORECASE),
    re.compile(r"\bjust\s+works?\b", re.IGNORECASE),
]

# Patterns for failure mode issues
FAILURE_MODE_PATTERNS = [
    re.compile(r"\bexcept\s*:\s*(?:pass|\.\.\.|$)", re.IGNORECASE),
    re.compile(r"\bcatch\s*\(\s*(?:Exception|Error|e)\s*\)", re.IGNORECASE),
    re.compile(r"\btry\s*{[^}]*}\s*catch\s*{[^}]*}\s*$", re.IGNORECASE | re.MULTILINE),
]

# Patterns for bad exit shapes
BAD_EXIT_PATTERNS = [
    re.compile(r"\bhope\s+this\s+helps?\b", re.IGNORECASE),
    re.compile(r"\blet\s+me\s+know\s+if\b", re.IGNORECASE),
    re.compile(r"\bfeel\s+free\s+to\b", re.IGNORECASE),
    re.compile(r"\bhappy\s+to\s+help\b", re.IGNORECASE),
    re.compile(r"\bgood\s+luck\b", re.IGNORECASE),
]


def generate_claim_id(text: str) -> str:
    """Generate a unique claim ID from text."""
    h = hashlib.sha256(text.encode()).hexdigest()[:8]
    return f"c{h}"


def extract_claims(text: str) -> list[EvidenceGateClaim]:
    """
    Extract claims from text.

    Identifies HARD claims (definitive assertions) and SOFT claims
    (tentative/conditional statements).
    """
    claims = []

    # Extract HARD claims
    for pattern in HARD_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            claim_text = match.group(0)
            claim_id = generate_claim_id(claim_text)
            # Check for duplicates
            if not any(c.id == claim_id for c in claims):
                claims.append(EvidenceGateClaim(
                    id=claim_id,
                    text=claim_text,
                    level=ClaimLevel.HARD,
                    source_span=(match.start(), match.end()),
                ))

    # Extract SOFT claims
    for pattern in SOFT_CLAIM_PATTERNS:
        for match in pattern.finditer(text):
            claim_text = match.group(0)
            claim_id = generate_claim_id(claim_text)
            # Check for duplicates
            if not any(c.id == claim_id for c in claims):
                claims.append(EvidenceGateClaim(
                    id=claim_id,
                    text=claim_text,
                    level=ClaimLevel.SOFT,
                    source_span=(match.start(), match.end()),
                ))

    return claims


def check_evidence(text: str) -> list[str]:
    """
    Check for evidence patterns in text.

    Returns list of evidence indicators found.
    """
    evidence = []
    for pattern in EVIDENCE_PATTERNS:
        for match in pattern.finditer(text):
            evidence.append(match.group(0))
    return evidence


def link_evidence_to_claims(
    claims: list[EvidenceGateClaim],
    evidence_indicators: list[str],
    text: str,
) -> list[EvidenceGateClaim]:
    """
    Link evidence to claims.

    Simple heuristic: if evidence appears within N characters of a claim,
    the claim is considered supported.
    """
    EVIDENCE_PROXIMITY = 500  # characters

    for claim in claims:
        if claim.source_span is None:
            continue

        claim_start, claim_end = claim.source_span
        claim_region = text[max(0, claim_start - EVIDENCE_PROXIMITY):claim_end + EVIDENCE_PROXIMITY]

        for evidence in evidence_indicators:
            if evidence.lower() in claim_region.lower():
                claim.evidence = evidence
                break

    return claims


def detect_contradictions(
    claims: list[EvidenceGateClaim],
    prior_claims: list[EvidenceGateClaim],
) -> list[EvidenceGateClaim]:
    """
    Detect contradictions between current and prior claims.

    Simple heuristic: Claims about the same subject with opposing
    sentiment (improves vs degrades, faster vs slower) conflict.
    """
    OPPOSING_PAIRS = [
        ("improves", "degrades"),
        ("faster", "slower"),
        ("better", "worse"),
        ("increases", "decreases"),
        ("safe", "unsafe"),
        ("secure", "insecure"),
    ]

    for claim in claims:
        claim_lower = claim.text.lower()
        for prior in prior_claims:
            prior_lower = prior.text.lower()
            for pos, neg in OPPOSING_PAIRS:
                if (pos in claim_lower and neg in prior_lower) or \
                   (neg in claim_lower and pos in prior_lower):
                    if prior.id not in claim.conflicts_with:
                        claim.conflicts_with.append(prior.id)

    return claims


def score_accountability(text: str) -> float:
    """
    Score accountability clarity (Ap).

    Returns 1.0 if no accountability issues, decreases with each issue found.
    """
    score = 1.0
    for pattern in ACCOUNTABILITY_PATTERNS:
        matches = pattern.findall(text)
        score -= 0.2 * len(matches)
    return max(0.0, score)


def score_failure_explicitness(text: str) -> float:
    """
    Score failure mode explicitness (Fp).

    Returns 1.0 if failure modes are explicit, decreases with broad
    exception handling or missing error handling.
    """
    score = 1.0

    # Penalize broad exception handling
    for pattern in FAILURE_MODE_PATTERNS:
        matches = pattern.findall(text)
        score -= 0.3 * len(matches)

    # Reward explicit error handling mentions
    explicit_patterns = [
        re.compile(r"\braises?\s+\w+Error\b", re.IGNORECASE),
        re.compile(r"\breturn\s+(?:None|null|error)\b", re.IGNORECASE),
        re.compile(r"\bif\s+error\b", re.IGNORECASE),
    ]
    for pattern in explicit_patterns:
        if pattern.search(text):
            score += 0.1

    return min(1.0, max(0.0, score))


def score_invariant_coupling(text: str) -> float:
    """
    Score invariant implementation coupling (Ip).

    Returns 1.0 if invariants are well-coupled, decreases with
    signs of weak coupling.
    """
    score = 0.8  # Start at 0.8, adjust based on signals

    # Positive signals (increase score)
    positive_patterns = [
        re.compile(r"\bassert\b", re.IGNORECASE),
        re.compile(r"\brequire\b", re.IGNORECASE),
        re.compile(r"\bvalidate\b", re.IGNORECASE),
        re.compile(r"\bcheck\b", re.IGNORECASE),
    ]
    for pattern in positive_patterns:
        if pattern.search(text):
            score += 0.1

    # Negative signals (decrease score)
    negative_patterns = [
        re.compile(r"\bTODO\b"),
        re.compile(r"\bFIXME\b"),
        re.compile(r"\bhack\b", re.IGNORECASE),
        re.compile(r"\bworkaround\b", re.IGNORECASE),
    ]
    for pattern in negative_patterns:
        if pattern.search(text):
            score -= 0.15

    return min(1.0, max(0.0, score))


def score_custody(text: str) -> CustodyScore:
    """
    Calculate full custody score (Ap, Ip, Fp).
    """
    return CustodyScore(
        ap=score_accountability(text),
        ip=score_invariant_coupling(text),
        fp=score_failure_explicitness(text),
    )


def check_exit_shape(text: str) -> list[str]:
    """
    Check for bad exit patterns.

    Returns list of bad patterns found.
    """
    bad_patterns = []
    for pattern in BAD_EXIT_PATTERNS:
        for match in pattern.finditer(text):
            bad_patterns.append(match.group(0))
    return bad_patterns


# =============================================================================
# JSONL Logging
# =============================================================================


@dataclass
class EvidenceGateEvent:
    """A structured event for JSONL logging."""

    timestamp: str
    event: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "event": self.event,
            **self.data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class EvidenceGateLogger:
    """JSONL logger for Evidence Gate events."""

    def __init__(self, log_path: Path | None = None):
        self.log_path = log_path
        self.events: list[EvidenceGateEvent] = []

    def log(self, event: str, **data: Any) -> None:
        """Log an event."""
        e = EvidenceGateEvent(
            timestamp=datetime.now().isoformat(),
            event=event,
            data=data,
        )
        self.events.append(e)

        if self.log_path:
            with open(self.log_path, "a") as f:
                f.write(e.to_json() + "\n")

    def get_events(self) -> list[dict[str, Any]]:
        """Get all logged events as dicts."""
        return [e.to_dict() for e in self.events]


# =============================================================================
# Main Validator
# =============================================================================


class EvidenceGate:
    """
    Evidence Gate: Evidence-gated coding harness.

    Usage:
        lite = EvidenceGate()
        result = lite.check(
            task="fix the null pointer in auth.py",
            context="./src/",
            output="Here's the fix...",
        )
        if result.status == EvidenceGateStatus.BLOCKED:
            print("BLOCKED:", result.blocking_reasons)
    """

    def __init__(
        self,
        config: EvidenceGateConfig | None = None,
        log_path: Path | None = None,
        receipt_system: Any | None = None,
        kernel_bridge: Any | None = None,
    ):
        self.config = config or EvidenceGateConfig()
        self.logger = EvidenceGateLogger(log_path)
        self.prior_claims: list[EvidenceGateClaim] = []
        self._receipt_system = receipt_system  # GateReceiptSystem or None
        self._kernel_bridge = kernel_bridge  # ReceiptKernelBridge or None

    def check(
        self,
        task: str,
        context: str,
        output: str,
        constraints: list[str] | None = None,
        prior_claims: list[EvidenceGateClaim] | None = None,
        oracle_evidence: list[Any] | None = None,
    ) -> EvidenceGateOutput:
        """
        Validate agent output against kernel constraints.

        Args:
            task: The task description
            context: The context (repo state, files, etc.)
            output: The agent's output to validate
            constraints: Additional constraints
            prior_claims: Prior claims for contradiction checking
            oracle_evidence: Oracle artifacts (e.g. OraclePytestLog) to
                attach as STRONG evidence. These are produced by real
                tool execution, not model narration.

        Returns:
            EvidenceGateOutput with status, claims, and any issues
        """
        self.logger.log("task_start", task=task)

        constraints = constraints or []
        prior = prior_claims or self.prior_claims

        result = EvidenceGateOutput()
        result.response = output

        # 1. Extract claims from output
        claims = extract_claims(output)
        self.logger.log("claims_extracted", count=len(claims))

        # 2. Check for evidence
        evidence = check_evidence(output)
        self.logger.log("evidence_found", evidence=evidence)

        # 3. Link evidence to claims
        claims = link_evidence_to_claims(claims, evidence, output)

        # 4. Check for contradictions with prior claims
        claims = detect_contradictions(claims, prior)

        # 5. Score custody
        custody = score_custody(output)
        self.logger.log("custody_score", **custody.to_dict())

        # 6. Check exit shape
        bad_exits = check_exit_shape(output)

        # 7. Evaluate results
        for claim in claims:
            self.logger.log("claim", **claim.to_dict())

            # Check HARD claims without evidence
            if claim.level == ClaimLevel.HARD and not claim.evidence:
                if self.config.strict:
                    result.status = EvidenceGateStatus.BLOCKED
                    reason = f"claim lacks evidence: \"{claim.text}\""
                    result.blocking_reasons.append(reason)
                    self.logger.log("blocked", reason=reason, claim_id=claim.id)
                else:
                    result.warnings.append(f"claim {claim.id} lacks evidence (SOFT, proceeding)")
                    self.logger.log("warn", reason="claim lacks evidence", claim_id=claim.id)
                    if result.status == EvidenceGateStatus.OK:
                        result.status = EvidenceGateStatus.WARN

            # Check contradictions
            if claim.conflicts_with:
                if self.config.contradiction_action == "block":
                    result.status = EvidenceGateStatus.BLOCKED
                    reason = f"contradicts prior claim ({', '.join(claim.conflicts_with)})"
                    result.blocking_reasons.append(reason)
                    self.logger.log("blocked", reason=reason, claim_id=claim.id)
                else:
                    result.warnings.append(f"conflicts with prior claim {claim.conflicts_with} (recorded)")
                    self.logger.log("warn", reason="contradiction", claim_id=claim.id, conflicts=claim.conflicts_with)
                    if result.status == EvidenceGateStatus.OK:
                        result.status = EvidenceGateStatus.WARN

        # Check custody score
        if not custody.passed:
            for reason in custody.blocking_reasons:
                if self.config.strict:
                    result.status = EvidenceGateStatus.BLOCKED
                    result.blocking_reasons.append(reason)
                    self.logger.log("blocked", reason=reason)
                else:
                    result.warnings.append(reason)
                    if result.status == EvidenceGateStatus.OK:
                        result.status = EvidenceGateStatus.WARN

        # Check exit shape
        for bad_exit in bad_exits:
            result.warnings.append(f"bad exit pattern: \"{bad_exit}\"")
            if result.status == EvidenceGateStatus.OK:
                result.status = EvidenceGateStatus.WARN

        # Finalize
        result.claims = claims
        result.claim_ids = [c.id for c in claims]

        # Store claims for future contradiction checking
        self.prior_claims.extend(claims)

        self.logger.log("output", status=result.status.value, warnings=result.warnings, blocking_reasons=result.blocking_reasons)

        # Emit gate receipt (if receipt system is configured)
        self._emit_receipt(output, result)

        # Emit receipt kernel run (if bridge is configured)
        self._emit_kernel_run(task, output, result, custody, oracle_evidence or [])

        return result

    def _emit_receipt(self, output: str, result: EvidenceGateOutput) -> None:
        """Emit a gate receipt for this check.

        If no receipt_system is configured, logs a 'receipt_suppressed' event
        so the absence is auditable.
        """
        if self._receipt_system is None:
            self.logger.log("receipt_suppressed", reason="no receipt system configured")
            return

        verdict_map = {
            EvidenceGateStatus.OK: "pass",
            EvidenceGateStatus.WARN: "warn",
            EvidenceGateStatus.BLOCKED: "block",
        }

        evidence_bundle = {
            "claims": [c.to_dict() for c in result.claims],
            "blocking_reasons": result.blocking_reasons,
            "warnings": result.warnings,
            "claim_ids": result.claim_ids,
        }

        self._receipt_system.emit(
            gate="evidence_gate",
            verdict=verdict_map[result.status],
            subject_kind="text",
            subject_bytes=output.encode("utf-8"),
            evidence_bundle=evidence_bundle,
            gate_config=self.config.to_dict(),
        )

    def _emit_kernel_run(
        self,
        task: str,
        output: str,
        result: EvidenceGateOutput,
        custody: CustodyScore,
        oracle_evidence: list[Any] | None = None,
    ) -> None:
        """Emit a complete receipt kernel run for this check.

        One check() = one kernel run. The kernel is the receipted mirror
        of the evidence gate, not a replacement.

        If the bridge is not configured or not available, this is a no-op.
        If a write fails, the failure is logged and result.kernel_ok is set
        to False — callers MUST check this to prevent silent green.
        """
        bridge = self._kernel_bridge
        if bridge is None:
            return
        if not bridge.available:
            self.logger.log("kernel_skipped", reason=bridge.status.reason)
            return

        run_id = str(uuid.uuid4())
        mode = "factual" if self.config.strict else "mixed"

        try:
            self._do_kernel_run(bridge, run_id, mode, task, output, result, custody, oracle_evidence or [])
            result.kernel_run_id = run_id
            result.kernel_ok = True
            self.logger.log("kernel_run_complete", run_id=run_id)

            # Compute release taint (informational, non-fatal)
            try:
                from governor.release_taint import compute_taint
                taint = compute_taint(bridge._store, run_id)
                result.release_taint = taint.to_dict()
            except Exception as exc:
                logger.warning("release taint computation failed: %s", exc)
        except Exception as exc:
            # CRITICAL: write failure must NOT produce silent green.
            result.kernel_run_id = run_id
            result.kernel_ok = False
            self.logger.log("kernel_write_failed", run_id=run_id, error=str(exc))
            logger.warning("receipt kernel write failed for run %s: %s", run_id, exc)

            # Belt: don't rely only on callers checking kernel_ok.
            # In strict/factual mode: kernel failure → BLOCKED (unverifiable = inadmissible).
            # In mixed mode: → WARN (acceptable uncertainty).
            msg = f"receipt kernel write failed (run {run_id[:8]}): verdict unverifiable"
            if self.config.strict:
                result.blocking_reasons.append(msg)
                result.status = EvidenceGateStatus.BLOCKED
            else:
                result.warnings.append(msg)
                if result.status == EvidenceGateStatus.OK:
                    result.status = EvidenceGateStatus.WARN

    def _do_kernel_run(
        self,
        bridge: Any,
        run_id: str,
        mode: str,
        task: str,
        output: str,
        result: EvidenceGateOutput,
        custody: CustodyScore,
        oracle_evidence: list[Any] | None = None,
    ) -> None:
        """Execute the full kernel run sequence. Raises on write failure."""

        # --- RUN_START ---
        bridge.ensure_run(run_id, meta={"mode": mode})
        bridge.run_start(run_id, "START", meta={
            "mode": mode,
            "task": task[:500],
            "strict": self.config.strict,
        })

        # --- COLLECT stage ---
        bridge.stage_advance(run_id, "START", "COLLECT")

        # Evidence: final_output (model-generated text being checked)
        _, output_blob = bridge.evidence_put(
            run_id, "COLLECT", "final_output",
            output.encode("utf-8"),
            content_type="text/plain",
            evidence_class="public",
            meta={"evidence_kind": "model:generated"},
        )

        # Evidence: oracle artifacts (real tool execution, STRONG)
        # Each oracle blob gets its own evidence_kind tag. Claims that
        # reference these blobs will have STRONG evidence in confidence.sanity.
        oracle_blob_refs: list[str] = []
        for oracle in (oracle_evidence or []):
            # Duck-type: anything with to_bytes() and a .kind attribute
            if hasattr(oracle, "to_bytes") and hasattr(oracle, "kind"):
                _, oracle_blob = bridge.evidence_put(
                    run_id, "COLLECT", oracle.kind.replace(":", "_"),
                    oracle.to_bytes(),
                    content_type="application/json",
                    evidence_class="public",
                    meta={
                        "evidence_kind": oracle.kind,
                        "oracle_class": getattr(oracle, "oracle_class", 0),
                    },
                )
                if oracle_blob:
                    oracle_blob_refs.append(oracle_blob.ref)

        # Evidence: claims_map (governor's extraction — oracle)
        output_ref = output_blob.ref if output_blob else None
        output_sha = output_blob.sha256 if output_blob else None
        claims_map = self._build_claims_map(result.claims, output_ref, output_sha, oracle_blob_refs)
        bridge.evidence_put(
            run_id, "COLLECT", "claims_map",
            _canonical_json(claims_map),
            content_type="application/json",
            evidence_class="public",
            meta={"evidence_kind": "oracle:static_analysis"},
        )

        # Evidence: tool_trace (evidence_gate has no tool system)
        # system="none" distinguishes "no tool system" from "tool system
        # recorded zero calls". Strength is WEAK because this doesn't prove
        # tools weren't invoked — only that we have no tool integration.
        tool_trace = {"schema_version": 1, "system": "none", "calls": []}
        bridge.evidence_put(
            run_id, "COLLECT", "tool_trace",
            _canonical_json(tool_trace),
            content_type="application/json",
            evidence_class="public",
            meta={"evidence_kind": "model:self_report"},
        )

        # --- EVALUATE stage ---
        bridge.stage_advance(run_id, "COLLECT", "EVALUATE")

        eval_results = self._build_eval_results(result, custody)
        overall_verdict = STATUS_TO_KERNEL_VERDICT.get(result.status.value, "unknown")
        eval_ref = bridge.record_evaluation(
            run_id, "EVALUATE",
            results=eval_results,
            overall_verdict=overall_verdict,
            evidence_complete=True,
        )

        # --- DECIDE stage ---
        bridge.stage_advance(run_id, "EVALUATE", "DECIDE")

        decision_ref = bridge.record_decision(
            run_id, "DECIDE",
            decision_id=f"eg_{run_id[:8]}",
            basis={
                "status": result.status.value,
                "blocking_reasons": result.blocking_reasons,
                "warnings": result.warnings,
                "custody": custody.to_dict(),
            },
            event_refs=[eval_ref] if eval_ref else None,
        )

        # --- FINALIZE stage ---
        bridge.stage_advance(run_id, "DECIDE", "FINALIZE")

        bridge.run_finalize(
            run_id, "FINALIZE",
            overall_verdict=overall_verdict,
            summary={
                "claim_count": len(result.claims),
                "status": result.status.value,
                "blocking_reasons": result.blocking_reasons,
                "custody_total": custody.total,
            },
            event_refs=[r for r in [eval_ref, decision_ref] if r],
        )

    @staticmethod
    def _build_claims_map(
        claims: list[EvidenceGateClaim],
        output_ref: str | None,
        output_sha: str | None,
        oracle_refs: list[str] | None = None,
    ) -> dict[str, Any]:
        """Build claims_map evidence blob from extracted claims.

        When oracle evidence is present, HARD claims get oracle blob refs
        in addition to the output ref. This is what makes confidence.sanity
        PASS: the evidence_kind on those blobs is oracle:* (STRONG), which
        satisfies the "high confidence needs strong evidence" invariant.
        """
        kernel_claims = []
        oracle_refs = oracle_refs or []
        for claim in claims:
            # All claims come from the output text
            evidence_refs = [output_ref] if output_ref else []
            confidence = "high" if claim.level == ClaimLevel.HARD else "low"

            # HARD claims get oracle refs — STRONG evidence backing
            if claim.level == ClaimLevel.HARD and oracle_refs:
                evidence_refs.extend(oracle_refs)

            kernel_claims.append({
                "id": claim.id,
                "text": claim.text,
                "evidence_refs": evidence_refs,
                "confidence": confidence,
                "tool_call_ids": [],
            })

        return {
            "schema_version": 1,
            "claims": kernel_claims,
            "output_ref": output_ref,
            "output_sha256": output_sha,
        }

    @staticmethod
    def _build_eval_results(
        result: EvidenceGateOutput,
        custody: CustodyScore,
    ) -> list[dict[str, Any]]:
        """Build evaluation results payload from evidence gate output."""
        results = []
        for reason in result.blocking_reasons:
            results.append({
                "check": "evidence_gate",
                "verdict": "fail",
                "message": reason,
            })
        for warning in result.warnings:
            results.append({
                "check": "evidence_gate",
                "verdict": "warn",
                "message": warning,
            })
        if not result.blocking_reasons and not result.warnings:
            results.append({
                "check": "evidence_gate",
                "verdict": "pass",
                "message": "all checks passed",
            })
        # Always include custody scores
        results.append({
            "check": "custody_score",
            "verdict": "pass" if custody.passed else "fail",
            "message": f"Ap={custody.ap:.2f} Ip={custody.ip:.2f} Fp={custody.fp:.2f}",
        })
        return results

    def validate_input(self, input_data: EvidenceGateInput) -> EvidenceGateOutput:
        """
        Validate using EvidenceGateInput structure.
        """
        self.config.strict = input_data.strict
        return self.check(
            task=input_data.task,
            context=input_data.context,
            output="",  # No output yet - just validate input
            constraints=input_data.constraints,
            prior_claims=input_data.prior_claims,
        )

    def format_status(self, result: EvidenceGateOutput) -> str:
        """
        Format status for display (no personality, bare status).
        """
        lines = []

        if result.status == EvidenceGateStatus.OK:
            lines.append("OK: output validated")
            if result.claims:
                lines.append(f"  - {len(result.claims)} claims made, all supported")
            lines.append("  - no contradictions with prior outputs")

        elif result.status == EvidenceGateStatus.WARN:
            lines.append("WARN: output produced with concerns")
            for warning in result.warnings:
                lines.append(f"  - {warning}")

        elif result.status == EvidenceGateStatus.BLOCKED:
            lines.append("BLOCKED: output suppressed")
            for reason in result.blocking_reasons:
                lines.append(f"  - {reason}")
            if result.blocking_reasons:
                lines.append("")
                lines.append("To proceed:")
                for reason in result.blocking_reasons:
                    if "lacks evidence" in reason:
                        lines.append("  - provide evidence or downgrade to SOFT claim")
                    elif "contradicts" in reason:
                        lines.append("  - reconcile with prior claim or explicitly override")
                    elif "accountability" in reason:
                        lines.append("  - clarify ownership and assumptions")
                    elif "failure" in reason:
                        lines.append("  - document failure modes explicitly")

        return "\n".join(lines)

    def get_log_events(self) -> list[dict[str, Any]]:
        """Get all logged events."""
        return self.logger.get_events()


# =============================================================================
# Agent Wrapper (integration pattern)
# =============================================================================


class AgentFn(Protocol):
    """Protocol for agent functions."""
    def __call__(self, task: str, context: str, **kwargs: Any) -> str: ...


class BlockedError(Exception):
    """Raised when Evidence Gate blocks agent output."""

    def __init__(self, reasons: list[str]):
        self.reasons = reasons
        super().__init__(f"BLOCKED: {', '.join(reasons)}")


def evidence_gate_wrapper(
    agent_fn: AgentFn,
    config: EvidenceGateConfig | None = None,
    receipt_system: Any | None = None,
) -> Callable[[str, str], str]:
    """
    Wrap any agent function with Evidence Gate validation.

    Usage:
        @evidence_gate_wrapper
        def my_agent(task, context, **kwargs):
            return "Here's the code..."

        result = my_agent("fix bug", "./src/")  # Validated!
    """
    lite = EvidenceGate(config=config, receipt_system=receipt_system)

    def wrapped(task: str, context: str, **kwargs: Any) -> str:
        # Get agent output
        output = agent_fn(task, context, **kwargs)

        # Validate with Evidence Gate
        result = lite.check(task=task, context=context, output=output)

        if result.status == EvidenceGateStatus.BLOCKED:
            raise BlockedError(result.blocking_reasons)

        return output

    return wrapped


# =============================================================================
# Convenience Functions
# =============================================================================


def check_output(
    output: str,
    task: str = "",
    context: str = "",
    strict: bool = True,
) -> EvidenceGateOutput:
    """
    Quick check of agent output.

    Usage:
        result = check_output("Here's the code...", task="fix bug")
        print(result.status)  # OK, WARN, or BLOCKED
    """
    config = EvidenceGateConfig(strict=strict)
    lite = EvidenceGate(config=config)
    return lite.check(task=task, context=context, output=output)


def format_blocking_reason(reason: str) -> str:
    """Format a blocking reason with resolution hint."""
    if "lacks evidence" in reason:
        return f"BLOCKED: {reason}\n  required: benchmark data, profiler output, or documentation\n  to proceed: provide evidence or downgrade to SOFT"
    elif "contradicts" in reason:
        return f"BLOCKED: {reason}\n  to proceed: reconcile with prior claim or explicitly override with rationale"
    elif "accountability" in reason:
        return f"BLOCKED: {reason}\n  to proceed: clarify ownership, assumptions, and responsibilities"
    elif "failure" in reason:
        return f"BLOCKED: {reason}\n  to proceed: document failure modes explicitly"
    else:
        return f"BLOCKED: {reason}"
