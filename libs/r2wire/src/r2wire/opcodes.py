# SPDX-License-Identifier: Apache-2.0
"""R2-WIRE opcodes and envelope schema.

Five opcodes.  That's it.  If you want to add one, justify it in
STATE_MACHINE.md first.

Envelope fields are the same for every event type.  Body schema
varies by opcode.  Unknown fields in the envelope or body are
validation errors (no permissive parsing).
"""

from __future__ import annotations

import enum
from typing import Any


class Opcode(enum.Enum):
    """The five wire opcodes."""

    PROPOSE = "PROPOSE"     # Plan with steps, preconditions, asks
    COMMIT = "COMMIT"       # Approval gate (scoped, budgeted, expirable)
    VETO = "VETO"           # Rejection with reason code
    TOOL = "TOOL"           # Tool invocation (must have covering COMMIT)
    RESULT = "RESULT"       # Tool output or answer


# Hard limits
MAX_EVENT_BYTES = 8192
MAX_RENDER_CHARS = 256
MAX_LIST_ITEMS = 64

# Envelope: fields present on every event, regardless of opcode.
ENVELOPE_FIELDS: frozenset[str] = frozenset({
    "v",        # int: protocol version (currently 1)
    "type",     # str: one of the Opcode values
    "id",       # str: unique event ID
    "ts",       # int: Unix epoch seconds (no floats)
    "from",     # str: sender (e.g. "agent:planner", "policy:gate")
    "to",       # str: recipient
    "ctx",      # str: run/session context ID
    "body",     # dict: opcode-specific payload
    "render",   # str: optional human hint (never authoritative)
})

# Required envelope fields (render is optional).
REQUIRED_ENVELOPE_FIELDS: frozenset[str] = ENVELOPE_FIELDS - {"render"}

# Valid opcode strings (for fast membership check).
VALID_OPCODES: frozenset[str] = frozenset(op.value for op in Opcode)


# Body schemas: required keys per opcode.
# Values are {field_name: type_description} for documentation.
# Actual validation is in validate.py.

BODY_REQUIRED: dict[str, frozenset[str]] = {
    "PROPOSE": frozenset({"pid", "goal", "steps"}),
    "COMMIT": frozenset({"approve", "allow", "limits"}),
    "VETO": frozenset({"against", "reason"}),
    "TOOL": frozenset({"tid", "sid", "name"}),
    "RESULT": frozenset({"for", "ok"}),
}

BODY_OPTIONAL: dict[str, frozenset[str]] = {
    "PROPOSE": frozenset({"preconds", "asks"}),
    "COMMIT": frozenset({"scope_grant", "expires"}),
    "VETO": frozenset({"detail"}),
    "TOOL": frozenset({"args"}),
    "RESULT": frozenset({"out", "error"}),
}
