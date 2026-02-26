# SPDX-License-Identifier: Apache-2.0
"""
Verifier Gate: composition boundary for mechanical verification.

Netflix pattern — "allow flexibility upstream, put a hard mechanical contract
at the boundary."  The governor has verifiers, invariants, receipts, routing,
and provenance.  This module is the composition boundary that binds them.

Types + suite composition + receipt emission + env hash + flake/quarantine.
No framework, no plugins, no YAML.

Design:
- All dataclasses are frozen.  No mutable defaults.
- Map-like fields stored as tuple[tuple[str, ...], ...] (sorted), normalized
  in __post_init__.  Stable hashing, stable to_dict(), no accidental mutation.
- All hashing goes through canonical_json + content_hash from gate_receipt.py.
"""

from __future__ import annotations

import logging
import math
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, NamedTuple

from governor.gate_receipt import (
    GateReceiptSystem,
    canonical_json,
    content_hash,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

VERIFIER_GATE = "verifier_gate"

VALID_ARTIFACT_KINDS: frozenset[str] = frozenset({
    "code_patch",
    "config",
    "migration",
    "model_port",
    "policy_bundle",
    "prompt_template",
})


# =============================================================================
# Enums
# =============================================================================


class Verdict(str, Enum):
    """Suite-level verdict after aggregating all verifier results."""

    PASS = "pass"
    FAIL = "fail"
    QUARANTINE = "quarantine"
    NEEDS_HUMAN = "needs_human"
    INCONCLUSIVE = "inconclusive"


class RunStatus(str, Enum):
    """Per-verifier run status (debugging/routing, not in stable evidence)."""

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    MISSING = "missing"


# Verdict → gate receipt verdict
_VERDICT_TO_GATE_VERDICT: dict[Verdict, str] = {
    Verdict.PASS: "pass",
    Verdict.FAIL: "block",
    Verdict.QUARANTINE: "warn",
    Verdict.NEEDS_HUMAN: "observe",
    Verdict.INCONCLUSIVE: "observe",
}


# =============================================================================
# Callable Protocol
# =============================================================================


class CheckOutcome(NamedTuple):
    """Return type for verifier check functions."""

    passed: bool
    metrics: tuple[tuple[str, Any], ...] = ()


# =============================================================================
# Internal Helpers
# =============================================================================


def _safe_metric_value(v: Any) -> int | float | str | bool | None:
    """Coerce a metric value to a JSON-safe type, or raise TypeError."""
    if v is None or isinstance(v, (bool, str, int)):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise TypeError(
                f"Metric value {v!r} is not JSON-safe "
                "(NaN and Infinity are not representable in JSON)"
            )
        return v
    raise TypeError(
        f"Metric value {v!r} (type {type(v).__name__}) is not JSON-safe; "
        "expected int | float | str | bool | None"
    )


def _normalize_metrics(
    raw: dict[str, Any] | tuple[tuple[str, Any], ...] | None,
) -> tuple[tuple[str, Any], ...]:
    """Normalize metrics to a sorted tuple of pairs with JSON-safe values."""
    if raw is None:
        return ()
    if isinstance(raw, dict):
        return tuple(sorted((k, _safe_metric_value(v)) for k, v in raw.items()))
    # Already a tuple — validate values
    return tuple(sorted((k, _safe_metric_value(v)) for k, v in raw))


def _normalize_str_pairs(
    raw: dict[str, str] | tuple[tuple[str, str], ...] | None,
) -> tuple[tuple[str, str], ...]:
    """Normalize string-valued pairs to a sorted tuple."""
    if raw is None:
        return ()
    if isinstance(raw, dict):
        return tuple(sorted(raw.items()))
    return tuple(sorted(raw))


def _stable_hash(d: dict[str, Any]) -> str:
    """Hash a dict through canonical_json + content_hash."""
    return content_hash(canonical_json(d))


# =============================================================================
# Types (all frozen dataclasses)
# =============================================================================


@dataclass(frozen=True)
class FlakePolicy:
    """Policy for handling flaky verifiers."""

    max_reruns: int = 0
    max_flake_score: float = 0.0
    quarantine_on_flake: bool = True

    def __post_init__(self) -> None:
        if self.max_reruns < 0:
            raise ValueError(f"max_reruns must be >= 0, got {self.max_reruns}")
        if not (0.0 <= self.max_flake_score <= 1.0):
            raise ValueError(
                f"max_flake_score must be in [0.0, 1.0], got {self.max_flake_score}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_reruns": self.max_reruns,
            "max_flake_score": self.max_flake_score,
            "quarantine_on_flake": self.quarantine_on_flake,
        }


@dataclass(frozen=True)
class Candidate:
    """A candidate artifact to be verified by a suite."""

    candidate_id: str
    artifact_kind: str
    payload_hash: str
    base_ref: str | None = None
    declared_intent: str | None = None
    proposed_scope: tuple[str, ...] = ()
    provenance: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        # Normalize artifact_kind
        kind = self.artifact_kind.strip().lower()
        if kind not in VALID_ARTIFACT_KINDS:
            raise ValueError(
                f"Invalid artifact_kind {self.artifact_kind!r}; "
                f"must be one of {sorted(VALID_ARTIFACT_KINDS)}"
            )
        object.__setattr__(self, "artifact_kind", kind)

        # Normalize proposed_scope
        if isinstance(self.proposed_scope, list):
            object.__setattr__(
                self, "proposed_scope",
                tuple(s.strip() for s in self.proposed_scope),
            )
        elif isinstance(self.proposed_scope, tuple):
            object.__setattr__(
                self, "proposed_scope",
                tuple(s.strip() for s in self.proposed_scope),
            )

        # Normalize provenance
        prov = self.provenance
        if isinstance(prov, dict):
            prov = tuple(sorted(prov.items()))
        else:
            prov = tuple(sorted(prov))
        object.__setattr__(self, "provenance", prov)

        # Normalize declared_intent
        if self.declared_intent is not None:
            stripped = self.declared_intent.strip() or None
            object.__setattr__(self, "declared_intent", stripped)

    def content_hash(self) -> str:
        """Content hash excluding candidate_id and provenance (metadata)."""
        d = {
            "artifact_kind": self.artifact_kind,
            "payload_hash": self.payload_hash,
            "base_ref": self.base_ref,
            "proposed_scope": list(self.proposed_scope),
            "declared_intent": self.declared_intent,
        }
        return _stable_hash(d)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "artifact_kind": self.artifact_kind,
            "payload_hash": self.payload_hash,
            "base_ref": self.base_ref,
            "declared_intent": self.declared_intent,
            "proposed_scope": list(self.proposed_scope),
            "provenance": {k: v for k, v in self.provenance},
        }


@dataclass(frozen=True)
class VerifierEntry:
    """A single verifier in a suite."""

    verifier_id: str
    version: str
    required: bool = True
    timeout_s: int = 300
    run_contract: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if self.timeout_s <= 0:
            raise ValueError(f"timeout_s must be > 0, got {self.timeout_s}")
        # Normalize run_contract
        rc = self.run_contract
        if isinstance(rc, dict):
            rc = tuple(sorted(rc.items()))
        else:
            rc = tuple(sorted(rc))
        object.__setattr__(self, "run_contract", rc)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verifier_id": self.verifier_id,
            "version": self.version,
            "required": self.required,
            "timeout_s": self.timeout_s,
            "run_contract": {k: v for k, v in self.run_contract},
        }


@dataclass(frozen=True)
class VerifierSuite:
    """An ordered collection of verifiers with shared flake policy."""

    suite_id: str
    version: str
    entries: tuple[VerifierEntry, ...]
    flake_policy: FlakePolicy = field(default_factory=FlakePolicy)
    env_fingerprint_required: bool = False

    def __post_init__(self) -> None:
        if len(self.entries) == 0:
            raise ValueError("VerifierSuite must have at least one entry")
        ids = [e.verifier_id for e in self.entries]
        if len(ids) != len(set(ids)):
            dupes = [vid for vid in ids if ids.count(vid) > 1]
            raise ValueError(f"Duplicate verifier_id(s): {sorted(set(dupes))}")

    def get_entry(self, verifier_id: str) -> VerifierEntry | None:
        for e in self.entries:
            if e.verifier_id == verifier_id:
                return e
        return None

    def required_ids(self) -> frozenset[str]:
        return frozenset(e.verifier_id for e in self.entries if e.required)

    def all_ids(self) -> frozenset[str]:
        return frozenset(e.verifier_id for e in self.entries)

    def policy_dict(self) -> dict[str, Any]:
        """Deterministic dict of suite policy for hashing."""
        return {
            "entries": [
                {
                    "verifier_id": e.verifier_id,
                    "version": e.version,
                    "required": e.required,
                    "timeout_s": e.timeout_s,
                    "run_contract": {k: v for k, v in e.run_contract},
                }
                for e in self.entries
            ],
            "flake_policy": self.flake_policy.to_dict(),
            "env_fingerprint_required": self.env_fingerprint_required,
        }

    def policy_hash(self) -> str:
        return _stable_hash(self.policy_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "version": self.version,
            "entries": [e.to_dict() for e in self.entries],
            "flake_policy": self.flake_policy.to_dict(),
            "env_fingerprint_required": self.env_fingerprint_required,
        }


@dataclass(frozen=True)
class VerifierResult:
    """Result of running a single verifier (possibly with reruns)."""

    verifier_id: str
    version: str
    passed: bool
    status: RunStatus
    runs: int
    failures: int
    flake_score: float
    duration_ms: int
    error_message: str | None = None
    metrics: tuple[tuple[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "verifier_id": self.verifier_id,
            "version": self.version,
            "passed": self.passed,
            "status": self.status.value,
            "runs": self.runs,
            "failures": self.failures,
            "flake_score": self.flake_score,
            "duration_ms": self.duration_ms,
        }
        if self.error_message is not None:
            d["error_message"] = self.error_message
        if self.metrics:
            d["metrics"] = {k: v for k, v in self.metrics}
        return d

    def stable_dict(self) -> dict[str, Any]:
        """Stable subset for evidence hashing.

        Excludes duration_ms, error_message, metrics, status (runtime noise)
        and flake_score (float — ratio is derivable from failures/runs,
        integers are safer for canonical hashing across runtimes).
        """
        return {
            "verifier_id": self.verifier_id,
            "version": self.version,
            "passed": self.passed,
            "runs": self.runs,
            "failures": self.failures,
        }


@dataclass(frozen=True)
class EnvFingerprint:
    """Environment fingerprint for reproducibility tracking."""

    python_version: str
    platform_str: str
    git_sha: str | None = None
    dependency_lock_hash: str | None = None
    extra: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        # Normalize extra
        ex = self.extra
        if isinstance(ex, dict):
            ex = tuple(sorted(ex.items()))
        else:
            ex = tuple(sorted(ex))
        object.__setattr__(self, "extra", ex)

    def fingerprint(self) -> str:
        """Content hash of the environment fingerprint."""
        d = {
            "python_version": self.python_version,
            "platform_str": self.platform_str,
            "git_sha": self.git_sha or "",
            "dependency_lock_hash": self.dependency_lock_hash or "",
            "extra": {k: v for k, v in self.extra},
        }
        return _stable_hash(d)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "python_version": self.python_version,
            "platform_str": self.platform_str,
        }
        if self.git_sha is not None:
            d["git_sha"] = self.git_sha
        if self.dependency_lock_hash is not None:
            d["dependency_lock_hash"] = self.dependency_lock_hash
        if self.extra:
            d["extra"] = {k: v for k, v in self.extra}
        return d


@dataclass(frozen=True)
class SuiteResult:
    """Result of running a full verifier suite against a candidate."""

    suite_id: str
    suite_version: str
    candidate_hash: str
    verdict: Verdict
    results: tuple[VerifierResult, ...]
    policy_version: str
    base_ref_hash: str | None
    env_fingerprint: str | None
    stable_receipt_hash: str
    receipt_hash: str | None = None
    receipt_emission_ok: bool | None = None
    receipt_emission_error: str | None = None

    def stable_evidence_dict(self) -> dict[str, Any]:
        """Stable evidence for receipt hashing. No runtime noise."""
        return {
            "candidate_hash": self.candidate_hash,
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "verdict": self.verdict.value,
            "results": [r.stable_dict() for r in self.results],
            "env_fingerprint": self.env_fingerprint,
        }

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "candidate_hash": self.candidate_hash,
            "verdict": self.verdict.value,
            "results": [r.to_dict() for r in self.results],
            "policy_version": self.policy_version,
            "base_ref_hash": self.base_ref_hash,
            "env_fingerprint": self.env_fingerprint,
            "stable_receipt_hash": self.stable_receipt_hash,
        }
        if self.receipt_hash is not None:
            d["receipt_hash"] = self.receipt_hash
        if self.receipt_emission_ok is not None:
            d["receipt_emission_ok"] = self.receipt_emission_ok
        if self.receipt_emission_error is not None:
            d["receipt_emission_error"] = self.receipt_emission_error
        return d


# =============================================================================
# Pure Functions
# =============================================================================


def compute_env_fingerprint(
    extra: dict[str, str] | None = None,
) -> EnvFingerprint:
    """Compute environment fingerprint from current runtime.

    Args:
        extra: Additional key-value pairs (lock hash, container digest, etc.)
    """
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    plat = platform.platform()

    git_sha: str | None = None
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_sha = result.stdout.strip()
    except Exception:
        pass

    return EnvFingerprint(
        python_version=py_ver,
        platform_str=plat,
        git_sha=git_sha,
        extra=_normalize_str_pairs(extra),
    )


def aggregate_verdict(
    results: tuple[VerifierResult, ...],
    suite: VerifierSuite,
) -> Verdict:
    """Aggregate per-verifier results into a suite-level verdict.

    Precedence: FAIL > INCONCLUSIVE > QUARANTINE > PASS.
    Only required verifiers affect the verdict (advisory never does).
    NEEDS_HUMAN is not mechanically produced.
    """
    required_ids = suite.required_ids()
    required_results = [r for r in results if r.verifier_id in required_ids]

    # Step 1: Any required verifier failed with runs > 0 → FAIL
    for r in required_results:
        if r.runs > 0 and not r.passed:
            return Verdict.FAIL

    # Step 2: Any required verifier has runs == 0 → INCONCLUSIVE
    for r in required_results:
        if r.runs == 0:
            return Verdict.INCONCLUSIVE

    # Also INCONCLUSIVE if a required verifier has no result at all
    result_ids = {r.verifier_id for r in results}
    for rid in required_ids:
        if rid not in result_ids:
            return Verdict.INCONCLUSIVE

    # Step 3: Flake check — passed but flake_score exceeds threshold
    for r in required_results:
        if r.passed and r.flake_score > suite.flake_policy.max_flake_score:
            if suite.flake_policy.quarantine_on_flake:
                return Verdict.QUARANTINE
            else:
                return Verdict.FAIL

    # Step 4: All required passed cleanly
    return Verdict.PASS


def run_verifier(
    entry: VerifierEntry,
    check_fn: Callable[[], bool | tuple[bool, dict[str, Any]] | CheckOutcome],
    max_reruns: int = 0,
) -> VerifierResult:
    """Run a single verifier, handling reruns and coercing return types.

    Args:
        entry: The verifier entry describing this verifier.
        check_fn: Callable returning bool, (bool, dict), or CheckOutcome.
        max_reruns: Maximum number of reruns on failure (from FlakePolicy).

    Returns:
        VerifierResult with run counts, flake score, timing, etc.
    """
    runs = 0
    failures = 0
    last_error: str | None = None
    last_status = RunStatus.PASS
    merged_metrics: dict[str, Any] = {}

    t0 = time.monotonic()

    # First run + reruns
    max_attempts = 1 + max_reruns
    passed = False

    for _ in range(max_attempts):
        runs += 1
        try:
            raw = check_fn()

            # Coerce return type
            if isinstance(raw, CheckOutcome):
                outcome = raw
            elif isinstance(raw, tuple):
                ok, mdict = raw
                outcome = CheckOutcome(
                    passed=bool(ok),
                    metrics=_normalize_metrics(mdict),
                )
            else:
                outcome = CheckOutcome(passed=bool(raw))

            if outcome.passed:
                passed = True
                last_status = RunStatus.PASS
                # Merge metrics from last successful run
                merged_metrics.update(dict(outcome.metrics))
                break  # First pass stops immediately
            else:
                failures += 1
                last_status = RunStatus.FAIL
                merged_metrics.update(dict(outcome.metrics))

        except Exception as exc:
            failures += 1
            last_error = f"{type(exc).__name__}: {exc}"
            last_status = RunStatus.ERROR

    t1 = time.monotonic()
    duration_ms = int((t1 - t0) * 1000)
    flake_score = failures / runs if runs > 0 else 0.0

    return VerifierResult(
        verifier_id=entry.verifier_id,
        version=entry.version,
        passed=passed,
        status=last_status,
        runs=runs,
        failures=failures,
        flake_score=flake_score,
        duration_ms=duration_ms,
        error_message=last_error if not passed else None,
        metrics=_normalize_metrics(merged_metrics),
    )


# =============================================================================
# Receipt Emission (internal)
# =============================================================================


@dataclass(frozen=True)
class _ReceiptEmissionResult:
    """Internal: result of best-effort receipt emission."""

    receipt_hash: str | None
    ok: bool | None  # None = no receipt system configured
    error: str | None = None


def _try_emit_receipt(
    candidate: Candidate,
    suite: VerifierSuite,
    verdict: Verdict,
    stable_evidence: dict[str, Any],
    receipt_system: GateReceiptSystem | None,
) -> _ReceiptEmissionResult:
    """Best-effort receipt emission. Fail-open."""
    if receipt_system is None:
        return _ReceiptEmissionResult(receipt_hash=None, ok=None)
    try:
        gate_verdict = _VERDICT_TO_GATE_VERDICT[verdict]
        subject = f"{candidate.content_hash()}:{suite.suite_id}@{suite.version}"
        receipt = receipt_system.emit(
            gate=VERIFIER_GATE,
            verdict=gate_verdict,
            subject_kind="verifier_suite",
            subject_bytes=subject.encode("utf-8"),
            evidence_bundle=stable_evidence,
            gate_config=suite.policy_dict(),
        )
        return _ReceiptEmissionResult(receipt_hash=receipt.receipt_id, ok=True)
    except Exception as exc:
        error_str = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Failed to emit verifier_gate receipt: %s", error_str, exc_info=True,
        )
        return _ReceiptEmissionResult(receipt_hash=None, ok=False, error=error_str)


# =============================================================================
# Suite Runner
# =============================================================================


def run_suite(
    candidate: Candidate,
    suite: VerifierSuite,
    checks: dict[str, Callable[[], bool | tuple[bool, dict[str, Any]] | CheckOutcome]],
    env: EnvFingerprint | None = None,
    receipt_system: GateReceiptSystem | None = None,
) -> SuiteResult:
    """Run a full verifier suite against a candidate.

    Args:
        candidate: The artifact to verify.
        suite: The suite defining which verifiers to run.
        checks: Mapping of verifier_id → callable.
        env: Optional environment fingerprint.
        receipt_system: Optional receipt system for emission.

    Returns:
        SuiteResult with aggregated verdict and per-verifier results.
    """
    candidate_hash = candidate.content_hash()
    env_fp = env.fingerprint() if env is not None else None
    policy_ver = suite.policy_hash()
    base_ref_hash = (
        content_hash(candidate.base_ref.encode("utf-8"))
        if candidate.base_ref is not None
        else None
    )

    # Early return: env required but missing
    if suite.env_fingerprint_required and env is None:
        verdict = Verdict.INCONCLUSIVE
        results: tuple[VerifierResult, ...] = ()
        evidence = _build_stable_evidence(
            candidate_hash, suite, verdict, results, env_fp,
        )
        stable_hash = _stable_hash({
            "subject": f"{candidate_hash}:{suite.suite_id}@{suite.version}",
            "policy_hash": policy_ver,
            "evidence": evidence,
        })
        emission = _try_emit_receipt(
            candidate, suite, verdict, evidence, receipt_system,
        )
        return SuiteResult(
            suite_id=suite.suite_id,
            suite_version=suite.version,
            candidate_hash=candidate_hash,
            verdict=verdict,
            results=results,
            policy_version=policy_ver,
            base_ref_hash=base_ref_hash,
            env_fingerprint=env_fp,
            stable_receipt_hash=stable_hash,
            receipt_hash=emission.receipt_hash,
            receipt_emission_ok=emission.ok,
            receipt_emission_error=emission.error,
        )

    # Run verifiers in suite order
    result_list: list[VerifierResult] = []
    for entry in suite.entries:
        fn = checks.get(entry.verifier_id)
        if fn is None:
            if entry.required:
                # Missing callable for required → MISSING result
                result_list.append(VerifierResult(
                    verifier_id=entry.verifier_id,
                    version=entry.version,
                    passed=False,
                    status=RunStatus.MISSING,
                    runs=0,
                    failures=0,
                    flake_score=0.0,
                    duration_ms=0,
                ))
            # Advisory missing → skip entirely
            continue
        vr = run_verifier(entry, fn, max_reruns=suite.flake_policy.max_reruns)
        result_list.append(vr)

    results = tuple(result_list)
    verdict = aggregate_verdict(results, suite)

    evidence = _build_stable_evidence(
        candidate_hash, suite, verdict, results, env_fp,
    )
    stable_hash = _stable_hash({
        "subject": f"{candidate_hash}:{suite.suite_id}@{suite.version}",
        "policy_hash": policy_ver,
        "evidence": evidence,
    })

    emission = _try_emit_receipt(
        candidate, suite, verdict, evidence, receipt_system,
    )

    return SuiteResult(
        suite_id=suite.suite_id,
        suite_version=suite.version,
        candidate_hash=candidate_hash,
        verdict=verdict,
        results=results,
        policy_version=policy_ver,
        base_ref_hash=base_ref_hash,
        env_fingerprint=env_fp,
        stable_receipt_hash=stable_hash,
        receipt_hash=emission.receipt_hash,
        receipt_emission_ok=emission.ok,
        receipt_emission_error=emission.error,
    )


def _build_stable_evidence(
    candidate_hash: str,
    suite: VerifierSuite,
    verdict: Verdict,
    results: tuple[VerifierResult, ...],
    env_fingerprint: str | None,
) -> dict[str, Any]:
    """Build stable evidence dict for receipt hashing."""
    return {
        "candidate_hash": candidate_hash,
        "suite_id": suite.suite_id,
        "suite_version": suite.version,
        "verdict": verdict.value,
        "results": [r.stable_dict() for r in results],
        "env_fingerprint": env_fingerprint,
    }


# =============================================================================
# Monotonicity Check
# =============================================================================


def is_monotonic(strict_suite: VerifierSuite, weak_suite: VerifierSuite) -> bool:
    """Check if strict_suite is a superset of weak_suite (by verifier_id).

    Returns True if every verifier_id in weak_suite also appears in strict_suite.
    ID-based only (not version matching). Informational.
    """
    return weak_suite.all_ids().issubset(strict_suite.all_ids())
