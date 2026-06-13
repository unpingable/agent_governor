"""Specimens for the read-only annealing observer (P1.3).

The PRIMARY invariant under test is purity, not classification accuracy:

    annealing_observer can observe forever and never mutate shape.

That is structural here — the module has no emitter, store, sink, or write path —
so "observer sessions emit zero mutation receipts" (loop-protocol §11) holds by
construction. The classification tests are secondary sanity checks.
"""

from __future__ import annotations

import builtins
import inspect

import pytest

from governor import annealing_observer as ao
from governor.annealing_observer import (
    DEFAULT_SOFT_BURN_PER_PROGRESS,
    PATTERN_NONE,
    PATTERN_RECOMPOSITION_LOSS,
    PATTERN_REPEATED_REFUSAL,
    PATTERN_RETRY_EXHAUSTION,
    PATTERN_VERIFIER_FRAGILITY,
    PATTERN_WITNESS_GAP,
    AnnealingObservation,
    ObservationInput,
    burn_per_progress,
    failure_class_entropy,
    observation_input_from_recomposition,
    observe_window,
)
from governor.pipeline_types import (
    VERDICT_ADMISSIBLE,
    VERDICT_REFUSED_CARRIED,
    VERDICT_REFUSED_LAUNDERING,
    RecompositionReceipt,
)

_PROFILE = "workflow:self_governance"


# --------------------------------------------------------------------------- #
# PRIMARY teeth: purity / zero mutation surface
# --------------------------------------------------------------------------- #


class TestObserverPurity:
    _MUTATION_VERBS = (
        "emit",
        "write",
        "apply",
        "store",
        "commit",
        "mutate",
        "persist",
        "save",
        "insert",
        "update",
        "delete",
        "sink",
    )
    # NB: "put" deliberately omitted — it is a substring of the read-only word
    # "input"/"inputs" and would false-flag the observer's pure surface.

    def test_module_exposes_no_mutation_surface(self) -> None:
        # The observer must offer nothing that could write/emit/persist. Every
        # public module-level callable's name is checked against mutation verbs.
        for name, obj in vars(ao).items():
            if name.startswith("_"):
                continue
            if inspect.isfunction(obj):
                lowered = name.lower()
                assert not any(v in lowered for v in self._MUTATION_VERBS), name

    def test_observe_window_takes_no_sink_or_store(self) -> None:
        params = set(inspect.signature(observe_window).parameters)
        assert params == {"inputs", "profile", "soft_burn_threshold"}
        for forbidden in self._MUTATION_VERBS:
            assert not any(forbidden in p for p in params)

    def test_observe_window_performs_no_file_io(self, monkeypatch) -> None:
        # Hard pin: with open() booby-trapped to raise, observation still works —
        # proving the derivation touches no file (no emission, no store).
        def _boom(*a, **k):
            raise AssertionError("annealing_observer must perform no file IO")

        monkeypatch.setattr(builtins, "open", _boom)
        obs = observe_window(
            [ObservationInput(kind="x", progressed=True)], profile=_PROFILE
        )
        assert isinstance(obs, AnnealingObservation)

    def test_observe_window_does_not_mutate_inputs(self) -> None:
        inputs = [
            ObservationInput(kind="x", progressed=True, receipt_id="r1"),
            ObservationInput(kind="y", failure_class="c", receipt_id="r2"),
        ]
        snapshot = list(inputs)
        observe_window(inputs, profile=_PROFILE)
        # Same objects, same order, untouched (records are frozen, but the
        # sequence must not be rebound or reordered either).
        assert inputs == snapshot
        assert all(a is b for a, b in zip(inputs, snapshot))

    def test_no_mutable_module_global_advisory_map(self) -> None:
        # The advisory map is read at derivation time; a mutable global would
        # make observe_window depend on shared state. Pin it immutable so the
        # purity / deterministic-id claim cannot silently regress.
        with pytest.raises(TypeError):
            ao._SUGGESTED_DELTA_KIND["x"] = "mutated"  # type: ignore[index]

    def test_deterministic_content_id(self) -> None:
        inputs = [ObservationInput(kind="x", progressed=True)]
        a = observe_window(inputs, profile=_PROFILE)
        b = observe_window(inputs, profile=_PROFILE)
        assert a.observation_id == b.observation_id
        assert len(a.observation_id) == 64


# --------------------------------------------------------------------------- #
# Metric helpers (loop-protocol §11 definitions)
# --------------------------------------------------------------------------- #


class TestMetrics:
    def test_entropy_zero_for_empty_or_single_class(self) -> None:
        assert failure_class_entropy([]) == 0.0
        assert failure_class_entropy(["a", "a", "a"]) == 0.0
        assert failure_class_entropy([None, None]) == 0.0

    def test_entropy_positive_for_distinct_classes(self) -> None:
        assert failure_class_entropy(["a", "b"]) == pytest.approx(1.0)

    def test_burn_per_progress_none_when_no_progress(self) -> None:
        # missing != zero: a ratio over zero progress is undefined, not infinite.
        assert burn_per_progress(10.0, 0) is None
        assert burn_per_progress(6.0, 2) == 3.0


# --------------------------------------------------------------------------- #
# Classification (secondary) — precedence:
#   recomposition_loss > verifier_fragility > retry_exhaustion
#       > repeated_refusal > witness_gap > none
# --------------------------------------------------------------------------- #


class TestClassification:
    def test_recomposition_loss_wins(self) -> None:
        inputs = [
            ObservationInput(kind=VERDICT_REFUSED_LAUNDERING, failure_class="x"),
            ObservationInput(kind=VERDICT_ADMISSIBLE, progressed=True),
        ]
        obs = observe_window(inputs, profile=_PROFILE)
        assert obs.pattern == PATTERN_RECOMPOSITION_LOSS
        assert obs.recomposition_loss_count == 1
        assert obs.suggested_delta_kind == "tighten_boundary_accounting"

    def test_distinct_classes_is_verifier_fragility(self) -> None:
        inputs = [
            ObservationInput(kind="f", failure_class="a"),
            ObservationInput(kind="f", failure_class="b"),
        ]
        obs = observe_window(inputs, profile=_PROFILE)
        assert obs.pattern == PATTERN_VERIFIER_FRAGILITY
        assert obs.failure_entropy > 0.0

    def test_burn_over_threshold_is_retry_exhaustion(self) -> None:
        # Zero progress with spend = definitional flail; no failure classes so it
        # is not verifier_fragility.
        inputs = [
            ObservationInput(kind="t", capacity_spent=5.0, progressed=False),
            ObservationInput(kind="t", capacity_spent=5.0, progressed=False),
        ]
        obs = observe_window(inputs, profile=_PROFILE)
        assert obs.pattern == PATTERN_RETRY_EXHAUSTION

    def test_repeated_same_class_is_repeated_refusal(self) -> None:
        inputs = [
            ObservationInput(kind="r", failure_class="x"),
            ObservationInput(kind="r", failure_class="x"),
        ]
        obs = observe_window(inputs, profile=_PROFILE)
        assert obs.pattern == PATTERN_REPEATED_REFUSAL

    def test_missing_witness_is_witness_gap(self) -> None:
        inputs = [
            ObservationInput(kind="w", witness_present=False, progressed=True),
        ]
        obs = observe_window(inputs, profile=_PROFILE)
        assert obs.pattern == PATTERN_WITNESS_GAP
        assert obs.witness_gap_count == 1

    def test_quiet_window_is_none(self) -> None:
        inputs = [
            ObservationInput(kind="ok", progressed=True),
            ObservationInput(kind="ok", progressed=True),
        ]
        obs = observe_window(inputs, profile=_PROFILE)
        assert obs.pattern == PATTERN_NONE
        assert obs.suggested_delta_kind is None

    def test_empty_window_is_none(self) -> None:
        obs = observe_window([], profile=_PROFILE)
        assert obs.pattern == PATTERN_NONE
        assert obs.window_size == 0
        assert obs.burn_per_progress is None


# --------------------------------------------------------------------------- #
# Recomposition adapter + observation shape
# --------------------------------------------------------------------------- #


class TestRecompositionAdapter:
    def _receipt(self, admitted, accounted):
        return RecompositionReceipt.from_boundaries(
            projected_intent_hash="sha256:" + "0" * 64,
            admitted=admitted,
            accounted=accounted,
            accepted_by_kernel="workflow:cooked_context (provisional)",
        )

    def test_admissible_maps_to_progress(self) -> None:
        r = self._receipt(("b",), {"b": "completed"})
        inp = observation_input_from_recomposition(r)
        assert inp.kind == VERDICT_ADMISSIBLE
        assert inp.progressed is True
        assert inp.failure_class is None
        assert inp.receipt_id == r.recomposition_id

    def test_laundering_maps_to_failure_class(self) -> None:
        # admitted boundary with no accounting -> refused_laundering
        r = self._receipt(("b1", "b2"), {"b1": "completed"})
        inp = observation_input_from_recomposition(r)
        assert inp.kind == VERDICT_REFUSED_LAUNDERING
        assert inp.failure_class == VERDICT_REFUSED_LAUNDERING
        assert inp.progressed is False

    def test_carried_maps_to_failure_class(self) -> None:
        r = self._receipt(("b",), {"b": "refused"})
        inp = observation_input_from_recomposition(r)
        assert inp.kind == VERDICT_REFUSED_CARRIED
        assert inp.failure_class == VERDICT_REFUSED_CARRIED

    def test_observation_rejects_unknown_pattern(self) -> None:
        with pytest.raises(ValueError, match="pattern must be one of"):
            AnnealingObservation(
                pattern="vibes",
                affected_profile=_PROFILE,
                window_size=0,
                failure_classes=(),
                failure_entropy=0.0,
                burn_per_progress=None,
                recomposition_loss_count=0,
                witness_gap_count=0,
                source_receipt_ids=(),
            )

    def test_to_dict_carries_id_and_schema(self) -> None:
        obs = observe_window(
            [ObservationInput(kind="ok", progressed=True)], profile=_PROFILE
        )
        d = obs.to_dict()
        assert d["observation_id"] == obs.observation_id
        assert d["schema"] == "annealing_observation_v0"

    def test_default_threshold_constant_is_exposed(self) -> None:
        assert DEFAULT_SOFT_BURN_PER_PROGRESS == 3.0
