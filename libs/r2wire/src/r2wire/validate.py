# SPDX-License-Identifier: Apache-2.0
"""Strict event validation.  Unknown fields are errors."""

from __future__ import annotations

from typing import Any

from r2wire.opcodes import (
    BODY_OPTIONAL,
    BODY_REQUIRED,
    ENVELOPE_FIELDS,
    MAX_EVENT_BYTES,
    MAX_LIST_ITEMS,
    MAX_RENDER_CHARS,
    REQUIRED_ENVELOPE_FIELDS,
    VALID_OPCODES,
)
from r2wire.canonical import canonical_json_bytes


class ValidationError(Exception):
    """Raised when an event fails validation."""


def validate_event(event: dict[str, Any]) -> None:
    """Validate a single R2-WIRE event.  Raises ValidationError on failure."""

    if not isinstance(event, dict):
        raise ValidationError("event must be a dict")

    # -- Envelope fields --
    unknown_top = set(event.keys()) - ENVELOPE_FIELDS
    if unknown_top:
        raise ValidationError(f"unknown envelope fields: {sorted(unknown_top)}")

    for field in REQUIRED_ENVELOPE_FIELDS:
        if field not in event:
            raise ValidationError(f"missing required field: {field}")

    # -- Types --
    if not isinstance(event["v"], int) or event["v"] < 1:
        raise ValidationError("v must be a positive integer")

    if event["type"] not in VALID_OPCODES:
        raise ValidationError(f"unknown opcode: {event['type']}")

    if not isinstance(event["id"], str) or not event["id"]:
        raise ValidationError("id must be a non-empty string")

    if not isinstance(event["ts"], int) or event["ts"] < 0:
        raise ValidationError("ts must be a non-negative integer (epoch seconds)")

    for field in ("from", "to", "ctx"):
        if not isinstance(event[field], str) or not event[field]:
            raise ValidationError(f"{field} must be a non-empty string")

    if not isinstance(event["body"], dict):
        raise ValidationError("body must be a dict")

    # -- Render (optional) --
    if "render" in event:
        if not isinstance(event["render"], str):
            raise ValidationError("render must be a string")
        if len(event["render"]) > MAX_RENDER_CHARS:
            raise ValidationError(
                f"render exceeds {MAX_RENDER_CHARS} chars: {len(event['render'])}"
            )

    # -- Size cap --
    raw = canonical_json_bytes(event, nfc=False)
    if len(raw) > MAX_EVENT_BYTES:
        raise ValidationError(
            f"event exceeds {MAX_EVENT_BYTES} bytes: {len(raw)}"
        )

    # -- Body validation --
    opcode = event["type"]
    body = event["body"]

    required = BODY_REQUIRED.get(opcode, frozenset())
    optional = BODY_OPTIONAL.get(opcode, frozenset())
    allowed_body = required | optional

    missing = required - set(body.keys())
    if missing:
        raise ValidationError(f"{opcode} body missing fields: {sorted(missing)}")

    unknown_body = set(body.keys()) - allowed_body
    if unknown_body:
        raise ValidationError(
            f"{opcode} body has unknown fields: {sorted(unknown_body)}"
        )

    # -- List size caps --
    for key, val in body.items():
        if isinstance(val, list) and len(val) > MAX_LIST_ITEMS:
            raise ValidationError(
                f"{opcode}.body.{key} exceeds {MAX_LIST_ITEMS} items: {len(val)}"
            )
