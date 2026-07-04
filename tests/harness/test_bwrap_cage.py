# SPDX-License-Identifier: Apache-2.0
"""Tests for the bubblewrap real-cage backend (`harness/bwrap_cage.py`).

The acceptance criteria are about GATING + LOGIC + EVIDENCE, which are exercised
deterministically with an injected `FakeProber` (synthetic compatibility — never live
testimony). The real `BwrapProber` is smoke-checked + its v0 refuse-by-construction
(C11 unavailable) is pinned. Live witnessing is unavailable in this environment (bwrap
cannot establish a cage in the nested sandbox), so the real backend refuses — which is
itself the correct, witnessed-discipline behaviour.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from harness.bwrap_cage import (
    BWRAP_BASE_ARGS,
    METHOD_PROPERTY_HOLDS,
    METHOD_UNAVAILABLE,
    ORDERED_FACT_IDS,
    PROBE_SPECS,
    REQUIRED_FACT_IDS,
    BwrapCage,
    BwrapProber,
    CageRunAttestation,
    FactWitness,
    HostSupport,
    all_required_witnessed,
    assess_host,
    persist_run_attestation,
)
from harness.cage import (
    REFUSED_NO_ISOLATION_ATTESTED,
    SCOPE_LIVE,
    SCOPE_NONE,
    LiveAdmissionRequest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_FACTS = tuple(f"C{i}" for i in range(1, 12))


# --------------------------------------------------------------------------- #
# A synthetic prober (lab substrate — NOT live testimony).
# --------------------------------------------------------------------------- #


class FakeProber:
    def __init__(self, host: HostSupport, witnessed: dict[str, bool]):
        self._host = host
        self._witnessed = witnessed

    def host_support(self) -> HostSupport:
        return self._host

    def witness(self, fact_id: str) -> FactWitness:
        w = self._witnessed.get(fact_id, False)
        return FactWitness(fact_id, fact_id, witnessed=w, method=METHOD_PROPERTY_HOLDS)


def _ok_host() -> HostSupport:
    return assess_host(is_linux=True, bwrap_present=True, userns_ok=True,
                       seccomp_supported=True, cage_smoke_ok=True)


def _all_witnessed() -> dict[str, bool]:
    return {f: True for f in ORDERED_FACT_IDS}


# --------------------------------------------------------------------------- #
# Fact set.
# --------------------------------------------------------------------------- #


def test_fact_set_is_c1_through_c11_all_required():
    assert ORDERED_FACT_IDS == EXPECTED_FACTS
    assert REQUIRED_FACT_IDS == frozenset(EXPECTED_FACTS)


# --------------------------------------------------------------------------- #
# Host gate: refuse when bwrap missing / linux/userns/seccomp/cage unavailable.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "kw,reason_substr",
    [
        (dict(is_linux=False), "not Linux"),
        (dict(bwrap_present=False), "bwrap"),
        (dict(userns_ok=False), "user namespaces"),
        (dict(seccomp_supported=False), "seccomp"),
        (dict(cage_smoke_ok=False), "cage smoke"),
    ],
)
def test_host_gate_refuses_when_a_requirement_is_missing(kw, reason_substr):
    base = dict(is_linux=True, bwrap_present=True, userns_ok=True,
                seccomp_supported=True, cage_smoke_ok=True)
    base.update(kw)
    hs = assess_host(**base)
    assert hs.ok is False
    assert any(reason_substr in r for r in hs.reasons)


def test_host_gate_ok_only_when_everything_holds():
    assert _ok_host().ok is True


def test_unsupported_host_refuses_with_no_battery():
    bad = assess_host(is_linux=True, bwrap_present=False, userns_ok=True,
                      seccomp_supported=True, cage_smoke_ok=False)
    cage = BwrapCage(prober=FakeProber(bad, _all_witnessed()))
    run = cage.evaluate(run_id="r-host")
    assert run.confirms_isolation is False
    assert run.attestation.scope == SCOPE_NONE
    assert run.witnesses == ()  # battery never ran


# --------------------------------------------------------------------------- #
# Battery logic: full pass is the ONLY path to confirms_isolation=True.
# --------------------------------------------------------------------------- #


def test_full_battery_is_the_only_path_to_confirms_isolation():
    cage = BwrapCage(prober=FakeProber(_ok_host(), _all_witnessed()))
    run = cage.evaluate(run_id="r-ok")
    assert run.confirms_isolation is True
    assert run.attestation.scope == SCOPE_LIVE
    assert all_required_witnessed(run.witnesses) is True


@pytest.mark.parametrize("missing", EXPECTED_FACTS)
def test_any_single_missing_fact_prevents_confirms_isolation(missing):
    witnessed = _all_witnessed()
    witnessed[missing] = False  # one fact not witnessed
    cage = BwrapCage(prober=FakeProber(_ok_host(), witnessed))
    run = cage.evaluate(run_id="r-miss")
    assert run.confirms_isolation is False
    assert run.attestation.scope == SCOPE_NONE
    assert missing in run.missing_or_unwitnessed()


def test_all_required_witnessed_is_conjunctive():
    full = tuple(FactWitness(f, f, True, METHOD_PROPERTY_HOLDS) for f in ORDERED_FACT_IDS)
    assert all_required_witnessed(full) is True
    short = full[:-1]  # drop C11
    assert all_required_witnessed(short) is False


# --------------------------------------------------------------------------- #
# admit_live: refuse unless the battery passed (typed).
# --------------------------------------------------------------------------- #


def _req() -> LiveAdmissionRequest:
    return LiveAdmissionRequest(actor_kind="claude", handoff_id="h-1")


def test_admit_live_refuses_when_battery_incomplete_typed():
    witnessed = _all_witnessed()
    witnessed["C11"] = False
    cage = BwrapCage(prober=FakeProber(_ok_host(), witnessed))
    decision = cage.admit_live(_req())
    assert decision.admitted is False
    assert decision.refusal_code == REFUSED_NO_ISOLATION_ATTESTED


def test_admit_live_admitted_only_on_full_synthetic_pass():
    cage = BwrapCage(prober=FakeProber(_ok_host(), _all_witnessed()))
    decision = cage.admit_live(_req())
    # Synthetic substrate (FakeProber) — proves the admission LOGIC, not live containment.
    assert decision.admitted is True


# --------------------------------------------------------------------------- #
# Evidence: per-fact witnesses carried + persisted under the audit store.
# --------------------------------------------------------------------------- #


def test_attestation_carries_per_fact_witnesses():
    cage = BwrapCage(prober=FakeProber(_ok_host(), _all_witnessed()))
    run = cage.evaluate(run_id="r-ev")
    ev = run.to_evidence_dict()
    assert [w["fact_id"] for w in ev["witnesses"]] == list(EXPECTED_FACTS)
    assert ev["confirms_isolation"] is True
    assert ev["host_support"]["ok"] is True


def test_evidence_persists_under_audit_store_outside_ag(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    cage = BwrapCage(prober=FakeProber(_ok_host(), _all_witnessed()))
    run = cage.evaluate(run_id="run-123")
    path = persist_run_attestation(run)
    # Under the XDG harness audit store, outside the AG repo.
    assert path == tmp_path / "agent-gov" / "harness-runs" / "run-123" / "cage_attestation.json"
    assert REPO_ROOT not in path.resolve().parents
    data = json.loads(path.read_text())
    assert data["run_id"] == "run-123"
    assert len(data["witnesses"]) == 11


# --------------------------------------------------------------------------- #
# Probe specs: real bwrap shapes exist for the inner-command facts.
# --------------------------------------------------------------------------- #


def test_probe_specs_cover_inner_command_facts():
    assert set(PROBE_SPECS) == {"C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"}


def test_base_args_enforce_the_named_isolation_flags():
    base = " ".join(BWRAP_BASE_ARGS)
    assert "--unshare-all" in base  # C1/C2/C3
    assert "--clearenv" in base  # C8
    assert "--tmpfs" in base  # C5 single writable area
    assert "--ro-bind" in base  # C4 read-only input


def test_c1_probe_attempts_network_and_c4_attempts_ro_write():
    assert "/dev/tcp/" in " ".join(PROBE_SPECS["C1"].inner)
    assert "/usr/" in " ".join(PROBE_SPECS["C4"].inner)


# --------------------------------------------------------------------------- #
# Real prober: conservative; v0 cannot witness C11 (refuse by construction).
# --------------------------------------------------------------------------- #


def test_real_prober_host_support_returns_without_crashing():
    hs = BwrapProber().host_support()
    assert isinstance(hs, HostSupport)
    assert isinstance(hs.ok, bool)


def test_real_prober_never_witnesses_c11_in_v0():
    w = BwrapProber().witness("C11")
    assert w.witnessed is False
    assert w.method == METHOD_UNAVAILABLE


def test_real_backend_refuses_live_in_this_environment():
    """With the real prober, the v0 backend cannot mint confirms_isolation=True
    (C11 unavailable, and/or the cage cannot start here) → live admission refused."""
    decision = BwrapCage().admit_live(_req())
    assert decision.admitted is False


# --------------------------------------------------------------------------- #
# The backend runs NO actor.
# --------------------------------------------------------------------------- #


def test_backend_has_no_actor_invocation_surface():
    """Static AST scan (identifiers only, so the module's own *prose* doesn't trip it):
    bwrap_cage.py must not invoke an actor — no actor-runner identifier, no import of the
    actor harness, no `run`/`spawn`/`run_once` method. The only subprocess it runs is
    `bwrap` (the probe commands required to test the cage itself)."""
    src = (REPO_ROOT / "harness" / "bwrap_cage.py").read_text()
    tree = ast.parse(src)
    forbidden_ids = {
        "run_once", "run_actor", "invoke_actor", "spawn_actor",
        "offline_echo_actor", "run_once_under_cage",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in forbidden_ids:
            raise AssertionError(f"actor-invocation identifier in code: {node.id!r}")
        if isinstance(node, ast.Attribute) and node.attr in forbidden_ids:
            raise AssertionError(f"actor-invocation attribute in code: {node.attr!r}")
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in ("run", "spawn", "run_once", "run_actor", "invoke"), (
                f"backend must not define an actor-running method {node.name!r}"
            )
        if isinstance(node, ast.Import):
            for a in node.names:
                assert "actor_harness" not in a.name
        if isinstance(node, ast.ImportFrom):
            assert "actor_harness" not in (node.module or "")


def test_bwrap_cage_does_not_import_governor():
    src = (REPO_ROOT / "harness" / "bwrap_cage.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                assert not a.name.startswith("governor")
        elif isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("governor")


# --------------------------------------------------------------------------- #
# C5 root-seal — construction check (NOT live testimony).
#
# Real-substrate finding capable-vm-noble-001 (docs/playbooks/capable-vm-substrate-
# finding.md): bwrap's root `/` is a writable tmpfs by default, so the cage had TWO
# writable areas (/tmp + root /), violating C5. The fix seals the root with
# `--remount-ro /`. This test asserts the SEAL IS PRESENT IN THE CONFIG — it does not
# and cannot prove containment on a real host (that is what the capable-VM run does).
# --------------------------------------------------------------------------- #


def test_base_args_seal_the_container_root_for_c5():
    # `--remount-ro /` must be present, and must come AFTER the writable /tmp + the
    # ro-binds (bwrap applies mount ops in order; the remount seals the root last).
    args = list(BWRAP_BASE_ARGS)
    assert "--remount-ro" in args, "cage root is not sealed (C5 regression)"
    ri = args.index("--remount-ro")
    assert args[ri + 1] == "/", "--remount-ro must target the container root /"
    # /tmp stays the one declared writable area, mounted before the seal
    tmp_i = args.index("/tmp")
    assert tmp_i < ri, "the writable /tmp mount must precede the root seal"


def test_exactly_one_declared_writable_area_is_tmp():
    # C5 = "exactly one narrow writable area". The only writable mount declared is --tmpfs
    # /tmp; every other bound path is --ro-bind and the root is remounted read-only.
    args = BWRAP_BASE_ARGS
    tmpfs_targets = [args[i + 1] for i, a in enumerate(args) if a == "--tmpfs"]
    assert tmpfs_targets == ["/tmp"], f"expected one writable tmpfs (/tmp), got {tmpfs_targets}"
