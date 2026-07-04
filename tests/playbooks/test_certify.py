# SPDX-License-Identifier: Apache-2.0
"""Slice 1 — certified_kind as MEASUREMENT, not authority.

Pins: the checker (not the artifact) emits certified_kind; the measurement binds
the Slice 0 spec digest + parser/canonical/checker versions; it is deterministic;
unsupported or invalid kinds refuse with typed errors; and the result confers no
authority (it is evidence — Wicket consequence is a later slice).
"""

from __future__ import annotations

import pytest

from governor.playbooks import (
    CANONICAL_VERSION,
    CERT_MEASUREMENT_BASIS_VERSION,
    CHECKER_VERSION,
    PARSER_VERSION,
    CertifiedKindMeasurement,
    KindCheckError,
    UnsupportedKindError,
    certified_kind_measurement_digest,
    certify,
    measurement_basis,
    parse_playbook,
    playbook_spec_digest,
)

TOY = """\
schema: governed-playbook.v0
kind: procedure
name: toy-copy
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
"""

TWO_STEP = """\
schema: governed-playbook.v0
kind: procedure
name: toy-copy
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
  - id: step2
    action: write_file
    target: sandbox://beta.txt
"""


def _certify(src: str = TOY) -> CertifiedKindMeasurement:
    return certify(parse_playbook(src))


# --------------------------------------------------------------------------- #
# The checker emits certified_kind; it is earned, not copied
# --------------------------------------------------------------------------- #


def test_certify_emits_certified_kind() -> None:
    m = _certify()
    assert isinstance(m, CertifiedKindMeasurement)
    assert m.certified_kind == "procedure"
    assert m.claimed_kind == "procedure"
    assert m.checks == ("steps_nonempty", "step_ids_unique")


def test_certification_binds_the_slice0_spec_digest() -> None:
    spec = parse_playbook(TOY)
    m = certify(spec)
    assert m.playbook_spec_digest == playbook_spec_digest(spec)


def test_certification_binds_versions() -> None:
    basis = measurement_basis(_certify())
    assert basis["checker_version"] == CHECKER_VERSION
    assert basis["parser_version"] == PARSER_VERSION
    assert basis["canonical_version"] == CANONICAL_VERSION
    assert basis["cert_measurement_basis"] == CERT_MEASUREMENT_BASIS_VERSION


# --------------------------------------------------------------------------- #
# claimed_kind cannot authorize anything
# --------------------------------------------------------------------------- #


def test_unsupported_claimed_kind_refuses_typed() -> None:
    # The author writing `kind: pipeline` parses fine but cannot get it certified.
    src = TOY.replace("kind: procedure", "kind: pipeline")
    with pytest.raises(UnsupportedKindError, match="unknown claimed_kind"):
        _certify(src)


def test_claimed_kind_is_not_self_certifying() -> None:
    # A claimed procedure whose structure violates the kind invariant is refused —
    # the self-claim does not earn a certified_kind.
    dup = TWO_STEP.replace("id: step2", "id: step1")  # duplicate id
    with pytest.raises(KindCheckError, match="duplicate step id"):
        _certify(dup)


def test_measurement_is_not_authority() -> None:
    # Measurement semantics: the result is inert evidence. It exposes no method
    # that grants/admits/permits — only descriptive fields + a digest.
    m = _certify()
    public = {a for a in dir(m) if not a.startswith("_")}
    forbidden = {"admit", "authorize", "permit", "grant", "allow", "approve"}
    assert public & forbidden == set()


# --------------------------------------------------------------------------- #
# Determinism + the measurement digest binds the bytes
# --------------------------------------------------------------------------- #


def test_measurement_digest_is_deterministic() -> None:
    assert certified_kind_measurement_digest(_certify()) == (
        certified_kind_measurement_digest(_certify())
    )


def test_measurement_digest_is_hex_sha256() -> None:
    d = certified_kind_measurement_digest(_certify())
    assert isinstance(d, str) and len(d) == 64
    int(d, 16)


def test_semantic_change_changes_measurement_digest() -> None:
    # Because the spec digest is bound, changing the authored bytes moves the
    # measurement digest too.
    changed = TOY.replace("alpha.txt", "gamma.txt")
    assert certified_kind_measurement_digest(_certify(TOY)) != (
        certified_kind_measurement_digest(_certify(changed))
    )


def test_equivalent_formatting_same_measurement_digest() -> None:
    reformatted = """\
kind: procedure
name: toy-copy
schema: governed-playbook.v0
steps:
  - target: sandbox://alpha.txt
    id: step1
    action: write_file
"""
    assert certified_kind_measurement_digest(_certify(TOY)) == (
        certified_kind_measurement_digest(_certify(reformatted))
    )
