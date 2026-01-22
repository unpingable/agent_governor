"""
Fiction Governor: Constraint system for LLM-assisted fiction writing.

Keeps characters in-character, stories consistent, and tropes at bay.
"""

from .types import (
    Character,
    CharacterTrait,
    CharacterVoice,
    WorldRule,
    BannedTrope,
    ToneSettings,
    CanonEvent,
    Relationship,
    FictionClaimType,
    FictionClaim,
)
from .bible import Bible
from .canon import Canon
from .verifiers import (
    InCharacterVerifier,
    TropeVerifier,
    CanonVerifier,
    ToneVerifier,
    FictionVerifier,
)

__all__ = [
    # Types
    "Character",
    "CharacterTrait",
    "CharacterVoice",
    "WorldRule",
    "BannedTrope",
    "ToneSettings",
    "CanonEvent",
    "Relationship",
    "FictionClaimType",
    "FictionClaim",
    # Ledgers
    "Bible",
    "Canon",
    # Verifiers
    "InCharacterVerifier",
    "TropeVerifier",
    "CanonVerifier",
    "ToneVerifier",
    "FictionVerifier",
]
