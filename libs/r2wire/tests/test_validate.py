# SPDX-License-Identifier: Apache-2.0
"""Tests for R2-WIRE event validation."""

from __future__ import annotations

import pytest

from r2wire.validate import validate_event, ValidationError
from r2wire.opcodes import Opcode, MAX_EVENT_BYTES, MAX_RENDER_CHARS, MAX_LIST_ITEMS


def _make_event(opcode: str = "PROPOSE", **overrides) -> dict:
    """Build a minimal valid event, with overrides."""
    base = {
        "v": 1,
        "type": opcode,
        "id": "evt_test_01",
        "ts": 1700000000,
        "from": "agent:test",
        "to": "agent:other",
        "ctx": "run:test",
        "body": _default_body(opcode),
    }
    base.update(overrides)
    return base


def _default_body(opcode: str) -> dict:
    bodies = {
        "PROPOSE": {
            "pid": "P1",
            "goal": "test goal",
            "steps": [{"sid": "S1", "op": "TOOL", "ref": "h:sha256:abc"}],
        },
        "COMMIT": {
            "approve": "P1",
            "allow": ["S1"],
            "limits": {"tokens": 1000, "tool_calls": 5},
        },
        "VETO": {
            "against": "P1",
            "reason": "insufficient_evidence",
        },
        "TOOL": {
            "tid": "T1",
            "sid": "S1",
            "name": "web.search",
        },
        "RESULT": {
            "for": "T1",
            "ok": True,
        },
    }
    return bodies[opcode]


class TestValidEvent:
    """All five opcodes should validate when well-formed."""

    @pytest.mark.parametrize("opcode", [op.value for op in Opcode])
    def test_valid_event(self, opcode):
        evt = _make_event(opcode)
        validate_event(evt)  # should not raise

    def test_valid_with_render(self):
        evt = _make_event()
        evt["render"] = "Planning vendor search"
        validate_event(evt)

    def test_valid_with_optional_body_fields(self):
        evt = _make_event("PROPOSE")
        evt["body"]["preconds"] = [{"kind": "BUDGET", "tokens_lte": 500}]
        evt["body"]["asks"] = [{"kind": "APPROVAL", "for": ["S1"]}]
        validate_event(evt)


class TestEnvelopeValidation:
    """Envelope-level validation errors."""

    def test_not_a_dict(self):
        with pytest.raises(ValidationError, match="must be a dict"):
            validate_event("not a dict")

    def test_missing_required_field(self):
        evt = _make_event()
        del evt["from"]
        with pytest.raises(ValidationError, match="missing required field"):
            validate_event(evt)

    def test_unknown_envelope_field(self):
        evt = _make_event()
        evt["surprise"] = "bad"
        with pytest.raises(ValidationError, match="unknown envelope fields"):
            validate_event(evt)

    def test_bad_version(self):
        evt = _make_event(v=0)
        with pytest.raises(ValidationError, match="v must be"):
            validate_event(evt)

    def test_float_version(self):
        evt = _make_event(v=1.5)
        with pytest.raises(ValidationError, match="v must be"):
            validate_event(evt)

    def test_unknown_opcode(self):
        evt = _make_event(type="EXPLODE")
        with pytest.raises(ValidationError, match="unknown opcode"):
            validate_event(evt)

    def test_empty_id(self):
        evt = _make_event(id="")
        with pytest.raises(ValidationError, match="id must be"):
            validate_event(evt)

    def test_negative_ts(self):
        evt = _make_event(ts=-1)
        with pytest.raises(ValidationError, match="ts must be"):
            validate_event(evt)

    def test_float_ts(self):
        evt = _make_event(ts=1.5)
        with pytest.raises(ValidationError, match="ts must be"):
            validate_event(evt)

    def test_render_too_long(self):
        evt = _make_event()
        evt["render"] = "x" * (MAX_RENDER_CHARS + 1)
        with pytest.raises(ValidationError, match="render exceeds"):
            validate_event(evt)


class TestBodyValidation:
    """Body-level validation per opcode."""

    def test_missing_body_field(self):
        evt = _make_event("COMMIT")
        del evt["body"]["approve"]
        with pytest.raises(ValidationError, match="missing fields"):
            validate_event(evt)

    def test_unknown_body_field(self):
        evt = _make_event("TOOL")
        evt["body"]["surprise"] = "bad"
        with pytest.raises(ValidationError, match="unknown fields"):
            validate_event(evt)

    def test_list_too_long(self):
        evt = _make_event("COMMIT")
        evt["body"]["allow"] = [f"S{i}" for i in range(MAX_LIST_ITEMS + 1)]
        with pytest.raises(ValidationError, match="exceeds"):
            validate_event(evt)


class TestSizeCap:
    """Event size limits."""

    def test_oversized_event(self):
        evt = _make_event("PROPOSE")
        # Stuff the goal with enough data to exceed 8 KiB
        evt["body"]["goal"] = "x" * (MAX_EVENT_BYTES + 1)
        with pytest.raises(ValidationError, match="exceeds"):
            validate_event(evt)
