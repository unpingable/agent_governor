# SPDX-License-Identifier: Apache-2.0
"""Local candidate worker — Slice 0 (failure-triage over a local model).

The whole point: local output can be OBSERVED but never ADMITTED. These tests use
deterministic fake clients (no live model, no network) to prove the candidate
discipline — schema gate, authority-claim refusal, non-authoritative receipt — and
that the emitted gate receipt fails the authority-admission predicate.
"""

from __future__ import annotations

import json
from pathlib import Path

from governor.cooked_context_orchestrator import is_authority_admission_receipt
from governor.gate_receipt import GateReceiptSystem
from governor.local_candidate import (
    CANDIDATE_OBSERVED,
    CANDIDATE_REFUSED,
    LOCAL_CANDIDATE_GATE,
    REFUSED_AUTHORITY_CLAIM,
    REFUSED_BACKEND_ERROR,
    REFUSED_EMPTY_OUTPUT,
    REFUSED_OUTSIDE_CARD,
    REFUSED_SCHEMA_INVALID,
    REFUSED_UNSUPPORTED_TASK,
    TASK_FAILURE_TRIAGE,
    FailureTriage,
    LocalCandidateRequest,
    RationCard,
    triage_failure,
)

_MODEL = "qwen2.5-coder:7b"


def _request(**overrides) -> LocalCandidateRequest:
    base = dict(
        task_kind=TASK_FAILURE_TRIAGE,
        model=_MODEL,
        command="pytest tests/ -q",
        exit_code=1,
        transcript="E   assert 0 == 1\ntests/test_x.py:42: AssertionError",
    )
    base.update(overrides)
    return LocalCandidateRequest(**base)


class _FixedClient:
    """Returns a fixed string regardless of prompt."""

    def __init__(self, output: str):
        self._output = output
        self.calls = 0

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return self._output


class _RaisingClient:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("ollama not reachable")


_GOOD = json.dumps(
    {
        "failure_kind": "assertion_failure",
        "likely_files": ["tests/test_x.py"],
        "next_action": "inspect the assertion at line 42",
        "confidence": "medium",
        "authority_claims": [],
    }
)


# --------------------------------------------------------------------------- #
# Observed candidate.
# --------------------------------------------------------------------------- #


class TestObserved:
    def test_good_output_is_observed(self):
        r = triage_failure(_request(), client=_FixedClient(_GOOD))
        assert r.verdict == CANDIDATE_OBSERVED
        assert r.is_observed is True
        assert r.candidate.failure_kind == "assertion_failure"
        assert r.candidate.likely_files == ("tests/test_x.py",)
        assert r.candidate.confidence == "medium"
        assert r.schema_valid is True
        assert r.authority_claims_detected is False
        assert r.output_digest is not None

    def test_receipt_is_non_authoritative(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        triage_failure(_request(), client=_FixedClient(_GOOD), receipt_sink=sink)
        receipts = [r for r in sink.receipt_store.all() if r.gate == LOCAL_CANDIDATE_GATE]
        assert len(receipts) == 1
        gr = receipts[0]
        assert gr.verdict == "observe"
        # The whole slogan: observed, never admitted.
        assert is_authority_admission_receipt(gr) is False
        bundle = sink.evidence_for(gr)
        assert bundle["non_authoritative"] is True
        assert bundle["verdict"] == CANDIDATE_OBSERVED


# --------------------------------------------------------------------------- #
# Authority-claim refusal — the tiny constitution.
# --------------------------------------------------------------------------- #


class TestAuthorityRefusal:
    def test_authority_claim_in_list_refused(self):
        out = json.dumps(
            {
                "failure_kind": "x",
                "likely_files": [],
                "next_action": "y",
                "confidence": "low",
                "authority_claims": ["tests_pass"],
            }
        )
        r = triage_failure(_request(), client=_FixedClient(out))
        assert r.verdict == CANDIDATE_REFUSED
        assert r.refusal_reason == REFUSED_AUTHORITY_CLAIM
        assert r.authority_claims_detected is True

    def test_smuggled_top_level_authority_key_refused(self):
        # A model trying to sneak "safe_to_commit": true past the empty list.
        out = json.dumps(
            {
                "failure_kind": "x",
                "likely_files": [],
                "next_action": "y",
                "confidence": "low",
                "authority_claims": [],
                "safe_to_commit": True,
            }
        )
        r = triage_failure(_request(), client=_FixedClient(out))
        assert r.verdict == CANDIDATE_REFUSED
        assert r.refusal_reason == REFUSED_AUTHORITY_CLAIM

    def test_refused_authority_receipt_still_non_authoritative(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        out = json.dumps(
            {
                "failure_kind": "x",
                "likely_files": [],
                "next_action": "y",
                "confidence": "low",
                "authority_claims": ["operational_effect"],
            }
        )
        triage_failure(_request(), client=_FixedClient(out), receipt_sink=sink)
        gr = [r for r in sink.receipt_store.all() if r.gate == LOCAL_CANDIDATE_GATE][0]
        assert gr.verdict == "observe"
        assert is_authority_admission_receipt(gr) is False


# --------------------------------------------------------------------------- #
# Schema / backend refusals.
# --------------------------------------------------------------------------- #


class TestRefusals:
    def test_non_json_refused(self):
        r = triage_failure(_request(), client=_FixedClient("the build is probably fine lol"))
        assert r.verdict == CANDIDATE_REFUSED
        assert r.refusal_reason == REFUSED_SCHEMA_INVALID

    def test_missing_key_refused(self):
        out = json.dumps({"failure_kind": "x", "likely_files": [], "next_action": "y"})
        r = triage_failure(_request(), client=_FixedClient(out))
        assert r.refusal_reason == REFUSED_SCHEMA_INVALID

    def test_bad_confidence_refused(self):
        out = json.dumps(
            {
                "failure_kind": "x",
                "likely_files": [],
                "next_action": "y",
                "confidence": "extremely",
                "authority_claims": [],
            }
        )
        r = triage_failure(_request(), client=_FixedClient(out))
        assert r.refusal_reason == REFUSED_SCHEMA_INVALID

    def test_empty_output_refused(self):
        r = triage_failure(_request(), client=_FixedClient("   "))
        assert r.refusal_reason == REFUSED_EMPTY_OUTPUT

    def test_backend_error_refused_not_raised(self):
        r = triage_failure(_request(), client=_RaisingClient())
        assert r.verdict == CANDIDATE_REFUSED
        assert r.refusal_reason == REFUSED_BACKEND_ERROR

    def test_unsupported_task_refused_without_calling_model(self):
        client = _FixedClient(_GOOD)
        r = triage_failure(_request(task_kind="apply_patch"), client=client)
        assert r.refusal_reason == REFUSED_UNSUPPORTED_TASK
        assert client.calls == 0  # never reached the model

    def test_outside_card_refused_without_calling_model(self):
        # A card for a DIFFERENT model: the request agent won't match.
        client = _FixedClient(_GOOD)
        card = RationCard(agent_id="some-other-model", task_kind=TASK_FAILURE_TRIAGE)
        r = triage_failure(_request(), client=client, card=card)
        assert r.refusal_reason == REFUSED_OUTSIDE_CARD
        assert client.calls == 0


# --------------------------------------------------------------------------- #
# Receipt invariants.
# --------------------------------------------------------------------------- #


class TestReceiptInvariants:
    def test_confidence_vocab_enforced_on_candidate(self):
        import pytest

        with pytest.raises(ValueError):
            FailureTriage(
                failure_kind="x",
                likely_files=(),
                next_action="y",
                confidence="vibes",
            )

    def test_refused_receipt_has_no_candidate(self):
        r = triage_failure(_request(), client=_FixedClient("not json"))
        assert r.candidate is None
        assert r.is_observed is False
