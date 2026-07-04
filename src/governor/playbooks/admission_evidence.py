# SPDX-License-Identifier: Apache-2.0
"""Playbook admission **evidence** binding (Slice 3, the Wicket-facing seam).

> **Certification is admissible evidence for Wicket, not authority.**

This module is the boundary where the three inert measurements (Slices 0-2) are
assembled into an *evidence packet* a caller may present for a playbook-governed
admission. It does exactly one thing: decide whether that packet is **internally
coherent** — and refuse, with a closed reason, when it is not.

What it is NOT:

- It does not admit, reserve, permit, or authorize anything. A coherent packet is
  a *necessary precondition* for a playbook-governed admission, never a *sufficient*
  one. The authority decision lives entirely at the Standing seam (``wicket_client``);
  this verifier runs *before* that seam and can only refuse or pass through.
- It mints no receipt and touches no organ. It is a pure, total function over the
  evidence objects.

The NLAI scalpel applied to evidence: the caller hands over the measurement
*objects* (a ``CertifiedKindMeasurement``, a ``DependencyClosure``) **and** the digest
strings it claims for them. This verifier never trusts the claimed strings — it
**re-derives** each digest from the object (``certified_kind_measurement_digest``,
``dependency_closure_digest``) and refuses on any mismatch. A claimed digest is a
pointer; the re-derived digest is the receipt. Stapling a legitimate-looking digest
onto a different measurement is the canonical laundering move, and it refuses here.

Cross-binding (the "binds the evaluated closure, not just the named playbook"
requirement): the certified-kind measurement must be *about* the declared spec
(``cert.playbook_spec_digest == spec_digest``), and the dependency closure must be
*rooted at* it (``closure.root_digest == spec_digest`` and the root is a member).
You cannot present certification for spec A, a closure for spec B, and a declared
spec digest C and have them admitted as one coherent body of evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .certify import CertifiedKindMeasurement, certified_kind_measurement_digest
from .closure import DependencyClosure, dependency_closure_digest

# Bump when the binding-verification basis or reason vocabulary changes.
ADMISSION_EVIDENCE_BASIS_VERSION = "playbook-admission-evidence.v0"

# A spec/closure/cert digest is a lowercase sha256 hex string (the shape
# ``content_hash`` produces). A malformed digest is a laundering vector
# (stapling junk where a digest belongs), so it is refused, not coerced.
_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


# ---------------------------------------------------------------------------
# Closed binding-reason vocabulary. One reason per distinct incoherence; the
# Wicket seam wraps any of these in its single ``playbook_evidence_unbound``
# refusal kind and carries the specific reason in the detail + evidence bundle.
# ---------------------------------------------------------------------------

REASON_INCOMPLETE = "evidence_incomplete"
REASON_SPEC_DIGEST_MALFORMED = "spec_digest_malformed"
REASON_CERT_NOT_BOUND_TO_SPEC = "cert_not_bound_to_spec"
REASON_CERT_DIGEST_TAMPERED = "cert_digest_tampered"
REASON_CLOSURE_NOT_ROOTED_AT_SPEC = "closure_not_rooted_at_spec"
REASON_CLOSURE_ROOT_NOT_MEMBER = "closure_root_not_member"
REASON_CLOSURE_DIGEST_TAMPERED = "closure_digest_tampered"

BINDING_REASONS = frozenset({
    REASON_INCOMPLETE,
    REASON_SPEC_DIGEST_MALFORMED,
    REASON_CERT_NOT_BOUND_TO_SPEC,
    REASON_CERT_DIGEST_TAMPERED,
    REASON_CLOSURE_NOT_ROOTED_AT_SPEC,
    REASON_CLOSURE_ROOT_NOT_MEMBER,
    REASON_CLOSURE_DIGEST_TAMPERED,
})


@dataclass(frozen=True)
class PlaybookAdmissionEvidence:
    """The measurement evidence a caller presents for a playbook-governed admission.

    Carries the measurement **objects** plus the digest strings the caller
    **claims** for them. Presenting this packet is the opt-in to
    playbook-governed admission: once presented, it must be complete and
    internally coherent or admission refuses *before* the authority seam is
    consulted. Coherent evidence is necessary, never sufficient — it
    authorizes nothing.

    Fields:
        spec_digest: the declared ``playbook_spec_digest`` (Slice 0). The
            anchor the other two measurements must bind to.
        certified_kind: the ``CertifiedKindMeasurement`` object (Slice 1), or
            None (→ incomplete).
        claimed_certified_kind_digest: the digest the caller claims for that
            measurement. Re-derived and compared; mismatch → tampered.
        closure: the ``DependencyClosure`` object (Slice 2), or None (→
            incomplete).
        claimed_closure_digest: the digest the caller claims for that closure.
            Re-derived and compared; mismatch → tampered.
    """

    spec_digest: str
    certified_kind: Optional[CertifiedKindMeasurement]
    claimed_certified_kind_digest: Optional[str]
    closure: Optional[DependencyClosure]
    claimed_closure_digest: Optional[str]


@dataclass(frozen=True)
class EvidenceBindingResult:
    """The verdict of ``verify_admission_evidence``.

    ``ok`` True ⇒ the packet is internally coherent and the re-derived digests
    are surfaced (for the Wicket-seam evidence receipt). ``ok`` False ⇒
    ``reason`` is one of ``BINDING_REASONS`` and the digest fields may be None.

    This is an evidence-coherence verdict, NOT an admission verdict. Even when
    ``ok`` is True, nothing is authorized — the authority decision is the
    Standing seam's, downstream of this result.
    """

    ok: bool
    reason: Optional[str]
    detail: str
    spec_digest: Optional[str] = None
    certified_kind_digest: Optional[str] = None
    closure_digest: Optional[str] = None
    certified_kind: Optional[str] = None


def _refuse(reason: str, detail: str) -> EvidenceBindingResult:
    assert reason in BINDING_REASONS, f"unknown binding reason {reason!r}"
    return EvidenceBindingResult(ok=False, reason=reason, detail=detail)


def verify_admission_evidence(
    evidence: PlaybookAdmissionEvidence,
) -> EvidenceBindingResult:
    """Decide whether a playbook admission-evidence packet is internally coherent.

    Pure and total. Never raises on a malformed packet — every incoherence maps
    to a closed ``reason``. Mints nothing, touches no organ, authorizes nothing.

    Checks, in order:

    1. **Completeness** — spec digest, both measurement objects, and both
       claimed digests must be present. (Presenting the packet declares the
       admission playbook-governed; an incomplete packet is a refused
       admission, not a fall-through to a plain one.)
    2. **Spec digest shape** — must be a lowercase sha256 hex string.
    3. **Cert re-derivation + binding** — the claimed cert digest must equal
       the digest re-derived from the cert object, and the cert must be *about*
       the declared spec.
    4. **Closure re-derivation + binding** — the claimed closure digest must
       equal the digest re-derived from the closure object, the closure must be
       *rooted at* the declared spec, and the root must be a member.

    On success the re-derived (trusted) digests and the certified-kind value are
    surfaced for the evidence receipt.
    """
    # 1. Completeness.
    if not evidence.spec_digest:
        return _refuse(REASON_INCOMPLETE, "spec_digest is absent")
    if evidence.certified_kind is None:
        return _refuse(REASON_INCOMPLETE, "certified_kind measurement is absent")
    if not evidence.claimed_certified_kind_digest:
        return _refuse(REASON_INCOMPLETE, "claimed_certified_kind_digest is absent")
    if evidence.closure is None:
        return _refuse(REASON_INCOMPLETE, "closure is absent")
    if not evidence.claimed_closure_digest:
        return _refuse(REASON_INCOMPLETE, "claimed_closure_digest is absent")

    spec_digest = evidence.spec_digest

    # 2. Spec digest shape.
    if not _SHA256_HEX.match(spec_digest):
        return _refuse(
            REASON_SPEC_DIGEST_MALFORMED,
            f"spec_digest {spec_digest!r} is not a lowercase sha256 hex string",
        )

    # 3. Certified-kind: re-derive, never trust the claimed string.
    cert = evidence.certified_kind
    rederived_cert_digest = certified_kind_measurement_digest(cert)
    if evidence.claimed_certified_kind_digest != rederived_cert_digest:
        return _refuse(
            REASON_CERT_DIGEST_TAMPERED,
            "claimed certified_kind digest "
            f"{evidence.claimed_certified_kind_digest!r} != re-derived "
            f"{rederived_cert_digest!r}",
        )
    if cert.playbook_spec_digest != spec_digest:
        return _refuse(
            REASON_CERT_NOT_BOUND_TO_SPEC,
            "certified_kind measurement binds spec digest "
            f"{cert.playbook_spec_digest!r}, not the declared {spec_digest!r}",
        )

    # 4. Closure: re-derive, then check it is rooted at this spec.
    closure = evidence.closure
    rederived_closure_digest = dependency_closure_digest(closure)
    if evidence.claimed_closure_digest != rederived_closure_digest:
        return _refuse(
            REASON_CLOSURE_DIGEST_TAMPERED,
            "claimed closure digest "
            f"{evidence.claimed_closure_digest!r} != re-derived "
            f"{rederived_closure_digest!r}",
        )
    if closure.root_digest != spec_digest:
        return _refuse(
            REASON_CLOSURE_NOT_ROOTED_AT_SPEC,
            f"closure is rooted at {closure.root_digest!r}, not the declared "
            f"spec {spec_digest!r}",
        )
    if spec_digest not in closure.member_digests:
        return _refuse(
            REASON_CLOSURE_ROOT_NOT_MEMBER,
            f"declared spec {spec_digest!r} is not among the closure members",
        )

    return EvidenceBindingResult(
        ok=True,
        reason=None,
        detail="playbook admission evidence is internally coherent",
        spec_digest=spec_digest,
        certified_kind_digest=rederived_cert_digest,
        closure_digest=rederived_closure_digest,
        certified_kind=cert.certified_kind,
    )


__all__ = [
    "ADMISSION_EVIDENCE_BASIS_VERSION",
    "BINDING_REASONS",
    "REASON_INCOMPLETE",
    "REASON_SPEC_DIGEST_MALFORMED",
    "REASON_CERT_NOT_BOUND_TO_SPEC",
    "REASON_CERT_DIGEST_TAMPERED",
    "REASON_CLOSURE_NOT_ROOTED_AT_SPEC",
    "REASON_CLOSURE_ROOT_NOT_MEMBER",
    "REASON_CLOSURE_DIGEST_TAMPERED",
    "PlaybookAdmissionEvidence",
    "EvidenceBindingResult",
    "verify_admission_evidence",
]
