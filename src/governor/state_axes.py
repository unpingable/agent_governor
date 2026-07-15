# SPDX-License-Identifier: Apache-2.0
"""Closed vocabulary for the six portfolio state axes.

Ruled 2026-07-15 (operator), following the six-axis audit finding that axis
values were free-form strings: two records saying the same thing in different
words counted as different states, and nothing stopped a session from minting
a new de-facto state (two were minted *during* the audit itself). This module
closes the domain the same way ``operator_mode`` was closed: an allowlist per
axis, where a novel string is a typed violation — never a new state.

**Single canonical home per fact.** The canonical machine-readable home for a
record's six-axis state is its ``current_disposition.state_axes`` block — in
the backlog stub for campaign/slice records, in the specimen's
``current_disposition.json`` for specimen records, in ``loop.json`` for the
loop itself. Campaign ``STATUS.md`` prose ``State axes:`` lines are
*projections* of that home: they must agree with it, and the checker in
``portfolio_audit`` flags divergence. Prose never outranks the stub.

**Value vs detail.** The closed ``state`` carries the load-bearing class; the
free-text ``detail`` carries the nuance that used to be packed into strings
like ``ns1_closed_unpushed``. Compression lives in the vocabulary, precision
lives in the detail — never the reverse.

Vocabulary changes are custody-affecting (cross-module vocabulary): extend by
commit with a stated forcing case, not ad hoc from a session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

AXIS_VOCABULARY_VERSION = "ag-state-axes-vocab/v1"

#: The six axes, in canonical order. This tuple is the closed set of axis
#: NAMES; ``AXIS_VOCABULARY`` closes the value domain per axis.
AXES: tuple[str, ...] = (
    "admission",
    "selection",
    "plan_approval",
    "runtime_activity",
    "effect_authority",
    "custody",
)

#: Closed per-axis value sets. ``unknown`` is a member everywhere: absent
#: evidence stays unknown, and unknown is an honest state, not a violation.
#: ``not_determined`` is distinct — it means "looked, could not determine",
#: where ``unknown`` means "never projected".
AXIS_VOCABULARY: dict[str, frozenset[str]] = {
    "admission": frozenset(
        {"ratified", "admitted", "unverifiable", "not_applicable", "not_determined", "unknown"}
    ),
    "selection": frozenset({"selected", "unselected", "not_applicable", "unknown"}),
    "plan_approval": frozenset(
        {
            "attached",
            "retained_historical",
            "none",
            "unverifiable",
            "not_applicable",
            "not_determined",
            "unknown",
        }
    ),
    "runtime_activity": frozenset(
        {"active", "inactive", "terminal", "not_evidenced", "not_applicable", "unknown"}
    ),
    "effect_authority": frozenset(
        {
            "live_grant",
            "none_evidenced",
            "terminal_no_live_grant",
            "not_applicable",
            "not_determined",
            "unknown",
        }
    ),
    "custody": frozenset(
        {"complete", "partial", "open", "stale_marker", "not_determined", "unknown"}
    ),
}

#: Explicit, total migration map over every legacy free-form value observed in
#: the repository at closure time (2026-07-15 six-axis audit). Each entry maps
#: a legacy string to ``(closed_value, detail_or_None)`` — the nuance the old
#: string packed into its name moves into ``detail``. A legacy value absent
#: from this map AND absent from the vocabulary is unmapped: migration refuses
#: (``UnmappedAxisValueError``) rather than guessing. Closed values map to
#: themselves (idempotence), added programmatically below.
LEGACY_VALUE_MAP: dict[str, dict[str, tuple[str, str | None]]] = {
    "admission": {
        "unverifiable_exact_artifact": ("unverifiable", "exact artifact unverifiable"),
    },
    "selection": {},
    "plan_approval": {
        "approved_record_retained": (
            "retained_historical",
            "approved record retained without consumption state",
        ),
        "none_recorded": ("none", None),
        "not_applicable_completed": ("not_applicable", "completed run"),
        "not_attached_to_unselected_remainders": (
            "none",
            "not attached to unselected remainders",
        ),
        "ns1_unverifiable_ns2_6_not_attached": (
            "unverifiable",
            "NS-1 exact approved artifact unverifiable; NS-2..6 not attached",
        ),
        "unverifiable_exact_artifact": ("unverifiable", "exact artifact unverifiable"),
    },
    "runtime_activity": {},
    "effect_authority": {
        "none_recorded": ("none_evidenced", None),
        "not_applicable_completed": ("not_applicable", "completed run"),
        "not_evidenced_for_new_effect": ("none_evidenced", "no new-effect grant evidenced"),
        "not_evidenced_for_unselected_packets": (
            "none_evidenced",
            "for unselected packets",
        ),
        "not_evidenced_for_unselected_remainders": (
            "none_evidenced",
            "for unselected remainders",
        ),
        "terminal_no_live_grant_evidenced": ("terminal_no_live_grant", None),
    },
    "custody": {
        "current": ("complete", "record custody reconciled current"),
        "ns1_closed_unpushed": (
            "partial",
            "NS-1 impl closed at nightshift e71303f (local, unpushed); "
            "S1-S7 closed; NS-2..6 unbuilt",
        ),
        "impl_closed_unpushed_approval_unverifiable": (
            "partial",
            "implementation closed (local, unpushed); approval custody unverifiable",
        ),
    },
}
for _axis, _values in AXIS_VOCABULARY.items():
    for _value in _values:
        LEGACY_VALUE_MAP[_axis].setdefault(_value, (_value, None))


class UnmappedAxisValueError(ValueError):
    """A legacy axis value has no explicit mapping — refuse, never guess."""


@dataclass(frozen=True)
class AxisViolation:
    """One typed vocabulary violation on a projected record."""

    kind: str  # "unknown_axis" | "novel_value" | "malformed"
    axis: str
    value: str

    def describe(self) -> str:
        if self.kind == "unknown_axis":
            return f"axis {self.axis!r} is not one of the six closed axes"
        if self.kind == "novel_value":
            allowed = ", ".join(sorted(AXIS_VOCABULARY[self.axis]))
            return (
                f"{self.axis}={self.value!r} is not in the closed vocabulary "
                f"({allowed}); a novel string never mints a state — extend the "
                f"vocabulary by commit or carry the nuance in detail"
            )
        return f"{self.axis} carries a malformed value {self.value!r}"


def validate_state_axes(axes: Mapping[str, Any]) -> list[AxisViolation]:
    """Validate a raw ``state_axes`` mapping against the closed vocabulary.

    Accepts both compact (``axis: "value"``) and nested
    (``axis: {"state": "value", ...}``) forms — the same shapes
    ``portfolio_audit.normalize_state_axes`` accepts.
    """

    violations: list[AxisViolation] = []
    for axis, raw in axes.items():
        if axis not in AXIS_VOCABULARY:
            violations.append(AxisViolation("unknown_axis", axis, str(raw)))
            continue
        if isinstance(raw, str):
            value = raw
        elif isinstance(raw, Mapping) and isinstance(raw.get("state"), str):
            value = raw["state"]
        else:
            violations.append(AxisViolation("malformed", axis, repr(raw)))
            continue
        if value not in AXIS_VOCABULARY[axis]:
            violations.append(AxisViolation("novel_value", axis, value))
    return violations


def migrate_axis_value(axis: str, value: str) -> tuple[str, str | None]:
    """Map one legacy value to ``(closed_value, detail)``.

    Total over the explicit map; anything else refuses. Idempotent on
    already-closed values.
    """

    if axis not in LEGACY_VALUE_MAP:
        raise UnmappedAxisValueError(f"unknown axis {axis!r}")
    try:
        return LEGACY_VALUE_MAP[axis][value]
    except KeyError:
        raise UnmappedAxisValueError(
            f"{axis}={value!r} has no explicit migration mapping; refusing to guess"
        ) from None


def migrate_state_axes(axes: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    """Rewrite a ``state_axes`` mapping into closed-vocabulary form.

    Returns ``(new_axes, changed)``. String values whose migration yields a
    detail become nested ``{"state", "detail"}`` objects; nested values keep
    their ``basis``/``evidence``/existing ``detail`` (an existing detail is
    never overwritten — the mapped detail is appended only when absent).
    """

    migrated: dict[str, Any] = {}
    changed = False
    for axis, raw in axes.items():
        if isinstance(raw, str):
            closed, detail = migrate_axis_value(axis, raw)
            if detail is None:
                migrated[axis] = closed
                changed = changed or closed != raw
            else:
                migrated[axis] = {"state": closed, "detail": detail}
                changed = True
        elif isinstance(raw, Mapping) and isinstance(raw.get("state"), str):
            closed, detail = migrate_axis_value(axis, raw["state"])
            entry = dict(raw)
            entry["state"] = closed
            if detail is not None and not entry.get("detail"):
                entry["detail"] = detail
            migrated[axis] = entry
            changed = changed or entry != dict(raw)
        else:
            migrated[axis] = raw  # malformed: preserved verbatim, flagged by validate
    return migrated, changed


@dataclass(frozen=True)
class ProseAxisBlock:
    """One ``State axes:`` (or drifted-header) block found in prose."""

    header: str  # the literal header label, e.g. "State axes" / "Current axes"
    line_number: int  # 1-indexed line of the header
    values: dict[str, str]  # axis -> backticked value token


_CANONICAL_PROSE_HEADER = "State axes"


def parse_prose_axis_blocks(text: str) -> list[ProseAxisBlock]:
    """Extract axis blocks from campaign STATUS prose.

    A block starts at the first line CONTAINING ``<Header> axes:`` (searched
    anywhere in the line, not just at line start — a drifted header buried
    mid-paragraph must still be visible to the checker, or indentation becomes
    a dodge) and extends until a blank line. Values are the backticked tokens
    in ``axis=`value``` pairs; parenthetical detail after the backtick is
    prose, not compared. A candidate block is kept only when it carries at
    least one recognized axis token, so generic prose about "axes" never
    false-positives. Blocks after the first are historical (superseded
    copies) — callers wanting the current projection take ``blocks[0]``.
    """

    import re

    blocks: list[ProseAxisBlock] = []
    lines = text.splitlines()
    header_re = re.compile(r"\b([A-Z][A-Za-z]*(?: [a-z]+)?) axes:", re.ASCII)
    pair_re = re.compile(r"(\w+)=`([^`]+)`")
    i = 0
    while i < len(lines):
        match = header_re.search(lines[i])
        if not match:
            i += 1
            continue
        header = f"{match.group(1)} axes"
        start = i
        chunk: list[str] = [lines[i][match.start():]]
        i += 1
        while i < len(lines) and lines[i].strip():
            chunk.append(lines[i])
            i += 1
        values = dict(pair_re.findall("\n".join(chunk)))
        axis_values = {k: v for k, v in values.items() if k in AXES}
        if axis_values:
            blocks.append(ProseAxisBlock(header, start + 1, axis_values))
    return blocks


def current_prose_block(text: str) -> ProseAxisBlock | None:
    """The first (current-projection) axis block in a prose document."""

    blocks = parse_prose_axis_blocks(text)
    return blocks[0] if blocks else None


def is_canonical_prose_header(block: ProseAxisBlock) -> bool:
    return block.header == _CANONICAL_PROSE_HEADER


def all_vocabulary_values() -> Iterable[tuple[str, str]]:
    """Every (axis, value) pair in the closed vocabulary — for tests/tools."""

    for axis in AXES:
        for value in sorted(AXIS_VOCABULARY[axis]):
            yield axis, value
