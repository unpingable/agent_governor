# SPDX-License-Identifier: Apache-2.0
"""InprocRunner — deterministic in-process simulation runner."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .api import SimAPI
from .schema import TraceEvent

logger = logging.getLogger(__name__)


@dataclass
class SimClock:
    """Monotonic sim clock.  Base: epoch (1970-01-01T00:00:00Z).

    Sim time, not real time.  advance_to() enforces monotonicity.
    """

    _offset_ms: int = 0

    @property
    def now(self) -> datetime:
        """Current sim time as a UTC datetime."""
        return datetime.fromtimestamp(self._offset_ms / 1000.0, tz=timezone.utc)

    def advance_to(self, t_ms: int) -> None:
        """Advance clock to *at least* t_ms.  Raises on backwards jump."""
        if t_ms < self._offset_ms:
            raise ValueError(
                f"SimClock cannot go backwards: current {self._offset_ms}, requested {t_ms}"
            )
        self._offset_ms = t_ms


@dataclass
class RunResult:
    """Summary of a simulation run."""

    events_processed: int = 0
    assertion_results: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when no errors and all assertions passed."""
        if self.errors:
            return False
        return all(a.get("passed", False) for a in self.assertion_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "events_processed": self.events_processed,
            "assertion_results": self.assertion_results,
            "errors": self.errors,
            "passed": self.passed,
        }


class InprocRunner:
    """Run a compiled trace in-process against a real governor directory.

    Parameters
    ----------
    work_dir:
        Root directory containing (or to contain) the ``.governor/`` tree.
    params:
        Override thresholds forwarded to SimAPI.
    emit_signals:
        If True, derive and emit signal envelopes after the run completes.
        Default True — every sim run exercises the signal pipeline.
    """

    def __init__(
        self,
        work_dir: Path,
        params: dict[str, Any] | None = None,
        *,
        emit_signals: bool = True,
    ) -> None:
        self.work_dir = work_dir
        self.gov_dir = work_dir / ".governor"
        self.params = params or {}
        self.emit_signals = emit_signals
        self.clock = SimClock()
        self._fault_state: dict[str, bool] = {}
        self._api: SimAPI | None = None
        self.emitted_signals: list[Any] = []

    def _get_api(self) -> SimAPI:
        if self._api is None:
            self._init_governor()
            self._api = SimAPI(self.gov_dir, params=self.params)
        return self._api

    def _init_governor(self) -> None:
        """Ensure .governor/ directory exists with minimal structure."""
        self.gov_dir.mkdir(parents=True, exist_ok=True)
        receipts_dir = self.gov_dir / "receipts"
        receipts_dir.mkdir(exist_ok=True)

    def run(
        self,
        events: list[TraceEvent],
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        scenario: str | None = None,
    ) -> RunResult:
        """Execute events in order, return results summary.

        If emit_signals=True, derives signal envelopes from the run's
        receipts after execution completes. Emitted envelopes are stored
        in self.emitted_signals for inspection.
        """
        result = RunResult()

        # Sort by (t_ms, seq) to ensure deterministic ordering
        sorted_events = sorted(events, key=lambda e: (e.t_ms, e.seq))

        for event in sorted_events:
            try:
                self.clock.advance_to(event.t_ms)
                self._dispatch(event, result)
                result.events_processed += 1
            except Exception as exc:
                result.errors.append(f"event seq={event.seq}: {exc}")

        # Post-run signal emission
        if self.emit_signals:
            self._emit_post_run_signals(
                events=sorted_events,
                run_id=run_id,
                session_id=session_id,
                scenario=scenario,
            )

        return result

    def _emit_post_run_signals(
        self,
        events: list[TraceEvent],
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        scenario: str | None = None,
    ) -> None:
        """Derive and emit signals from the run's receipts."""
        from .signal_adapter import SimRunContext, derive_signals_from_run

        # Infer context from events if not provided
        _run_id = run_id or (events[0].run_id if events else None) or "unknown"
        _session_id = session_id or (events[0].session_id if events else None) or ""
        _scenario = scenario or (events[0].scenario if events else "unknown")

        # Window from sim clock (epoch-based)
        start_ms = events[0].t_ms if events else 0
        end_ms = events[-1].t_ms if events else 0
        window_start = datetime.fromtimestamp(start_ms / 1000.0, tz=timezone.utc).isoformat()
        window_end = datetime.fromtimestamp(end_ms / 1000.0, tz=timezone.utc).isoformat()

        ctx = SimRunContext(
            run_id=_run_id,
            session_id=_session_id,
            scenario=_scenario,
            window_start=window_start,
            window_end=window_end,
        )

        try:
            envelopes = derive_signals_from_run(self.gov_dir, ctx)
            self.emitted_signals.extend(envelopes)
        except Exception as exc:
            logger.warning("sim signal emission failed: %s", exc)

    def _dispatch(self, event: TraceEvent, result: RunResult) -> None:
        """Route an event to the appropriate handler."""
        handler = {
            "call": self._handle_call,
            "emit": self._handle_emit,
            "fault": self._handle_fault,
            "assert": self._handle_assert,
        }.get(event.event_type)

        if handler is None:
            raise ValueError(f"unknown event_type: {event.event_type!r}")

        handler(event, result)

    def _handle_call(self, event: TraceEvent, result: RunResult) -> None:
        """Dispatch a call event through SimAPI."""
        api = self._get_api()
        target = event.payload.get("target", "")

        # Fault injection: if gate_enabled is False, skip gate calls
        if target in ("gate_check", "evidence_gate.check"):
            if not self._fault_state.get("gate_enabled", True):
                logger.debug("fault: gate_enabled=False, skipping %s", target)
                return

        if target in ("gate_check", "evidence_gate.check"):
            api.gate_check(
                output=event.payload.get("output", ""),
                task=event.payload.get("task", ""),
                context=event.payload.get("context", "."),
            )
        elif target in ("gate_heartbeat",):
            session_active = event.payload.get("session_active", True)
            api.gate_heartbeat(
                now=self.clock.now,
                session_active=session_active,
            )
        else:
            raise ValueError(f"unknown call target: {target!r}")

    def _handle_emit(self, event: TraceEvent, result: RunResult) -> None:
        """Dispatch an emit event through SimAPI."""
        api = self._get_api()
        kind = event.payload.get("kind", "")

        if kind == "receipt":
            api.emit_receipt(
                event.payload.get("data", {}),
                timestamp=self.clock.now.isoformat(),
            )
        else:
            raise ValueError(f"unknown emit kind: {kind!r}")

    def _handle_fault(self, event: TraceEvent, result: RunResult) -> None:
        """Toggle a fault flag."""
        flag = event.payload.get("flag")
        value = event.payload.get("value", True)
        if not flag:
            raise ValueError("fault event must have payload.flag")
        self._fault_state[flag] = bool(value)
        logger.debug("fault: %s = %s", flag, value)

    def _handle_assert(self, event: TraceEvent, result: RunResult) -> None:
        """Evaluate a named assertion check."""
        api = self._get_api()
        check = event.payload.get("check", "")
        assertion_result: dict[str, Any] = {
            "check": check,
            "seq": event.seq,
            "t_ms": event.t_ms,
        }

        try:
            if check == "expect_stale":
                expected = event.payload.get("value", True)
                hb = api.gate_heartbeat(
                    now=self.clock.now,
                    session_active=event.payload.get("session_active", True),
                )
                actual = hb["is_stale"]
                assertion_result["passed"] = actual == expected
                assertion_result["expected"] = expected
                assertion_result["actual"] = actual

            elif check == "expect_receipt_count":
                expected = event.payload["value"]
                actual = api.receipt_count()
                assertion_result["passed"] = actual == expected
                assertion_result["expected"] = expected
                assertion_result["actual"] = actual

            elif check == "expect_missed_count":
                op = event.payload.get("op", "eq")
                expected = event.payload["value"]
                hb = api.gate_heartbeat(
                    now=self.clock.now,
                    session_active=event.payload.get("session_active", True),
                )
                actual = hb["missed_count"]
                assertion_result["passed"] = _compare(actual, op, expected)
                assertion_result["expected"] = f"{op} {expected}"
                assertion_result["actual"] = actual

            elif check == "expect_fault_state":
                flag = event.payload["flag"]
                expected = event.payload.get("value", True)
                actual = self._fault_state.get(flag, True)  # default: enabled
                assertion_result["passed"] = actual == expected
                assertion_result["expected"] = expected
                assertion_result["actual"] = actual

            else:
                assertion_result["passed"] = False
                assertion_result["error"] = f"unknown check: {check!r}"

        except Exception as exc:
            assertion_result["passed"] = False
            assertion_result["error"] = str(exc)

        result.assertion_results.append(assertion_result)


def _compare(actual: int, op: str, expected: int) -> bool:
    """Evaluate a comparison operation."""
    if op == "eq":
        return actual == expected
    if op == "gte":
        return actual >= expected
    if op == "lte":
        return actual <= expected
    if op == "gt":
        return actual > expected
    if op == "lt":
        return actual < expected
    raise ValueError(f"unknown comparison op: {op!r}")
