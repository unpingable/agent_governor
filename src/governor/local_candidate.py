# SPDX-License-Identifier: Apache-2.0
"""Local candidate worker — Slice 0: failure-triage over a local model.

> Local output is cheap testimony, never standing. Qwen may nominate; Qwen may not admit.

Wires the EXISTING local lane (``chat_bridge.OllamaBackend`` / ``routing.ModelTier.LOCAL``)
into a fenced candidate producer, so a cheap local model can triage failures without
burning frontier-model budget. A local model turns a bounded failure transcript into a
structured candidate diagnosis; AG schema-checks it, REFUSES any authority claim, and
records it as a **non-authoritative candidate receipt** (gate ``local_candidate``,
``verdict=observe`` — fails ``is_authority_admission_receipt`` by construction, exactly
like the dispatch report).

Deliberate scope (Slice 0):

- **No new origin enum.** "Candidate may not admit" is already enforced upstream: a
  candidate receipt is observe-verdict on its own gate, so the existing operational
  fence (``operational_admission`` admits effect only for ``origin_mode == observed``)
  refuses it standing for free. We recognize the worker; the fence already refuses it.
- **No new ration-card type.** Reuses ``playbooks.ration_card.RationCard`` (all authority
  closed) + ``match_ration_card`` as the pre-check fence. It does NOT run
  ``dispatch_under_ration_card``'s spend chain: a free local candidate
  (``ModelTier.LOCAL`` cost = 0.0) spends nothing, so binding it to an LA consume would
  be cargo custody. The custody here is: zero declared authority + schema gate +
  authority-claim refusal + non-authoritative receipt.
- **No repo write, no shell, no patch apply.** Read-only structured output only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from governor.gate_receipt import canonical_json, content_hash

from .playbooks.ration_card import DispatchRequest, RationCard, match_ration_card

# --------------------------------------------------------------------------- #
# Vocabulary (closed).
# --------------------------------------------------------------------------- #

# Slice 0 supports exactly one task kind.
TASK_FAILURE_TRIAGE = "failure_triage_candidate"
SUPPORTED_TASK_KINDS = frozenset({TASK_FAILURE_TRIAGE})

CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})

# Claims a local candidate may NEVER make. Their presence is a hard refusal —
# the tiny constitution that keeps a sleepy 7B model from claiming standing.
FORBIDDEN_AUTHORITY_CLAIMS = frozenset(
    {
        "tests_pass",
        "safe_to_commit",
        "doctrine_satisfied",
        "authority_granted",
        "operational_effect",
    }
)

LOCAL_CANDIDATE_GATE = "local_candidate"
LOCAL_CANDIDATE_VERDICT = "observe"  # a candidate decides nothing

CANDIDATE_OBSERVED = "candidate_observed"
CANDIDATE_REFUSED = "candidate_refused"
CANDIDATE_VERDICTS = frozenset({CANDIDATE_OBSERVED, CANDIDATE_REFUSED})

# Closed refusal vocabulary.
REFUSED_OUTSIDE_CARD = "outside_ration_card"
REFUSED_UNSUPPORTED_TASK = "unsupported_task_kind"
REFUSED_BACKEND_ERROR = "backend_error"
REFUSED_EMPTY_OUTPUT = "empty_output"
REFUSED_SCHEMA_INVALID = "schema_invalid"
REFUSED_AUTHORITY_CLAIM = "authority_claim_detected"
CANDIDATE_REFUSALS = frozenset(
    {
        REFUSED_OUTSIDE_CARD,
        REFUSED_UNSUPPORTED_TASK,
        REFUSED_BACKEND_ERROR,
        REFUSED_EMPTY_OUTPUT,
        REFUSED_SCHEMA_INVALID,
        REFUSED_AUTHORITY_CLAIM,
    }
)

# Default bound on how much transcript text is sent to the model.
DEFAULT_MAX_TRANSCRIPT_CHARS = 8000


# --------------------------------------------------------------------------- #
# Injected model client.
# --------------------------------------------------------------------------- #


class LocalModelClient(Protocol):
    """A synchronous local-model completion seam. Production wraps an
    OpenAI-compatible local endpoint (Ollama); tests inject a deterministic fake."""

    def complete(self, prompt: str) -> str: ...


# --------------------------------------------------------------------------- #
# Request + candidate + receipt.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class LocalCandidateRequest:
    """A bounded failure transcript to triage. ``model`` is the local model id (e.g.
    ``qwen2.5-coder:7b``); it is also the carded agent identity."""

    task_kind: str
    model: str
    command: str
    exit_code: int
    transcript: str
    max_transcript_chars: int = DEFAULT_MAX_TRANSCRIPT_CHARS

    def bounded_transcript(self) -> str:
        if len(self.transcript) <= self.max_transcript_chars:
            return self.transcript
        head = self.transcript[: self.max_transcript_chars]
        return head + "\n...[truncated]..."


@dataclass(frozen=True)
class FailureTriage:
    """The structured candidate diagnosis. Advisory only."""

    failure_kind: str
    likely_files: tuple[str, ...]
    next_action: str
    confidence: str
    authority_claims: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(
                f"confidence {self.confidence!r} not in {sorted(CONFIDENCE_LEVELS)}"
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "failure_kind": self.failure_kind,
            "likely_files": list(self.likely_files),
            "next_action": self.next_action,
            "confidence": self.confidence,
            "authority_claims": list(self.authority_claims),
        }


@dataclass(frozen=True)
class LocalCandidateReceipt:
    """The non-authoritative record of one local candidate run. ``non_authoritative``
    is always True; ``verdict`` is observed/refused; a ``candidate`` is present only
    when observed."""

    model: str
    backend: str
    transport: str
    task_kind: str
    verdict: str
    prompt_digest: str
    input_digest: str
    schema_valid: bool
    authority_claims_detected: bool
    output_digest: Optional[str] = None
    refusal_reason: Optional[str] = None
    candidate: Optional[FailureTriage] = None
    non_authoritative: bool = True

    def __post_init__(self) -> None:
        if self.verdict not in CANDIDATE_VERDICTS:
            raise ValueError(f"verdict {self.verdict!r} not in {sorted(CANDIDATE_VERDICTS)}")
        if not self.non_authoritative:
            raise ValueError("a local candidate receipt is always non_authoritative")
        if self.refusal_reason is not None and self.refusal_reason not in CANDIDATE_REFUSALS:
            raise ValueError(f"refusal_reason {self.refusal_reason!r} not recognized")
        if self.verdict == CANDIDATE_REFUSED and self.refusal_reason is None:
            raise ValueError("a refused candidate must carry a refusal_reason")
        if self.verdict == CANDIDATE_OBSERVED and self.candidate is None:
            raise ValueError("an observed candidate must carry a candidate")

    @property
    def is_observed(self) -> bool:
        return self.verdict == CANDIDATE_OBSERVED

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "backend": self.backend,
            "transport": self.transport,
            "task_kind": self.task_kind,
            "verdict": self.verdict,
            "prompt_digest": self.prompt_digest,
            "input_digest": self.input_digest,
            "output_digest": self.output_digest,
            "schema_valid": self.schema_valid,
            "authority_claims_detected": self.authority_claims_detected,
            "refusal_reason": self.refusal_reason,
            "candidate": self.candidate.as_dict() if self.candidate else None,
            "non_authoritative": True,
        }


# --------------------------------------------------------------------------- #
# Prompt + parsing helpers.
# --------------------------------------------------------------------------- #

_REQUIRED_KEYS = ("failure_kind", "likely_files", "next_action", "confidence", "authority_claims")

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json_object(raw: str) -> Optional[str]:
    """Extract a single JSON object from possibly fence- or prose-wrapped model
    output (chat models often wrap JSON in ```json fences``` or chatter). Robustness
    ONLY — the extracted object still passes the full schema + authority-claim gate,
    so this never weakens the discipline. Returns None if no balanced object exists.
    The first balanced ``{...}`` (string-aware) is taken."""
    text = raw.strip()
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def build_triage_prompt(request: LocalCandidateRequest) -> str:
    """A bounded, JSON-only triage prompt. The model is told it may NOT claim
    authority; AG enforces that regardless of what the model says."""
    return (
        "You are a failure-triage assistant. Read the command transcript and return "
        "ONLY a single JSON object, no prose, with exactly these keys:\n"
        '  failure_kind (string), likely_files (array of strings), next_action (string),\n'
        '  confidence ("low"|"medium"|"high"), authority_claims (array, MUST be empty []).\n'
        "You may diagnose. You may NOT claim that tests pass, that anything is safe to "
        "commit, that doctrine is satisfied, that authority is granted, or that any "
        "operational effect occurred. authority_claims MUST be [].\n\n"
        f"command: {request.command}\n"
        f"exit_code: {request.exit_code}\n"
        f"transcript:\n{request.bounded_transcript()}\n"
    )


def _hash(obj: Any) -> str:
    return content_hash(canonical_json(obj))


def all_closed_card(model: str, task_kind: str) -> RationCard:
    """The fence: a ration card carrying ZERO authority for the local model. Reuses
    the existing primitive rather than minting a new card type."""
    return RationCard(agent_id=model, task_kind=task_kind)  # all axes default-closed


def _detect_authority_claims(parsed: dict[str, Any]) -> bool:
    """True if the candidate makes any forbidden authority claim — either by listing
    one in authority_claims, or by carrying a forbidden top-level key with a truthy
    value (a model trying to smuggle ``"tests_pass": true``)."""
    claims = parsed.get("authority_claims")
    if isinstance(claims, list) and any(
        str(c) in FORBIDDEN_AUTHORITY_CLAIMS for c in claims
    ):
        return True
    for key in FORBIDDEN_AUTHORITY_CLAIMS:
        if key in parsed and bool(parsed[key]):
            return True
    return False


# --------------------------------------------------------------------------- #
# The worker.
# --------------------------------------------------------------------------- #


def triage_failure(
    request: LocalCandidateRequest,
    *,
    client: LocalModelClient,
    card: Optional[RationCard] = None,
    backend: str = "ollama",
    transport: str = "loopback",
    receipt_sink: Any | None = None,
) -> LocalCandidateReceipt:
    """Run ONE local failure-triage candidate. Always returns a receipt (observed or
    refused); never raises for an ordinary bad model output. Emits a non-authoritative
    gate receipt when a sink is provided."""
    card = card or all_closed_card(request.model, request.task_kind)
    prompt = build_triage_prompt(request)
    prompt_digest = _hash({"prompt": prompt})
    input_digest = _hash(
        {
            "task_kind": request.task_kind,
            "model": request.model,
            "command": request.command,
            "exit_code": request.exit_code,
            "transcript": request.bounded_transcript(),
        }
    )

    def _refuse(reason: str, *, output_digest: Optional[str] = None, schema_valid: bool = False,
                authority: bool = False) -> LocalCandidateReceipt:
        receipt = LocalCandidateReceipt(
            model=request.model,
            backend=backend,
            transport=transport,
            task_kind=request.task_kind,
            verdict=CANDIDATE_REFUSED,
            prompt_digest=prompt_digest,
            input_digest=input_digest,
            output_digest=output_digest,
            schema_valid=schema_valid,
            authority_claims_detected=authority,
            refusal_reason=reason,
        )
        _emit(receipt_sink, receipt)
        return receipt

    # 1. Task kind + ration-card fence (zero authority, no writes/shell/net/git).
    if request.task_kind not in SUPPORTED_TASK_KINDS:
        return _refuse(REFUSED_UNSUPPORTED_TASK)
    dispatch = DispatchRequest(agent_id=request.model, task_kind=request.task_kind)
    if match_ration_card(card, dispatch) is not None:
        return _refuse(REFUSED_OUTSIDE_CARD)

    # 2. Call the local model (the only place anything external happens).
    try:
        raw = client.complete(prompt)
    except Exception:  # noqa: BLE001 — any backend failure is a refusal, not a crash
        return _refuse(REFUSED_BACKEND_ERROR)
    if not raw or not raw.strip():
        return _refuse(REFUSED_EMPTY_OUTPUT)
    output_digest = _hash({"output": raw})

    # 3. Extract a JSON object (tolerate fences/prose), then parse + schema-validate.
    json_text = _extract_json_object(raw)
    if json_text is None:
        return _refuse(REFUSED_SCHEMA_INVALID, output_digest=output_digest)
    try:
        parsed = json.loads(json_text)
    except (json.JSONDecodeError, ValueError):
        return _refuse(REFUSED_SCHEMA_INVALID, output_digest=output_digest)
    if not isinstance(parsed, dict) or any(k not in parsed for k in _REQUIRED_KEYS):
        return _refuse(REFUSED_SCHEMA_INVALID, output_digest=output_digest)

    # 4. Authority-claim refusal (the tiny constitution) — BEFORE accepting it.
    if _detect_authority_claims(parsed):
        return _refuse(
            REFUSED_AUTHORITY_CLAIM, output_digest=output_digest, schema_valid=True, authority=True
        )

    likely = parsed["likely_files"]
    if not isinstance(likely, list) or not all(isinstance(x, str) for x in likely):
        return _refuse(REFUSED_SCHEMA_INVALID, output_digest=output_digest)
    if parsed["confidence"] not in CONFIDENCE_LEVELS:
        return _refuse(REFUSED_SCHEMA_INVALID, output_digest=output_digest)
    if not isinstance(parsed["failure_kind"], str) or not isinstance(parsed["next_action"], str):
        return _refuse(REFUSED_SCHEMA_INVALID, output_digest=output_digest)

    # 5. Observed candidate (advisory; non-authoritative by construction).
    candidate = FailureTriage(
        failure_kind=parsed["failure_kind"],
        likely_files=tuple(likely),
        next_action=parsed["next_action"],
        confidence=parsed["confidence"],
        authority_claims=(),
    )
    receipt = LocalCandidateReceipt(
        model=request.model,
        backend=backend,
        transport=transport,
        task_kind=request.task_kind,
        verdict=CANDIDATE_OBSERVED,
        prompt_digest=prompt_digest,
        input_digest=input_digest,
        output_digest=output_digest,
        schema_valid=True,
        authority_claims_detected=False,
        candidate=candidate,
    )
    _emit(receipt_sink, receipt)
    return receipt


def _emit(receipt_sink: Any | None, receipt: LocalCandidateReceipt) -> None:
    if receipt_sink is None:
        return
    receipt_sink.emit(
        gate=LOCAL_CANDIDATE_GATE,
        verdict=LOCAL_CANDIDATE_VERDICT,
        subject_kind="local_candidate",
        subject_bytes=f"{receipt.model}|{receipt.task_kind}|{receipt.verdict}".encode("utf-8"),
        evidence_bundle={"record_kind": "local_candidate", **receipt.as_dict()},
        gate_config={"seam": "local_candidate", "tier": "local", "slice": "S0_failure_triage"},
    )


# --------------------------------------------------------------------------- #
# Live seam: OpenAI-compatible local endpoint (Ollama). NOT exercised in tests
# (tests inject a fake); this is the "swap real client in" point.
# --------------------------------------------------------------------------- #


def ollama_candidate_client(
    model: str, host: str = "http://localhost:11434"
) -> LocalModelClient:
    """Wrap the existing ``chat_bridge.OllamaBackend`` (async) as a synchronous
    ``LocalModelClient``. Localhost loopback is already egress-internal. Imports are
    lazy so this module loads without the chat-bridge dependency."""
    import asyncio

    from .chat_bridge import ChatMessage, create_backend

    # create_backend supplies ollama's default egress gate (localhost = internal).
    backend = create_backend("ollama", host=host)

    class _OllamaClient:
        def complete(self, prompt: str) -> str:
            resp = asyncio.run(
                backend.chat([ChatMessage(role="user", content=prompt)], model=model)
            )
            return resp.content

    return _OllamaClient()


__all__ = [
    "TASK_FAILURE_TRIAGE",
    "SUPPORTED_TASK_KINDS",
    "CONFIDENCE_LEVELS",
    "FORBIDDEN_AUTHORITY_CLAIMS",
    "LOCAL_CANDIDATE_GATE",
    "LOCAL_CANDIDATE_VERDICT",
    "CANDIDATE_OBSERVED",
    "CANDIDATE_REFUSED",
    "CANDIDATE_VERDICTS",
    "REFUSED_OUTSIDE_CARD",
    "REFUSED_UNSUPPORTED_TASK",
    "REFUSED_BACKEND_ERROR",
    "REFUSED_EMPTY_OUTPUT",
    "REFUSED_SCHEMA_INVALID",
    "REFUSED_AUTHORITY_CLAIM",
    "CANDIDATE_REFUSALS",
    "LocalModelClient",
    "LocalCandidateRequest",
    "FailureTriage",
    "LocalCandidateReceipt",
    "build_triage_prompt",
    "all_closed_card",
    "triage_failure",
    "ollama_candidate_client",
]
