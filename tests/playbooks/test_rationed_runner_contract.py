# SPDX-License-Identifier: Apache-2.0
"""Stub-origin rationed-runner execution contract (Slice B-9/10 — collapsed).

The dispatch GATE (``test_ration_card_dispatch.py``) already covers admission /
spend / card / the seven laundering walls. This file covers ONLY the genuinely new
surface: how a single rationed run *executes* — success, timeout, kill-before-start,
kill-during-run, forbidden-authority refusal, the closed result vocabulary, and the
non-authoritative receipt shape.

Everything is driven by injected fakes. **No real sleeps, no subprocess, no cage.**
A "hang" is a fake origin reporting ``timed_out``; a "kill" is a fake kill switch the
runner / origin observes. ``TERM``-then-``KILL`` is not exercised here — it is future
cage-backend behaviour, represented only as the origin returning ``killed``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pytest

from governor.cooked_context_orchestrator import is_authority_admission_receipt
from governor.gate_receipt import GateReceiptSystem
from governor.playbooks.ration_card import DispatchRequest, RationCard
from governor.playbooks.rationed_runner import (
    GOVERNED_RATIONED_RUN_GATE,
    ORIGIN_FAILED,
    ORIGIN_KILLED,
    ORIGIN_OK,
    ORIGIN_STUB,
    ORIGIN_TIMED_OUT,
    RESULT_CONSUMED,
    RESULT_FAILED,
    RESULT_KILLED,
    RESULT_REFUSED,
    RESULT_TIMED_OUT,
    OriginOutcome,
    RationedRunner,
    RationedRunReceipt,
)

_AGENT = "claude-code-runner-1"
_TASK = "read_only_audit"
_ADAPTER = "stub-adapter"
_TIMEOUT_MS = 30_000


# --------------------------------------------------------------------------- #
# Fakes — origins, kill switches, clock. Deterministic; no real time.
# --------------------------------------------------------------------------- #


class _StubOrigin:
    """Base fake: declares the only origin kind this slice will run."""

    origin_kind = ORIGIN_STUB

    def __init__(self) -> None:
        self.calls = 0


class FakeSuccessfulOrigin(_StubOrigin):
    def run(self, request, *, timeout_ms, kill_switch) -> OriginOutcome:
        self.calls += 1
        return OriginOutcome(
            status=ORIGIN_OK,
            transcript="audited ok; no findings",
            produced_writes=frozenset({"reports/audit.json"}),
            exit_code=0,
            duration_ms=12,
        )


class FakeHangingOrigin(_StubOrigin):
    """Models a run that would hang: the (fake) backend bounds it by the timeout
    and reports ``timed_out`` with a partial transcript. No real sleep."""

    def run(self, request, *, timeout_ms, kill_switch) -> OriginOutcome:
        self.calls += 1
        return OriginOutcome(
            status=ORIGIN_TIMED_OUT,
            transcript="started audit... (truncated at deadline)",
            produced_writes=frozenset(),
            exit_code=None,
            duration_ms=timeout_ms,
        )


class FakeCooperativeOrigin(_StubOrigin):
    """Polls the kill switch during the run; if tripped, stops and reports
    ``killed`` with a partial transcript, else succeeds."""

    def run(self, request, *, timeout_ms, kill_switch) -> OriginOutcome:
        self.calls += 1
        reason = kill_switch.tripped()
        if reason:
            return OriginOutcome(
                status=ORIGIN_KILLED,
                transcript="started audit... (killed mid-run)",
                produced_writes=frozenset(),
                exit_code=None,
                duration_ms=7,
            )
        return OriginOutcome(status=ORIGIN_OK, transcript="ok", exit_code=0)


class FakeFailingOrigin(_StubOrigin):
    def run(self, request, *, timeout_ms, kill_switch) -> OriginOutcome:
        self.calls += 1
        return OriginOutcome(
            status=ORIGIN_FAILED,
            transcript="audit crashed",
            exit_code=3,
            duration_ms=4,
        )


class FakeLiveOrigin:
    """An origin that claims a non-stub kind — must be refused by the slice."""

    origin_kind = "live"

    def run(self, request, *, timeout_ms, kill_switch) -> OriginOutcome:  # pragma: no cover
        raise AssertionError("a live origin must never be run in the stub slice")


class NeverKilled:
    def tripped(self) -> Optional[str]:
        return None


class KilledBeforeStart:
    def tripped(self) -> Optional[str]:
        return "operator tripped the kill switch before start"


class KilledDuringRun:
    """Clean at the pre-start check, tripped on every subsequent poll — so the
    runner starts but the origin observes the kill mid-run."""

    def __init__(self) -> None:
        self._polls = 0

    def tripped(self) -> Optional[str]:
        self._polls += 1
        if self._polls <= 1:
            return None
        return "operator tripped the kill switch during the run"


class FakeClock:
    def __init__(self, start: int = 1000, step: int = 5) -> None:
        self.t = start
        self.step = step

    def __call__(self) -> int:
        v = self.t
        self.t += self.step
        return v


# --------------------------------------------------------------------------- #
# Builders.
# --------------------------------------------------------------------------- #


def _card(**overrides) -> RationCard:
    base = dict(
        agent_id=_AGENT,
        task_kind=_TASK,
        allowed_write_paths=frozenset({"reports/audit.json"}),
    )
    base.update(overrides)
    return RationCard(**base)


def _request(**overrides) -> DispatchRequest:
    base = dict(
        agent_id=_AGENT,
        task_kind=_TASK,
        requested_write_paths=frozenset({"reports/audit.json"}),
    )
    base.update(overrides)
    return DispatchRequest(**base)


def _runner(origin, kill_switch=None, *, card=None, sink=None, timeout_ms=_TIMEOUT_MS):
    return RationedRunner(
        card=card or _card(),
        origin=origin,
        kill_switch=kill_switch or NeverKilled(),
        clock=FakeClock(),
        timeout_ms=timeout_ms,
        adapter_id=_ADAPTER,
        receipt_sink=sink,
    )


def _run_receipts(sink: GateReceiptSystem):
    return [r for r in sink.receipt_store.all() if r.gate == GOVERNED_RATIONED_RUN_GATE]


# --------------------------------------------------------------------------- #
# Stub-origin success.
# --------------------------------------------------------------------------- #


class TestStubOriginSuccess:
    def test_one_invocation_consumed_with_hashes(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        origin = FakeSuccessfulOrigin()
        receipt = _runner(origin, sink=sink).run(_request(), run_id="run-1")

        assert origin.calls == 1
        assert receipt.result_status == RESULT_CONSUMED
        assert receipt.consumable_as_success is True
        assert receipt.timed_out is False
        assert receipt.killed is False
        assert receipt.exit_code == 0
        # Output + transcript reduced to digests; raw text never carried.
        assert receipt.transcript_hash is not None
        assert receipt.output_hash is not None
        assert receipt.origin_kind == ORIGIN_STUB

    def test_receipt_is_non_authoritative(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        _runner(FakeSuccessfulOrigin(), sink=sink).run(_request(), run_id="run-1")

        receipts = _run_receipts(sink)
        assert len(receipts) == 1
        gr = receipts[0]
        assert gr.verdict == "observe"
        assert is_authority_admission_receipt(gr) is False
        bundle = sink.evidence_for(gr)
        assert bundle["non_authoritative"] is True
        assert bundle["result_status"] == RESULT_CONSUMED
        # The transcript is a digest in the bundle; the raw text is not.
        assert "transcript_hash" in bundle
        assert "transcript" not in bundle


# --------------------------------------------------------------------------- #
# Timeout.
# --------------------------------------------------------------------------- #


class TestTimeout:
    def test_hanging_origin_is_bounded_and_not_success(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        origin = FakeHangingOrigin()
        receipt = _runner(origin, sink=sink).run(_request(), run_id="run-1")

        assert origin.calls == 1
        assert receipt.result_status == RESULT_TIMED_OUT
        assert receipt.timed_out is True
        assert receipt.killed is False
        assert receipt.consumable_as_success is False
        # A timed-out run mints no success output, but the partial transcript is
        # retained as a (tainted) digest.
        assert receipt.output_hash is None
        assert receipt.transcript_hash is not None
        assert len(_run_receipts(sink)) == 1


# --------------------------------------------------------------------------- #
# Kill — before start and during run.
# --------------------------------------------------------------------------- #


class TestKill:
    def test_kill_before_start_does_not_invoke_origin(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        origin = FakeSuccessfulOrigin()
        receipt = _runner(origin, KilledBeforeStart(), sink=sink).run(
            _request(), run_id="run-1"
        )

        assert origin.calls == 0  # refused before the origin is touched
        assert receipt.result_status == RESULT_KILLED
        assert receipt.killed is True
        assert receipt.consumable_as_success is False
        assert receipt.output_hash is None
        assert len(_run_receipts(sink)) == 1

    def test_kill_during_run_observed_by_origin(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        origin = FakeCooperativeOrigin()
        receipt = _runner(origin, KilledDuringRun(), sink=sink).run(
            _request(), run_id="run-1"
        )

        assert origin.calls == 1  # the run started, then observed the kill
        assert receipt.result_status == RESULT_KILLED
        assert receipt.killed is True
        assert receipt.consumable_as_success is False
        # Partial output/transcript marked non-success; transcript still digested.
        assert receipt.output_hash is None
        assert receipt.transcript_hash is not None


# --------------------------------------------------------------------------- #
# Origin failure.
# --------------------------------------------------------------------------- #


class TestOriginFailure:
    def test_failed_origin_is_not_success(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        receipt = _runner(FakeFailingOrigin(), sink=sink).run(_request(), run_id="run-1")
        assert receipt.result_status == RESULT_FAILED
        assert receipt.consumable_as_success is False
        assert receipt.exit_code == 3
        assert receipt.output_hash is None


# --------------------------------------------------------------------------- #
# Authority locks — smoke, not a re-test of all seven gate walls.
# --------------------------------------------------------------------------- #


class TestAuthorityLocks:
    def test_forbidden_authority_refused_before_execution(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path / "receipts")
        origin = FakeSuccessfulOrigin()
        # The request asks for git — locked closed by the card; refuse pre-exec.
        receipt = _runner(origin, sink=sink).run(
            _request(requested_git=True), run_id="run-1"
        )
        assert receipt.result_status == RESULT_REFUSED
        assert origin.calls == 0  # never executed
        assert receipt.consumable_as_success is False

    def test_receipt_carries_locks_false(self, tmp_path: Path):
        receipt = _runner(FakeSuccessfulOrigin()).run(_request(), run_id="run-1")
        assert receipt.git_allowed is False
        assert receipt.doctrine_allowed is False
        assert receipt.network_allowed is False

    def test_cage_fields_are_inert(self, tmp_path: Path):
        receipt = _runner(FakeSuccessfulOrigin()).run(_request(), run_id="run-1")
        assert receipt.sandbox_id is None
        assert receipt.write_manifest == ()
        assert receipt.forbidden_write_detected is False
        assert receipt.command_argv_hash is None


# --------------------------------------------------------------------------- #
# Receipt vocabulary + scope fence enforced by type.
# --------------------------------------------------------------------------- #


class TestReceiptShapeAndScopeFence:
    def test_unknown_result_status_refused(self):
        with pytest.raises(ValueError):
            RationedRunReceipt(
                run_id="r",
                origin_kind=ORIGIN_STUB,
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
                result_status="bogus",
            )

    def test_non_stub_origin_kind_refused_on_receipt(self):
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

    @pytest.mark.parametrize(
        "kw",
        [
            {"git_allowed": True},
            {"doctrine_allowed": True},
            {"network_allowed": True},
        ],
    )
    def test_authority_locks_cannot_be_opened_on_receipt(self, kw):
        with pytest.raises(ValueError):
            RationedRunReceipt(
                run_id="r",
                origin_kind=ORIGIN_STUB,
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
                **kw,
            )

    def test_runner_refuses_non_stub_origin(self):
        with pytest.raises(ValueError):
            _runner(FakeLiveOrigin()).run(_request(), run_id="run-1")
