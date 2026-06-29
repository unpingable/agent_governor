# SPDX-License-Identifier: Apache-2.0
"""Sandbox cage contract (Slice B-11 — contract + honest null backend only).

> Python is not the cage. Python is only the clerk.

The dispatch gate (``ration_card.py``) decides *whether* to dispatch; the runner
(``rationed_runner.py``) governs *how one run executes* under a timeout + kill
switch. Neither contains a subprocess — and ``subprocess.run()`` is **not**
containment. This module is the missing piece: the contract a real OS/container
cage must satisfy, so the runner can refuse to *claim* sandbox safety it cannot
prove.

The load-bearing rule (from the allowlist review, Q1):

    The runner must not claim sandbox safety unless the cage backend CONFIRMS its
    isolation properties.

So safety is an **attestation**, absence-restrictive: a property the backend does
not explicitly confirm is treated as unconfirmed. The only backend shipped here is
``NullCage`` — the honest "no containment" default that confirms *nothing*, so a
live origin can never be admitted under it. Real backends (Docker / Podman /
bubblewrap) are a later slice; this one fixes the SHAPE they must fill, and the
guard (``admit_origin_under_cage``) the live slice (B-12) will enforce. Building
the contract before the backend is deliberate: it is the only thing that keeps a
future ``subprocess.run()`` from quietly passing for a sandbox.

Consumer: ``admit_origin_under_cage`` is the seam B-12 calls before running a
non-stub origin. Stub origins (this campaign's only live-runnable kind so far)
execute no real process and need no cage — but they also get no safety claim.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from .rationed_runner import ORIGIN_STUB

# --------------------------------------------------------------------------- #
# Isolation property vocabulary (closed). Each is a property a real cage backend
# either ENFORCES (and so may confirm) or does not. Absence ⇒ unconfirmed.
# --------------------------------------------------------------------------- #

NETWORK_DISABLED = "network_disabled"
INPUT_READ_ONLY = "input_read_only"
WRITES_CONFINED = "writes_confined"
NON_ROOT = "non_root"
NO_HOST_CREDENTIALS = "no_host_credentials"
NO_HOST_HOME = "no_host_home"
PROCESS_LIMITS = "process_limits"
ENV_ALLOWLIST = "env_allowlist"
POST_RUN_WRITE_VALIDATION = "post_run_write_validation"

ISOLATION_PROPERTIES = frozenset(
    {
        NETWORK_DISABLED,
        INPUT_READ_ONLY,
        WRITES_CONFINED,
        NON_ROOT,
        NO_HOST_CREDENTIALS,
        NO_HOST_HOME,
        PROCESS_LIMITS,
        ENV_ALLOWLIST,
        POST_RUN_WRITE_VALIDATION,
    }
)

# Conservative default: a live run requires the cage to confirm EVERY property.
# A future slice may relax this via explicit policy — but the default never
# trades isolation for convenience.
REQUIRED_ISOLATION = ISOLATION_PROPERTIES


# --------------------------------------------------------------------------- #
# Attestation + verdicts.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CageAttestation:
    """What a cage backend CONFIRMS it enforces. Absence-restrictive: a property
    not in ``confirmed`` is unconfirmed, never assumed. ``sandbox_id`` is only
    meaningful for a backend that actually provisioned an isolated workspace —
    the null backend leaves it None rather than fabricate one."""

    backend_id: str
    backend_version: str
    confirmed: frozenset[str] = field(default_factory=frozenset)
    sandbox_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.backend_id:
            raise ValueError("CageAttestation requires a backend_id")
        unknown = self.confirmed - ISOLATION_PROPERTIES
        if unknown:
            raise ValueError(
                f"unknown isolation properties: {sorted(unknown)} "
                f"(closed vocabulary {sorted(ISOLATION_PROPERTIES)})"
            )


@dataclass(frozen=True)
class CageSafetyVerdict:
    """Whether an attestation satisfies the required isolation set. ``missing``
    names exactly what is unconfirmed — the verdict never says "safe" by rounding
    up."""

    safe: bool
    backend_id: str
    confirmed: frozenset[str]
    missing: frozenset[str]
    required: frozenset[str]
    reason: str


def evaluate_cage_safety(
    attestation: CageAttestation,
    required: frozenset[str] = REQUIRED_ISOLATION,
) -> CageSafetyVerdict:
    """Pure. Safe iff every required property is confirmed. The null backend
    confirms nothing, so it is never safe — which is the whole point."""
    required = frozenset(required)
    missing = required - attestation.confirmed
    safe = not missing
    reason = (
        "all required isolation properties confirmed"
        if safe
        else f"unconfirmed isolation: {sorted(missing)}"
    )
    return CageSafetyVerdict(
        safe=safe,
        backend_id=attestation.backend_id,
        confirmed=attestation.confirmed,
        missing=missing,
        required=required,
        reason=reason,
    )


@dataclass(frozen=True)
class WriteValidation:
    """Post-run write-manifest validation: the writes the run actually produced,
    checked ⊆ the writable allowlist. ``forbidden_writes`` is non-empty iff the
    run reached outside its writable area."""

    ok: bool
    forbidden_writes: frozenset[str]
    allowed: frozenset[str]
    produced: frozenset[str]


def validate_writes(
    produced_writes: frozenset[str], allowed_writes: frozenset[str]
) -> WriteValidation:
    """Pure. Observation, not enforcement — a backend that does not confirm
    ``POST_RUN_WRITE_VALIDATION`` can still compute this, but its verdict is not
    trustworthy. Enforcement is the cage's job; this is the audit."""
    produced = frozenset(produced_writes)
    allowed = frozenset(allowed_writes)
    forbidden = produced - allowed
    return WriteValidation(
        ok=not forbidden,
        forbidden_writes=forbidden,
        allowed=allowed,
        produced=produced,
    )


# --------------------------------------------------------------------------- #
# The cage backend interface + the honest null default.
# --------------------------------------------------------------------------- #


class SandboxCage(Protocol):
    """A cage backend. Production backends provision a disposable workspace with
    a read-only input snapshot, a narrow writable dir, no network, non-root, no
    host credentials/HOME, process/time limits, and an env allowlist — and
    ``attest()`` what they actually enforce. This slice ships only ``NullCage``."""

    backend_id: str

    def attest(self) -> CageAttestation: ...

    def validate_writes(
        self, produced_writes: frozenset[str], allowed_writes: frozenset[str]
    ) -> WriteValidation: ...


class NullCage:
    """The honest no-containment backend. ``subprocess.run()`` IS this: it
    enforces nothing and therefore confirms nothing. ``evaluate_cage_safety`` on
    a NullCage attestation is never safe, so ``admit_origin_under_cage`` refuses
    every non-stub origin under it. This is the default precisely so that the
    absence of a real cage fails closed instead of silently passing."""

    backend_id = "null_cage"

    def attest(self) -> CageAttestation:
        return CageAttestation(
            backend_id=self.backend_id,
            backend_version="0",
            confirmed=frozenset(),  # confirms NOTHING
            sandbox_id=None,  # no workspace was provisioned; do not fabricate one
        )

    def validate_writes(
        self, produced_writes: frozenset[str], allowed_writes: frozenset[str]
    ) -> WriteValidation:
        return validate_writes(produced_writes, allowed_writes)


# --------------------------------------------------------------------------- #
# The admission seam (B-12 will enforce this before a non-stub origin runs).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CageAdmission:
    """Whether an origin of a given kind may run under a cage with this safety
    verdict. The rule: a stub origin executes no real process and needs no cage
    (admitted, but it gets NO safety claim); any other origin requires a
    confirmed-safe cage."""

    admitted: bool
    origin_kind: str
    requires_cage: bool
    reason: str


def admit_origin_under_cage(
    origin_kind: str, cage_verdict: CageSafetyVerdict
) -> CageAdmission:
    """Pure guard. Stub origins are admitted without a cage requirement; any
    non-stub origin is admitted ONLY when the cage verdict is safe — otherwise
    refused with the unconfirmed-isolation reason. The live slice (B-12) calls
    this before running a non-stub origin; it cannot launder a NullCage into a
    sandbox."""
    if origin_kind == ORIGIN_STUB:
        return CageAdmission(
            admitted=True,
            origin_kind=origin_kind,
            requires_cage=False,
            reason="stub origin executes no real process; no cage required, no safety claimed",
        )
    if cage_verdict.safe:
        return CageAdmission(
            admitted=True,
            origin_kind=origin_kind,
            requires_cage=True,
            reason=f"non-stub origin admitted under confirmed-safe cage {cage_verdict.backend_id!r}",
        )
    return CageAdmission(
        admitted=False,
        origin_kind=origin_kind,
        requires_cage=True,
        reason=(
            f"non-stub origin refused: cage {cage_verdict.backend_id!r} did not confirm "
            f"isolation ({cage_verdict.reason})"
        ),
    )


__all__ = [
    "NETWORK_DISABLED",
    "INPUT_READ_ONLY",
    "WRITES_CONFINED",
    "NON_ROOT",
    "NO_HOST_CREDENTIALS",
    "NO_HOST_HOME",
    "PROCESS_LIMITS",
    "ENV_ALLOWLIST",
    "POST_RUN_WRITE_VALIDATION",
    "ISOLATION_PROPERTIES",
    "REQUIRED_ISOLATION",
    "CageAttestation",
    "CageSafetyVerdict",
    "evaluate_cage_safety",
    "WriteValidation",
    "validate_writes",
    "SandboxCage",
    "NullCage",
    "CageAdmission",
    "admit_origin_under_cage",
]
