# SPDX-License-Identifier: Apache-2.0
"""
ag-admit — the admission mouth for governed self-build.

A dumb generator (Codex/Claude scaffold) proposes a ``CandidateStep`` (a *diff-shaped*
construction step). ``ag_admit`` reduces it to a ``PreflightRequest``, hands it to a
``PreflightClient`` gate, and projects the gate's *source verdict* onto the four-verdict
``StepVerdict`` union. A disposable conductor carries the ``CandidateStep`` and obeys the
``StepVerdict`` — it never decides admissibility.

Doctrine: ``docs/doctrine/specs_do_not_bootstrap.md`` — "Cheap construction, expensive
admission." The reusable piece is the admission client, not the loop.

Load-bearing invariants (each has a test in ``tests/test_ag_admit.py``):

1. **The gate observes touched paths from the diff.** ``CandidateStep.touched_paths`` is
   a DECLARED claim, recorded for cross-check, NEVER the authority basis.
2. **Source verdicts are LOCAL.** No ``scope.EscalationVerdict`` / ``ScopeGovernor``
   import — the toy patch-authority gate stays decoupled from the SRE scope governor.
3. **Projection reads ``raw.source_verdict``**, never the coarse
   ``PreflightDecision.decision`` (``"allow"|"would_block"|"blocked"``). ``BLOCK`` and
   ``CANNOT_TESTIFY`` are both ``decision="blocked"`` on the wire but project distinctly.
4. **Unknown / unmapped source verdict → ``CANNOT_TESTIFY``** — never best-effort
   ``REJECT`` / ``NEEDS_HUMAN``.
5. **``NEEDS_HUMAN`` only on an explicit source ``REQUIRE_HUMAN``.** The conductor must
   not rewrite a ``CANNOT_TESTIFY`` into ``NEEDS_HUMAN``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Any

from .governed_dispatch import PreflightDecision, PreflightRequest

# =============================================================================
# CandidateStep — diff-shaped construction step (doctrine's named 11 fields)
# =============================================================================


@dataclass(frozen=True)
class CandidateStep:
    """A construction step a dumb generator wants admitted.

    Diff-shaped (distinct from dispatch-shaped ``PreflightRequest``). Per
    ``feedback_kind_fit_is_guard_not_enum``: a data carrier, not a typed-enum zoo.
    """

    step_id: str
    repo: str
    base_commit: str
    diff: str
    declared_intent: str
    scope: str  # declared authorized surface, e.g. "toy_repo/allowed/**"
    # DECLARED — carried for cross-check + receipt, NOT the decision basis:
    touched_paths: tuple[str, ...] = ()
    required_authorities: tuple[str, ...] = ()
    tests_to_run: tuple[str, ...] = ()
    invariants_claimed: tuple[str, ...] = ()
    receipts_proposed: tuple[str, ...] = ()
    rollback_note: str = ""


# =============================================================================
# StepVerdict — the four-verdict union (ratified; consumer = the conductor)
# =============================================================================


class StepVerdict(Enum):
    ADMIT = "admit"
    REJECT = "reject"
    CANNOT_TESTIFY = "cannot_testify"
    NEEDS_HUMAN = "needs_human"


# Local source-verdict strings (NOT EscalationVerdict — no ScopeGovernor coupling).
SOURCE_PROCEED = "PROCEED"
SOURCE_BLOCK = "BLOCK"
SOURCE_CANNOT_TESTIFY = "CANNOT_TESTIFY"
SOURCE_REQUIRE_HUMAN = "REQUIRE_HUMAN"

# Recognized aliases other gates may emit (projection accepts these strings; it does
# NOT import any other gate's enum). Keeps ag_admit a multi-gate projector.
_ADMIT_SOURCES = frozenset({SOURCE_PROCEED, "PASS", "ALLOW"})
_REJECT_SOURCES = frozenset({SOURCE_BLOCK, "DENY"})

# Source reasons emitted by DiffPathScopeGate.
REASON_PATHS_WITHIN_SCOPE = "paths_within_scope"
REASON_PATH_OUT_OF_SCOPE = "path_out_of_scope"
REASON_CANNOT_OBSERVE = "cannot_observe_touched_paths"
REASON_UNSAFE_PATH = "unsafe_or_ambiguous_path"


def project_source_verdict(source_verdict: str | None) -> StepVerdict:
    """Project a gate's source verdict string onto the StepVerdict union.

    THE single, centralized projection. The conductor must call this (or read an
    ``AdmitResult``) — it must never branch on a raw string itself.

    Unknown / missing → CANNOT_TESTIFY (operator rule: never best-effort).
    NEEDS_HUMAN only on an explicit REQUIRE_HUMAN.
    """
    if source_verdict in _ADMIT_SOURCES:
        return StepVerdict.ADMIT
    if source_verdict in _REJECT_SOURCES:
        return StepVerdict.REJECT
    if source_verdict == SOURCE_REQUIRE_HUMAN:
        return StepVerdict.NEEDS_HUMAN
    # SOURCE_CANNOT_TESTIFY, None, "would_block", or any unrecognized value:
    return StepVerdict.CANNOT_TESTIFY


# =============================================================================
# AdmitResult — everything the conductor's receipt needs
# =============================================================================


@dataclass(frozen=True)
class AdmitResult:
    verdict: StepVerdict
    source_verdict: str | None
    reasons: tuple[dict[str, Any], ...]
    observed_paths: tuple[str, ...]
    declared_scope: str
    preflight_decision: PreflightDecision


def _candidate_to_request(step: CandidateStep) -> PreflightRequest:
    """Reduce a diff-shaped CandidateStep to a dispatch-shaped PreflightRequest.

    The diff rides in ``args`` so the GATE (not this adapter) observes paths from it.
    """
    return PreflightRequest(
        tool_id="construction.apply",
        correlation_id=step.step_id,
        args={
            "repo": step.repo,
            "base_commit": step.base_commit,
            "diff": step.diff,
            "declared_intent": step.declared_intent,
            # declared, non-authoritative — for cross-check + receipt only:
            "declared_touched_paths": list(step.touched_paths),
            "required_authorities": list(step.required_authorities),
        },
        exceptions=[],
    )


def _extract_reasons(decision: PreflightDecision) -> tuple[dict[str, Any], ...]:
    reasons: list[dict[str, Any]] = []
    raw = decision.raw if isinstance(decision.raw, dict) else {}
    if raw.get("reason"):
        reasons.append(
            {"reason": raw["reason"], "source_verdict": raw.get("source_verdict")}
        )
    for br in decision.block_reasons:
        if isinstance(br, dict):
            reasons.append(br)
    return tuple(reasons)


async def ag_admit(step: CandidateStep, client) -> AdmitResult:
    """Submit a CandidateStep to an admission gate and project the verdict.

    Pure translation + projection — no authority decision of its own. ``client`` is any
    object satisfying the ``governed_dispatch.PreflightClient`` Protocol.
    """
    request = _candidate_to_request(step)
    decision = await client.preflight(request)
    raw = decision.raw if isinstance(decision.raw, dict) else {}
    source_verdict = raw.get("source_verdict")
    verdict = project_source_verdict(source_verdict)
    observed = raw.get("observed_paths") or []
    return AdmitResult(
        verdict=verdict,
        source_verdict=source_verdict,
        reasons=_extract_reasons(decision),
        observed_paths=tuple(observed),
        declared_scope=step.scope,
        preflight_decision=decision,
    )


# =============================================================================
# DiffPathScopeGate — the toy patch-authority gate (slice 0)
# =============================================================================
#
# A deliberately narrow gate: every observed touched path (derived from the diff,
# never from CandidateStep.touched_paths) must fall inside the granted path globs.
# It governs PATCH PATH AUTHORITY — NOT SRE operational scope. ScopeGovernor is left
# entirely untouched (no import, no coupling).


def _observe_paths_from_diff(diff_text: str) -> list[str] | None:
    """Observe touched paths from a unified diff's file headers.

    Collects pre-image (``--- a/...``) and post-image (``+++ b/...``) paths, dropping
    ``/dev/null``. Returns None if no file header is present (cannot observe).
    """
    raw_paths: list[str] = []
    saw_header = False
    for line in diff_text.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            saw_header = True
            token = line[4:].strip()
            # strip a trailing tab + timestamp if present (POSIX diff)
            token = token.split("\t", 1)[0].strip()
            if token and token != "/dev/null":
                raw_paths.append(token)
        elif line.startswith("diff --git "):
            saw_header = True
            parts = line[len("diff --git ") :].split()
            for p in parts:
                if p and p != "/dev/null":
                    raw_paths.append(p)
    if not saw_header:
        return None
    return raw_paths


def _normalize_repo_path(raw: str) -> str | None:
    """Normalize to a repo-relative POSIX path, or None if unsafe/ambiguous.

    Rejects: ``/dev/null``, empty, absolute paths, ``..`` segments, repo-root escape.
    "Path handling is where clown cars enter the courtroom."
    """
    p = raw.strip()
    # strip git a/ b/ prefixes
    if p.startswith(("a/", "b/")):
        p = p[2:]
    if not p or p == "/dev/null":
        return None
    if p.startswith("/"):  # absolute
        return None
    if "\\" in p:  # ambiguous separator
        return None
    parts = PurePosixPath(p).parts
    if not parts:
        return None
    if any(part == ".." for part in parts):
        return None
    norm = PurePosixPath(*parts).as_posix()
    if not norm or norm.startswith("/"):
        return None
    return norm


def _path_matches_glob(path: str, glob: str) -> bool:
    """Path-aware glob match. ``foo/**`` = prefix match; ``foo/*`` = direct children."""
    if glob.endswith("/**"):
        prefix = glob[:-3]
        return path == prefix or path.startswith(prefix + "/")
    if glob.endswith("/*"):
        prefix = glob[:-2]
        if not path.startswith(prefix + "/"):
            return False
        return "/" not in path[len(prefix) + 1 :]
    return path == glob


def _path_in_any_scope(path: str, globs: tuple[str, ...]) -> bool:
    return any(_path_matches_glob(path, g) for g in globs)


class DiffPathScopeGate:
    """Patch-authority gate: observed diff paths must be ⊆ the granted path globs.

    Satisfies the ``governed_dispatch.PreflightClient`` Protocol; runs in-process, no
    daemon. NOT the SRE ScopeGovernor — local source-verdict strings, no EscalationVerdict.
    """

    GATE_NAME = "DiffPathScopeGate"
    OBSERVATION_METHOD = "unidiff_header_parse"

    def __init__(self, allowed_globs: tuple[str, ...] | list[str]):
        self.allowed_globs: tuple[str, ...] = tuple(allowed_globs)

    def _decision(
        self,
        *,
        decision: str,
        source_verdict: str,
        reason: str,
        observed_paths: list[str],
        declared_touched_paths: list[str],
        extra_block: dict[str, Any] | None = None,
    ) -> PreflightDecision:
        raw: dict[str, Any] = {
            "source_gate": self.GATE_NAME,
            "source_verdict": source_verdict,
            "reason": reason,
            "observed_paths": observed_paths,
            "allowed_scope": list(self.allowed_globs),
            "observation_method": self.OBSERVATION_METHOD,
            # declared paths are non-authoritative; recorded for cross-check only:
            "declared_touched_paths": sorted(set(declared_touched_paths)),
            "declared_observed_mismatch": (
                sorted(set(declared_touched_paths)) != sorted(set(observed_paths))
            ),
        }
        block_reasons: list[dict[str, Any]] = []
        if decision == "blocked":
            br = {"kind": reason, "source_verdict": source_verdict}
            if extra_block:
                br.update(extra_block)
            block_reasons.append(br)
        return PreflightDecision(
            decision=decision,
            mode="enforce",
            block_reasons=block_reasons,
            raw=raw,
        )

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        diff = request.args.get("diff")
        declared = list(request.args.get("declared_touched_paths") or [])

        if not isinstance(diff, str) or not diff.strip():
            return self._decision(
                decision="blocked",  # fail-closed: it did not allow
                source_verdict=SOURCE_CANNOT_TESTIFY,
                reason=REASON_CANNOT_OBSERVE,
                observed_paths=[],
                declared_touched_paths=declared,
            )

        observed_raw = _observe_paths_from_diff(diff)
        if observed_raw is None:
            return self._decision(
                decision="blocked",
                source_verdict=SOURCE_CANNOT_TESTIFY,
                reason=REASON_CANNOT_OBSERVE,
                observed_paths=[],
                declared_touched_paths=declared,
            )

        normalized: list[str] = []
        for raw_path in observed_raw:
            norm = _normalize_repo_path(raw_path)
            if norm is None:
                return self._decision(
                    decision="blocked",
                    source_verdict=SOURCE_CANNOT_TESTIFY,
                    reason=REASON_UNSAFE_PATH,
                    observed_paths=sorted(set(observed_raw)),
                    declared_touched_paths=declared,
                    extra_block={"offending_path": raw_path},
                )
            normalized.append(norm)
        observed = sorted(set(normalized))

        out_of_scope = [
            p for p in observed if not _path_in_any_scope(p, self.allowed_globs)
        ]
        if out_of_scope:
            return self._decision(
                decision="blocked",
                source_verdict=SOURCE_BLOCK,
                reason=REASON_PATH_OUT_OF_SCOPE,
                observed_paths=observed,
                declared_touched_paths=declared,
                extra_block={"out_of_scope": out_of_scope},
            )

        return self._decision(
            decision="allow",
            source_verdict=SOURCE_PROCEED,
            reason=REASON_PATHS_WITHIN_SCOPE,
            observed_paths=observed,
            declared_touched_paths=declared,
        )

    async def record(
        self,
        request: PreflightRequest,
        result_status: str,
        preflight_token: str | None = None,
        record_id: str | None = None,
    ) -> dict[str, Any]:
        # The toy gate has no durable ledger; recording is a no-op acknowledgement.
        return {
            "recorded": True,
            "gate": self.GATE_NAME,
            "result_status": result_status,
            "record_id": record_id,
        }


# =============================================================================
# Test stub gate — emits an explicit REQUIRE_HUMAN (fixture only)
# =============================================================================


class _FixedVerdictGate:
    """A stub PreflightClient that emits a fixed source verdict. Fixtures/tests only.

    Used to exercise NEEDS_HUMAN (explicit REQUIRE_HUMAN) and unknown-verdict paths
    without a custody heuristic in the real gate.
    """

    def __init__(self, source_verdict: str | None, decision: str = "blocked"):
        self._source_verdict = source_verdict
        self._decision = decision

    async def preflight(self, request: PreflightRequest) -> PreflightDecision:
        raw: dict[str, Any] = {"source_gate": "_FixedVerdictGate"}
        if self._source_verdict is not None:
            raw["source_verdict"] = self._source_verdict
        return PreflightDecision(decision=self._decision, mode="enforce", raw=raw)

    async def record(self, request, result_status, preflight_token=None, record_id=None):
        return {"recorded": True}
