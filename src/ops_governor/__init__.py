"""
Ops Governor: SRE/Operations constraint system.

Mechanical verification for operational claims:
- Claim gating with proof types
- Policy packs (installable constraints per environment)
- Incident timeline integrity
- Change management enforcement

The keystone: No claim without proof.
"""

from .types import (
    # Proof and claims
    ProofType,
    ProofRequirement,
    ProofEvidence,
    ClaimDefinition,
    ClaimAttempt,
    # Policy packs
    PolicyPack,
    # Incidents
    IncidentSeverity,
    IncidentStatus,
    IncidentEvent,
    Incident,
)

from .policy import (
    PolicyRegistry,
    ProofCollector,
    ClaimVerifier,
    # Built-in packs
    BUILTIN_PACKS,
    install_builtin_pack,
    create_deploy_safe_rollout_pack,
    create_incident_strict_pack,
    create_change_mgmt_basic_pack,
    create_database_migration_pack,
    create_security_access_pack,
    create_oncall_handoff_pack,
    create_feature_rollout_pack,
    create_infra_scaling_pack,
)

from .verifiers import (
    RunbookVerifier,
    TimeWindowVerifier,
    BlastRadiusVerifier,
    PreconditionChainVerifier,
)


__all__ = [
    # Proof and claims
    "ProofType",
    "ProofRequirement",
    "ProofEvidence",
    "ClaimDefinition",
    "ClaimAttempt",
    # Policy packs
    "PolicyPack",
    "PolicyRegistry",
    "ProofCollector",
    "ClaimVerifier",
    # Built-in packs
    "BUILTIN_PACKS",
    "install_builtin_pack",
    "create_deploy_safe_rollout_pack",
    "create_incident_strict_pack",
    "create_change_mgmt_basic_pack",
    "create_database_migration_pack",
    "create_security_access_pack",
    "create_oncall_handoff_pack",
    "create_feature_rollout_pack",
    "create_infra_scaling_pack",
    # Incidents
    "IncidentSeverity",
    "IncidentStatus",
    "IncidentEvent",
    "Incident",
    # Specialized verifiers
    "RunbookVerifier",
    "TimeWindowVerifier",
    "BlastRadiusVerifier",
    "PreconditionChainVerifier",
]

__version__ = "0.1.0"
