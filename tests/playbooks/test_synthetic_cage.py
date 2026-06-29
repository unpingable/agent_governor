# SPDX-License-Identifier: Apache-2.0
"""Synthetic cage verdict contract (Slice B-11.S2).

The load-bearing rule: ``safe == True`` is NOT sufficient for live admission. A
synthetic cage produces a ``synthetic_only`` verdict that is safe within synthetic
scope yet structurally incapable of permitting a live origin — and that
impossibility is enforced by the verdict's own invariants, not by comments.

Admission matrix proven here:
    SyntheticOrigin + SyntheticCage   -> admitted (synthetic_only, inert)
    LiveOrigin      + SyntheticCage   -> rejected
    LiveOrigin      + synthetic verdict object (reuse) -> rejected
    LiveOrigin      + NullCage        -> rejected
    SyntheticOrigin + NullCage        -> rejected
    SyntheticOrigin + live (real) verdict -> rejected
"""

from __future__ import annotations

import pytest

from governor.playbooks.rationed_runner import ORIGIN_SYNTHETIC
from governor.playbooks.sandbox_cage import (
    REQUIRED_ISOLATION,
    SCOPE_LIVE,
    SCOPE_SYNTHETIC_ONLY,
    CageSafetyVerdict,
    NullCage,
    SyntheticCage,
    admit_origin_under_cage,
    evaluate_cage_safety,
    synthetic_cage_verdict,
)

_LIVE = "live"


def _real_safe_verdict() -> CageSafetyVerdict:
    """A real cage that confirms every required isolation property."""
    return evaluate_cage_safety(
        # a fully-confirming attestation, via a tiny fake backend
        _AllConfirmingCage().attest()
    )


class _AllConfirmingCage:
    backend_id = "fake_real_cage"

    def attest(self):
        from governor.playbooks.sandbox_cage import CageAttestation

        return CageAttestation(
            backend_id=self.backend_id,
            backend_version="test",
            confirmed=REQUIRED_ISOLATION,
            sandbox_id="sbx-real-1",
        )


# --------------------------------------------------------------------------- #
# The synthetic verdict: safe within scope, never live-capable.
# --------------------------------------------------------------------------- #


class TestSyntheticVerdictShape:
    def test_synthetic_verdict_is_safe_but_not_live_capable(self):
        v = synthetic_cage_verdict()
        assert v.safe is True
        assert v.scope == SCOPE_SYNTHETIC_ONLY
        assert v.attests_live_isolation is False
        assert v.live_admission_permitted is False
        # It confirms NO real isolation — every required property is missing.
        assert v.missing == frozenset(REQUIRED_ISOLATION)

    def test_synthetic_cage_attests_nothing_real(self):
        """SyntheticCage must not fake a live attestation: its attestation is empty,
        so the real-isolation path (evaluate_cage_safety) is never live-safe."""
        live_view = evaluate_cage_safety(SyntheticCage().attest())
        assert live_view.safe is False
        assert live_view.live_admission_permitted is False

    def test_synthetic_cage_verdict_matches_factory(self):
        assert SyntheticCage().verdict().scope == SCOPE_SYNTHETIC_ONLY


# --------------------------------------------------------------------------- #
# safe == True is insufficient for live — enforced by the verdict invariants.
# --------------------------------------------------------------------------- #


class TestSafeIsInsufficientByConstruction:
    def test_cannot_build_synthetic_verdict_that_permits_live(self):
        with pytest.raises(ValueError):
            CageSafetyVerdict(
                safe=True,
                backend_id="liar",
                confirmed=frozenset(),
                missing=frozenset(REQUIRED_ISOLATION),
                required=frozenset(REQUIRED_ISOLATION),
                reason="trying to sneak live admission into a synthetic scope",
                scope=SCOPE_SYNTHETIC_ONLY,
                attests_live_isolation=False,
                live_admission_permitted=True,  # <- the lie, refused by type
            )

    def test_cannot_permit_live_without_attesting_isolation(self):
        with pytest.raises(ValueError):
            CageSafetyVerdict(
                safe=True,
                backend_id="liar",
                confirmed=frozenset(),
                missing=frozenset(),
                required=frozenset(),
                reason="permit live without attesting isolation",
                scope=SCOPE_LIVE,
                attests_live_isolation=False,
                live_admission_permitted=True,  # <- requires attestation, refused
            )

    def test_cannot_attest_live_isolation_in_synthetic_scope(self):
        with pytest.raises(ValueError):
            CageSafetyVerdict(
                safe=True,
                backend_id="liar",
                confirmed=frozenset(),
                missing=frozenset(),
                required=frozenset(),
                reason="attest live isolation while synthetic",
                scope=SCOPE_SYNTHETIC_ONLY,
                attests_live_isolation=True,  # <- refused by type
                live_admission_permitted=False,
            )


# --------------------------------------------------------------------------- #
# Admission matrix.
# --------------------------------------------------------------------------- #


class TestAdmissionMatrix:
    def test_synthetic_origin_under_synthetic_cage_admitted_inert(self):
        admission = admit_origin_under_cage(
            ORIGIN_SYNTHETIC, SyntheticCage().verdict()
        )
        assert admission.admitted is True
        assert admission.scope == SCOPE_SYNTHETIC_ONLY
        assert admission.confers_live_effect is False
        assert admission.requires_cage is True

    def test_live_origin_under_synthetic_cage_rejected(self):
        admission = admit_origin_under_cage(_LIVE, SyntheticCage().verdict())
        assert admission.admitted is False
        assert admission.confers_live_effect is False
        assert "does not permit live admission" in admission.reason

    def test_live_origin_cannot_reuse_synthetic_verdict_object(self):
        """The exact same safe synthetic verdict, handed to a live origin, is
        rejected — a synthetic verdict cannot be replayed/adapted into live
        authority."""
        synth = synthetic_cage_verdict()
        assert synth.safe is True  # safe...
        live = admit_origin_under_cage(_LIVE, synth)
        assert live.admitted is False  # ...but not for live

    def test_live_origin_under_null_cage_rejected(self):
        admission = admit_origin_under_cage(_LIVE, evaluate_cage_safety(NullCage().attest()))
        assert admission.admitted is False
        assert "did not confirm" in admission.reason

    def test_synthetic_origin_under_null_cage_rejected(self):
        # NullCage yields a live-scoped unsafe verdict, not a synthetic_only one.
        admission = admit_origin_under_cage(
            ORIGIN_SYNTHETIC, evaluate_cage_safety(NullCage().attest())
        )
        assert admission.admitted is False

    def test_synthetic_origin_under_real_live_verdict_rejected(self):
        # A synthetic origin uses the synthetic lane; it does not borrow a live
        # verdict's safety even when that verdict is fully safe.
        admission = admit_origin_under_cage(ORIGIN_SYNTHETIC, _real_safe_verdict())
        assert admission.admitted is False

    def test_live_origin_under_real_safe_cage_admitted(self):
        # The live lane still works: a real confirmed-safe cage admits a live origin.
        admission = admit_origin_under_cage(_LIVE, _real_safe_verdict())
        assert admission.admitted is True
        assert admission.confers_live_effect is True
        assert admission.scope == SCOPE_LIVE
