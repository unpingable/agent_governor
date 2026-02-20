# SPDX-License-Identifier: Apache-2.0
"""CLI entry point: python -m governor_sim {compile,run,export}."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from .dsl import compile_scenario, load_scenario
from .runner import InprocRunner


def _compile(path: str) -> int:
    """Compile scenario to canonical JSONL on stdout (no asserts)."""
    spec = load_scenario(path)
    header, events = compile_scenario(spec)

    # Emit header line
    print(json.dumps({"header": header.to_dict()}, sort_keys=True, separators=(",", ":")))

    # Emit events (skip asserts — they're out-of-band)
    for event in events:
        if event.event_type != "assert":
            print(event.to_json_line())

    return 0


def _run(path: str) -> int:
    """Run scenario, print JSON summary, exit 0 on pass / 1 on fail."""
    spec = load_scenario(path)
    header, events = compile_scenario(spec)

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = InprocRunner(work_dir=Path(tmpdir), params=header.params)
        result = runner.run(events)

    summary = result.to_dict()
    print(json.dumps(summary, indent=2))

    return 0 if result.passed else 1


def _export(path: str, out_dir: str) -> int:
    """Export scenario as a run artifact (replay-ready directory).

    Compiles the scenario, runs it in a temp directory, and writes
    the result as a RunArtifact with receipts captured.
    """
    from governor.replay import ArtifactHeader, RunArtifact, TraceEvent as ReplayEvent

    spec = load_scenario(path)
    header, events = compile_scenario(spec)

    # Convert sim TraceEvents to replay TraceEvents (same shape, different class)
    replay_events = [
        ReplayEvent.from_dict(e.to_dict())
        for e in events
        if e.event_type != "assert"  # Strip asserts
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        runner = InprocRunner(work_dir=Path(tmpdir), params=header.params)
        result = runner.run(events)

        # Read receipts from the runner's .governor/ tree
        receipts_path = Path(tmpdir) / ".governor" / "receipts" / "gate_receipts.jsonl"
        raw_receipts: list[dict] = []
        if receipts_path.exists():
            for line in receipts_path.read_text().splitlines():
                line = line.strip()
                if line:
                    raw_receipts.append(json.loads(line))

    artifact_header = ArtifactHeader(
        params=header.params,
        provenance={
            "source": "sim",
            "scenario": spec.get("name", Path(path).stem),
            "timestamp": __import__("datetime").datetime.now(
                __import__("datetime").timezone.utc
            ).isoformat(),
            "sim_passed": result.passed,
        },
    )

    artifact = RunArtifact.create(
        path=Path(out_dir),
        header=artifact_header,
        events=replay_events,
    )

    if raw_receipts:
        artifact.write_output("receipts", raw_receipts)

    print(json.dumps({
        "artifact_path": str(artifact.path),
        "artifact_id": artifact.header.artifact_id,
        "trace_sha256": artifact.header.trace_sha256,
        "events": len(replay_events),
        "receipts": len(raw_receipts),
        "sim_passed": result.passed,
    }, indent=2))

    return 0


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python -m governor_sim {compile,run,export} <scenario.json> [--out DIR]",
              file=sys.stderr)
        sys.exit(2)

    cmd = sys.argv[1]
    path = sys.argv[2]

    if cmd == "compile":
        sys.exit(_compile(path))
    elif cmd == "run":
        sys.exit(_run(path))
    elif cmd == "export":
        # Parse --out argument
        out_dir = None
        for i, arg in enumerate(sys.argv[3:], start=3):
            if arg == "--out" and i + 1 < len(sys.argv):
                out_dir = sys.argv[i + 1]
                break
        if out_dir is None:
            stem = Path(path).stem
            out_dir = f"{stem}_artifact"
        sys.exit(_export(path, out_dir))
    else:
        print(f"Unknown command: {cmd!r}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
