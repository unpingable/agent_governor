"""
Measurement Integrity — Tidepool Defense.

Tool outputs treated as authoritative telemetry can be weaponized.
Trust predicate: trusted(z_t) ⟺ sig(z_t) ∧ schema(z_t).
Untrusted blobs quarantined, instruction masquerade detected, tools frozen.

Spec: MEASUREMENT_INTEGRITY_SPEC (Layer 2.1-B)
Invariant C: Only signed+schema tool outputs update state estimates.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TrustLevel(str, Enum):
    """Trust classification for tool output."""
    TRUSTED = "trusted"
    UNTRUSTED = "untrusted"
    QUARANTINED = "quarantined"


class AlertType(str, Enum):
    """Types of measurement integrity alerts."""
    UNTRUSTED_BLOB = "untrusted_blob"
    INSTRUCTION_MASQUERADE = "instruction_masquerade"
    SCHEMA_VIOLATION = "schema_violation"
    SIGNATURE_MISSING = "signature_missing"
    TOOL_FROZEN = "tool_frozen"


class FreezeReason(str, Enum):
    """Why a tool was frozen."""
    ADVERSARIAL_DISTURBANCE = "adversarial_disturbance"
    REPEATED_VIOLATIONS = "repeated_violations"
    MANUAL = "manual"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

UNTRUSTED_BLOB_PENALTY = 0.1
ADVERSARIAL_DISTURBANCE_PENALTY = 0.5

# Instruction masquerade patterns
INSTRUCTION_PATTERNS = [
    r"you are now",
    r"your (new )?(persona|identity|role)",
    r"you must (always|never)",
    r"from now on",
    r"remember that you",
    r"ignore (previous|prior|all) instructions",
    r"disregard (previous|prior|all)",
    r"system prompt",
    r"override (your|the) (rules|constraints|guidelines)",
]

# Tools that have side effects (freeze candidates)
SIDE_EFFECT_TOOLS = frozenset({
    "write_file", "execute", "send_email", "deploy",
    "delete", "modify", "create",
})

# Violation threshold before auto-freeze
AUTO_FREEZE_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ToolOutput:
    """A tool output with trust metadata."""
    tool_id: str
    payload: str
    signature: str = ""
    declared_schema: str = ""
    tool_pubkey: str = ""

    def content_hash(self) -> str:
        return hashlib.sha256(self.payload.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "tool_id": self.tool_id,
            "payload_hash": self.content_hash(),
            "has_signature": bool(self.signature),
            "has_schema": bool(self.declared_schema),
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ToolOutput:
        return cls(
            tool_id=d["tool_id"],
            payload=d.get("payload", ""),
            signature=d.get("signature", ""),
            declared_schema=d.get("declared_schema", ""),
            tool_pubkey=d.get("tool_pubkey", ""),
        )


@dataclass
class TrustResult:
    """Result of trust evaluation for a tool output."""
    level: TrustLevel
    reasons: list[str] = field(default_factory=list)
    patterns_matched: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"level": self.level.value, "reasons": self.reasons}
        if self.patterns_matched:
            d["patterns_matched"] = self.patterns_matched
        return d


@dataclass
class Alert:
    """A measurement integrity alert."""
    alert_type: AlertType
    source: str
    content_hash: str = ""
    action_taken: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    ts: str = ""

    def __post_init__(self) -> None:
        if not self.ts:
            self.ts = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_type": self.alert_type.value,
            "source": self.source,
            "content_hash": self.content_hash,
            "action_taken": self.action_taken,
            "details": self.details,
            "ts": self.ts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Alert:
        return cls(
            alert_type=AlertType(d["alert_type"]),
            source=d["source"],
            content_hash=d.get("content_hash", ""),
            action_taken=d.get("action_taken", ""),
            details=d.get("details", {}),
            ts=d.get("ts", ""),
        )


@dataclass
class MeasurementState:
    """Tracks measurement integrity state for a run."""
    run_id: str
    risk_score: float = 0.0
    alerts: list[Alert] = field(default_factory=list)
    frozen_tools: set[str] = field(default_factory=set)
    untrusted_count: int = 0
    quarantined_count: int = 0
    trusted_count: int = 0
    violation_counts: dict[str, int] = field(default_factory=dict)

    def freeze_tool(self, tool_id: str, reason: FreezeReason) -> None:
        self.frozen_tools.add(tool_id)
        self.alerts.append(Alert(
            alert_type=AlertType.TOOL_FROZEN,
            source=tool_id,
            action_taken=f"frozen: {reason.value}",
        ))

    def is_frozen(self, tool_id: str) -> bool:
        return tool_id in self.frozen_tools

    def record_violation(self, tool_id: str) -> int:
        """Record a violation for a tool. Returns new count."""
        self.violation_counts[tool_id] = self.violation_counts.get(tool_id, 0) + 1
        return self.violation_counts[tool_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "risk_score": self.risk_score,
            "alerts": [a.to_dict() for a in self.alerts],
            "frozen_tools": sorted(self.frozen_tools),
            "untrusted_count": self.untrusted_count,
            "quarantined_count": self.quarantined_count,
            "trusted_count": self.trusted_count,
            "violation_counts": self.violation_counts,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MeasurementState:
        return cls(
            run_id=d["run_id"],
            risk_score=d.get("risk_score", 0.0),
            alerts=[Alert.from_dict(a) for a in d.get("alerts", [])],
            frozen_tools=set(d.get("frozen_tools", [])),
            untrusted_count=d.get("untrusted_count", 0),
            quarantined_count=d.get("quarantined_count", 0),
            trusted_count=d.get("trusted_count", 0),
            violation_counts=d.get("violation_counts", {}),
        )


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def verify_signature(payload: str, signature: str, pubkey: str) -> bool:
    """Verify tool output signature.

    v0: Presence-based check. Real implementation would use cryptographic verification.
    """
    return bool(signature) and bool(pubkey)


def validate_schema(payload: str, schema: str) -> bool:
    """Validate tool output against declared schema.

    v0: Schema presence check. Real implementation would use JSON Schema validation.
    """
    if not schema:
        return False
    # v0: check that payload is valid JSON if schema declares JSON
    if "json" in schema.lower():
        try:
            json.loads(payload)
            return True
        except (json.JSONDecodeError, TypeError):
            return False
    return bool(schema)


def is_trusted(output: ToolOutput) -> bool:
    """Trust predicate: trusted(z_t) ⟺ sig(z_t) ∧ schema(z_t)."""
    return (
        verify_signature(output.payload, output.signature, output.tool_pubkey)
        and validate_schema(output.payload, output.declared_schema)
    )


def detect_instruction_masquerade(text: str) -> list[str]:
    """Detect instruction masquerade patterns in text.

    Returns list of matched pattern descriptions.
    """
    matches = []
    for pattern in INSTRUCTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            matches.append(pattern)
    return matches


def evaluate_output(
    output: ToolOutput, state: MeasurementState
) -> TrustResult:
    """Evaluate a tool output and update measurement state.

    Implements the full trust pipeline:
    1. Check if tool is frozen → reject
    2. Check trust predicate (sig + schema)
    3. Check for instruction masquerade
    4. Update state accordingly
    """
    # Frozen tool check
    if state.is_frozen(output.tool_id):
        state.quarantined_count += 1
        state.alerts.append(Alert(
            alert_type=AlertType.TOOL_FROZEN,
            source=output.tool_id,
            content_hash=output.content_hash(),
            action_taken="rejected (tool frozen)",
        ))
        return TrustResult(
            level=TrustLevel.QUARANTINED,
            reasons=["tool is frozen"],
        )

    # Instruction masquerade check (runs regardless of trust)
    masquerade_patterns = detect_instruction_masquerade(output.payload)
    if masquerade_patterns and not is_trusted(output):
        state.quarantined_count += 1
        state.risk_score += ADVERSARIAL_DISTURBANCE_PENALTY
        count = state.record_violation(output.tool_id)

        state.alerts.append(Alert(
            alert_type=AlertType.INSTRUCTION_MASQUERADE,
            source=output.tool_id,
            content_hash=output.content_hash(),
            action_taken="quarantined",
            details={"patterns": masquerade_patterns},
        ))

        # Auto-freeze side-effect tools on adversarial disturbance
        for tool in SIDE_EFFECT_TOOLS:
            if tool not in state.frozen_tools:
                state.freeze_tool(tool, FreezeReason.ADVERSARIAL_DISTURBANCE)

        # Auto-freeze source tool after threshold
        if count >= AUTO_FREEZE_THRESHOLD:
            state.freeze_tool(output.tool_id, FreezeReason.REPEATED_VIOLATIONS)

        return TrustResult(
            level=TrustLevel.QUARANTINED,
            reasons=["instruction masquerade detected"],
            patterns_matched=masquerade_patterns,
        )

    # Trust predicate
    if is_trusted(output):
        state.trusted_count += 1
        return TrustResult(level=TrustLevel.TRUSTED, reasons=["signature and schema valid"])

    # Untrusted
    state.untrusted_count += 1
    state.risk_score += UNTRUSTED_BLOB_PENALTY
    reasons = []
    if not output.signature:
        reasons.append("no signature")
    if not output.declared_schema:
        reasons.append("no schema")

    state.alerts.append(Alert(
        alert_type=AlertType.UNTRUSTED_BLOB,
        source=output.tool_id,
        content_hash=output.content_hash(),
        action_taken="stored as untrusted",
        details={"reasons": reasons},
    ))

    return TrustResult(level=TrustLevel.UNTRUSTED, reasons=reasons)


def check_invariant_c(state: MeasurementState) -> list[str]:
    """Check Invariant C: Only trusted outputs should update state.

    Returns list of violations (empty = compliant).
    """
    violations = []
    if state.untrusted_count > 0 and state.risk_score == 0:
        violations.append(
            "Untrusted blobs exist but risk score not updated — "
            "possible invariant C violation"
        )
    return violations


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class MeasurementStore:
    """Persistent store for measurement integrity state."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.measurement_dir = self.governor_dir / "measurement"

    def _ensure_dirs(self) -> None:
        self.measurement_dir.mkdir(parents=True, exist_ok=True)

    def save(self, state: MeasurementState) -> Path:
        self._ensure_dirs()
        path = self.measurement_dir / f"{state.run_id}.json"
        path.write_text(json.dumps(state.to_dict(), indent=2) + "\n")
        return path

    def load(self, run_id: str) -> MeasurementState | None:
        path = self.measurement_dir / f"{run_id}.json"
        if not path.exists():
            return None
        try:
            return MeasurementState.from_dict(json.loads(path.read_text()))
        except (json.JSONDecodeError, KeyError):
            return None

    def list_runs(self) -> list[str]:
        if not self.measurement_dir.exists():
            return []
        return sorted(f.stem for f in self.measurement_dir.glob("*.json"))


# ---------------------------------------------------------------------------
# Telemetry events
# ---------------------------------------------------------------------------

def make_measurement_event(
    action: str, run_id: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "measurement_integrity",
        "action": action,
        "run_id": run_id,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
