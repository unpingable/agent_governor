# SPDX-License-Identifier: Apache-2.0
"""Certified-kind **measurement** (Slice 1).

> The claim proposes; the proof disposes; the gate between them is the architecture.

`claimed_kind` is the author's assertion (the `kind:` field a human wrote). It
authorizes nothing. The **checker** here reads a parsed `PlaybookSpec`, runs the
structural invariants for that kind, and — only if they hold — emits a
`certified_kind` as a **measurement**. The certified kind is *earned from the
checker*, never copied off the artifact's self-claim.

This is a measurement, not authority (the same scalpel the receipt-jurisdiction
map turned on standing-verify): the checker *originates* the kind-fact the way a
thermometer originates a temperature — originating a measured fact is not minting
authority. Nothing here admits, reserves, or permits anything. A later slice
(Slice 3) lets Wicket consume this measurement as *evidence*; Wicket owns any
consequence. This module emits no receipt and touches no organ.

v0 knows exactly one kind: ``procedure``. An unknown claimed_kind refuses
(``UnsupportedKindError``); a claimed kind whose structure violates its invariants
refuses (``KindCheckError``). Either way no `certified_kind` is emitted — uncertified
means not-certified, full stop. (A second kind with divergent dispatch is a later
slice; the claimed≠certified machinery is already structural here.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from governor.gate_receipt import canonical_json, content_hash

from .canonical import CANONICAL_VERSION
from .digest import playbook_spec_digest
from .spec import PARSER_VERSION, PlaybookError, PlaybookSpec

# Bump when the checker's logic or check vocabulary changes (feeds the digest).
CHECKER_VERSION = "playbook-checker.v0"
# Bump when the measurement basis composition changes.
CERT_MEASUREMENT_BASIS_VERSION = "playbook-cert-measurement.v0"

KIND_PROCEDURE = "procedure"
KNOWN_KINDS = frozenset({KIND_PROCEDURE})


class CertificationError(PlaybookError):
    """Base for certification refusals. No certified_kind is emitted on refusal."""


class UnsupportedKindError(CertificationError):
    """The claimed_kind is not one the checker knows how to certify."""


class KindCheckError(CertificationError):
    """The claimed kind's structural invariants do not hold for this spec."""


@dataclass(frozen=True)
class CertifiedKindMeasurement:
    """A measurement that a checker classified a spec as ``certified_kind``.

    NOT authority. ``certified_kind`` is the checker's output; ``claimed_kind`` is
    the author's assertion (recorded distinctly). The Slice 0 ``playbook_spec_digest``
    is bound, so the measurement is about exactly those authored bytes. ``checks``
    is the (ordered) vocabulary of invariants the checker confirmed.
    """

    certified_kind: str
    claimed_kind: str
    playbook_spec_digest: str
    checker_version: str
    parser_version: str
    canonical_version: str
    checks: tuple[str, ...]


def _check_procedure(spec: PlaybookSpec) -> tuple[str, ...]:
    """Procedure invariants: a non-empty linear list of steps with unique ids.

    (Shape — keys/types/non-empty — is the parser's job; the *kind* invariant the
    checker earns here is id-uniqueness: a procedure references steps by id, so
    duplicates would be ambiguous.)
    """
    ids = [s.id for s in spec.steps]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise KindCheckError(f"procedure has duplicate step id(s): {dupes}")
    return ("steps_nonempty", "step_ids_unique")


_KIND_CHECKERS: dict[str, Callable[[PlaybookSpec], tuple[str, ...]]] = {
    KIND_PROCEDURE: _check_procedure,
}


def certify(spec: PlaybookSpec) -> CertifiedKindMeasurement:
    """Measure the certified kind of ``spec``, or refuse with a typed error.

    Dispatches on the checker's verdict, never on the artifact's self-claim: an
    unknown ``claimed_kind`` → ``UnsupportedKindError``; failed kind invariants →
    ``KindCheckError``. On success the ``certified_kind`` is set from the checker's
    confirmation and the Slice 0 spec digest is bound.
    """
    claimed = spec.kind
    if claimed not in KNOWN_KINDS:
        raise UnsupportedKindError(
            f"unknown claimed_kind {claimed!r}; this checker certifies "
            f"{sorted(KNOWN_KINDS)}"
        )
    checks = _KIND_CHECKERS[claimed](spec)  # raises KindCheckError on violation
    return CertifiedKindMeasurement(
        certified_kind=claimed,  # earned: the checker confirmed the invariants
        claimed_kind=claimed,
        playbook_spec_digest=playbook_spec_digest(spec),
        checker_version=CHECKER_VERSION,
        parser_version=PARSER_VERSION,
        canonical_version=CANONICAL_VERSION,
        checks=checks,
    )


def measurement_basis(m: CertifiedKindMeasurement) -> dict[str, Any]:
    """The exact object the measurement digest is taken over (versions + result).

    Exposed so the binding is testable and a reviewer can see what the digest
    commits to.
    """
    return {
        "cert_measurement_basis": CERT_MEASUREMENT_BASIS_VERSION,
        "checker_version": m.checker_version,
        "parser_version": m.parser_version,
        "canonical_version": m.canonical_version,
        "certified_kind": m.certified_kind,
        "claimed_kind": m.claimed_kind,
        "playbook_spec_digest": m.playbook_spec_digest,
        "checks": list(m.checks),
    }


def certified_kind_measurement_digest(m: CertifiedKindMeasurement) -> str:
    """SHA-256 hex over the version-bound measurement basis. Deterministic; this
    is the digest a later slice's Wicket consumes as evidence."""
    return content_hash(canonical_json(measurement_basis(m)))
