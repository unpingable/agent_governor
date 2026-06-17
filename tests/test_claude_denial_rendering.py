"""Slice 2 — worker-facing delivery of legible refusals (the consumer boundary).

The structured refusal fields (retry_disposition / terminal_scope / message) are
authoritative on the bus + socket; this proves the Claude adapter RENDERS them
into the one channel the inner model actually reads — `permissionDecisionReason`
— without mutating the stable `reason` token. Two hops are under test:

  1. send_control forwards the fields onto the deny socket response (sibling keys);
  2. the embedded pre-tool hook renders them into permissionDecisionReason.

Acceptance #3's transport edge: legible in the bus is not legible to the worker
unless this boundary delivers it.
"""

from __future__ import annotations

import json

from governor.runtime.adapter import ControlAction
from governor.runtime.adapters.claude_code import (
    _SUPERVISED_PRE_TOOL_SCRIPT,
    ClaudeCodeAdapter,
)


def _render_fn():
    """Extract the REAL embedded hook renderer (no duplication, no drift): exec
    the hook script under a non-__main__ name so main() does not run, and return
    its `_worker_denial_reason`."""
    ns: dict = {"__name__": "_hook_under_test"}
    exec(compile(_SUPERVISED_PRE_TOOL_SCRIPT, "<pre_tool_hook>", "exec"), ns)
    return ns["_worker_denial_reason"]


# --------------------------------------------------------------------------- #
# Rendering (the embedded hook function).
# --------------------------------------------------------------------------- #


def test_legacy_reason_only_renders_unchanged():
    """A legacy/unknown deny carrying only `reason` renders byte-for-byte as
    before — no appended punctuation, no guessed disposition."""
    render = _render_fn()
    assert render({"reason": "LA refused: capacity_refused"}) == "LA refused: capacity_refused"
    # Total absence of reason falls back to the original default, nothing else.
    assert render({}) == "Blocked by governor"


def test_new_authority_required_reaches_permission_string():
    """The strong disposition + scope + human message all reach the rendered
    permission reason the model sees (acceptance #2/#3)."""
    render = _render_fn()
    out = render({
        "reason": "LA refused: capacity_refused",
        "message": "Write capacity for this grant is exhausted. "
                   "Retrying under the same grant cannot succeed.",
        "retry_disposition": "new_authority_required",
        "terminal_scope": "current_grant",
    })
    assert out.startswith("LA refused: capacity_refused")  # base reason intact
    assert "Write capacity for this grant is exhausted." in out
    assert "Retry disposition: new_authority_required." in out
    assert "Terminal scope: current_grant." in out


def test_missing_optional_fields_produce_no_none_or_empty_punctuation():
    """Acceptance #3 hygiene: absent fields are omitted — never the string
    'None', never a dangling clause, never a guessed disposition."""
    render = _render_fn()
    # message only.
    out = render({"reason": "base", "message": "ctx"})
    assert out == "base ctx"
    assert "None" not in out
    assert "Retry disposition" not in out
    assert "Terminal scope" not in out
    # disposition only (no message, no scope) — unknown is not invented.
    out2 = render({"reason": "base", "retry_disposition": "unknown"})
    assert out2 == "base Retry disposition: unknown."
    assert "Terminal scope" not in out2


def test_message_and_disposition_render_faithfully_together():
    """Acceptance #5: machine field + human text cannot disagree (enforced
    upstream by RefusalResult.__post_init__); here we prove BOTH render, intact
    and in order (human message before the machine clause)."""
    render = _render_fn()
    out = render({
        "reason": "LA refused: capacity_refused",
        "message": "Write capacity for this grant is exhausted.",
        "retry_disposition": "new_authority_required",
    })
    assert out.index("Write capacity for this grant is exhausted.") < \
        out.index("Retry disposition: new_authority_required.")


# --------------------------------------------------------------------------- #
# Forwarding (send_control → deny socket response).
# --------------------------------------------------------------------------- #


class _FakeConn:
    def __init__(self) -> None:
        self.sent = b""
        self.closed = False

    def sendall(self, b: bytes) -> None:
        self.sent += b

    def close(self) -> None:
        self.closed = True


def _deny_response(payload: dict) -> dict:
    adapter = ClaudeCodeAdapter()
    conn = _FakeConn()
    adapter._pending_hooks = {"tc1": conn}
    adapter.send_control(None, ControlAction(kind="deny", target_id="tc1", payload=payload))
    assert conn.closed
    return json.loads(conn.sent.decode().strip())


def test_send_control_forwards_structured_fields_reason_stable():
    """Acceptance #1/#4: `reason` is forwarded byte-stable; the structured fields
    ride as SIBLING keys (the socket carries what the hook will render)."""
    sent = _deny_response({
        "reason": "LA refused: capacity_refused",
        "retry_disposition": "new_authority_required",
        "terminal_scope": "current_grant",
        "message": "Write capacity for this grant is exhausted.",
    })
    assert sent["decision"] == "deny"
    assert sent["reason"] == "LA refused: capacity_refused"  # byte-stable
    assert sent["retry_disposition"] == "new_authority_required"
    assert sent["terminal_scope"] == "current_grant"
    assert sent["message"] == "Write capacity for this grant is exhausted."


def test_send_control_legacy_deny_omits_absent_fields():
    """A deny with no structured fields sends exactly {decision, reason} — no
    null sibling keys leak onto the socket."""
    sent = _deny_response({"reason": "Blocked by operator"})
    assert sent == {"decision": "deny", "reason": "Blocked by operator"}
