# SPDX-License-Identifier: Apache-2.0
"""
Composition-aware capability gating (GOV-GAP-CHAIN-001, Phase 2B).

Detects denied action compositions — sequences of tool calls that are
individually benign but harmful in combination (e.g. read_file(secrets.env)
followed by http_post(attacker.com)).

Phase 2B is **detect-only**: signals + receipts, no execution blocking.
ChainGate.evaluate() is pure — returns results, no side effects.
Daemon owns persistence and receipt emission.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from .gate_receipt import canonical_json, content_hash

logger = logging.getLogger(__name__)

# =============================================================================
# Versioned vocabulary enums
# =============================================================================


class CapabilityClass(str, Enum):
    """cap-class-v1. Maps to policy_engine.Capability where applicable."""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    NETWORK_EGRESS = "network_egress"
    NETWORK_INGRESS = "network_ingress"
    SHELL_EXEC = "shell_exec"
    CODE_EXEC = "code_exec"
    MODEL_CALL = "model_call"
    UNKNOWN = "unknown"


class TrustDomain(str, Enum):
    """trust-v1."""
    LOCAL = "local"
    SAME_ORG = "same_org"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class DataSensitivity(str, Enum):
    """sens-v1."""
    NONE = "none"
    INTERNAL = "internal"
    SECRET_CANDIDATE = "secret_candidate"
    CLASSIFIED = "classified"


# Explicit ordering — avoids cursed lexicographic comparison
SENSITIVITY_ORDER: dict[str, int] = {
    "none": 0,
    "internal": 1,
    "secret_candidate": 2,
    "classified": 3,
}


def sensitivity_gte(a: DataSensitivity, b: DataSensitivity) -> bool:
    """True if sensitivity *a* >= *b* in the ordering."""
    return SENSITIVITY_ORDER[a.value] >= SENSITIVITY_ORDER[b.value]


class AnnotationSource(str, Enum):
    PROVENANCE_MODULE = "provenance"
    INLINE_PATH_HEURISTIC = "path_heuristic"
    TOOL_METADATA = "tool_metadata"
    FALLBACK = "fallback"


# =============================================================================
# ActionStep dataclass
# =============================================================================

# Fields included in action_log_hash (volatile fields excluded)
HASHED_STEP_FIELDS = (
    "step_index",
    "tool_id",
    "capability_class",
    "trust_domain",
    "data_sensitivity",
    "result_status",
    "args_hash",
)


@dataclass(frozen=True)
class ActionStep:
    tool_id: str
    capability_class: CapabilityClass
    trust_domain: TrustDomain
    data_sensitivity: DataSensitivity
    result_status: str  # "ok" | "failed" | "timeout"
    args_hash: str      # H(canonical_json(tool_arguments))
    # Annotation provenance
    capability_source: AnnotationSource = AnnotationSource.FALLBACK
    sensitivity_source: AnnotationSource = AnnotationSource.FALLBACK
    trust_domain_source: AnnotationSource = AnnotationSource.FALLBACK
    # Volatile (excluded from action_log_hash)
    timestamp: str | None = None
    duration_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "tool_id": self.tool_id,
            "capability_class": self.capability_class.value,
            "trust_domain": self.trust_domain.value,
            "data_sensitivity": self.data_sensitivity.value,
            "result_status": self.result_status,
            "args_hash": self.args_hash,
            "capability_source": self.capability_source.value,
            "sensitivity_source": self.sensitivity_source.value,
            "trust_domain_source": self.trust_domain_source.value,
        }
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionStep:
        return cls(
            tool_id=data["tool_id"],
            capability_class=CapabilityClass(data["capability_class"]),
            trust_domain=TrustDomain(data["trust_domain"]),
            data_sensitivity=DataSensitivity(data["data_sensitivity"]),
            result_status=data["result_status"],
            args_hash=data["args_hash"],
            capability_source=AnnotationSource(
                data.get("capability_source", "fallback")
            ),
            sensitivity_source=AnnotationSource(
                data.get("sensitivity_source", "fallback")
            ),
            trust_domain_source=AnnotationSource(
                data.get("trust_domain_source", "fallback")
            ),
            timestamp=data.get("timestamp"),
            duration_ms=data.get("duration_ms"),
        )


# =============================================================================
# CompositionRule + ChainRuleSet
# =============================================================================


@dataclass(frozen=True)
class CompositionRule:
    rule_id: str
    description: str = ""
    # Prior step condition (any prior step matching triggers)
    prior_sensitivity_gte: DataSensitivity | None = None
    prior_capability: CapabilityClass | None = None
    prior_trust_domain: TrustDomain | None = None
    # Proposed step condition
    proposed_capability: CapabilityClass | None = None
    proposed_trust_domain: TrustDomain | None = None
    # Exception clause (at most one per rule in v1)
    unless_condition: str | None = None
    # Effect
    effect: str = "deny"  # "deny" | "escalate"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"rule_id": self.rule_id}
        if self.description:
            d["description"] = self.description
        if self.prior_sensitivity_gte is not None:
            d["prior_sensitivity_gte"] = self.prior_sensitivity_gte.value
        if self.prior_capability is not None:
            d["prior_capability"] = self.prior_capability.value
        if self.prior_trust_domain is not None:
            d["prior_trust_domain"] = self.prior_trust_domain.value
        if self.proposed_capability is not None:
            d["proposed_capability"] = self.proposed_capability.value
        if self.proposed_trust_domain is not None:
            d["proposed_trust_domain"] = self.proposed_trust_domain.value
        if self.unless_condition is not None:
            d["unless_condition"] = self.unless_condition
        d["effect"] = self.effect
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CompositionRule:
        return cls(
            rule_id=data["rule_id"],
            description=data.get("description", ""),
            prior_sensitivity_gte=(
                DataSensitivity(data["prior_sensitivity_gte"])
                if data.get("prior_sensitivity_gte") is not None else None
            ),
            prior_capability=(
                CapabilityClass(data["prior_capability"])
                if data.get("prior_capability") is not None else None
            ),
            prior_trust_domain=(
                TrustDomain(data["prior_trust_domain"])
                if data.get("prior_trust_domain") is not None else None
            ),
            proposed_capability=(
                CapabilityClass(data["proposed_capability"])
                if data.get("proposed_capability") is not None else None
            ),
            proposed_trust_domain=(
                TrustDomain(data["proposed_trust_domain"])
                if data.get("proposed_trust_domain") is not None else None
            ),
            unless_condition=data.get("unless_condition"),
            effect=data.get("effect", "deny"),
        )


@dataclass(frozen=True)
class ChainRuleSet:
    rules: tuple[CompositionRule, ...] = ()
    description: str = ""
    rule_set_version: str = "1.0.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "rules": [r.to_dict() for r in self.rules],
            "description": self.description,
            "rule_set_version": self.rule_set_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChainRuleSet:
        return cls(
            rules=tuple(
                CompositionRule.from_dict(r) for r in data.get("rules", [])
            ),
            description=data.get("description", ""),
            rule_set_version=data.get("rule_set_version", "1.0.0"),
        )


# =============================================================================
# ActionLog
# =============================================================================


@dataclass
class ActionLog:
    correlation_id: str
    steps: list[ActionStep] = field(default_factory=list)
    created_at: str = ""
    # Dedupe state: key = "{rule_id}:{edge_key}" → count
    dedupe_counts: dict[str, int] = field(default_factory=dict)

    def append(self, step: ActionStep) -> None:
        self.steps.append(step)

    def record_match(self, dedupe_key: str) -> int:
        """Increment and return count. 1 = first match (full receipt)."""
        self.dedupe_counts[dedupe_key] = self.dedupe_counts.get(dedupe_key, 0) + 1
        return self.dedupe_counts[dedupe_key]

    def to_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "dedupe_counts": dict(self.dedupe_counts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionLog:
        return cls(
            correlation_id=data["correlation_id"],
            steps=[ActionStep.from_dict(s) for s in data.get("steps", [])],
            created_at=data.get("created_at", ""),
            dedupe_counts=dict(data.get("dedupe_counts", {})),
        )


# =============================================================================
# Hashing
# =============================================================================


def compute_action_log_hash(steps: list[ActionStep]) -> tuple[bytes, str]:
    """Returns (canonical_bytes, hex_digest) for the normalized step array.

    Only HASHED_STEP_FIELDS are included. Timestamps, durations, and
    annotation sources are excluded.
    """
    normalized = []
    for i, step in enumerate(steps):
        normalized.append({
            "step_index": i,
            "tool_id": step.tool_id,
            "capability_class": step.capability_class.value,
            "trust_domain": step.trust_domain.value,
            "data_sensitivity": step.data_sensitivity.value,
            "result_status": step.result_status,
            "args_hash": step.args_hash,
        })
    raw = canonical_json({"steps": normalized})
    return raw, hashlib.sha256(raw).hexdigest()


# =============================================================================
# Annotation — server-owned, mechanical
# =============================================================================

# Tool ID → CapabilityClass mapping
_TOOL_CAPABILITY_MAP: dict[str, CapabilityClass] = {
    "read_file": CapabilityClass.FILE_READ,
    "read": CapabilityClass.FILE_READ,
    "glob": CapabilityClass.FILE_READ,
    "grep": CapabilityClass.FILE_READ,
    "list_dir": CapabilityClass.FILE_READ,
    "write_file": CapabilityClass.FILE_WRITE,
    "write": CapabilityClass.FILE_WRITE,
    "edit": CapabilityClass.FILE_WRITE,
    "edit_file": CapabilityClass.FILE_WRITE,
    "create_file": CapabilityClass.FILE_WRITE,
    "bash": CapabilityClass.SHELL_EXEC,
    "shell": CapabilityClass.SHELL_EXEC,
    "execute": CapabilityClass.SHELL_EXEC,
    "run_command": CapabilityClass.SHELL_EXEC,
    "http_get": CapabilityClass.NETWORK_EGRESS,
    "http_post": CapabilityClass.NETWORK_EGRESS,
    "fetch": CapabilityClass.NETWORK_EGRESS,
    "web_fetch": CapabilityClass.NETWORK_EGRESS,
    "web_search": CapabilityClass.NETWORK_EGRESS,
    "curl": CapabilityClass.NETWORK_EGRESS,
    "python": CapabilityClass.CODE_EXEC,
    "eval": CapabilityClass.CODE_EXEC,
    "model_call": CapabilityClass.MODEL_CALL,
    "llm_call": CapabilityClass.MODEL_CALL,
}

# File path patterns for sensitivity detection (reuses redaction module ideas)
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\.env($|\.)", re.IGNORECASE),
    re.compile(r"credentials", re.IGNORECASE),
    re.compile(r"secrets?[_.]", re.IGNORECASE),
    re.compile(r"_key\.", re.IGNORECASE),
    re.compile(r"\.pem$", re.IGNORECASE),
    re.compile(r"\.key$", re.IGNORECASE),
    re.compile(r"private[_.]", re.IGNORECASE),
    re.compile(r"token[_.]", re.IGNORECASE),
    re.compile(r"password", re.IGNORECASE),
    re.compile(r"api[_-]?key", re.IGNORECASE),
]

# URL pattern for trust domain detection
_URL_PATTERN = re.compile(r"https?://", re.IGNORECASE)


def _detect_sensitivity(args: dict[str, Any]) -> tuple[DataSensitivity, AnnotationSource]:
    """Inspect tool arguments for data sensitivity signals."""
    for key in ("path", "file_path", "file", "filename", "target"):
        val = args.get(key)
        if isinstance(val, str):
            for pat in _SECRET_PATTERNS:
                if pat.search(val):
                    return DataSensitivity.SECRET_CANDIDATE, AnnotationSource.INLINE_PATH_HEURISTIC
            # Non-secret local file → INTERNAL
            return DataSensitivity.INTERNAL, AnnotationSource.INLINE_PATH_HEURISTIC
    return DataSensitivity.NONE, AnnotationSource.FALLBACK


def _detect_trust_domain(args: dict[str, Any]) -> tuple[TrustDomain, AnnotationSource]:
    """Inspect tool arguments for trust domain signals."""
    for key in ("url", "uri", "endpoint", "host", "destination"):
        val = args.get(key)
        if isinstance(val, str) and _URL_PATTERN.match(val):
            return TrustDomain.EXTERNAL, AnnotationSource.INLINE_PATH_HEURISTIC
    return TrustDomain.LOCAL, AnnotationSource.FALLBACK


def annotate_step(
    tool_id: str,
    args: dict[str, Any] | None = None,
    result_status: str = "ok",
) -> ActionStep:
    """Mechanical annotation. Server-owned — daemon calls this, not the RPC caller.

    Caller-supplied classification fields are ignored.  The annotation is
    purely from tool_id mapping + argument inspection.
    """
    safe_args = args or {}

    # Capability from tool_id
    cap = _TOOL_CAPABILITY_MAP.get(tool_id.lower(), CapabilityClass.UNKNOWN)
    cap_source = (
        AnnotationSource.TOOL_METADATA
        if cap != CapabilityClass.UNKNOWN
        else AnnotationSource.FALLBACK
    )

    # Sensitivity from file path patterns
    sensitivity, sens_source = _detect_sensitivity(safe_args)

    # Trust domain from URL patterns
    trust, trust_source = _detect_trust_domain(safe_args)

    # args_hash
    args_hash_val = hashlib.sha256(
        canonical_json(safe_args)
    ).hexdigest()

    return ActionStep(
        tool_id=tool_id,
        capability_class=cap,
        trust_domain=trust,
        data_sensitivity=sensitivity,
        result_status=result_status,
        args_hash=args_hash_val,
        capability_source=cap_source,
        sensitivity_source=sens_source,
        trust_domain_source=trust_source,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


# =============================================================================
# Edge key (dedupe)
# =============================================================================


def edge_key(
    prior_index: int,
    proposed_index: int,
    prior_step: ActionStep,
    proposed_step: ActionStep,
) -> str:
    """Canonical edge key for dedup. Includes only rule-matching fields."""
    return content_hash(canonical_json({
        "prior_index": prior_index,
        "proposed_index": proposed_index,
        "prior_cap": prior_step.capability_class.value,
        "prior_sens": prior_step.data_sensitivity.value,
        "prior_trust": prior_step.trust_domain.value,
        "proposed_cap": proposed_step.capability_class.value,
        "proposed_trust": proposed_step.trust_domain.value,
    }))


# =============================================================================
# Filename sanitization
# =============================================================================


def sanitize_correlation_id(correlation_id: str) -> str:
    """Filename safety for ActionLogStore. Returns truncated SHA-256."""
    return hashlib.sha256(correlation_id.encode("utf-8")).hexdigest()[:32]


# =============================================================================
# ChainEvalResult
# =============================================================================


@dataclass
class ChainEvalResult:
    kernel_verdict: str            # "deny" | "allow" (before policy)
    effective_verdict: str         # after policy augmentation
    mode: str                      # "detect_only" | "enforce"
    composition_match: bool        # kernel fact: did any denied rule match?
    matched_rule_ids: list[str]
    exception_results: dict[str, bool]  # rule_id → exception_satisfied
    history_length: int
    action_log_hash: str           # hex digest
    action_log_bytes: bytes        # canonical bytes (for receipt subject)
    proposed_step_dict: dict       # serialized proposed step
    policy_fragment: dict | None   # canonical PolicyReceiptFragment shape
    dedupe_keys: list[str]         # keys for daemon to call record_match() on
    verdict_reason: str            # "composition_denied" | "allow" | ...

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "kernel_verdict": self.kernel_verdict,
            "effective_verdict": self.effective_verdict,
            "mode": self.mode,
            "composition_match": self.composition_match,
            "matched_rule_ids": self.matched_rule_ids,
            "exception_results": self.exception_results,
            "history_length": self.history_length,
            "action_log_hash": self.action_log_hash,
            "proposed_step": self.proposed_step_dict,
            "verdict_reason": self.verdict_reason,
        }
        if self.policy_fragment is not None:
            d["policy_fragment"] = self.policy_fragment
        return d


# =============================================================================
# ChainGate — pure evaluation, no side effects
# =============================================================================


class ChainGate:
    """Composition-aware capability gate.

    evaluate() is pure: returns ChainEvalResult, does NOT persist
    action logs or emit receipts. Daemon owns those side effects.
    """

    def evaluate(
        self,
        action_log: ActionLog,
        proposed_step: ActionStep,
        rules: ChainRuleSet,
        exceptions: set[str] | None = None,
        policy: Any = None,
    ) -> ChainEvalResult:
        """Evaluate proposed step against composition rules and action history.

        Args:
            action_log: Current action log (prior steps).
            proposed_step: The step being proposed.
            rules: Composition rules to evaluate.
            exceptions: Active exception keys (for unless_condition clauses).
            policy: Optional PolicyRuleSet for severity augmentation.

        Returns:
            ChainEvalResult with kernel + effective verdicts, matched rules,
            dedupe keys, and receipt payload data.
        """
        active_exceptions = exceptions or set()

        # Compute action_log_hash over existing log + proposed step
        all_steps = list(action_log.steps) + [proposed_step]
        action_log_bytes, action_log_hash_hex = compute_action_log_hash(all_steps)
        history_length = len(all_steps)

        # Failed proposed step short-circuit: skip proposed-step matching
        if proposed_step.result_status != "ok":
            return ChainEvalResult(
                kernel_verdict="allow",
                effective_verdict="allow",
                mode="detect_only",
                composition_match=False,
                matched_rule_ids=[],
                exception_results={},
                history_length=history_length,
                action_log_hash=action_log_hash_hex,
                action_log_bytes=action_log_bytes,
                proposed_step_dict=proposed_step.to_dict(),
                policy_fragment=None,
                dedupe_keys=[],
                verdict_reason="failed_step_skipped",
            )

        # Evaluate all rules — not first-match-wins
        matched_rule_ids: list[str] = []
        exception_results: dict[str, bool] = {}
        unsatisfied_denies: list[str] = []
        dedupe_keys: list[str] = []

        for rule in rules.rules:
            # Check proposed_* conditions against proposed_step
            if not self._proposed_matches(rule, proposed_step):
                continue

            # Scan all prior steps for prior_* condition match
            matched_prior_indices = []
            for i, prior_step in enumerate(action_log.steps):
                if self._prior_matches(rule, prior_step):
                    matched_prior_indices.append(i)

            if not matched_prior_indices:
                continue

            # Rule fires — check unless_condition
            exception_satisfied = (
                rule.unless_condition is not None
                and rule.unless_condition in active_exceptions
            )
            matched_rule_ids.append(rule.rule_id)
            exception_results[rule.rule_id] = exception_satisfied

            if not exception_satisfied and rule.effect == "deny":
                unsatisfied_denies.append(rule.rule_id)

            # Build dedupe keys for each (rule, prior_step, proposed) edge
            for prior_idx in matched_prior_indices:
                ek = edge_key(
                    prior_idx, len(action_log.steps),
                    action_log.steps[prior_idx], proposed_step,
                )
                dk = f"{rule.rule_id}:{ek}"
                dedupe_keys.append(dk)

        # Kernel verdict
        composition_match = len(matched_rule_ids) > 0
        if unsatisfied_denies:
            kernel_verdict = "deny"
            verdict_reason = "composition_denied"
        elif not rules.rules:
            kernel_verdict = "allow"
            verdict_reason = "empty_rules"
        else:
            kernel_verdict = "allow"
            verdict_reason = "allow"

        # Policy augmentation
        effective_verdict = kernel_verdict
        policy_fragment = None
        if policy is not None:
            policy_fragment, augmented_verdict = self._evaluate_policy(
                action_log, proposed_step, kernel_verdict,
                composition_match, history_length, policy,
            )
            if augmented_verdict is not None:
                effective_verdict = augmented_verdict

        return ChainEvalResult(
            kernel_verdict=kernel_verdict,
            effective_verdict=effective_verdict,
            mode="detect_only",
            composition_match=composition_match,
            matched_rule_ids=matched_rule_ids,
            exception_results=exception_results,
            history_length=history_length,
            action_log_hash=action_log_hash_hex,
            action_log_bytes=action_log_bytes,
            proposed_step_dict=proposed_step.to_dict(),
            policy_fragment=policy_fragment,
            dedupe_keys=dedupe_keys,
            verdict_reason=verdict_reason,
        )

    def _proposed_matches(self, rule: CompositionRule, step: ActionStep) -> bool:
        """Check proposed_* conditions. ALL non-None must match."""
        if (
            rule.proposed_capability is not None
            and step.capability_class != rule.proposed_capability
        ):
            return False
        if (
            rule.proposed_trust_domain is not None
            and step.trust_domain != rule.proposed_trust_domain
        ):
            return False
        return True

    def _prior_matches(self, rule: CompositionRule, step: ActionStep) -> bool:
        """Check prior_* conditions. ALL non-None must match."""
        if rule.prior_sensitivity_gte is not None:
            if not sensitivity_gte(step.data_sensitivity, rule.prior_sensitivity_gte):
                return False
        if (
            rule.prior_capability is not None
            and step.capability_class != rule.prior_capability
        ):
            return False
        if (
            rule.prior_trust_domain is not None
            and step.trust_domain != rule.prior_trust_domain
        ):
            return False
        return True

    def _evaluate_policy(
        self,
        action_log: ActionLog,
        proposed_step: ActionStep,
        kernel_verdict: str,
        composition_match: bool,
        history_length: int,
        policy: Any,
    ) -> tuple[dict | None, str | None]:
        """Evaluate policy and return (fragment_dict, augmented_verdict).

        Policy augments, never replaces: PASS from policy never downgrades
        kernel DENY. ESCALATE is explicit noop.

        Returns (None, None) on error (fail-open).
        """
        import time as _time
        try:
            from .policy_engine import (
                PolicyEvalRequest,
                SubjectInfo,
                ContextInfo,
                AttributesInfo,
                PolicyReceiptFragment,
                PolicyVerdict,
                evaluate as policy_evaluate,
            )

            # Build synthetic capabilities from gate context
            caps: list[str] = []
            if composition_match:
                caps.append("synthetic.comp.denied_chain")
            # Secret + egress pattern
            has_secret_prior = any(
                sensitivity_gte(s.data_sensitivity, DataSensitivity.SECRET_CANDIDATE)
                for s in action_log.steps
            )
            if has_secret_prior and proposed_step.capability_class == CapabilityClass.NETWORK_EGRESS:
                caps.append("synthetic.comp.sensitive_egress")
            # Trust domain transition
            prior_domains = {s.trust_domain for s in action_log.steps}
            if proposed_step.trust_domain not in prior_domains and len(prior_domains) > 0:
                caps.append("synthetic.comp.cross_trust")

            request = PolicyEvalRequest(
                subject=SubjectInfo(
                    kind="action_chain",
                    subject_id=action_log.correlation_id,
                    action="compose",
                    capabilities=tuple(caps),
                ),
                context=ContextInfo(
                    gate_name="chain_composition",
                    trust_mode="local",
                ),
                attributes=AttributesInfo(
                    is_composed=True,
                    chain_length=history_length,
                    sensitivity=proposed_step.data_sensitivity.value,
                ),
            )

            t0 = _time.monotonic()
            eval_result = policy_evaluate(request, policy, strict_taxonomy=False)
            duration_ms = (_time.monotonic() - t0) * 1000

            # Augment verdict (escalate only, never downgrade)
            augmented_verdict: str | None = None
            if eval_result.verdict == PolicyVerdict.BLOCK:
                augmented_verdict = "deny"
            elif eval_result.verdict == PolicyVerdict.WARN:
                if kernel_verdict == "allow":
                    augmented_verdict = "deny"  # warn escalates to deny in composition context
            # ESCALATE and PASS: no change

            # Detect-only: applied=False on ALL fragments, reason="detect_only_mode"
            fragment = PolicyReceiptFragment(
                policy_verdict=eval_result.verdict.value,
                matched_rule_ids=tuple(r.rule_id for r in eval_result.matched_rules),
                obligation_kinds=tuple(o.kind for o in eval_result.obligations),
                policy_identity=eval_result.policy_identity,
                applied=False,
                reason="detect_only_mode",
                duration_ms=duration_ms,
            )

            return fragment.to_dict(), augmented_verdict

        except Exception:
            logger.warning(
                "chain_gate: policy evaluation failed (fail-open)",
                exc_info=True,
            )
            return None, None


# =============================================================================
# ActionLogStore — simple persistence
# =============================================================================


class ActionLogStore:
    """Persistent action logs keyed by correlation_id.

    Storage: one JSON file per correlation_id in base_dir.
    Filename is sha256(correlation_id)[:32] for path traversal safety.
    Original correlation_id stored inside the JSON file.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def _filename(self, correlation_id: str) -> Path:
        return self.base_dir / f"{sanitize_correlation_id(correlation_id)}.json"

    def get(self, correlation_id: str) -> ActionLog | None:
        path = self._filename(correlation_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text("utf-8"))
            return ActionLog.from_dict(data)
        except Exception:
            logger.warning("Failed to load action log for %s", correlation_id)
            return None

    def put(self, log: ActionLog) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self._filename(log.correlation_id)
        path.write_text(json.dumps(log.to_dict(), indent=2), encoding="utf-8")

    def reset(self, correlation_id: str) -> bool:
        """Delete the action log. Returns True if it existed."""
        path = self._filename(correlation_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_ids(self) -> list[str]:
        """List correlation_ids of stored logs (reads each file)."""
        if not self.base_dir.exists():
            return []
        ids = []
        for f in sorted(self.base_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text("utf-8"))
                ids.append(data["correlation_id"])
            except Exception:
                continue
        return ids


# =============================================================================
# ChainRuleSet loading
# =============================================================================


def load_chain_rules(path: Path) -> tuple[ChainRuleSet, str]:
    """Load chain rules from a JSON file.

    Returns (rule_set, load_status) where load_status is one of:
        "loaded", "loaded_empty", "missing_policy", "corrupt_fallback"
    """
    if not path.exists():
        return ChainRuleSet(), "missing_policy"
    try:
        data = json.loads(path.read_text("utf-8"))
        rs = ChainRuleSet.from_dict(data)
        if not rs.rules:
            return rs, "loaded_empty"
        return rs, "loaded"
    except Exception:
        logger.warning("Failed to load chain_rules.json, using empty rules", exc_info=True)
        return ChainRuleSet(), "corrupt_fallback"
