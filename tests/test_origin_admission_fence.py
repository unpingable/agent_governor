"""Operational-admission fence (simulated-evidence fence, ratified 2026-06-11).

The fence answers the gate's one local question: may a receipt bearing this
``origin_mode`` satisfy an operational check (promote / suppress a real event /
become spendable)?  It is a closed-world ALLOWLIST, not a blocklist.

The load-bearing test here is ``test_pinning_novel_origin_never_admitted`` — the
fence's fence.  A blocklist would admit every unmodeled value by default; the
allowlist must refuse it.  If this test ever goes green for a novel string, the
fence has silently inverted into a blocklist and the launch demo can be
contaminated by a tool emitting a new origin label.
"""

import pytest

from governor.cooked_context_orchestrator import (
    AG_INTERNAL_ORIGIN_MODES,
    CLOSED_ORIGIN_MODES,
    EVIDENCE_KEY_ORIGIN_MODE,
    MalformedOriginError,
    NQ_ORIGIN_MODES,
    ORIGIN_ADMITTED,
    ORIGIN_MODE_CLI,
    ORIGIN_MODE_DRILL,
    ORIGIN_MODE_OBSERVED,
    ORIGIN_MODE_REPLAY,
    ORIGIN_MODE_STUB,
    ORIGIN_MODE_SYNTHETIC,
    ORIGIN_REFUSED_MISSING,
    ORIGIN_REFUSED_NOT_OPERATIONAL,
    ORIGIN_REFUSED_UNRECOGNIZED,
    OPERATIONAL_ORIGIN_MODES,
    operational_admission,
    operational_admission_for_bundle,
)


# --- admission (the one operational mode) ----------------------------------

def test_observed_is_admitted():
    a = operational_admission(ORIGIN_MODE_OBSERVED)
    assert a.admitted is True
    assert a.refused is False
    assert a.reason == ORIGIN_ADMITTED
    assert a.origin_mode == ORIGIN_MODE_OBSERVED


# --- recognized-but-non-operational (the simulated/staged/internal modes) --

@pytest.mark.parametrize(
    "mode",
    [
        ORIGIN_MODE_SYNTHETIC,  # the demo case — must never contaminate
        ORIGIN_MODE_DRILL,
        ORIGIN_MODE_REPLAY,
        ORIGIN_MODE_CLI,
        ORIGIN_MODE_STUB,
    ],
)
def test_recognized_non_operational_modes_refuse(mode):
    a = operational_admission(mode)
    assert a.refused is True
    assert a.reason == ORIGIN_REFUSED_NOT_OPERATIONAL
    assert a.origin_mode == mode


# --- THE PINNING TEST: novel / unmodeled strings never admitted ------------

@pytest.mark.parametrize(
    "novel",
    [
        "test2",            # the canonical "modified tool emits a new class" case
        "operational",      # a plausible-looking word that is NOT a modeled mode
        "nq_origin",        # the umbrella alias the closed vocab already forbids
        "Observed",         # wrong case — closed-world is exact, not fuzzy
        " observed ",       # whitespace — no trimming/coercion
        "synthetic2",       # near-miss of a real mode
        "",                 # empty string
        "admitted",
    ],
)
def test_pinning_novel_origin_never_admitted(novel):
    """A tool emitting an unmodeled origin string MUST land in refusal, never
    admission.  This is the fence's fence — see module docstring."""
    a = operational_admission(novel)
    assert a.admitted is False
    assert a.reason == ORIGIN_REFUSED_UNRECOGNIZED
    assert a.origin_mode == novel


# --- missing is malformed, never default-operational -----------------------

def test_none_refuses_missing_not_operational():
    a = operational_admission(None)
    assert a.admitted is False
    assert a.reason == ORIGIN_REFUSED_MISSING
    assert a.origin_mode is None


# --- malformed type aborts (never coerced, never admitted) -----------------

@pytest.mark.parametrize("bad", [123, 1.5, True, ["observed"], {"m": "observed"}, object()])
def test_non_string_origin_aborts(bad):
    with pytest.raises(MalformedOriginError):
        operational_admission(bad)


# --- bundle convenience -----------------------------------------------------

def test_bundle_missing_or_empty_refuses_missing():
    assert operational_admission_for_bundle(None).reason == ORIGIN_REFUSED_MISSING
    assert operational_admission_for_bundle({}).reason == ORIGIN_REFUSED_MISSING
    # bundle present but no origin_mode key
    assert (
        operational_admission_for_bundle({"other": "x"}).reason
        == ORIGIN_REFUSED_MISSING
    )


def test_bundle_reads_origin_mode_key():
    admit = operational_admission_for_bundle(
        {EVIDENCE_KEY_ORIGIN_MODE: ORIGIN_MODE_OBSERVED}
    )
    assert admit.admitted is True
    refuse = operational_admission_for_bundle(
        {EVIDENCE_KEY_ORIGIN_MODE: ORIGIN_MODE_SYNTHETIC}
    )
    assert refuse.refused is True
    assert refuse.reason == ORIGIN_REFUSED_NOT_OPERATIONAL


# --- structural invariants (closed-world integrity) ------------------------

def test_operational_set_is_strict_subset_of_closed():
    """No operational mode may exist outside the ratified closed vocabulary."""
    assert OPERATIONAL_ORIGIN_MODES <= CLOSED_ORIGIN_MODES
    assert OPERATIONAL_ORIGIN_MODES < CLOSED_ORIGIN_MODES  # strict: more than one mode total


def test_every_closed_mode_is_classified_admit_or_not_operational():
    """Every member of the closed vocab resolves to admit or
    not-operational — never unrecognized.  Guards against a CLOSED member
    that the fence forgot to classify."""
    for mode in CLOSED_ORIGIN_MODES:
        a = operational_admission(mode)
        assert a.reason in (ORIGIN_ADMITTED, ORIGIN_REFUSED_NOT_OPERATIONAL)
        assert a.reason != ORIGIN_REFUSED_UNRECOGNIZED


def test_adding_a_closed_mode_does_not_auto_admit_it():
    """Closed-world allowlist property: being in the closed vocab does NOT
    confer operational status.  Every non-observed closed mode refuses, so a
    future closed-set widening cannot silently become operational."""
    non_observed_closed = CLOSED_ORIGIN_MODES - OPERATIONAL_ORIGIN_MODES
    assert non_observed_closed  # there are such modes
    for mode in non_observed_closed:
        assert operational_admission(mode).refused is True


def test_operational_set_is_exactly_observed():
    """Pin the current ratified membership.  Widening this is a custody
    change and must update this assertion + add a pinning case above."""
    assert OPERATIONAL_ORIGIN_MODES == frozenset({ORIGIN_MODE_OBSERVED})
