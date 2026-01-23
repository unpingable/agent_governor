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
]
