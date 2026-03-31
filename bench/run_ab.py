#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Policy IR A/B runner: prose vs minimal renderer comparison.

Usage:
    python3 bench/run_ab.py                          # dry run (no API, just token counts)
    python3 bench/run_ab.py --backend anthropic       # live run with Anthropic API
    python3 bench/run_ab.py --backend ollama          # live run with Ollama
    python3 bench/run_ab.py --model claude-haiku-4-5-20251001  # specific model
    python3 bench/run_ab.py --mode fiction             # single mode only
    python3 bench/run_ab.py --task fiction_voice_comedy # single task

Outputs paired JSONL records to bench/results/<timestamp>.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from governor.policy_ir import (
    CORE_VOCAB,
    MinimalRenderer,
    ProseRenderer,
    hash_slot_set,
    mode_slot_set,
    validate_slot_set,
)


# ---------------------------------------------------------------------------
# Failure tags — defined before running, not rationalized after
# ---------------------------------------------------------------------------

FAILURE_TAGS = {
    "meta_leak",              # governance surfaces in-band
    "citation_drop",          # expected citation absent or fabricated
    "structure_drift",        # argument/narrative structure breaks down
    "tone_regime_failure",    # wrong tone/pacing for declared regime
    "unsupported_claim",      # hard claim without evidence
    "pattern_conflict_missed", # didn't flag contradiction with existing pattern
    "research_state_loss",    # ED/source state not tracked properly
    "canon_discipline",       # invented stable details without canon check
    "decision_reference",     # didn't reference existing decisions
    "epistemic_care",         # claimed file/code state without checking
    "exit_unclean",           # moral bow, unearned CTA, inflation
    "hedge_miscalibration",   # social hedge instead of epistemic hedge
}


# ---------------------------------------------------------------------------
# Run record
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    task_id: str
    mode: str
    renderer_id: str
    renderer_version: str
    vocab_id: str
    vocab_hash: str
    slot_set_hash: str
    content_hash: str
    prompt_chars: int
    prompt_tokens: int | None = None   # from API response, if available
    output_chars: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None
    model: str | None = None
    backend: str | None = None
    pass_fail: str | None = None       # "pass", "fail", or None (not scored)
    failure_tags: list[str] = field(default_factory=list)
    notes: str = ""
    timestamp: str = ""

    def to_jsonl(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


# ---------------------------------------------------------------------------
# Corpus loader
# ---------------------------------------------------------------------------

def load_corpus(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    return data["tasks"]


# ---------------------------------------------------------------------------
# Dry run (no API, just render and measure)
# ---------------------------------------------------------------------------

def dry_run(tasks: list[dict]) -> list[RunRecord]:
    """Render each task with both renderers, compare token/char counts."""
    records: list[RunRecord] = []
    prose = ProseRenderer()
    minimal = MinimalRenderer()
    ts = datetime.now(timezone.utc).isoformat()

    for task in tasks:
        mode = task["mode"]
        params = task.get("params", {})
        ss = mode_slot_set(mode, **params)
        if ss is None:
            continue
        validate_slot_set(ss, CORE_VOCAB)

        for renderer in [prose, minimal]:
            result = renderer.render(ss, CORE_VOCAB)
            records.append(RunRecord(
                task_id=task["id"],
                mode=mode,
                renderer_id=result.renderer_id,
                renderer_version=result.renderer_version,
                vocab_id=result.vocab_id,
                vocab_hash=result.vocab_hash,
                slot_set_hash=result.slot_set_hash,
                content_hash=result.content_hash,
                prompt_chars=len(result.text),
                notes=f"dry run — {task.get('notes', '')}",
                timestamp=ts,
            ))

    return records


# ---------------------------------------------------------------------------
# Live run (with API backend)
# ---------------------------------------------------------------------------

def live_run(
    tasks: list[dict],
    backend_type: str,
    model: str | None,
) -> list[RunRecord]:
    """Run each task through both renderers against a real backend."""
    import asyncio
    import tempfile
    from governor.chat_bridge import ChatBridge, ChatMessage, GovernorHooks, create_backend
    from governor.context_manager import GovernorContext

    records: list[RunRecord] = []
    prose = ProseRenderer()
    minimal = MinimalRenderer()
    ts = datetime.now(timezone.utc).isoformat()

    # Create a temporary governor context
    tmp = Path(tempfile.mkdtemp())
    gov = tmp / ".governor"
    gov.mkdir()
    (gov / "facts").mkdir()
    (gov / "facts" / "receipts").mkdir()
    (gov / "decisions").mkdir()
    (gov / "facts" / "index.json").write_text("[]")
    (gov / "decisions" / "index.json").write_text("[]")

    backend = create_backend(backend_type)
    if backend is None:
        print(f"ERROR: Could not create backend {backend_type!r}", file=sys.stderr)
        sys.exit(1)

    if model is None:
        model = getattr(backend, "default_model", None) or "unknown"

    async def run_one(task: dict, renderer: ProseRenderer | MinimalRenderer) -> RunRecord:
        mode = task["mode"]
        params = task.get("params", {})

        ctx = GovernorContext(
            context_id="bench",
            mode=mode,
            root=tmp,
            governor_dir=gov,
            created_at=ts,
        )
        hooks = GovernorHooks(ctx, renderer=renderer)

        messages = [ChatMessage(role="user", content=task["user"])]
        augmented = hooks.augment_messages(messages)

        ss = mode_slot_set(mode, **params)
        validate_slot_set(ss, CORE_VOCAB)
        render_result = renderer.render(ss, CORE_VOCAB)

        t0 = time.monotonic()
        try:
            response = await backend.chat(augmented, model)
            latency_ms = (time.monotonic() - t0) * 1000
            return RunRecord(
                task_id=task["id"],
                mode=mode,
                renderer_id=render_result.renderer_id,
                renderer_version=render_result.renderer_version,
                vocab_id=render_result.vocab_id,
                vocab_hash=render_result.vocab_hash,
                slot_set_hash=render_result.slot_set_hash,
                content_hash=render_result.content_hash,
                prompt_chars=len(render_result.text),
                prompt_tokens=response.usage.get("prompt_tokens"),
                output_chars=len(response.content),
                output_tokens=response.usage.get("completion_tokens"),
                latency_ms=latency_ms,
                model=model,
                backend=backend_type,
                timestamp=ts,
            )
        except Exception as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            return RunRecord(
                task_id=task["id"],
                mode=mode,
                renderer_id=render_result.renderer_id,
                renderer_version=render_result.renderer_version,
                vocab_id=render_result.vocab_id,
                vocab_hash=render_result.vocab_hash,
                slot_set_hash=render_result.slot_set_hash,
                content_hash=render_result.content_hash,
                prompt_chars=len(render_result.text),
                latency_ms=latency_ms,
                model=model,
                backend=backend_type,
                pass_fail="error",
                notes=f"{type(exc).__name__}: {exc}",
                timestamp=ts,
            )

    async def run_all():
        for task in tasks:
            for renderer in [prose, minimal]:
                record = await run_one(task, renderer)
                records.append(record)
                tag = "P" if record.renderer_id.startswith("prose") else "M"
                status = f"{record.prompt_tokens or '?'}→{record.output_tokens or '?'} tok"
                if record.latency_ms:
                    status += f" {record.latency_ms:.0f}ms"
                print(f"  [{tag}] {record.task_id}: {status}")

    asyncio.run(run_all())
    return records


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_records(records: list[RunRecord], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{ts}.jsonl"
    with open(path, "w") as f:
        for r in records:
            f.write(r.to_jsonl() + "\n")
    return path


def print_summary(records: list[RunRecord]) -> None:
    """Print a quick comparison table."""
    from collections import defaultdict
    by_task: dict[str, dict[str, RunRecord]] = defaultdict(dict)
    for r in records:
        by_task[r.task_id][r.renderer_id] = r

    print(f"\n{'task':<30} {'prose_chars':>12} {'minimal_chars':>14} {'ratio':>8}")
    print("-" * 68)
    for task_id, renderers in sorted(by_task.items()):
        prose = renderers.get("prose_v1")
        minimal = renderers.get("minimal_v1")
        if prose and minimal:
            ratio = minimal.prompt_chars / prose.prompt_chars if prose.prompt_chars else 0
            tok_col = ""
            if prose.prompt_tokens and minimal.prompt_tokens:
                tok_ratio = minimal.prompt_tokens / prose.prompt_tokens
                tok_col = f"  tok: {prose.prompt_tokens}→{minimal.prompt_tokens} ({tok_ratio:.1%})"
            print(f"{task_id:<30} {prose.prompt_chars:>12} {minimal.prompt_chars:>14} {ratio:>7.1%}{tok_col}")

    # Totals
    prose_total = sum(r.prompt_chars for r in records if r.renderer_id == "prose_v1")
    minimal_total = sum(r.prompt_chars for r in records if r.renderer_id == "minimal_v1")
    if prose_total:
        print("-" * 68)
        print(f"{'TOTAL':<30} {prose_total:>12} {minimal_total:>14} {minimal_total/prose_total:>7.1%}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Policy IR A/B runner")
    parser.add_argument("--backend", choices=["anthropic", "ollama", "claude_code"],
                        help="Live backend (omit for dry run)")
    parser.add_argument("--model", help="Model name")
    parser.add_argument("--mode", help="Filter to single mode")
    parser.add_argument("--task", help="Filter to single task ID")
    parser.add_argument("--corpus", default="bench/corpus.json", help="Corpus path")
    parser.add_argument("--out", default="bench/results", help="Output directory")
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"Corpus not found: {corpus_path}", file=sys.stderr)
        sys.exit(1)

    tasks = load_corpus(corpus_path)

    if args.mode:
        tasks = [t for t in tasks if t["mode"] == args.mode]
    if args.task:
        tasks = [t for t in tasks if t["id"] == args.task]

    if not tasks:
        print("No tasks match filters.", file=sys.stderr)
        sys.exit(1)

    print(f"Running {len(tasks)} tasks × 2 renderers")

    if args.backend:
        print(f"Backend: {args.backend}, model: {args.model or 'default'}")
        records = live_run(tasks, args.backend, args.model)
    else:
        print("Dry run (no API calls)")
        records = dry_run(tasks)

    path = write_records(records, Path(args.out))
    print(f"\nResults written to {path}")
    print_summary(records)


if __name__ == "__main__":
    main()
