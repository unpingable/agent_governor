"""Specimens for the DebtLedger (P3.0b) — the authoritative claim source.

The load-bearing properties: it returns the LIVE open claim set by rung, refuses
duplicate-id masking, preserves source-boundary identity, distinguishes
open/discharged, and never activates/applies/rolls back anything.
"""

from __future__ import annotations

import inspect

import pytest

from governor import debt_ledger as dl
from governor.activation_preflight import RungDebt
from governor.debt_ledger import DebtLedger, DuplicateClaimError

_HASH = "a" * 64
_RUNG = "self_governance"


def _debt(debt_id="d1", target_rung=_RUNG, collector="operator", discharged=False,
          source=_HASH):
    return RungDebt(
        debt_id=debt_id,
        target_rung=target_rung,
        authorized_collector=collector,
        discharge_witness="w",
        blocks_before="any activation",
        source_boundary_id=source,
        discharged=discharged,
    )


class TestRecordAndIdentity:
    def test_record_get_roundtrip_preserves_source_identity(self, tmp_path) -> None:
        led = DebtLedger(tmp_path)
        led.record(_debt(source=_HASH))
        got = led.get("d1")
        assert got is not None
        assert got.source_boundary_id == _HASH
        assert got.target_rung == _RUNG

    def test_record_idempotent_same_content(self, tmp_path) -> None:
        led = DebtLedger(tmp_path)
        led.record(_debt())
        led.record(_debt())  # identical re-record is fine
        assert led.get("d1") is not None

    def test_duplicate_id_different_content_refused(self, tmp_path) -> None:
        # The anti-masking rule: one id maps to one claim.
        led = DebtLedger(tmp_path)
        led.record(_debt(collector="operator"))
        with pytest.raises(DuplicateClaimError):
            led.record(_debt(collector="someone_else"))

    def test_anti_masking_holds_after_discharge(self, tmp_path) -> None:
        # Recording, discharging, then trying a different claim under the same id
        # must still be refused — discharge does not free the id for a new claim.
        led = DebtLedger(tmp_path)
        led.record(_debt(collector="operator"))
        led.discharge("d1")
        with pytest.raises(DuplicateClaimError):
            led.record(_debt(collector="someone_else"))

    def test_record_refuses_born_discharged(self, tmp_path) -> None:
        # Claims are recorded OPEN; a born-discharged record could hide an open
        # claim at creation. discharge() is the only path to discharged.
        led = DebtLedger(tmp_path)
        with pytest.raises(ValueError, match="recorded OPEN"):
            led.record(_debt(discharged=True))

    def test_get_unknown_returns_none(self, tmp_path) -> None:
        assert DebtLedger(tmp_path).get("nope") is None


class TestOpenClaims:
    def test_open_claims_only_open_and_only_target_rung(self, tmp_path) -> None:
        led = DebtLedger(tmp_path)
        led.record(_debt(debt_id="open_here", target_rung=_RUNG))
        led.record(_debt(debt_id="open_other", target_rung="other_rung"))
        led.record(_debt(debt_id="closed_here", target_rung=_RUNG))
        led.discharge("closed_here")
        ids = [d.debt_id for d in led.open_claims(_RUNG)]
        assert ids == ["open_here"]  # excludes other-rung AND discharged

    def test_open_claims_sorted(self, tmp_path) -> None:
        led = DebtLedger(tmp_path)
        for did in ("d3", "d1", "d2"):
            led.record(_debt(debt_id=did))
        assert [d.debt_id for d in led.open_claims(_RUNG)] == ["d1", "d2", "d3"]

    def test_all_claims_includes_discharged(self, tmp_path) -> None:
        led = DebtLedger(tmp_path)
        led.record(_debt(debt_id="a"))
        led.record(_debt(debt_id="b"))
        led.discharge("b")
        assert {d.debt_id for d in led.all_claims(_RUNG)} == {"a", "b"}
        assert {d.debt_id for d in led.open_claims(_RUNG)} == {"a"}


class TestDischarge:
    def test_discharge_transitions_open_to_discharged(self, tmp_path) -> None:
        led = DebtLedger(tmp_path)
        led.record(_debt(debt_id="d1", discharged=False))
        assert [d.debt_id for d in led.open_claims(_RUNG)] == ["d1"]
        out = led.discharge("d1")
        assert out is not None and out.discharged is True
        assert led.open_claims(_RUNG) == ()  # no longer open
        assert led.get("d1").discharged is True

    def test_discharge_unknown_returns_none(self, tmp_path) -> None:
        assert DebtLedger(tmp_path).discharge("nope") is None

    def test_discharge_idempotent(self, tmp_path) -> None:
        led = DebtLedger(tmp_path)
        led.record(_debt(debt_id="d1"))
        led.discharge("d1")
        again = led.discharge("d1")
        assert again is not None and again.discharged is True


class TestNoEffectSurface:
    _EFFECT_VERBS = ("activate", "apply", "rollback", "promote", "mutate")

    def test_ledger_has_no_effect_method(self) -> None:
        # The ledger records/queries; it does not activate/apply/roll back.
        # ('discharge' is the ledger's own sanctioned state transition, allowed.)
        for name in dir(DebtLedger):
            if name.startswith("_"):
                continue
            assert not any(v in name.lower() for v in self._EFFECT_VERBS), name

    def test_module_has_no_effect_function(self) -> None:
        for name, obj in vars(dl).items():
            if name.startswith("_") or not inspect.isfunction(obj):
                continue
            assert not any(v in name.lower() for v in self._EFFECT_VERBS), name
