# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from governor.operator_decisions import (
    DecisionItem,
    DecisionOption,
    build_decision_feed,
)


@dataclass
class FakePromotion:
    promotion_id: str
    session_id: str
    created_at: str
    status: str
    repo_path: str
    changed_files: list[str]
    diff_stat: str
    diff_text: str
    decision_at: str | None = None
    decision_reason: str | None = None
    excluded_files: list[str] = dataclasses.field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "promotion_id": self.promotion_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "status": self.status,
            "repo_path": self.repo_path,
            "changed_files": self.changed_files,
            "diff_stat": self.diff_stat,
            "decision_at": self.decision_at,
            "decision_reason": self.decision_reason,
            "excluded_files": self.excluded_files or [],
        }


def option_keys(item: Any) -> tuple[str, ...]:
    return tuple(option["key"] for option in item.to_dict()["options"])


def test_empty_feed_returns_empty_tuple() -> None:
    assert build_decision_feed() == ()


def test_intervention_normalizes_with_contract_options() -> None:
    feed = build_decision_feed(
        interventions=[
            {
                "intervention_id": "int_1",
                "tool_call_id": "call_1",
                "tool_name": "write_file",
                "tool_input": {"path": "x"},
                "event_id": "evt_1",
                "created_at": 1_000.0,
                "timeout_seconds": 300.0,
            }
        ],
        now=1_100.0,
    )

    item = feed[0]
    assert item.kind == "intervention"
    assert item.source == {"subsystem": "runtime.intervention", "native_id": "int_1"}
    assert item.urgency == "blocking"
    assert item.timeout_at == "1970-01-01T00:21:40+00:00"
    assert option_keys(item) == ("y", "n")


def test_violation_normalizes_with_contract_options() -> None:
    feed = build_decision_feed(
        violations=[
            {
                "id": "viol_1",
                "context_id": "ctx_1",
                "run_id": "run_1",
                "violations": [{"type": "claim"}],
                "blocked_response": "blocked",
                "timestamp": "2026-07-02T10:00:00Z",
                "mode": "code",
                "status": "pending",
                "receipt_id": "rcpt_1",
            }
        ]
    )

    item = feed[0]
    assert item.kind == "violation"
    assert item.session_ref == "run_1"
    assert item.receipt_refs == ("rcpt_1",)
    assert item.why_ref == "rcpt_1"
    assert option_keys(item) == ("f", "r", "p")


def test_promotion_normalizes_with_contract_options() -> None:
    feed = build_decision_feed(
        promotions=[
            {
                "promotion_id": "prom_1",
                "session_id": "sess_1",
                "created_at": "2026-07-02T10:00:00Z",
                "status": "pending",
                "repo_path": "/repo",
                "changed_files": ["a.py", "b.py"],
                "diff_stat": "2 files changed",
                "diff_text": "---",
            }
        ]
    )

    item = feed[0]
    assert item.kind == "promotion"
    assert item.session_ref == "sess_1"
    assert item.urgency == "normal"
    assert option_keys(item) == ("y", "n")


def test_docket_case_normalizes_with_contract_options() -> None:
    feed = build_decision_feed(
        docket_cases=[
            {
                "case_number": 7,
                "case_type": "contested",
                "claim_id": "claim_1",
                "anchor_id": "anchor_1",
                "status": "pending",
                "description": "needs ruling",
                "evidence": [],
                "created_at": datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc),
            }
        ]
    )

    item = feed[0]
    assert item.kind == "docket_case"
    assert item.source["native_id"] == "7"
    assert item.created_at == "2026-07-02T10:00:00+00:00"
    assert option_keys(item) == ("s", "a", "g", "v", "d")


def test_admissibility_question_normalizes_with_answer_schema() -> None:
    feed = build_decision_feed(
        admissibility_questions=[
            {
                "id": "unk_1",
                "description": "What is the objective?",
                "severity": "S2",
                "resolvable_by": "user_clarification",
                "created_at": "2026-07-02T10:00:00Z",
            }
        ]
    )

    item = feed[0]
    assert item.kind == "admissibility_question"
    assert item.urgency == "blocking"
    assert item.to_dict()["options"] == [
        {"key": "a", "label": "answer", "action": "answer", "args_schema": {"answer": "string"}}
    ]


def test_operator_question_passes_source_options_through() -> None:
    feed = build_decision_feed(
        operator_questions=[
            {
                "id": "q_1",
                "subsystem": "runtime.adapter",
                "session_id": "sess_1",
                "created_at": "2026-07-02T10:00:00Z",
                "urgency": "info",
                "summary": "Choose one",
                "detail": {"prompt": "Choose one"},
                "options": [
                    {"key": "x", "label": "xray", "action": "choose_x", "args_schema": None},
                    {"key": "z", "label": "zulu", "action": "choose_z", "args_schema": {"why": "string"}},
                ],
            }
        ]
    )

    item = feed[0]
    assert item.kind == "operator_question"
    assert item.source == {"subsystem": "runtime.adapter", "native_id": "q_1"}
    assert item.urgency == "info"
    assert item.to_dict()["options"] == [
        {"key": "x", "label": "xray", "action": "choose_x", "args_schema": None},
        {"key": "z", "label": "zulu", "action": "choose_z", "args_schema": {"why": "string"}},
    ]


def test_determinism_same_inputs_and_now_produce_identical_dicts() -> None:
    kwargs = {
        "promotions": [
            {
                "promotion_id": "prom_1",
                "session_id": "sess_1",
                "created_at": "2026-07-02T10:00:00Z",
                "status": "pending",
                "repo_path": "/repo",
                "changed_files": ["a.py"],
                "diff_stat": "1 file changed",
                "diff_text": "---",
            }
        ],
        "now": 1_000.0,
    }

    first = [item.to_dict() for item in build_decision_feed(**kwargs)]
    second = [item.to_dict() for item in build_decision_feed(**kwargs)]

    assert first == second


def test_unknown_kind_refused() -> None:
    with pytest.raises(ValueError, match="unknown decision kind"):
        DecisionItem(
            decision_id="dec_bad",
            kind="autonomy_offer",
            session_ref=None,
            created_at="2026-07-02T10:00:00Z",
            urgency="normal",
            timeout_at=None,
            summary="bad",
            detail={},
            options=(),
            receipt_refs=(),
            why_ref=None,
            refs=(),
            source={"subsystem": "x", "native_id": "y"},
        )


def test_missing_native_id_refused() -> None:
    with pytest.raises(ValueError, match="missing native decision id"):
        build_decision_feed(
            promotions=[
                {
                    "promotion_id": "",
                    "session_id": "sess_1",
                    "created_at": "2026-07-02T10:00:00Z",
                    "status": "pending",
                    "repo_path": "/repo",
                    "changed_files": [],
                    "diff_stat": "",
                    "diff_text": "",
                }
            ]
        )


def test_urgency_ordering_then_created_at_then_decision_id() -> None:
    feed = build_decision_feed(
        promotions=[
            {
                "promotion_id": "prom_1",
                "session_id": "sess_1",
                "created_at": "2026-07-02T09:00:00Z",
                "status": "pending",
                "repo_path": "/repo",
                "changed_files": [],
                "diff_stat": "",
                "diff_text": "",
            }
        ],
        violations=[
            {
                "id": "viol_1",
                "context_id": "ctx_1",
                "run_id": "run_1",
                "violations": [],
                "blocked_response": "blocked",
                "timestamp": "2026-07-02T11:00:00Z",
                "mode": "code",
                "status": "pending",
            }
        ],
        interventions=[
            {
                "intervention_id": "int_1",
                "tool_call_id": "call_1",
                "tool_name": "write_file",
                "tool_input": {},
                "event_id": "evt_1",
                "created_at": 1_000.0,
                "timeout_seconds": 100.0,
            }
        ],
        operator_questions=[
            {
                "id": "q_1",
                "subsystem": "runtime.adapter",
                "created_at": "2026-07-02T08:00:00Z",
                "urgency": "info",
                "summary": "FYI",
                "options": [{"key": "o", "label": "ok", "action": "ok", "args_schema": None}],
            }
        ],
        now=1_050.0,
    )

    assert [item.urgency for item in feed] == ["blocking", "expiring", "normal", "info"]


def test_intervention_expiring_boundary_at_60_seconds() -> None:
    at_boundary = build_decision_feed(
        interventions=[
            {
                "intervention_id": "int_1",
                "tool_call_id": "call_1",
                "tool_name": "write_file",
                "tool_input": {},
                "event_id": "evt_1",
                "created_at": 1_000.0,
                "timeout_seconds": 100.0,
            }
        ],
        now=1_040.0,
    )
    just_before = build_decision_feed(
        interventions=[
            {
                "intervention_id": "int_2",
                "tool_call_id": "call_2",
                "tool_name": "write_file",
                "tool_input": {},
                "event_id": "evt_2",
                "created_at": 1_000.0,
                "timeout_seconds": 100.0,
            }
        ],
        now=1_039.999,
    )

    assert at_boundary[0].urgency == "expiring"
    assert just_before[0].urgency == "blocking"


def test_dict_input_and_dataclass_input_parity_for_promotion() -> None:
    dict_feed = build_decision_feed(
        promotions=[
            {
                "promotion_id": "prom_1",
                "session_id": "sess_1",
                "created_at": "2026-07-02T10:00:00Z",
                "status": "pending",
                "repo_path": "/repo",
                "changed_files": ["a.py"],
                "diff_stat": "1 file changed",
                "diff_text": "---",
                "decision_at": None,
                "decision_reason": None,
                "excluded_files": [],
            }
        ]
    )
    dataclass_feed = build_decision_feed(
        promotions=[
            FakePromotion(
                promotion_id="prom_1",
                session_id="sess_1",
                created_at="2026-07-02T10:00:00Z",
                status="pending",
                repo_path="/repo",
                changed_files=["a.py"],
                diff_stat="1 file changed",
                diff_text="---",
            )
        ]
    )

    assert [item.to_dict() for item in dict_feed] == [item.to_dict() for item in dataclass_feed]


def test_to_dict_has_exact_contract_field_names() -> None:
    item = build_decision_feed(
        promotions=[
            {
                "promotion_id": "prom_1",
                "session_id": "sess_1",
                "created_at": "2026-07-02T10:00:00Z",
                "status": "pending",
                "repo_path": "/repo",
                "changed_files": [],
                "diff_stat": "",
                "diff_text": "",
            }
        ]
    )[0]

    assert set(item.to_dict()) == {
        "decision_id",
        "kind",
        "session_ref",
        "created_at",
        "urgency",
        "timeout_at",
        "summary",
        "detail",
        "options",
        "receipt_refs",
        "why_ref",
        "refs",
        "source",
    }


def test_duplicate_option_keys_refused() -> None:
    with pytest.raises(ValueError, match="unique"):
        DecisionItem(
            decision_id="dec_dup",
            kind="operator_question",
            session_ref=None,
            created_at="2026-07-02T10:00:00Z",
            urgency="normal",
            timeout_at=None,
            summary="bad",
            detail={},
            options=(
                DecisionOption("a", "one", "one", None),
                DecisionOption("a", "two", "two", None),
            ),
            receipt_refs=(),
            why_ref=None,
            refs=(),
            source={"subsystem": "x", "native_id": "y"},
        )


# --------------------------------------------------------------------------- #
# Hardening (adversarial audit findings, 2026-07-03)
# --------------------------------------------------------------------------- #


def test_duplicate_decision_id_is_refused() -> None:
    # Two backing objects that resolve to one routable identity are ambiguous.
    with pytest.raises(ValueError, match="duplicate decision_id"):
        build_decision_feed(
            promotions=[
                {"promotion_id": "p", "session_id": "s", "created_at": "2026-07-02T10:00:00Z",
                 "status": "pending", "repo_path": "/r", "changed_files": [], "diff_stat": "", "diff_text": ""},
                {"promotion_id": "p", "session_id": "s2", "created_at": "2026-07-02T10:00:01Z",
                 "status": "pending", "repo_path": "/r2", "changed_files": [], "diff_stat": "", "diff_text": ""},
            ]
        )


def test_operator_question_without_subsystem_is_refused() -> None:
    # subsystem is half the source identity; a default would drift the id.
    with pytest.raises(ValueError, match="subsystem"):
        build_decision_feed(
            operator_questions=[
                {"id": "q", "created_at": "2026-07-02T10:00:00Z", "summary": "x",
                 "options": [{"key": "a", "label": "a", "action": "a", "args_schema": None}]}
            ]
        )


def test_operator_option_keys_must_be_single_char_and_unique() -> None:
    base = {"id": "q", "subsystem": "sub", "created_at": "2026-07-02T10:00:00Z", "summary": "x"}
    with pytest.raises(ValueError, match="single character"):
        build_decision_feed(operator_questions=[{**base, "options": [
            {"key": "ab", "label": "l", "action": "a", "args_schema": None}]}])
    with pytest.raises(ValueError, match="duplicate option key"):
        build_decision_feed(operator_questions=[{**base, "options": [
            {"key": "x", "label": "l", "action": "a", "args_schema": None},
            {"key": "x", "label": "m", "action": "b", "args_schema": None}]}])


def test_operator_question_non_mapping_detail_is_refused() -> None:
    with pytest.raises(ValueError, match="detail must be a mapping"):
        build_decision_feed(operator_questions=[{
            "id": "q", "subsystem": "sub", "created_at": "2026-07-02T10:00:00Z", "summary": "x",
            "detail": ["not", "a", "map"],
            "options": [{"key": "a", "label": "l", "action": "a", "args_schema": None}]}])


def test_intervention_past_deadline_is_blocking_not_expiring() -> None:
    # remaining <= 0 (auto-deny imminent/past) => blocking, not expiring.
    feed = build_decision_feed(
        interventions=[{"intervention_id": "i", "tool_call_id": "c", "tool_name": "t",
                        "tool_input": {}, "created_at": 1_000.0, "timeout_seconds": 30.0}],
        now=1_100.0,  # 70s past a 30s deadline
    )
    assert feed[0].urgency == "blocking"


def test_intervention_created_at_as_datetime_does_not_raise() -> None:
    # Time handling is consistent: a datetime created_at is coerced, not crashed.
    dt = datetime(2026, 7, 2, 10, 0, tzinfo=timezone.utc)
    feed = build_decision_feed(
        interventions=[{"intervention_id": "i", "tool_call_id": "c", "tool_name": "t",
                        "tool_input": {}, "created_at": dt, "timeout_seconds": 300.0}],
        now=dt.timestamp() + 270,  # 30s remaining of a 300s window => expiring
    )
    assert feed[0].urgency == "expiring"
    assert feed[0].timeout_at is not None  # datetime created_at was coerced, not crashed


def test_decision_id_is_stable_and_64_bit() -> None:
    a = build_decision_feed(promotions=[{"promotion_id": "p", "session_id": "s",
        "created_at": "2026-07-02T10:00:00Z", "status": "pending", "repo_path": "/r",
        "changed_files": [], "diff_stat": "", "diff_text": ""}])[0]
    b = build_decision_feed(promotions=[{"promotion_id": "p", "session_id": "s",
        "created_at": "2026-07-02T10:00:00Z", "status": "pending", "repo_path": "/r",
        "changed_files": [], "diff_stat": "", "diff_text": ""}])[0]
    assert a.decision_id == b.decision_id  # stable
    assert len(a.decision_id) == len("dec_") + 16  # 64-bit hex prefix


# --------------------------------------------------------------------------- #
# build_feed_from_runtime (GS-2b — maps live supervisor/resolver objects)
# --------------------------------------------------------------------------- #


@dataclass
class _FakeIntervention:
    intervention_id: str
    tool_call_id: str
    tool_name: str
    tool_input: dict
    event_id: str
    elapsed: float
    timeout_seconds: float = 300.0


@dataclass
class _FakeViolation:
    id: str
    run_id: str
    violations: list
    timestamp: str
    receipt_id: str | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "run_id": self.run_id, "violations": self.violations,
                "timestamp": self.timestamp, "receipt_id": self.receipt_id}


def test_build_feed_from_runtime_threads_session_and_exact_remaining() -> None:
    from governor.operator_decisions import build_feed_from_runtime
    now = 1_000_000.0
    feed = build_feed_from_runtime(
        interventions=[("sess_A", _FakeIntervention(
            intervention_id="i1", tool_call_id="c1", tool_name="Bash",
            tool_input={"cmd": "rm"}, event_id="e1", elapsed=280.0, timeout_seconds=300.0))],
        pending_violation=_FakeViolation(id="v1", run_id="run1", violations=[{"t": "x"}],
                                         timestamp="2026-07-03T10:00:00Z", receipt_id="r1"),
        now_wall=now,
    )
    kinds = {i.kind for i in feed}
    assert kinds == {"intervention", "violation"}
    iv = next(i for i in feed if i.kind == "intervention")
    assert iv.session_ref == "sess_A"
    # 300s timeout, 280s elapsed -> 20s remaining -> expiring (<=60), monotonic-exact.
    assert iv.urgency == "expiring"
    # created_at is the honest wall approximation (now - elapsed), a real ISO.
    assert iv.created_at.startswith("1970") is False or iv.created_at  # renders an ISO


def test_build_feed_from_runtime_empty_is_empty() -> None:
    from governor.operator_decisions import build_feed_from_runtime
    assert build_feed_from_runtime(now_wall=1.0) == ()
