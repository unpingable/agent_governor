# SPDX-License-Identifier: Apache-2.0
"""Tests for the fenced substrate-validation entrypoint (`harness/validate_bwrap_substrate.py`).

Scope (per the operator pass in `docs/playbooks/next-gate-selection-review.md`): these tests
cover **parser / recording / refusal behaviour only**, on **synthetic inputs and injected
fakes**. They are **NOT live testimony**: a green run here proves the entrypoint's record
assembly and its refusal logic, NOT that any bwrap cage contained anything. No real cage is
built, no actor is run, and `confirms_isolation=True` is never produced — it is a hard error.
"""

from __future__ import annotations

import json

import pytest

from harness.bwrap_cage import (
    BWRAP_BASE_ARGS,
    ORDERED_FACT_IDS,
    CageRunAttestation,
    FactWitness,
    HostSupport,
    assess_host,
)
from harness.cage import SCOPE_LIVE, SCOPE_NONE, CageAttestation
from harness import validate_bwrap_substrate as V


# --------------------------------------------------------------------------- #
# Synthetic builders (lab substrate — NOT live testimony).
# --------------------------------------------------------------------------- #


def _ok_host() -> HostSupport:
    return assess_host(is_linux=True, bwrap_present=True, userns_ok=True,
                       seccomp_supported=True, cage_smoke_ok=True)


def _bad_host() -> HostSupport:
    return assess_host(is_linux=True, bwrap_present=True, userns_ok=True,
                       seccomp_supported=True, cage_smoke_ok=False)


def _witnesses(true_facts: set[str]) -> tuple[FactWitness, ...]:
    return tuple(
        FactWitness(f, f, witnessed=(f in true_facts), method="property_holds")
        for f in ORDERED_FACT_IDS
    )


def _run_attestation(
    *, host: HostSupport, witnessed: set[str], confirms: bool = False
) -> CageRunAttestation:
    att = CageAttestation(
        backend_id="bwrap-cage.v0",
        confirms_isolation=confirms,
        scope=SCOPE_LIVE if confirms else SCOPE_NONE,
        notes="synthetic",
    )
    wits = _witnesses(witnessed) if host.ok else ()
    return CageRunAttestation("bwrap-cage.v0", "run-x", host, wits, att)


def _substrate() -> V.SubstrateFacts:
    return V.SubstrateFacts(
        host_id="lab-host", host_class="vm", kernel="Linux lab 6.8 x86_64",
        bwrap_version="bubblewrap 0.8.0", userns_available=True, seccomp_available=True,
        nested_sandbox="no", nested_signals=(), audit_store_path="/tmp/audit",
    )


class FakeCage:
    """Injected cage: returns a canned attestation, runs nothing."""

    def __init__(self, attestation: CageRunAttestation):
        self._att = attestation

    def evaluate(self, *, run_id: str = "preflight") -> CageRunAttestation:
        return CageRunAttestation(
            self._att.backend_id, run_id, self._att.host_support,
            self._att.witnesses, self._att.attestation,
        )


# --------------------------------------------------------------------------- #
# classify_outcome — the refusal logic.
# --------------------------------------------------------------------------- #


def test_confirms_isolation_true_is_a_hard_refusal():
    # C11 must force refusal: a live-admissible verdict is never a valid outcome.
    with pytest.raises(V.SubstrateValidationRefused):
        V.classify_outcome(confirms_isolation=True, host_ok=True,
                           witnessed_fact_ids=frozenset(ORDERED_FACT_IDS))


def test_host_unsupported_classifies_as_host_refusal():
    out = V.classify_outcome(confirms_isolation=False, host_ok=False,
                             witnessed_fact_ids=frozenset())
    assert out == V.OUTCOME_HOST_UNSUPPORTED


def test_c1_c10_witnessed_c11_absent_is_successful_refusal_partial():
    facts = frozenset(f"C{i}" for i in range(1, 11))  # C1..C10, no C11
    out = V.classify_outcome(confirms_isolation=False, host_ok=True,
                             witnessed_fact_ids=facts)
    assert out == V.OUTCOME_SUCCESSFUL_REFUSAL_PARTIAL


def test_partial_c1_c10_is_refused_incomplete():
    facts = frozenset({"C1", "C2", "C3"})  # missing several
    out = V.classify_outcome(confirms_isolation=False, host_ok=True,
                             witnessed_fact_ids=facts)
    assert out == V.OUTCOME_REFUSED_INCOMPLETE


# --------------------------------------------------------------------------- #
# build_validation_record — the recorder.
# --------------------------------------------------------------------------- #


def test_record_shape_and_not_live_testimony_marker():
    facts = {f"C{i}" for i in range(1, 11)}
    rec = V.build_validation_record(
        run_id="run-1", substrate=_substrate(),
        run_attestation=_run_attestation(host=_ok_host(), witnessed=facts),
        detection_transcript=[{"cmd": ["uname", "-a"], "stdout": "Linux"}],
        probe_transcript=[{"fact_id": "cage_smoke", "returncode": 0}],
    )
    assert rec["record_kind"] == V.RECORD_KIND
    assert rec["run_id"] == "run-1"
    assert "not live testimony" in rec["not_live_testimony"].lower()
    # substrate facts are declared
    for key in ("host_id", "host_class", "kernel", "bwrap_version",
                "userns_available", "seccomp_available", "nested_sandbox",
                "audit_store_path"):
        assert key in rec["substrate"]
    # transcript carried
    assert rec["commands"]["detection"] and rec["commands"]["probes"]
    # decision: refusal, never admission
    dec = rec["decision"]
    assert dec["confirms_isolation"] is False
    assert dec["live_admission"] is False
    assert dec["mandatory_c11_refusal"] is True
    assert dec["c11_witnessed"] is False
    assert dec["outcome"] == V.OUTCOME_SUCCESSFUL_REFUSAL_PARTIAL
    assert "C11" in dec["unwitnessed_facts"]
    assert "C1" in dec["witnessed_facts"]


def test_record_builder_refuses_a_live_admission_attestation():
    # Defensive: a confirms_isolation=True attestation must never be recorded.
    with pytest.raises(V.SubstrateValidationRefused):
        V.build_validation_record(
            run_id="run-2", substrate=_substrate(),
            run_attestation=_run_attestation(
                host=_ok_host(), witnessed=set(ORDERED_FACT_IDS), confirms=True
            ),
            detection_transcript=[], probe_transcript=[],
        )


def test_host_unsupported_record_outcome():
    rec = V.build_validation_record(
        run_id="run-3", substrate=_substrate(),
        run_attestation=_run_attestation(host=_bad_host(), witnessed=set()),
        detection_transcript=[], probe_transcript=[{"fact_id": "cage_smoke", "returncode": 1}],
    )
    assert rec["decision"]["outcome"] == V.OUTCOME_HOST_UNSUPPORTED
    assert rec["decision"]["host_supported"] is False


# --------------------------------------------------------------------------- #
# probe argv builders — exact commands, sourced from the backend's constants.
# --------------------------------------------------------------------------- #


def test_probe_argv_uses_backend_base_args():
    argv = V.probe_argv("C1", "bwrap")
    assert argv is not None
    assert argv[0] == "bwrap"
    assert tuple(argv[1:1 + len(BWRAP_BASE_ARGS)]) == BWRAP_BASE_ARGS
    assert "--" in argv


def test_probe_argv_none_for_non_inner_facts():
    assert V.probe_argv("C9", "bwrap") is None   # prober-lifecycle guarantee
    assert V.probe_argv("C11", "bwrap") is None  # unwitnessable in v0


def test_smoke_argv_is_true_command():
    assert V.smoke_argv("bwrap")[-1] == "/bin/true"


# --------------------------------------------------------------------------- #
# run_validation — orchestration, with detection + probes stubbed (no subprocess).
# --------------------------------------------------------------------------- #


def _stub_io(monkeypatch, *, host_ok: bool):
    monkeypatch.setattr(
        V, "detect_substrate",
        lambda *, host_id, host_class, transcript: _substrate(),
    )
    monkeypatch.setattr(
        V, "capture_probe_transcript",
        lambda host_ok_arg: [{"fact_id": "cage_smoke", "returncode": 0 if host_ok else 1}],
    )


def test_run_validation_writes_exactly_one_record(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _stub_io(monkeypatch, host_ok=True)
    facts = {f"C{i}" for i in range(1, 11)}
    cage = FakeCage(_run_attestation(host=_ok_host(), witnessed=facts))

    record, path = V.run_validation(run_id="run-live-sub", host_class="vm", cage=cage)

    assert record["decision"]["outcome"] == V.OUTCOME_SUCCESSFUL_REFUSAL_PARTIAL
    assert record["decision"]["live_admission"] is False
    assert path.exists()
    assert path.name == V.RECORD_FILENAME
    # exactly one record file in the run dir
    siblings = list(path.parent.glob("*.json"))
    assert siblings == [path]
    # persisted content round-trips
    on_disk = json.loads(path.read_text())
    assert on_disk["record_kind"] == V.RECORD_KIND
    assert on_disk["run_id"] == "run-live-sub"


def test_run_validation_host_unsupported_still_writes_a_refusal_record(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _stub_io(monkeypatch, host_ok=False)
    cage = FakeCage(_run_attestation(host=_bad_host(), witnessed=set()))

    record, path = V.run_validation(run_id="run-nested", cage=cage)

    assert record["decision"]["outcome"] == V.OUTCOME_HOST_UNSUPPORTED
    assert path.exists()


def test_run_validation_refuses_a_live_admission_and_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    _stub_io(monkeypatch, host_ok=True)
    cage = FakeCage(
        _run_attestation(host=_ok_host(), witnessed=set(ORDERED_FACT_IDS), confirms=True)
    )
    with pytest.raises(V.SubstrateValidationRefused):
        V.run_validation(run_id="run-should-not-exist", cage=cage)
    # no record written for a would-be admission
    run_root = tmp_path / "agent-gov" / "harness-runs"
    written = list(run_root.rglob("*.json")) if run_root.exists() else []
    assert written == []
