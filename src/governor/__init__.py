"""
Epistemic Governor for Agentic Development

A constraint system that makes AI coding agents production-safe by preventing
hallucination, maintaining architectural coherence, and enforcing evidence requirements.
"""

from .core import AgentGovernor
from .ledger import CodebaseLedger, Commitment, CommitID
from .validators import Validator, FileValidator, Evidence
from .types import ProposalResult, Contradiction

__all__ = [
    "AgentGovernor",
    "CodebaseLedger", 
    "Commitment",
    "CommitID",
    "Validator",
    "FileValidator",
    "Evidence",
    "ProposalResult",
    "Contradiction",
]

__version__ = "0.1.0"
