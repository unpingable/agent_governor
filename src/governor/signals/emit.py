# SPDX-License-Identifier: Apache-2.0
"""
Signal emitter — interface + JSONL sink for SignalEnvelope.

Keeps derivation code separate from emission transport so derivations
can be replayed later (Phase C) without dragging runtime IO.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
from pathlib import Path
from typing import Protocol, runtime_checkable

from .envelope import SignalEnvelope, validate_envelope

logger = logging.getLogger(__name__)


@runtime_checkable
class SignalEmitter(Protocol):
    """Protocol for signal emission sinks."""

    def emit(self, envelope: SignalEnvelope) -> None:
        """Emit a signal envelope. Must not raise on transient failures."""
        ...


class JsonlSink:
    """Append-only JSONL file sink for signal envelopes.

    Validates envelopes before writing. Invalid envelopes are logged and
    skipped (observe-only — never blocks on emission failure).

    Uses O_APPEND + fcntl.flock for concurrent-safe writes (same pattern
    as semantic_stability.py JSONL persistence).
    """

    def __init__(self, path: Path, *, validate: bool = True) -> None:
        self._path = path
        self._validate = validate

    @property
    def path(self) -> Path:
        return self._path

    def emit(self, envelope: SignalEnvelope) -> None:
        """Append envelope as one JSON line. Never raises."""
        try:
            if self._validate:
                errors = validate_envelope(envelope)
                if errors:
                    logger.warning(
                        "Signal envelope validation failed for %s: %s",
                        envelope.signal_id,
                        "; ".join(errors),
                    )
                    return

            line = json.dumps(
                envelope.to_dict(), separators=(",", ":"), ensure_ascii=True,
            )

            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(
                str(self._path),
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o644,
            )
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                os.write(fd, (line + "\n").encode("utf-8"))
            finally:
                os.close(fd)

        except Exception:
            # Observe-only: emission failure must never block execution
            logger.exception(
                "Failed to emit signal envelope for %s",
                getattr(envelope, "signal_id", "unknown"),
            )

    def read_all(self) -> list[SignalEnvelope]:
        """Read all envelopes from the JSONL file. For testing/replay."""
        if not self._path.exists():
            return []
        envelopes = []
        for line in self._path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                envelopes.append(SignalEnvelope.from_json(line))
            except Exception:
                logger.warning("Skipping malformed signal line: %s", line[:100])
        return envelopes

    def count(self) -> int:
        """Count envelopes in the file without fully parsing."""
        if not self._path.exists():
            return 0
        return sum(
            1 for line in self._path.read_text().splitlines()
            if line.strip()
        )


class MultiSink:
    """Fan-out emitter: writes to multiple sinks."""

    def __init__(self, sinks: list[SignalEmitter]) -> None:
        self._sinks = list(sinks)

    def emit(self, envelope: SignalEnvelope) -> None:
        for sink in self._sinks:
            try:
                sink.emit(envelope)
            except Exception:
                logger.exception("Sink %s failed", type(sink).__name__)
