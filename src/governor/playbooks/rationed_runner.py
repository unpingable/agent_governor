# SPDX-License-Identifier: Apache-2.0
"""Stub-origin rationed-runner execution contract (Slice B-9/10 — collapsed).

> Tiny door, big lock; this slice adds the part that watches the clock and the
> kill switch — and nothing that touches a real process.

The dispatch GATE (``ration_card.py``) decides *whether* an external agent may be
dispatched (admission · durable spend · card · output fence). This module governs
*how a single rationed run executes*: it bounds the run by a timeout, honours a
kill switch, and reduces the outcome to a structured, **non-authoritative**
receipt. The two compose later; this slice builds only the execution contract.

SCOPE FENCE — enforced by type, not by comment:

- **no-process origins only** (``origin_kind`` ∈ ``{stub, synthetic}``). A live
  origin is refused at receipt construction and at ``run()`` — it needs a
  confirmed-safe cage (see ``sandbox_cage.admit_origin_under_cage``), a future
  separately-gated slice. ``Synthetic safe ≠ live safe``: a synthetic origin
  exercises the positive admission path with fake inputs and confers no live
  effect, so the overnight conveyor can produce reviewable evidence — never facts.
- git / doctrine / network authority is locked **False** on every receipt; a
  receipt that tries to carry it is refused by type.
- timeout and kill are modelled through an **injected** ``ExecutionOrigin`` +
  ``KillSwitch`` + ``Clock``. **Python is not a sandbox.** Real ``TERM``-then-
  ``KILL`` and real process / wall-clock bounding belong to a future cage backend;
  here they are interface *intent* a fake backend satisfies, never claimed as real
  process control. Cage-only receipt fields (``sandbox_id``, ``write_manifest``,
  ``forbidden_write_detected``, ``command_argv_hash``) are present but explicitly
  **inert** — better an honest null than a fabricated sandbox id that teaches the
  codebase to lie in JSON.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional, Protocol

from governor.gate_receipt import canonical_json, content_hash

from .ration_card import DispatchRequest, RationCard, match_ration_card

# --------------------------------------------------------------------------- #
# Vocabulary (closed).
# --------------------------------------------------------------------------- #

ORIGIN_STUB = "stub"  # a test-double origin: no real process, no safety claim
ORIGIN_SYNTHETIC = "synthetic"  # first-class fixture/overnight origin: fake inputs,
# positive-path exercise; no real process / network / secrets / live repo authority

# Origins that execute NO real OS process, and so are runnable WITHOUT a real cage.
# Any other kind (e.g. a live adapter) requires a confirmed-safe cage — a future,
# separately-gated slice. ``Synthetic safe ≠ live safe``: a synthetic run exercises
# the positive admission path and produces reviewable evidence, never live effect.
NO_PROCESS_ORIGINS = frozenset({ORIGIN_STUB, ORIGIN_SYNTHETIC})

RUNNER_RECEIPT_VERSION = "rationed_run.v0"

# The run receipt is its own gate, always observe — a run record decides nothing
# and authorizes nothing (it fails ``is_authority_admission_receipt`` by gate).
GOVERNED_RATIONED_RUN_GATE = "governed_rationed_run"
GOVERNED_RATIONED_RUN_VERDICT = "observe"

# result_status — the closed outcome vocabulary for a rationed run.
RESULT_CONSUMED = "consumed"  # ran to completion; the ONLY consumable-as-success state
RESULT_TIMED_OUT = "timed_out"  # bounded by the timeout; not a success
RESULT_KILLED = "killed"  # kill switch tripped (before or during); not a success
RESULT_REFUSED = "refused"  # refused before execution (forbidden authority / card)
RESULT_FAILED = "failed"  # origin ran but reported failure
RUN_RESULT_STATUSES = frozenset(
    {
        RESULT_CONSUMED,
        RESULT_TIMED_OUT,
        RESULT_KILLED,
        RESULT_REFUSED,
        RESULT_FAILED,
    }
)
SUCCESS_STATUS = RESULT_CONSUMED

# origin status — what an ``ExecutionOrigin`` reports back to the runner.
ORIGIN_OK = "ok"
ORIGIN_TIMED_OUT = "timed_out"
ORIGIN_KILLED = "killed"
ORIGIN_FAILED = "failed"
ORIGIN_STATUSES = frozenset({ORIGIN_OK, ORIGIN_TIMED_OUT, ORIGIN_KILLED, ORIGIN_FAILED})

_ORIGIN_TO_RESULT = {
    ORIGIN_OK: RESULT_CONSUMED,
    ORIGIN_TIMED_OUT: RESULT_TIMED_OUT,
    ORIGIN_KILLED: RESULT_KILLED,
    ORIGIN_FAILED: RESULT_FAILED,
}


# --------------------------------------------------------------------------- #
# Injected seams: origin backend, kill switch, clock.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class OriginOutcome:
    """What an ``ExecutionOrigin`` reports. ``transcript`` is opaque text (may be
    partial on a timeout/kill); ``produced_writes`` is what it claims to have
    written. None of it is authority — the runner reduces it to a digest."""

    status: str
    transcript: Optional[str] = None
    produced_writes: frozenset[str] = field(default_factory=frozenset)
    exit_code: Optional[int] = None
    duration_ms: int = 0

    def __post_init__(self) -> None:
        if self.status not in ORIGIN_STATUSES:
            raise ValueError(
                f"origin status {self.status!r} not in {sorted(ORIGIN_STATUSES)}"
            )


class ExecutionOrigin(Protocol):
    """The injected backend that actually runs the one task. In production a thin
    wrapper over a ``runtime.RuntimeAdapter`` inside a real cage; in this slice a
    deterministic fake. It is responsible for honouring ``timeout_ms`` and polling
    ``kill_switch`` — the runner does not pre-empt a running origin (that is real
    process control, which lives in the future cage, not here)."""

    origin_kind: str

    def run(
        self,
        request: DispatchRequest,
        *,
        timeout_ms: int,
        kill_switch: "KillSwitch",
    ) -> OriginOutcome: ...


class KillSwitch(Protocol):
    """Fail-closed kill switch. ``tripped()`` returns a reason string if the run
    must not proceed / must stop, else ``None``. Consulted by the runner *before*
    start and by the origin *during* the run. The runner never clears it."""

    def tripped(self) -> Optional[str]: ...


# An injected logical monotonic clock returning milliseconds. Deterministic in
# tests; a real monotonic source in production. (Not the typed clock-witness
# basis — a run duration is a local stamp, not a spendability gap.)
Clock = Callable[[], int]


# --------------------------------------------------------------------------- #
# The structured, non-authoritative run receipt.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RationedRunReceipt:
    """The structured outcome of one rationed run. Non-authoritative by
    construction: stub origin, authority locks False, success is exactly
    ``result_status == consumed``."""

    run_id: str
    origin_kind: str
    agent_id: str
    adapter_id: str
    ration_card_hash: str
    input_hash: str
    started_at: int
    ended_at: int
    duration_ms: int
    timeout_ms: int
    timed_out: bool
    killed: bool
    result_status: str
    output_hash: Optional[str] = None
    transcript_hash: Optional[str] = None
    exit_code: Optional[int] = None
    # Authority locks — False, and may not be opened in this slice.
    git_allowed: bool = False
    doctrine_allowed: bool = False
    network_allowed: bool = False
    receipt_version: str = RUNNER_RECEIPT_VERSION
    # Cage-only fields: present but INERT (no sandbox exists yet). Do not populate
    # these with plausible-looking values — an honest null beats a fabricated cage.
    sandbox_id: Optional[str] = None
    write_manifest: tuple[str, ...] = ()
    forbidden_write_detected: bool = False
    command_argv_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if self.result_status not in RUN_RESULT_STATUSES:
            raise ValueError(
                f"result_status {self.result_status!r} not in {sorted(RUN_RESULT_STATUSES)}"
            )
        if self.origin_kind not in NO_PROCESS_ORIGINS:
            raise ValueError(
                f"origin_kind {self.origin_kind!r}: only no-process origins "
                f"{sorted(NO_PROCESS_ORIGINS)} may mint a run receipt; a live origin "
                "requires a confirmed-safe cage (future, separately-gated slice)"
            )
        if self.git_allowed or self.doctrine_allowed or self.network_allowed:
            raise ValueError(
                "a rationed run cannot carry git / doctrine / network authority "
                "(locked False by type in this slice)"
            )

    @property
    def consumable_as_success(self) -> bool:
        """A timed_out / killed / failed / refused run is NOT a success and must
        not be consumed as one — only ``consumed`` is."""
        return self.result_status == SUCCESS_STATUS


# --------------------------------------------------------------------------- #
# Hashing helpers (digest-only; raw bytes never become a claim).
# --------------------------------------------------------------------------- #


def _hash(obj: dict[str, Any]) -> str:
    return content_hash(canonical_json(obj))


def ration_card_hash(card: RationCard) -> str:
    return _hash(
        {
            "agent_id": card.agent_id,
            "task_kind": card.task_kind,
            "allowed_write_paths": sorted(card.allowed_write_paths),
            "allowed_shell_commands": sorted(card.allowed_shell_commands),
            "git_allowed": card.git_allowed,
            "doctrine_writes_allowed": card.doctrine_writes_allowed,
            "network_allowed": card.network_allowed,
            "output_is_observe_only": card.output_is_observe_only,
        }
    )


def dispatch_request_hash(request: DispatchRequest) -> str:
    return _hash(
        {
            "agent_id": request.agent_id,
            "task_kind": request.task_kind,
            "requested_write_paths": sorted(request.requested_write_paths),
            "requested_shell_commands": sorted(request.requested_shell_commands),
            "requested_network": request.requested_network,
            "requested_git": request.requested_git,
        }
    )


# --------------------------------------------------------------------------- #
# The runner.
# --------------------------------------------------------------------------- #


@dataclass
class RationedRunner:
    """Executes ONE rationed run against an injected no-process origin (stub or
    synthetic), bounded by a timeout and a kill switch, and reduces it to a
    non-authoritative receipt.

    The order encodes the guarantees:

    1. **no-process origins only** — a live origin is refused before anything runs
       (it requires a confirmed-safe cage, a future separately-gated slice).
    2. **forbidden authority / out-of-card** — refused *before execution* (smoke
       of the card's authority locks; the dispatch gate owns the full ⊆-card
       fence, not duplicated here).
    3. **kill before start** — the kill switch is consulted first; tripped ⇒ the
       origin is never invoked, the receipt is ``killed``.
    4. **bounded execution** — the origin runs once, honouring the timeout and
       polling the kill switch; its reported status maps to the run status.
    5. **non-authoritative receipt** — observe verdict; transcript reduced to a
       digest; output_hash only when ``consumed``.
    """

    card: RationCard
    origin: ExecutionOrigin
    kill_switch: KillSwitch
    clock: Clock
    timeout_ms: int
    adapter_id: str
    receipt_sink: Any | None = None

    def run(self, request: DispatchRequest, *, run_id: str) -> RationedRunReceipt:
        # 1. no-process origins only — the runner cannot run a live origin (that
        #    requires a confirmed-safe cage; see sandbox_cage.admit_origin_under_cage).
        origin_kind = getattr(self.origin, "origin_kind", None)
        if origin_kind not in NO_PROCESS_ORIGINS:
            raise ValueError(
                f"origin_kind {origin_kind!r}: the runner runs only no-process origins "
                f"{sorted(NO_PROCESS_ORIGINS)}; a live origin requires a confirmed-safe cage"
            )

        started = self.clock()

        # 2. forbidden authority / out-of-card — refuse before any execution.
        violation = match_ration_card(self.card, request)
        if violation is not None:
            return self._finish(
                RESULT_REFUSED, request, run_id, started, self.clock(), detail=violation
            )

        # 3. kill before start — refusal wins before the origin is touched.
        pre_kill = self.kill_switch.tripped()
        if pre_kill:
            return self._finish(
                RESULT_KILLED,
                request,
                run_id,
                started,
                self.clock(),
                killed=True,
                detail=f"kill switch tripped before start: {pre_kill}",
            )

        # 4. bounded execution — the origin honours timeout + kill switch.
        outcome = self.origin.run(
            request, timeout_ms=self.timeout_ms, kill_switch=self.kill_switch
        )
        status = _ORIGIN_TO_RESULT[outcome.status]
        return self._finish(
            status,
            request,
            run_id,
            started,
            self.clock(),
            outcome=outcome,
            timed_out=(outcome.status == ORIGIN_TIMED_OUT),
            killed=(outcome.status == ORIGIN_KILLED),
        )

    # ------------------------------------------------------------------ #

    def _finish(
        self,
        status: str,
        request: DispatchRequest,
        run_id: str,
        started: int,
        ended: int,
        *,
        outcome: Optional[OriginOutcome] = None,
        killed: bool = False,
        timed_out: bool = False,
        detail: Optional[str] = None,
    ) -> RationedRunReceipt:
        transcript = outcome.transcript if outcome is not None else None
        produced = outcome.produced_writes if outcome is not None else frozenset()
        exit_code = outcome.exit_code if outcome is not None else None

        # A partial transcript (timeout/kill) is still reduced to a digest for
        # audit, but the status (≠ consumed) marks it non-success / tainted.
        transcript_hash = (
            _hash({"transcript": transcript}) if transcript is not None else None
        )
        # output_hash is a SUCCESS artifact only — never minted for a non-success.
        output_hash = (
            _hash({"writes": sorted(produced)})
            if status == RESULT_CONSUMED and produced
            else None
        )

        receipt = RationedRunReceipt(
            run_id=run_id,
            origin_kind=self.origin.origin_kind,
            agent_id=request.agent_id,
            adapter_id=self.adapter_id,
            ration_card_hash=ration_card_hash(self.card),
            input_hash=dispatch_request_hash(request),
            started_at=started,
            ended_at=ended,
            duration_ms=max(0, ended - started),
            timeout_ms=self.timeout_ms,
            timed_out=timed_out,
            killed=killed,
            result_status=status,
            output_hash=output_hash,
            transcript_hash=transcript_hash,
            exit_code=exit_code,
        )
        self._emit(receipt, detail=detail)
        return receipt

    def _emit(self, receipt: RationedRunReceipt, *, detail: Optional[str]) -> None:
        if self.receipt_sink is None:
            return
        bundle: dict[str, Any] = {
            "record_kind": "rationed_run",
            "non_authoritative": True,
            "detail": detail,
            **asdict(receipt),
        }
        subject_bytes = (
            f"{receipt.run_id}|{receipt.agent_id}|{receipt.result_status}"
        ).encode("utf-8")
        self.receipt_sink.emit(
            gate=GOVERNED_RATIONED_RUN_GATE,
            verdict=GOVERNED_RATIONED_RUN_VERDICT,
            subject_kind="governed_rationed_run",
            subject_bytes=subject_bytes,
            evidence_bundle=bundle,
            gate_config={
                "seam": "rationed_runner",
                "origin_kind": receipt.origin_kind,
                "slice": "B11_S1_no_process_origins",
            },
        )


__all__ = [
    "ORIGIN_STUB",
    "ORIGIN_SYNTHETIC",
    "NO_PROCESS_ORIGINS",
    "RUNNER_RECEIPT_VERSION",
    "GOVERNED_RATIONED_RUN_GATE",
    "GOVERNED_RATIONED_RUN_VERDICT",
    "RESULT_CONSUMED",
    "RESULT_TIMED_OUT",
    "RESULT_KILLED",
    "RESULT_REFUSED",
    "RESULT_FAILED",
    "RUN_RESULT_STATUSES",
    "SUCCESS_STATUS",
    "ORIGIN_OK",
    "ORIGIN_TIMED_OUT",
    "ORIGIN_KILLED",
    "ORIGIN_FAILED",
    "ORIGIN_STATUSES",
    "OriginOutcome",
    "ExecutionOrigin",
    "KillSwitch",
    "Clock",
    "RationedRunReceipt",
    "RationedRunner",
    "ration_card_hash",
    "dispatch_request_hash",
]
