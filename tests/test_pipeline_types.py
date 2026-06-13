"""Specimens for recomposition receipts + boundary accounting.

P1.1 of the workflow-kernel / self-annealing campaign. The discipline under
test: "all slices passed" must not launder into "the whole is admissible." An
admitted decomposition boundary that goes unaccounted forces refused_laundering
regardless of how green the surviving slices are.

Shadow-only: nothing here wires into the orchestrator or enforces. These pin the
receipt shape and the accounting verdicts so later slices (P1.2 shadow emission,
P3b enforcement) inherit a frozen contract.
"""

from __future__ import annotations

import pytest

from governor.pipeline_types import (
    CLOSED_DISPOSITIONS,
    CLOSED_FIDELITY_CLASSES,
    CLOSED_VERDICTS,
    DISPOSITION_COMPLETED,
    DISPOSITION_FAILED,
    DISPOSITION_PARKED,
    DISPOSITION_REFUSED,
    VERDICT_ADMISSIBLE,
    VERDICT_ADMISSIBLE_PARTIAL,
    VERDICT_REFUSED_CARRIED,
    VERDICT_REFUSED_LAUNDERING,
    BoundaryAccounting,
    RecompositionReceipt,
    account_boundaries,
)

# --------------------------------------------------------------------------- #
# Representative boundary sets (stand in for replayed receipt trails)
# --------------------------------------------------------------------------- #

# A clean cooked-context-shaped chain: every admitted boundary completed.
_CLEAN_ADMITTED = ("b_standing", "b_wicket", "b_spendability", "b_la")
_CLEAN_ACCOUNTED = {
    "b_standing": DISPOSITION_COMPLETED,
    "b_wicket": DISPOSITION_COMPLETED,
    "b_spendability": DISPOSITION_COMPLETED,
    "b_la": DISPOSITION_COMPLETED,
}

# The synthetic laundering fixture: a slice dropped between decompose and
# recompose. Every *surviving* slice is green, but b_spendability is admitted
# and never accounted. This must refuse.
_DROPPED_SLICE_ADMITTED = _CLEAN_ADMITTED
_DROPPED_SLICE_ACCOUNTED = {
    "b_standing": DISPOSITION_COMPLETED,
    "b_wicket": DISPOSITION_COMPLETED,
    # b_spendability silently missing
    "b_la": DISPOSITION_COMPLETED,
}


# --------------------------------------------------------------------------- #
# account_boundaries — the pure, total teeth
# --------------------------------------------------------------------------- #


class TestAccountBoundaries:
    def test_all_completed_is_admissible(self) -> None:
        r = account_boundaries(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        assert r.verdict == VERDICT_ADMISSIBLE
        assert r.unaccounted == ()
        assert r.admitted_count == 4
        assert r.admissible is True

    def test_dropped_slice_is_laundering(self) -> None:
        # AC2: surviving slices all green, one admitted boundary unaccounted.
        r = account_boundaries(_DROPPED_SLICE_ADMITTED, _DROPPED_SLICE_ACCOUNTED)
        assert r.verdict == VERDICT_REFUSED_LAUNDERING
        assert r.unaccounted == ("b_spendability",)
        assert r.is_laundering is True

    def test_unrecognized_disposition_is_laundering(self) -> None:
        # Claiming an accounting with a nonsense token is laundering by another
        # name. The boundary is "present" but dishonestly dispositioned.
        accounted = dict(_CLEAN_ACCOUNTED)
        accounted["b_la"] = "banana"
        r = account_boundaries(_CLEAN_ADMITTED, accounted)
        assert r.verdict == VERDICT_REFUSED_LAUNDERING
        assert r.unrecognized == ("b_la",)
        assert r.unaccounted == ()

    def test_refused_boundary_is_carried_refusal(self) -> None:
        accounted = dict(_CLEAN_ACCOUNTED)
        accounted["b_spendability"] = DISPOSITION_REFUSED
        r = account_boundaries(_CLEAN_ADMITTED, accounted)
        assert r.verdict == VERDICT_REFUSED_CARRIED
        assert r.refused == ("b_spendability",)
        assert r.admissible is False

    def test_failed_or_parked_is_partial_progress(self) -> None:
        accounted = dict(_CLEAN_ACCOUNTED)
        accounted["b_la"] = DISPOSITION_PARKED
        accounted["b_wicket"] = DISPOSITION_FAILED
        r = account_boundaries(_CLEAN_ADMITTED, accounted)
        assert r.verdict == VERDICT_ADMISSIBLE_PARTIAL
        assert set(r.incomplete) == {"b_la", "b_wicket"}
        assert r.admissible is True

    def test_empty_decomposition_is_vacuously_admissible(self) -> None:
        r = account_boundaries((), {})
        assert r.verdict == VERDICT_ADMISSIBLE
        assert r.admitted_count == 0

    def test_extraneous_accounting_recorded_not_verdict_changing(self) -> None:
        # A boundary accounted but never admitted is recorded for diagnosis but
        # does not change the verdict in P1.1.
        accounted = dict(_CLEAN_ACCOUNTED)
        accounted["b_ghost"] = DISPOSITION_COMPLETED
        r = account_boundaries(_CLEAN_ADMITTED, accounted)
        assert r.verdict == VERDICT_ADMISSIBLE
        assert r.extraneous == ("b_ghost",)

    def test_laundering_outranks_carried_refusal(self) -> None:
        # Precedence: an unaccounted boundary (silent drop) is more dangerous
        # than an honest refusal, so laundering wins.
        accounted = {
            "b_standing": DISPOSITION_REFUSED,  # honest refusal present
            # b_wicket, b_spendability, b_la all silently dropped
        }
        r = account_boundaries(_CLEAN_ADMITTED, accounted)
        assert r.verdict == VERDICT_REFUSED_LAUNDERING

    def test_totality_every_admitted_boundary_is_bucketed(self) -> None:
        # AC1: the function is total. Across a sweep of synthetic decompositions,
        # every admitted boundary lands in exactly one bucket, and any
        # unaccounted boundary always forces laundering.
        dispositions = [
            DISPOSITION_COMPLETED,
            DISPOSITION_FAILED,
            DISPOSITION_PARKED,
            DISPOSITION_REFUSED,
            "__missing__",  # sentinel: omit from accounting
            "__garbage__",  # sentinel: unrecognized disposition
        ]
        admitted = tuple(f"b{i}" for i in range(len(dispositions)))
        accounted: dict[str, str] = {}
        for bid, disp in zip(admitted, dispositions):
            if disp == "__missing__":
                continue
            accounted[bid] = "not_a_real_disposition" if disp == "__garbage__" else disp

        r = account_boundaries(admitted, accounted)
        bucketed = (
            set(r.unaccounted)
            | set(r.unrecognized)
            | set(r.refused)
            | set(r.incomplete)
        )
        completed = set(admitted) - bucketed
        # every admitted boundary accounted for exactly once across buckets+clean
        assert bucketed | completed == set(admitted)
        assert len(bucketed) + len(completed) == len(admitted)
        # a missing OR garbage boundary forces laundering
        assert r.verdict == VERDICT_REFUSED_LAUNDERING

    def test_missing_boundary_always_forces_laundering(self) -> None:
        # AC1 sharpened: for any otherwise-green set, omitting any single
        # admitted boundary flips the verdict to laundering.
        for omit in _CLEAN_ADMITTED:
            accounted = {
                k: v for k, v in _CLEAN_ACCOUNTED.items() if k != omit
            }
            r = account_boundaries(_CLEAN_ADMITTED, accounted)
            assert r.verdict == VERDICT_REFUSED_LAUNDERING, omit
            assert omit in r.unaccounted

    def test_returns_boundary_accounting(self) -> None:
        assert isinstance(
            account_boundaries(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED),
            BoundaryAccounting,
        )


# --------------------------------------------------------------------------- #
# Closed vocabularies
# --------------------------------------------------------------------------- #


class TestClosedVocabularies:
    def test_dispositions_closed(self) -> None:
        assert CLOSED_DISPOSITIONS == {
            "completed",
            "failed",
            "parked",
            "refused",
        }

    def test_verdicts_closed(self) -> None:
        assert CLOSED_VERDICTS == {
            "admissible",
            "admissible_partial_progress",
            "refused_laundering",
            "refused_carried",
        }

    def test_fidelity_classes_closed(self) -> None:
        assert CLOSED_FIDELITY_CLASSES == {
            "exact",
            "bounded",
            "heuristic",
            "exploratory",
        }


# --------------------------------------------------------------------------- #
# RecompositionReceipt
# --------------------------------------------------------------------------- #


class TestRecompositionReceipt:
    def _build(self, admitted, accounted, **kw):
        return RecompositionReceipt.from_boundaries(
            projected_intent_hash="sha256:" + "0" * 64,
            admitted=admitted,
            accounted=accounted,
            accepted_by_kernel="workflow:self_governance (provisional)",
            **kw,
        )

    def test_from_boundaries_computes_verdict(self) -> None:
        r = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        assert r.verdict == VERDICT_ADMISSIBLE
        assert r.shadow is True
        assert r.effective is False

    def test_from_boundaries_laundering(self) -> None:
        r = self._build(_DROPPED_SLICE_ADMITTED, _DROPPED_SLICE_ACCOUNTED)
        assert r.verdict == VERDICT_REFUSED_LAUNDERING
        assert r.accounting().unaccounted == ("b_spendability",)

    def test_cannot_construct_inconsistent_verdict(self) -> None:
        # The receipt-level teeth: you cannot hand-set a verdict its own
        # boundaries do not support.
        with pytest.raises(ValueError, match="inconsistent with boundary"):
            RecompositionReceipt(
                verdict=VERDICT_ADMISSIBLE,
                projected_intent_hash="sha256:" + "0" * 64,
                boundaries_admitted=_DROPPED_SLICE_ADMITTED,
                boundaries_accounted=tuple(sorted(_DROPPED_SLICE_ACCOUNTED.items())),
                accepted_by_kernel="k",
            )

    def test_shadow_and_effective_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="exactly one of shadow"):
            self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED, shadow=True, effective=True)
        with pytest.raises(ValueError, match="exactly one of shadow"):
            self._build(
                _CLEAN_ADMITTED, _CLEAN_ACCOUNTED, shadow=False, effective=False
            )

    def test_effective_mode_permitted_as_data(self) -> None:
        # The dataclass permits the effective representation (enforcement flip is
        # P3b); it just must be exactly-one.
        r = self._build(
            _CLEAN_ADMITTED, _CLEAN_ACCOUNTED, shadow=False, effective=True
        )
        assert r.effective is True

    def test_rejects_bad_fidelity_class(self) -> None:
        with pytest.raises(ValueError, match="fidelity_class"):
            self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED, fidelity_class="vibes")

    def test_accepts_known_fidelity_class(self) -> None:
        r = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED, fidelity_class="bounded")
        assert r.fidelity_class == "bounded"

    def test_requires_projected_intent_hash(self) -> None:
        with pytest.raises(ValueError, match="projected_intent_hash"):
            RecompositionReceipt.from_boundaries(
                projected_intent_hash="",
                admitted=_CLEAN_ADMITTED,
                accounted=_CLEAN_ACCOUNTED,
                accepted_by_kernel="k",
            )

    def test_la_custody_defaults_false_visible_downgrade(self) -> None:
        # Standalone rule: without LA the spend is local/receipt-only and the
        # downgrade is visible, not faked.
        r = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        assert r.la_custody is False

    def test_content_hash_is_deterministic(self) -> None:
        a = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        b = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        assert a.recomposition_id == b.recomposition_id
        assert len(a.recomposition_id) == 64
        assert all(c in "0123456789abcdef" for c in a.recomposition_id)

    def test_distinct_verdicts_distinct_ids(self) -> None:
        clean = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        dropped = self._build(_DROPPED_SLICE_ADMITTED, _DROPPED_SLICE_ACCOUNTED)
        assert clean.recomposition_id != dropped.recomposition_id

    def test_shadow_and_effective_distinct_ids(self) -> None:
        shadow = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        effective = self._build(
            _CLEAN_ADMITTED, _CLEAN_ACCOUNTED, shadow=False, effective=True
        )
        assert shadow.recomposition_id != effective.recomposition_id

    def test_to_dict_carries_id_and_schema(self) -> None:
        r = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        d = r.to_dict()
        assert d["recomposition_id"] == r.recomposition_id
        assert d["schema"] == "recomposition_receipt_v0"
        assert d["verdict"] == VERDICT_ADMISSIBLE


# --------------------------------------------------------------------------- #
# Golden hash lock — catches canonical-form drift
# --------------------------------------------------------------------------- #


class TestGoldenHashes:
    """Frozen content hashes. If canonical_dict changes shape, these break —
    which is the point: a silent canonicalization change is a schema break.
    """

    # Filled from a live run (see test body comment). Regenerate intentionally
    # only when the schema is deliberately bumped.
    GOLDEN_ADMISSIBLE = (
        "3171e201cb4ce19eb7d6f96e330912da31edfc7a1ca254a42971fc80fc591a98"
    )
    GOLDEN_LAUNDERING = (
        "f906e9c0b307adf1399d34e78e14d4ef708c06104994a55e43bf1ac9564b0e5d"
    )

    def _build(self, admitted, accounted, **kw):
        return RecompositionReceipt.from_boundaries(
            projected_intent_hash="sha256:" + "0" * 64,
            admitted=admitted,
            accounted=accounted,
            accepted_by_kernel="workflow:self_governance (provisional)",
            **kw,
        )

    def test_golden_admissible(self) -> None:
        r = self._build(_CLEAN_ADMITTED, _CLEAN_ACCOUNTED)
        assert r.recomposition_id == self.GOLDEN_ADMISSIBLE

    def test_golden_laundering(self) -> None:
        r = self._build(_DROPPED_SLICE_ADMITTED, _DROPPED_SLICE_ACCOUNTED)
        assert r.recomposition_id == self.GOLDEN_LAUNDERING
