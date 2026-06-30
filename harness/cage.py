# SPDX-License-Identifier: Apache-2.0
"""H-series cage contract + a refuse-live backend (cage-DESIGN slice, OUTSIDE AG).

> The cage gets a constitution before it gets a keycard.

This is the contract-first cage slice ratified by `docs/playbooks/harness-cage-review.md`
(operator pass, 2026-06-30). It defines the *contract* a future real cage backend must
satisfy and ships exactly one backend — `RefusingCage` / `NoLiveCage` — that **always
refuses live actor admission**. It proves the cage/admission API without pretending
containment exists. There is **no execution surface here**: no method runs, spawns, or
streams an actor. Running a live actor is H2 — a separate, later, separately-ratified
gate. This module never gets there.

Three things this slice fixes, all reimplemented in-lane (this file does NOT import
`governor` — the contract between H and AG is artifacts, not shared Python types):

1. **Refuse-live by attestation, not by hardcode.** A cage may admit a live actor ONLY
   if its attestation *confirms isolation* in *live* scope. `RefusingCage` attests
   nothing, so live is refused — structurally, the same shape AG's own
   `admit_origin_under_cage` uses (`safe` alone is never enough). No shipped backend
   confirms live isolation, so live admission is unreachable.
2. **Audit-store layout, outside AG.** Tainted harness transcripts live at
   `$XDG_STATE_HOME/agent-gov/harness-runs/` (fallback `~/.local/state/...`), never in
   the repo and never in AG's ingest path. These are pure path computations — this slice
   writes nothing.
3. **One-artifact ingest boundary.** The only artifact H may hand AG is `actor_output.v0`.
   `assert_ag_ingestible()` refuses anything else with a typed error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from .actor_harness import ACTOR_KINDS

# --------------------------------------------------------------------------- #
# Scopes + closed refusal vocabulary.
# --------------------------------------------------------------------------- #

SCOPE_NONE = "none"  # confirms nothing; no live, no synthetic isolation claim
SCOPE_LIVE = "live"  # a real backend attesting genuine isolation (none ship here)
CAGE_SCOPES = frozenset({SCOPE_NONE, SCOPE_LIVE})

# Typed live-admission refusal codes (closed). A refusal is a value with one of these,
# never a bare bool or a free-text reason.
REFUSED_NO_ISOLATION_ATTESTED = "live_admission_refused_no_isolation_attested"
REFUSED_NOT_LIVE_SCOPE = "live_admission_refused_not_live_scope"
REFUSED_UNKNOWN_ACTOR_KIND = "live_admission_refused_unknown_actor_kind"
LIVE_ADMISSION_REFUSAL_CODES = frozenset(
    {
        REFUSED_NO_ISOLATION_ATTESTED,
        REFUSED_NOT_LIVE_SCOPE,
        REFUSED_UNKNOWN_ACTOR_KIND,
    }
)

# The single AG-ingestible artifact type. Absence-restrictive: anything not here is
# refused. No diff-reference, no verifier result, no auxiliary bundle.
AG_INGESTIBLE_ARTIFACT_TYPE = "actor_output.v0"
AG_INGESTIBLE_ARTIFACT_TYPES = frozenset({AG_INGESTIBLE_ARTIFACT_TYPE})


class CageError(ValueError):
    """Base for typed cage-contract rejections."""


class LiveAdmissionRefused(CageError):
    """A live actor was refused admission. ``code`` is from the closed
    ``LIVE_ADMISSION_REFUSAL_CODES`` vocabulary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


class AuditPathError(CageError):
    """A run id is not a single safe path segment (traversal / separator / empty)."""


class NonIngestibleArtifact(CageError):
    """An artifact type other than ``actor_output.v0`` was offered for AG ingest."""

    def __init__(self, artifact_type: str) -> None:
        super().__init__(
            f"artifact type {artifact_type!r} is not AG-ingestible; the only "
            f"AG-ingestible artifact is {AG_INGESTIBLE_ARTIFACT_TYPE!r}"
        )
        self.artifact_type = artifact_type


# --------------------------------------------------------------------------- #
# The attestation + admission value types.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CageAttestation:
    """What a cage backend *confirms* about its isolation. ``confirms_isolation`` is a
    real claim a real backend earns; ``scope`` says in which lane.

    Invariant (mirrors AG's verdict discipline): you cannot confirm isolation outside
    ``live`` scope — a half-confirmed cage is a lie. So ``confirms_isolation`` ⇒
    ``scope == live``. A backend that confirms nothing carries ``scope == none``."""

    backend_id: str
    confirms_isolation: bool
    scope: str = SCOPE_NONE
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.backend_id:
            raise CageError("CageAttestation requires a backend_id")
        if self.scope not in CAGE_SCOPES:
            raise CageError(f"scope {self.scope!r} not in {sorted(CAGE_SCOPES)}")
        if self.confirms_isolation and self.scope != SCOPE_LIVE:
            raise CageError(
                "a cage cannot confirm isolation outside 'live' scope "
                "(no half-confirmed cages)"
            )


@dataclass(frozen=True)
class LiveAdmissionRequest:
    """A request to admit a live actor into a cage. Inert: it carries identity only,
    no command, no payload, no executable — there is nothing to run in this slice."""

    actor_kind: str
    handoff_id: str


@dataclass(frozen=True)
class LiveAdmission:
    """The typed admission decision. ``admitted`` is True only for an attested-live
    cage; otherwise ``refusal_code`` carries a closed reason. There is no path in this
    slice that yields ``admitted=True`` — no shipped backend attests live isolation."""

    admitted: bool
    backend_id: str
    actor_kind: str
    refusal_code: Optional[str] = None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.admitted and self.refusal_code is not None:
            raise CageError("an admitted decision cannot carry a refusal_code")
        if not self.admitted and self.refusal_code not in LIVE_ADMISSION_REFUSAL_CODES:
            raise CageError(
                f"a refusal needs a code in {sorted(LIVE_ADMISSION_REFUSAL_CODES)}; "
                f"got {self.refusal_code!r}"
            )


def evaluate_live_admission(
    attestation: CageAttestation, request: LiveAdmissionRequest
) -> LiveAdmission:
    """Pure guard. A live actor is admitted ONLY when the cage attests genuine isolation
    in live scope. Refusal is typed. (No shipped backend confirms live isolation, so this
    never returns ``admitted=True`` in this slice — refuse-live is structural.)"""
    if request.actor_kind not in ACTOR_KINDS:
        return LiveAdmission(
            admitted=False,
            backend_id=attestation.backend_id,
            actor_kind=request.actor_kind,
            refusal_code=REFUSED_UNKNOWN_ACTOR_KIND,
            reason=f"actor_kind {request.actor_kind!r} not in {sorted(ACTOR_KINDS)}",
        )
    if not attestation.confirms_isolation:
        return LiveAdmission(
            admitted=False,
            backend_id=attestation.backend_id,
            actor_kind=request.actor_kind,
            refusal_code=REFUSED_NO_ISOLATION_ATTESTED,
            reason=(
                f"backend {attestation.backend_id!r} attests no isolation; a live "
                "actor needs a cage that confirms containment"
            ),
        )
    if attestation.scope != SCOPE_LIVE:  # pragma: no cover - unreachable via invariant
        return LiveAdmission(
            admitted=False,
            backend_id=attestation.backend_id,
            actor_kind=request.actor_kind,
            refusal_code=REFUSED_NOT_LIVE_SCOPE,
            reason=f"attestation scope {attestation.scope!r} is not live",
        )
    return LiveAdmission(  # pragma: no cover - no shipped backend reaches here
        admitted=True,
        backend_id=attestation.backend_id,
        actor_kind=request.actor_kind,
        reason="attested live isolation",
    )


def require_live_admission(
    cage: "HarnessCage", request: LiveAdmissionRequest
) -> LiveAdmission:
    """Fail-closed wrapper: returns the admission if admitted, else RAISES the typed
    ``LiveAdmissionRefused``. For callers that want a hard gate, not a value to inspect."""
    decision = cage.admit_live(request)
    if not decision.admitted:
        raise LiveAdmissionRefused(decision.refusal_code or "", decision.reason)
    return decision  # pragma: no cover - unreachable in this slice


# --------------------------------------------------------------------------- #
# The cage contract + the only shipped backend.
# --------------------------------------------------------------------------- #


@runtime_checkable
class HarnessCage(Protocol):
    """The contract a cage backend must satisfy. NOTE the deliberate absence of any
    execution method (no ``run``/``spawn``/``stream``): admission is a *decision*, not an
    invocation, and running a live actor is H2.

    A future real backend (bubblewrap is the named first candidate to evaluate later,
    NOT authorized here) implements ``attest()`` *truthfully* — and only such a backend
    could ever produce an admitted ``LiveAdmission``."""

    backend_id: str

    def attest(self) -> CageAttestation: ...

    def admit_live(self, request: LiveAdmissionRequest) -> LiveAdmission: ...


@dataclass(frozen=True)
class RefusingCage:
    """The honest no-containment backend. It attests **nothing** and therefore refuses
    **every** live admission — by attestation, not by special-case. This is the only
    cage this slice ships; until a real backend earns a live attestation, the harness
    cannot admit a live actor at all.

    Alias: ``NoLiveCage`` — same object, the name that says what it does."""

    backend_id: str = "refusing-cage.v0"

    def attest(self) -> CageAttestation:
        return CageAttestation(
            backend_id=self.backend_id,
            confirms_isolation=False,
            scope=SCOPE_NONE,
            notes="no containment; confirms nothing; admits no live actor",
        )

    def admit_live(self, request: LiveAdmissionRequest) -> LiveAdmission:
        return evaluate_live_admission(self.attest(), request)


# The operator named both; they are the same honest thing.
NoLiveCage = RefusingCage


# --------------------------------------------------------------------------- #
# Audit-store layout (pure path computation; writes nothing, never into AG).
# --------------------------------------------------------------------------- #


def audit_store_root() -> Path:
    """The harness audit-store root, OUTSIDE the repo and OUTSIDE AG's ingest path:

        $XDG_STATE_HOME/agent-gov/harness-runs/      (when XDG_STATE_HOME is set)
        ~/.local/state/agent-gov/harness-runs/       (fallback)

    Pure: computes a path, creates nothing."""
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else (Path.home() / ".local" / "state")
    return base / "agent-gov" / "harness-runs"


def _safe_run_segment(run_id: str) -> str:
    """A run id must be exactly one safe path segment — no separators, no traversal,
    no absolute path — so a run dir can never escape the audit store into AG."""
    if not isinstance(run_id, str) or run_id == "":
        raise AuditPathError("run_id must be a non-empty string")
    if "/" in run_id or "\\" in run_id:
        raise AuditPathError(f"run_id {run_id!r} must be a single path segment")
    if run_id in (".", ".."):
        raise AuditPathError(f"run_id {run_id!r} is not a valid segment")
    if run_id.startswith("."):
        raise AuditPathError(f"run_id {run_id!r} may not start with a dot")
    return run_id


def run_dir(run_id: str) -> Path:
    """The per-run audit directory for ``run_id`` (content-addressed or timestamped id
    chosen by the caller). Pure: computes a path under ``audit_store_root()``, creates
    nothing. Raises ``AuditPathError`` for an unsafe id."""
    return audit_store_root() / _safe_run_segment(run_id)


# --------------------------------------------------------------------------- #
# One-artifact AG-ingest boundary.
# --------------------------------------------------------------------------- #


def assert_ag_ingestible(artifact_type: str) -> None:
    """Refuse (typed) any artifact type other than ``actor_output.v0`` for AG ingest.
    The harness commits to handing AG exactly one artifact type; AG's own fail-closed
    parse is the backstop, but the harness states the boundary at its own edge too."""
    if artifact_type not in AG_INGESTIBLE_ARTIFACT_TYPES:
        raise NonIngestibleArtifact(artifact_type)


__all__ = [
    "SCOPE_NONE",
    "SCOPE_LIVE",
    "CAGE_SCOPES",
    "REFUSED_NO_ISOLATION_ATTESTED",
    "REFUSED_NOT_LIVE_SCOPE",
    "REFUSED_UNKNOWN_ACTOR_KIND",
    "LIVE_ADMISSION_REFUSAL_CODES",
    "AG_INGESTIBLE_ARTIFACT_TYPE",
    "AG_INGESTIBLE_ARTIFACT_TYPES",
    "CageError",
    "LiveAdmissionRefused",
    "AuditPathError",
    "NonIngestibleArtifact",
    "CageAttestation",
    "LiveAdmissionRequest",
    "LiveAdmission",
    "evaluate_live_admission",
    "require_live_admission",
    "HarnessCage",
    "RefusingCage",
    "NoLiveCage",
    "audit_store_root",
    "run_dir",
    "assert_ag_ingestible",
]
