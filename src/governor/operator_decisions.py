# SPDX-License-Identifier: Apache-2.0
"""Operator decision feed — normalize pending decisions without authority.

The shell contract's decision envelope is a rendering surface, not a new source
of truth. This module only mirrors native pending objects from AG subsystems into
that closed envelope. It performs no IO, imports no daemon/runtime machinery, and
mints no native backing: every item must carry a subsystem native id.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable, Mapping, Sequence


DECISION_KINDS = frozenset(
    {
        "intervention",
        "violation",
        "promotion",
        "docket_case",
        "admissibility_question",
        "operator_question",
    }
)
URGENCIES = frozenset({"blocking", "expiring", "normal", "info"})
URGENCY_RANK = {"blocking": 0, "expiring": 1, "normal": 2, "info": 3}


@dataclass(frozen=True)
class DecisionOption:
    key: str
    label: str
    action: str
    args_schema: dict[str, Any] | None

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or len(self.key) != 1:
            raise ValueError("decision option key must be a single character")
        if not isinstance(self.label, str) or not self.label:
            raise ValueError("decision option label must be a non-empty string")
        if not isinstance(self.action, str) or not self.action:
            raise ValueError("decision option action must be a non-empty string")
        if self.args_schema is not None and not isinstance(self.args_schema, dict):
            raise ValueError("decision option args_schema must be a dict or None")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "action": self.action,
            "args_schema": dict(self.args_schema) if self.args_schema is not None else None,
        }


@dataclass(frozen=True)
class DecisionItem:
    decision_id: str
    kind: str
    session_ref: str | None
    created_at: str
    urgency: str
    timeout_at: str | None
    summary: str
    detail: dict[str, Any]
    options: tuple[DecisionOption, ...]
    receipt_refs: tuple[str, ...]
    why_ref: str | None
    refs: tuple[Any, ...]
    source: dict[str, str]

    def __post_init__(self) -> None:
        if self.kind not in DECISION_KINDS:
            raise ValueError(f"unknown decision kind: {self.kind}")
        if self.urgency not in URGENCIES:
            raise ValueError(f"unknown decision urgency: {self.urgency}")
        if set(self.source) != {"subsystem", "native_id"}:
            raise ValueError("source must contain exactly subsystem and native_id")
        if not self.source["subsystem"] or not self.source["native_id"]:
            raise ValueError("source subsystem and native_id are required")

        keys = [option.key for option in self.options]
        if len(keys) != len(set(keys)):
            raise ValueError("decision option keys must be unique per item")

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "kind": self.kind,
            "session_ref": self.session_ref,
            "created_at": self.created_at,
            "urgency": self.urgency,
            "timeout_at": self.timeout_at,
            "summary": self.summary,
            "detail": dict(self.detail),
            "options": [option.to_dict() for option in self.options],
            "receipt_refs": list(self.receipt_refs),
            "why_ref": self.why_ref,
            "refs": list(self.refs),
            "source": dict(self.source),
        }


def build_decision_feed(
    *,
    interventions: Sequence[Any] | None = None,
    violations: Sequence[Any] | None = None,
    promotions: Sequence[Any] | None = None,
    docket_cases: Sequence[Any] | None = None,
    admissibility_questions: Sequence[Any] | None = None,
    operator_questions: Sequence[Any] | None = None,
    now: float | datetime | str | None = None,
) -> tuple[DecisionItem, ...]:
    """Return pending native decisions as shell-contract decision envelopes."""

    now_value = _coerce_now(now)
    items: list[DecisionItem] = []

    items.extend(_intervention_item(item, now_value) for item in _items(interventions))
    items.extend(_violation_item(item) for item in _items(violations))
    items.extend(_promotion_item(item) for item in _items(promotions))
    items.extend(_docket_case_item(item) for item in _items(docket_cases))
    items.extend(_admissibility_question_item(item) for item in _items(admissibility_questions))
    items.extend(_operator_question_item(item) for item in _items(operator_questions))

    return tuple(
        sorted(
            items,
            key=lambda item: (URGENCY_RANK[item.urgency], item.created_at, item.decision_id),
        )
    )


def _items(values: Sequence[Any] | None) -> tuple[Any, ...]:
    if values is None:
        return ()
    return tuple(values)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _required(obj: Any, name: str) -> Any:
    value = _get(obj, name)
    if value is None or value == "":
        raise ValueError(f"missing required field: {name}")
    return value


def _native_id(obj: Any, *names: str) -> str:
    for name in names:
        value = _get(obj, name)
        if value is not None and value != "":
            return str(value)
    raise ValueError("missing native decision id")


def _value(value: Any) -> Any:
    if hasattr(value, "value"):
        return value.value
    return value


def _as_detail(obj: Any, fields: Iterable[str]) -> dict[str, Any]:
    # Always project the DECLARED field list — never an object's own to_dict()
    # — so dict inputs and dataclass inputs normalize identically (parity is a
    # contract property, not a fixture accident).
    detail: dict[str, Any] = {}
    for field in fields:
        value = _get(obj, field)
        if value is not None:
            if isinstance(value, datetime):
                detail[field] = value.isoformat()
            else:
                detail[field] = _value(value)
    return detail


def _iso(value: Any) -> str:
    if value is None or value == "":
        raise ValueError("created_at is required")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    return str(value)


def _coerce_now(now: float | datetime | str | None) -> float | None:
    if now is None:
        return None
    if isinstance(now, datetime):
        return now.timestamp()
    if isinstance(now, (int, float)):
        return float(now)
    raise ValueError("now must be a float, datetime, or None")


def _timeout_from_intervention(item: Any, now: float | None) -> tuple[float | None, str | None]:
    timeout_seconds = _get(item, "timeout_seconds")
    created_at = _get(item, "created_at")

    if timeout_seconds is None or created_at is None:
        return None, None

    deadline = float(created_at) + float(timeout_seconds)
    remaining = max(0.0, deadline - now) if now is not None else _get(item, "remaining")
    if remaining is None:
        return None, None

    return float(remaining), datetime.fromtimestamp(deadline, tz=timezone.utc).isoformat()


def _decision_id(kind: str, source_subsystem: str, native_id: str) -> str:
    if kind not in DECISION_KINDS:
        raise ValueError(f"unknown decision kind: {kind}")
    digest = sha256(f"{kind}:{source_subsystem}:{native_id}".encode()).hexdigest()[:12]
    return f"dec_{digest}"


def _source(kind: str, subsystem: str, native_id: str) -> dict[str, str]:
    return {"subsystem": subsystem, "native_id": native_id}


def _make_item(
    *,
    kind: str,
    subsystem: str,
    native_id: str,
    session_ref: str | None,
    created_at: str,
    urgency: str,
    timeout_at: str | None,
    summary: str,
    detail: dict[str, Any],
    options: tuple[DecisionOption, ...],
    receipt_refs: tuple[str, ...] = (),
    why_ref: str | None = None,
    refs: tuple[Any, ...] = (),
) -> DecisionItem:
    return DecisionItem(
        decision_id=_decision_id(kind, subsystem, native_id),
        kind=kind,
        session_ref=session_ref,
        created_at=created_at,
        urgency=urgency,
        timeout_at=timeout_at,
        summary=summary,
        detail=detail,
        options=options,
        receipt_refs=receipt_refs,
        why_ref=why_ref,
        refs=refs,
        source=_source(kind, subsystem, native_id),
    )


def _intervention_options() -> tuple[DecisionOption, ...]:
    return (
        DecisionOption("y", "approve", "approve", None),
        DecisionOption("n", "deny", "deny", None),
    )


def _violation_options() -> tuple[DecisionOption, ...]:
    return (
        DecisionOption("f", "fix", "fix", None),
        DecisionOption("r", "revise", "revise", None),
        DecisionOption("p", "proceed", "proceed", None),
    )


def _promotion_options() -> tuple[DecisionOption, ...]:
    return (
        DecisionOption("y", "approve", "approve", None),
        DecisionOption("n", "reject", "reject", None),
    )


def _docket_options() -> tuple[DecisionOption, ...]:
    return (
        DecisionOption("s", "sustain", "sustain", None),
        DecisionOption("a", "amend", "amend", None),
        DecisionOption("g", "grant_exception", "grant_exception", None),
        DecisionOption("v", "reverify", "reverify", None),
        DecisionOption("d", "dismiss", "dismiss", None),
    )


def _admissibility_options() -> tuple[DecisionOption, ...]:
    return (DecisionOption("a", "answer", "answer", {"answer": "string"}),)


def _intervention_item(item: Any, now: float | None) -> DecisionItem:
    native_id = _native_id(item, "intervention_id", "tool_call_id")
    tool_name = str(_required(item, "tool_name"))
    remaining, timeout_at = _timeout_from_intervention(item, now)
    urgency = "expiring" if remaining is not None and remaining <= 60.0 else "blocking"
    receipt_refs = (str(_get(item, "event_id")),) if _get(item, "event_id") else ()

    detail = _as_detail(
        item,
        (
            "intervention_id",
            "tool_call_id",
            "tool_name",
            "tool_input",
            "event_id",
            "created_at",
            "timeout_seconds",
            "resolved",
            "decision",
            "reason",
        ),
    )

    return _make_item(
        kind="intervention",
        subsystem="runtime.intervention",
        native_id=native_id,
        session_ref=_get(item, "session_id"),
        created_at=_iso(_required(item, "created_at")),
        urgency=urgency,
        timeout_at=timeout_at,
        summary=f"Tool call requires approval: {tool_name}",
        detail=detail,
        options=_intervention_options(),
        receipt_refs=receipt_refs,
        why_ref=_get(item, "event_id"),
    )


def _violation_item(item: Any) -> DecisionItem:
    native_id = _native_id(item, "id")
    violations = _get(item, "violations", [])
    count = len(violations) if isinstance(violations, Sequence) else 0
    receipt_id = _get(item, "receipt_id")
    receipt_refs = (str(receipt_id),) if receipt_id else ()

    return _make_item(
        kind="violation",
        subsystem="violation_resolver",
        native_id=native_id,
        session_ref=_get(item, "run_id"),
        created_at=_iso(_required(item, "timestamp")),
        urgency="blocking",
        timeout_at=None,
        summary=f"Blocked response has {count} violation{'s' if count != 1 else ''}",
        detail=_as_detail(
            item,
            (
                "id",
                "context_id",
                "run_id",
                "violations",
                "blocked_response",
                "timestamp",
                "mode",
                "status",
                "receipt_id",
            ),
        ),
        options=_violation_options(),
        receipt_refs=receipt_refs,
        why_ref=str(receipt_id) if receipt_id else None,
    )


def _promotion_item(item: Any) -> DecisionItem:
    native_id = _native_id(item, "promotion_id")
    changed_files = _get(item, "changed_files", [])
    count = len(changed_files) if isinstance(changed_files, Sequence) else 0

    return _make_item(
        kind="promotion",
        subsystem="runtime.promotion",
        native_id=native_id,
        session_ref=_get(item, "session_id"),
        created_at=_iso(_required(item, "created_at")),
        urgency="normal",
        timeout_at=None,
        summary=f"Promotion awaiting decision for {count} changed file{'s' if count != 1 else ''}",
        detail=_as_detail(
            item,
            (
                "promotion_id",
                "session_id",
                "created_at",
                "status",
                "repo_path",
                "changed_files",
                "diff_stat",
                "diff_text",
                "decision_at",
                "decision_reason",
                "excluded_files",
            ),
        ),
        options=_promotion_options(),
    )


def _docket_case_item(item: Any) -> DecisionItem:
    native_id = _native_id(item, "case_number")
    case_type = _value(_get(item, "case_type", "case"))
    description = str(_get(item, "description", "Docket case awaiting ruling"))

    return _make_item(
        kind="docket_case",
        subsystem="docket",
        native_id=native_id,
        session_ref=None,
        created_at=_iso(_required(item, "created_at")),
        urgency="normal",
        timeout_at=None,
        summary=f"Docket {case_type}: {description}",
        detail=_as_detail(
            item,
            (
                "case_number",
                "case_type",
                "claim_id",
                "anchor_id",
                "status",
                "description",
                "evidence",
                "created_at",
                "blocked_content",
                "freshness_info",
            ),
        ),
        options=_docket_options(),
    )


def _admissibility_question_item(item: Any) -> DecisionItem:
    native_id = _native_id(item, "id")
    description = str(_get(item, "description", "Admissibility question"))

    return _make_item(
        kind="admissibility_question",
        subsystem="admissibility",
        native_id=native_id,
        session_ref=_get(item, "session_id"),
        created_at=_iso(_get(item, "created_at", "")),
        urgency="blocking",
        timeout_at=None,
        summary=description,
        detail=_as_detail(
            item,
            (
                "id",
                "description",
                "severity",
                "resolvable_by",
                "category",
                "created_at",
                "session_id",
            ),
        ),
        options=_admissibility_options(),
    )


def _operator_question_item(item: Any) -> DecisionItem:
    native_id = _native_id(item, "id", "question_id")
    subsystem = str(_get(item, "subsystem", "operator_question"))
    urgency = str(_get(item, "urgency", "normal"))
    if urgency not in URGENCIES:
        raise ValueError(f"unknown decision urgency: {urgency}")

    return _make_item(
        kind="operator_question",
        subsystem=subsystem,
        native_id=native_id,
        session_ref=_get(item, "session_id"),
        created_at=_iso(_required(item, "created_at")),
        urgency=urgency,
        timeout_at=_get(item, "timeout_at"),
        summary=str(_get(item, "summary", _get(item, "question", "Operator question"))),
        detail=dict(_get(item, "detail", {})),
        options=_operator_options(_required(item, "options")),
        receipt_refs=tuple(str(ref) for ref in _get(item, "receipt_refs", ())),
        why_ref=_get(item, "why_ref"),
        refs=tuple(_get(item, "refs", ())),
    )


def _operator_options(options: Sequence[Any]) -> tuple[DecisionOption, ...]:
    normalized: list[DecisionOption] = []
    for option in options:
        normalized.append(
            DecisionOption(
                key=str(_required(option, "key")),
                label=str(_required(option, "label")),
                action=str(_required(option, "action")),
                args_schema=_get(option, "args_schema"),
            )
        )
    return tuple(normalized)
