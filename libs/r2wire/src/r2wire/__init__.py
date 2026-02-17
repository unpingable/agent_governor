# SPDX-License-Identifier: Apache-2.0
"""R2-WIRE: Minimal typed wire protocol for LLM/agent coordination."""

__version__ = "0.2.0"

from r2wire.opcodes import Opcode, ENVELOPE_FIELDS, MAX_EVENT_BYTES

__all__ = [
    "Opcode",
    "ENVELOPE_FIELDS",
    "MAX_EVENT_BYTES",
]
