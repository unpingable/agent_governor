# SPDX-License-Identifier: Apache-2.0
"""Replay harness: replay run artifacts under different knobs, diff outputs.

Takes a stored run artifact (directory with header.json + trace.jsonl + outputs/)
and replays it through governor subsystems with optional parameter overrides.
Produces a new artifact with captured outputs for diffing.

Artifact format:
    artifact_dir/
    ├── header.json          # ArtifactHeader (schema, params, provenance)
    ├── trace.jsonl          # Canonical TraceEvents (sorted by t_ms, seq)
    └── outputs/             # Named output streams (JSONL per stream)
        ├── receipts.jsonl   # Gate receipts produced during the run
        ├── heartbeat.jsonl  # Heartbeat snapshots (if heartbeat calls present)
        └── ...              # Future: signals.jsonl, regime.jsonl, etc.

Design decisions:
    - Self-contained in governor package.  No imports from sim/.
    - Accepts only canonical artifacts, not scenario JSON.
    - Artifact is a directory, never in-place modification.
    - outputs/ is a namespace of named streams, not hardcoded files.
    - Provenance includes hashes + identity (trace_sha256, governor_git_rev, artifact_id).
    - Diff uses fingerprinted receipts, not just counts.
    - Replay writes outputs from in-memory reads, not by copying .governor/ tree.
"""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

ARTIFACT_VERSION = 1
VALID_EVENT_TYPES = frozenset({"call", "emit", "fault", "assert"})


# =============================================================================
# TraceEvent (own copy — no sim/ import)
# =============================================================================


@dataclass(frozen=True)
class TraceEvent:
    """Single event in a trace.  Same shape as governor_sim.schema.TraceEvent."""

    t_ms: int
    seq: int
    scenario: str
    event_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    actor: str | None = None
    session_id: str | None = None
    run_id: str | None = None

    def __post_init__(self) -> None:
        if self.t_ms < 0:
            raise ValueError(f"t_ms must be >= 0, got {self.t_ms}")
        if self.seq < 0:
            raise ValueError(f"seq must be >= 0, got {self.seq}")
        if self.event_type not in VALID_EVENT_TYPES:
            raise ValueError(
                f"event_type must be one of {sorted(VALID_EVENT_TYPES)}, "
                f"got {self.event_type!r}"
            )
        if not self.scenario:
            raise ValueError("scenario must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "t_ms": self.t_ms,
            "seq": self.seq,
            "scenario": self.scenario,
            "event_type": self.event_type,
            "payload": self.payload,
        }
        if self.actor is not None:
            d["actor"] = self.actor
        if self.session_id is not None:
            d["session_id"] = self.session_id
        if self.run_id is not None:
            d["run_id"] = self.run_id
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TraceEvent:
        return cls(
            t_ms=d["t_ms"],
            seq=d["seq"],
            scenario=d["scenario"],
            event_type=d["event_type"],
            payload=d.get("payload", {}),
            actor=d.get("actor"),
            session_id=d.get("session_id"),
            run_id=d.get("run_id"),
        )

    def to_json_line(self) -> str:
        """Canonical JSON line: sorted keys, compact separators."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))


# =============================================================================
# ArtifactHeader
# =============================================================================


@dataclass
class ArtifactHeader:
    """Metadata header for a run artifact."""

    artifact_version: int = ARTIFACT_VERSION
    artifact_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    trace_sha256: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_version": self.artifact_version,
            "artifact_id": self.artifact_id,
            "trace_sha256": self.trace_sha256,
            "params": self.params,
            "provenance": self.provenance,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ArtifactHeader:
        return cls(
            artifact_version=d.get("artifact_version", ARTIFACT_VERSION),
            artifact_id=d.get("artifact_id", str(uuid.uuid4())),
            trace_sha256=d.get("trace_sha256", ""),
            params=d.get("params", {}),
            provenance=d.get("provenance", {}),
        )


# =============================================================================
# RunArtifact
# =============================================================================


def _compute_trace_hash(events: list[TraceEvent]) -> str:
    """SHA-256 of the canonical trace JSONL content."""
    content = "\n".join(e.to_json_line() for e in events)
    if content:
        content += "\n"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class RunArtifact:
    """Read/write run artifact directories."""

    def __init__(
        self,
        path: Path,
        header: ArtifactHeader,
        events: list[TraceEvent],
    ) -> None:
        self.path = path
        self.header = header
        self.events = events

    @classmethod
    def create(
        cls,
        path: Path,
        header: ArtifactHeader,
        events: list[TraceEvent],
    ) -> RunArtifact:
        """Write a new artifact directory."""
        path.mkdir(parents=True, exist_ok=True)

        # Compute trace hash
        header.trace_sha256 = _compute_trace_hash(events)

        # Write header.json
        header_path = path / "header.json"
        header_path.write_text(
            json.dumps(header.to_dict(), indent=2, sort_keys=True) + "\n"
        )

        # Write trace.jsonl
        trace_path = path / "trace.jsonl"
        lines = [e.to_json_line() for e in events]
        trace_path.write_text("\n".join(lines) + "\n" if lines else "")

        return cls(path=path, header=header, events=events)

    @classmethod
    def load(cls, path: Path) -> RunArtifact:
        """Load from existing directory.  Validates trace_sha256."""
        if not path.is_dir():
            raise FileNotFoundError(f"Artifact directory not found: {path}")

        header_path = path / "header.json"
        if not header_path.exists():
            raise FileNotFoundError(f"Missing header.json in {path}")

        header = ArtifactHeader.from_dict(json.loads(header_path.read_text()))

        trace_path = path / "trace.jsonl"
        events: list[TraceEvent] = []
        if trace_path.exists():
            for line in trace_path.read_text().splitlines():
                line = line.strip()
                if line:
                    events.append(TraceEvent.from_dict(json.loads(line)))

        # Validate trace hash
        actual_hash = _compute_trace_hash(events)
        if header.trace_sha256 and actual_hash != header.trace_sha256:
            raise ValueError(
                f"Trace hash mismatch: expected {header.trace_sha256}, "
                f"got {actual_hash}"
            )

        return cls(path=path, header=header, events=events)

    def write_output(self, name: str, lines: list[dict[str, Any]]) -> None:
        """Write JSONL lines to outputs/<name>.jsonl."""
        outputs_dir = self.path / "outputs"
        outputs_dir.mkdir(exist_ok=True)
        out_path = outputs_dir / f"{name}.jsonl"
        content = "\n".join(
            json.dumps(line, sort_keys=True, separators=(",", ":"))
            for line in lines
        )
        if content:
            content += "\n"
        out_path.write_text(content)

    def read_output(self, name: str) -> list[dict[str, Any]]:
        """Read all JSONL lines from outputs/<name>.jsonl."""
        out_path = self.path / "outputs" / f"{name}.jsonl"
        if not out_path.exists():
            return []
        result: list[dict[str, Any]] = []
        for line in out_path.read_text().splitlines():
            line = line.strip()
            if line:
                result.append(json.loads(line))
        return result

    def output_names(self) -> list[str]:
        """List available output stream names (without .jsonl suffix)."""
        outputs_dir = self.path / "outputs"
        if not outputs_dir.is_dir():
            return []
        return sorted(
            p.stem for p in outputs_dir.iterdir()
            if p.suffix == ".jsonl" and p.is_file()
        )


# =============================================================================
# ReplayAPI (SimAPI pattern — independent implementation)
# =============================================================================


class ReplayAPI:
    """Thin adapter — same shape as sim's SimAPI, independent implementation.

    Lazy-inits governor subsystems.  Supports the same param overrides.
    """

    def __init__(self, gov_dir: Path, params: dict[str, Any] | None = None) -> None:
        self.gov_dir = gov_dir
        self.params = params or {}
        self._receipt_system: Any | None = None
        self._evidence_gate: Any | None = None

    def _get_receipt_system(self) -> Any:
        if self._receipt_system is None:
            from .gate_receipt import GateReceiptSystem
            self._receipt_system = GateReceiptSystem(self.gov_dir)
        return self._receipt_system

    def _get_evidence_gate(self) -> Any:
        if self._evidence_gate is None:
            from .evidence_gate import EvidenceGate, EvidenceGateConfig
            strict = self.params.get("evidence_gate_strict", True)
            cfg = EvidenceGateConfig(strict=strict)
            self._evidence_gate = EvidenceGate(
                config=cfg,
                receipt_system=self._get_receipt_system(),
            )
        return self._evidence_gate

    def _heartbeat_config(self) -> Any:
        from .gate_heartbeat import HeartbeatConfig
        kwargs: dict[str, Any] = {}
        if "heartbeat_interval" in self.params:
            kwargs["expected_interval_seconds"] = float(self.params["heartbeat_interval"])
        if "heartbeat_grace" in self.params:
            kwargs["grace_period_seconds"] = float(self.params["heartbeat_grace"])
        if "heartbeat_threshold" in self.params:
            kwargs["stale_after_missed"] = int(self.params["heartbeat_threshold"])
        return HeartbeatConfig(**kwargs)

    def gate_check(self, output: str, task: str = "", context: str = ".") -> dict[str, Any]:
        """Call EvidenceGate.check() and return result as dict."""
        gate = self._get_evidence_gate()
        result = gate.check(task=task, context=context, output=output)
        return {
            "status": result.status.value,
            "blocking_reasons": list(result.blocking_reasons),
            "warnings": list(result.warnings),
            "claim_count": len(result.claims),
        }

    def gate_heartbeat(self, now: datetime, session_active: bool = True) -> dict[str, Any]:
        """Call gate_heartbeat() and return HeartbeatStatus as dict."""
        from .gate_heartbeat import gate_heartbeat
        status = gate_heartbeat(
            self.gov_dir,
            config=self._heartbeat_config(),
            now=now,
            session_active=session_active,
        )
        return status.to_dict()

    def emit_receipt(
        self,
        receipt_data: dict[str, Any],
        *,
        timestamp: str | None = None,
    ) -> None:
        """Write a receipt through GateReceiptSystem."""
        system = self._get_receipt_system()
        raw = receipt_data.get("subject_bytes", b"sim")
        if isinstance(raw, str):
            subject_bytes = raw.encode("utf-8")
        elif isinstance(raw, bytes):
            subject_bytes = raw
        else:
            raise TypeError(
                f"subject_bytes must be str or bytes, got {type(raw).__name__}"
            )
        system.emit(
            gate=receipt_data.get("gate", "sim"),
            verdict=receipt_data.get("verdict", "pass"),
            subject_kind=receipt_data.get("subject_kind", "sim_event"),
            subject_bytes=subject_bytes,
            evidence_bundle=receipt_data.get("evidence_bundle", {}),
            gate_config=receipt_data.get("gate_config", {}),
            timestamp=timestamp,
        )

    def receipt_count(self) -> int:
        """Count receipts via ReceiptStore.all()."""
        system = self._get_receipt_system()
        return len(system.receipt_store.all())

    def read_receipts(self) -> list[dict[str, Any]]:
        """Read all receipts as dicts."""
        system = self._get_receipt_system()
        return [r.to_dict() for r in system.receipt_store.all()]


# =============================================================================
# ReplayClock
# =============================================================================


@dataclass
class ReplayClock:
    """Monotonic replay clock.  Base: epoch (1970-01-01T00:00:00Z)."""

    _offset_ms: int = 0

    @property
    def now(self) -> datetime:
        """Current replay time as a UTC datetime."""
        return datetime.fromtimestamp(self._offset_ms / 1000.0, tz=timezone.utc)

    def advance_to(self, t_ms: int) -> None:
        """Advance clock to *at least* t_ms.  Raises on backwards jump."""
        if t_ms < self._offset_ms:
            raise ValueError(
                f"ReplayClock cannot go backwards: current {self._offset_ms}, requested {t_ms}"
            )
        self._offset_ms = t_ms


# =============================================================================
# Receipt fingerprinting
# =============================================================================


def _fingerprint_receipt(r: dict[str, Any]) -> str:
    """Stable fingerprint: sha256(gate|verdict|subject_hash)[:16]."""
    key = f"{r.get('gate', '')}|{r.get('verdict', '')}|{r.get('subject_hash', '')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


# =============================================================================
# replay_run()
# =============================================================================


def replay_run(
    artifact: RunArtifact,
    out_dir: Path | None = None,
    param_overrides: dict[str, Any] | None = None,
) -> RunArtifact:
    """Replay a run artifact under (optionally) different params.

    Args:
        artifact: Source artifact to replay.
        out_dir: Where to write the output artifact.  Auto-generated if None.
        param_overrides: Override specific params from the original header.

    Returns:
        A new RunArtifact at out_dir with captured outputs.
    """
    # Merge params
    merged_params = dict(artifact.header.params)
    if param_overrides:
        merged_params.update(param_overrides)

    # Auto-generate output dir if not provided
    if out_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        out_dir = artifact.path.parent / f"{artifact.path.name}__replay_{ts}"

    # Create scratch .governor/ in a temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        gov_dir = Path(tmpdir) / ".governor"
        gov_dir.mkdir(parents=True)
        (gov_dir / "receipts").mkdir()

        api = ReplayAPI(gov_dir, params=merged_params)
        clock = ReplayClock()
        fault_state: dict[str, bool] = {}
        heartbeat_captures: list[dict[str, Any]] = []

        # Walk events sorted by (t_ms, seq)
        sorted_events = sorted(artifact.events, key=lambda e: (e.t_ms, e.seq))

        for event in sorted_events:
            clock.advance_to(event.t_ms)

            if event.event_type == "call":
                target = event.payload.get("target", "")

                # Fault injection: skip gate calls if gate_enabled is False
                if target in ("gate_check", "evidence_gate.check"):
                    if not fault_state.get("gate_enabled", True):
                        continue
                    api.gate_check(
                        output=event.payload.get("output", ""),
                        task=event.payload.get("task", ""),
                        context=event.payload.get("context", "."),
                    )

                elif target == "gate_heartbeat":
                    session_active = event.payload.get("session_active", True)
                    hb = api.gate_heartbeat(
                        now=clock.now,
                        session_active=session_active,
                    )
                    heartbeat_captures.append({
                        "t_ms": event.t_ms,
                        **hb,
                    })

            elif event.event_type == "emit":
                kind = event.payload.get("kind", "")
                if kind == "receipt":
                    api.emit_receipt(
                        event.payload.get("data", {}),
                        timestamp=clock.now.isoformat(),
                    )

            elif event.event_type == "fault":
                flag = event.payload.get("flag")
                value = event.payload.get("value", True)
                if flag:
                    fault_state[flag] = bool(value)

            elif event.event_type == "assert":
                # Skip silently — asserts are evaluation-time
                pass

        # Read receipts in-memory
        receipts = api.read_receipts()

    # Build output artifact
    header = ArtifactHeader(
        params=merged_params,
        provenance={
            "source": "replay",
            "source_artifact": str(artifact.path),
            "source_artifact_id": artifact.header.artifact_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

    output_artifact = RunArtifact.create(
        path=out_dir,
        header=header,
        events=artifact.events,  # Trace copied verbatim
    )

    # Write output streams
    if receipts:
        output_artifact.write_output("receipts", receipts)
    if heartbeat_captures:
        output_artifact.write_output("heartbeat", heartbeat_captures)

    return output_artifact


# =============================================================================
# DiffResult + replay_diff()
# =============================================================================


@dataclass
class DiffResult:
    """Result of diffing two run artifacts."""

    receipt_summary: dict[str, Any] = field(default_factory=dict)
    receipt_fingerprints: dict[str, Any] = field(default_factory=dict)
    heartbeat_delta: list[dict[str, Any]] = field(default_factory=list)
    first_divergence: dict[str, Any] | None = None
    summary: str = ""
    passed: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "receipt_summary": self.receipt_summary,
            "receipt_fingerprints": self.receipt_fingerprints,
            "heartbeat_delta": self.heartbeat_delta,
            "first_divergence": self.first_divergence,
            "summary": self.summary,
            "passed": self.passed,
        }


def _count_receipts(receipts: list[dict[str, Any]]) -> dict[str, int]:
    """Count receipts by (gate, verdict)."""
    counts: dict[str, int] = {}
    for r in receipts:
        key = f"{r.get('gate', '?')}:{r.get('verdict', '?')}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def replay_diff(baseline: RunArtifact, replay: RunArtifact) -> DiffResult:
    """Diff two run artifacts and report differences.

    Args:
        baseline: The original run artifact.
        replay: The replayed run artifact.

    Returns:
        DiffResult with deltas and a human-readable summary.
    """
    result = DiffResult()
    issues: list[str] = []

    # 1. Receipt summary — count by (gate, verdict)
    baseline_receipts = baseline.read_output("receipts")
    replay_receipts = replay.read_output("receipts")
    baseline_counts = _count_receipts(baseline_receipts)
    replay_counts = _count_receipts(replay_receipts)
    result.receipt_summary = {
        "baseline": baseline_counts,
        "replay": replay_counts,
    }
    if baseline_counts != replay_counts:
        issues.append(
            f"Receipt counts differ: baseline={sum(baseline_counts.values())}, "
            f"replay={sum(replay_counts.values())}"
        )

    # 2. Receipt fingerprints — set difference
    baseline_fps = {_fingerprint_receipt(r) for r in baseline_receipts}
    replay_fps = {_fingerprint_receipt(r) for r in replay_receipts}
    added = sorted(replay_fps - baseline_fps)
    removed = sorted(baseline_fps - replay_fps)
    result.receipt_fingerprints = {
        "added": added,
        "removed": removed,
        "baseline_count": len(baseline_fps),
        "replay_count": len(replay_fps),
    }
    if added or removed:
        issues.append(
            f"Receipt fingerprints differ: {len(added)} added, {len(removed)} removed"
        )

    # 3. Heartbeat delta
    baseline_hb = baseline.read_output("heartbeat")
    replay_hb = replay.read_output("heartbeat")
    baseline_hb_by_t = {h["t_ms"]: h for h in baseline_hb}
    replay_hb_by_t = {h["t_ms"]: h for h in replay_hb}
    all_t_ms = sorted(set(baseline_hb_by_t.keys()) | set(replay_hb_by_t.keys()))

    for t_ms in all_t_ms:
        b = baseline_hb_by_t.get(t_ms)
        r = replay_hb_by_t.get(t_ms)
        if b is None or r is None:
            result.heartbeat_delta.append({
                "t_ms": t_ms,
                "baseline": b,
                "replay": r,
            })
        elif (b.get("is_stale") != r.get("is_stale")
              or b.get("missed_count") != r.get("missed_count")):
            result.heartbeat_delta.append({
                "t_ms": t_ms,
                "baseline": {"is_stale": b.get("is_stale"), "missed_count": b.get("missed_count")},
                "replay": {"is_stale": r.get("is_stale"), "missed_count": r.get("missed_count")},
            })

    if result.heartbeat_delta:
        issues.append(f"Heartbeat differs at {len(result.heartbeat_delta)} time point(s)")

    # 4. First divergence — across all shared output streams
    baseline_streams = set(baseline.output_names())
    replay_streams = set(replay.output_names())
    shared = sorted(baseline_streams & replay_streams)

    earliest_divergence: dict[str, Any] | None = None
    for stream in shared:
        b_lines = baseline.read_output(stream)
        r_lines = replay.read_output(stream)
        max_len = max(len(b_lines), len(r_lines))
        for i in range(max_len):
            b_val = b_lines[i] if i < len(b_lines) else None
            r_val = r_lines[i] if i < len(r_lines) else None
            if b_val != r_val:
                # Get t_ms from whichever side has it
                t_ms = (b_val or r_val or {}).get("t_ms", 0)
                candidate = {
                    "t_ms": t_ms,
                    "stream": stream,
                    "index": i,
                    "baseline_value": b_val,
                    "replay_value": r_val,
                }
                if earliest_divergence is None or t_ms < earliest_divergence["t_ms"]:
                    earliest_divergence = candidate
                break  # Only need first divergence per stream

    result.first_divergence = earliest_divergence

    # 5. Compute passed
    result.passed = (
        not added
        and not removed
        and not result.heartbeat_delta
    )

    # 6. Build summary
    if not issues:
        result.summary = "No differences detected."
    else:
        result.summary = "; ".join(issues) + "."

    return result
