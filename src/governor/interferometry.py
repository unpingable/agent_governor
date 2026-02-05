"""
Interferometry — multi-model claim comparison.

Two modes:
  - **parallel**: Send the same prompt to N backends simultaneously,
    extract claims from each response, compare via Jaccard fingerprinting.
  - **serial**: "Yes, and" deliberation chain — send prompt to model A,
    feed A's response to model B as context, iterate for N rounds.
    Produces the same claim alignment at the end.

Reuses existing governor subsystems:
  - claim_signals.SignalExtractor for claim extraction
  - taint.fingerprint() / taint.score() for Jaccard similarity
  - chat_bridge.create_backend() / ChatMessage for backend calls
  - epistemic.EpistemicLedger.new_claim() for ledger promotion
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .chat_bridge import ChatMessage, create_backend
from .claim_signals import ExtractionResult, SignalExtractor
from .epistemic import Provenance
from .taint import Fingerprint, fingerprint, score as jaccard_score


# ============================================================================
# Enums & Types
# ============================================================================


class AlignmentType(str, Enum):
    SHARED = "shared"
    UNIQUE = "unique"
    CONFLICTING = "conflicting"


class RunMode(str, Enum):
    PARALLEL = "parallel"
    SERIAL = "serial"


@dataclass
class ModelRun:
    """Result from a single model invocation."""
    model_id: str
    backend_type: str
    response: str
    extraction: ExtractionResult | None = None
    usage: dict[str, int] = field(default_factory=dict)
    latency_ms: float = 0.0
    round_number: int = 0  # For serial mode: which round this was

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "backend_type": self.backend_type,
            "response": self.response,
            "extraction": {
                "total_signals": self.extraction.total_signals,
                "assertiveness_score": self.extraction.assertiveness_score,
                "signals_by_category": self.extraction.signals_by_category,
            } if self.extraction else None,
            "usage": self.usage,
            "latency_ms": self.latency_ms,
            "round_number": self.round_number,
        }


@dataclass
class ClaimAlignment:
    """A claim with alignment info across models."""
    claim_text: str
    fp: Fingerprint
    sources: list[str]  # model_ids that produced this claim
    alignment: AlignmentType
    confidence: float  # Proportion of models that agree
    category: str = ""  # From extraction: DATE, ENTITY, QUANTITY, ASSERTIVE

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_text": self.claim_text,
            "fingerprint": self.fp.text_hash,
            "sources": self.sources,
            "alignment": self.alignment.value,
            "confidence": round(self.confidence, 3),
            "category": self.category,
        }


@dataclass
class InterferometrySignals:
    """Summary statistics from a comparison run."""
    disagreement_rate: float  # conflicting / total
    specifics_conflict_count: int  # Dates/quantities that disagree
    unique_count: int
    shared_count: int
    conflict_count: int
    total_claims: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "disagreement_rate": round(self.disagreement_rate, 3),
            "specifics_conflict_count": self.specifics_conflict_count,
            "unique_count": self.unique_count,
            "shared_count": self.shared_count,
            "conflict_count": self.conflict_count,
            "total_claims": self.total_claims,
        }


@dataclass
class InterferometryRun:
    """Complete record of an interferometry session."""
    id: str
    prompt: str
    mode: RunMode
    runs: list[ModelRun]
    shared: list[ClaimAlignment]
    unique: list[ClaimAlignment]
    conflicts: list[ClaimAlignment]
    signals: InterferometrySignals
    rounds: int = 1  # For serial mode
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prompt": self.prompt,
            "mode": self.mode.value,
            "rounds": self.rounds,
            "runs": [r.to_dict() for r in self.runs],
            "shared": [c.to_dict() for c in self.shared],
            "unique": [c.to_dict() for c in self.unique],
            "conflicts": [c.to_dict() for c in self.conflicts],
            "signals": self.signals.to_dict(),
            "created_at": self.created_at,
        }


# ============================================================================
# Core Functions
# ============================================================================


_extractor = SignalExtractor()


def extract_claims(response: str) -> ExtractionResult:
    """Extract implicit claims from a model response."""
    return _extractor.extract(response)


def match_claims(
    text_a: str, text_b: str, threshold: float = 0.65
) -> float:
    """Compute Jaccard similarity between two claim texts.

    Returns score in [0, 1]. Score >= threshold means match.
    """
    fp_a = fingerprint(text_a)
    fp_b = fingerprint(text_b)
    return jaccard_score(fp_a, fp_b)


def align_claims(
    runs: list[ModelRun],
    threshold: float = 0.65,
) -> tuple[list[ClaimAlignment], list[ClaimAlignment], list[ClaimAlignment]]:
    """Compare claims across model runs.

    Returns (shared, unique, conflicts).
    - shared: claims that appear in 2+ runs with consistent specifics
    - unique: claims that appear in only 1 run
    - conflicts: claims that appear in 2+ runs with differing specifics
    """
    if not runs:
        return [], [], []

    # Collect all claims with their source model
    all_claims: list[tuple[str, str, str, Fingerprint]] = []
    # (claim_text, model_id, category, fingerprint)
    for run in runs:
        if run.extraction is None:
            continue
        for match in run.extraction.matches:
            fp = fingerprint(match.value)
            all_claims.append((match.value, run.model_id, match.category.value, fp))

    if not all_claims:
        return [], [], []

    # Greedy clustering: group claims by fingerprint similarity
    clusters: list[list[tuple[str, str, str, Fingerprint]]] = []
    used = [False] * len(all_claims)

    for i in range(len(all_claims)):
        if used[i]:
            continue
        cluster = [all_claims[i]]
        used[i] = True
        for j in range(i + 1, len(all_claims)):
            if used[j]:
                continue
            sim = jaccard_score(all_claims[i][3], all_claims[j][3])
            if sim >= threshold:
                cluster.append(all_claims[j])
                used[j] = True
        clusters.append(cluster)

    model_count = len(runs)
    shared: list[ClaimAlignment] = []
    unique: list[ClaimAlignment] = []
    conflicts: list[ClaimAlignment] = []

    for cluster in clusters:
        sources = list({item[1] for item in cluster})
        # Use the first claim text as representative
        text = cluster[0][0]
        fp = cluster[0][3]
        category = cluster[0][2]
        confidence = len(sources) / model_count if model_count > 0 else 0.0

        alignment_obj = ClaimAlignment(
            claim_text=text,
            fp=fp,
            sources=sources,
            alignment=AlignmentType.SHARED,
            confidence=confidence,
            category=category,
        )

        if len(sources) == 1:
            alignment_obj.alignment = AlignmentType.UNIQUE
            unique.append(alignment_obj)
        elif _has_specifics_conflict(cluster):
            alignment_obj.alignment = AlignmentType.CONFLICTING
            conflicts.append(alignment_obj)
        else:
            shared.append(alignment_obj)

    return shared, unique, conflicts


def _has_specifics_conflict(
    cluster: list[tuple[str, str, str, Fingerprint]],
) -> bool:
    """Check if a cluster has conflicting dates or quantities.

    A conflict exists when different models produced different specific
    values (dates, numbers) for the same claim topic.
    """
    specifics_categories = {"date", "quantity"}
    specifics_values: dict[str, set[str]] = {}

    for text, model_id, category, _ in cluster:
        if category in specifics_categories:
            if model_id not in specifics_values:
                specifics_values[model_id] = set()
            specifics_values[model_id].add(text.strip().lower())

    if len(specifics_values) < 2:
        return False

    # If different models produced different specific values, it's a conflict
    all_vals = list(specifics_values.values())
    return any(v != all_vals[0] for v in all_vals[1:])


def compute_signals(
    shared: list[ClaimAlignment],
    unique: list[ClaimAlignment],
    conflicts: list[ClaimAlignment],
    model_count: int,
) -> InterferometrySignals:
    """Compute summary signals from alignment results."""
    total = len(shared) + len(unique) + len(conflicts)
    disagreement_rate = len(conflicts) / total if total > 0 else 0.0
    specifics_conflict_count = sum(
        1 for c in conflicts if c.category in ("date", "quantity")
    )

    return InterferometrySignals(
        disagreement_rate=disagreement_rate,
        specifics_conflict_count=specifics_conflict_count,
        unique_count=len(unique),
        shared_count=len(shared),
        conflict_count=len(conflicts),
        total_claims=total,
    )


# ============================================================================
# Ensemble Execution
# ============================================================================


async def run_parallel(
    prompt: str,
    backend_configs: list[dict[str, Any]],
    threshold: float = 0.65,
) -> InterferometryRun:
    """Run the same prompt across multiple backends in parallel.

    backend_configs: list of dicts with keys:
        - backend_type: str (e.g. "ollama", "anthropic")
        - model: str (e.g. "llama3", "claude-3-haiku")
        - Plus any backend-specific kwargs (api_key, host, etc.)
    """
    run_id = uuid.uuid4().hex[:12]
    model_runs: list[ModelRun] = []

    for config in backend_configs:
        backend_type = config.pop("backend_type")
        model = config.pop("model")

        try:
            backend = create_backend(backend_type, **config)
            messages = [ChatMessage(role="user", content=prompt)]

            t0 = time.monotonic()
            result = await backend.chat(messages, model=model)
            latency = (time.monotonic() - t0) * 1000

            extraction = extract_claims(result.content)
            model_runs.append(ModelRun(
                model_id=model,
                backend_type=backend_type,
                response=result.content,
                extraction=extraction,
                usage=result.usage,
                latency_ms=round(latency, 1),
            ))
        except Exception as e:
            model_runs.append(ModelRun(
                model_id=model,
                backend_type=backend_type,
                response=f"[error] {e}",
            ))

    shared, unique, conflicts = align_claims(model_runs, threshold)
    signals = compute_signals(shared, unique, conflicts, len(model_runs))

    return InterferometryRun(
        id=run_id,
        prompt=prompt,
        mode=RunMode.PARALLEL,
        runs=model_runs,
        shared=shared,
        unique=unique,
        conflicts=conflicts,
        signals=signals,
        created_at=_now_iso(),
    )


async def run_serial(
    prompt: str,
    backend_configs: list[dict[str, Any]],
    rounds: int = 1,
    threshold: float = 0.65,
) -> InterferometryRun:
    """Run a serial deliberation chain across backends.

    Round 0: Model A answers the original prompt.
    Round 1: Model B sees A's response and responds.
    Round N: Next model sees accumulated conversation and responds.

    Backends are cycled round-robin through the configs list.
    """
    run_id = uuid.uuid4().hex[:12]
    model_runs: list[ModelRun] = []

    # Build the conversation thread
    thread: list[ChatMessage] = [ChatMessage(role="user", content=prompt)]
    total_steps = rounds + 1  # Initial response + N deliberation rounds

    for step in range(total_steps):
        config = dict(backend_configs[step % len(backend_configs)])
        backend_type = config.pop("backend_type")
        model = config.pop("model")

        try:
            backend = create_backend(backend_type, **config)

            if step == 0:
                messages = list(thread)
            else:
                # Build deliberation prompt
                prev_response = model_runs[-1].response
                prev_model = model_runs[-1].model_id
                deliberation = (
                    f"Here is {prev_model}'s response:\n\n"
                    f"{prev_response}\n\n"
                    f"Please provide your own response to the original question. "
                    f"Where you agree, say so. Where you disagree or have "
                    f"additional information, explain."
                )
                messages = list(thread) + [
                    ChatMessage(role="assistant", content=prev_response),
                    ChatMessage(role="user", content=deliberation),
                ]

            t0 = time.monotonic()
            result = await backend.chat(messages, model=model)
            latency = (time.monotonic() - t0) * 1000

            extraction = extract_claims(result.content)
            model_runs.append(ModelRun(
                model_id=model,
                backend_type=backend_type,
                response=result.content,
                extraction=extraction,
                usage=result.usage,
                latency_ms=round(latency, 1),
                round_number=step,
            ))
        except Exception as e:
            model_runs.append(ModelRun(
                model_id=model,
                backend_type=backend_type,
                response=f"[error] {e}",
                round_number=step,
            ))

    shared, unique, conflicts = align_claims(model_runs, threshold)
    signals = compute_signals(shared, unique, conflicts, len(model_runs))

    return InterferometryRun(
        id=run_id,
        prompt=prompt,
        mode=RunMode.SERIAL,
        rounds=rounds,
        runs=model_runs,
        shared=shared,
        unique=unique,
        conflicts=conflicts,
        signals=signals,
        created_at=_now_iso(),
    )


async def run_ensemble(
    prompt: str,
    backend_configs: list[dict[str, Any]],
    mode: RunMode = RunMode.PARALLEL,
    rounds: int = 1,
    threshold: float = 0.65,
) -> InterferometryRun:
    """Unified entry point for both parallel and serial modes."""
    if mode == RunMode.SERIAL:
        return await run_serial(prompt, backend_configs, rounds, threshold)
    return await run_parallel(prompt, backend_configs, threshold)


# ============================================================================
# Ledger Promotion
# ============================================================================


def promote_to_ledger(
    run: InterferometryRun,
    ledger: Any,  # EpistemicLedger
    shared_only: bool = True,
) -> list[str]:
    """Promote interferometry claims to the epistemic ledger.

    Args:
        run: Completed interferometry run.
        ledger: EpistemicLedger instance.
        shared_only: If True, only promote shared claims. Otherwise also
            promote unique claims at low confidence.

    Returns:
        List of created claim IDs.
    """
    ids: list[str] = []

    for claim in run.shared:
        c = ledger.new_claim(
            content=claim.claim_text,
            provenance=Provenance.DERIVED,
            confidence=claim.confidence,
            source_agent_id=f"interferometry:{run.id}",
        )
        ids.append(c.claim_id)

    if not shared_only:
        for claim in run.unique:
            c = ledger.new_claim(
                content=claim.claim_text,
                provenance=Provenance.ASSUMED,
                confidence=0.2,
                source_agent_id=f"interferometry:{run.id}",
            )
            ids.append(c.claim_id)

    return ids


# ============================================================================
# Persistence
# ============================================================================


class InterferometryStore:
    """JSON file-per-run persistence in .governor/interferometry/."""

    def __init__(self, gov_dir: Path) -> None:
        self.store_dir = gov_dir / "interferometry"

    def _ensure_dir(self) -> None:
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def save(self, run: InterferometryRun) -> Path:
        self._ensure_dir()
        path = self.store_dir / f"{run.id}.json"
        path.write_text(json.dumps(run.to_dict(), indent=2))
        return path

    def load(self, run_id: str) -> InterferometryRun | None:
        path = self.store_dir / f"{run_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return _run_from_dict(data)

    def list_runs(self) -> list[dict[str, Any]]:
        """List all runs (summary only: id, prompt, mode, created_at, signals)."""
        if not self.store_dir.exists():
            return []
        summaries = []
        for p in sorted(self.store_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                data = json.loads(p.read_text())
                summaries.append({
                    "id": data["id"],
                    "prompt": data["prompt"][:80],
                    "mode": data.get("mode", "parallel"),
                    "rounds": data.get("rounds", 1),
                    "created_at": data.get("created_at", ""),
                    "signals": data.get("signals", {}),
                    "model_count": len(data.get("runs", [])),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return summaries

    def last(self) -> InterferometryRun | None:
        """Load the most recent run."""
        if not self.store_dir.exists():
            return None
        files = sorted(self.store_dir.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
        if not files:
            return None
        data = json.loads(files[0].read_text())
        return _run_from_dict(data)


# ============================================================================
# Helpers
# ============================================================================


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _run_from_dict(data: dict[str, Any]) -> InterferometryRun:
    """Reconstruct an InterferometryRun from a dict (best-effort)."""
    mode = RunMode(data.get("mode", "parallel"))
    runs = [
        ModelRun(
            model_id=r["model_id"],
            backend_type=r["backend_type"],
            response=r["response"],
            usage=r.get("usage", {}),
            latency_ms=r.get("latency_ms", 0.0),
            round_number=r.get("round_number", 0),
        )
        for r in data.get("runs", [])
    ]
    shared = [_alignment_from_dict(c) for c in data.get("shared", [])]
    unique = [_alignment_from_dict(c) for c in data.get("unique", [])]
    conflicts = [_alignment_from_dict(c) for c in data.get("conflicts", [])]

    sig = data.get("signals", {})
    signals = InterferometrySignals(
        disagreement_rate=sig.get("disagreement_rate", 0.0),
        specifics_conflict_count=sig.get("specifics_conflict_count", 0),
        unique_count=sig.get("unique_count", 0),
        shared_count=sig.get("shared_count", 0),
        conflict_count=sig.get("conflict_count", 0),
        total_claims=sig.get("total_claims", 0),
    )

    return InterferometryRun(
        id=data["id"],
        prompt=data["prompt"],
        mode=mode,
        rounds=data.get("rounds", 1),
        runs=runs,
        shared=shared,
        unique=unique,
        conflicts=conflicts,
        signals=signals,
        created_at=data.get("created_at", ""),
    )


def _alignment_from_dict(data: dict[str, Any]) -> ClaimAlignment:
    return ClaimAlignment(
        claim_text=data.get("claim_text", ""),
        fp=fingerprint(data.get("claim_text", "")),
        sources=data.get("sources", []),
        alignment=AlignmentType(data.get("alignment", "shared")),
        confidence=data.get("confidence", 0.0),
        category=data.get("category", ""),
    )
