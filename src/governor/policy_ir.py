# SPDX-License-Identifier: Apache-2.0
"""Policy Intermediate Representation.

Control slots are policy. Rendered prompts are compiled artifacts.
Natural language is documentation. Control needs an IR.

See specs/gaps/POLICY_IR.md for architecture and evidence.
See specs/gaps/POLYGLOT_FINDINGS.md for benchmark data.

This module is the thin compiler: vocabulary → slot set → renderer → artifact.
Dynamic runtime state (ED scores, accepted sources, anchor lists) is state IR,
not policy IR, and stays in chat_bridge.py.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Protocol


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class PolicyIRError(Exception):
    """Raised on validation failures. Fail closed, fail loud."""


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ControlSlot:
    """A named semantic directive with stable identity.

    slot_id: stable machine key (authority surface)
    category: classification (participates in vocab hash)
    description: human-readable docs (NOT authority, excluded from hash)
    required_params: parameter keys this slot requires when active
    """

    slot_id: str
    category: str
    description: str
    required_params: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlVocabulary:
    """Versioned, content-addressed set of control slots."""

    vocab_id: str
    version: str
    slots: tuple[ControlSlot, ...]
    content_hash: str  # computed from (slot_id, category) pairs

    def slot_by_id(self, slot_id: str) -> ControlSlot | None:
        for s in self.slots:
            if s.slot_id == slot_id:
                return s
        return None


@dataclass(frozen=True)
class SlotSet:
    """An ordered set of active slots with parameters.

    active: ordered tuple of slot IDs (render order = tuple order)
    parameters: sorted tuple of (key, value) pairs
    """

    vocab_id: str
    active: tuple[str, ...]
    parameters: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RenderResult:
    """The compiled artifact from rendering a slot set."""

    text: str
    renderer_id: str
    renderer_version: str
    vocab_id: str
    vocab_version: str
    vocab_hash: str
    slot_set_hash: str
    content_hash: str
    slots_rendered: tuple[str, ...]
    parameters_resolved: tuple[tuple[str, str], ...]


# ---------------------------------------------------------------------------
# Canonical helpers
# ---------------------------------------------------------------------------

def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def hash_vocab(vocab: ControlVocabulary) -> str:
    """Hash over sorted (slot_id, category) pairs. Description excluded."""
    pairs = sorted((s.slot_id, s.category) for s in vocab.slots)
    return "sha256:" + hashlib.sha256(_canonical_json(pairs).encode()).hexdigest()


def build_vocab(
    vocab_id: str, version: str, slots: tuple[ControlSlot, ...],
) -> ControlVocabulary:
    """Build a vocabulary with computed content hash."""
    v = ControlVocabulary(vocab_id=vocab_id, version=version, slots=slots, content_hash="")
    h = hash_vocab(v)
    return ControlVocabulary(vocab_id=vocab_id, version=version, slots=slots, content_hash=h)


def hash_slot_set(ss: SlotSet) -> str:
    """Hash over (active tuple + parameters tuple)."""
    payload = _canonical_json({"active": ss.active, "parameters": ss.parameters})
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def make_slot_set(
    vocab_id: str,
    active: tuple[str, ...] | list[str],
    parameters: tuple[tuple[str, str], ...] | list[tuple[str, str]] | None = None,
) -> SlotSet:
    """Construct a SlotSet with canonicalization.

    - Deduplicates active (preserving first occurrence order)
    - Sorts parameters by key
    """
    # Deduplicate preserving order
    seen: set[str] = set()
    deduped: list[str] = []
    for s in active:
        if s not in seen:
            seen.add(s)
            deduped.append(s)

    params = tuple(sorted(parameters or (), key=lambda p: p[0]))

    return SlotSet(
        vocab_id=vocab_id,
        active=tuple(deduped),
        parameters=params,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_slot_set(ss: SlotSet, vocab: ControlVocabulary) -> None:
    """Validate a slot set against a vocabulary. Raises PolicyIRError on failure."""
    if ss.vocab_id != vocab.vocab_id:
        raise PolicyIRError(
            f"Vocab ID mismatch: slot set has {ss.vocab_id!r}, vocab has {vocab.vocab_id!r}"
        )

    vocab_ids = {s.slot_id for s in vocab.slots}
    param_keys = {k for k, _ in ss.parameters}

    for slot_id in ss.active:
        if slot_id not in vocab_ids:
            raise PolicyIRError(f"Unknown slot: {slot_id!r}")

    # Check duplicates (should be prevented by make_slot_set, but belt + suspenders)
    if len(ss.active) != len(set(ss.active)):
        dupes = [s for s in ss.active if ss.active.count(s) > 1]
        raise PolicyIRError(f"Duplicate slots in active: {dupes}")

    # Check required params
    for slot_id in ss.active:
        slot = vocab.slot_by_id(slot_id)
        if slot is None:
            continue  # already caught above
        for rp in slot.required_params:
            if rp not in param_keys:
                raise PolicyIRError(
                    f"Slot {slot_id!r} requires parameter {rp!r}, not provided"
                )


# ---------------------------------------------------------------------------
# Renderer protocol
# ---------------------------------------------------------------------------

class Renderer(Protocol):
    renderer_id: str
    renderer_version: str

    def render(self, slot_set: SlotSet, vocab: ControlVocabulary) -> RenderResult: ...


def _build_render_result(
    text: str,
    renderer_id: str,
    renderer_version: str,
    vocab: ControlVocabulary,
    slot_set: SlotSet,
    slots_rendered: tuple[str, ...],
    parameters_resolved: tuple[tuple[str, str], ...],
) -> RenderResult:
    return RenderResult(
        text=text,
        renderer_id=renderer_id,
        renderer_version=renderer_version,
        vocab_id=vocab.vocab_id,
        vocab_version=vocab.version,
        vocab_hash=vocab.content_hash,
        slot_set_hash=hash_slot_set(slot_set),
        content_hash="sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        slots_rendered=slots_rendered,
        parameters_resolved=parameters_resolved,
    )


# ---------------------------------------------------------------------------
# Core vocabulary: governor_core_v1
# ---------------------------------------------------------------------------

# Global baseline
GOVERNANCE_INVISIBLE = ControlSlot(
    "GOVERNANCE_INVISIBLE", "behavioral",
    "Governance must never surface in-band",
)
EXIT_CLEAN = ControlSlot(
    "EXIT_CLEAN", "behavioral",
    "No moral bows, unearned conclusions, or CTAs",
)
EVIDENCE_REQUIRED = ControlSlot(
    "EVIDENCE_REQUIRED", "epistemic",
    "Cite evidence for claims; don't fabricate",
)

# Fiction
CANON_AUTHORITY_BOUNDARY = ControlSlot(
    "CANON_AUTHORITY_BOUNDARY", "structural",
    "Chat is provisional; canon lives in UI stores",
)
AFFECT_REGIME_AWARE = ControlSlot(
    "AFFECT_REGIME_AWARE", "behavioral",
    "Regime-specific pacing and tone",
    required_params=("regime",),
)
CHARACTER_CONSISTENCY = ControlSlot(
    "CHARACTER_CONSISTENCY", "structural",
    "Track motivations, flag contradictions with established facts",
)
NO_COMMITTEE_VOICE = ControlSlot(
    "NO_COMMITTEE_VOICE", "behavioral",
    "No apologies, no meta-commentary, no authorial anxiety",
)

# Code
ARCHITECTURAL_COHERENCE = ControlSlot(
    "ARCHITECTURAL_COHERENCE", "structural",
    "Reference existing decisions before proposing changes",
)
PATTERN_CONFLICT_DETECTION = ControlSlot(
    "PATTERN_CONFLICT_DETECTION", "structural",
    "Flag contradictions with established patterns",
)
EPISTEMIC_CARE = ControlSlot(
    "EPISTEMIC_CARE", "epistemic",
    "Don't claim files exist without checking",
)

# Nonfiction
CLAIM_TAXONOMY = ControlSlot(
    "CLAIM_TAXONOMY", "epistemic",
    "Claims have levels: SOFT (maybe), HARD (supported), NORM (value-laden)",
)
CLAIM_VELOCITY = ControlSlot(
    "CLAIM_VELOCITY", "epistemic",
    "Claim rate must not outpace evidence rate",
)
HEDGE_CALIBRATION = ControlSlot(
    "HEDGE_CALIBRATION", "behavioral",
    "Epistemic hedges (uncertainty) are appropriate; social hedges (anxiety) reveal governance",
)
FALSIFIER_EXPOSURE = ControlSlot(
    "FALSIFIER_EXPOSURE", "epistemic",
    "Expose boundary conditions and falsifiers; engage alternatives honestly",
)
STRUCTURAL_INTEGRITY = ControlSlot(
    "STRUCTURAL_INTEGRITY", "structural",
    "Verify citations, maintain consistent terminology, track argument structure",
)

# Research
EPISTEMIC_DEBT_TRACKING = ControlSlot(
    "EPISTEMIC_DEBT_TRACKING", "epistemic",
    "ED score visible; floating claims are liabilities",
)
CLAIM_LIFECYCLE = ControlSlot(
    "CLAIM_LIFECYCLE", "epistemic",
    "Claims start FLOATING; need evidence links or resolution",
)
LINK_TYPING = ControlSlot(
    "LINK_TYPING", "structural",
    "Typed links: SUPPORTS, CONTESTS, ASSUMES, SUPERSEDES, NARROWS",
)
SOURCE_DISCIPLINE = ControlSlot(
    "SOURCE_DISCIPLINE", "structural",
    "Only cite accepted refs; new sources via CANDIDATE_SOURCE flow",
)
ASSUMPTION_SURFACING = ControlSlot(
    "ASSUMPTION_SURFACING", "epistemic",
    "Surface assumptions early; hidden assumptions are worst debt",
)

CORE_VOCAB = build_vocab(
    "governor_core_v1",
    "0.1.0",
    (
        # Global
        GOVERNANCE_INVISIBLE, EXIT_CLEAN, EVIDENCE_REQUIRED,
        # Fiction
        CANON_AUTHORITY_BOUNDARY, AFFECT_REGIME_AWARE, CHARACTER_CONSISTENCY,
        NO_COMMITTEE_VOICE,
        # Code
        ARCHITECTURAL_COHERENCE, PATTERN_CONFLICT_DETECTION, EPISTEMIC_CARE,
        # Nonfiction
        CLAIM_TAXONOMY, CLAIM_VELOCITY, HEDGE_CALIBRATION, FALSIFIER_EXPOSURE,
        STRUCTURAL_INTEGRITY,
        # Research
        EPISTEMIC_DEBT_TRACKING, CLAIM_LIFECYCLE, LINK_TYPING, SOURCE_DISCIPLINE,
        ASSUMPTION_SURFACING,
    ),
)


# ---------------------------------------------------------------------------
# Mode → SlotSet composition
# ---------------------------------------------------------------------------

_GLOBAL_BASELINE = (
    "GOVERNANCE_INVISIBLE",
    "EXIT_CLEAN",
    "EVIDENCE_REQUIRED",
)

_MODE_SLOTS: dict[str, tuple[str, ...]] = {
    "fiction": (
        "CANON_AUTHORITY_BOUNDARY",
        "AFFECT_REGIME_AWARE",
        "NO_COMMITTEE_VOICE",
        "CHARACTER_CONSISTENCY",
    ),
    "code": (
        "ARCHITECTURAL_COHERENCE",
        "PATTERN_CONFLICT_DETECTION",
        "EPISTEMIC_CARE",
    ),
    "nonfiction": (
        "CLAIM_TAXONOMY",
        "CLAIM_VELOCITY",
        "HEDGE_CALIBRATION",
        "FALSIFIER_EXPOSURE",
        "STRUCTURAL_INTEGRITY",
    ),
    "research": (
        "EPISTEMIC_DEBT_TRACKING",
        "CLAIM_LIFECYCLE",
        "LINK_TYPING",
        "SOURCE_DISCIPLINE",
        "ASSUMPTION_SURFACING",
    ),
}


def mode_slot_set(mode: str, **params: str) -> SlotSet | None:
    """Build a SlotSet for a mode by composing global baseline + mode slots.

    Returns None for unknown modes.
    """
    mode_specific = _MODE_SLOTS.get(mode)
    if mode_specific is None:
        return None

    active = _GLOBAL_BASELINE + mode_specific
    param_tuples = tuple(sorted(params.items()))

    return make_slot_set(
        vocab_id=CORE_VOCAB.vocab_id,
        active=active,
        parameters=param_tuples,
    )


# ---------------------------------------------------------------------------
# ProseRenderer — byte-identical to incumbent prompts
# ---------------------------------------------------------------------------

class ProseRenderer:
    """Renders slot sets as English prose matching current GovernorHooks output.

    This is a 'mildly dishonest compiler': mode-specific render plans with
    grouped composites where the original prose wasn't cleanly decomposable.
    Its job is compatibility, not ideological purity.
    """

    renderer_id: str = "prose_v1"
    renderer_version: str = "0.1.0"

    def render(self, slot_set: SlotSet, vocab: ControlVocabulary) -> RenderResult:
        params = dict(slot_set.parameters)

        # Mode-specific render plans
        active_set = set(slot_set.active)
        if "CANON_AUTHORITY_BOUNDARY" in active_set:
            text = self._render_fiction(params)
        elif "ARCHITECTURAL_COHERENCE" in active_set:
            text = self._render_code()
        elif "CLAIM_TAXONOMY" in active_set:
            text = self._render_nonfiction()
        elif "EPISTEMIC_DEBT_TRACKING" in active_set:
            text = self._render_research()
        else:
            raise PolicyIRError(
                f"ProseRenderer cannot determine mode from slot set: {slot_set.active}"
            )

        resolved_params = tuple(
            (k, v) for k, v in sorted(params.items())
            if any(k in (vocab.slot_by_id(s) or ControlSlot("", "", "")).required_params
                   for s in slot_set.active)
        )

        return _build_render_result(
            text=text,
            renderer_id=self.renderer_id,
            renderer_version=self.renderer_version,
            vocab=vocab,
            slot_set=slot_set,
            slots_rendered=slot_set.active,
            parameters_resolved=resolved_params,
        )

    def _render_fiction(self, params: dict[str, str]) -> str:
        regime = params.get("regime", "neutral")
        return (
            "You are a fiction writing assistant with governor integration.\n\n"
            "## Core Invariant\n"
            "Governance must never surface in-band. The reader should never detect "
            "that an author is managing outcomes. No apologies, no meta-commentary, "
            "no committee voice, no hedging that reveals authorial anxiety.\n\n"
            "## Canon Authority\n"
            "Canonical truth lives only in the Characters and World Rules stores.\n"
            "Facts mentioned in chat are provisional draft notes until saved to canon.\n"
            "Do not imply a chat-stated fact is \"remembered\" or established canon "
            "unless it exists in canon.\n"
            "When the user states a new character or world fact that is not in canon, "
            "acknowledge it as a draft detail and include a single short nudge: "
            "\"If you want that to stick, add it under Characters/World Rules.\"\n"
            "If the user asks for consistency or recall and the fact is not in canon, "
            "say so plainly and point to the canon UI.\n\n"
            "## Affect Regime\n"
            f"Current regime: {regime}. Maintain regime-appropriate tone and pacing.\n"
            "- Comedy: preserve perceived risk (Rp). Hedges kill comedy.\n"
            "- Tragedy: meaning must lag suffering. Don't explain too soon.\n"
            "- Horror: maintain unresolved threat. Premature closure kills tension.\n"
            "- Romance: authentic vulnerability. Fake confidence kills credibility.\n\n"
            "## Consistency\n"
            "- Track character motivations and beliefs\n"
            "- Note when actions might contradict established facts\n"
            "- Respect the narrative tone and style\n"
            "- Exit cleanly without moral bows or unearned CTAs"
        )

    def _render_code(self) -> str:
        return (
            "You are a code development assistant with governor integration. "
            "Help maintain architectural coherence:\n"
            "- Reference existing decisions before proposing changes\n"
            "- Cite evidence for claims about the codebase\n"
            "- Flag potential conflicts with established patterns\n"
            "- Don't claim files exist without checking"
        )

    def _render_nonfiction(self) -> str:
        return (
            "You are a non-fiction writing assistant with governor integration.\n\n"
            "## Core Invariant\n"
            "Governance must never surface in-band. No preemptive defense, no virtue "
            "signaling, no balance theater, no empty rigor markers.\n\n"
            "## Epistemic Control\n"
            "- Claims have levels: SOFT (maybe), HARD (supported), NORM (value-laden)\n"
            "- Don't promote claims without explicit evidence support\n"
            "- Maintain velocity discipline: claim rate should not outpace evidence\n"
            "- Normative claims require sufficient evidence foundation first\n\n"
            "## Epistemic Honesty (Ep)\n"
            "- Calibrate hedges: epistemic hedges (uncertainty) are appropriate, "
            "social hedges (anxiety) reveal governance\n"
            "- Expose falsifiers and boundary conditions\n"
            "- Engage alternatives honestly, not as strawmen\n\n"
            "## Structural Integrity\n"
            "- Verify citations and references\n"
            "- Maintain consistent terminology\n"
            "- Track the argument structure\n"
            "- Exit cleanly without moral inflation or unearned conclusions"
        )

    def _render_research(self) -> str:
        return (
            "You are a research writing assistant with epistemic debt tracking.\n\n"
            "## Core Principle\n"
            "Epistemic debt is like technical debt: visible, survivable, impossible "
            "to gaslight away. Every claim starts FLOATING until supported by evidence. "
            "Unsupported claims are liabilities, not lies — but they accumulate.\n\n"
            "## Claim Registration\n"
            "- Register claims explicitly. A claim without a scope is a liability.\n"
            "- Support claims with typed links (SUPPORTS, CONTESTS, ASSUMES, "
            "SUPERSEDES, NARROWS).\n"
            "- FLOATING claims need evidence. CONTESTED claims need resolution.\n\n"
            "## Assumptions & Uncertainties\n"
            "- Surface assumptions early. Hidden assumptions are the worst debt.\n"
            "- Log uncertainties when you find them. An acknowledged uncertainty is "
            "better than a hidden one.\n"
            "- Resolving uncertainty without new support is a collapse — it inflates ED.\n\n"
            "## ED Score\n"
            "- ED rises with floating claims, missing scopes, open uncertainties, "
            "collapse events, and unresolved contests.\n"
            "- Reduce ED by adding support links, filling in scopes, and resolving "
            "uncertainties with evidence."
        )


# ---------------------------------------------------------------------------
# MinimalRenderer — true IR renderer with defined grammar
# ---------------------------------------------------------------------------

class MinimalRenderer:
    """Renders slot sets as semicolon-delimited compact syntax.

    Grammar:
      output     = slot_token (";" slot_token)*
      slot_token = SLOT_ID | SLOT_ID "(" params ")"
      params     = param ("," param)*
      param      = KEY "=" VALUE
      SLOT_ID    = [a-z_]+
      KEY        = [a-z_]+
      VALUE      = [a-z0-9_]+

    Rules:
      - lowercase only
      - semicolon delimiter, no spaces
      - params sorted by key
      - values constrained to [a-z0-9_]
    """

    renderer_id: str = "minimal_v1"
    renderer_version: str = "0.1.0"

    def render(self, slot_set: SlotSet, vocab: ControlVocabulary) -> RenderResult:
        params = dict(slot_set.parameters)
        tokens: list[str] = []
        resolved: list[tuple[str, str]] = []

        for slot_id in slot_set.active:
            slot = vocab.slot_by_id(slot_id)
            if slot is None:
                raise PolicyIRError(f"Slot {slot_id!r} not in vocabulary")

            token = slot_id.lower()
            if slot.required_params:
                param_parts = []
                for rp in sorted(slot.required_params):
                    val = params.get(rp)
                    if val is None:
                        raise PolicyIRError(
                            f"Slot {slot_id!r} requires parameter {rp!r}"
                        )
                    # Sanitize value to grammar constraint
                    safe_val = "".join(c for c in val.lower() if c.isalnum() or c == "_")
                    param_parts.append(f"{rp}={safe_val}")
                    resolved.append((rp, val))
                token += "(" + ",".join(param_parts) + ")"

            tokens.append(token)

        text = ";".join(tokens)

        return _build_render_result(
            text=text,
            renderer_id=self.renderer_id,
            renderer_version=self.renderer_version,
            vocab=vocab,
            slot_set=slot_set,
            slots_rendered=slot_set.active,
            parameters_resolved=tuple(sorted(resolved)),
        )


# ---------------------------------------------------------------------------
# Default renderer
# ---------------------------------------------------------------------------

def get_default_renderer() -> ProseRenderer:
    """Return the default renderer. Explicit, not hidden."""
    return ProseRenderer()
