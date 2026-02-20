# SPDX-License-Identifier: Apache-2.0
"""Trace event schema for governor_sim."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

VALID_EVENT_TYPES = frozenset({"call", "emit", "fault", "assert"})


@dataclass(frozen=True)
class TraceHeader:
    """Top-line header for a compiled trace.

    Captures everything that affects replay semantics so old traces don't
    silently run under new rules.

    dsl_version:          Schema version for the DSL itself.
    seed:                 PRNG seed for determinism.
    params:               Semantic knobs active at compile time — heartbeat
                          interval, grace period, stale threshold, etc.
                          Replayed traces MUST use the params recorded here,
                          not whatever the current governor defaults are.
    """

    dsl_version: int = 1
    seed: int = 0
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "dsl_version": self.dsl_version,
            "seed": self.seed,
        }
        if self.params:
            d["params"] = self.params
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TraceHeader:
        return cls(
            dsl_version=d.get("dsl_version", 1),
            seed=d.get("seed", 0),
            params=d.get("params", {}),
        )


@dataclass(frozen=True)
class TraceEvent:
    """Single event in a simulation trace.

    t_ms:       Absolute monotonic milliseconds (epoch-based sim time).
    seq:        Monotonic integer assigned at compile-time; breaks ties at same t_ms.
    scenario:   Name of the scenario this event belongs to.
    event_type: One of "call", "emit", "fault", "assert".
    payload:    Arbitrary dict carried by the event.
    actor:      Optional actor tag (None for env-level events).
    session_id: Optional session identifier.
    run_id:     Optional run identifier.
    """

    t_ms: int
    seq: int
    scenario: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    actor: str | None = None
    session_id: str | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        if self.t_ms < 0:
            raise ValueError(f"t_ms must be >= 0, got {self.t_ms}")
        if self.seq < 0:
            raise ValueError(f"seq must be >= 0, got {self.seq}")
        if self.event_type not in VALID_EVENT_TYPES:
            raise ValueError(
                f"event_type must be one of {sorted(VALID_EVENT_TYPES)}, "
                f"got {self.event_type!r}"
            )
        if not self.scenario:
            raise ValueError("scenario must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "t_ms": self.t_ms,
            "seq": self.seq,
            "scenario": self.scenario,
            "event_type": self.event_type,
            "payload": self.payload,
        }
        if self.actor is not None:
            d["actor"] = self.actor
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.run_id is not None:
            d["run_id"] = self.run_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TraceEvent:
        return cls(
            t_ms=d["t_ms"],
            seq=d["seq"],
            scenario=d["scenario"],
            event_type=d["event_type"],
            payload=d.get("payload", {}),
            actor=d.get("actor"),
            session_id=d.get("session_id"),
            run_id=d.get("run_id"),
        )

    def to_json_line(self) -> str:
        """Canonical JSON line: sorted keys, compact separators."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
