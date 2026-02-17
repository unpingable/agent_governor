# SPDX-License-Identifier: Apache-2.0
"""Tests for mode_detection — Bayesian mode posterior (AG2 Layer 2.1-C)."""

import json
import math
from pathlib import Path

import pytest

from governor.mode_detection import (
    DomainMode,
    DriftAction,
    DriftPhase,
    Observation,
    ModePosterior,
    DriftAlert,
    ModeState,
    ModeDetectionStore,
    compute_mode_features,
    update_mode_posterior,
    compute_drift,
    check_mode_drift,
    get_mode_profile,
    observe_and_update,
    make_mode_event,
    DEFAULT_PRIOR,
    DEFAULT_BETA,
    DRIFT_THRESHOLD,
    MODE_PROFILES,
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_domain_mode(self):
        assert len(DomainMode) == 4
        assert DomainMode.CODE.value == "code"

    def test_drift_action(self):
        assert len(DriftAction) == 3

    def test_drift_phase(self):
        assert len(DriftPhase) == 3


# ---------------------------------------------------------------------------
# Observation
# ---------------------------------------------------------------------------

class TestObservation:
    def test_defaults(self):
        o = Observation()
        assert not o.has_code_blocks
        assert not o.requests_story

    def test_to_dict(self):
        o = Observation(has_code_blocks=True)
        d = o.to_dict()
        assert d["has_code_blocks"] is True
        assert d["requests_story"] is False

    def test_roundtrip(self):
        o = Observation(requests_citations=True, analytical_language=True)
        o2 = Observation.from_dict(o.to_dict())
        assert o2.requests_citations is True
        assert o2.analytical_language is True


# ---------------------------------------------------------------------------
# ModePosterior
# ---------------------------------------------------------------------------

class TestModePosterior:
    def test_uniform(self):
        p = ModePosterior.uniform()
        assert abs(p.code - 0.25) < 1e-9
        assert abs(p.confidence - 0.25) < 1e-9

    def test_peaked(self):
        p = ModePosterior.peaked(DomainMode.CODE, 0.8)
        assert p.dominant_mode == DomainMode.CODE
        assert abs(p.code - 0.8) < 1e-9
        assert abs(p.confidence - 0.8) < 1e-9

    def test_as_dict(self):
        p = ModePosterior.peaked(DomainMode.FICTION)
        d = p.as_dict()
        assert DomainMode.FICTION in d
        assert d[DomainMode.FICTION] > 0.5

    def test_to_dict(self):
        p = ModePosterior(code=0.5, research=0.3, fiction=0.1, task=0.1)
        d = p.to_dict()
        assert "code" in d
        assert d["code"] == 0.5

    def test_roundtrip(self):
        p = ModePosterior(code=0.6, research=0.2, fiction=0.1, task=0.1)
        p2 = ModePosterior.from_dict(p.to_dict())
        assert abs(p2.code - 0.6) < 1e-6


# ---------------------------------------------------------------------------
# compute_mode_features
# ---------------------------------------------------------------------------

class TestFeatures:
    def test_code_features(self):
        o = Observation(has_code_blocks=True, requests_implementation=True)
        assert compute_mode_features(o, DomainMode.CODE) == 2.0

    def test_research_features(self):
        o = Observation(requests_citations=True, mentions_sources=True)
        assert compute_mode_features(o, DomainMode.RESEARCH) == 2.0

    def test_fiction_features(self):
        o = Observation(creative_prompt=True, narrative_language=True, requests_story=True)
        assert compute_mode_features(o, DomainMode.FICTION) == 3.0

    def test_task_fallback(self):
        o = Observation()
        assert compute_mode_features(o, DomainMode.TASK) == 0.0

    def test_no_features(self):
        o = Observation()
        assert compute_mode_features(o, DomainMode.CODE) == 0.0


# ---------------------------------------------------------------------------
# update_mode_posterior
# ---------------------------------------------------------------------------

class TestUpdatePosterior:
    def test_code_observation(self):
        prior = {m: 0.25 for m in DomainMode}
        o = Observation(has_code_blocks=True, requests_implementation=True,
                        mentions_programming_language=True)
        post = update_mode_posterior(prior, o)
        assert post[DomainMode.CODE] > post[DomainMode.RESEARCH]
        assert post[DomainMode.CODE] > post[DomainMode.FICTION]

    def test_fiction_observation(self):
        prior = {m: 0.25 for m in DomainMode}
        o = Observation(creative_prompt=True, requests_story=True, narrative_language=True)
        post = update_mode_posterior(prior, o)
        assert post[DomainMode.FICTION] > post[DomainMode.CODE]

    def test_sums_to_one(self):
        prior = {m: 0.25 for m in DomainMode}
        o = Observation(has_code_blocks=True)
        post = update_mode_posterior(prior, o)
        assert abs(sum(post.values()) - 1.0) < 1e-9

    def test_neutral_observation(self):
        prior = {m: 0.25 for m in DomainMode}
        o = Observation()
        post = update_mode_posterior(prior, o)
        # All features 0 → all get exp(0)=1 → stays uniform
        for m in DomainMode:
            assert abs(post[m] - 0.25) < 1e-9

    def test_beta_sensitivity(self):
        prior = {m: 0.25 for m in DomainMode}
        o = Observation(has_code_blocks=True)
        low_beta = update_mode_posterior(prior, o, beta=0.1)
        high_beta = update_mode_posterior(prior, o, beta=5.0)
        assert high_beta[DomainMode.CODE] > low_beta[DomainMode.CODE]


# ---------------------------------------------------------------------------
# compute_drift
# ---------------------------------------------------------------------------

class TestDrift:
    def test_uniform_distribution(self):
        # dot(uniform, uniform) = 4 * 0.25^2 = 0.25, drift = 0.75
        d = {m: 0.25 for m in DomainMode}
        assert abs(compute_drift(d, d) - 0.75) < 1e-9

    def test_peaked_same(self):
        # dot([0.7,0.1,0.1,0.1],[0.7,0.1,0.1,0.1]) = 0.49+0.03 = 0.52
        d = {DomainMode.CODE: 0.7, DomainMode.RESEARCH: 0.1,
             DomainMode.FICTION: 0.1, DomainMode.TASK: 0.1}
        drift = compute_drift(d, d)
        assert drift < 0.5  # Same dist → lower drift than opposite

    def test_opposite(self):
        a = {DomainMode.CODE: 1.0, DomainMode.RESEARCH: 0.0,
             DomainMode.FICTION: 0.0, DomainMode.TASK: 0.0}
        b = {DomainMode.CODE: 0.0, DomainMode.RESEARCH: 0.0,
             DomainMode.FICTION: 1.0, DomainMode.TASK: 0.0}
        drift = compute_drift(a, b)
        assert abs(drift - 1.0) < 1e-9

    def test_partial(self):
        a = {m: 0.25 for m in DomainMode}
        b = {DomainMode.CODE: 0.7, DomainMode.RESEARCH: 0.1,
             DomainMode.FICTION: 0.1, DomainMode.TASK: 0.1}
        drift = compute_drift(a, b)
        assert 0 < drift < 1


# ---------------------------------------------------------------------------
# check_mode_drift
# ---------------------------------------------------------------------------

class TestCheckDrift:
    def test_no_drift_peaked(self):
        d = {DomainMode.CODE: 0.9, DomainMode.RESEARCH: 0.03,
             DomainMode.FICTION: 0.04, DomainMode.TASK: 0.03}
        # dot product with self is high enough that drift < threshold
        assert check_mode_drift(d, d, DriftPhase.LATE) is None

    def test_drift_early_no_alert(self):
        initial = {DomainMode.CODE: 0.7, DomainMode.RESEARCH: 0.1,
                   DomainMode.FICTION: 0.1, DomainMode.TASK: 0.1}
        current = {DomainMode.CODE: 0.1, DomainMode.RESEARCH: 0.1,
                   DomainMode.FICTION: 0.7, DomainMode.TASK: 0.1}
        alert = check_mode_drift(current, initial, DriftPhase.EARLY)
        assert alert is None

    def test_drift_mid_warns(self):
        initial = {DomainMode.CODE: 0.7, DomainMode.RESEARCH: 0.1,
                   DomainMode.FICTION: 0.1, DomainMode.TASK: 0.1}
        current = {DomainMode.CODE: 0.1, DomainMode.RESEARCH: 0.1,
                   DomainMode.FICTION: 0.7, DomainMode.TASK: 0.1}
        alert = check_mode_drift(current, initial, DriftPhase.MID)
        assert alert is not None
        assert alert.action == DriftAction.WARN

    def test_drift_late_blocks(self):
        initial = {DomainMode.CODE: 0.7, DomainMode.RESEARCH: 0.1,
                   DomainMode.FICTION: 0.1, DomainMode.TASK: 0.1}
        current = {DomainMode.CODE: 0.1, DomainMode.RESEARCH: 0.1,
                   DomainMode.FICTION: 0.7, DomainMode.TASK: 0.1}
        alert = check_mode_drift(current, initial, DriftPhase.LATE)
        assert alert is not None
        assert alert.action == DriftAction.BLOCK
        assert alert.initial_mode == DomainMode.CODE
        assert alert.current_mode == DomainMode.FICTION


# ---------------------------------------------------------------------------
# DriftAlert
# ---------------------------------------------------------------------------

class TestDriftAlert:
    def test_create(self):
        a = DriftAlert(
            drift_score=0.5, initial_mode=DomainMode.CODE,
            current_mode=DomainMode.FICTION, action=DriftAction.WARN,
            phase=DriftPhase.MID,
        )
        assert a.ts

    def test_roundtrip(self):
        a = DriftAlert(
            drift_score=0.5, initial_mode=DomainMode.CODE,
            current_mode=DomainMode.RESEARCH, action=DriftAction.BLOCK,
            phase=DriftPhase.LATE,
        )
        d = a.to_dict()
        a2 = DriftAlert.from_dict(d)
        assert a2.initial_mode == DomainMode.CODE
        assert a2.action == DriftAction.BLOCK


# ---------------------------------------------------------------------------
# ModeState
# ---------------------------------------------------------------------------

class TestModeState:
    def test_create(self):
        s = ModeState(run_id="r1")
        assert s.observation_count == 0
        assert s.active_profile == "task"

    def test_to_dict(self):
        s = ModeState(run_id="r1")
        d = s.to_dict()
        assert d["run_id"] == "r1"
        assert "dominant_mode" in d
        assert "drift" in d

    def test_roundtrip(self):
        s = ModeState(run_id="r1", active_profile="code", observation_count=5)
        d = s.to_dict()
        s2 = ModeState.from_dict(d)
        assert s2.run_id == "r1"
        assert s2.active_profile == "code"


# ---------------------------------------------------------------------------
# get_mode_profile
# ---------------------------------------------------------------------------

class TestModeProfiles:
    def test_code_profile(self):
        p = get_mode_profile(DomainMode.CODE)
        assert "tests" in p["verification_focus"]
        assert p["late_novelty_penalty"] == 2.0

    def test_fiction_profile(self):
        p = get_mode_profile(DomainMode.FICTION)
        assert "continuity" in p["verification_focus"]
        assert p["late_novelty_penalty"] == 0.5

    def test_research_profile(self):
        p = get_mode_profile(DomainMode.RESEARCH)
        assert "citations" in p["verification_focus"]

    def test_task_profile(self):
        p = get_mode_profile(DomainMode.TASK)
        assert "completeness" in p["verification_focus"]

    def test_all_modes_have_profiles(self):
        for m in DomainMode:
            assert get_mode_profile(m) is not None


# ---------------------------------------------------------------------------
# observe_and_update
# ---------------------------------------------------------------------------

class TestObserveAndUpdate:
    def test_code_observation(self):
        state = ModeState(run_id="r1")
        o = Observation(has_code_blocks=True, requests_implementation=True)
        alert = observe_and_update(state, o)
        assert alert is None
        assert state.observation_count == 1
        assert state.current_posterior.code > 0.25

    def test_drift_alert_late(self):
        state = ModeState(
            run_id="r1",
            initial_posterior=ModePosterior.peaked(DomainMode.CODE, 0.8),
            current_posterior=ModePosterior.peaked(DomainMode.CODE, 0.8),
        )
        # Strong fiction observation in late phase
        o = Observation(creative_prompt=True, narrative_language=True,
                        requests_story=True, character_names=True)
        alert = observe_and_update(state, o, phase=DriftPhase.LATE)
        assert alert is not None
        assert alert.action == DriftAction.BLOCK

    def test_profile_updates(self):
        state = ModeState(run_id="r1")
        o = Observation(requests_citations=True, mentions_sources=True,
                        analytical_language=True, asks_factual_questions=True)
        observe_and_update(state, o)
        assert state.active_profile == "research"


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class TestStore:
    def test_save_load(self, tmp_path):
        store = ModeDetectionStore(governor_dir=tmp_path)
        state = ModeState(run_id="r1")
        o = Observation(has_code_blocks=True)
        observe_and_update(state, o)
        store.save(state)
        loaded = store.load("r1")
        assert loaded is not None
        assert loaded.observation_count == 1

    def test_list_runs(self, tmp_path):
        store = ModeDetectionStore(governor_dir=tmp_path)
        store.save(ModeState(run_id="a"))
        store.save(ModeState(run_id="b"))
        assert "a" in store.list_runs()
        assert "b" in store.list_runs()

    def test_load_missing(self, tmp_path):
        store = ModeDetectionStore(governor_dir=tmp_path)
        assert store.load("nope") is None

    def test_default_dir(self):
        store = ModeDetectionStore()
        assert store.mode_dir == Path(".governor") / "mode_detection"


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents:
    def test_create(self):
        e = make_mode_event("mode_update", "r1", {"mode": "code"})
        assert e["type"] == "mode_detection"
        assert e["ts"]

    def test_minimal(self):
        e = make_mode_event("detect")
        assert e["details"] == {}


# ---------------------------------------------------------------------------
# Golden schemas
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_posterior_schema(self):
        p = ModePosterior.peaked(DomainMode.CODE)
        d = p.to_dict()
        assert {"code", "research", "fiction", "task"} <= set(d.keys())

    def test_alert_schema(self):
        a = DriftAlert(0.5, DomainMode.CODE, DomainMode.FICTION,
                       DriftAction.WARN, DriftPhase.MID)
        d = a.to_dict()
        assert {"drift_score", "initial_mode", "current_mode", "action", "phase", "ts"} <= set(d.keys())

    def test_state_schema(self):
        s = ModeState(run_id="r1")
        d = s.to_dict()
        assert {"run_id", "initial_posterior", "current_posterior",
                "observation_count", "alerts", "active_profile",
                "dominant_mode", "drift"} <= set(d.keys())


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        store = ModeDetectionStore(governor_dir=tmp_path)
        state = ModeState(
            run_id="lifecycle1",
            initial_posterior=ModePosterior.peaked(DomainMode.CODE, 0.7),
            current_posterior=ModePosterior.peaked(DomainMode.CODE, 0.7),
        )

        # Several code observations
        for _ in range(3):
            observe_and_update(state, Observation(has_code_blocks=True))

        assert state.current_posterior.dominant_mode == DomainMode.CODE

        # Fiction drift in late phase
        alert = observe_and_update(
            state,
            Observation(creative_prompt=True, requests_story=True,
                        narrative_language=True, character_names=True),
            phase=DriftPhase.LATE,
        )
        # May or may not trigger depending on accumulated posterior
        store.save(state)
        loaded = store.load("lifecycle1")
        assert loaded is not None
        assert loaded.observation_count == 4


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_drift_threshold_positive(self):
        assert DRIFT_THRESHOLD > 0

    def test_default_prior_sums(self):
        assert abs(sum(DEFAULT_PRIOR.values()) - 1.0) < 1e-9

    def test_all_profiles_present(self):
        for mode in DomainMode:
            assert mode.value in MODE_PROFILES

    def test_default_beta_positive(self):
        assert DEFAULT_BETA > 0
