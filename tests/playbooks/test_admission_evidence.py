# SPDX-License-Identifier: Apache-2.0
"""Slice 3 — playbook admission-**evidence** binding (the pure verifier).

> Certification is admissible evidence for Wicket, not authority.

These tests pin the pure ``verify_admission_evidence`` over REAL measurement
objects (real specs, real digests). Every incoherence maps to a closed reason;
the NLAI laundering vectors (claimed digest != re-derived; cert/closure for a
different spec stapled onto a declared one) each refuse.
"""

from __future__ import annotations

from governor.playbooks import (
    REASON_CERT_DIGEST_TAMPERED,
    REASON_CERT_NOT_BOUND_TO_SPEC,
    REASON_CLOSURE_DIGEST_TAMPERED,
    REASON_CLOSURE_NOT_ROOTED_AT_SPEC,
    REASON_CLOSURE_ROOT_NOT_MEMBER,
    REASON_INCOMPLETE,
    REASON_SPEC_DIGEST_MALFORMED,
    DependencyClosure,
    PlaybookAdmissionEvidence,
    certified_kind_measurement_digest,
    certify,
    dependency_closure_digest,
    parse_playbook,
    playbook_spec_digest,
    resolve_closure,
    verify_admission_evidence,
)


def _pb(name: str, target: str = "sandbox://x.txt") -> str:
    return (
        "schema: governed-playbook.v0\n"
        "kind: procedure\n"
        f"name: {name}\n"
        "steps:\n"
        "  - id: s1\n"
        "    action: write_file\n"
        f"    target: {target}\n"
    )


def _coherent(name: str = "alpha") -> PlaybookAdmissionEvidence:
    """A fully coherent evidence packet for an import-less playbook."""
    spec = parse_playbook(_pb(name))
    cert = certify(spec)
    closure = resolve_closure(spec, lambda ref: None)
    return PlaybookAdmissionEvidence(
        spec_digest=playbook_spec_digest(spec),
        certified_kind=cert,
        claimed_certified_kind_digest=certified_kind_measurement_digest(cert),
        closure=closure,
        claimed_closure_digest=dependency_closure_digest(closure),
    )


# --------------------------------------------------------------------------- #
# Positive: coherent evidence binds, re-derived digests surfaced.
# --------------------------------------------------------------------------- #


def test_coherent_evidence_binds() -> None:
    ev = _coherent()
    r = verify_admission_evidence(ev)
    assert r.ok is True
    assert r.reason is None
    # The surfaced digests are the trusted re-derived ones (equal to claimed).
    assert r.spec_digest == ev.spec_digest
    assert r.certified_kind_digest == ev.claimed_certified_kind_digest
    assert r.closure_digest == ev.claimed_closure_digest
    assert r.certified_kind == "procedure"


def test_import_less_closure_is_rooted_and_member() -> None:
    """An import-less playbook's closure is exactly {root}, so it is rooted and
    the root is a member — coherent by construction."""
    ev = _coherent()
    assert ev.closure.root_digest == ev.spec_digest
    assert ev.spec_digest in ev.closure.member_digests
    assert verify_admission_evidence(ev).ok is True


# --------------------------------------------------------------------------- #
# Completeness: any absent required field refuses (presenting the packet
# declares the admission playbook-governed; incomplete is refused, not a
# fall-through to a plain admission).
# --------------------------------------------------------------------------- #


def test_absent_spec_digest_incomplete() -> None:
    ev = _coherent()
    r = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest="",
            certified_kind=ev.certified_kind,
            claimed_certified_kind_digest=ev.claimed_certified_kind_digest,
            closure=ev.closure,
            claimed_closure_digest=ev.claimed_closure_digest,
        )
    )
    assert r.ok is False
    assert r.reason == REASON_INCOMPLETE


def test_absent_certified_kind_incomplete() -> None:
    ev = _coherent()
    r = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=ev.spec_digest,
            certified_kind=None,
            claimed_certified_kind_digest=ev.claimed_certified_kind_digest,
            closure=ev.closure,
            claimed_closure_digest=ev.claimed_closure_digest,
        )
    )
    assert r.ok is False
    assert r.reason == REASON_INCOMPLETE


def test_absent_closure_incomplete() -> None:
    ev = _coherent()
    r = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=ev.spec_digest,
            certified_kind=ev.certified_kind,
            claimed_certified_kind_digest=ev.claimed_certified_kind_digest,
            closure=None,
            claimed_closure_digest=ev.claimed_closure_digest,
        )
    )
    assert r.ok is False
    assert r.reason == REASON_INCOMPLETE


def test_absent_claimed_digests_incomplete() -> None:
    ev = _coherent()
    r_cert = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=ev.spec_digest,
            certified_kind=ev.certified_kind,
            claimed_certified_kind_digest=None,
            closure=ev.closure,
            claimed_closure_digest=ev.claimed_closure_digest,
        )
    )
    assert r_cert.reason == REASON_INCOMPLETE
    r_closure = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=ev.spec_digest,
            certified_kind=ev.certified_kind,
            claimed_certified_kind_digest=ev.claimed_certified_kind_digest,
            closure=ev.closure,
            claimed_closure_digest=None,
        )
    )
    assert r_closure.reason == REASON_INCOMPLETE


# --------------------------------------------------------------------------- #
# Malformed spec digest (a laundering vector: junk where a digest belongs).
# --------------------------------------------------------------------------- #


def test_malformed_spec_digest_refuses() -> None:
    ev = _coherent()
    for bad in ("not-a-digest", "A" * 64, "abc", ev.spec_digest + "x"):
        r = verify_admission_evidence(
            PlaybookAdmissionEvidence(
                spec_digest=bad,
                certified_kind=ev.certified_kind,
                claimed_certified_kind_digest=ev.claimed_certified_kind_digest,
                closure=ev.closure,
                claimed_closure_digest=ev.claimed_closure_digest,
            )
        )
        assert r.ok is False
        assert r.reason == REASON_SPEC_DIGEST_MALFORMED, bad


# --------------------------------------------------------------------------- #
# Tamper (NLAI): claimed digest != re-derived. The canonical laundering move —
# staple a legitimate-looking digest onto a different/edited object.
# --------------------------------------------------------------------------- #


def test_cert_digest_tampered_refuses() -> None:
    ev = _coherent()
    # A real digest, but for a DIFFERENT measurement.
    other = _coherent("beta")
    r = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=ev.spec_digest,
            certified_kind=ev.certified_kind,
            claimed_certified_kind_digest=other.claimed_certified_kind_digest,
            closure=ev.closure,
            claimed_closure_digest=ev.claimed_closure_digest,
        )
    )
    assert r.ok is False
    assert r.reason == REASON_CERT_DIGEST_TAMPERED


def test_closure_digest_tampered_refuses() -> None:
    ev = _coherent()
    other = _coherent("beta")
    r = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=ev.spec_digest,
            certified_kind=ev.certified_kind,
            claimed_certified_kind_digest=ev.claimed_certified_kind_digest,
            closure=ev.closure,
            claimed_closure_digest=other.claimed_closure_digest,
        )
    )
    assert r.ok is False
    assert r.reason == REASON_CLOSURE_DIGEST_TAMPERED


# --------------------------------------------------------------------------- #
# Cross-binding: cert/closure must be ABOUT the declared spec. Stapling
# evidence for spec A onto a declared spec B refuses.
# --------------------------------------------------------------------------- #


def test_cert_not_bound_to_declared_spec_refuses() -> None:
    """spec_digest names spec B; the cert measurement is about spec A. The
    cert digest re-derives fine, but it binds the wrong spec."""
    a = _coherent("alpha")
    b = _coherent("beta")
    r = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=b.spec_digest,  # declared: B
            certified_kind=a.certified_kind,  # but cert is about A
            claimed_certified_kind_digest=a.claimed_certified_kind_digest,
            closure=b.closure,
            claimed_closure_digest=b.claimed_closure_digest,
        )
    )
    assert r.ok is False
    assert r.reason == REASON_CERT_NOT_BOUND_TO_SPEC


def test_closure_not_rooted_at_declared_spec_refuses() -> None:
    """cert agrees with declared spec A, but the closure is rooted at B."""
    a = _coherent("alpha")
    b = _coherent("beta")
    r = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=a.spec_digest,  # declared: A
            certified_kind=a.certified_kind,  # cert about A — agrees
            claimed_certified_kind_digest=a.claimed_certified_kind_digest,
            closure=b.closure,  # but closure rooted at B
            claimed_closure_digest=b.claimed_closure_digest,
        )
    )
    assert r.ok is False
    assert r.reason == REASON_CLOSURE_NOT_ROOTED_AT_SPEC


def test_closure_root_not_member_refuses() -> None:
    """A synthetic closure whose declared root is not among its members is
    internally incoherent and refuses (binds the evaluated closure, not just
    the named root)."""
    a = _coherent("alpha")
    b = _coherent("beta")
    # Rooted at A (matches declared + cert), but members do not contain A.
    bad_closure = DependencyClosure(
        root_digest=a.spec_digest,
        member_digests=(b.spec_digest,),
    )
    r = verify_admission_evidence(
        PlaybookAdmissionEvidence(
            spec_digest=a.spec_digest,
            certified_kind=a.certified_kind,
            claimed_certified_kind_digest=a.claimed_certified_kind_digest,
            closure=bad_closure,
            claimed_closure_digest=dependency_closure_digest(bad_closure),
        )
    )
    assert r.ok is False
    assert r.reason == REASON_CLOSURE_ROOT_NOT_MEMBER
