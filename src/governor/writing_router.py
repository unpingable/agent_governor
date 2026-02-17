# SPDX-License-Identifier: Apache-2.0
"""Writing Router — Language Domain Toggle + Explicit Fiction Type Selection.

Sits after intent classification, before regime detection. Routes to
appropriate controller stack based on domain (prose/code) and explicit
fiction type selection.

Key insight: No one wants comedy in their drama (unless it's a dramedy).
Fiction type must be explicit, not auto-detected.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Any


# =============================================================================
# Domain Toggle
# =============================================================================


class LanguageDomain(str, Enum):
    """Top-level domain toggle."""

    PROSE = "prose"
    CODE = "code"


# =============================================================================
# Fiction Type (Explicit Selection)
# =============================================================================


class FictionType(str, Enum):
    """Explicit fiction type — user-selected, never auto-detected.

    No one wants comedy in their drama. Unless it's a dramedy.
    """

    # Pure types
    COMEDY = "comedy"
    TRAGEDY = "tragedy"
    DRAMA = "drama"
    SINCERITY = "sincerity"

    # Hybrid types (explicit combinations)
    DRAMEDY = "dramedy"  # drama + comedy
    TRAGICOMEDY = "tragicomedy"  # tragedy + comedy
    SINCERE_DRAMA = "sincere_drama"  # sincerity + drama

    # Neutral (no affect regime constraint)
    NEUTRAL = "neutral"


# Hybrid decomposition for regime vector initialization
FICTION_TYPE_WEIGHTS: dict[FictionType, dict[str, float]] = {
    FictionType.COMEDY: {"comedy": 1.0, "tragedy": 0.0, "sincerity": 0.0, "drama": 0.0},
    FictionType.TRAGEDY: {"comedy": 0.0, "tragedy": 1.0, "sincerity": 0.0, "drama": 0.0},
    FictionType.DRAMA: {"comedy": 0.0, "tragedy": 0.0, "sincerity": 0.0, "drama": 1.0},
    FictionType.SINCERITY: {"comedy": 0.0, "tragedy": 0.0, "sincerity": 1.0, "drama": 0.0},
    FictionType.DRAMEDY: {"comedy": 0.4, "tragedy": 0.0, "sincerity": 0.0, "drama": 0.6},
    FictionType.TRAGICOMEDY: {"comedy": 0.4, "tragedy": 0.6, "sincerity": 0.0, "drama": 0.0},
    FictionType.SINCERE_DRAMA: {"comedy": 0.0, "tragedy": 0.0, "sincerity": 0.4, "drama": 0.6},
    FictionType.NEUTRAL: {"comedy": 0.25, "tragedy": 0.25, "sincerity": 0.25, "drama": 0.25},
}


def get_regime_weights(fiction_type: FictionType) -> dict[str, float]:
    """Get initial regime vector weights for a fiction type."""
    return FICTION_TYPE_WEIGHTS.get(
        fiction_type,
        FICTION_TYPE_WEIGHTS[FictionType.NEUTRAL],
    )


# =============================================================================
# Prose Mode (Nonfiction vs Fiction)
# =============================================================================


class ProseMode(str, Enum):
    """Prose mode — fiction vs nonfiction."""

    FICTION = "fiction"
    NONFICTION = "nonfiction"


# =============================================================================
# Code Regime (from writing_code.py)
# =============================================================================


class CodeRegime(str, Enum):
    """Code regime — dev vs SRE vs analysis."""

    DEV = "dev"
    SRE = "sre"
    ANALYSIS = "analysis"


# =============================================================================
# Router Configuration
# =============================================================================


@dataclass
class RouterConfig:
    """Configuration for the writing router.

    Neutral is the DEFAULT for fiction. Most language isn't doing heavy
    authorial work - it's connective tissue. Neutral is the idle loop.

    Users must explicitly select comedy/tragedy/drama/sincerity.
    """

    # Domain selection
    domain: LanguageDomain = LanguageDomain.PROSE

    # Prose configuration
    prose_mode: ProseMode = ProseMode.NONFICTION

    # Fiction configuration (only used when prose_mode == FICTION)
    # Neutral is default - user must explicitly choose a regime
    fiction_type: FictionType = FictionType.NEUTRAL

    # Code configuration (only used when domain == CODE)
    code_regime: CodeRegime = CodeRegime.DEV

    # Allow hybrid fiction types
    allow_hybrids: bool = True

    # Lock fiction type (prevent drift)
    lock_fiction_type: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "domain": self.domain.value,
            "prose_mode": self.prose_mode.value,
            "fiction_type": self.fiction_type.value,
            "code_regime": self.code_regime.value,
            "allow_hybrids": self.allow_hybrids,
            "lock_fiction_type": self.lock_fiction_type,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RouterConfig":
        """Deserialize from dict."""
        return cls(
            domain=LanguageDomain(data.get("domain", "prose")),
            prose_mode=ProseMode(data.get("prose_mode", "nonfiction")),
            fiction_type=FictionType(data.get("fiction_type", "neutral")),
            code_regime=CodeRegime(data.get("code_regime", "dev")),
            allow_hybrids=data.get("allow_hybrids", True),
            lock_fiction_type=data.get("lock_fiction_type", False),
        )


# =============================================================================
# Polarity Inversion Table
# =============================================================================


@dataclass
class PolarityProfile:
    """Polarity characteristics for a domain.

    When domain switches, these invert.
    """

    # Governance visibility
    governance_visible: bool

    # Load-bearing variables
    load_bearing_vars: list[str]

    # Silence semantics
    silence_is_restraint: bool  # True for prose, False for code

    # Repetition semantics
    repetition_is_good: bool  # False for prose, True for code

    # Retry strategy
    retry_strategy: str  # "rephrase" for prose, "augment" for code


PROSE_POLARITY = PolarityProfile(
    governance_visible=False,
    load_bearing_vars=["Ep", "Cp", "Rp"],  # epistemic, coupling, risk exposure
    silence_is_restraint=True,
    repetition_is_good=False,
    retry_strategy="rephrase",
)

CODE_POLARITY = PolarityProfile(
    governance_visible=True,
    load_bearing_vars=["Ap", "Ip", "Fp"],  # accountability, invariant, failure
    silence_is_restraint=False,  # omission = ambiguity
    repetition_is_good=True,  # predictability
    retry_strategy="augment",  # structural augmentation
)


def get_polarity(domain: LanguageDomain) -> PolarityProfile:
    """Get polarity profile for domain."""
    if domain == LanguageDomain.CODE:
        return CODE_POLARITY
    return PROSE_POLARITY


# =============================================================================
# Router Input/Output
# =============================================================================


@dataclass
class RouterInput:
    """Input to the writing router."""

    # Raw input text
    text: str

    # Intent classification result (from writing_intent.py)
    intent: str | None = None

    # User-provided configuration
    config: RouterConfig | None = None

    # Context hints
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class RouterOutput:
    """Output from the writing router."""

    # Determined domain
    domain: LanguageDomain

    # Polarity profile
    polarity: PolarityProfile

    # Controller to use
    controller: str  # "regime" | "custody" | "nonfiction"

    # Controller configuration
    controller_config: dict[str, Any]

    # Regime name (for anchor loading)
    regime_name: str

    # Initial weights (for fiction)
    regime_weights: dict[str, float] | None = None


# =============================================================================
# Controller Protocol
# =============================================================================


class WritingController(Protocol):
    """Protocol for writing controllers."""

    def check(self, text: str, context: dict[str, Any] | None = None) -> Any:
        """Check text against controller constraints."""
        ...


# =============================================================================
# Writing Router
# =============================================================================


class WritingRouter:
    """Routes input to appropriate writing controller.

    Sits after intent classification, before regime detection.

    Pipeline:
        Input → Intent Classifier → Language Domain Toggle → [prose|code path]
                                           ↓
                                 prose → Regime/Nonfiction Controller
                                 code  → Custody Controller
    """

    def __init__(self, config: RouterConfig | None = None):
        """Initialize router with configuration."""
        self.config = config or RouterConfig()

    def route(self, input: RouterInput) -> RouterOutput:
        """Route input to appropriate controller.

        Args:
            input: Router input with text, intent, and config

        Returns:
            Router output with domain, polarity, and controller info
        """
        # Use input config if provided, else use instance config
        config = input.config or self.config

        # Get polarity for domain
        polarity = get_polarity(config.domain)

        # Route based on domain
        if config.domain == LanguageDomain.CODE:
            return self._route_code(config, polarity)
        else:
            return self._route_prose(config, polarity)

    def _route_prose(
        self,
        config: RouterConfig,
        polarity: PolarityProfile,
    ) -> RouterOutput:
        """Route to prose controller stack."""
        if config.prose_mode == ProseMode.FICTION:
            return self._route_fiction(config, polarity)
        else:
            return self._route_nonfiction(config, polarity)

    def _route_fiction(
        self,
        config: RouterConfig,
        polarity: PolarityProfile,
    ) -> RouterOutput:
        """Route to fiction controller (regime-based)."""
        # Get initial regime weights from explicit fiction type
        weights = get_regime_weights(config.fiction_type)

        # Determine regime name for anchors
        regime_name = self._fiction_type_to_regime(config.fiction_type)

        return RouterOutput(
            domain=LanguageDomain.PROSE,
            polarity=polarity,
            controller="regime",
            controller_config={
                "fiction_type": config.fiction_type.value,
                "initial_weights": weights,
                "lock_type": config.lock_fiction_type,
                "allow_hybrids": config.allow_hybrids,
            },
            regime_name=regime_name,
            regime_weights=weights,
        )

    def _route_nonfiction(
        self,
        config: RouterConfig,
        polarity: PolarityProfile,
    ) -> RouterOutput:
        """Route to nonfiction controller."""
        return RouterOutput(
            domain=LanguageDomain.PROSE,
            polarity=polarity,
            controller="nonfiction",
            controller_config={
                "claim_levels": True,
                "velocity_control": True,
            },
            regime_name="nonfiction",
            regime_weights=None,
        )

    def _route_code(
        self,
        config: RouterConfig,
        polarity: PolarityProfile,
    ) -> RouterOutput:
        """Route to code controller (custody-based)."""
        return RouterOutput(
            domain=LanguageDomain.CODE,
            polarity=polarity,
            controller="custody",
            controller_config={
                "regime": config.code_regime.value,
                "custody_scoring": True,
            },
            regime_name=f"code_{config.code_regime.value}",
            regime_weights=None,
        )

    def _fiction_type_to_regime(self, fiction_type: FictionType) -> str:
        """Map fiction type to regime name for anchor loading.

        Neutral is its own regime (idle loop) - not mapped to comedy.
        """
        mapping = {
            FictionType.COMEDY: "comedy",
            FictionType.TRAGEDY: "tragedy",
            FictionType.DRAMA: "drama",
            FictionType.SINCERITY: "sincerity",
            FictionType.DRAMEDY: "drama",  # primary component
            FictionType.TRAGICOMEDY: "tragedy",  # primary component
            FictionType.SINCERE_DRAMA: "drama",  # primary component
            FictionType.NEUTRAL: "neutral",  # idle loop, not a regime
        }
        return mapping.get(fiction_type, "neutral")

    def set_domain(self, domain: LanguageDomain) -> None:
        """Set the language domain."""
        self.config.domain = domain

    def set_prose_mode(self, mode: ProseMode) -> None:
        """Set prose mode (fiction/nonfiction)."""
        self.config.prose_mode = mode

    def set_fiction_type(self, fiction_type: FictionType) -> None:
        """Set explicit fiction type.

        This is the key function — fiction type is ALWAYS explicit.
        """
        self.config.fiction_type = fiction_type

    def set_code_regime(self, regime: CodeRegime) -> None:
        """Set code regime (dev/sre/analysis)."""
        self.config.code_regime = regime

    def lock_fiction_type(self, lock: bool = True) -> None:
        """Lock/unlock fiction type to prevent drift."""
        self.config.lock_fiction_type = lock


# =============================================================================
# Convenience Functions
# =============================================================================


def create_prose_router(
    mode: ProseMode = ProseMode.NONFICTION,
    fiction_type: FictionType = FictionType.NEUTRAL,
) -> WritingRouter:
    """Create a router configured for prose."""
    config = RouterConfig(
        domain=LanguageDomain.PROSE,
        prose_mode=mode,
        fiction_type=fiction_type,
    )
    return WritingRouter(config)


def create_fiction_router(
    fiction_type: FictionType = FictionType.COMEDY,
    lock_type: bool = False,
) -> WritingRouter:
    """Create a router configured for fiction with explicit type."""
    config = RouterConfig(
        domain=LanguageDomain.PROSE,
        prose_mode=ProseMode.FICTION,
        fiction_type=fiction_type,
        lock_fiction_type=lock_type,
    )
    return WritingRouter(config)


def create_code_router(
    regime: CodeRegime = CodeRegime.DEV,
) -> WritingRouter:
    """Create a router configured for code."""
    config = RouterConfig(
        domain=LanguageDomain.CODE,
        code_regime=regime,
    )
    return WritingRouter(config)


# =============================================================================
# Fiction Type Helpers
# =============================================================================


def is_hybrid_type(fiction_type: FictionType) -> bool:
    """Check if fiction type is a hybrid."""
    return fiction_type in {
        FictionType.DRAMEDY,
        FictionType.TRAGICOMEDY,
        FictionType.SINCERE_DRAMA,
    }


def get_hybrid_components(fiction_type: FictionType) -> list[FictionType]:
    """Get component types for a hybrid."""
    components = {
        FictionType.DRAMEDY: [FictionType.DRAMA, FictionType.COMEDY],
        FictionType.TRAGICOMEDY: [FictionType.TRAGEDY, FictionType.COMEDY],
        FictionType.SINCERE_DRAMA: [FictionType.SINCERITY, FictionType.DRAMA],
    }
    return components.get(fiction_type, [fiction_type])


def validate_fiction_type_transition(
    current: FictionType,
    target: FictionType,
    allow_hybrids: bool = True,
) -> tuple[bool, str]:
    """Validate a fiction type transition.

    Returns (allowed, reason).
    """
    # Hybrid check
    if not allow_hybrids and is_hybrid_type(target):
        return False, "Hybrid types not allowed in current configuration"

    # Warn on major tonal shifts
    major_shifts = {
        (FictionType.COMEDY, FictionType.TRAGEDY),
        (FictionType.TRAGEDY, FictionType.COMEDY),
    }
    if (current, target) in major_shifts:
        return True, "Warning: Major tonal shift - ensure this is intentional"

    return True, "Transition allowed"


# =============================================================================
# Domain Detection Hints (Optional, User Can Override)
# =============================================================================


def detect_domain_hint(text: str) -> LanguageDomain | None:
    """Detect domain hint from text (optional, user can override).

    This is just a hint — the user's explicit setting always wins.
    """
    code_indicators = [
        "```",
        "def ",
        "class ",
        "import ",
        "function ",
        "const ",
        "let ",
        "var ",
        "return ",
        "if (",
        "for (",
        "while (",
    ]

    text_lower = text.lower()
    code_score = sum(1 for ind in code_indicators if ind.lower() in text_lower)

    if code_score >= 3:
        return LanguageDomain.CODE

    return None  # No strong signal, use user setting
