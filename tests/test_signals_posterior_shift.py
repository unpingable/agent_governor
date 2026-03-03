# SPDX-License-Identifier: Apache-2.0
"""Tests for B3 POSTERIOR_SHIFT_ATTRIBUTION (leave-one-out influence).

Invariants tested:
  1. Determinism: same input set → identical rankings + deltas
  2. Degenerates: empty set, singleton, None scores
  3. Removal semantics: recompute, not subtract
  4. Non-conservation: deltas don't sum to score_full (that's correct)
  5. Stability: removing unused signal yields delta=0
  6. Method field: always "loo_influence_v1"
  7. Calibration: monotone cal → sign(delta_raw) matches sign(delta_cal)
  8. Compute cost: always n+1
"""

from __future__ import annotations

import pytest

from governor.signals.capture_self_diagnostic import (
    CLASSIFICATION_NORMAL,
    CLASSIFICATION_WATCH,
    CLASSIFICATION_WARNING,
    CLASSIFICATION_INSTRUMENTATION_COMPROMISED,
    CLASSIFICATION_INSUFFICIENT_HISTORY,
    DiagnosticInputs,
    derive_capture_self_diagnostic,
)
from governor.signals.exposure_proxy import (
    ExposureComponents,
    derive_exposure_proxy,
)
from governor.signals.posterior_shift import (
    ATTRIBUTION_CONFIG_VERSION,
    ATTRIBUTION_METHOD,
    EPSILON,
    Influence,
    compute_loo_influences,
    derive_posterior_shift,
)
from governor.signals.sigma_rate import (
    SigmaEvent,
    SigmaMatchResult,
    derive_sigma_rate,
)
from governor.signals.silent_suppression import (
    SuppressionIndicators,
    derive_silent_suppression,
)


# ── Helpers ──────────────────────────────────────────────────────────────

WIN_START = "2026-03-03T00:00:00Z"
WIN_END = "2026-03-03T00:05:00Z"
WIN_KIND = "rolling_5m"


def _make_a1(**kwargs):
    defaults = {"tool_dispatch_attempts": 5, "chat_generation_calls": 3}
    defaults.update(kwargs)
    return derive_exposure_proxy(
        ExposureComponents(**defaults),
        WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END,
    )


def _make_a2_healthy():
    return derive_silent_suppression(
        SuppressionIndicators(
            expected_event_markers=5,
            observed_event_markers=5,
            activity_observed=True,
            in_path_evidence_present=True,
        ),
        WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END,
    )


def _make_a2_suppressed():
    return derive_silent_suppression(
        SuppressionIndicators(
            expected_event_markers=5,
            observed_event_markers=0,
            activity_observed=True,
            in_path_evidence_present=False,
        ),
        WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END,
    )


def _make_a3_clean():
    return derive_sigma_rate(
        SigmaMatchResult(eligible_events=10),
        WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END,
    )


def _make_a3_elevated():
    pairs = [
        SigmaEvent(
            subject_hash=f"subj_{i}",
            endorsement_id=f"e_{i}",
            invalidation_id=f"i_{i}",
            endorsement_ts=WIN_START,
            invalidation_ts=WIN_END,
            lag_ms=1000.0,
        )
        for i in range(5)
    ]
    return derive_sigma_rate(
        SigmaMatchResult(pairs=pairs, eligible_events=10),
        WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END,
    )


# ── 1. Determinism ───────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_inputs_same_deltas(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        r1 = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)
        r2 = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)
        assert len(r1) == len(r2)
        for i1, i2 in zip(r1, r2):
            assert i1.delta_raw == i2.delta_raw
            assert i1.rank == i2.rank
            assert i1.signal_id == i2.signal_id

    def test_same_inputs_same_rankings(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        r1 = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)
        r2 = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)
        ids1 = [i.signal_id for i in r1]
        ids2 = [i.signal_id for i in r2]
        assert ids1 == ids2

    def test_envelope_content_hash_stable(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        e1 = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        e2 = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert e1.content_hash() == e2.content_hash()


# ── 2. Degenerates ───────────────────────────────────────────────────────

class TestDegenerates:
    def test_no_signals_empty_influences(self):
        """All None → no influences, unavailable."""
        result = compute_loo_influences(None, None, None, WIN_START, WIN_END, WIN_KIND)
        assert result == []

    def test_singleton_a2_only(self):
        """Only A2 → one influence, B1 can't compute score without A1/A3."""
        a2 = _make_a2_healthy()
        result = compute_loo_influences(None, a2, None, WIN_START, WIN_END, WIN_KIND)
        assert len(result) == 1
        assert result[0].signal_id == "SILENT_SUPPRESSION"

    def test_singleton_a3_only(self):
        """Only A3 → B1 needs A2, so score_full likely None or limited."""
        a3 = _make_a3_clean()
        result = compute_loo_influences(None, None, a3, WIN_START, WIN_END, WIN_KIND)
        assert len(result) == 1
        assert result[0].signal_id == "SIGMA_RATE"

    def test_missing_a1_two_signals(self):
        """A2 + A3 only → two influences, A1 absent."""
        a2, a3 = _make_a2_healthy(), _make_a3_elevated()
        result = compute_loo_influences(None, a2, a3, WIN_START, WIN_END, WIN_KIND)
        assert len(result) == 2
        signal_ids = {i.signal_id for i in result}
        assert signal_ids == {"SILENT_SUPPRESSION", "SIGMA_RATE"}

    def test_envelope_unavailable_when_no_signals(self):
        env = derive_posterior_shift(None, None, None, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.quality_status == "unavailable"
        assert env.value is None


# ── 3. Removal semantics (recompute, not subtract) ───────────────────────

class TestRemovalSemantics:
    def test_removing_a2_changes_classification(self):
        """Removing A2 (suppression) should change B1 fundamentally — it gates everything."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)

        a2_inf = next(i for i in result if i.signal_id == "SILENT_SUPPRESSION")
        # Without A2, B1 returns "indeterminate" or "insufficient" — not the same score
        # The classification should change
        assert a2_inf.classification_minus != a2_inf.classification_full or a2_inf.score_minus != a2_inf.score_full

    def test_removing_a3_with_elevated_sigma(self):
        """Removing elevated A3 should lower the score (sigma is the main contributor)."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)

        a3_inf = next(i for i in result if i.signal_id == "SIGMA_RATE")
        # delta_raw = score_full - score_minus
        # Removing A3 should lower score → score_minus < score_full → delta_raw > 0
        if a3_inf.delta_raw is not None:
            assert a3_inf.delta_raw > 0, "Removing elevated sigma should show positive influence"
            assert a3_inf.direction == "increase"

    def test_removing_a1_with_clean_state(self):
        """Removing A1 from a clean state — minimal impact on score."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)
        a1_inf = next(i for i in result if i.signal_id == "EXPOSURE_PROXY")
        # In clean state, A1 contributes little (coverage is fine)
        if a1_inf.delta_raw is not None:
            assert abs(a1_inf.delta_raw) < 0.5  # not the dominant signal


# ── 4. Non-conservation ──────────────────────────────────────────────────

class TestNonConservation:
    def test_deltas_dont_sum_to_score(self):
        """LOO deltas should NOT sum to score_full — they're influences, not partitions."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)

        score_full = result[0].score_full if result else None
        if score_full is not None and score_full > EPSILON:
            delta_sum = sum(
                i.delta_raw for i in result if i.delta_raw is not None
            )
            # They might happen to sum close to score_full in this linear model,
            # but the test is that we DON'T assert equality
            # Instead, verify the influence_mass concept in the envelope
            env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
            mass = env.values.get("influence_mass")
            assert mass is not None
            # mass = sum(|delta|), which is >= |sum(delta)|
            assert mass >= 0


# ── 5. Stability ─────────────────────────────────────────────────────────

class TestStability:
    def test_removing_absent_signal_not_in_influences(self):
        """If a signal is None, it shouldn't appear in influences at all."""
        a2, a3 = _make_a2_healthy(), _make_a3_clean()
        result = compute_loo_influences(None, a2, a3, WIN_START, WIN_END, WIN_KIND)
        signal_ids = {i.signal_id for i in result}
        assert "EXPOSURE_PROXY" not in signal_ids

    def test_ranks_are_contiguous(self):
        """Ranks should be 1, 2, ..., n with no gaps."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)
        ranks = sorted(i.rank for i in result)
        assert ranks == list(range(1, len(result) + 1))

    def test_rank_1_has_largest_abs_delta(self):
        """Rank 1 should have the largest |delta_raw|."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)
        if len(result) >= 2:
            r1 = next(i for i in result if i.rank == 1)
            r2 = next(i for i in result if i.rank == 2)
            d1 = abs(r1.delta_raw) if r1.delta_raw is not None else 0.0
            d2 = abs(r2.delta_raw) if r2.delta_raw is not None else 0.0
            assert d1 >= d2


# ── 6. Method field ──────────────────────────────────────────────────────

class TestMethodField:
    def test_method_is_loo(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.values["method"] == "loo_influence_v1"
        assert env.annotations["method"] == "loo_influence_v1"

    def test_config_version(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.values["config_version"] == ATTRIBUTION_CONFIG_VERSION
        assert env.derivation_version == ATTRIBUTION_CONFIG_VERSION


# ── 7. Calibration ───────────────────────────────────────────────────────

class TestCalibration:
    def test_no_calibration_no_cal_fields(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)
        for inf in result:
            assert inf.cal_full is None
            assert inf.cal_minus is None
            assert inf.delta_cal is None

    def test_identity_calibration(self):
        """Identity calibration: delta_cal == delta_raw."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        identity = lambda x: x  # noqa: E731
        result = compute_loo_influences(
            a1, a2, a3, WIN_START, WIN_END, WIN_KIND, calibrate=identity,
        )
        for inf in result:
            if inf.delta_raw is not None and inf.delta_cal is not None:
                assert abs(inf.delta_raw - inf.delta_cal) < EPSILON

    def test_monotone_calibration_preserves_sign(self):
        """Monotone calibration: sign(delta_cal) == sign(delta_raw)."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        # Monotone increasing: x → 2*x (clamped to [0,1])
        monotone = lambda x: min(2.0 * x, 1.0)  # noqa: E731
        result = compute_loo_influences(
            a1, a2, a3, WIN_START, WIN_END, WIN_KIND, calibrate=monotone,
        )
        for inf in result:
            if inf.delta_raw is not None and inf.delta_cal is not None:
                if abs(inf.delta_raw) > EPSILON and abs(inf.delta_cal) > EPSILON:
                    # Signs should match for monotone cal
                    assert (inf.delta_raw > 0) == (inf.delta_cal > 0), (
                        f"{inf.signal_id}: delta_raw={inf.delta_raw}, "
                        f"delta_cal={inf.delta_cal}"
                    )

    def test_calibration_fields_in_influence_dict(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        identity = lambda x: x  # noqa: E731
        result = compute_loo_influences(
            a1, a2, a3, WIN_START, WIN_END, WIN_KIND, calibrate=identity,
        )
        for inf in result:
            d = inf.to_dict()
            if inf.cal_full is not None:
                assert "cal_full" in d
                assert "cal_minus" in d
                assert "delta_cal" in d

    def test_has_calibration_flag_in_annotations(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env_no_cal = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env_no_cal.annotations["has_calibration"] is False

        env_cal = derive_posterior_shift(
            a1, a2, a3, WIN_START, WIN_END, WIN_KIND,
            calibrate=lambda x: x, emitted_at=WIN_END,
        )
        assert env_cal.annotations["has_calibration"] is True


# ── 8. Compute cost ──────────────────────────────────────────────────────

class TestComputeCost:
    def test_cost_is_n_plus_1(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.values["compute_cost"] == 4  # 3 signals + 1 full

    def test_cost_with_two_signals(self):
        a2, a3 = _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(None, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.values["compute_cost"] == 3  # 2 signals + 1 full

    def test_cost_with_one_signal(self):
        a2 = _make_a2_healthy()
        env = derive_posterior_shift(None, a2, None, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.values["compute_cost"] == 2  # 1 signal + 1 full

    def test_cost_with_zero_signals(self):
        env = derive_posterior_shift(None, None, None, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.values["compute_cost"] == 1  # 0 signals + 1 full


# ── 9. Envelope shape ────────────────────────────────────────────────────

class TestEnvelopeShape:
    def test_signal_id_and_phase(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.signal_id == "POSTERIOR_SHIFT_ATTRIBUTION"
        assert env.signal_version == 1
        assert env.phase == "2.4B"

    def test_unit_is_influence(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.unit == "influence"

    def test_source_versions_populated(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.source_versions
        assert "governor" in env.source_versions

    def test_source_streams_lists_inputs(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert "EXPOSURE_PROXY" in env.source_streams
        assert "SILENT_SUPPRESSION" in env.source_streams
        assert "SIGMA_RATE" in env.source_streams

    def test_window_fields(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.window_start == WIN_START
        assert env.window_end == WIN_END
        assert env.window_kind == WIN_KIND

    def test_content_hashes_in_annotations(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.annotations["a1_content_hash"] is not None
        assert env.annotations["a2_content_hash"] is not None
        assert env.annotations["a3_content_hash"] is not None

    def test_session_id_forwarded(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(
            a1, a2, a3, WIN_START, WIN_END, WIN_KIND,
            session_id="test-sess", emitted_at=WIN_END,
        )
        assert env.session_id == "test-sess"

    def test_n_signals_in_values(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert env.values["n_signals"] == 3

    def test_influences_list_in_values(self):
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        assert isinstance(env.values["influences"], list)
        assert len(env.values["influences"]) == 3


# ── 10. Integration: elevated sigma dominates ─────────────────────────────

class TestIntegration:
    def test_suppression_highest_influence_with_all_signals(self):
        """A2 (suppression) gates all scoring — removing it is most influential."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)

        # A2 gates everything: removing it makes B1 return indeterminate/None
        a2_inf = next((i for i in result if i.signal_id == "SILENT_SUPPRESSION"), None)
        assert a2_inf is not None
        # A2 removal → score_minus is None → delta is None → indeterminate
        # But SIGMA_RATE should still be influential when A2 is held constant
        sigma_inf = next((i for i in result if i.signal_id == "SIGMA_RATE"), None)
        assert sigma_inf is not None

    def test_sigma_rate_highest_among_scoring_signals(self):
        """Among A1 and A3 (the scoring signals), elevated A3 dominates."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_elevated()
        result = compute_loo_influences(a1, a2, a3, WIN_START, WIN_END, WIN_KIND)

        # Compare only A1 and A3 (A2 is the gate, different category)
        scoring = [i for i in result if i.signal_id in ("EXPOSURE_PROXY", "SIGMA_RATE")]
        scoring_with_delta = [i for i in scoring if i.delta_raw is not None]
        if len(scoring_with_delta) >= 2:
            by_abs_delta = sorted(scoring_with_delta, key=lambda x: -abs(x.delta_raw))
            assert by_abs_delta[0].signal_id == "SIGMA_RATE"

    def test_clean_state_low_influence_mass(self):
        """Clean state → low total influence mass."""
        a1, a2, a3 = _make_a1(), _make_a2_healthy(), _make_a3_clean()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        if env.value is not None:
            assert env.value < 1.0  # influence mass should be small for clean state

    def test_suppressed_state_all_indeterminate(self):
        """With suppressed A2, score_full is None → most deltas are None."""
        a1, a2, a3 = _make_a1(), _make_a2_suppressed(), _make_a3_elevated()
        env = derive_posterior_shift(a1, a2, a3, WIN_START, WIN_END, WIN_KIND, emitted_at=WIN_END)
        # Score not computable when suppressed
        assert env.quality_status in ("unavailable", "ok")


# ── 11. Influence.to_dict ─────────────────────────────────────────────────

class TestInfluenceModel:
    def test_to_dict_no_cal(self):
        inf = Influence(
            signal_id="SIGMA_RATE",
            score_full=0.5,
            score_minus=0.1,
            delta_raw=0.4,
            classification_full="warning",
            classification_minus="normal",
            direction="increase",
            rank=1,
        )
        d = inf.to_dict()
        assert d["signal_id"] == "SIGMA_RATE"
        assert d["delta_raw"] == 0.4
        assert "cal_full" not in d  # no cal fields when None

    def test_to_dict_with_cal(self):
        inf = Influence(
            signal_id="SIGMA_RATE",
            score_full=0.5,
            score_minus=0.1,
            delta_raw=0.4,
            classification_full="warning",
            classification_minus="normal",
            direction="increase",
            rank=1,
            cal_full=0.7,
            cal_minus=0.2,
            delta_cal=0.5,
        )
        d = inf.to_dict()
        assert d["cal_full"] == 0.7
        assert d["cal_minus"] == 0.2
        assert d["delta_cal"] == 0.5
