# SPDX-License-Identifier: Apache-2.0
"""Acceptance tests — ``operator_mode`` is a closed domain and fails closed.

Slice: ``operator-mode-closed-domain-fail-closed``
(``working/security-slice-operator-mode-closed-domain-2026-07-14.md``, ruled
2026-07-15; filed as A-7 in the 2026-07-14 authority-seams decision packet).

The finding: ``operator_mode`` was an unvalidated string, and the effect path
prompted for WRITE/COMMUNICATE only when it was exactly ``"interactive"``.
Every other value — typo, case variant, padded string, non-string, private
custom mode — fell through to auto-approve. An unvetted string bought silent
write authority.

Two fences, tested separately because they fail for different reasons:

* **Ingress** (``create_session``) closes the domain at the authoritative
  construction point, before a session ID or event file exists.
* **Effect point** (``_handle_tool_call``) requires an exact ``"autonomous"``
  record to skip the prompt, so a malformed, restored, or forged record that
  never passed ingress still cannot fail open.

Reads stay auto-approved: fail-closed must not mean blanket deadlock.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Iterable

import pytest

from governor.runtime.adapter import (
    AdapterCapabilities,
    BackendHandle,
    ControlAction,
    NativeEvent,
)
from governor.runtime.events import EventKind, SourceLayer
from governor.runtime.supervisor import (
    OPERATOR_MODES,
    SessionSupervisor,
)

# Values that must never be admitted. Each is a realistic way the field gets
# corrupted, not a fuzz corpus: a typo, an empty default, a case variant, a
# padded copy-paste, and three non-strings.
INVALID_MODES: tuple[Any, ...] = (
    "not-a-real-mode",
    "",
    "Interactive",
    " autonomous ",
    None,
    1,
    {},
)


class EffectOnApproveAdapter:
    """Fake hook adapter that materializes an effect only after ``approve``.

    Mirrors the audit reproduction (``working/repro-operator-mode-fail-open.py``):
    the write is real, so a test that observes ``destination.exists()`` is
    observing an effect that crossed the gate, not a log line about one.
    """

    def __init__(
        self,
        destination: Path,
        tool_name: str = "Write",
        tool_input: dict[str, Any] | None = None,
    ) -> None:
        self.destination = destination
        self.tool_name = tool_name
        self.tool_input = tool_input if tool_input is not None else {
            "path": str(destination),
            "content": "effect crossed\n",
        }
        self.controls: list[ControlAction] = []

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_native_tool_hooks=True,
            supports_structured_events=True,
        )

    def launch(self, config: object) -> BackendHandle:
        return BackendHandle(pid=4242)

    def iter_events(self, handle: BackendHandle) -> Iterable[NativeEvent]:
        yield NativeEvent(
            kind="pre_tool_use",
            payload={
                "tool_name": self.tool_name,
                "tool_call_id": "tc_effect_1",
                "tool_input": self.tool_input,
            },
        )

    def send_control(self, handle: BackendHandle, action: ControlAction) -> None:
        self.controls.append(action)
        if action.kind == "approve" and action.target_id == "tc_effect_1":
            self.destination.write_text("effect crossed\n", encoding="utf-8")

    def shutdown(self, handle: BackendHandle, graceful: bool = True) -> None:
        return None

    def map_event(self, event: NativeEvent) -> list[dict[str, Any]]:
        return [
            {
                "kind": EventKind.TOOL_CALL_PROPOSED,
                "source_layer": SourceLayer.ADAPTER,
                "tool_call_id": event.payload["tool_call_id"],
                "payload": event.payload,
            }
        ]

    def is_alive(self, handle: BackendHandle) -> bool:
        return True


def _drive_tool_call(
    supervisor: SessionSupervisor,
    session_id: str,
    adapter: EffectOnApproveAdapter,
) -> dict[str, Any]:
    """Launch and settle one tool call; return what the gate actually did.

    Settling is deliberately not "first interesting event wins". The supervisor
    emits TOOL_CALL_ALLOWED *before* calling ``send_control``, which is what
    materializes the effect — so breaking on ALLOWED can observe
    ``write_exists=False`` purely because the write has not landed yet. On the
    allow path we therefore wait for the control action too. On the prompt path
    OPERATOR_PROMPTED is already terminal: no control is coming, and asserting
    "no approve ever arrived" is the whole point of the fail-closed tests.
    """
    supervisor.launch_session(session_id)

    for _ in range(200):
        events = supervisor.get_events(session_id)
        prompted = any(e.kind == EventKind.OPERATOR_PROMPTED for e in events)
        allowed = any(e.kind == EventKind.TOOL_CALL_ALLOWED for e in events)
        if prompted or (allowed and adapter.controls):
            break
        time.sleep(0.01)

    events = supervisor.get_events(session_id)
    allowed = [e for e in events if e.kind == EventKind.TOOL_CALL_ALLOWED]
    return {
        "write_exists": adapter.destination.exists(),
        "controls": [a.kind for a in adapter.controls],
        "allowed": len(allowed),
        "prompted": sum(e.kind == EventKind.OPERATOR_PROMPTED for e in events),
        "pending": len(supervisor.get_pending_interventions(session_id)),
        "auto": [e.payload.get("auto") for e in allowed],
    }


def _forge_mode(supervisor: SessionSupervisor, session_id: str, mode: Any) -> None:
    """Corrupt a stored record's mode, bypassing the ingress fence.

    Stands in for a restored legacy record, a hand-edited state file, or a
    forgery — anything that reaches the effect path without passing
    ``create_session``. Reaching into ``_sessions`` is the point: it is the
    only way to prove the second fence carries its own weight.
    """
    supervisor._sessions[session_id].operator_mode = mode


# ---------------------------------------------------------------------
# 1. Ingress — the domain is closed at the construction point
# ---------------------------------------------------------------------


@pytest.mark.parametrize("mode", INVALID_MODES, ids=lambda m: repr(m))
def test_create_session_rejects_invalid_operator_mode_before_state_write(
    tmp_path, mode
):
    state_dir = tmp_path / "runtime"
    supervisor = SessionSupervisor(state_dir=state_dir)
    adapter = EffectOnApproveAdapter(tmp_path / "effect.txt")

    with pytest.raises(ValueError) as exc:
        supervisor.create_session(
            adapter, "mock", str(tmp_path), operator_mode=mode
        )

    # The error names the closed set rather than just saying "invalid".
    for allowed in OPERATOR_MODES:
        assert allowed in str(exc.value)

    # Refused BEFORE any state exists: no session, no event file.
    assert supervisor._sessions == {}
    assert list(supervisor.list_sessions()) == []
    assert not list(state_dir.glob("*_events.jsonl"))


@pytest.mark.parametrize("mode", OPERATOR_MODES)
def test_create_session_admits_exactly_the_closed_set(tmp_path, mode):
    supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
    adapter = EffectOnApproveAdapter(tmp_path / "effect.txt")

    record = supervisor.create_session(
        adapter, "mock", str(tmp_path), operator_mode=mode
    )

    assert record.operator_mode == mode


def test_default_operator_mode_is_admissible(tmp_path):
    """The default must be inside the domain it is validated against."""
    supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
    adapter = EffectOnApproveAdapter(tmp_path / "effect.txt")

    record = supervisor.create_session(adapter, "mock", str(tmp_path))

    assert record.operator_mode in OPERATOR_MODES


# ---------------------------------------------------------------------
# 2. Daemon RPC reports the refusal and creates nothing
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_daemon_runtime_session_create_rejects_invalid_operator_mode(tmp_path):
    from governor.daemon import DaemonState, Dispatcher, register_handlers

    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()
    state = DaemonState(gov_dir, mode="general")
    dispatcher = Dispatcher()
    register_handlers(dispatcher, state)

    response = await dispatcher.dispatch({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "runtime.session.create",
        "params": {
            "backend_kind": "claude_code",
            "cwd": str(tmp_path),
            "operator_mode": "not-a-real-mode",
        },
    })

    assert "error" in response, f"RPC must report the refusal; got {response}"
    assert "operator_mode" in str(response["error"])
    assert not state.runtime_supervisor.list_sessions()


# ---------------------------------------------------------------------
# 3-5. Effect point — a malformed stored record cannot fail open
# ---------------------------------------------------------------------


def test_malformed_session_record_write_fails_closed(tmp_path):
    """The original finding, at the effect point rather than the ingress."""
    supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
    destination = tmp_path / "effect.txt"
    adapter = EffectOnApproveAdapter(destination)

    record = supervisor.create_session(
        adapter, "mock", str(tmp_path), operator_mode="interactive"
    )
    _forge_mode(supervisor, record.session_id, "interactve")  # typo

    result = _drive_tool_call(supervisor, record.session_id, adapter)

    assert result["write_exists"] is False, "a forged mode must not buy a write"
    assert result["controls"] == [], "no approve control may reach the adapter"
    assert result["allowed"] == 0
    assert result["prompted"] == 1
    assert result["pending"] == 1


def test_malformed_session_record_communicate_fails_closed(tmp_path):
    supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
    destination = tmp_path / "effect.txt"
    adapter = EffectOnApproveAdapter(
        destination,
        tool_name="Bash",
        tool_input={"command": "git push origin main"},
    )

    record = supervisor.create_session(
        adapter, "mock", str(tmp_path), operator_mode="interactive"
    )
    _forge_mode(supervisor, record.session_id, "interactve")

    result = _drive_tool_call(supervisor, record.session_id, adapter)

    assert result["write_exists"] is False
    assert result["controls"] == []
    assert result["allowed"] == 0
    assert result["prompted"] == 1
    assert result["pending"] == 1


@pytest.mark.parametrize("mode", ["interactve", None, 1])
def test_malformed_session_record_read_remains_auto_approved(tmp_path, mode):
    """Fail-closed on writes must not deadlock the whole session."""
    supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
    destination = tmp_path / "effect.txt"
    adapter = EffectOnApproveAdapter(
        destination,
        tool_name="Read",
        tool_input={"path": str(destination)},
    )

    record = supervisor.create_session(
        adapter, "mock", str(tmp_path), operator_mode="interactive"
    )
    _forge_mode(supervisor, record.session_id, mode)

    result = _drive_tool_call(supervisor, record.session_id, adapter)

    assert result["allowed"] == 1, "reads must stay auto-approved"
    assert result["auto"] == [True]
    assert result["prompted"] == 0
    assert result["pending"] == 0


# ---------------------------------------------------------------------
# 6. Regression pins — the two real modes are behaviorally unchanged
# ---------------------------------------------------------------------


def test_interactive_write_still_prompts(tmp_path):
    supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
    destination = tmp_path / "effect.txt"
    adapter = EffectOnApproveAdapter(destination)

    record = supervisor.create_session(
        adapter, "mock", str(tmp_path), operator_mode="interactive"
    )

    result = _drive_tool_call(supervisor, record.session_id, adapter)

    assert result == {
        "write_exists": False,
        "controls": [],
        "allowed": 0,
        "prompted": 1,
        "pending": 1,
        "auto": [],
    }


def test_autonomous_write_still_auto_approves(tmp_path):
    """The exact pre-slice autonomous path, pinned.

    This is the one mode that keeps silent write authority. If this test ever
    has to change, the slice's compatibility claim is void.
    """
    supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
    destination = tmp_path / "effect.txt"
    adapter = EffectOnApproveAdapter(destination)

    record = supervisor.create_session(
        adapter, "mock", str(tmp_path), operator_mode="autonomous"
    )

    result = _drive_tool_call(supervisor, record.session_id, adapter)

    assert result["allowed"] == 1
    assert result["auto"] == [True]
    assert result["prompted"] == 0
    assert result["controls"] == ["approve"]
    assert result["write_exists"] is True


def test_fork_inherits_only_an_admissible_mode(tmp_path):
    """Fork routes through create_session, so the fence covers it too."""
    supervisor = SessionSupervisor(state_dir=tmp_path / "runtime")
    adapter = EffectOnApproveAdapter(tmp_path / "effect.txt")

    record = supervisor.create_session(
        adapter, "mock", str(tmp_path), operator_mode="interactive"
    )
    _forge_mode(supervisor, record.session_id, "not-a-real-mode")

    # A forged parent cannot launder its mode into a child.
    with pytest.raises(ValueError):
        supervisor.create_session(
            adapter,
            "mock",
            str(tmp_path),
            operator_mode=supervisor._sessions[record.session_id].operator_mode,
        )


# ---------------------------------------------------------------------
# 7. CLI ingress ergonomics — refuses before supervisor construction
# ---------------------------------------------------------------------


def test_cli_launch_rejects_invalid_mode_before_supervisor_construction(tmp_path):
    """CLI validation is ergonomics, not the boundary — but it should bite."""
    from click.testing import CliRunner

    from governor.cli import cli

    result = CliRunner().invoke(
        cli, ["runtime", "launch", "--mode", "not-a-real-mode"]
    )

    assert result.exit_code != 0
    assert "not-a-real-mode" in result.output


def test_cli_launch_mode_is_case_sensitive(tmp_path):
    from click.testing import CliRunner

    from governor.cli import cli

    result = CliRunner().invoke(cli, ["runtime", "launch", "--mode", "Interactive"])

    assert result.exit_code != 0
