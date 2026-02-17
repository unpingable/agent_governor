# SPDX-License-Identifier: Apache-2.0
"""
Fiction guardrails: consent tracking, DSI, AII, hard constraints, soft penalties.

Based on ingest/next.md — the fiction-specific safety layer that separates
content governance from content policing.

Hard constraints (veto/block):
  C1: Consent gate — coercive dynamics require explicit opt-in
  C2: Mode escalation — high-risk content requires user enablement
  C3: Anachronism causal — identity terms used causally must be valid for era

Soft penalties (steer/penalize):
  P1: DSI — demographic salience intrusion without narrative cause
  P2: Unearned fact — sensitive facts injected without establishment
  P3: Register drift — style shifting without user signal
  P4: Proxy dominance — population-level rationale in character fiction

Key invariant: the system enforces user-authored intent fidelity, not morality.
"""

from dataclasses import dataclass, field
from enum import Enum
import re


# ============================================================
# Enums
# ============================================================


class ConsentLevel(Enum):
    """Consent state for a character pair within a scope."""

    UNKNOWN = "unknown"
    NO = "no"
    YES = "yes"
    YES_EXPLICIT = "yes_explicit"


class ConsentScope(Enum):
    """Scopes of consent tracked between character pairs."""

    FLIRT = "flirt"
    TOUCH = "touch"
    SEX = "sex"
    KINK_COERCIVE_PLAY = "kink_coercive_play"


# Scope ordering: escalation must go in order
SCOPE_ORDER: dict[ConsentScope, int] = {
    ConsentScope.FLIRT: 0,
    ConsentScope.TOUCH: 1,
    ConsentScope.SEX: 2,
    ConsentScope.KINK_COERCIVE_PLAY: 3,
}


class HardConstraintId(Enum):
    """Identifiers for hard constraint checks."""

    C1_CONSENT_GATE = "C1_consent_gate"
    C2_MODE_ESCALATION = "C2_mode_escalation"
    C3_ANACHRONISM_CAUSAL = "C3_anachronism_causal"


class SoftPenaltyId(Enum):
    """Identifiers for soft penalty checks."""

    P1_DSI = "P1_dsi"
    P2_UNEARNED_FACT = "P2_unearned_fact"
    P3_REGISTER_DRIFT = "P3_register_drift"
    P4_PROXY_DOMINANCE = "P4_proxy_dominance"


# ============================================================
# Dataclasses
# ============================================================


@dataclass
class ConsentPairState:
    """Consent state for a specific character pair."""

    scopes: dict[str, str] = field(default_factory=lambda: {
        s.value: ConsentLevel.UNKNOWN.value for s in ConsentScope
    })
    last_update_token: int = 0
    evidence_spans: list[str] = field(default_factory=list)

    def get_level(self, scope: ConsentScope) -> ConsentLevel:
        raw = self.scopes.get(scope.value, ConsentLevel.UNKNOWN.value)
        return ConsentLevel(raw)

    def set_level(self, scope: ConsentScope, level: ConsentLevel) -> None:
        self.scopes[scope.value] = level.value

    def to_dict(self) -> dict:
        return {
            "scopes": dict(self.scopes),
            "last_update_token": self.last_update_token,
            "evidence_spans": list(self.evidence_spans),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConsentPairState":
        return cls(
            scopes=d.get("scopes", {s.value: ConsentLevel.UNKNOWN.value for s in ConsentScope}),
            last_update_token=d.get("last_update_token", 0),
            evidence_spans=d.get("evidence_spans", []),
        )


@dataclass
class GlobalConsentState:
    """Global consent state (user-level opt-ins)."""

    erotic_allowed: bool = False
    coercive_play_allowed: bool = False
    user_opt_in_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "erotic_allowed": self.erotic_allowed,
            "coercive_play_allowed": self.coercive_play_allowed,
            "user_opt_in_evidence": list(self.user_opt_in_evidence),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GlobalConsentState":
        return cls(
            erotic_allowed=d.get("erotic_allowed", False),
            coercive_play_allowed=d.get("coercive_play_allowed", False),
            user_opt_in_evidence=d.get("user_opt_in_evidence", []),
        )


@dataclass
class ValidityProfile:
    """Temporal validity profile for identity terms.

    Defines which identity terms are valid/invalid for a given era.
    """

    name: str
    valid_terms: list[str] = field(default_factory=list)
    invalid_terms: list[str] = field(default_factory=list)
    era_start: int | None = None
    era_end: int | None = None
    description: str = ""

    def is_term_valid(self, term: str) -> bool:
        """Check if an identity term is valid for this profile's era."""
        term_lower = term.lower()
        for inv in self.invalid_terms:
            if inv.lower() == term_lower:
                return False
        # If in valid list, it's valid
        for val in self.valid_terms:
            if val.lower() == term_lower:
                return True
        # Not in either list — default valid (be permissive)
        return True

    def covers_year(self, year: int) -> bool:
        """Check if this profile covers a given year."""
        if self.era_start is not None and year < self.era_start:
            return False
        if self.era_end is not None and year > self.era_end:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "valid_terms": list(self.valid_terms),
            "invalid_terms": list(self.invalid_terms),
            "era_start": self.era_start,
            "era_end": self.era_end,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValidityProfile":
        return cls(
            name=d["name"],
            valid_terms=d.get("valid_terms", []),
            invalid_terms=d.get("invalid_terms", []),
            era_start=d.get("era_start"),
            era_end=d.get("era_end"),
            description=d.get("description", ""),
        )


@dataclass
class DSISignal:
    """A detected demographic salience intrusion signal."""

    demographic_marker: str
    correlated_bundle: str
    has_local_trigger: bool
    score: float

    def to_dict(self) -> dict:
        return {
            "demographic_marker": self.demographic_marker,
            "correlated_bundle": self.correlated_bundle,
            "has_local_trigger": self.has_local_trigger,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "DSISignal":
        return cls(
            demographic_marker=d["demographic_marker"],
            correlated_bundle=d["correlated_bundle"],
            has_local_trigger=d.get("has_local_trigger", False),
            score=d.get("score", 0.0),
        )


@dataclass
class AIISignal:
    """A detected anachronistic identity injection signal."""

    identity_term: str
    era: str
    used_causally: bool
    valid_for_era: bool

    def to_dict(self) -> dict:
        return {
            "identity_term": self.identity_term,
            "era": self.era,
            "used_causally": self.used_causally,
            "valid_for_era": self.valid_for_era,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "AIISignal":
        return cls(
            identity_term=d["identity_term"],
            era=d["era"],
            used_causally=d.get("used_causally", False),
            valid_for_era=d.get("valid_for_era", True),
        )


@dataclass
class ConstraintViolation:
    """A hard constraint violation — candidate should be dropped."""

    constraint_id: HardConstraintId
    reason: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "constraint_id": self.constraint_id.value,
            "reason": self.reason,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConstraintViolation":
        return cls(
            constraint_id=HardConstraintId(d["constraint_id"]),
            reason=d["reason"],
            detail=d.get("detail", ""),
        )


@dataclass
class PenaltyResult:
    """A soft penalty — steers away but doesn't forbid."""

    penalty_id: SoftPenaltyId
    score: float
    detail: str

    def to_dict(self) -> dict:
        return {
            "penalty_id": self.penalty_id.value,
            "score": self.score,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PenaltyResult":
        return cls(
            penalty_id=SoftPenaltyId(d["penalty_id"]),
            score=d.get("score", 0.0),
            detail=d.get("detail", ""),
        )


@dataclass
class GuardrailConfig:
    """Configuration for fiction guardrails."""

    # Hard constraint toggles
    block_coercive_without_opt_in: bool = True
    block_high_risk_without_enable: bool = True
    block_anachronistic_causal: bool = True

    # Soft penalty weights (lambdas)
    lambda_dsi: float = 2.0
    lambda_unearned: float = 1.5
    lambda_drift: float = 1.0
    lambda_proxy: float = 1.0

    def to_dict(self) -> dict:
        return {
            "block_coercive_without_opt_in": self.block_coercive_without_opt_in,
            "block_high_risk_without_enable": self.block_high_risk_without_enable,
            "block_anachronistic_causal": self.block_anachronistic_causal,
            "lambda_dsi": self.lambda_dsi,
            "lambda_unearned": self.lambda_unearned,
            "lambda_drift": self.lambda_drift,
            "lambda_proxy": self.lambda_proxy,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GuardrailConfig":
        return cls(
            block_coercive_without_opt_in=d.get("block_coercive_without_opt_in", True),
            block_high_risk_without_enable=d.get("block_high_risk_without_enable", True),
            block_anachronistic_causal=d.get("block_anachronistic_causal", True),
            lambda_dsi=d.get("lambda_dsi", 2.0),
            lambda_unearned=d.get("lambda_unearned", 1.5),
            lambda_drift=d.get("lambda_drift", 1.0),
            lambda_proxy=d.get("lambda_proxy", 1.0),
        )


@dataclass
class StateContext:
    """Context for guardrail evaluation.

    Packages the relevant state for constraint/penalty checks.
    """

    # World state
    world_year: int | None = None
    era_tags: list[str] = field(default_factory=list)

    # Mode state
    current_register: str = "literary"
    current_risk_tier: str = "low"
    user_signaled_mode: bool = False

    # Character KB (name -> list of established facts)
    character_facts: dict[str, list[str]] = field(default_factory=dict)

    # Global consent
    erotic_allowed: bool = False
    coercive_play_allowed: bool = False

    # Drift score (from ContextDriftDetector, if available)
    drift_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "world_year": self.world_year,
            "era_tags": list(self.era_tags),
            "current_register": self.current_register,
            "current_risk_tier": self.current_risk_tier,
            "user_signaled_mode": self.user_signaled_mode,
            "character_facts": {k: list(v) for k, v in self.character_facts.items()},
            "erotic_allowed": self.erotic_allowed,
            "coercive_play_allowed": self.coercive_play_allowed,
            "drift_score": self.drift_score,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StateContext":
        return cls(
            world_year=d.get("world_year"),
            era_tags=d.get("era_tags", []),
            current_register=d.get("current_register", "literary"),
            current_risk_tier=d.get("current_risk_tier", "low"),
            user_signaled_mode=d.get("user_signaled_mode", False),
            character_facts=d.get("character_facts", {}),
            erotic_allowed=d.get("erotic_allowed", False),
            coercive_play_allowed=d.get("coercive_play_allowed", False),
            drift_score=d.get("drift_score", 0.0),
        )


@dataclass
class GuardrailResult:
    """Result of running all guardrail checks on a text."""

    violations: list[ConstraintViolation] = field(default_factory=list)
    penalties: list[PenaltyResult] = field(default_factory=list)
    total_penalty: float = 0.0
    passed: bool = True

    def to_dict(self) -> dict:
        return {
            "violations": [v.to_dict() for v in self.violations],
            "penalties": [p.to_dict() for p in self.penalties],
            "total_penalty": self.total_penalty,
            "passed": self.passed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GuardrailResult":
        return cls(
            violations=[ConstraintViolation.from_dict(v) for v in d.get("violations", [])],
            penalties=[PenaltyResult.from_dict(p) for p in d.get("penalties", [])],
            total_penalty=d.get("total_penalty", 0.0),
            passed=d.get("passed", True),
        )


# ============================================================
# Detection patterns
# ============================================================

# Sexual content markers
SEXUAL_CONTENT_PATTERNS: list[str] = [
    r"\b(kiss(ed|ing)?|caress(ed|ing)?|undress(ed|ing)?)\b",
    r"\b(moan(ed|ing)?|groan(ed|ing)?|gasp(ed|ing)?)\b",
    r"\b(naked|nude|arousal|orgasm|climax)\b",
    r"\b(thrust(ed|ing)?|straddl(ed|ing)?|strok(ed|ing)?)\b",
    r"\b(breast|nipple|groin|thigh|buttock)\b",
    r"\b(erect(ion)?|pant(ed|ing)|writhe[ds]?)\b",
]

# Coercion / non-consent markers
COERCION_PATTERNS: list[str] = [
    r"\b(forced?\s+(her|him|them)\s+to)\b",
    r"\b(pin(ned|ning)\s+(her|him|them)\s+down)\b",
    r"\b(couldn'?t\s+(escape|resist|stop|pull away))\b",
    r"\b(despite\s+(her|his|their)\s+(protest|refusal|plea))\b",
    r"\b(no[,!]?\s+(stop|please|don'?t))\b",
    r"\b(against\s+(her|his|their)\s+will)\b",
    r"\b(struggle[ds]?\s+(against|beneath|under))\b",
    r"\b(helpless(ly)?|powerless(ly)?|unable\s+to\s+resist)\b",
    r"\b(submitt?(ed|ing)\s+(reluctant|unwilling))\b",
]

# Demographic markers (race, ethnicity, nationality as identity)
DEMOGRAPHIC_MARKERS: dict[str, list[str]] = {
    "race_black": [
        r"\b(Black|African[- ]American|Afro[- ])\b",
    ],
    "race_asian": [
        r"\b(Asian|Chinese|Japanese|Korean|Vietnamese|Indian)\b",
    ],
    "race_hispanic": [
        r"\b(Hispanic|Latino|Latina|Latinx|Mexican|Puerto Rican)\b",
    ],
    "race_indigenous": [
        r"\b(Indigenous|Native American|Aboriginal|First Nations)\b",
    ],
    "nationality_italian": [
        r"\b(Italian|Sicilian|Neapolitan)\b",
    ],
    "nationality_irish": [
        r"\b(Irish)\b",
    ],
    "nationality_jewish": [
        r"\b(Jewish|Jew)\b",
    ],
}

# Correlated bundles: topics that corpus associates with demographic groups
# but which shouldn't appear without narrative cause
CORRELATED_BUNDLES: dict[str, list[str]] = {
    "race_black": [
        r"\b(civil rights|slavery|plantation|segregat|Jim Crow)\b",
        r"\b(high blood pressure|hypertension|sickle cell|diabetes)\b",
        r"\b(incarcerat|prison|police brutal|systemic racism)\b",
        r"\b(welfare|food stamps|poverty|project[s]?|hood)\b",
        r"\b(single (mother|parent|mom)|absent father)\b",
    ],
    "race_asian": [
        r"\b(tiger (parent|mom|mother)|strict parent)\b",
        r"\b(math|engineer|doctor|violin|piano|straight A)\b",
        r"\b(martial art|kung fu|karate|samurai|ninja)\b",
        r"\b(honor|shame|filial piety|ancestor)\b",
        r"\b(exotic|oriental|mysterious east)\b",
    ],
    "race_hispanic": [
        r"\b(illegal|undocumented|border|cartel|gang)\b",
        r"\b(spicy|fiery|passionate|hot-tempered|caliente)\b",
        r"\b(large family|catholic|quinceañera)\b",
    ],
    "race_indigenous": [
        r"\b(spiritual|mystic|wise elder|shaman|vision quest)\b",
        r"\b(noble savage|connected to (nature|earth|land))\b",
        r"\b(reservation|alcoholism|casino)\b",
    ],
    "nationality_italian": [
        r"\b(mafia|mob|godfather|cosa nostra)\b",
        r"\b(mama|nonna|family honor|vendetta)\b",
        r"\b(pasta|wine|olive oil|gesticul)\b",
        r"\b(loud|emotional|passionate|hot-tempered)\b",
    ],
    "nationality_irish": [
        r"\b(drunk|alcoholi|pub|whiskey|temper)\b",
        r"\b(fighting|brawl|stubborn|red-haired)\b",
        r"\b(potato famine|IRA|troubles)\b",
    ],
    "nationality_jewish": [
        r"\b(money|banker|cheap|frugal|wealthy)\b",
        r"\b(guilt|neurotic|overbearing mother)\b",
        r"\b(Holocaust|persecution)\b",
    ],
}

# Causal identity patterns (e.g., "because he's Italian")
CAUSAL_IDENTITY_PATTERNS: list[str] = [
    r"\bbecause\s+(?:he|she|they)\s+(?:is|was|were|are)\s+(\w+)\b",
    r"\bbecause\s+(?:he|she|they)'(?:s|re)\s+(\w+)\b",
    r"\bas\s+(?:a|an)\s+(\w+)(?:\s+\w+)?\s*,\s*(?:he|she|they)\b",
    r"\bbeing\s+(\w+)\s*,\s*(?:he|she|they)\b",
    r"\b(?:his|her|their)\s+(\w+)\s+(?:heritage|blood|roots|background)\s+(?:made|drove|caused|compelled)\b",
    r"\bit\s+was\s+(?:the|his|her|their)\s+(\w+)\s+in\s+(?:him|her|them)\b",
]

# Population-level rationale patterns
PROXY_DOMINANCE_PATTERNS: list[str] = [
    r"\b(statistically|studies show|research indicates|data suggests)\b",
    r"\b(people like (him|her|them)|his (kind|people|community))\b",
    r"\b(it'?s (common|typical|known) (for|among|in) \w+ (people|community|population))\b",
    r"\b(culturally|traditionally|historically),?\s+(they|he|she)\b",
    r"\b(as (is|was) (typical|common|expected) (of|for|among))\b",
]


# ============================================================
# Builtin validity profiles
# ============================================================

BUILTIN_PROFILES: dict[str, ValidityProfile] = {
    "medieval_europe": ValidityProfile(
        name="medieval_europe",
        valid_terms=[
            "Frankish", "Lombard", "Saxon", "Norman", "Moorish",
            "Tuscan", "Venetian", "Florentine", "Castilian", "Aragonese",
            "Burgundian", "Flemish", "Breton", "Gascon", "Angevin",
            "Christian", "Muslim", "Jewish", "Cathar", "Waldensian",
        ],
        invalid_terms=[
            "Italian", "German", "French", "Spanish", "British",
            "European", "American", "nationality",
        ],
        era_start=500,
        era_end=1500,
        description="Medieval Europe: national identities do not exist. Use regional, dynastic, or religious identity.",
    ),
    "renaissance_europe": ValidityProfile(
        name="renaissance_europe",
        valid_terms=[
            "Venetian", "Florentine", "Roman", "Milanese", "Genoese",
            "Castilian", "Aragonese", "English", "Scottish", "Welsh",
            "Portuguese", "Burgundian", "Ottoman", "Habsburg",
        ],
        invalid_terms=[
            "Italian", "German", "Spanish",
        ],
        era_start=1400,
        era_end=1700,
        description="Renaissance Europe: city-states and dynasties, not nation-states.",
    ),
    "ancient_world": ValidityProfile(
        name="ancient_world",
        valid_terms=[
            "Roman", "Greek", "Athenian", "Spartan", "Egyptian", "Persian",
            "Carthaginian", "Gaul", "Celtic", "Germanic", "Phoenician",
            "Hebrew", "Babylonian", "Assyrian", "Scythian",
        ],
        invalid_terms=[
            "Italian", "Greek" if False else "",  # "Greek" is actually valid here
            "French", "English", "German", "Spanish", "Turkish",
            "Iraqi", "Iranian", "Israeli", "Lebanese", "Syrian",
        ],
        era_start=-3000,
        era_end=500,
        description="Ancient world: ethnic and civic identities, no modern national identities.",
    ),
    "colonial_era": ValidityProfile(
        name="colonial_era",
        valid_terms=[
            "English", "French", "Spanish", "Portuguese", "Dutch",
            "Ottoman", "Chinese", "Japanese", "Mughal",
            "Inca", "Aztec", "Maya",
        ],
        invalid_terms=[
            "American",  # before ~1776
            "Canadian",  # before 1867
            "Australian",  # before 1901
        ],
        era_start=1492,
        era_end=1800,
        description="Colonial era: emerging national identities, still largely imperial/colonial.",
    ),
}
# Filter empty strings from ancient_world
BUILTIN_PROFILES["ancient_world"].invalid_terms = [
    t for t in BUILTIN_PROFILES["ancient_world"].invalid_terms if t
]


# ============================================================
# ConsentLedger
# ============================================================


class ConsentLedger:
    """Tracks consent state between character pairs.

    Consent is:
    - Scene-local and pairwise
    - Monotone-with-retractions (can escalate or withdraw)
    - Scope-specific (flirt/touch/sex/kink)
    """

    def __init__(self) -> None:
        self._pairwise: dict[str, ConsentPairState] = {}
        self._global = GlobalConsentState()

    @property
    def global_state(self) -> GlobalConsentState:
        return self._global

    def _pair_key(self, char_a: str, char_b: str) -> str:
        """Canonical key for a character pair (alphabetical order)."""
        return "|".join(sorted([char_a.lower(), char_b.lower()]))

    def update_consent(
        self,
        char_a: str,
        char_b: str,
        scope: ConsentScope,
        level: ConsentLevel,
        token: int = 0,
        evidence: str = "",
    ) -> ConsentPairState:
        """Update consent state for a character pair in a given scope."""
        key = self._pair_key(char_a, char_b)
        if key not in self._pairwise:
            self._pairwise[key] = ConsentPairState()

        pair = self._pairwise[key]
        pair.set_level(scope, level)
        pair.last_update_token = token
        if evidence:
            pair.evidence_spans.append(evidence)
        return pair

    def get_consent(self, char_a: str, char_b: str, scope: ConsentScope) -> ConsentLevel:
        """Get current consent level for a pair in a scope."""
        key = self._pair_key(char_a, char_b)
        pair = self._pairwise.get(key)
        if pair is None:
            return ConsentLevel.UNKNOWN
        return pair.get_level(scope)

    def get_pair_state(self, char_a: str, char_b: str) -> ConsentPairState | None:
        """Get full consent state for a character pair."""
        key = self._pair_key(char_a, char_b)
        return self._pairwise.get(key)

    def check_escalation(
        self,
        char_a: str,
        char_b: str,
        proposed_scope: ConsentScope,
    ) -> ConstraintViolation | None:
        """Check if proposed scope requires consent not yet established.

        Returns a violation if escalation is unsafe.
        """
        current = self.get_consent(char_a, char_b, proposed_scope)

        # If consent is explicit or yes, OK
        if current in (ConsentLevel.YES, ConsentLevel.YES_EXPLICIT):
            return None

        # If consent is NO, block
        if current == ConsentLevel.NO:
            return ConstraintViolation(
                constraint_id=HardConstraintId.C1_CONSENT_GATE,
                reason="consent_explicitly_denied",
                detail=f"Consent for {proposed_scope.value} between {char_a} and {char_b} was explicitly denied",
            )

        # UNKNOWN — check if scope requires explicit consent
        if proposed_scope in (ConsentScope.SEX, ConsentScope.KINK_COERCIVE_PLAY):
            return ConstraintViolation(
                constraint_id=HardConstraintId.C1_CONSENT_GATE,
                reason="high_scope_without_consent",
                detail=(
                    f"Scope {proposed_scope.value} between {char_a} and {char_b} "
                    f"requires explicit consent (current: {current.value})"
                ),
            )

        # Lower scopes with UNKNOWN are OK (permitted without explicit consent)
        return None

    def set_global(
        self,
        erotic_allowed: bool | None = None,
        coercive_play_allowed: bool | None = None,
        evidence: str = "",
    ) -> GlobalConsentState:
        """Set global consent state (user-level opt-ins)."""
        if erotic_allowed is not None:
            self._global.erotic_allowed = erotic_allowed
        if coercive_play_allowed is not None:
            self._global.coercive_play_allowed = coercive_play_allowed
        if evidence:
            self._global.user_opt_in_evidence.append(evidence)
        return self._global

    def to_dict(self) -> dict:
        return {
            "pairwise": {k: v.to_dict() for k, v in self._pairwise.items()},
            "global": self._global.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ConsentLedger":
        ledger = cls()
        for k, v in d.get("pairwise", {}).items():
            ledger._pairwise[k] = ConsentPairState.from_dict(v)
        ledger._global = GlobalConsentState.from_dict(d.get("global", {}))
        return ledger


# ============================================================
# DSIDetector
# ============================================================


class DSIDetector:
    """Detects Demographic Salience Intrusion.

    Flags when demographic-correlated traits, topics, or motivations
    appear without narrative causality or user request.
    """

    def __init__(self, custom_bundles: dict[str, list[str]] | None = None) -> None:
        self._markers = dict(DEMOGRAPHIC_MARKERS)
        self._bundles = dict(CORRELATED_BUNDLES)
        if custom_bundles:
            for key, patterns in custom_bundles.items():
                self._bundles.setdefault(key, []).extend(patterns)

    def detect(
        self,
        text: str,
        character_facts: dict[str, list[str]] | None = None,
    ) -> list[DSISignal]:
        """Detect demographic salience intrusions in text.

        character_facts: dict mapping character names to established facts.
        If a correlated topic is already established in character facts,
        it's not an intrusion.
        """
        signals: list[DSISignal] = []
        all_facts = []
        if character_facts:
            for facts in character_facts.values():
                all_facts.extend(f.lower() for f in facts)
        facts_text = " ".join(all_facts)

        for category, marker_patterns in self._markers.items():
            # Check if demographic marker is present
            marker_found = False
            for pattern in marker_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    marker_found = True
                    break

            if not marker_found:
                continue

            # Check if correlated bundles are triggered
            bundle_patterns = self._bundles.get(category, [])
            for bp in bundle_patterns:
                match = re.search(bp, text, re.IGNORECASE)
                if match:
                    bundle_text = match.group(0)
                    # Check for local trigger in character facts
                    has_trigger = bool(
                        re.search(bp, facts_text, re.IGNORECASE)
                    ) if facts_text else False

                    signals.append(DSISignal(
                        demographic_marker=category,
                        correlated_bundle=bundle_text,
                        has_local_trigger=has_trigger,
                        score=0.0 if has_trigger else 1.0,
                    ))

        return signals


# ============================================================
# AIIDetector
# ============================================================


class AIIDetector:
    """Detects Anachronistic Identity Injection.

    Flags when modern identity terms are used causally in historical
    contexts where they are undefined or incoherent.
    """

    def __init__(self, profiles: list[ValidityProfile] | None = None) -> None:
        self._custom: list[ValidityProfile] = list(profiles) if profiles else []
        self._builtins: dict[str, ValidityProfile] = dict(BUILTIN_PROFILES)

    @property
    def _all_profiles(self) -> list[ValidityProfile]:
        """All profiles, custom first (custom takes priority)."""
        return self._custom + list(self._builtins.values())

    def _find_profile(
        self, world_year: int | None, era_tags: list[str] | None
    ) -> ValidityProfile | None:
        """Find the best matching validity profile. Custom profiles take priority."""
        if world_year is not None:
            for profile in self._all_profiles:
                if profile.covers_year(world_year):
                    return profile

        if era_tags:
            for tag in era_tags:
                tag_lower = tag.lower().replace(" ", "_")
                for profile in self._all_profiles:
                    if tag_lower in profile.name.lower() or profile.name.lower() in tag_lower:
                        return profile

        return None

    def _extract_causal_terms(self, text: str) -> list[tuple[str, str]]:
        """Extract identity terms used causally.

        Returns list of (term, full_match) tuples.
        """
        results = []
        for pattern in CAUSAL_IDENTITY_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                term = match.group(1) if match.lastindex else match.group(0)
                results.append((term, match.group(0)))
        return results

    def detect(
        self,
        text: str,
        world_year: int | None = None,
        era_tags: list[str] | None = None,
    ) -> list[AIISignal]:
        """Detect anachronistic identity injections."""
        profile = self._find_profile(world_year, era_tags)
        if profile is None:
            return []  # No profile means no temporal constraints

        signals: list[AIISignal] = []
        causal_terms = self._extract_causal_terms(text)

        for term, _full_match in causal_terms:
            valid = profile.is_term_valid(term)
            signals.append(AIISignal(
                identity_term=term,
                era=profile.name,
                used_causally=True,
                valid_for_era=valid,
            ))

        return signals


# ============================================================
# Utility detection functions
# ============================================================


def detect_sexual_content(text: str) -> bool:
    """Check if text contains sexual content markers."""
    for pattern in SEXUAL_CONTENT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def detect_coercion(text: str) -> bool:
    """Check if text contains coercion / non-consent markers."""
    for pattern in COERCION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def detect_proxy_dominance(text: str) -> list[str]:
    """Detect population-level rationale patterns in text."""
    matches = []
    for pattern in PROXY_DOMINANCE_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            matches.append(m.group(0))
    return matches


def detect_unearned_facts(
    text: str,
    character_facts: dict[str, list[str]] | None = None,
) -> list[str]:
    """Detect sensitive facts (medical, trauma) not established in character KB.

    Returns list of detected unearned fact strings.
    """
    # Sensitive fact patterns
    sensitive_patterns = [
        r"\b(high blood pressure|hypertension|diabetes|cancer|heart disease)\b",
        r"\b(depression|anxiety|PTSD|bipolar|schizophren)\b",
        r"\b(abuse[ds]?|trauma|molest|assault|rape)\b",
        r"\b(addiction|alcoholism|alcoholic|drug use|overdose)\b",
        r"\b(poverty|homeless|welfare|food stamps)\b",
        r"\b(prison|incarcer|arrest|conviction|parole)\b",
    ]

    all_facts_text = ""
    if character_facts:
        for facts in character_facts.values():
            all_facts_text += " ".join(f.lower() for f in facts) + " "

    unearned = []
    for pattern in sensitive_patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            fact_text = match.group(0).lower()
            # Check if established in character facts
            if all_facts_text and fact_text in all_facts_text:
                continue
            unearned.append(match.group(0))

    return unearned


# ============================================================
# FictionGuardrails
# ============================================================


class FictionGuardrails:
    """Combined hard constraints and soft penalties for fiction.

    Hard constraints block candidates. Soft penalties steer via scoring.
    """

    def __init__(
        self,
        config: GuardrailConfig | None = None,
        consent_ledger: ConsentLedger | None = None,
        dsi_detector: DSIDetector | None = None,
        aii_detector: AIIDetector | None = None,
    ) -> None:
        self.config = config or GuardrailConfig()
        self.consent = consent_ledger or ConsentLedger()
        self.dsi = dsi_detector or DSIDetector()
        self.aii = aii_detector or AIIDetector()

    # --- Hard constraints ---

    def _c1_consent_gate(
        self, text: str, ctx: StateContext
    ) -> ConstraintViolation | None:
        """C1: Block coercive dynamics without explicit opt-in."""
        if not self.config.block_coercive_without_opt_in:
            return None

        if not detect_sexual_content(text):
            return None

        if detect_coercion(text):
            if not ctx.coercive_play_allowed and not self.consent.global_state.coercive_play_allowed:
                return ConstraintViolation(
                    constraint_id=HardConstraintId.C1_CONSENT_GATE,
                    reason="coercive_play_not_opted_in",
                    detail="Coercive sexual dynamics detected without user opt-in",
                )

        return None

    def _c2_mode_escalation(
        self, text: str, ctx: StateContext
    ) -> ConstraintViolation | None:
        """C2: Block high-risk mode escalation without user enablement."""
        if not self.config.block_high_risk_without_enable:
            return None

        if ctx.user_signaled_mode:
            return None

        # Check if text contains high-risk content while current mode is low/medium
        if ctx.current_risk_tier in ("low", "medium"):
            has_erotic = detect_sexual_content(text) and any(
                re.search(p, text, re.IGNORECASE)
                for p in [
                    r"\b(arousal|orgasm|climax|erect(ion)?)\b",
                    r"\b(thrust(ed|ing)?|writhe[ds]?)\b",
                ]
            )
            if has_erotic and not ctx.erotic_allowed and not self.consent.global_state.erotic_allowed:
                return ConstraintViolation(
                    constraint_id=HardConstraintId.C2_MODE_ESCALATION,
                    reason="high_risk_mode_not_enabled",
                    detail=(
                        f"Explicit erotic content detected in {ctx.current_risk_tier} risk mode "
                        f"without user enablement"
                    ),
                )

        return None

    def _c3_anachronism_causal(
        self, text: str, ctx: StateContext
    ) -> ConstraintViolation | None:
        """C3: Block anachronistic identity terms used causally."""
        if not self.config.block_anachronistic_causal:
            return None

        signals = self.aii.detect(text, ctx.world_year, ctx.era_tags)
        for signal in signals:
            if signal.used_causally and not signal.valid_for_era:
                return ConstraintViolation(
                    constraint_id=HardConstraintId.C3_ANACHRONISM_CAUSAL,
                    reason="anachronistic_identity_causal",
                    detail=(
                        f"Identity term '{signal.identity_term}' used causally "
                        f"but invalid for era '{signal.era}'"
                    ),
                )
        return None

    # --- Soft penalties ---

    def _p1_dsi(self, text: str, ctx: StateContext) -> PenaltyResult:
        """P1: Demographic Salience Intrusion penalty."""
        signals = self.dsi.detect(text, ctx.character_facts)
        intrusions = [s for s in signals if not s.has_local_trigger]

        if not intrusions:
            return PenaltyResult(
                penalty_id=SoftPenaltyId.P1_DSI,
                score=0.0,
                detail="no intrusions detected",
            )

        score = sum(s.score for s in intrusions)
        markers = [s.demographic_marker for s in intrusions]
        bundles = [s.correlated_bundle for s in intrusions]

        return PenaltyResult(
            penalty_id=SoftPenaltyId.P1_DSI,
            score=score,
            detail=f"DSI: markers={markers}, bundles={bundles}",
        )

    def _p2_unearned_fact(self, text: str, ctx: StateContext) -> PenaltyResult:
        """P2: Unearned sensitive fact injection penalty."""
        unearned = detect_unearned_facts(text, ctx.character_facts)

        if not unearned:
            return PenaltyResult(
                penalty_id=SoftPenaltyId.P2_UNEARNED_FACT,
                score=0.0,
                detail="no unearned facts detected",
            )

        return PenaltyResult(
            penalty_id=SoftPenaltyId.P2_UNEARNED_FACT,
            score=float(len(unearned)),
            detail=f"unearned facts: {unearned}",
        )

    def _p3_register_drift(self, text: str, ctx: StateContext) -> PenaltyResult:
        """P3: Register drift penalty (uses pre-computed drift_score)."""
        if ctx.user_signaled_mode:
            return PenaltyResult(
                penalty_id=SoftPenaltyId.P3_REGISTER_DRIFT,
                score=0.0,
                detail="user signaled mode change",
            )

        score = ctx.drift_score

        return PenaltyResult(
            penalty_id=SoftPenaltyId.P3_REGISTER_DRIFT,
            score=score,
            detail=f"drift_score={score:.3f}" if score > 0 else "no drift",
        )

    def _p4_proxy_dominance(self, text: str, ctx: StateContext) -> PenaltyResult:
        """P4: Population-level rationale penalty."""
        matches = detect_proxy_dominance(text)

        if not matches:
            return PenaltyResult(
                penalty_id=SoftPenaltyId.P4_PROXY_DOMINANCE,
                score=0.0,
                detail="no proxy dominance detected",
            )

        return PenaltyResult(
            penalty_id=SoftPenaltyId.P4_PROXY_DOMINANCE,
            score=float(len(matches)),
            detail=f"proxy patterns: {matches}",
        )

    # --- Combined checks ---

    def check_hard(
        self, text: str, ctx: StateContext
    ) -> list[ConstraintViolation]:
        """Run all hard constraint checks. Returns list of violations."""
        violations = []
        for check in [self._c1_consent_gate, self._c2_mode_escalation, self._c3_anachronism_causal]:
            v = check(text, ctx)
            if v is not None:
                violations.append(v)
        return violations

    def check_soft(
        self, text: str, ctx: StateContext
    ) -> list[PenaltyResult]:
        """Run all soft penalty checks. Returns list of penalty results."""
        return [
            self._p1_dsi(text, ctx),
            self._p2_unearned_fact(text, ctx),
            self._p3_register_drift(text, ctx),
            self._p4_proxy_dominance(text, ctx),
        ]

    def check(
        self, text: str, ctx: StateContext
    ) -> GuardrailResult:
        """Run all checks and return combined result."""
        violations = self.check_hard(text, ctx)
        penalties = self.check_soft(text, ctx)

        total = sum(
            p.score * getattr(self.config, f"lambda_{p.penalty_id.value.split('_', 1)[1]}", 1.0)
            for p in penalties
        )

        return GuardrailResult(
            violations=violations,
            penalties=penalties,
            total_penalty=total,
            passed=len(violations) == 0,
        )

    def to_dict(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "consent": self.consent.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FictionGuardrails":
        config = GuardrailConfig.from_dict(d.get("config", {}))
        consent = ConsentLedger.from_dict(d.get("consent", {}))
        return cls(config=config, consent_ledger=consent)


# ============================================================
# Convenience functions
# ============================================================


def create_consent_ledger() -> ConsentLedger:
    """Create a new consent ledger."""
    return ConsentLedger()


def create_fiction_guardrails(
    config: GuardrailConfig | None = None,
) -> FictionGuardrails:
    """Create a fiction guardrails instance."""
    return FictionGuardrails(config=config)


def create_guardrail_config(**kwargs) -> GuardrailConfig:
    """Create a guardrail config with custom settings."""
    return GuardrailConfig(**kwargs)


def create_validity_profile(
    name: str,
    valid_terms: list[str] | None = None,
    invalid_terms: list[str] | None = None,
    era_start: int | None = None,
    era_end: int | None = None,
    description: str = "",
) -> ValidityProfile:
    """Create a custom validity profile for identity terms."""
    return ValidityProfile(
        name=name,
        valid_terms=valid_terms or [],
        invalid_terms=invalid_terms or [],
        era_start=era_start,
        era_end=era_end,
        description=description,
    )


def get_builtin_profiles() -> dict[str, ValidityProfile]:
    """Get all builtin validity profiles."""
    return dict(BUILTIN_PROFILES)
