# SPDX-License-Identifier: Apache-2.0
"""Slice 5 / AGY-0 — the Antigravity capability probe (recognition, not admission).

The probe recognizes the ``agy`` CLI surface from an injected runner. The tests that
matter most are the NEGATIVE ones: an absent binary must be ``not_supported`` (never
a crash), and anything not positively observed must be ``unknown`` (never assumed).
The result is compatibility evidence, structurally never live testimony.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.provider_descriptors import antigravity_cli_descriptor, claude_code_descriptor
from governor.provider_registry import ConformanceLevel, ProviderRegistry
from governor.runtime.adapters.antigravity_probe import (
    EVIDENCE_KIND,
    AntigravityProbeResult,
    ProbeExec,
    probe,
)

_REPO = Path(__file__).resolve().parents[1]

# Real `agy --help` prints usage to STDERR (Go flag CLI); the fixtures mirror that.
_HELP_STDERR = (
    "Usage of agy:\n"
    "  --model   Model for the current CLI session\n"
    "  -p        Short alias for --print\n"
    "  --print   Run a single prompt non-interactively and print the response\n"
    "  --sandbox Run in a sandbox with terminal restrictions enabled\n"
)


def _runner(mapping):
    """Build an injected runner from {argv_tuple: ProbeExec}."""

    def run(argv):
        return mapping.get(tuple(argv), ProbeExec(ran=False, exit_code=None))

    return run


def _live_like():
    return _runner(
        {
            ("agy", "--version"): ProbeExec(ran=True, exit_code=0, stdout="1.0.9\n"),
            ("agy", "--help"): ProbeExec(ran=True, exit_code=0, stdout="", stderr=_HELP_STDERR),
        }
    )


# --- the fixture that mirrors the real binary ------------------------------- #
def test_probe_recognizes_the_agy_surface():
    r = probe(_live_like())
    assert r.availability == "available"
    assert r.agy_version == "1.0.9"
    assert r.supports_print_mode == "yes"
    assert r.supports_sandbox_flag == "yes"
    assert r.supports_model_flag == "yes"
    # The known gap: no read-only/plan-mode flag → outer cage must fence writes.
    assert r.supports_plan_mode == "no"
    assert any("outer cage" in n for n in r.notes)
    # AGY-0 runs no behavioural probe.
    assert r.headless_stdout_probe == "skipped"
    assert r.write_probe_result == "skipped"
    assert r.network_probe_result == "skipped"


# --- fail-closed negatives (the load-bearing cases) ------------------------- #
def test_absent_binary_is_not_supported_never_crash():
    r = probe(_runner({}))  # nothing runs → binary absent
    assert r.availability == "not_supported"
    assert r.agy_version is None
    assert any("absent" in n for n in r.notes)


def test_version_nonzero_exit_is_unknown_not_available():
    r = probe(_runner({("agy", "--version"): ProbeExec(ran=True, exit_code=2, stderr="boom")}))
    assert r.availability == "unknown"


def test_unreadable_help_leaves_flags_unknown_not_assumed_yes():
    r = probe(
        _runner(
            {
                ("agy", "--version"): ProbeExec(ran=True, exit_code=0, stdout="1.0.9"),
                ("agy", "--help"): ProbeExec(ran=True, exit_code=0, stdout="", stderr=""),
            }
        )
    )
    assert r.availability == "available"
    assert r.agy_version == "1.0.9"
    # Not observed ⇒ unknown, never a silent "no" or an assumed "yes".
    assert r.supports_print_mode == "unknown"
    assert r.supports_sandbox_flag == "unknown"
    assert any("unknown" in n for n in r.notes)


def test_help_parsed_from_stdout_too():
    # Some CLIs print usage to stdout; the probe reads both streams.
    r = probe(
        _runner(
            {
                ("agy", "--version"): ProbeExec(ran=True, exit_code=0, stdout="1.0.9"),
                ("agy", "--help"): ProbeExec(ran=True, exit_code=0, stdout=_HELP_STDERR),
            }
        )
    )
    assert r.supports_print_mode == "yes"


# --- the honesty invariant: probe ≠ live testimony -------------------------- #
def test_evidence_kind_cannot_be_live_testimony():
    assert probe(_live_like()).evidence_kind == EVIDENCE_KIND == "probe_compatibility"
    with pytest.raises(ValueError):
        AntigravityProbeResult(availability="available", evidence_kind="live_testimony")


def test_result_rejects_out_of_vocabulary_values():
    with pytest.raises(ValueError):
        AntigravityProbeResult(availability="totally_fine")  # not in AVAILABILITY
    with pytest.raises(ValueError):
        AntigravityProbeResult(availability="available", supports_print_mode="maybe")


# --- descriptor: structural, thinner than Claude Code, declares no authority - #
def test_antigravity_descriptor_is_structural_and_authorityless():
    d = antigravity_cli_descriptor()
    assert d.provider_id == "antigravity_cli"
    assert d.provider_kind == "agent_runtime"
    assert d.authority_claims == ()
    # Deliberately thinner: no live adapter ⇒ no projected runtime capabilities.
    assert d.runtime_capabilities == frozenset()
    # (Claude Code, which HAS a live adapter, does project some — the contrast.)
    assert claude_code_descriptor().runtime_capabilities != frozenset()


def test_antigravity_descriptor_registers_structural():
    reg = ProviderRegistry()
    entry = reg.register(antigravity_cli_descriptor())
    assert entry.conformance is ConformanceLevel.STRUCTURAL
    got = [
        d.provider_id
        for d in reg.candidates_for(capability_requirements={"file_write"}, provider_kind="agent_runtime")
    ]
    assert "antigravity_cli" in got


# --- the persisted real probe fixture stays honest -------------------------- #
def test_persisted_probe_fixture_is_compatibility_evidence():
    data = json.loads((_REPO / "docs" / "playbooks" / "antigravity-probe.v0.json").read_text())
    assert data["evidence_kind"] == "probe_compatibility"  # never live testimony
    assert data["adapter"] == "antigravity_cli"
    # It records a real recognition, and it does NOT overclaim any behavioural probe.
    for k in ("headless_stdout_probe", "write_probe_result", "network_probe_result"):
        assert data[k] == "skipped"
