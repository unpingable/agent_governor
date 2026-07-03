# SPDX-License-Identifier: Apache-2.0
"""Typed models for the shell contract, with the safe-defaults idiom.

A shell reads these off the wire; the daemon may be a newer or older version, so
``from_dict`` tolerates missing optional fields and IGNORES unknown ones (forward
compat) — but refuses an item with no ``decision_id``/``kind`` (a decision
envelope without an identity or a kind is not a decision). Unknown KINDS are
preserved as-is and flagged, never dropped and never guessed (the allowlist
recognition discipline: recognize, don't fabricate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# The closed decision-kind vocabulary the shell contract defines (v0 §1). A kind
# outside this set is rendered raw + flagged (`is_known_kind` False), never
# dropped, never guessed.
KNOWN_DECISION_KINDS = frozenset(
    {
        "intervention",
        "violation",
        "promotion",
        "docket_case",
        "admissibility_question",
        "operator_question",
    }
)

KNOWN_URGENCIES = frozenset({"blocking", "expiring", "normal", "info"})


def _as_dict(value: Any) -> dict:
    """A mapping field off the wire, or ``{}`` if the daemon sent a non-mapping.

    Safe-defaults discipline: a malformed payload (``detail: "x"``) degrades to
    empty, never crashes the shell that is trying to read past it."""
    return dict(value) if isinstance(value, dict) else {}


@dataclass(frozen=True)
class DecisionOption:
    key: str
    label: str
    action: str
    args_schema: dict | None = None

    @classmethod
    def from_dict(cls, d: dict) -> "DecisionOption":
        return cls(
            key=str(d.get("key", "")),
            label=str(d.get("label", "")),
            action=str(d.get("action", "")),
            args_schema=d.get("args_schema"),
        )


@dataclass(frozen=True)
class DecisionItem:
    decision_id: str
    kind: str
    session_ref: str | None
    created_at: str
    urgency: str
    summary: str
    timeout_at: str | None = None
    detail: dict = field(default_factory=dict)
    options: tuple[DecisionOption, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    why_ref: str | None = None
    refs: tuple[Any, ...] = ()
    source: dict = field(default_factory=dict)

    @property
    def is_known_kind(self) -> bool:
        """False for a kind outside the contract's closed set — render raw +
        flagged, never guess a handler for it."""
        return self.kind in KNOWN_DECISION_KINDS

    @property
    def is_interrupt(self) -> bool:
        """Whether this item should interrupt (bell) vs. accumulate silently.
        Interrupt on blocking/expiring; accumulate otherwise. An unknown urgency
        conservatively interrupts (better to over-surface than to silently bury)."""
        return self.urgency not in ("normal", "info")

    @classmethod
    def from_dict(cls, d: dict) -> "DecisionItem":
        # Required identity: a decision without an id or a kind is not routable.
        decision_id = d.get("decision_id")
        kind = d.get("kind")
        if not decision_id or not kind:
            raise ValueError(f"decision envelope missing decision_id/kind: {d!r}")
        return cls(
            decision_id=str(decision_id),
            kind=str(kind),
            session_ref=d.get("session_ref"),
            created_at=str(d.get("created_at", "")),
            urgency=str(d.get("urgency", "normal")),
            summary=str(d.get("summary", "")),
            timeout_at=d.get("timeout_at"),
            detail=_as_dict(d.get("detail")),
            options=tuple(
                DecisionOption.from_dict(o)
                for o in (d.get("options") or ())
                if isinstance(o, dict)
            ),
            receipt_refs=tuple(str(r) for r in d.get("receipt_refs") or ()),
            why_ref=d.get("why_ref"),
            refs=tuple(d.get("refs") or ()),
            source=_as_dict(d.get("source")),
        )


def decisions_from_response(result: dict) -> tuple[DecisionItem, ...]:
    """Parse an ``operator.decisions.list`` result into typed items."""
    return tuple(DecisionItem.from_dict(i) for i in result.get("items", ()))
