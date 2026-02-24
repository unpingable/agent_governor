# SPDX-License-Identifier: Apache-2.0
"""
v2.4 Instrumentation Spine — signal envelope and emitter plumbing.

Phase A substrate: envelope model, quality semantics, JSONL emission.
No signal derivation logic lives here — see exposure_proxy.py, etc.
"""

from .envelope import (
    CURRENT_SCHEMA_VERSION,
    DerivationType,
    QualityStatus,
    SignalEnvelope,
    validate_envelope,
)
from .emit import JsonlSink, SignalEmitter

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "DerivationType",
    "JsonlSink",
    "QualityStatus",
    "SignalEmitter",
    "SignalEnvelope",
    "validate_envelope",
]
