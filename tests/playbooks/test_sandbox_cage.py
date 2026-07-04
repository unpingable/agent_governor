# SPDX-License-Identifier: Apache-2.0
"""Sandbox cage contract (Slice B-11 — contract + honest null backend).

Covers the load-bearing rule: a cage is safe ONLY when it confirms every required
isolation property, and the null backend (``subprocess.run()`` in disguise)
confirms nothing — so a non-stub origin can never be admitted under it. The real
OS/container backends are a later slice; here we pin the SHAPE and the guard.

No real subprocess, no real container — a ``FakeCage`` attests a configurable set
of properties, exactly as a real backend would report what it enforces.
"""

from __future__ import annotations

import pytest

from governor.playbooks.rationed_runner import ORIGIN_STUB
from governor.playbooks.sandbox_cage import (
    ISOLATION_PROPERTIES,
    NETWORK_DISABLED,
    REQUIRED_ISOLATION,
    CageAttestation,
    NullCage,
    admit_origin_under_cage,
    evaluate_cage_safety,
    validate_writes,
)

_LIVE = "live"


class FakeCage:
    """A test backend that attests exactly the properties it is told it enforces
    — the stand-in for a Docker/Podman/bubblewrap backend reporting its real
    isolation. Confirming all of ``REQUIRED_ISOLATION`` models a sound cage;
    omitting any models a backend that cannot prove that property."""

    backend_id = "fake_cage"

    def __init__(self, confirmed=REQUIRED_ISOLATION, sandbox_id="sbx-fake-1"):
        self._confirmed = frozenset(confirmed)
        self._sandbox_id = sandbox_id

    def attest(self) -> CageAttestation:
        return CageAttestation(
            backend_id=self.backend_id,
            backend_version="test",
            confirmed=self._confirmed,
            sandbox_id=self._sandbox_id,
        )

    def validate_writes(self, produced_writes, allowed_writes):
        return validate_writes(produced_writes, allowed_writes)


# --------------------------------------------------------------------------- #
# The honest null default: Python is not a cage.
# --------------------------------------------------------------------------- #


class TestNullCageConfirmsNothing:
    def test_null_cage_attests_nothing_and_is_never_safe(self):
        att = NullCage().attest()
        assert att.confirmed == frozenset()
        assert att.sandbox_id is None  # no workspace fabricated

        verdict = evaluate_cage_safety(att)
        assert verdict.safe is False
        # Every required property is missing — nothing was confirmed.
        assert verdict.missing == REQUIRED_ISOLATION

    def test_live_origin_refused_under_null_cage(self):
        verdict = evaluate_cage_safety(NullCage().attest())
        admission = admit_origin_under_cage(_LIVE, verdict)
        assert admission.admitted is False
        assert admission.requires_cage is True
        assert "did not confirm" in admission.reason


# --------------------------------------------------------------------------- #
# A confirming cage is safe; a cage missing one property is not.
# --------------------------------------------------------------------------- #


class TestCageSafetyEvaluation:
    def test_cage_confirming_all_required_is_safe(self):
        verdict = evaluate_cage_safety(FakeCage().attest())
        assert verdict.safe is True
        assert verdict.missing == frozenset()

    def test_cage_missing_one_property_is_not_safe(self):
        """Load-bearing: safety is not claimed unless EVERY required property is
        confirmed. Drop exactly one and the cage is unsafe, naming the gap."""
        partial = REQUIRED_ISOLATION - {NETWORK_DISABLED}
        verdict = evaluate_cage_safety(FakeCage(confirmed=partial).attest())
        assert verdict.safe is False
        assert verdict.missing == frozenset({NETWORK_DISABLED})

    def test_live_origin_admitted_only_under_safe_cage(self):
        safe = evaluate_cage_safety(FakeCage().attest())
        admitted = admit_origin_under_cage(_LIVE, safe)
        assert admitted.admitted is True
        assert admitted.requires_cage is True


# --------------------------------------------------------------------------- #
# Stub origins need no cage — but get no safety claim either.
# --------------------------------------------------------------------------- #


class TestStubOriginNeedsNoCage:
    def test_stub_origin_admitted_even_under_null_cage(self):
        verdict = evaluate_cage_safety(NullCage().attest())
        admission = admit_origin_under_cage(ORIGIN_STUB, verdict)
        assert admission.admitted is True
        assert admission.requires_cage is False
        assert "no cage required" in admission.reason


# --------------------------------------------------------------------------- #
# Post-run write-manifest validation.
# --------------------------------------------------------------------------- #


class TestWriteValidation:
    def test_writes_inside_allowlist_ok(self):
        result = validate_writes(
            frozenset({"out/report.json"}), frozenset({"out/report.json", "out/log"})
        )
        assert result.ok is True
        assert result.forbidden_writes == frozenset()

    def test_write_outside_allowlist_detected(self):
        result = validate_writes(
            frozenset({"out/report.json", "../escape.txt"}),
            frozenset({"out/report.json"}),
        )
        assert result.ok is False
        assert result.forbidden_writes == frozenset({"../escape.txt"})


# --------------------------------------------------------------------------- #
# Closed vocabulary: an unknown isolation property is refused.
# --------------------------------------------------------------------------- #


class TestClosedVocabulary:
    def test_unknown_isolation_property_refused(self):
        with pytest.raises(ValueError):
            CageAttestation(
                backend_id="fake",
                backend_version="x",
                confirmed=frozenset({"teleport_disabled"}),
            )

    def test_required_isolation_is_subset_of_vocabulary(self):
        assert REQUIRED_ISOLATION <= ISOLATION_PROPERTIES
