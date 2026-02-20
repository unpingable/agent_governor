# SPDX-License-Identifier: Apache-2.0
"""Trace recorder: poll gate receipt JSONL and transcribe to run artifacts.

Phase 1: receipt-only.  Named "record-receipts" honestly — no call-level
fidelity.  Recorded trace contains only "emit" events (kind=receipt),
inferred from the receipt log.

Usage:
    recorder = ReceiptRecorder(gov_dir, scenario="live")
    # ... some time passes, receipts accumulate ...
    new_events = recorder.poll()
    artifact = recorder.finalize(out_dir)
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .replay import ArtifactHeader, RunArtifact, TraceEvent


# =============================================================================
# ReceiptRecorder
# =============================================================================


class ReceiptRecorder:
    """Polls the gate receipt JSONL and transcribes to trace artifact format.

    Each receipt line becomes a TraceEvent with event_type="emit" and
    payload={"kind": "receipt", "data": <receipt_dict>}.

    t_ms is real elapsed time (monotonic offset from start).
    """

    def __init__(self, gov_dir: Path, scenario: str = "live") -> None:
        self.gov_dir = gov_dir
        self.scenario = scenario
        self._receipt_path = gov_dir / "receipts" / "gate_receipts.jsonl"
        self._seq: int = 0
        self._start_monotonic: float = time.monotonic()
        self._start_position: int = self._current_file_size()
        self._events: list[TraceEvent] = []
        self._raw_receipts: list[dict[str, Any]] = []

    def _current_file_size(self) -> int:
        """Current byte size of the receipt file, 0 if missing."""
        try:
            return self._receipt_path.stat().st_size
        except (OSError, FileNotFoundError):
            return 0

    def poll(self) -> list[TraceEvent]:
        """Read new receipt lines since last poll, return as TraceEvents."""
        if not self._receipt_path.exists():
            return []

        new_events: list[TraceEvent] = []

        try:
            with open(self._receipt_path, "r") as f:
                f.seek(self._start_position)
                new_data = f.read()
                self._start_position = f.tell()
        except OSError:
            return []

        for line in new_data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                receipt_dict = json.loads(line)
            except json.JSONDecodeError:
                continue

            t_ms = int((time.monotonic() - self._start_monotonic) * 1000)
            event = TraceEvent(
                t_ms=t_ms,
                seq=self._seq,
                scenario=self.scenario,
                event_type="emit",
                payload={"kind": "receipt", "data": receipt_dict},
            )
            self._seq += 1
            new_events.append(event)
            self._events.append(event)
            self._raw_receipts.append(receipt_dict)

        return new_events

    def finalize(self, out_dir: Path) -> RunArtifact:
        """Collect all recorded events, write artifact.

        Does a final poll to catch any remaining receipts.
        """
        self.poll()  # Final sweep

        header = ArtifactHeader(
            params={},
            provenance={
                "source": "recorded-receipts",
                "governor_dir": str(self.gov_dir),
                "scenario": self.scenario,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        artifact = RunArtifact.create(
            path=out_dir,
            header=header,
            events=self._events,
        )

        # Write the raw receipts as an output stream
        if self._raw_receipts:
            artifact.write_output("receipts", self._raw_receipts)

        return artifact
