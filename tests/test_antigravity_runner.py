# SPDX-License-Identifier: Apache-2.0
"""Slice 5 / AGY-1 — fenced Antigravity behavioral probes (prove the cage first).

The through-line: AG never runs agy uncaged, and every cage escape is fail-closed.
The negative tests are the point — a write escaping scope or the network being
reachable when denied means the CAGE failed, and the verdict must say so, never
launder it into "observed success". All logic is exercised through injected runners;
no live agy is invoked.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.runtime.adapters.antigravity_probe import ProbeExec
from governor.runtime.adapters.antigravity_runner import (
    AGY1_PROBES,
    HEADLESS_PROBE,
    NETWORK_PROBE,
    WRITE_PROBE,
    BehaviorProbeReceipt,
    OuterCage,
    ProbeObservation,
    build_bwrap_argv,
    cage_preflight,
    classify_probe,
    run_behavior_probe,
    run_live_probes,
)

_REPO = Path(__file__).resolve().parents[1]
_CAGE = OuterCage(kind="bwrap", network="denied", write_scope=("/work/scratch",))


def _runner(result_for):
    def run(argv):
        return result_for(list(argv))

    return run


def _fixed(exec_):
    return _runner(lambda argv: exec_)


# --- cage argv construction ------------------------------------------------- #
def test_bwrap_argv_denies_network_and_fences_writes():
    argv = build_bwrap_argv(_CAGE, ["agy", "-p", "hi"])
    assert "--unshare-net" in argv  # network denied → unshared
    assert argv[argv.index("--bind") + 1] == "/work/scratch"  # writable area bound
    assert argv[-3:] == ["agy", "-p", "hi"]
    # forbidden paths are enforced by ABSENCE — never bound in.
    assert "~/.ssh" not in argv and "/home" not in argv


def test_bwrap_argv_allows_network_only_when_ration_says_so():
    open_cage = OuterCage(kind="bwrap", network="allowed", write_scope=())
    assert "--unshare-net" not in build_bwrap_argv(open_cage, ["/bin/true"])


# --- docker cage backend (works where bwrap can't) -------------------------- #
def test_docker_argv_denies_network_and_read_only_root():
    from governor.runtime.adapters.antigravity_runner import build_docker_argv

    argv = build_docker_argv(OuterCage(kind="docker", network="denied", write_scope=("/work",)), ["agy", "-p", "x"])
    assert "--network" in argv and argv[argv.index("--network") + 1] == "none"
    assert "--read-only" in argv  # immutable root; only the bound scope is writable
    assert "-v" in argv and "/work:/work:rw" in argv
    # forbidden paths / $HOME are enforced by ABSENCE — never mounted.
    assert not any(h in " ".join(argv) for h in ("/home", ".ssh", ".gemini"))
    assert argv[-3:] == ["agy", "-p", "x"]


def test_docker_argv_no_network_flag_when_allowed():
    from governor.runtime.adapters.antigravity_runner import build_docker_argv

    argv = build_docker_argv(OuterCage(kind="docker", network="allowed", write_scope=()), ["/bin/true"])
    assert "--network" not in argv


def test_build_cage_argv_dispatches_by_kind():
    from governor.runtime.adapters.antigravity_runner import build_cage_argv

    assert build_cage_argv(OuterCage(kind="bwrap", write_scope=()), ["/bin/true"])[0] == "bwrap"
    assert build_cage_argv(OuterCage(kind="docker", write_scope=()), ["/bin/true"])[0] == "docker"
    with pytest.raises(ValueError):
        build_cage_argv(OuterCage(kind="porter", write_scope=()), ["/bin/true"])  # driven via porter


def test_docker_cage_preflight_available_via_injected_runner():
    docker_cage = OuterCage(kind="docker", network="denied", write_scope=())
    r = cage_preflight(_fixed(ProbeExec(ran=True, exit_code=0)), cage=docker_cage)
    assert r.available is True


# --- cage preflight: prove the cage before feeding it work ------------------ #
def test_preflight_unavailable_when_bwrap_cannot_namespace():
    r = cage_preflight(_fixed(ProbeExec(ran=True, exit_code=1, stderr="bwrap: setting up uid map: Permission denied")))
    assert r.available is False
    assert "uid map" in r.reason


def test_preflight_available_when_trivial_command_exits_zero():
    assert cage_preflight(_fixed(ProbeExec(ran=True, exit_code=0))).available is True


def test_live_probes_refuse_when_cage_unavailable_and_run_no_agy():
    calls = []

    def run(argv):
        calls.append(argv)
        return ProbeExec(ran=True, exit_code=1, stderr="bwrap: setting up uid map: Permission denied")

    receipts = run_live_probes(run, _CAGE, opt_in=True)
    assert len(receipts) == 1
    assert receipts[0].verdict == "cage_unavailable"
    # Only the preflight /bin/true was attempted — NO agy invocation.
    assert all("agy" not in argv for argv in calls)
    assert any("refused to run agy uncaged" in n for n in receipts[0].notes)


def test_live_probes_require_explicit_opt_in():
    with pytest.raises(ValueError):
        run_live_probes(_fixed(ProbeExec(ran=True, exit_code=0)), _CAGE, opt_in=False)


# --- verdict logic: the negatives that matter ------------------------------- #
def _obs(**kw):
    base = dict(ran=True, exit_status=0, stdout="", stderr="")
    base.update(kw)
    return ProbeObservation(**base)


def test_absent_binary_is_not_supported():
    v, _ = classify_probe(HEADLESS_PROBE, _CAGE, _obs(ran=False))
    assert v == "not_supported"


def test_auth_prompt_is_held():
    v, notes = classify_probe(HEADLESS_PROBE, _CAGE, _obs(stdout="Please sign in to continue"))
    assert v == "held"


def test_timeout_preserves_and_reports():
    v, notes = classify_probe(HEADLESS_PROBE, _CAGE, _obs(timed_out=True))
    assert v == "timed_out"
    assert any("transcript preserved" in n for n in notes)


def test_write_escaping_scope_fails_closed():
    v, notes = classify_probe(WRITE_PROBE, _CAGE, _obs(observed_writes=("/etc/passwd",)))
    assert v == "blocked"
    assert any("FAIL CLOSED" in n for n in notes)


def test_write_inside_scope_is_fine():
    v, _ = classify_probe(WRITE_PROBE, _CAGE, _obs(observed_writes=("/work/scratch/agy-write-probe.txt",)))
    assert v == "observed"


def test_network_reachable_when_denied_fails_closed():
    v, notes = classify_probe(NETWORK_PROBE, _CAGE, _obs(network_reachable=True))
    assert v == "blocked"
    assert any("cage escape" in n for n in notes)


def test_nonzero_exit_captured_not_laundered():
    v, notes = classify_probe(HEADLESS_PROBE, _CAGE, _obs(exit_status=3))
    assert v == "blocked"
    assert any("nonzero exit 3" in n for n in notes)


def test_token_mismatch_is_observed_but_unsuccessful():
    v, _ = classify_probe(HEADLESS_PROBE, _CAGE, _obs(stdout="here you go: maybe"))
    assert v == "observed_unsuccessful"


def test_token_match_is_observed():
    v, _ = classify_probe(HEADLESS_PROBE, _CAGE, _obs(stdout="READY"))
    assert v == "observed"


# --- run_behavior_probe wiring (injected runner, no live agy) --------------- #
def test_run_behavior_probe_builds_a_receipt():
    r = run_behavior_probe(
        HEADLESS_PROBE, _CAGE,
        runner=_fixed(ProbeExec(ran=True, exit_code=0, stdout="READY")),
        agy_version="1.0.9",
    )
    assert r.verdict == "observed"
    assert r.command_shape == ("agy", "-p", "<redacted>")  # prompt redacted
    assert r.stdout_digest and r.stdout_digest.startswith("sha256:")
    assert r.authority == "none"


# --- receipt invariants ----------------------------------------------------- #
def test_receipt_confers_no_authority_and_is_behavioral():
    with pytest.raises(ValueError):
        BehaviorProbeReceipt(probe_id="x", verdict="observed", outer_cage={}, live=True, authority="granted")
    with pytest.raises(ValueError):
        BehaviorProbeReceipt(probe_id="x", verdict="admitted", outer_cage={}, live=True)  # not a probe verdict


def test_three_named_probes_present():
    assert {p.probe_id for p in AGY1_PROBES} == {"agy-1-headless-ready", "agy-1-write", "agy-1-network"}


# --- import boundary: AGY-1 is measurement, not dispatch/authority ---------- #
def test_runner_imports_no_dispatch_or_registry_authority():
    src = (_REPO / "src/governor/runtime/adapters/antigravity_runner.py").read_text()
    for line in src.splitlines():
        s = line.strip()
        if s.startswith(("import ", "from ")):
            assert "provider_registry" not in s
            assert "governed_dispatch" not in s


# --- Porter-backed cage: AG consumes honest porter.record.v0 ---------------- #
_PORTER_CAGE = OuterCage(kind="porter", network="denied", write_scope=("/work",))


def _porter_record(outcome, *, exit_code=None, refusal_reason=None, run_id="r1"):
    steps = []
    if exit_code is not None:
        steps = [{"kind": "exec", "exit_code_observed": True, "exit_code": exit_code}]
    return {
        "schema": "porter.record.v0",
        "run_id": run_id,
        "outcome": outcome,
        "steps": steps,
        "refusal_reason": refusal_reason,
    }


def _porter(record):
    def run(*, target, command, **kw):
        return record

    return run


def test_porter_completed_run_is_observed():
    from governor.runtime.adapters.antigravity_runner import run_probe_via_porter

    r = run_probe_via_porter(
        NETWORK_PROBE, _PORTER_CAGE,
        porter_run=_porter(_porter_record("completed", exit_code=0)),
        target="recipe:/recipes/agy-docker",
    )
    assert r.verdict == "observed"
    assert r.outer_cage["kind"] == "porter"
    assert any("porter outcome=completed" in n for n in r.notes)


def test_porter_refused_is_fail_closed_blocked():
    # Porter never coerces an unknown exit — refused stays refused, AG blocks.
    from governor.runtime.adapters.antigravity_runner import run_probe_via_porter

    r = run_probe_via_porter(
        WRITE_PROBE, _PORTER_CAGE,
        porter_run=_porter(_porter_record("refused", refusal_reason="unknown exit code")),
        target="recipe:/recipes/agy-docker",
    )
    assert r.verdict == "blocked"
    assert any("porter refused" in n for n in r.notes)


def test_porter_courier_failure_is_not_supported():
    from governor.runtime.adapters.antigravity_runner import run_probe_via_porter

    r = run_probe_via_porter(
        WRITE_PROBE, _PORTER_CAGE,
        porter_run=_porter(_porter_record("porter_failed", refusal_reason="no substrate")),
        target="recipe:/recipes/agy-docker",
    )
    assert r.verdict == "not_supported"


def test_porter_run_failed_nonzero_is_blocked_not_laundered():
    from governor.runtime.adapters.antigravity_runner import run_probe_via_porter

    r = run_probe_via_porter(
        WRITE_PROBE, _PORTER_CAGE,
        porter_run=_porter(_porter_record("run_failed", exit_code=3)),
        target="recipe:/recipes/agy-docker",
    )
    assert r.verdict == "blocked"
    assert r.exit_status == 3


def test_porter_seam_requires_porter_cage():
    from governor.runtime.adapters.antigravity_runner import run_probe_via_porter

    with pytest.raises(ValueError):
        run_probe_via_porter(
            WRITE_PROBE, _CAGE,  # a bwrap cage, not porter
            porter_run=_porter(_porter_record("completed", exit_code=0)),
            target="recipe:/x",
        )


# --- persisted live artifact is the honest refusal -------------------------- #
def test_persisted_behavior_artifact_is_the_caged_refusal():
    data = json.loads((_REPO / "docs/playbooks/antigravity-behavior-probe.v0.json").read_text())
    assert isinstance(data, list) and len(data) == 1
    rec = data[0]
    assert rec["verdict"] == "cage_unavailable"  # this host cannot cage → refused
    assert rec["authority"] == "none"
    assert rec["evidence_kind"] == "behavioral_probe"
    assert any("refused to run agy uncaged" in n for n in rec["notes"])


def test_persisted_docker_cage_attestation_is_honest():
    data = json.loads((_REPO / "docs/playbooks/antigravity-cage-docker.v0.json").read_text())
    assert data["evidence_kind"] == "cage_attestation"
    assert data["authority"] == "none"
    assert "no agy was run" in data["not_live_testimony"]
    facts = " ".join(data["witnessed_facts"])
    assert "network_denied" in facts and "write_fenced" in facts and "cage_available" in facts
    # agy behavior is explicitly NOT claimed — it stays gated.
    assert any("agy behavioral probes" in g for g in data["unwitnessed_or_gated"])
