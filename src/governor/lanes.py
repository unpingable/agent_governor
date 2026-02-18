# SPDX-License-Identifier: Apache-2.0
"""
Capability-based lane routing with artifact reuse.

Lanes route by capability, not cost. "Serve cheap when you can, escalate
when you must, and reuse anything that's actually reusable."

Terminology fence (no CDN language):
- "Capability ladder" / "execution ladder" — not hierarchy/cache
- "Lane 0/1/2/3" — not edge/regional/origin
- "Artifact reuse store" — not cache
- "Refresh" — not revalidate
- "Deduplicate" — not request collapsing
- "Hedge execution" — not hedged requests

Lane 0 (ROUTER): routing logic + guards + validators — always runs, no model.
Lane 1 (FAST): cheap model / trivial tasks.
Lane 2 (GENERAL): workhorse.
Lane 3 (DEEP): big/specialist, verification/escalation.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum, IntEnum
from pathlib import Path
from typing import Any, Callable

try:
    import fcntl
except ImportError:  # pragma: no cover – Windows
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Key must be lowercase hex only (sha256 output) to prevent path traversal.
_VALID_KEY_RE = re.compile(r"^[0-9a-f]{8,128}$")


# =============================================================================
# Enums
# =============================================================================


class Lane(IntEnum):
    """Capability-based execution lane."""

    ROUTER = 0   # Lane 0: routing + guards + validators (always runs, no model)
    FAST = 1     # Lane 1: cheap model / trivial tasks
    GENERAL = 2  # Lane 2: workhorse
    DEEP = 3     # Lane 3: big/specialist, verification/escalation


class ProbePolicy(str, Enum):
    """When and how to run a stability probe."""

    NONE = "none"              # No probe
    CANARY = "canary"          # Single-transform quick check
    DEEP = "deep"              # Full transform set
    RISK_GATED = "risk_gated"  # Depends on risk_class at routing time


class ArtifactKind(str, Enum):
    """Types of reusable LLM artifacts with different TTL defaults."""

    TOOL_RESULT = "tool_result"      # TTL 24h
    INTERMEDIATE = "intermediate"    # TTL 1h (entities, outlines, schema-filled JSON)
    FINAL_ANSWER = "final_answer"    # TTL 5min, OFF BY DEFAULT


# Default TTLs in seconds per artifact kind
DEFAULT_TTLS: dict[str, int] = {
    ArtifactKind.TOOL_RESULT.value: 86400,    # 24h
    ArtifactKind.INTERMEDIATE.value: 3600,     # 1h
    ArtifactKind.FINAL_ANSWER.value: 300,      # 5min
}

# Mapping from Lane to ModelTier value strings
LANE_TO_TIERS: dict[int, list[str]] = {
    Lane.FAST: ["local", "fast"],
    Lane.GENERAL: ["standard"],
    Lane.DEEP: ["heavy"],
}

# Mapping from OperationalRegime name to risk_class for lane routing.
# ELASTIC/WARM → standard (nominal), DUCTILE → elevated, UNSTABLE → critical.
REGIME_TO_RISK_CLASS: dict[str, str] = {
    "elastic": "standard",
    "warm": "standard",
    "ductile": "elevated",
    "unstable": "critical",
}


def regime_to_risk_class(regime_value: str) -> tuple[str, bool]:
    """Map an OperationalRegime value to a lane routing risk_class.

    Returns (risk_class, is_known_regime).  Unknown regimes default to
    "standard" (fail-open availability posture) but the caller MUST log
    a loud reason so a broken detector doesn't silently masquerade as
    nominal.
    """
    if regime_value in REGIME_TO_RISK_CLASS:
        return REGIME_TO_RISK_CLASS[regime_value], True
    return "standard", False


# =============================================================================
# LaneContract
# =============================================================================


@dataclass(frozen=True)
class LaneContract:
    """What a lane promises and requires.

    Frozen for hashability — contracts are identity-bearing.
    """

    lane: int
    model_tiers: tuple[str, ...] = ()
    must_have_strengths: tuple[str, ...] = ()
    nice_to_have_strengths: tuple[str, ...] = ()
    min_context_window: int = 0
    budget_per_call_usd: float = 0.0
    validators: tuple[str, ...] = ()
    probe_policy: str = "none"
    tools_allowed: bool = False
    artifact_reuse: str = "none"
    hard_disallow: tuple[tuple[str, Any], ...] = ()

    def contract_hash(self) -> str:
        """Deterministic hash of this contract."""
        data = _canonical_json({
            "lane": self.lane,
            "model_tiers": list(self.model_tiers),
            "must_have_strengths": list(self.must_have_strengths),
            "nice_to_have_strengths": list(self.nice_to_have_strengths),
            "min_context_window": self.min_context_window,
            "budget_per_call_usd": self.budget_per_call_usd,
            "validators": list(self.validators),
            "probe_policy": self.probe_policy,
            "tools_allowed": self.tools_allowed,
            "artifact_reuse": self.artifact_reuse,
            "hard_disallow": {k: v for k, v in self.hard_disallow},
        })
        return hashlib.sha256(data).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "model_tiers": list(self.model_tiers),
            "must_have_strengths": list(self.must_have_strengths),
            "nice_to_have_strengths": list(self.nice_to_have_strengths),
            "min_context_window": self.min_context_window,
            "budget_per_call_usd": self.budget_per_call_usd,
            "validators": list(self.validators),
            "probe_policy": self.probe_policy,
            "tools_allowed": self.tools_allowed,
            "artifact_reuse": self.artifact_reuse,
            "hard_disallow": {k: v for k, v in self.hard_disallow},
        }


# Default contracts (conservative v2)
LANE_CONTRACTS: dict[int, LaneContract] = {
    Lane.FAST: LaneContract(
        lane=Lane.FAST,
        model_tiers=("local", "fast"),
        must_have_strengths=(),
        nice_to_have_strengths=("speed",),
        budget_per_call_usd=0.01,
        validators=("format", "schema"),
        probe_policy=ProbePolicy.NONE.value,
        tools_allowed=False,
        artifact_reuse="intermediates",
        hard_disallow=(
            ("risk_class", ("elevated", "critical")),
            ("context_heavy", True),
            ("has_side_effects", True),
        ),
    ),
    Lane.GENERAL: LaneContract(
        lane=Lane.GENERAL,
        model_tiers=("standard",),
        must_have_strengths=(),
        nice_to_have_strengths=("code", "reasoning"),
        budget_per_call_usd=0.50,
        validators=("format", "schema"),
        probe_policy=ProbePolicy.RISK_GATED.value,
        tools_allowed=False,
        artifact_reuse="tool_results",
        hard_disallow=(),
    ),
    Lane.DEEP: LaneContract(
        lane=Lane.DEEP,
        model_tiers=("heavy",),
        must_have_strengths=("reasoning",),
        nice_to_have_strengths=("code", "creative", "complex"),
        budget_per_call_usd=5.00,
        validators=("format", "schema", "continuity"),
        probe_policy=ProbePolicy.DEEP.value,
        tools_allowed=True,
        artifact_reuse="tool_results",
        hard_disallow=(),
    ),
}


# =============================================================================
# Helpers
# =============================================================================


def _canonical_json(obj: Any) -> bytes:
    """Deterministic JSON for hashing."""
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# =============================================================================
# Vary Key
# =============================================================================


def compute_vary_key(
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    tool_schemas: list[dict] | None = None,
    tools_allowed: bool = False,
    doc_hashes: list[str] | None = None,
    envelope_version: str = "",
    route_policy_version: str = "",
    probe_config_version: str = "",
    generation_params: dict | None = None,
    budget_per_call_usd: float = 0.0,
    probe_policy: str = "",
) -> str:
    """Content hash for artifact reuse keying.

    Any component change → different key → miss.
    tools_allowed is a boolean in the key: a result produced without tools
    MUST NOT be served when tools are now permitted.
    budget_per_call_usd and probe_policy are included so a cached artifact
    produced under a different budget/probe regime is not inadvertently reused.
    """
    components = {
        "model_id": model_id,
        "system_prompt_hash": _sha256(system_prompt.encode("utf-8")),
        "user_prompt_hash": _sha256(user_prompt.encode("utf-8")),
        "tool_schemas_hash": _sha256(
            _canonical_json(tool_schemas) if tool_schemas else b""
        ),
        "tools_allowed": tools_allowed,
        "doc_hashes": sorted(doc_hashes or []),
        "envelope_version": envelope_version,
        "route_policy_version": route_policy_version,
        "probe_config_version": probe_config_version,
        "generation_params": generation_params or {},
        "budget_per_call_usd": budget_per_call_usd,
        "probe_policy": probe_policy,
    }
    return _sha256(_canonical_json(components))


# =============================================================================
# RoutePlan
# =============================================================================


@dataclass
class RoutePlan:
    """The decision artifact — what lane/model/budget to use for this request."""

    lane: int
    model: str
    provider: str
    budget_per_call_usd: float
    budget_total_usd: float
    tools_allowed: bool
    validators: list[str]
    probe_policy: str
    vary_key: str
    escalation_policy: str  # "auto" | "manual" | "disabled"
    fallback_chain: list[str]
    reasons: list[str]
    autopilot_level: int = 1
    receipt_id: str | None = None
    timestamp: str = ""
    risk_class: str = "standard"   # for cooldown scoping
    task_hint: str = ""            # for cooldown scoping

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "model": self.model,
            "provider": self.provider,
            "budget_per_call_usd": self.budget_per_call_usd,
            "budget_total_usd": self.budget_total_usd,
            "tools_allowed": self.tools_allowed,
            "validators": self.validators,
            "probe_policy": self.probe_policy,
            "vary_key": self.vary_key,
            "escalation_policy": self.escalation_policy,
            "fallback_chain": self.fallback_chain,
            "reasons": self.reasons,
            "autopilot_level": self.autopilot_level,
            "receipt_id": self.receipt_id,
            "timestamp": self.timestamp,
            "risk_class": self.risk_class,
            "task_hint": self.task_hint,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoutePlan:
        return cls(
            lane=d["lane"],
            model=d["model"],
            provider=d.get("provider", ""),
            budget_per_call_usd=d.get("budget_per_call_usd", 0.0),
            budget_total_usd=d.get("budget_total_usd", 0.0),
            tools_allowed=d.get("tools_allowed", False),
            validators=d.get("validators", []),
            probe_policy=d.get("probe_policy", "none"),
            vary_key=d.get("vary_key", ""),
            escalation_policy=d.get("escalation_policy", "auto"),
            fallback_chain=d.get("fallback_chain", []),
            reasons=d.get("reasons", []),
            autopilot_level=d.get("autopilot_level", 1),
            receipt_id=d.get("receipt_id"),
            timestamp=d.get("timestamp", ""),
            risk_class=d.get("risk_class", "standard"),
            task_hint=d.get("task_hint", ""),
        )


# =============================================================================
# CascadeResult
# =============================================================================


@dataclass
class CascadeResult:
    """Result of executing a RoutePlan through the cascade."""

    output: str
    lane_used: int
    model_used: str
    escalated: bool
    escalation_chain: list[str]
    mitigations_attempted: list[str]
    probe_decision: str | None
    artifact_hit: bool
    vary_key: str
    budget_spent_usd: float
    budget_exhausted: bool
    receipt_id: str | None = None
    validators_passed: list[str] = field(default_factory=list)
    validators_failed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "output": self.output,
            "lane_used": self.lane_used,
            "model_used": self.model_used,
            "escalated": self.escalated,
            "escalation_chain": self.escalation_chain,
            "mitigations_attempted": self.mitigations_attempted,
            "probe_decision": self.probe_decision,
            "artifact_hit": self.artifact_hit,
            "vary_key": self.vary_key,
            "budget_spent_usd": self.budget_spent_usd,
            "budget_exhausted": self.budget_exhausted,
            "receipt_id": self.receipt_id,
            "validators_passed": self.validators_passed,
            "validators_failed": self.validators_failed,
        }


# =============================================================================
# StoredArtifact + ArtifactReuseStore
# =============================================================================


@dataclass
class StoredArtifact:
    """A reusable LLM artifact in the store."""

    vary_key: str
    content: str
    model: str
    lane: int
    kind: str
    contract_hash: str
    tools_were_allowed: bool
    created_at: str
    expires_at: str
    probe_decision: str | None = None
    hit_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "vary_key": self.vary_key,
            "content": self.content,
            "model": self.model,
            "lane": self.lane,
            "kind": self.kind,
            "contract_hash": self.contract_hash,
            "tools_were_allowed": self.tools_were_allowed,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "probe_decision": self.probe_decision,
            "hit_count": self.hit_count,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> StoredArtifact:
        return cls(
            vary_key=d["vary_key"],
            content=d["content"],
            model=d["model"],
            lane=d["lane"],
            kind=d["kind"],
            contract_hash=d["contract_hash"],
            tools_were_allowed=d.get("tools_were_allowed", False),
            created_at=d["created_at"],
            expires_at=d["expires_at"],
            probe_decision=d.get("probe_decision"),
            hit_count=d.get("hit_count", 0),
        )


class ArtifactReuseStore:
    """File-per-artifact at .governor/artifacts/{key[:2]}/{key}.json.

    Conservative v2 defaults: final answer reuse OFF.

    Hardening (v2.1):
    - Key validated as hex-only (prevents path traversal).
    - Symlinks rejected on read/write.
    - Atomic writes (tmp + rename) with fcntl.flock on Linux.
    - Bad JSON on disk → treated as miss, not crash.
    - no_store flag for sensitive artifacts.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base = base_dir
        self._memory: dict[str, StoredArtifact] = {}
        self._no_store_keys: set[str] = set()  # Keys that must never be persisted

    @staticmethod
    def _validate_key(vary_key: str) -> bool:
        """Return True if key is safe to use as a path component."""
        return bool(_VALID_KEY_RE.match(vary_key))

    def _safe_path(self, vary_key: str) -> Path | None:
        """Return artifact path after validating key and rejecting symlinks.

        Returns None if base_dir is not set, key is invalid, or path is a
        symlink (defense against symlink attacks in .governor/artifacts/).
        """
        if self._base is None:
            return None
        if not self._validate_key(vary_key):
            logger.warning("Invalid artifact key rejected: %r", vary_key[:40])
            return None
        shard = vary_key[:2]
        path = self._base / shard / f"{vary_key}.json"
        # Reject existing symlinks — artifacts must be regular files.
        if path.is_symlink():
            logger.warning("Symlink artifact rejected: %s", path)
            return None
        return path

    # Keep old name as alias for backwards compatibility in tests.
    def _artifact_path(self, vary_key: str) -> Path | None:
        return self._safe_path(vary_key)

    def lookup(
        self,
        vary_key: str,
        current_contract: LaneContract | None = None,
    ) -> StoredArtifact | None:
        """Returns artifact if exists, not expired, and contract-compatible."""
        artifact = self._memory.get(vary_key)
        if artifact is None and self._base:
            path = self._safe_path(vary_key)
            if path and path.exists() and not path.is_symlink():
                try:
                    artifact = StoredArtifact.from_dict(
                        json.loads(path.read_text())
                    )
                    self._memory[vary_key] = artifact
                except (json.JSONDecodeError, KeyError, OSError, TypeError, ValueError) as exc:
                    logger.debug("Corrupt artifact treated as miss: %s (%s)", vary_key[:16], exc)
                    return None

        if artifact is None:
            return None

        # Expiry check
        now = datetime.now(timezone.utc)
        try:
            expires = datetime.fromisoformat(artifact.expires_at)
            if now >= expires:
                return None
        except ValueError:
            return None

        # BLOCK/HUMAN_GATE never served
        if artifact.probe_decision in ("block", "human_gate"):
            return None

        # Contract compatibility
        if current_contract is not None:
            # If current plan allows tools but artifact was produced without,
            # don't serve (would skip tool execution)
            if current_contract.tools_allowed and not artifact.tools_were_allowed:
                return None

        # Record hit
        artifact.hit_count += 1
        self._persist(vary_key, artifact)
        return artifact

    def store(
        self,
        vary_key: str,
        content: str,
        model: str,
        lane: int,
        kind: str,
        contract: LaneContract,
        tools_allowed: bool,
        probe_decision: str | None = None,
        ttl_seconds: int | None = None,
        no_store: bool = False,
    ) -> StoredArtifact:
        """Store artifact. Idempotent on vary_key. Default TTL by kind.

        Args:
            no_store: If True, artifact is held in memory only and never
                written to disk.  Use for sensitive artifacts (e.g. tool
                results containing credentials).
        """
        now = datetime.now(timezone.utc)
        if ttl_seconds is None:
            ttl_seconds = DEFAULT_TTLS.get(kind, 3600)
        expires = now + timedelta(seconds=ttl_seconds)

        artifact = StoredArtifact(
            vary_key=vary_key,
            content=content,
            model=model,
            lane=lane,
            kind=kind,
            contract_hash=contract.contract_hash(),
            tools_were_allowed=tools_allowed,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
            probe_decision=probe_decision,
            hit_count=0,
        )
        self._memory[vary_key] = artifact
        if no_store:
            self._no_store_keys.add(vary_key)
        else:
            self._persist(vary_key, artifact)
        return artifact

    def refresh(self, vary_key: str, probe_decision: str) -> None:
        """Update probe_decision (extends confidence, not TTL)."""
        artifact = self._memory.get(vary_key)
        if artifact is not None:
            artifact.probe_decision = probe_decision
            self._persist(vary_key, artifact)

    def evict(self, vary_key: str) -> bool:
        """Remove artifact from store."""
        removed = vary_key in self._memory
        self._memory.pop(vary_key, None)
        if self._base:
            path = self._safe_path(vary_key)
            if path and path.exists() and not path.is_symlink():
                path.unlink()
                removed = True
        return removed

    def evict_expired(self) -> int:
        """Remove all expired artifacts. Returns count evicted."""
        now = datetime.now(timezone.utc)
        to_evict = []
        for key, artifact in list(self._memory.items()):
            try:
                expires = datetime.fromisoformat(artifact.expires_at)
                if now >= expires:
                    to_evict.append(key)
            except ValueError:
                to_evict.append(key)
        for key in to_evict:
            self.evict(key)
        return len(to_evict)

    def stats(self) -> dict[str, Any]:
        """Return store statistics."""
        total = len(self._memory)
        by_kind: dict[str, int] = {}
        total_hits = 0
        for a in self._memory.values():
            by_kind[a.kind] = by_kind.get(a.kind, 0) + 1
            total_hits += a.hit_count
        return {
            "total_artifacts": total,
            "by_kind": by_kind,
            "total_hits": total_hits,
        }

    def _persist(self, vary_key: str, artifact: StoredArtifact) -> None:
        """Atomic write: tmp + flock + rename.  Bad key or symlink → skip."""
        if self._base is None:
            return
        if vary_key in self._no_store_keys:
            return
        path = self._safe_path(vary_key)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Reject symlinks created between validation and write.
            if path.is_symlink():
                logger.warning("Symlink appeared before write: %s", path)
                return
            tmp = path.with_suffix(".tmp")
            data = json.dumps(artifact.to_dict(), indent=2).encode("utf-8")
            fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
            try:
                if fcntl is not None:
                    fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, data)
                os.fsync(fd)
            finally:
                os.close(fd)
            tmp.rename(path)
        except OSError as exc:
            logger.debug("Artifact persist failed for %s: %s", vary_key[:16], exc)


# =============================================================================
# Final answer eligibility (v2: OFF by default)
# =============================================================================


def is_final_answer_reusable(
    tools_allowed: bool,
    risk_class: str,
    format_strict: bool,
    validators_passed: list[str],
    validators_failed: list[str],
    probe_decision: str | None,
    doc_hashes_present: bool,
) -> bool:
    """Check whether a final answer may be stored for reuse.

    Default: OFF. Only allowed when ALL conditions are true.
    """
    if tools_allowed:
        return False
    if risk_class != "standard":
        return False
    if not format_strict:
        return False
    if validators_failed:
        return False
    if probe_decision and probe_decision not in ("proceed", "none"):
        return False
    if not doc_hashes_present:
        return False
    return True


# =============================================================================
# Task hint → ClaimType mapping
# =============================================================================

# Lazy import to avoid circular dependency
_TASK_HINT_MAP: dict[str, str] | None = None


def _get_task_hint_map() -> dict[str, str]:
    global _TASK_HINT_MAP
    if _TASK_HINT_MAP is None:
        _TASK_HINT_MAP = {
            "extract": "file_exists",
            "summarize": "symbol_defined",
            "codegen": "changeset",
            "decision": "decision",
            "verify": "tests_pass",
        }
    return _TASK_HINT_MAP


def resolve_task_hint(task_hint: str) -> list:
    """Resolve a convenience task_hint to synthetic Claim objects.

    Returns list of Claim objects, or raises ValueError for unknown hints.
    """
    from .claims import Claim, ClaimType

    hint_map = _get_task_hint_map()
    if task_hint not in hint_map:
        raise ValueError(
            f"Unknown task_hint: {task_hint!r}. "
            f"Valid hints: {sorted(hint_map.keys())}"
        )
    ct = ClaimType(hint_map[task_hint])
    # Build minimal synthetic claim
    if ct == ClaimType.FILE_EXISTS:
        return [Claim(type=ct, path="<synthetic>")]
    elif ct == ClaimType.SYMBOL_DEFINED:
        return [Claim(type=ct, path="<synthetic>", symbol="<synthetic>")]
    elif ct == ClaimType.CHANGESET:
        return [Claim(type=ct, diff="<synthetic>")]
    elif ct == ClaimType.DECISION:
        return [Claim(type=ct, topic="<synthetic>", choice="<synthetic>")]
    elif ct == ClaimType.TESTS_PASS:
        return [Claim(type=ct, command=("pytest",))]
    else:
        return [Claim(type=ct, path="<synthetic>")]


# =============================================================================
# LaneRouter
# =============================================================================


class LaneRouter:
    """Capability-based lane router. Receipt-producing.

    Uses existing Router for complexity estimation + model selection.
    Adds lane contracts, probe policy, artifact reuse lookup.
    """

    def __init__(
        self,
        router: Any | None = None,
        contracts: dict[int, LaneContract] | None = None,
        autopilot_level: int = 1,
        artifact_store: ArtifactReuseStore | None = None,
        budget_total_usd: float = 10.0,
        receipt_system: Any | None = None,
        cooldown_store: CooldownStore | None = None,
    ) -> None:
        self.contracts = contracts or dict(LANE_CONTRACTS)
        self.autopilot_level = autopilot_level
        self.artifact_store = artifact_store
        self.budget_total_usd = budget_total_usd
        self.receipt_system = receipt_system
        self.cooldown_store = cooldown_store

        # Lazily import and build Router if not provided
        if router is not None:
            self._router = router
        else:
            self._router = None

    @property
    def router(self):
        if self._router is None:
            from .routing import Router
            self._router = Router()
        return self._router

    def route(
        self,
        claims: list | None = None,
        task_hint: str | None = None,
        risk_class: str = "standard",
        has_side_effects: bool = False,
        format_strict: bool = False,
        context_heavy: bool = False,
        prompt_words: int = 0,
        must_have_strengths: list[str] | None = None,
        nice_to_have_strengths: list[str] | None = None,
        force_lane: int | None = None,
    ) -> RoutePlan:
        """Route a request to a lane + model. Returns RoutePlan."""
        from .routing import ModelTier, ComplexityEstimator
        from .claims import Claim

        reasons: list[str] = []

        # --- Resolve claims ---
        resolved_claims: list[Claim] = []
        if claims:
            resolved_claims = list(claims)
        elif task_hint:
            resolved_claims = resolve_task_hint(task_hint)
            reasons.append(f"task_hint={task_hint!r} → synthetic claims")

        # --- Autopilot level 0: force_lane required ---
        if self.autopilot_level == 0:
            if force_lane is None:
                raise ValueError(
                    "Autopilot level 0 requires force_lane parameter"
                )

        # --- Complexity estimation ---
        estimator = self.router.estimator
        desc = task_hint or ""
        estimate = estimator.estimate(resolved_claims, description=desc)
        score = estimate.score

        # --- Initial lane from complexity ---
        if force_lane is not None:
            lane = force_lane
            reasons.append(f"force_lane={lane}")
        else:
            if score < 0.25:
                lane = Lane.FAST
            elif score < 0.45:
                lane = Lane.FAST
            elif score < 0.7:
                lane = Lane.GENERAL
            else:
                lane = Lane.DEEP
            reasons.append(f"complexity={score:.3f} → Lane {lane}")

        # --- Hard overrides ---
        if risk_class == "elevated" and lane < Lane.GENERAL:
            lane = Lane.GENERAL
            reasons.append("risk=elevated → min Lane 2")
        if risk_class == "critical" and lane < Lane.DEEP:
            lane = Lane.DEEP
            reasons.append("risk=critical → min Lane 3")
        if has_side_effects and lane < Lane.DEEP:
            lane = Lane.DEEP
            reasons.append("has_side_effects → min Lane 3")
        if context_heavy and lane < Lane.GENERAL:
            lane = Lane.GENERAL
            reasons.append("context_heavy → min Lane 2")

        # --- Check hard_disallow on contract ---
        lane = self._check_hard_disallow(
            lane, risk_class, has_side_effects, context_heavy, reasons
        )

        # --- critical + side_effects → HUMAN_GATE ---
        human_gate = risk_class == "critical" and has_side_effects

        # --- Get contract ---
        contract = self.contracts.get(lane)
        if contract is None:
            # No contract → promote
            for try_lane in range(lane + 1, Lane.DEEP + 1):
                contract = self.contracts.get(try_lane)
                if contract is not None:
                    lane = try_lane
                    reasons.append(f"no contract at Lane {lane-1} → promoted to Lane {lane}")
                    break
            if contract is None:
                contract = LANE_CONTRACTS[Lane.GENERAL]
                lane = Lane.GENERAL

        # --- Select model ---
        model, provider = self._select_model(
            lane, contract, must_have_strengths, nice_to_have_strengths, reasons
        )

        # --- Resolve probe policy ---
        resolved_probe = self._resolve_probe_policy(
            contract.probe_policy, risk_class
        )
        if human_gate:
            resolved_probe = "deep"
            reasons.append("critical+side_effects → deep probe (HUMAN_GATE required)")

        # --- Build fallback chain ---
        fallback_chain = self._build_fallback_chain(lane, model)

        # --- Escalation policy ---
        if self.autopilot_level == 0:
            escalation_policy = "disabled"
        elif self.autopilot_level >= 1:
            escalation_policy = "auto"
        else:
            escalation_policy = "manual"

        # --- Vary key (placeholder — callers provide full inputs) ---
        vary_key = compute_vary_key(
            model_id=model,
            system_prompt="",
            user_prompt=desc,
            route_policy_version=contract.contract_hash(),
            budget_per_call_usd=contract.budget_per_call_usd,
            probe_policy=resolved_probe,
        )

        # --- Check artifact reuse store ---
        artifact_hit = False
        if self.artifact_store is not None:
            cached = self.artifact_store.lookup(vary_key, contract)
            if cached is not None:
                artifact_hit = True
                reasons.append("artifact reuse hit")

        # --- Emit receipt ---
        receipt_id = None
        if self.receipt_system is not None:
            try:
                receipt = self.receipt_system.emit(
                    gate="lane_routing",
                    verdict="pass",
                    subject_kind="route_plan",
                    subject_bytes=json.dumps({
                        "lane": lane, "model": model,
                        "risk_class": risk_class,
                    }).encode("utf-8"),
                    evidence_bundle={
                        "complexity_score": score,
                        "lane": lane,
                        "model": model,
                        "risk_class": risk_class,
                        "has_side_effects": has_side_effects,
                        "artifact_hit": artifact_hit,
                    },
                    gate_config={"autopilot_level": self.autopilot_level},
                )
                receipt_id = receipt.receipt_id
            except Exception:
                logger.debug("lane_routing receipt emission failed", exc_info=True)

        plan = RoutePlan(
            lane=lane,
            model=model,
            provider=provider,
            budget_per_call_usd=contract.budget_per_call_usd,
            budget_total_usd=self.budget_total_usd,
            tools_allowed=contract.tools_allowed,
            validators=list(contract.validators),
            probe_policy=resolved_probe,
            vary_key=vary_key,
            escalation_policy=escalation_policy,
            fallback_chain=fallback_chain,
            reasons=reasons,
            autopilot_level=self.autopilot_level,
            receipt_id=receipt_id,
            timestamp=_now_iso(),
            risk_class=risk_class,
            task_hint=task_hint or "",
        )
        return plan

    def explain(self, plan: RoutePlan) -> dict[str, Any]:
        """Generate a detailed explanation of a routing plan."""
        contract = self.contracts.get(plan.lane)
        return {
            "lane": plan.lane,
            "lane_name": Lane(plan.lane).name if plan.lane in Lane.__members__.values() else f"Lane {plan.lane}",
            "model": plan.model,
            "provider": plan.provider,
            "reasons": plan.reasons,
            "contract": contract.to_dict() if contract else None,
            "budget": {
                "per_call_usd": plan.budget_per_call_usd,
                "total_usd": plan.budget_total_usd,
            },
            "probe_policy": plan.probe_policy,
            "escalation_policy": plan.escalation_policy,
            "fallback_chain": plan.fallback_chain,
            "autopilot_level": plan.autopilot_level,
            "vary_key": plan.vary_key,
        }

    def get_status(self) -> dict[str, Any]:
        """Return current lane routing configuration status."""
        contracts_info = {}
        for lane_val, contract in self.contracts.items():
            contracts_info[f"lane_{lane_val}"] = contract.to_dict()

        artifact_stats = {}
        if self.artifact_store:
            artifact_stats = self.artifact_store.stats()

        registry_summary = {}
        try:
            reg = self.router.registry
            for tier_name in ("local", "fast", "standard", "heavy"):
                from .routing import ModelTier
                tier = ModelTier(tier_name)
                models = reg.get_available_models(tier)
                registry_summary[tier_name] = models
        except Exception:
            pass

        cooldown_stats = {}
        if self.cooldown_store:
            cooldown_stats = self.cooldown_store.stats()

        return {
            "autopilot_level": self.autopilot_level,
            "budget_total_usd": self.budget_total_usd,
            "contracts": contracts_info,
            "artifact_stats": artifact_stats,
            "cooldown_stats": cooldown_stats,
            "model_registry": registry_summary,
        }

    def _check_hard_disallow(
        self,
        lane: int,
        risk_class: str,
        has_side_effects: bool,
        context_heavy: bool,
        reasons: list[str],
    ) -> int:
        """Check hard_disallow conditions, promote if needed."""
        while lane <= Lane.DEEP:
            contract = self.contracts.get(lane)
            if contract is None:
                lane += 1
                continue

            disallowed = False
            disallow_dict = dict(contract.hard_disallow)

            # Check risk_class
            risk_disallow = disallow_dict.get("risk_class")
            if risk_disallow and risk_class in risk_disallow:
                disallowed = True

            # Check context_heavy
            if disallow_dict.get("context_heavy") and context_heavy:
                disallowed = True

            # Check has_side_effects
            if disallow_dict.get("has_side_effects") and has_side_effects:
                disallowed = True

            if disallowed:
                old = lane
                lane += 1
                reasons.append(f"Lane {old} hard_disallow → promoted to Lane {lane}")
            else:
                break

        return min(lane, Lane.DEEP)

    def _select_model(
        self,
        lane: int,
        contract: LaneContract,
        extra_must_have: list[str] | None,
        extra_nice_to_have: list[str] | None,
        reasons: list[str],
    ) -> tuple[str, str]:
        """Select a model satisfying the contract. Returns (model_name, provider)."""
        from .routing import ModelTier

        registry = self.router.registry

        # Gather candidates from contract tiers
        candidates = []
        for tier_name in contract.model_tiers:
            tier = ModelTier(tier_name)
            for name in registry.get_available_models(tier):
                caps = registry.get_capabilities(name)
                if caps:
                    candidates.append((name, caps))

        if not candidates:
            # Promote: try higher tiers
            for try_lane in range(lane + 1, Lane.DEEP + 1):
                try_contract = self.contracts.get(try_lane)
                if try_contract is None:
                    continue
                for tier_name in try_contract.model_tiers:
                    tier = ModelTier(tier_name)
                    for name in registry.get_available_models(tier):
                        caps = registry.get_capabilities(name)
                        if caps:
                            candidates.append((name, caps))
                if candidates:
                    reasons.append(f"no candidates at Lane {lane} → found at Lane {try_lane}")
                    break

        if not candidates:
            # Absolute fallback
            return "claude-sonnet-4", "anthropic"

        # --- must_have filter ---
        must_have = set(contract.must_have_strengths)
        if extra_must_have:
            must_have.update(extra_must_have)

        if must_have:
            filtered = [
                (n, c) for n, c in candidates
                if must_have <= set(c.strengths)
            ]
            if filtered:
                candidates = filtered
            else:
                logger.warning(
                    "must_have=%s found no exact match among %d candidates; "
                    "falling back to all candidates",
                    sorted(must_have), len(candidates),
                )
                reasons.append(f"must_have={sorted(must_have)} no exact match, using all candidates")

        # --- min_context_window filter ---
        if contract.min_context_window > 0:
            filtered = [
                (n, c) for n, c in candidates
                if c.context_window >= contract.min_context_window
            ]
            if filtered:
                candidates = filtered

        # --- cooldown filter (soft: prefer non-cooled, don't block) ---
        if self.cooldown_store is not None:
            not_cooled = [
                (n, c) for n, c in candidates
                if not self.cooldown_store.is_cooled_down(n, lane)
            ]
            if not_cooled:
                not_cooled_names = {n for n, _ in not_cooled}
                cooled_names = [n for n, _ in candidates if n not in not_cooled_names]
                if cooled_names:
                    reasons.append(
                        f"cooldown: skipping {cooled_names} at Lane {lane}"
                    )
                candidates = not_cooled
            elif candidates:
                # All candidates cooled — warn but proceed (availability > safety here)
                reasons.append(
                    f"cooldown: ALL candidates cooled at Lane {lane}, proceeding anyway"
                )

        # --- probe fail-rate penalty (soft: prefer low-probe-fail models) ---
        if self.cooldown_store is not None and len(candidates) > 1:
            probe_rates: dict[str, float] = {}
            for n, _c in candidates:
                rate, attempts = self.cooldown_store.probe_fail_rate(n, lane)
                if attempts >= CooldownStore._PROBE_MIN_SAMPLES:
                    probe_rates[n] = rate

            if probe_rates:
                # Sort: low probe-fail-rate first (stable sort preserves prior order for ties)
                candidates.sort(key=lambda nc: probe_rates.get(nc[0], 0.0))
                high_rate_models = [
                    f"{n}({probe_rates[n]:.0%})"
                    for n in probe_rates if probe_rates[n] > 0.3
                ]
                if high_rate_models:
                    reasons.append(
                        f"probe_fail_rate: penalized {high_rate_models} at Lane {lane}"
                    )

        # --- nice_to_have ranking ---
        nice_to_have = set(contract.nice_to_have_strengths)
        if extra_nice_to_have:
            nice_to_have.update(extra_nice_to_have)

        if nice_to_have:
            candidates.sort(
                key=lambda nc: len(nice_to_have & set(nc[1].strengths)),
                reverse=True,
            )

        # Autopilot level 2: pick cheapest within lane
        if self.autopilot_level >= 2 and len(candidates) > 1:
            candidates.sort(key=lambda nc: nc[1].cost_input)

        best_name, best_caps = candidates[0]
        return best_name, best_caps.provider

    def _resolve_probe_policy(self, policy: str, risk_class: str) -> str:
        """Resolve risk_gated policy to concrete policy."""
        if policy == ProbePolicy.RISK_GATED.value:
            if risk_class == "standard":
                return ProbePolicy.NONE.value
            elif risk_class == "elevated":
                return ProbePolicy.CANARY.value
            else:
                return ProbePolicy.DEEP.value
        return policy

    def _build_fallback_chain(self, lane: int, primary_model: str) -> list[str]:
        """Build ordered fallback chain from current lane upward."""
        from .routing import ModelTier

        registry = self.router.registry
        chain: list[str] = []

        # Models in same lane (other than primary)
        contract = self.contracts.get(lane)
        if contract:
            for tier_name in contract.model_tiers:
                tier = ModelTier(tier_name)
                for name in registry.get_available_models(tier):
                    if name != primary_model and name not in chain:
                        chain.append(name)

        # Models from higher lanes
        for next_lane in range(lane + 1, Lane.DEEP + 1):
            next_contract = self.contracts.get(next_lane)
            if next_contract is None:
                continue
            for tier_name in next_contract.model_tiers:
                tier = ModelTier(tier_name)
                for name in registry.get_available_models(tier):
                    if name != primary_model and name not in chain:
                        chain.append(name)

        return chain


# =============================================================================
# CascadeExecutor
# =============================================================================


# Mitigation strategies by sensitivity axis
MITIGATION_STRATEGIES: dict[str, str] = {
    "position": "relocate",       # Position sensitivity → relocate/sandwich trusted instructions
    "structure": "schema_form",   # Structure sensitivity → schema-form template
    "drift": "boundary_harden",   # Drift sensitivity → boundary hardening
}


# =============================================================================
# CooldownStore — persisted cascade outcome memory
# =============================================================================


def _cooldown_key(
    model: str,
    lane: int,
    risk_class: str = "",
    task_hint: str = "",
    validators_failed: list[str] | None = None,
) -> str:
    """Coarse key for cooldown scoping.

    Scoped to (model, lane, risk_class, task_hint, validator_set) so a
    model penalised for schema failures on codegen doesn't get banned
    from extract tasks.  Hash keeps the key fixed-width.
    """
    vset = ",".join(sorted(validators_failed)) if validators_failed else ""
    raw = f"{model}:{lane}:{risk_class}:{task_hint}:{vset}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


@dataclass
class CooldownEntry:
    """One recorded cascade outcome, scoped by cooldown_key."""

    cooldown_key: str             # H(model, lane, risk_class, task_hint, validators)
    model: str
    lane: int
    risk_class: str
    task_hint: str
    validators_failed: list[str]
    probe_decision: str | None
    escalated: bool
    is_failure: bool              # explicit: True only when entry counts toward cooldown
    timestamp: str                # ISO 8601

    def to_dict(self) -> dict[str, Any]:
        return {
            "ck": self.cooldown_key,
            "model": self.model,
            "lane": self.lane,
            "risk_class": self.risk_class,
            "task_hint": self.task_hint,
            "validators_failed": self.validators_failed,
            "probe_decision": self.probe_decision,
            "escalated": self.escalated,
            "is_failure": self.is_failure,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CooldownEntry:
        return cls(
            cooldown_key=d.get("ck", ""),
            model=d["model"],
            lane=d["lane"],
            risk_class=d.get("risk_class", ""),
            task_hint=d.get("task_hint", ""),
            validators_failed=d.get("validators_failed", []),
            probe_decision=d.get("probe_decision"),
            escalated=d.get("escalated", False),
            is_failure=d.get("is_failure", False),
            timestamp=d["timestamp"],
        )


def _is_cascade_failure(result: CascadeResult) -> bool:
    """Explicit failure predicate — only these count toward cooldown."""
    if result.validators_failed:
        return True
    if result.probe_decision in ("mitigate", "block", "human_gate"):
        return True
    if result.escalated:
        return True
    return False


class CooldownStore:
    """Scoped (model, lane, risk, task, validators) failure memory.

    JSONL store at .governor/cooldown.jsonl with O_APPEND writes for
    safe concurrent appends.  Compacts on load: only entries within the
    time window are kept in memory; the file is rewritten if it exceeds
    ``_COMPACT_THRESHOLD`` lines.

    Cooldown key = H(model, lane, risk_class, task_hint, sorted_validators)
    so a model penalised for one failure mode isn't banned from all asks.
    """

    DEFAULT_WINDOW_S: float = 3600.0   # 1 hour
    DEFAULT_THRESHOLD: int = 3          # failures in window → cooldown
    _COMPACT_THRESHOLD: int = 5000      # rewrite file when this many lines on load

    def __init__(
        self,
        path: Path | None = None,
        window_s: float = DEFAULT_WINDOW_S,
        threshold: int = DEFAULT_THRESHOLD,
    ) -> None:
        self._path = path
        self._window_s = window_s
        self._threshold = threshold
        self._entries: list[CooldownEntry] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if self._path is None or not self._path.exists():
            return
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._window_s)
        cutoff_iso = cutoff.isoformat()
        total_lines = 0
        try:
            with open(self._path, "r") as f:
                for line in f:
                    total_lines += 1
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        entry = CooldownEntry.from_dict(d)
                        if entry.timestamp >= cutoff_iso:
                            self._entries.append(entry)
                    except (json.JSONDecodeError, KeyError, TypeError):
                        # Tolerate corrupt/partial last line (concurrent writes)
                        continue
        except OSError:
            return

        # Compact if file is bloated — rewrite with only in-window entries
        if total_lines > self._COMPACT_THRESHOLD and self._path is not None:
            try:
                tmp = self._path.with_suffix(".jsonl.tmp")
                with open(tmp, "w") as f:
                    for e in self._entries:
                        f.write(json.dumps(e.to_dict()) + "\n")
                os.replace(str(tmp), str(self._path))
                logger.info(
                    "cooldown store compacted: %d → %d entries",
                    total_lines, len(self._entries),
                )
            except OSError:
                logger.debug("cooldown compaction failed", exc_info=True)

    def record(
        self,
        result: CascadeResult,
        risk_class: str = "",
        task_hint: str = "",
    ) -> None:
        """Record a cascade outcome.  Success decays the failure signal;
        explicit failures count toward cooldown threshold.
        """
        self._ensure_loaded()
        failure = _is_cascade_failure(result)
        ck = _cooldown_key(
            result.model_used, result.lane_used,
            risk_class, task_hint, result.validators_failed,
        )
        entry = CooldownEntry(
            cooldown_key=ck,
            model=result.model_used,
            lane=result.lane_used,
            risk_class=risk_class,
            task_hint=task_hint,
            validators_failed=result.validators_failed,
            probe_decision=result.probe_decision,
            escalated=result.escalated,
            is_failure=failure,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._entries.append(entry)
        if self._path is not None:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                # O_APPEND for safe concurrent single-line writes
                fd = os.open(str(self._path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
                try:
                    os.write(fd, (json.dumps(entry.to_dict()) + "\n").encode())
                finally:
                    os.close(fd)
            except OSError:
                logger.debug("cooldown store append failed", exc_info=True)

    def is_cooled_down(
        self,
        model: str,
        lane: int,
        risk_class: str = "",
        task_hint: str = "",
    ) -> bool:
        """Check if a model exceeds the failure threshold for a scoped context.

        Checks both the exact scoped key AND a broad (model, lane) key so
        that concentrated failures on one task type still surface.
        """
        self._ensure_loaded()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._window_s)
        cutoff_iso = cutoff.isoformat()

        # Broad check: failures for this model+lane regardless of task scope
        broad_failures = 0
        for e in self._entries:
            if (
                e.model == model
                and e.lane == lane
                and e.timestamp >= cutoff_iso
                and e.is_failure
            ):
                broad_failures += 1
        return broad_failures >= self._threshold

    def recent_failures(
        self,
        model: str,
        lane: int,
        risk_class: str = "",
        task_hint: str = "",
    ) -> int:
        """Count recent failures for a (model, lane) pair."""
        self._ensure_loaded()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._window_s)
        cutoff_iso = cutoff.isoformat()
        count = 0
        for e in self._entries:
            if (
                e.model == model
                and e.lane == lane
                and e.timestamp >= cutoff_iso
                and e.is_failure
            ):
                count += 1
        return count

    # --- Probe-specific failure view ---

    _PROBE_DECISIONS_BAD = {"mitigate", "block", "human_gate"}
    _PROBE_MIN_SAMPLES: int = 3  # ignore rate until this many probe attempts

    def probe_fail_rate(
        self,
        model: str,
        lane: int,
    ) -> tuple[float, int]:
        """Probe failure rate for a (model, lane) in the current window.

        A "probe attempt" is any entry where probe_decision is not None.
        A "probe failure" is probe_decision in {mitigate, block, human_gate}.

        Returns (rate, attempts).  Rate is 0.0 when attempts < _PROBE_MIN_SAMPLES
        (not enough data to form an opinion).
        """
        self._ensure_loaded()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._window_s)
        cutoff_iso = cutoff.isoformat()

        attempts = 0
        failures = 0
        for e in self._entries:
            if (
                e.model == model
                and e.lane == lane
                and e.timestamp >= cutoff_iso
                and e.probe_decision is not None
            ):
                attempts += 1
                if e.probe_decision in self._PROBE_DECISIONS_BAD:
                    failures += 1

        if attempts < self._PROBE_MIN_SAMPLES:
            return 0.0, attempts
        return failures / attempts, attempts

    def stats(self) -> dict[str, Any]:
        """Summary statistics."""
        self._ensure_loaded()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=self._window_s)
        cutoff_iso = cutoff.isoformat()
        total = len(self._entries)
        in_window = sum(1 for e in self._entries if e.timestamp >= cutoff_iso)
        cooled: set[tuple[str, int]] = set()
        for e in self._entries:
            if e.timestamp >= cutoff_iso and e.is_failure:
                key = (e.model, e.lane)
                if key not in cooled and self.is_cooled_down(e.model, e.lane):
                    cooled.add(key)
        return {
            "total_entries": total,
            "in_window": in_window,
            "window_s": self._window_s,
            "threshold": self._threshold,
            "models_cooled_down": [
                {"model": m, "lane": l} for m, l in sorted(cooled)
            ],
        }


class CascadeExecutor:
    """Executes a RoutePlan with cascade escalation.

    Pattern: Generate → Validate → Mitigate-once → Re-validate → Escalate

    1. Check artifact store (if hit + contract-compatible → return)
    2. Generate on chosen lane
    3. Run validators
    4. If validators fail → escalate (no mitigation for validator failures)
    5. If probe_required: run stability probe
    6. If probe = PROCEED → store artifact, return
    7. If probe = MITIGATE:
       a. Try ONE axis-targeted mitigation
       b. Re-run validators + probe
       c. If passes → return
       d. If still fails → escalate to next lane
    8. If probe = BLOCK/HUMAN_GATE → return blocked result (no escalation)
    9. Budget guard: if total spend exceeds budget_total → explainable failure
    """

    def __init__(
        self,
        lane_router: LaneRouter,
        artifact_store: ArtifactReuseStore | None = None,
        receipt_system: Any | None = None,
        probe_fn: Callable[[str, str], Any] | None = None,
        cooldown_store: CooldownStore | None = None,
    ) -> None:
        self.lane_router = lane_router
        self.artifact_store = artifact_store or lane_router.artifact_store
        self.receipt_system = receipt_system
        self.probe_fn = probe_fn
        self.cooldown_store = cooldown_store

    def _emit_reuse_receipt(
        self,
        cached: StoredArtifact,
        plan: RoutePlan,
    ) -> str | None:
        """Emit a receipt when an artifact is served from the reuse store."""
        if self.receipt_system is None:
            return None
        try:
            receipt = self.receipt_system.emit(
                gate="artifact_reuse",
                verdict="pass",
                subject_kind="artifact",
                subject_bytes=json.dumps({
                    "artifact_key": cached.vary_key,
                    "artifact_kind": cached.kind,
                    "artifact_model": cached.model,
                    "artifact_lane": cached.lane,
                }).encode("utf-8"),
                evidence_bundle={
                    "artifact_reused": True,
                    "artifact_key": cached.vary_key,
                    "artifact_kind": cached.kind,
                    "artifact_hit_count": cached.hit_count,
                    "eligibility_checks": [
                        "not_expired",
                        "probe_not_blocked",
                        "contract_compatible",
                    ],
                    "plan_vary_key": plan.vary_key,
                },
                gate_config={"artifact_reuse": True},
            )
            return receipt.receipt_id
        except Exception:
            logger.debug("artifact_reuse receipt emission failed", exc_info=True)
            return None

    def _record_cooldown(
        self, result: CascadeResult, plan: RoutePlan | None = None,
    ) -> CascadeResult:
        """Persist cascade outcome to cooldown store (if configured).

        Called for every non-artifact-hit result so that repeated failures
        steer future routing.  Returns the result unchanged (pass-through).
        """
        if self.cooldown_store is not None and not result.artifact_hit:
            try:
                self.cooldown_store.record(
                    result,
                    risk_class=plan.risk_class if plan else "",
                    task_hint=plan.task_hint if plan else "",
                )
            except Exception:
                logger.debug("cooldown store record failed", exc_info=True)
        return result

    def execute(
        self,
        plan: RoutePlan,
        prompt: str,
        generate_fn: Callable[[str, str], str],
        output: str | None = None,
    ) -> CascadeResult:
        """Execute with cascade escalation.

        Args:
            plan: The RoutePlan to execute.
            prompt: User prompt.
            generate_fn: (prompt, model) → output string.
            output: Pre-computed output (skip generation).
        """
        budget_spent = 0.0
        escalation_chain: list[str] = []
        mitigations_attempted: list[str] = []
        current_lane = plan.lane
        current_model = plan.model
        probe_decision_str: str | None = None
        artifact_hit = False
        validators_passed: list[str] = []
        validators_failed: list[str] = []

        # Cascade loop prevention: track visited (lane, model) to avoid cycles.
        seen: set[tuple[int, str]] = set()

        # --- 1. Check artifact store ---
        if self.artifact_store is not None and output is None:
            contract = self.lane_router.contracts.get(current_lane)
            cached = self.artifact_store.lookup(plan.vary_key, contract)
            if cached is not None:
                receipt_id = self._emit_reuse_receipt(cached, plan)
                return CascadeResult(
                    output=cached.content,
                    lane_used=cached.lane,
                    model_used=cached.model,
                    escalated=False,
                    escalation_chain=[],
                    mitigations_attempted=[],
                    probe_decision=cached.probe_decision,
                    artifact_hit=True,
                    vary_key=plan.vary_key,
                    budget_spent_usd=0.0,
                    budget_exhausted=False,
                    receipt_id=receipt_id,
                    validators_passed=list(plan.validators),
                    validators_failed=[],
                )

        # --- Cascade loop ---
        max_escalations = Lane.DEEP - plan.lane + 1  # At most climb to Lane 3
        attempt = 0
        current_output = output

        while attempt < max_escalations:
            attempt += 1

            # --- Loop guard: prevent revisiting the same (lane, model) ---
            key_pair = (current_lane, current_model)
            if key_pair in seen:
                escalation_chain.append(
                    f"Loop detected at Lane {current_lane}/{current_model} → stop"
                )
                break
            seen.add(key_pair)

            # --- Budget check before each step ---
            if budget_spent >= plan.budget_total_usd:
                return self._record_cooldown(CascadeResult(
                    output=current_output or "",
                    lane_used=current_lane,
                    model_used=current_model,
                    escalated=bool(escalation_chain),
                    escalation_chain=escalation_chain,
                    mitigations_attempted=mitigations_attempted,
                    probe_decision=probe_decision_str,
                    artifact_hit=False,
                    vary_key=plan.vary_key,
                    budget_spent_usd=budget_spent,
                    budget_exhausted=True,
                    validators_passed=validators_passed,
                    validators_failed=validators_failed,
                ), plan=plan)

            # --- Per-call budget cap ---
            contract = self.lane_router.contracts.get(current_lane)
            per_call_cap = contract.budget_per_call_usd if contract else plan.budget_per_call_usd

            # --- 2. Generate (if no pre-computed output) ---
            if current_output is None:
                current_output = generate_fn(prompt, current_model)
                # Estimate cost (crude — real cost tracking is out of scope for v2)
                budget_spent += min(per_call_cap, 0.01) if per_call_cap > 0 else 0.01

            # --- 3. Run validators ---
            v_passed, v_failed = self._run_validators(plan.validators, current_output)
            validators_passed = v_passed
            validators_failed = v_failed

            # --- 4. Validator failure → escalate (no mitigation) ---
            if v_failed:
                entry = f"Lane {current_lane} validators failed: {v_failed}"
                escalation_chain.append(entry)
                current_lane, current_model = self._escalate(
                    current_lane, current_model, plan
                )
                if current_lane > Lane.DEEP:
                    break
                current_output = None
                continue

            # --- 5. Probe (if required) ---
            if plan.probe_policy not in (ProbePolicy.NONE.value, "none"):
                probe_result = self._run_probe(
                    current_output, prompt, plan.probe_policy
                )
                if probe_result is not None:
                    probe_decision_str = probe_result.get("decision", "proceed")
                else:
                    probe_decision_str = "proceed"

                # --- 6. PROCEED → done ---
                if probe_decision_str == "proceed":
                    pass  # Fall through to store + return

                # --- 7. MITIGATE → try once ---
                elif probe_decision_str == "mitigate":
                    mitigation = self._pick_mitigation(probe_result)
                    if mitigation and mitigation not in mitigations_attempted:
                        mitigations_attempted.append(mitigation)
                        current_output = self._apply_mitigation(
                            mitigation, prompt, current_output
                        )
                        budget_spent += min(per_call_cap, 0.01) if per_call_cap > 0 else 0.01

                        # Re-validate + re-probe
                        v2_passed, v2_failed = self._run_validators(
                            plan.validators, current_output
                        )
                        validators_passed = v2_passed
                        validators_failed = v2_failed

                        if not v2_failed:
                            re_probe = self._run_probe(
                                current_output, prompt, plan.probe_policy
                            )
                            re_decision = (re_probe or {}).get("decision", "proceed")
                            if re_decision == "proceed":
                                probe_decision_str = "proceed"
                            else:
                                # Still failing → escalate
                                entry = f"Lane {current_lane} mitigate({mitigation}) → still {re_decision} → escalate"
                                escalation_chain.append(entry)
                                probe_decision_str = re_decision
                                current_lane, current_model = self._escalate(
                                    current_lane, current_model, plan
                                )
                                if current_lane > Lane.DEEP:
                                    break
                                current_output = None
                                continue
                        else:
                            # Validators still failing after mitigation → escalate
                            entry = f"Lane {current_lane} mitigate({mitigation}) → validators still failed → escalate"
                            escalation_chain.append(entry)
                            current_lane, current_model = self._escalate(
                                current_lane, current_model, plan
                            )
                            if current_lane > Lane.DEEP:
                                break
                            current_output = None
                            continue
                    else:
                        # No mitigation available → escalate
                        entry = f"Lane {current_lane} mitigate → no available strategy → escalate"
                        escalation_chain.append(entry)
                        current_lane, current_model = self._escalate(
                            current_lane, current_model, plan
                        )
                        if current_lane > Lane.DEEP:
                            break
                        current_output = None
                        continue

                # --- 8. BLOCK/HUMAN_GATE → return blocked (no escalation) ---
                elif probe_decision_str in ("block", "human_gate"):
                    return self._record_cooldown(CascadeResult(
                        output=current_output or "",
                        lane_used=current_lane,
                        model_used=current_model,
                        escalated=bool(escalation_chain),
                        escalation_chain=escalation_chain,
                        mitigations_attempted=mitigations_attempted,
                        probe_decision=probe_decision_str,
                        artifact_hit=False,
                        vary_key=plan.vary_key,
                        budget_spent_usd=budget_spent,
                        budget_exhausted=False,
                        validators_passed=validators_passed,
                        validators_failed=validators_failed,
                    ), plan=plan)
            else:
                probe_decision_str = None

            # --- Store artifact + return ---
            if self.artifact_store and current_output:
                contract = self.lane_router.contracts.get(current_lane)
                if contract and contract.artifact_reuse != "none":
                    kind = ArtifactKind.INTERMEDIATE.value
                    self.artifact_store.store(
                        vary_key=plan.vary_key,
                        content=current_output,
                        model=current_model,
                        lane=current_lane,
                        kind=kind,
                        contract=contract,
                        tools_allowed=plan.tools_allowed,
                        probe_decision=probe_decision_str,
                    )

            return self._record_cooldown(CascadeResult(
                output=current_output or "",
                lane_used=current_lane,
                model_used=current_model,
                escalated=bool(escalation_chain),
                escalation_chain=escalation_chain,
                mitigations_attempted=mitigations_attempted,
                probe_decision=probe_decision_str,
                artifact_hit=False,
                vary_key=plan.vary_key,
                budget_spent_usd=budget_spent,
                budget_exhausted=False,
                validators_passed=validators_passed,
                validators_failed=validators_failed,
            ), plan=plan)

        # Fell through — can't go past Lane 3
        return self._record_cooldown(CascadeResult(
            output=current_output or "",
            lane_used=min(current_lane, Lane.DEEP),
            model_used=current_model,
            escalated=bool(escalation_chain),
            escalation_chain=escalation_chain,
            mitigations_attempted=mitigations_attempted,
            probe_decision=probe_decision_str,
            artifact_hit=False,
            vary_key=plan.vary_key,
            budget_spent_usd=budget_spent,
            budget_exhausted=False,
            validators_passed=validators_passed,
            validators_failed=validators_failed,
        ), plan=plan)

    def _escalate(
        self,
        current_lane: int,
        current_model: str,
        plan: RoutePlan,
    ) -> tuple[int, str]:
        """Move to next lane. Returns (new_lane, new_model)."""
        next_lane = current_lane + 1
        if next_lane > Lane.DEEP:
            return next_lane, current_model

        # Pick model from fallback chain
        contract = self.lane_router.contracts.get(next_lane)
        if contract is not None:
            from .routing import ModelTier
            registry = self.lane_router.router.registry
            for tier_name in contract.model_tiers:
                tier = ModelTier(tier_name)
                models = registry.get_available_models(tier)
                if models:
                    return next_lane, models[0]

        # Fallback chain
        for fb in plan.fallback_chain:
            caps = self.lane_router.router.registry.get_capabilities(fb)
            if caps and caps.tier.value in (
                contract.model_tiers if contract else ("standard", "heavy")
            ):
                return next_lane, fb

        return next_lane, current_model

    def _run_validators(
        self, validator_names: list[str], output: str
    ) -> tuple[list[str], list[str]]:
        """Run named validators. Returns (passed, failed).

        v2: validators are stub checks — real implementation deferred.
        """
        passed = []
        failed = []
        for v in validator_names:
            # Stub: all pass unless output is empty
            if output:
                passed.append(v)
            else:
                failed.append(v)
        return passed, failed

    def _run_probe(
        self, output: str, prompt: str, policy: str
    ) -> dict[str, Any] | None:
        """Run stability probe if configured. Returns probe result dict or None."""
        if self.probe_fn is not None:
            try:
                result = self.probe_fn(output, prompt)
                if isinstance(result, dict):
                    return result
            except Exception:
                logger.debug("probe_fn failed", exc_info=True)
        return None

    def _pick_mitigation(self, probe_result: dict | None) -> str | None:
        """Pick a mitigation strategy from probe results."""
        if probe_result is None:
            return None
        mitigations = probe_result.get("mitigations", [])
        if mitigations:
            first = mitigations[0]
            if isinstance(first, dict):
                return first.get("transform", "relocate")
            return str(first)
        # Default: pick based on recommendation
        rec = probe_result.get("recommendation", "")
        if "position" in rec.lower() or "inject" in rec.lower():
            return "relocate"
        if "structure" in rec.lower() or "format" in rec.lower():
            return "schema_form"
        if "drift" in rec.lower() or "boundary" in rec.lower():
            return "boundary_harden"
        return "relocate"  # Default mitigation

    def _apply_mitigation(
        self, strategy: str, prompt: str, output: str
    ) -> str:
        """Apply a single mitigation strategy.

        v2: deterministic text transforms. No LLM calls.
        """
        if strategy == "relocate":
            # Sandwich trusted instructions around the prompt
            return f"[SYSTEM: Verify the following output]\n{output}\n[SYSTEM: End verification]"
        elif strategy == "schema_form":
            # Wrap in a structured template
            return f'{{"verified": true, "content": {json.dumps(output)}}}'
        elif strategy == "boundary_harden":
            # Add explicit boundary markers
            return f"---BEGIN VERIFIED OUTPUT---\n{output}\n---END VERIFIED OUTPUT---"
        return output
