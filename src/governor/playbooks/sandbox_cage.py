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

from .rationed_runner import ORIGIN_STUB, ORIGIN_SYNTHETIC

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


# Verdict scope (closed). A verdict's scope says what it is allowed to admit —
# NOT how "safe" it feels. ``safe`` alone is deliberately insufficient for live
# admission; the scope + ``live_admission_permitted`` carry that, structurally.
SCOPE_LIVE = "live"  # a real cage attesting real isolation; may permit a live origin
SCOPE_SYNTHETIC_ONLY = "synthetic_only"  # a fixture verdict; NEVER permits live
CAGE_VERDICT_SCOPES = frozenset({SCOPE_LIVE, SCOPE_SYNTHETIC_ONLY})

# Admission scope reported back for a stub origin (no cage was consulted at all).
SCOPE_NONE = "none"


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
    """Whether a cage verdict admits within its scope. ``safe`` is NOT sufficient
    for live admission — that is gated by ``live_admission_permitted``, which a
    synthetic-scoped verdict can never carry.

    The invariants (enforced in ``__post_init__``, not by comment) make a lying
    verdict unconstructable:

    - ``scope == synthetic_only`` ⇒ ``attests_live_isolation`` False AND
      ``live_admission_permitted`` False. A synthetic verdict CANNOT permit live.
    - ``live_admission_permitted`` ⇒ ``attests_live_isolation`` (you cannot permit
      live without having attested real isolation).
    - ``attests_live_isolation`` ⇒ ``scope == live`` (real isolation is only
      attestable in live scope).

    So ``safe == True`` on a synthetic verdict is structurally insufficient to
    admit a live origin — by construction, not by convention.
    """

    safe: bool
    backend_id: str
    confirmed: frozenset[str]
    missing: frozenset[str]
    required: frozenset[str]
    reason: str
    scope: str = SCOPE_LIVE
    attests_live_isolation: bool = False
    live_admission_permitted: bool = False

    def __post_init__(self) -> None:
        if self.scope not in CAGE_VERDICT_SCOPES:
            raise ValueError(
                f"scope {self.scope!r} not in {sorted(CAGE_VERDICT_SCOPES)}"
            )
        if self.scope == SCOPE_SYNTHETIC_ONLY:
            if self.attests_live_isolation:
                raise ValueError(
                    "a synthetic_only verdict cannot attest live isolation"
                )
            if self.live_admission_permitted:
                raise ValueError(
                    "a synthetic_only verdict cannot permit live admission "
                    "(synthetic safe != live safe)"
                )
        if self.live_admission_permitted and not self.attests_live_isolation:
            raise ValueError(
                "live_admission_permitted requires attested live isolation"
            )
        if self.attests_live_isolation and self.scope != SCOPE_LIVE:
            raise ValueError("live isolation can only be attested in live scope")


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
    # The live path: real isolation is attested iff safe, and live admission is
    # permitted iff that real isolation is attested. A NullCage (confirms nothing)
    # is unsafe ⇒ attests nothing ⇒ permits no live admission.
    return CageSafetyVerdict(
        safe=safe,
        backend_id=attestation.backend_id,
        confirmed=attestation.confirmed,
        missing=missing,
        required=required,
        reason=reason,
        scope=SCOPE_LIVE,
        attests_live_isolation=safe,
        live_admission_permitted=safe,
    )


def synthetic_cage_verdict(backend_id: str = "synthetic_cage") -> CageSafetyVerdict:
    """The synthetic-only verdict factory. ``safe`` within synthetic scope, but it
    confirms NO real isolation (``missing`` = every required property) and — by the
    verdict invariants — cannot attest live isolation or permit live admission. It
    exists so a synthetic origin can exercise the positive admission path; it can
    never be adapted into live authority."""
    return CageSafetyVerdict(
        safe=True,
        backend_id=backend_id,
        confirmed=frozenset(),
        missing=frozenset(REQUIRED_ISOLATION),
        required=frozenset(REQUIRED_ISOLATION),
        reason="synthetic-only verdict: positive-path fixture, NOT real containment",
        scope=SCOPE_SYNTHETIC_ONLY,
        attests_live_isolation=False,
        live_admission_permitted=False,
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


class SyntheticCage:
    """A synthetic FIXTURE cage for the overnight conveyor. It confirms NO real
    isolation — its attestation is empty, exactly like ``NullCage`` — so it can
    never be confused with real containment, and ``evaluate_cage_safety`` on it is
    never live-safe. The synthetic-ness lives entirely in its ``verdict()``: a
    ``synthetic_only`` verdict that is ``safe`` within synthetic scope but cannot
    attest live isolation or permit a live origin. It lets synthetic origins
    exercise the positive cage-admission path without any real backend."""

    backend_id = "synthetic_cage"

    def __init__(self, sandbox_id: str = "sbx-synthetic-1") -> None:
        self._sandbox_id = sandbox_id

    def attest(self) -> CageAttestation:
        # Confirms NOTHING real — identical isolation posture to NullCage. We do
        # not fake a live attestation; the synthetic verdict is a separate object.
        return CageAttestation(
            backend_id=self.backend_id,
            backend_version="synthetic",
            confirmed=frozenset(),
            sandbox_id=self._sandbox_id,
        )

    def verdict(self) -> CageSafetyVerdict:
        return synthetic_cage_verdict(self.backend_id)

    def validate_writes(
        self, produced_writes: frozenset[str], allowed_writes: frozenset[str]
    ) -> WriteValidation:
        return validate_writes(produced_writes, allowed_writes)


# --------------------------------------------------------------------------- #
# The admission seam (B-12 will enforce this before a non-stub origin runs).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class CageAdmission:
    """Whether an origin of a given kind may run under a cage with this verdict,
    and what the admission *is*. ``scope`` records the lane the decision was made
    in (``none`` for stub, ``synthetic_only`` / ``live``); ``confers_live_effect``
    is True ONLY for an admitted live origin under a live-permitting verdict — a
    synthetic admission is structurally inert."""

    admitted: bool
    origin_kind: str
    requires_cage: bool
    reason: str
    scope: str = SCOPE_NONE
    confers_live_effect: bool = False


def admit_origin_under_cage(
    origin_kind: str, cage_verdict: CageSafetyVerdict
) -> CageAdmission:
    """Pure guard. The admission depends on origin kind + verdict scope + live
    permission — **never on ``safe`` alone**:

    - **stub** — no real process; admitted without a cage and with no safety claim.
    - **synthetic** — admitted ONLY under a ``synthetic_only`` safe verdict; the
      admission is inert (no live effect). It cannot borrow a live verdict.
    - **live (any other)** — admitted ONLY when ``live_admission_permitted`` is
      True. A synthetic verdict can never carry that (verdict invariant), and a
      NullCage is unsafe, so neither admits a live origin even though a synthetic
      verdict's ``safe`` is True. ``safe`` is insufficient for live by construction.
    """
    if origin_kind == ORIGIN_STUB:
        return CageAdmission(
            admitted=True,
            origin_kind=origin_kind,
            requires_cage=False,
            reason="stub origin executes no real process; no cage required, no safety claimed",
            scope=SCOPE_NONE,
            confers_live_effect=False,
        )

    if origin_kind == ORIGIN_SYNTHETIC:
        if cage_verdict.safe and cage_verdict.scope == SCOPE_SYNTHETIC_ONLY:
            return CageAdmission(
                admitted=True,
                origin_kind=origin_kind,
                requires_cage=True,
                reason=(
                    f"synthetic origin admitted under synthetic-only verdict "
                    f"{cage_verdict.backend_id!r}; inert, no live effect"
                ),
                scope=SCOPE_SYNTHETIC_ONLY,
                confers_live_effect=False,
            )
        return CageAdmission(
            admitted=False,
            origin_kind=origin_kind,
            requires_cage=True,
            reason=(
                f"synthetic origin requires a synthetic-only safe verdict; got "
                f"scope={cage_verdict.scope!r} safe={cage_verdict.safe}"
            ),
            scope=cage_verdict.scope,
            confers_live_effect=False,
        )

    # Live / any other origin: gated on live_admission_permitted, NOT on safe.
    if cage_verdict.live_admission_permitted:
        return CageAdmission(
            admitted=True,
            origin_kind=origin_kind,
            requires_cage=True,
            reason=f"live origin admitted under live-permitting cage {cage_verdict.backend_id!r}",
            scope=SCOPE_LIVE,
            confers_live_effect=True,
        )
    if cage_verdict.scope == SCOPE_SYNTHETIC_ONLY:
        return CageAdmission(
            admitted=False,
            origin_kind=origin_kind,
            requires_cage=True,
            reason=(
                f"live origin refused: synthetic-only verdict {cage_verdict.backend_id!r} "
                "does not permit live admission (synthetic safe != live safe)"
            ),
            scope=cage_verdict.scope,
            confers_live_effect=False,
        )
    return CageAdmission(
        admitted=False,
        origin_kind=origin_kind,
        requires_cage=True,
        reason=(
            f"live origin refused: cage {cage_verdict.backend_id!r} did not confirm "
            f"isolation ({cage_verdict.reason})"
        ),
        scope=cage_verdict.scope,
        confers_live_effect=False,
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
    "SCOPE_LIVE",
    "SCOPE_SYNTHETIC_ONLY",
    "SCOPE_NONE",
    "CAGE_VERDICT_SCOPES",
    "CageAttestation",
    "CageSafetyVerdict",
    "evaluate_cage_safety",
    "synthetic_cage_verdict",
    "WriteValidation",
    "validate_writes",
    "SandboxCage",
    "NullCage",
    "SyntheticCage",
    "CageAdmission",
    "admit_origin_under_cage",
]
