# SPDX-License-Identifier: Apache-2.0
"""DSL compiler: scenario spec → list[TraceEvent]."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schema import TraceEvent, TraceHeader

_DURATION_RE = re.compile(
    r"^(?:(\d+)m)?(?:(\d+)s)?(?:(\d+)ms)?$"
)


def parse_duration_ms(s: str) -> int:
    """Parse a duration string like '5m30s' or '200ms' into milliseconds.

    Supported units: m (minutes), s (seconds), ms (milliseconds).
    At least one component must be present.
    """
    s = s.strip()
    m = _DURATION_RE.match(s)
    if not m or not any(m.groups()):
        raise ValueError(f"invalid duration string: {s!r}")
    minutes = int(m.group(1) or 0)
    seconds = int(m.group(2) or 0)
    millis = int(m.group(3) or 0)
    return minutes * 60_000 + seconds * 1_000 + millis


def compile_scenario(spec: dict[str, Any]) -> tuple[TraceHeader, list[TraceEvent]]:
    """Compile a scenario spec dict into a TraceHeader and ordered event list.

    The spec must contain:
      - name: str (scenario name)
      - steps: list of step dicts
    Optional:
      - dsl_version: int (default 1)
      - seed: int (default 0)
      - params: dict of semantic knobs (heartbeat_interval, etc.)
      - actors: list[str] (actor tags, informational)
      - session_id: str
      - run_id: str
      - asserts: list of assertion dicts (appended after steps)
    """
    name = spec.get("name")
    if not name:
        raise ValueError("scenario spec must have a non-empty 'name'")

    header = TraceHeader(
        dsl_version=spec.get("dsl_version", 1),
        seed=spec.get("seed", 0),
        params=spec.get("params", {}),
    )

    session_id = spec.get("session_id")
    run_id = spec.get("run_id")
    steps = spec.get("steps", [])

    events: list[TraceEvent] = []
    seq = 0
    current_t_ms = 0

    for step in steps:
        # Skip comment-only steps (no type, just annotation)
        if "type" not in step:
            continue
        t_ms = _resolve_time(step, current_t_ms)
        current_t_ms = t_ms

        events.append(TraceEvent(
            t_ms=t_ms,
            seq=seq,
            scenario=name,
            event_type=step["type"],
            payload=step.get("payload", {}),
            actor=step.get("actor"),
            session_id=session_id,
            run_id=run_id,
        ))
        seq += 1

    # Compile asserts: appended after all steps at final t_ms
    asserts = spec.get("asserts", [])
    for assertion in asserts:
        events.append(TraceEvent(
            t_ms=current_t_ms,
            seq=seq,
            scenario=name,
            event_type="assert",
            payload=assertion,
            actor=assertion.get("actor"),
            session_id=session_id,
            run_id=run_id,
        ))
        seq += 1

    return header, events


def _resolve_time(step: dict[str, Any], current_t_ms: int) -> int:
    """Resolve absolute 't' or relative 'after' into absolute t_ms."""
    if "t" in step:
        return int(step["t"])
    if "after" in step:
        delta = parse_duration_ms(step["after"])
        return current_t_ms + delta
    raise ValueError(f"step must have 't' (absolute ms) or 'after' (duration): {step}")


def load_scenario(path: str | Path) -> dict[str, Any]:
    """Load a scenario spec from a JSON or YAML file.

    JSON always works. YAML requires PyYAML to be installed.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError(
                "PyYAML is required to load YAML scenario files. "
                "Install it with: pip install pyyaml"
            )
        return yaml.safe_load(text)  # type: ignore[no-any-return]

    return json.loads(text)  # type: ignore[no-any-return]
