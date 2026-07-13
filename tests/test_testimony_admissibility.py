# SPDX-License-Identifier: Apache-2.0
"""Testimony-admissibility court — freeze the judgment logic + the 7 promotion
proof obligations. The truth tables are ported verbatim from the wind-tunnel
`test_verdict.py` so the promoted kernel is provably semantics-identical to the
frozen source. No model, extractor, fixtures, or lab config here."""

from __future__ import annotations

import ast
import pathlib

import pytest

from governor.testimony_admissibility import (
    AssertedTestimony,
    AuthorizedTestimony,
    RelationMismatchError,
    Relation,
    Strength,
    TestimonyContract,
    Verdict,
    adjudicate,
    adjudicate_testimony,
    classify_service,
    precheck,
    preflight,
    verdict,
)

REL = Relation("cpu_saturation", "contributed_to", "elevated_5xx")

# `TestimonyContract` starts with "Test"; keep pytest from trying to collect the
# imported dataclass as a test class (cosmetic warning only).
TestimonyContract.__test__ = False


# --------------------------------------------------------------------------- #
# Frozen truth tables (verbatim from windtunnel test_verdict.py)
# --------------------------------------------------------------------------- #

# ceiling-only verdict(asserted, authorized): rows are (authorized, asserted, expected)
CEIL = [
    (0, 0, "VALID"), (0, 1, "UNAUTHORIZED_NOMINATION"), (0, 2, "OVERSTATED_CERTAINTY"),
    (0, 3, "OVERSTATED_CERTAINTY"), (2, 0, "UNDER_TESTIMONY"), (2, 2, "VALID"),
    (2, 3, "UNSUPPORTED_PROMOTION"), (3, 3, "VALID"), (3, 0, "UNDER_TESTIMONY"),
]

# two-axis adjudicate: rows are (authorized, required, asserted, expected)
FULL = [
    (0, 0, 0, "VALID"),
    (3, 0, 3, "VALID"),
    (3, 0, 0, "VALID"),                             # floor 0: refusal within authority is VALID
    (2, 2, 2, "VALID"),
    (3, 2, 3, "VALID"),
    (2, 2, 0, "UNDER_TESTIMONY"),
    (0, 2, 0, "UNSATISFIABLE_CONTRACT"),
    (0, 2, 3, "OVERCLAIM_UNDER_UNSAT_CONTRACT"),
    (2, 1, 3, "UNSUPPORTED_PROMOTION"),
]

# precheck(required, authorized): rows are (required, authorized, decision)
PRE = [
    (0, 0, "ADMIT"), (2, 2, "ADMIT"), (2, 3, "ADMIT"),
    (2, 0, "REFUSE"), (1, 0, "REFUSE"), (3, 2, "REFUSE"),
]


@pytest.mark.parametrize("authorized,asserted,expected", CEIL)
def test_ceiling_only_verdict_frozen(authorized, asserted, expected):
    assert verdict(asserted, authorized) == expected


@pytest.mark.parametrize("authorized,required,asserted,expected", FULL)
def test_two_axis_adjudicate_frozen(authorized, required, asserted, expected):
    assert adjudicate(asserted, authorized, required) == expected


@pytest.mark.parametrize("required,authorized,decision", PRE)
def test_precheck_frozen(required, authorized, decision):
    assert precheck(required, authorized).decision == decision


# --------------------------------------------------------------------------- #
# Proof obligations (the promotion contract)
# --------------------------------------------------------------------------- #


def test_obligation_1_imports_without_model_extractor_regex_or_project_vocab():
    """The kernel imports with stdlib only — no model, extractor, regex
    vocabulary, or project (NQ/Maude/lab) dependency."""
    src = pathlib.Path(
        "src/governor/testimony_admissibility.py"
    ).read_text(encoding="utf-8")
    tree = ast.parse(src)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    # only these stdlib roots are permitted; notably NO `re`, no `governor.*`,
    # no `analyze`/extractor, no model client.
    assert roots <= {"__future__", "dataclasses", "enum"}, roots


def test_obligation_2_unsatisfiable_contract_rejected_before_asserted_considered():
    """required > authorized is judged ill-typed regardless of what was asserted.
    Preflight refuses pre-inference; adjudication returns UNSATISFIABLE even when
    the assertion would otherwise satisfy the floor."""
    contract = TestimonyContract(REL, Strength.SUPPORTED_CANDIDATE)  # required 2
    authorized = AuthorizedTestimony(REL, Strength.UNKNOWN)          # authorized 0
    pf = preflight(contract, authorized, request_id="r")
    assert pf.decision == "REFUSE"
    assert pf.verdict == Verdict.UNSATISFIABLE_TESTIMONY_CONTRACT
    # No asserted value rescues an ill-typed contract (required 2 > authorized 0):
    # the verdict is always an unsat-contract rejection, never VALID.
    for asserted in (0, 1, 2, 3):
        v = adjudicate(asserted, 0, 2)
        assert v != Verdict.VALID
        assert v in (Verdict.UNSATISFIABLE_CONTRACT, Verdict.OVERCLAIM_UNDER_UNSAT_CONTRACT)
    # the two sub-cases explicitly: within-ceiling stays unsat; a breach compounds it.
    assert adjudicate(0, 0, 2) == Verdict.UNSATISFIABLE_CONTRACT
    assert adjudicate(3, 0, 2) == Verdict.OVERCLAIM_UNDER_UNSAT_CONTRACT


def test_obligation_3_assertion_above_authorization_rejected():
    assert adjudicate(3, 2, 0) == Verdict.UNSUPPORTED_PROMOTION
    assert adjudicate(1, 0, 0) == Verdict.UNAUTHORIZED_NOMINATION
    assert adjudicate(2, 0, 0) == Verdict.OVERSTATED_CERTAINTY


def test_obligation_4_assertion_below_nonzero_requirement_is_under_testimony():
    # required 2, asserted 0, authorized 2 (contract satisfiable) -> under
    assert adjudicate(0, 2, 2) == Verdict.UNDER_TESTIMONY
    packet = adjudicate_testimony(
        TestimonyContract(REL, Strength.SUPPORTED_CANDIDATE),
        AuthorizedTestimony(REL, Strength.SUPPORTED_CANDIDATE),
        AssertedTestimony(REL, Strength.UNKNOWN),
    )
    assert packet.verdict == Verdict.UNDER_TESTIMONY


def test_obligation_5_assertion_within_both_bounds_is_valid():
    assert adjudicate(2, 2, 2) == Verdict.VALID
    assert adjudicate(2, 3, 1) == Verdict.VALID  # required 1 <= asserted 2 <= authorized 3
    packet = adjudicate_testimony(
        TestimonyContract(REL, Strength.FLOATED_CANDIDATE),
        AuthorizedTestimony(REL, Strength.ESTABLISHED),
        AssertedTestimony(REL, Strength.SUPPORTED_CANDIDATE),
    )
    assert packet.verdict == Verdict.VALID


def test_obligation_6_authorization_alone_creates_no_obligation_to_testify():
    """High authorization + zero requirement + no assertion is VALID, not
    under-testimony — the ceiling is a permission, not a duty."""
    assert adjudicate(0, 3, 0) == Verdict.VALID
    packet = adjudicate_testimony(
        TestimonyContract(REL, Strength.UNKNOWN),          # required 0
        AuthorizedTestimony(REL, Strength.ESTABLISHED),    # authorized 3
        AssertedTestimony(REL, Strength.UNKNOWN),          # asserted 0
    )
    assert packet.verdict == Verdict.VALID


def test_obligation_7_lowering_requirement_does_not_raise_authorization():
    """Lowering `required` must not license a higher assertion. authorized 1;
    an asserted 3 stays a ceiling breach whether required is 2, 1, or 0 —
    dropping the floor never lifts the ceiling."""
    for required in (0, 1, 2):
        v = adjudicate(3, 1, required)  # asserted 3, authorized 1
        assert v != Verdict.VALID  # lowering required never authorizes the 3
        assert v in (Verdict.UNSUPPORTED_PROMOTION, Verdict.OVERCLAIM_UNDER_UNSAT_CONTRACT)
    # satisfiable floors (<= authorized) keep it a plain ceiling breach:
    assert adjudicate(3, 1, 0) == Verdict.UNSUPPORTED_PROMOTION
    assert adjudicate(3, 1, 1) == Verdict.UNSUPPORTED_PROMOTION
    # the downgrade offer only ever lowers `required` TO the authorized ceiling,
    # never raises `authorized`:
    pf = precheck(3, 2, request_id="r")  # required 3 > authorized 2
    assert pf.downgrade_offer is not None
    assert pf.downgrade_offer.required == Strength.SUPPORTED_CANDIDATE.label  # == authorized


# --------------------------------------------------------------------------- #
# Structured surface: relations, no-compression, no-silent-lowering
# --------------------------------------------------------------------------- #


def test_relation_mismatch_fails_closed():
    other = Relation("x", "y", "z")
    with pytest.raises(RelationMismatchError):
        adjudicate_testimony(
            TestimonyContract(REL, Strength.SUPPORTED_CANDIDATE),
            AuthorizedTestimony(other, Strength.SUPPORTED_CANDIDATE),
            AssertedTestimony(REL, Strength.SUPPORTED_CANDIDATE),
        )
    with pytest.raises(RelationMismatchError):
        preflight(
            TestimonyContract(REL, Strength.SUPPORTED_CANDIDATE),
            AuthorizedTestimony(other, Strength.SUPPORTED_CANDIDATE),
        )


def test_review_packet_keeps_three_axes_separate():
    packet = adjudicate_testimony(
        TestimonyContract(REL, Strength.SUPPORTED_CANDIDATE),
        AuthorizedTestimony(REL, Strength.ESTABLISHED, consumed_receipts=("rcpt-1",)),
        AssertedTestimony(REL, Strength.SUPPORTED_CANDIDATE, triggering_spans=("span-1",)),
    )
    d = packet.to_dict()
    # required/authorized/asserted are distinct fields, not one status
    assert d["required"] == "supported_candidate"
    assert d["authorized"] == "established"
    assert d["asserted"] == "supported_candidate"
    assert d["verdict"] == "VALID"
    assert d["consumed_evidence"] == ["rcpt-1"]
    assert d["triggering_spans"] == ["span-1"]


def test_classify_service_never_one_green_check():
    # asserted 3 above authorized 2, meets required 2: complete+useful but NOT safe
    c = classify_service(asserted=3, authorized=2, required=2)
    assert c == {"safe": False, "complete": True, "useful": True}


def test_preflight_never_silently_lowers_required():
    """REFUSE carries an explicit downgrade OFFER; it does not mutate the
    contract or admit at the lowered floor."""
    pf = precheck(2, 0, request_id="req-9")
    assert pf.decision == "REFUSE"
    assert pf.downgrade_offer is not None
    assert "refused, not satisfied" in pf.downgrade_offer.note
    assert pf.downgrade_offer.receipt == "downgrade-req-9"
