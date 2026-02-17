# SPDX-License-Identifier: Apache-2.0
"""
Puppet Mode — Runtime persona pinning with semantic safety.

Pins a character policy (voice + allowed moves) while forcing outputs through
commit/ledger gates. Separates stance from commitment.

Key invariants:
1. Puppet layer is cosmetic — cannot introduce new claims
2. Semantic diff guard blocks certainty escalation, new entities, polarity flips
3. Content draft is generated first, puppet rendering applied second
4. Commit decisions happen on the draft, not the rendered output
5. Code blocks and no-rewrite zones are protected from transformation

Pipeline:
    draft → commit gating → skeleton → PuppetRenderer → DiffGuard → emit
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .semvar import (
    Register,
    TextInvariants,
    extract_invariants,
    mask_no_rewrite_zones,
    restore_zones,
)
from .strict import ClaimCategory, CommitLevel


# =============================================================================
# Enums
# =============================================================================


class CertaintyLevel(str, Enum):
    """Modal certainty classification."""

    HIGH = "high"       # is, does, will, has, must
    MEDIUM = "medium"   # likely, probably, should
    LOW = "low"         # might, maybe, plausibly, could


class TagPosition(str, Enum):
    """Where to place the role disclaimer tag."""

    PREFIX = "prefix"
    SUFFIX = "suffix"
    NONE = "none"


class AnswerMode(str, Enum):
    """Interaction style for the puppet."""

    DIRECT = "direct"
    DIAGNOSTIC = "diagnostic"
    SKEPTICAL = "skeptical"


class DiffRuleId(str, Enum):
    """Hard diff-guard rules (violations block rendering)."""

    R1_NEW_ENTITIES = "R1_NEW_ENTITIES"
    R2_NEW_NUMBERS = "R2_NEW_NUMBERS"
    R3_CERTAINTY_ESCALATION = "R3_CERTAINTY_ESCALATION"
    R4_SCOPE_ESCALATION = "R4_SCOPE_ESCALATION"
    R5_CITATION_REMOVAL = "R5_CITATION_REMOVAL"
    R6_POLARITY_FLIP = "R6_POLARITY_FLIP"
    R7_NEW_INSTRUCTIONS = "R7_NEW_INSTRUCTIONS"


class DiffWarnId(str, Enum):
    """Soft diff-guard warnings (informational, don't block)."""

    W1_COMPRESSION_RISK = "W1_COMPRESSION_RISK"
    W2_TONE_DRIFT = "W2_TONE_DRIFT"


class RenderVerdict(str, Enum):
    """Outcome of the puppet rendering pipeline."""

    PASSED = "passed"           # First attempt passed diff guard
    RERENDERED = "rerendered"   # Passed after retry with stricter constraints
    FALLBACK = "fallback"       # All attempts failed, returning original


# =============================================================================
# Certainty helpers
# =============================================================================

_HIGH_WORDS = frozenset({
    "is", "does", "will", "has", "must", "always", "never",
    "certainly", "definitely", "absolutely", "undoubtedly",
})
_MEDIUM_WORDS = frozenset({
    "likely", "probably", "should", "expected", "typically",
    "generally", "usually", "presumably",
})
_LOW_WORDS = frozenset({
    "might", "maybe", "plausibly", "could", "possibly",
    "perhaps", "conceivably", "potentially",
})

_IMPERATIVE_VERBS = frozenset({
    "run", "delete", "buy", "send", "install", "execute", "remove",
    "create", "update", "deploy", "stop", "start", "kill", "drop",
    "apply", "use", "set", "add", "move", "copy", "open", "close",
})

_CITATION_RE = re.compile(r"\[(?:\d+|[a-zA-Z][a-zA-Z0-9_-]*(?:\s+\d{4})?|source|ref|ibid)\]")


def classify_certainty(word: str) -> CertaintyLevel | None:
    """Classify a single word into a certainty level, or None if unknown."""
    w = word.lower().rstrip(".,;:!?")
    if w in _HIGH_WORDS:
        return CertaintyLevel.HIGH
    if w in _MEDIUM_WORDS:
        return CertaintyLevel.MEDIUM
    if w in _LOW_WORDS:
        return CertaintyLevel.LOW
    return None


def extract_certainty_profile(text: str) -> dict[CertaintyLevel, int]:
    """Count occurrences of each certainty level in text."""
    counts: dict[CertaintyLevel, int] = {
        CertaintyLevel.HIGH: 0,
        CertaintyLevel.MEDIUM: 0,
        CertaintyLevel.LOW: 0,
    }
    for word in text.split():
        level = classify_certainty(word)
        if level is not None:
            counts[level] += 1
    return counts


def extract_imperatives(text: str) -> set[str]:
    """Find imperative verbs at the start of sentences or after punctuation."""
    found: set[str] = set()
    # Split on sentence boundaries
    sentences = re.split(r"[.!?]\s+|^\s*", text)
    for sent in sentences:
        words = sent.strip().split()
        if words:
            w = words[0].lower().rstrip(".,;:!?")
            if w in _IMPERATIVE_VERBS:
                found.add(w)
    return found


def extract_citations(text: str) -> set[str]:
    """Find citation markers like [1], [source], [Smith 2020]."""
    return set(_CITATION_RE.findall(text))


# =============================================================================
# Dataclasses — Configuration
# =============================================================================


@dataclass
class FormattingRules:
    """Formatting constraints for puppet output."""

    allow_lists: bool = True
    allow_headings: bool = True
    allow_tables: bool = False
    max_bullets_per_list: int = 10
    max_lists: int = 4

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_lists": self.allow_lists,
            "allow_headings": self.allow_headings,
            "allow_tables": self.allow_tables,
            "max_bullets_per_list": self.max_bullets_per_list,
            "max_lists": self.max_lists,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FormattingRules:
        return cls(
            allow_lists=d.get("allow_lists", True),
            allow_headings=d.get("allow_headings", True),
            allow_tables=d.get("allow_tables", False),
            max_bullets_per_list=d.get("max_bullets_per_list", 10),
            max_lists=d.get("max_lists", 4),
        )


@dataclass
class VoiceConstraints:
    """Voice and stylistic constraints for a puppet persona."""

    tone_tags: list[str] = field(default_factory=list)
    register: Register = Register.NEUTRAL
    verbosity_cap_tokens: int = 500
    forbidden_phrases: list[str] = field(default_factory=list)
    required_ticks: list[str] = field(default_factory=list)
    formatting: FormattingRules = field(default_factory=FormattingRules)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tone_tags": self.tone_tags,
            "register": self.register.value,
            "verbosity_cap_tokens": self.verbosity_cap_tokens,
            "forbidden_phrases": self.forbidden_phrases,
            "required_ticks": self.required_ticks,
            "formatting": self.formatting.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VoiceConstraints:
        return cls(
            tone_tags=d.get("tone_tags", []),
            register=Register(d["register"]) if "register" in d else Register.NEUTRAL,
            verbosity_cap_tokens=d.get("verbosity_cap_tokens", 500),
            forbidden_phrases=d.get("forbidden_phrases", []),
            required_ticks=d.get("required_ticks", []),
            formatting=FormattingRules.from_dict(d["formatting"]) if "formatting" in d else FormattingRules(),
        )


@dataclass
class HedgePolicy:
    """Controls hedging language in puppet output."""

    soft_markers: list[str] = field(default_factory=list)
    hard_markers: list[str] = field(default_factory=list)
    forbid_overclaim_words: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "soft_markers": self.soft_markers,
            "hard_markers": self.hard_markers,
            "forbid_overclaim_words": self.forbid_overclaim_words,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HedgePolicy:
        return cls(
            soft_markers=d.get("soft_markers", []),
            hard_markers=d.get("hard_markers", []),
            forbid_overclaim_words=d.get("forbid_overclaim_words", []),
        )


@dataclass
class VolatilityPolicy:
    """Controls how the puppet handles volatile/time-sensitive claims."""

    allow_news_like_claims: bool = True
    force_sources_for_volatile: bool = True
    freshness_max_seconds: dict[str, int] = field(default_factory=lambda: {
        "LOW": 86400 * 30,   # 30 days
        "MEDIUM": 86400 * 7, # 7 days
        "HIGH": 3600,        # 1 hour
    })

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_news_like_claims": self.allow_news_like_claims,
            "force_sources_for_volatile": self.force_sources_for_volatile,
            "freshness_max_seconds": self.freshness_max_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> VolatilityPolicy:
        return cls(
            allow_news_like_claims=d.get("allow_news_like_claims", True),
            force_sources_for_volatile=d.get("force_sources_for_volatile", True),
            freshness_max_seconds=d.get("freshness_max_seconds", {
                "LOW": 86400 * 30,
                "MEDIUM": 86400 * 7,
                "HIGH": 3600,
            }),
        )


@dataclass
class EpistemicPosture:
    """How the puppet handles epistemic claims and uncertainty."""

    allowed_claim_types: list[ClaimCategory] = field(default_factory=lambda: list(ClaimCategory))
    default_commit_level: dict[str, CommitLevel] = field(default_factory=dict)
    volatility_policy: VolatilityPolicy = field(default_factory=VolatilityPolicy)
    hedge_policy: HedgePolicy = field(default_factory=HedgePolicy)

    def get_commit_level(self, category: ClaimCategory) -> CommitLevel:
        """Get the default commit level for a claim category."""
        return self.default_commit_level.get(category.value, CommitLevel.SOFT)

    def allows_claim_type(self, category: ClaimCategory) -> bool:
        """Check whether this posture allows a given claim category."""
        return category in self.allowed_claim_types

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_claim_types": [c.value for c in self.allowed_claim_types],
            "default_commit_level": {k: v.value for k, v in self.default_commit_level.items()},
            "volatility_policy": self.volatility_policy.to_dict(),
            "hedge_policy": self.hedge_policy.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EpistemicPosture:
        return cls(
            allowed_claim_types=[ClaimCategory(c) for c in d.get("allowed_claim_types", [c.value for c in ClaimCategory])],
            default_commit_level={k: CommitLevel(v) for k, v in d.get("default_commit_level", {}).items()},
            volatility_policy=VolatilityPolicy.from_dict(d["volatility_policy"]) if "volatility_policy" in d else VolatilityPolicy(),
            hedge_policy=HedgePolicy.from_dict(d["hedge_policy"]) if "hedge_policy" in d else HedgePolicy(),
        )


@dataclass
class BehavioralConstraints:
    """Behavioral rules for the puppet."""

    refuse_domains: list[str] = field(default_factory=list)
    allow_tools: list[str] = field(default_factory=list)
    forbid_tools: list[str] = field(default_factory=list)
    require_tool_for: dict[str, list[str]] = field(default_factory=dict)
    interaction_style: AnswerMode = AnswerMode.DIRECT
    ask_clarifying_questions: bool = True
    max_questions: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "refuse_domains": self.refuse_domains,
            "allow_tools": self.allow_tools,
            "forbid_tools": self.forbid_tools,
            "require_tool_for": self.require_tool_for,
            "interaction_style": self.interaction_style.value,
            "ask_clarifying_questions": self.ask_clarifying_questions,
            "max_questions": self.max_questions,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> BehavioralConstraints:
        return cls(
            refuse_domains=d.get("refuse_domains", []),
            allow_tools=d.get("allow_tools", []),
            forbid_tools=d.get("forbid_tools", []),
            require_tool_for=d.get("require_tool_for", {}),
            interaction_style=AnswerMode(d["interaction_style"]) if "interaction_style" in d else AnswerMode.DIRECT,
            ask_clarifying_questions=d.get("ask_clarifying_questions", True),
            max_questions=d.get("max_questions", 1),
        )


@dataclass
class RoleDisclaimer:
    """Disclaimer tag applied to puppet output."""

    enabled: bool = True
    tag_format: TagPosition = TagPosition.PREFIX
    tag_text: str = ""

    def apply(self, text: str) -> str:
        """Apply the disclaimer tag to text."""
        if not self.enabled or not self.tag_text:
            return text
        if self.tag_format == TagPosition.PREFIX:
            return f"{self.tag_text}\n\n{text}"
        if self.tag_format == TagPosition.SUFFIX:
            return f"{text}\n\n{self.tag_text}"
        return text

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "tag_format": self.tag_format.value,
            "tag_text": self.tag_text,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RoleDisclaimer:
        return cls(
            enabled=d.get("enabled", True),
            tag_format=TagPosition(d["tag_format"]) if "tag_format" in d else TagPosition.PREFIX,
            tag_text=d.get("tag_text", ""),
        )


@dataclass
class SafetyOverrides:
    """Safety constraints that override puppet personality."""

    allow_spice: bool = False
    forbid_insults: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_spice": self.allow_spice,
            "forbid_insults": self.forbid_insults,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SafetyOverrides:
        return cls(
            allow_spice=d.get("allow_spice", False),
            forbid_insults=d.get("forbid_insults", True),
        )


# =============================================================================
# Dataclasses — Profile
# =============================================================================


@dataclass
class PuppetProfile:
    """Complete puppet persona definition."""

    puppet_id: str
    version: str = "1.0"
    description: str = ""
    voice: VoiceConstraints = field(default_factory=VoiceConstraints)
    epistemic: EpistemicPosture = field(default_factory=EpistemicPosture)
    behavioral: BehavioralConstraints = field(default_factory=BehavioralConstraints)
    disclaimer: RoleDisclaimer = field(default_factory=RoleDisclaimer)
    safety: SafetyOverrides = field(default_factory=SafetyOverrides)

    def to_dict(self) -> dict[str, Any]:
        return {
            "puppet_id": self.puppet_id,
            "version": self.version,
            "description": self.description,
            "voice": self.voice.to_dict(),
            "epistemic": self.epistemic.to_dict(),
            "behavioral": self.behavioral.to_dict(),
            "disclaimer": self.disclaimer.to_dict(),
            "safety": self.safety.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PuppetProfile:
        return cls(
            puppet_id=d["puppet_id"],
            version=d.get("version", "1.0"),
            description=d.get("description", ""),
            voice=VoiceConstraints.from_dict(d["voice"]) if "voice" in d else VoiceConstraints(),
            epistemic=EpistemicPosture.from_dict(d["epistemic"]) if "epistemic" in d else EpistemicPosture(),
            behavioral=BehavioralConstraints.from_dict(d["behavioral"]) if "behavioral" in d else BehavioralConstraints(),
            disclaimer=RoleDisclaimer.from_dict(d["disclaimer"]) if "disclaimer" in d else RoleDisclaimer(),
            safety=SafetyOverrides.from_dict(d["safety"]) if "safety" in d else SafetyOverrides(),
        )


# =============================================================================
# Dataclasses — Diff Guard
# =============================================================================


@dataclass
class DiffViolation:
    """A single hard rule violation from the diff guard."""

    rule_id: DiffRuleId
    description: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id.value,
            "description": self.description,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DiffViolation:
        return cls(
            rule_id=DiffRuleId(d["rule_id"]),
            description=d["description"],
            detail=d.get("detail", ""),
        )


@dataclass
class DiffWarning:
    """A soft warning from the diff guard."""

    warn_id: DiffWarnId
    description: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.warn_id.value,
            "description": self.description,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DiffWarning:
        return cls(
            warn_id=DiffWarnId(d["rule_id"]),
            description=d["description"],
            detail=d.get("detail", ""),
        )


@dataclass
class DiffGuardResult:
    """Result of the puppet diff guard check."""

    passed: bool
    violations: list[DiffViolation] = field(default_factory=list)
    warnings: list[DiffWarning] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
            "warnings": [w.to_dict() for w in self.warnings],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DiffGuardResult:
        return cls(
            passed=d["passed"],
            violations=[DiffViolation.from_dict(v) for v in d.get("violations", [])],
            warnings=[DiffWarning.from_dict(w) for w in d.get("warnings", [])],
        )


# =============================================================================
# Dataclasses — Skeleton & Render Result
# =============================================================================


@dataclass
class SkeletonAtom:
    """A unit in the answer skeleton."""

    text: str
    commit_level: CommitLevel = CommitLevel.SOFT
    category: ClaimCategory | None = None
    citations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "commit_level": self.commit_level.value,
            "category": self.category.value if self.category else None,
            "citations": self.citations,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SkeletonAtom:
        return cls(
            text=d["text"],
            commit_level=CommitLevel(d["commit_level"]) if "commit_level" in d else CommitLevel.SOFT,
            category=ClaimCategory(d["category"]) if d.get("category") else None,
            citations=d.get("citations", []),
        )


@dataclass
class AnswerSkeleton:
    """Structured pre-puppet output."""

    atoms: list[SkeletonAtom] = field(default_factory=list)
    raw_text: str = ""

    def full_text(self) -> str:
        """Join atom texts to produce the full skeleton text."""
        if self.atoms:
            return " ".join(a.text for a in self.atoms)
        return self.raw_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "atoms": [a.to_dict() for a in self.atoms],
            "raw_text": self.raw_text,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> AnswerSkeleton:
        return cls(
            atoms=[SkeletonAtom.from_dict(a) for a in d.get("atoms", [])],
            raw_text=d.get("raw_text", ""),
        )


@dataclass
class PuppetRenderResult:
    """Result of the puppet rendering pipeline."""

    original: str
    rendered: str
    verdict: RenderVerdict
    guard_result: DiffGuardResult
    attempts: int = 1
    disclaimer_applied: bool = False
    forbidden_phrases_removed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "rendered": self.rendered,
            "verdict": self.verdict.value,
            "guard_result": self.guard_result.to_dict(),
            "attempts": self.attempts,
            "disclaimer_applied": self.disclaimer_applied,
            "forbidden_phrases_removed": self.forbidden_phrases_removed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PuppetRenderResult:
        return cls(
            original=d["original"],
            rendered=d["rendered"],
            verdict=RenderVerdict(d["verdict"]),
            guard_result=DiffGuardResult.from_dict(d["guard_result"]),
            attempts=d.get("attempts", 1),
            disclaimer_applied=d.get("disclaimer_applied", False),
            forbidden_phrases_removed=d.get("forbidden_phrases_removed", 0),
        )


# =============================================================================
# PuppetDiffGuard
# =============================================================================


class PuppetDiffGuard:
    """
    Semantic diff guard for puppet rendering.

    Extends semvar's guard with puppet-specific rules. Blocks rendering if
    the puppet introduces new claims, entities, or certainty escalation.
    """

    def __init__(self, compression_threshold: float = 0.5) -> None:
        self.compression_threshold = compression_threshold

    def check(
        self,
        skeleton: AnswerSkeleton,
        rendered: str,
        profile: PuppetProfile,
    ) -> DiffGuardResult:
        """Run all diff-guard rules and return the result."""
        skeleton_text = skeleton.full_text()
        skel_inv = extract_invariants(skeleton_text)
        rend_inv = extract_invariants(rendered)

        violations: list[DiffViolation] = []
        warnings: list[DiffWarning] = []

        # Hard rules (R1-R7)
        checks = [
            self._check_r1_new_entities(skel_inv, rend_inv, profile),
            self._check_r2_new_numbers(skel_inv, rend_inv),
            self._check_r3_certainty_escalation(skeleton_text, rendered),
            self._check_r4_scope_escalation(skeleton, rendered),
            self._check_r5_citation_removal(skeleton, rendered),
            self._check_r6_polarity_flip(skel_inv, rend_inv),
            self._check_r7_new_instructions(skeleton_text, rendered),
        ]
        for result in checks:
            if result is not None:
                violations.append(result)

        # Soft warnings (W1-W2)
        w1 = self._check_w1_compression(skeleton_text, rendered)
        if w1 is not None:
            warnings.append(w1)
        w2 = self._check_w2_tone_drift(rendered, profile)
        if w2 is not None:
            warnings.append(w2)

        return DiffGuardResult(
            passed=len(violations) == 0,
            violations=violations,
            warnings=warnings,
        )

    def _check_r1_new_entities(
        self,
        skel_inv: TextInvariants,
        rend_inv: TextInvariants,
        profile: PuppetProfile,
    ) -> DiffViolation | None:
        """Block if rendered text introduces entities not in the skeleton."""
        new_entities = rend_inv.entities - skel_inv.entities
        # Allow entities from disclaimer tag text
        if profile.disclaimer.enabled and profile.disclaimer.tag_text:
            tag_inv = extract_invariants(profile.disclaimer.tag_text)
            new_entities -= tag_inv.entities
        if new_entities:
            return DiffViolation(
                rule_id=DiffRuleId.R1_NEW_ENTITIES,
                description="Rendered text introduces new entities not in skeleton",
                detail=f"new entities: {{{', '.join(sorted(new_entities))}}}",
            )
        return None

    def _check_r2_new_numbers(
        self,
        skel_inv: TextInvariants,
        rend_inv: TextInvariants,
    ) -> DiffViolation | None:
        """Block if rendered text introduces numbers not in the skeleton."""
        new_numbers = rend_inv.numbers - skel_inv.numbers
        if new_numbers:
            return DiffViolation(
                rule_id=DiffRuleId.R2_NEW_NUMBERS,
                description="Rendered text introduces new numbers not in skeleton",
                detail=f"new numbers: {{{', '.join(sorted(new_numbers))}}}",
            )
        return None

    def _check_r3_certainty_escalation(
        self,
        skeleton_text: str,
        rendered: str,
    ) -> DiffViolation | None:
        """Block if rendering escalates certainty (more HIGH, fewer LOW)."""
        skel_profile = extract_certainty_profile(skeleton_text)
        rend_profile = extract_certainty_profile(rendered)

        high_increase = rend_profile[CertaintyLevel.HIGH] - skel_profile[CertaintyLevel.HIGH]
        low_decrease = skel_profile[CertaintyLevel.LOW] - rend_profile[CertaintyLevel.LOW]

        if high_increase > 0 or low_decrease > 0:
            return DiffViolation(
                rule_id=DiffRuleId.R3_CERTAINTY_ESCALATION,
                description="Rendering escalates certainty level",
                detail=f"HIGH delta: +{high_increase}, LOW delta: -{low_decrease}",
            )
        return None

    def _check_r4_scope_escalation(
        self,
        skeleton: AnswerSkeleton,
        rendered: str,
    ) -> DiffViolation | None:
        """Block if rendering broadens scope (more claim categories)."""
        skeleton_text = skeleton.full_text()
        skel_cats = set()
        for atom in skeleton.atoms:
            if atom.category:
                skel_cats.add(atom.category)

        # Check for scope-broadening words not in skeleton
        scope_words = {"all", "every", "always", "universal", "entire", "complete"}
        skel_scope = {w for w in skeleton_text.lower().split() if w in scope_words}
        rend_scope = {w for w in rendered.lower().split() if w in scope_words}
        new_scope = rend_scope - skel_scope
        if new_scope:
            return DiffViolation(
                rule_id=DiffRuleId.R4_SCOPE_ESCALATION,
                description="Rendering broadens scope with universal quantifiers",
                detail=f"new scope words: {{{', '.join(sorted(new_scope))}}}",
            )
        return None

    def _check_r5_citation_removal(
        self,
        skeleton: AnswerSkeleton,
        rendered: str,
    ) -> DiffViolation | None:
        """Block if rendering removes citations present in skeleton."""
        skeleton_text = skeleton.full_text()
        skel_cites = extract_citations(skeleton_text)
        rend_cites = extract_citations(rendered)
        removed = skel_cites - rend_cites
        if removed:
            return DiffViolation(
                rule_id=DiffRuleId.R5_CITATION_REMOVAL,
                description="Rendering removed citations from skeleton",
                detail=f"removed citations: {{{', '.join(sorted(removed))}}}",
            )
        return None

    def _check_r6_polarity_flip(
        self,
        skel_inv: TextInvariants,
        rend_inv: TextInvariants,
    ) -> DiffViolation | None:
        """Block if negation count changes significantly (polarity flip)."""
        delta = abs(rend_inv.negation_count - skel_inv.negation_count)
        if delta > 0:
            return DiffViolation(
                rule_id=DiffRuleId.R6_POLARITY_FLIP,
                description="Rendering changes negation polarity",
                detail=f"negation count: {skel_inv.negation_count} -> {rend_inv.negation_count}",
            )
        return None

    def _check_r7_new_instructions(
        self,
        skeleton_text: str,
        rendered: str,
    ) -> DiffViolation | None:
        """Block if rendering introduces imperative instructions not in skeleton."""
        skel_imperatives = extract_imperatives(skeleton_text)
        rend_imperatives = extract_imperatives(rendered)
        new_imperatives = rend_imperatives - skel_imperatives
        if new_imperatives:
            return DiffViolation(
                rule_id=DiffRuleId.R7_NEW_INSTRUCTIONS,
                description="Rendering introduces new imperative instructions",
                detail=f"new imperatives: {{{', '.join(sorted(new_imperatives))}}}",
            )
        return None

    def _check_w1_compression(
        self,
        skeleton_text: str,
        rendered: str,
    ) -> DiffWarning | None:
        """Warn if rendered text is significantly shorter than skeleton."""
        if not skeleton_text:
            return None
        ratio = len(rendered) / len(skeleton_text) if len(skeleton_text) > 0 else 1.0
        if ratio < self.compression_threshold:
            return DiffWarning(
                warn_id=DiffWarnId.W1_COMPRESSION_RISK,
                description="Rendered text is significantly shorter than skeleton",
                detail=f"compression ratio: {ratio:.2f} (threshold: {self.compression_threshold})",
            )
        return None

    def _check_w2_tone_drift(
        self,
        rendered: str,
        profile: PuppetProfile,
    ) -> DiffWarning | None:
        """Warn if rendered text contains forbidden phrases from the profile."""
        found = []
        rendered_lower = rendered.lower()
        for phrase in profile.voice.forbidden_phrases:
            if phrase.lower() in rendered_lower:
                found.append(phrase)
        if found:
            return DiffWarning(
                warn_id=DiffWarnId.W2_TONE_DRIFT,
                description="Rendered text contains forbidden phrases",
                detail=f"found: {{{', '.join(found)}}}",
            )
        return None


# =============================================================================
# PuppetRenderer
# =============================================================================


class PuppetRenderer:
    """
    Renders an answer skeleton through a puppet profile.

    Pipeline:
    1. Mask no-rewrite zones (code blocks)
    2. Apply forbidden phrase removal
    3. Apply verbosity cap (truncate at token limit)
    4. Apply role disclaimer
    5. Restore no-rewrite zones
    6. Run diff guard
    7. On fail: retry with stricter constraints; after max_attempts, fallback
    """

    def __init__(
        self,
        guard: PuppetDiffGuard | None = None,
        max_attempts: int = 2,
    ) -> None:
        self.guard = guard or PuppetDiffGuard()
        self.max_attempts = max(1, max_attempts)

    def render(
        self,
        skeleton: AnswerSkeleton,
        profile: PuppetProfile,
    ) -> PuppetRenderResult:
        """Render a skeleton through the puppet profile."""
        original = skeleton.full_text()

        for attempt in range(1, self.max_attempts + 1):
            # Step 1: mask no-rewrite zones
            masked, zones = mask_no_rewrite_zones(original)

            # Step 2-3: apply voice constraints
            text, removed_count = self._apply_voice(masked, profile)

            # Step 4: apply disclaimer
            text, disclaimer_applied = self._apply_disclaimer(text, profile)

            # Step 5: restore no-rewrite zones
            rendered = restore_zones(text, zones)

            # Step 6: run diff guard
            guard_result = self.guard.check(skeleton, rendered, profile)

            if guard_result.passed:
                verdict = RenderVerdict.PASSED if attempt == 1 else RenderVerdict.RERENDERED
                return PuppetRenderResult(
                    original=original,
                    rendered=rendered,
                    verdict=verdict,
                    guard_result=guard_result,
                    attempts=attempt,
                    disclaimer_applied=disclaimer_applied,
                    forbidden_phrases_removed=removed_count,
                )

        # All attempts failed — fallback to original
        # Apply disclaimer to original as well
        fallback_text, disclaimer_applied = self._apply_disclaimer(original, profile)
        return PuppetRenderResult(
            original=original,
            rendered=fallback_text,
            verdict=RenderVerdict.FALLBACK,
            guard_result=guard_result,
            attempts=self.max_attempts,
            disclaimer_applied=disclaimer_applied,
            forbidden_phrases_removed=0,
        )

    def _apply_voice(
        self,
        text: str,
        profile: PuppetProfile,
    ) -> tuple[str, int]:
        """Apply voice constraints: forbidden phrase removal, verbosity cap."""
        removed = 0

        # Remove forbidden phrases (case-insensitive replacement)
        for phrase in profile.voice.forbidden_phrases:
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            new_text = pattern.sub("", text)
            if new_text != text:
                removed += text.lower().count(phrase.lower())
                text = new_text

        # Clean up double spaces from removals
        text = re.sub(r"  +", " ", text).strip()

        # Verbosity cap (approximate token count as word count)
        cap = profile.voice.verbosity_cap_tokens
        if cap > 0:
            words = text.split()
            if len(words) > cap:
                text = " ".join(words[:cap]) + "..."

        return text, removed

    def _apply_disclaimer(
        self,
        text: str,
        profile: PuppetProfile,
    ) -> tuple[str, bool]:
        """Apply role disclaimer if configured."""
        if profile.disclaimer.enabled and profile.disclaimer.tag_text:
            return profile.disclaimer.apply(text), True
        return text, False


# =============================================================================
# Builtin Profiles
# =============================================================================


def _create_ops_scribe() -> PuppetProfile:
    """Timeline-first, blame-avoidant, Δt-obsessed."""
    return PuppetProfile(
        puppet_id="ops_scribe",
        version="1.0",
        description="Timeline-first, blame-avoidant, Δt-obsessed.",
        voice=VoiceConstraints(
            tone_tags=["dry", "forensic", "terse"],
            register=Register.CLINICAL,
            verbosity_cap_tokens=450,
            forbidden_phrases=["definitely", "obviously", "trust me"],
            required_ticks=["Timeline:", "Δt:"],
        ),
        epistemic=EpistemicPosture(
            hedge_policy=HedgePolicy(
                soft_markers=["likely", "plausibly", "best read is"],
                hard_markers=["is", "does", "has"],
                forbid_overclaim_words=["proves", "guarantees"],
            ),
        ),
        behavioral=BehavioralConstraints(
            interaction_style=AnswerMode.DIAGNOSTIC,
        ),
        disclaimer=RoleDisclaimer(
            enabled=True,
            tag_format=TagPosition.PREFIX,
            tag_text="[puppet: ops-scribe]",
        ),
        safety=SafetyOverrides(
            allow_spice=True,
            forbid_insults=True,
        ),
    )


def _create_procurement_lawyer() -> PuppetProfile:
    """Cautious, source-heavy, hates ambiguity."""
    return PuppetProfile(
        puppet_id="procurement_lawyer",
        version="1.0",
        description="Cautious, source-heavy, hates ambiguity.",
        voice=VoiceConstraints(
            tone_tags=["formal", "skeptical", "precise"],
            register=Register.FORMAL,
            verbosity_cap_tokens=500,
            forbidden_phrases=["sure", "lol", "obviously"],
            required_ticks=["Assumptions:", "Evidence:"],
        ),
        epistemic=EpistemicPosture(
            hedge_policy=HedgePolicy(
                soft_markers=["appears to", "I cannot verify", "on the available record"],
                hard_markers=["is", "does", "has"],
                forbid_overclaim_words=["confirmed", "settled"],
            ),
        ),
        behavioral=BehavioralConstraints(
            interaction_style=AnswerMode.SKEPTICAL,
        ),
        disclaimer=RoleDisclaimer(
            enabled=True,
            tag_format=TagPosition.SUFFIX,
            tag_text="[puppet: procurement-lawyer]",
        ),
        safety=SafetyOverrides(
            allow_spice=False,
            forbid_insults=True,
        ),
    )


def _create_daria_mirror() -> PuppetProfile:
    """Dry, wry, detached. High signal. No pep."""
    return PuppetProfile(
        puppet_id="daria_mirror",
        version="1.0",
        description="Dry, wry, detached. High signal. No pep.",
        voice=VoiceConstraints(
            tone_tags=["dry", "wry", "detached", "skeptical"],
            register=Register.WRY,
            verbosity_cap_tokens=420,
            forbidden_phrases=[
                "great question", "happy to help", "you've got this",
                "let's dive in", "in conclusion", "obviously", "definitely",
            ],
            required_ticks=[],
        ),
        epistemic=EpistemicPosture(
            hedge_policy=HedgePolicy(
                soft_markers=["probably", "likely", "plausibly", "best guess", "I'd bet"],
                hard_markers=["is", "does", "has"],
                forbid_overclaim_words=["proves", "guarantees", "settles", "confirmed"],
            ),
        ),
        behavioral=BehavioralConstraints(
            interaction_style=AnswerMode.DIRECT,
        ),
        disclaimer=RoleDisclaimer(
            enabled=False,
            tag_format=TagPosition.NONE,
            tag_text="",
        ),
        safety=SafetyOverrides(
            allow_spice=True,
            forbid_insults=True,
        ),
    )


_BUILTIN_PROFILES: dict[str, PuppetProfile] = {
    "ops_scribe": _create_ops_scribe(),
    "procurement_lawyer": _create_procurement_lawyer(),
    "daria_mirror": _create_daria_mirror(),
}


# =============================================================================
# PuppetRegistry
# =============================================================================

_CUSTOM_PROFILES_FILE = "puppet_profiles.json"
_ACTIVE_PUPPET_FILE = "puppet_active.json"


class PuppetRegistry:
    """Manages available puppet profiles (builtin + custom)."""

    def __init__(self, governor_dir: Path | None = None) -> None:
        self._builtins: dict[str, PuppetProfile] = dict(_BUILTIN_PROFILES)
        self._custom: dict[str, PuppetProfile] = {}
        self._active: str | None = None
        self._governor_dir = governor_dir

        if governor_dir is not None:
            self._load_custom()
            self._load_active()

    def list_profiles(self) -> list[str]:
        """List all available profile IDs."""
        return sorted(set(list(self._builtins.keys()) + list(self._custom.keys())))

    def get(self, puppet_id: str) -> PuppetProfile | None:
        """Get a profile by ID."""
        if puppet_id in self._builtins:
            return self._builtins[puppet_id]
        return self._custom.get(puppet_id)

    def activate(self, puppet_id: str) -> PuppetProfile:
        """Activate a puppet profile."""
        profile = self.get(puppet_id)
        if profile is None:
            raise ValueError(f"Unknown puppet profile: {puppet_id}")
        self._active = puppet_id
        if self._governor_dir:
            self._save_active()
        return profile

    def deactivate(self) -> None:
        """Deactivate the current puppet."""
        self._active = None
        if self._governor_dir:
            self._save_active()

    def active_profile(self) -> PuppetProfile | None:
        """Get the currently active profile, or None."""
        if self._active is None:
            return None
        return self.get(self._active)

    def is_active(self) -> bool:
        """Check if a puppet is currently active."""
        return self._active is not None

    def create(self, profile: PuppetProfile) -> None:
        """Create a custom profile. Cannot overwrite builtins."""
        if profile.puppet_id in self._builtins:
            raise ValueError(f"Cannot overwrite builtin profile: {profile.puppet_id}")
        self._custom[profile.puppet_id] = profile
        if self._governor_dir:
            self._save_custom()

    def delete(self, puppet_id: str) -> None:
        """Delete a custom profile. Cannot delete builtins."""
        if puppet_id in self._builtins:
            raise ValueError(f"Cannot delete builtin profile: {puppet_id}")
        if puppet_id not in self._custom:
            raise ValueError(f"Unknown custom profile: {puppet_id}")
        del self._custom[puppet_id]
        if self._active == puppet_id:
            self._active = None
        if self._governor_dir:
            self._save_custom()
            self._save_active()

    def _load_custom(self) -> None:
        """Load custom profiles from disk."""
        if self._governor_dir is None:
            return
        path = self._governor_dir / _CUSTOM_PROFILES_FILE
        if path.exists():
            data = json.loads(path.read_text())
            self._custom = {
                pid: PuppetProfile.from_dict(pd) for pid, pd in data.items()
            }

    def _save_custom(self) -> None:
        """Save custom profiles to disk."""
        if self._governor_dir is None:
            return
        path = self._governor_dir / _CUSTOM_PROFILES_FILE
        data = {pid: p.to_dict() for pid, p in self._custom.items()}
        path.write_text(json.dumps(data, indent=2))

    def _load_active(self) -> None:
        """Load active puppet from disk."""
        if self._governor_dir is None:
            return
        path = self._governor_dir / _ACTIVE_PUPPET_FILE
        if path.exists():
            data = json.loads(path.read_text())
            active_id = data.get("active")
            if active_id and self.get(active_id):
                self._active = active_id

    def _save_active(self) -> None:
        """Save active puppet to disk."""
        if self._governor_dir is None:
            return
        path = self._governor_dir / _ACTIVE_PUPPET_FILE
        path.write_text(json.dumps({"active": self._active}, indent=2))

    def to_dict(self) -> dict[str, Any]:
        return {
            "builtins": list(self._builtins.keys()),
            "custom": {pid: p.to_dict() for pid, p in self._custom.items()},
            "active": self._active,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], governor_dir: Path | None = None) -> PuppetRegistry:
        registry = cls(governor_dir=None)  # Don't load from disk
        registry._governor_dir = governor_dir
        for pid, pd in d.get("custom", {}).items():
            registry._custom[pid] = PuppetProfile.from_dict(pd)
        registry._active = d.get("active")
        return registry


# =============================================================================
# Convenience functions
# =============================================================================


def create_puppet_registry(governor_dir: Path | None = None) -> PuppetRegistry:
    """Create a puppet registry, optionally backed by a governor directory."""
    return PuppetRegistry(governor_dir=governor_dir)


def create_puppet_renderer() -> PuppetRenderer:
    """Create a puppet renderer with default settings."""
    return PuppetRenderer()


def create_diff_guard() -> PuppetDiffGuard:
    """Create a puppet diff guard with default settings."""
    return PuppetDiffGuard()


def create_skeleton(
    text: str,
    atoms: list[SkeletonAtom] | None = None,
) -> AnswerSkeleton:
    """Quick helper to create an answer skeleton from plain text."""
    if atoms is not None:
        return AnswerSkeleton(atoms=atoms, raw_text=text)
    return AnswerSkeleton(
        atoms=[SkeletonAtom(text=text)],
        raw_text=text,
    )


def render_with_puppet(text: str, profile: PuppetProfile) -> PuppetRenderResult:
    """One-shot convenience: render text through a puppet profile."""
    skeleton = create_skeleton(text)
    renderer = create_puppet_renderer()
    return renderer.render(skeleton, profile)
