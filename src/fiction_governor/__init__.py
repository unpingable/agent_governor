"""
Fiction Governor: Constraint system for LLM-assisted fiction writing.

Keeps characters in-character, stories consistent, and tropes at bay.

Three layers of constraint:
- Bible: Who characters ARE (static traits, voice, anti-patterns)
- Canon: What HAPPENED (events, relationships)
- State: WHY they act and WHAT they believe (motivations, beliefs, constraints)
"""

from .types import (
    # Character basics
    Character,
    CharacterTrait,
    CharacterVoice,
    # World and style
    WorldRule,
    BannedTrope,
    ToneSettings,
    # Canon
    CanonEvent,
    Relationship,
    # Claims
    FictionClaimType,
    FictionClaim,
    # Narrative constraints
    MotivationType,
    Motivation,
    Belief,
    BehavioralConstraint,
    NarrativeWarning,
    # Plot threads
    ThreadType,
    ThreadStatus,
    PlotThread,
    SceneProposal,
)
from .bible import Bible
from .canon import Canon
from .state import CharacterState
from .verifiers import (
    InCharacterVerifier,
    TropeVerifier,
    CanonVerifier,
    ToneVerifier,
    FictionVerifier,
    NarrativeVerifier,
    VerificationResult,
)
from .manuscript import (
    ManuscriptScanner,
    ScanResult,
    ExtractedCharacter,
    ExtractedLocation,
    ExtractedEvent,
    ExtractedThread,
    scan_manuscript_to_canon,
    scan_single_chapter,
)
from .similarity import (
    SimilarityMatch,
    VoiceAnalysis,
    ToneAnalysis,
    EmbeddingProvider,
    TFIDFProvider,
    SimilarityAnalyzer,
    create_analyzer,
    quick_trope_check,
    quick_voice_check,
    compute_text_similarity,
)
from .context_drift import (
    NarrativeMode,
    RiskTier,
    DriftFaultType,
    HysteresisConfig,
    ModeSignal,
    ModeTransition,
    DriftFault,
    DriftState,
    ContextDriftDetector,
    classify_register,
    estimate_risk_tier,
    create_context_drift_detector,
)
from .guardrails import (
    ConsentLevel,
    ConsentScope,
    HardConstraintId,
    SoftPenaltyId,
    ConsentPairState,
    GlobalConsentState,
    ValidityProfile,
    DSISignal,
    AIISignal,
    ConstraintViolation,
    PenaltyResult,
    GuardrailConfig,
    StateContext,
    GuardrailResult,
    ConsentLedger,
    DSIDetector,
    AIIDetector,
    FictionGuardrails,
    detect_sexual_content,
    detect_coercion,
    detect_proxy_dominance,
    detect_unearned_facts,
    create_consent_ledger,
    create_fiction_guardrails,
    create_guardrail_config,
    create_validity_profile,
    get_builtin_profiles,
)

__all__ = [
    # Types - Character basics
    "Character",
    "CharacterTrait",
    "CharacterVoice",
    # Types - World and style
    "WorldRule",
    "BannedTrope",
    "ToneSettings",
    # Types - Canon
    "CanonEvent",
    "Relationship",
    # Types - Claims
    "FictionClaimType",
    "FictionClaim",
    # Types - Narrative constraints (the new layer)
    "MotivationType",
    "Motivation",
    "Belief",
    "BehavioralConstraint",
    "NarrativeWarning",
    # Types - Plot threads
    "ThreadType",
    "ThreadStatus",
    "PlotThread",
    "SceneProposal",
    # Ledgers
    "Bible",
    "Canon",
    "CharacterState",
    # Verifiers
    "InCharacterVerifier",
    "TropeVerifier",
    "CanonVerifier",
    "ToneVerifier",
    "FictionVerifier",
    "NarrativeVerifier",
    "VerificationResult",
    # Manuscript scanner
    "ManuscriptScanner",
    "ScanResult",
    "ExtractedCharacter",
    "ExtractedLocation",
    "ExtractedEvent",
    "ExtractedThread",
    "scan_manuscript_to_canon",
    "scan_single_chapter",
    # Similarity matching
    "SimilarityMatch",
    "VoiceAnalysis",
    "ToneAnalysis",
    "EmbeddingProvider",
    "TFIDFProvider",
    "SimilarityAnalyzer",
    "create_analyzer",
    "quick_trope_check",
    "quick_voice_check",
    "compute_text_similarity",
    # Context drift detection
    "NarrativeMode",
    "RiskTier",
    "DriftFaultType",
    "HysteresisConfig",
    "ModeSignal",
    "ModeTransition",
    "DriftFault",
    "DriftState",
    "ContextDriftDetector",
    "classify_register",
    "estimate_risk_tier",
    "create_context_drift_detector",
    # Fiction guardrails
    "ConsentLevel",
    "ConsentScope",
    "HardConstraintId",
    "SoftPenaltyId",
    "ConsentPairState",
    "GlobalConsentState",
    "ValidityProfile",
    "DSISignal",
    "AIISignal",
    "ConstraintViolation",
    "PenaltyResult",
    "GuardrailConfig",
    "StateContext",
    "GuardrailResult",
    "ConsentLedger",
    "DSIDetector",
    "AIIDetector",
    "FictionGuardrails",
    "detect_sexual_content",
    "detect_coercion",
    "detect_proxy_dominance",
    "detect_unearned_facts",
    "create_consent_ledger",
    "create_fiction_guardrails",
    "create_guardrail_config",
    "create_validity_profile",
    "get_builtin_profiles",
]
