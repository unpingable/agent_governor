"""Specimens for activation preflight (P3.0).

Proves activation is GATED — impossible while a target is free-form, a gating
debt is open, a debt is self-collected by the gated rung, or the parked-boundary
handoff identity does not line up. Nothing here activates; these are checker
proofs. The genesis-allowlist debt (P2_GENESIS_TARGET_ALLOWLIST_001) is
discharged here by mechanism: activation requires allowlist membership.
"""

from __future__ import annotations

import builtins
import inspect
from pathlib import Path

import pytest

from governor import activation_preflight as ap
from governor.activation_preflight import (
    ELIGIBLE,
    REFUSED_FREE_FORM_TARGET,
    REFUSED_IDENTITY_BROKEN,
    REFUSED_OPEN_NONDISCHARGE_CLAIM,
    REFUSED_SELF_COLLECTED,
    TARGET_ALLOWLISTS,
    EligibilityResult,
    RungDebt,
    check_activation_eligibility,
    target_eligible,
)

_HASH = "a" * 64
_RUNG = "phase_3_activation"
_COLLECTOR = "phase_3_preflight"  # external to the gated rung


def _debt(**over):
    base = dict(
        debt_id="d1",
        target_rung=_RUNG,
        authorized_collector=_COLLECTOR,
        discharge_witness="per_surface_target_allowlists_present",
        blocks_before="any AnnealingDelta activation",
        source_boundary_id=_HASH,
        discharged=False,
    )
    base.update(over)
    return RungDebt(**base)


def _check(**over):
    base = dict(surface="retry_posture", target="retry_budget", target_rung=_RUNG)
    base.update(over)
    return check_activation_eligibility(**base)


# --------------------------------------------------------------------------- #
# Gate 1: per-surface target allowlist (discharges P2_GENESIS_TARGET_ALLOWLIST_001)
# --------------------------------------------------------------------------- #


class TestTargetAllowlist:
    def test_free_form_target_refused(self) -> None:
        r = _check(target="anything_freeform")
        assert r.verdict == REFUSED_FREE_FORM_TARGET
        assert not r.eligible

    def test_allowlisted_target_passes_gate1(self) -> None:
        # No debts → eligible once the target is allowlisted.
        assert _check(target="retry_budget").eligible

    def test_discharges_p2_genesis_debt_by_mechanism(self) -> None:
        # The door P2_GENESIS_TARGET_ALLOWLIST_001 locked: free-form refused,
        # allowlisted eligible — by allowlist membership, which no spelling
        # (camelCase / ALLCAPS / leetspeak) can evade.
        for evasion in ("standing", "STANDING", "stan2ding", "linearAcc0untant"):
            assert _check(target=evasion).verdict == REFUSED_FREE_FORM_TARGET
        assert _check(surface="budgets", target="capacity").eligible

    def test_target_eligible_helper(self) -> None:
        assert target_eligible("routing", "lane_weights") is True
        assert target_eligible("routing", "nope") is False
        assert target_eligible("no_such_surface", "x") is False

    def test_every_surface_has_an_allowlist(self) -> None:
        from governor.annealing import TUNABLE_SURFACES

        assert set(TARGET_ALLOWLISTS) == set(TUNABLE_SURFACES)


# --------------------------------------------------------------------------- #
# Gates 2–4: the rung-debt gate (conservation theorem at the activation seam)
# --------------------------------------------------------------------------- #


class TestRungDebtGate:
    def test_open_debt_refuses_activation(self) -> None:
        r = _check(debts=[_debt(discharged=False)])
        assert r.verdict == REFUSED_OPEN_NONDISCHARGE_CLAIM
        assert "d1" in r.offending

    def test_discharged_debt_is_eligible(self) -> None:
        # A discharged debt is eligible only with its carry witnessed (source in
        # the parked set) — see fail-closed test below.
        r = _check(
            debts=[_debt(discharged=True)],
            parked_boundary_ids=frozenset({_HASH}),
        )
        assert r.eligible

    def test_discharged_debt_with_no_parked_set_fails_closed(self) -> None:
        # A discharged debt with parked_boundary_ids=None (carry never witnessed)
        # must NOT be eligible — fail closed, never a silent ELIGIBLE.
        r = _check(debts=[_debt(discharged=True)])  # parked defaults to None
        assert r.verdict == REFUSED_IDENTITY_BROKEN

    def test_duplicate_id_open_debt_not_masked(self) -> None:
        # A discharged debt cannot mask an open debt that shares its id — unique
        # per-occurrence accounting keys keep the open occurrence visible.
        r = _check(
            debts=[
                _debt(debt_id="dup", discharged=True),
                _debt(debt_id="dup", discharged=False),
            ],
            parked_boundary_ids=frozenset({_HASH}),
        )
        assert r.verdict == REFUSED_OPEN_NONDISCHARGE_CLAIM
        assert "dup" in r.offending

    def test_debt_for_other_rung_is_irrelevant(self) -> None:
        # A debt targeting a different rung does not gate this one.
        r = _check(debts=[_debt(target_rung="some_other_rung", discharged=False)])
        assert r.eligible

    def test_self_collected_debt_refused(self) -> None:
        # RungDebt refuses collector==target at construction, so forge one past
        # the frozen dataclass to exercise the gate's own re-check.
        d = _debt()
        object.__setattr__(d, "authorized_collector", _RUNG)
        r = _check(debts=[d])
        assert r.verdict == REFUSED_SELF_COLLECTED
        assert "d1" in r.offending

    def test_identity_broken_malformed_source(self) -> None:
        d = _debt(source_boundary_id="not-a-content-hash", discharged=True)
        r = _check(debts=[d])
        assert r.verdict == REFUSED_IDENTITY_BROKEN

    def test_identity_broken_not_in_parked_set(self) -> None:
        d = _debt(discharged=True)
        r = _check(debts=[d], parked_boundary_ids=frozenset())  # id absent
        assert r.verdict == REFUSED_IDENTITY_BROKEN

    def test_identity_ok_when_in_parked_set(self) -> None:
        d = _debt(discharged=True)
        r = _check(debts=[d], parked_boundary_ids=frozenset({_HASH}))
        assert r.eligible

    def test_no_debts_is_eligible(self) -> None:
        assert _check(debts=()).eligible


# --------------------------------------------------------------------------- #
# RungDebt construction (the conservation theorem at bind time)
# --------------------------------------------------------------------------- #


class TestRungDebtConstruction:
    def test_collector_cannot_equal_target_rung(self) -> None:
        with pytest.raises(ValueError, match="must not equal target_rung"):
            _debt(authorized_collector=_RUNG)

    def test_mandatory_fields(self) -> None:
        for blank in ("debt_id", "target_rung", "source_boundary_id"):
            with pytest.raises(ValueError, match="mandatory"):
                _debt(**{blank: ""})

    def test_to_dict_roundtrip_shape(self) -> None:
        d = _debt(discharged=True)
        payload = d.to_dict()
        assert payload["authorized_collector"] == _COLLECTOR
        assert payload["discharged"] is True


# --------------------------------------------------------------------------- #
# Federation + no-activation fences
# --------------------------------------------------------------------------- #


class TestFences:
    _DOING_VERBS = ("apply", "activate", "mutate", "rollback", "promote",
                    "config_write", "write_config")

    def test_module_has_no_doing_verb_function(self) -> None:
        # The slice is a CHECKER. No function does activation/apply/write.
        # (NB: 'activation' the noun is fine; 'activate' the verb is not — and
        # 'activate' is not a substring of 'activation'.)
        for name, obj in vars(ap).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            lowered = name.lower()
            assert not any(v in lowered for v in self._DOING_VERBS), name

    def test_reuses_account_boundaries_combinator(self) -> None:
        # account_boundaries is imported and used, NOT reimplemented here — it
        # stays a shared combinator, not a new authority owned by this module.
        src = Path(ap.__file__).read_text()
        assert "from .pipeline_types import" in src
        assert "account_boundaries" in src
        assert "def account_boundaries" not in src

    def test_no_apply_or_write_primitive_in_source(self) -> None:
        src = Path(ap.__file__).read_text()
        for needle in ("open(", ".write(", "def apply", "def activate", "def rollback"):
            assert needle not in src, needle

    def test_check_performs_no_file_io(self, monkeypatch) -> None:
        def _boom(*a, **k):
            raise AssertionError("activation preflight must perform no file IO")

        monkeypatch.setattr(builtins, "open", _boom)
        assert _check(target="retry_budget").eligible

    def test_eligibility_result_rejects_unknown_verdict(self) -> None:
        with pytest.raises(ValueError, match="verdict must be one of"):
            EligibilityResult(verdict="vibes")
