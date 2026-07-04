# SPDX-License-Identifier: Apache-2.0
"""First-class synthetic origin (Slice B-11.S1 — synthetic overnight conveyor).

A ``SyntheticOrigin`` is a no-process origin alongside ``stub``: it produces fake
inputs and exercises the positive run path, but executes no real process and
confers no live effect. It lets the overnight conveyor produce reviewable evidence
without a real cage or live Claude Code.

The load-bearing boundary: ``Synthetic safe ≠ live safe``. Adding ``synthetic`` to
the runnable set must NOT open the door to a live origin — ``live`` is still
refused at ``run()`` and at receipt construction.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.cooked_context_orchestrator import is_authority_admission_receipt
from governor.gate_receipt import GateReceiptSystem
from governor.playbooks.ration_card import DispatchRequest, RationCard
from governor.playbooks.rationed_runner import (
    GOVERNED_RATIONED_RUN_GATE,
    NO_PROCESS_ORIGINS,
    ORIGIN_KILLED,
    ORIGIN_OK,
    ORIGIN_STUB,
    ORIGIN_SYNTHETIC,
    ORIGIN_TIMED_OUT,
    RESULT_CONSUMED,
    RESULT_KILLED,
    RESULT_TIMED_OUT,
    OriginOutcome,
    RationedRunner,
    RationedRunReceipt,
)

_AGENT = "claude-code-runner-1"
_TASK = "read_only_audit"
_ADAPTER = "synthetic-adapter"
_TIMEOUT_MS = 30_000


# --------------------------------------------------------------------------- #
# Synthetic + live fakes.
# --------------------------------------------------------------------------- #


class FakeSyntheticOrigin:
    """A first-class synthetic origin: fake inputs, positive-path exercise, no real
    process. Declares ``origin_kind = "synthetic"``."""

    origin_kind = ORIGIN_SYNTHETIC

    def __init__(self, status=ORIGIN_OK):
        self.calls = 0
        self._status = status

    def run(self, request, *, timeout_ms, kill_switch) -> OriginOutcome:
        self.calls += 1
        if self._status == ORIGIN_TIMED_OUT:
            return OriginOutcome(
                status=ORIGIN_TIMED_OUT,
                transcript="synthetic run truncated at deadline",
                duration_ms=timeout_ms,
            )
        if self._status == ORIGIN_KILLED:
            return OriginOutcome(
                status=ORIGIN_KILLED, transcript="synthetic run killed mid-flight"
            )
        return OriginOutcome(
            status=ORIGIN_OK,
            transcript="synthetic audit produced fixture findings",
            produced_writes=frozenset({"reports/audit.json"}),
            exit_code=0,
            duration_ms=9,
        )


class FakeLiveOrigin:
    origin_kind = "live"

    def run(self, request, *, timeout_ms, kill_switch):  # pragma: no cover
        raise AssertionError("a live origin must never run without a confirmed-safe cage")


class NeverKilled:
    def tripped(self):
        return None


class KilledBeforeStart:
    def tripped(self):
        return "operator tripped before start"


class FakeClock:
    def __init__(self, start: int = 1000, step: int = 5):
        self.t = start
        self.step = step

    def __call__(self) -> int:
        v = self.t
        self.t += self.step
        return v


def _card() -> RationCard:
    return RationCard(
        agent_id=_AGENT,
        task_kind=_TASK,
        allowed_write_paths=frozenset({"reports/audit.json"}),
    )


def _request(**overrides) -> DispatchRequest:
    base = dict(
        agent_id=_AGENT,
        task_kind=_TASK,
        requested_write_paths=frozenset({"reports/audit.json"}),
    )
    base.update(overrides)
    return DispatchRequest(**base)


def _runner(origin, kill_switch=None, sink=None) -> RationedRunner:
    return RationedRunner(
        card=_card(),
        origin=origin,
        kill_switch=kill_switch or NeverKilled(),
        clock=FakeClock(),
        timeout_ms=_TIMEOUT_MS,
        adapter_id=_ADAPTER,
        receipt_sink=sink,
    )


def _run_receipts(sink: GateReceiptSystem):
    return [r for r in sink.receipt_store.all() if r.gate == GOVERNED_RATIONED_RUN_GATE]


# --------------------------------------------------------------------------- #
# Synthetic origin is first-class — same execution path as stub.
# --------------------------------------------------------------------------- #


class TestSyntheticOriginRuns:
    def test_synthetic_in_no_process_set(self):
        assert ORIGIN_SYNTHETIC in NO_PROCESS_ORIGINS
        assert ORIGIN_STUB in NO_PROCESS_ORIGINS
        assert "live" not in NO_PROCESS_ORIGINS

    def test_synthetic_origin_consumes_and_stamps_kind(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        origin = FakeSyntheticOrigin()
        receipt = _runner(origin, sink=sink).run(_request(), run_id="syn-1")

        assert origin.calls == 1
        assert receipt.result_status == RESULT_CONSUMED
        assert receipt.consumable_as_success is True
        # The receipt records the ACTUAL origin kind, not a hardcoded stub.
        assert receipt.origin_kind == ORIGIN_SYNTHETIC
        assert receipt.transcript_hash is not None
        assert receipt.output_hash is not None

    def test_synthetic_receipt_is_non_authoritative(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        _runner(FakeSyntheticOrigin(), sink=sink).run(_request(), run_id="syn-1")
        receipts = _run_receipts(sink)
        assert len(receipts) == 1
        gr = receipts[0]
        assert gr.verdict == "observe"
        assert is_authority_admission_receipt(gr) is False
        bundle = sink.evidence_for(gr)
        assert bundle["non_authoritative"] is True
        assert bundle["origin_kind"] == ORIGIN_SYNTHETIC

    def test_synthetic_origin_honours_timeout(self, tmp_path: Path):
        receipt = _runner(FakeSyntheticOrigin(status=ORIGIN_TIMED_OUT)).run(
            _request(), run_id="syn-1"
        )
        assert receipt.result_status == RESULT_TIMED_OUT
        assert receipt.timed_out is True
        assert receipt.consumable_as_success is False

    def test_synthetic_origin_honours_kill_before_start(self, tmp_path: Path):
        origin = FakeSyntheticOrigin()
        receipt = _runner(origin, KilledBeforeStart()).run(_request(), run_id="syn-1")
        assert origin.calls == 0
        assert receipt.result_status == RESULT_KILLED
        assert receipt.killed is True


# --------------------------------------------------------------------------- #
# Synthetic safe ≠ live safe — live stays refused.
# --------------------------------------------------------------------------- #


class TestSyntheticDoesNotOpenLive:
    def test_live_origin_still_refused_at_run(self):
        with pytest.raises(ValueError):
            _runner(FakeLiveOrigin()).run(_request(), run_id="live-1")

    def test_live_origin_kind_still_refused_on_receipt(self):
        with pytest.raises(ValueError):
            RationedRunReceipt(
                run_id="r",
                origin_kind="live",
                agent_id=_AGENT,
                adapter_id=_ADAPTER,
                ration_card_hash="h",
                input_hash="h",
                started_at=0,
                ended_at=1,
                duration_ms=1,
                timeout_ms=_TIMEOUT_MS,
                timed_out=False,
                killed=False,
                result_status=RESULT_CONSUMED,
            )

    def test_synthetic_origin_kind_now_valid_on_receipt(self):
        # Synthetic is admissible; this must NOT raise.
        receipt = RationedRunReceipt(
            run_id="r",
            origin_kind=ORIGIN_SYNTHETIC,
            agent_id=_AGENT,
            adapter_id=_ADAPTER,
            ration_card_hash="h",
            input_hash="h",
            started_at=0,
            ended_at=1,
            duration_ms=1,
            timeout_ms=_TIMEOUT_MS,
            timed_out=False,
            killed=False,
            result_status=RESULT_CONSUMED,
        )
        assert receipt.origin_kind == ORIGIN_SYNTHETIC
