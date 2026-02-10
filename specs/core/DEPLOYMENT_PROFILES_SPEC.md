# Deployment Profiles Specification (Authority Classes)

```yaml
status: implemented
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, AG2_INSTRUMENT_SPEC, PHASE_CONTROL_SPEC]
```

## Overview

User ≠ Operator. Once running tools on behalf of others, the risk model shifts to delegated authority misuse, cross-tenant leakage, and liability.

## Authority Classes

| Class | Trust Model | Tool Access | Commit Rules | Audit Level |
|-------|-------------|-------------|--------------|-------------|
| A1: PUBLIC | Untrusted user, untrusted intent | Minimal (read-only, sandboxed) | Strict evidence gating | Standard |
| A2: DELEGATED | Trusted identity, untrusted intent | Limited tools + budgets | Two-phase commit for irreversible | Enhanced |
| A3: OPERATOR | Trusted identity, trusted intent | Broad tools | Approval for S3 only | Heavy + break-glass |
| A4: AUTONOMOUS | Automated pipeline | Per-policy | Pre-approved action sets | Full telemetry |

## Profile Definitions

```python
@dataclass
class DeploymentProfile:
    authority_class: AuthorityClass
    tool_whitelist: Set[str]
    tool_blacklist: Set[str]
    max_budget: Budget
    requires_two_phase: Set[Severity]  # which severities need approval
    evidence_threshold: float           # minimum E_t for action
    audit_level: AuditLevel

PUBLIC_PROFILE = DeploymentProfile(
    authority_class=AuthorityClass.A1,
    tool_whitelist={"web_search", "read_file"},
    tool_blacklist={"write_file", "execute", "send_email"},
    max_budget=Budget(explore=10, draft=5, verify=5),
    requires_two_phase={Severity.S2, Severity.S3},
    evidence_threshold=0.8,
    audit_level=AuditLevel.STANDARD
)

DELEGATED_PROFILE = DeploymentProfile(
    authority_class=AuthorityClass.A2,
    tool_whitelist={"web_search", "read_file", "write_file", "execute_sandboxed"},
    tool_blacklist={"send_email", "deploy", "delete"},
    max_budget=Budget(explore=20, draft=15, verify=10),
    requires_two_phase={Severity.S3},
    evidence_threshold=0.7,
    audit_level=AuditLevel.ENHANCED
)

OPERATOR_PROFILE = DeploymentProfile(
    authority_class=AuthorityClass.A3,
    tool_whitelist={"*"},  # all tools
    tool_blacklist=set(),
    max_budget=Budget(explore=50, draft=30, verify=20),
    requires_two_phase={Severity.S3},
    evidence_threshold=0.6,
    audit_level=AuditLevel.HEAVY
)
```

## Two-Phase Commit Protocol

For actions requiring approval:

**Phase A (Propose):**
```json
{"event": "action_proposed", "action": "write_file", "args": {"path": "/etc/config"}, "predicted_effects": ["modifies system config"], "severity": "S3", "approval_required": true, "proposal_hash": "abc123", "timestamp": "..."}
```

**Phase B (Execute):**
Only if approval event exists in ledger:
```json
{"event": "action_approved", "proposal_hash": "abc123", "approved_by": "user_session_xyz", "timestamp": "..."}
{"event": "action_executed", "proposal_hash": "abc123", "result": "success", "timestamp": "..."}
```

## Capability Token Binding

Actions require capability tokens with scope/verbs/TTL:

```python
@dataclass
class CapabilityToken:
    id: str
    scope: Set[str]        # resource patterns (glob)
    verbs: Set[str]        # read, write, execute, delete
    ttl: timedelta
    rate_limit: RateLimit
    bound_to: str          # run_id or session_id
    issued_at: datetime

    def permits(self, action: Action) -> bool:
        return (
            action.verb in self.verbs and
            any(fnmatch(action.resource, pattern) for pattern in self.scope) and
            datetime.now() < self.issued_at + self.ttl and
            self.rate_limit.check()
        )
```

**Invariant B:** Action u is admissible iff ∃ token k such that k.permits(u).

**Invariant E:** Irreversible actions require approval event (two-phase commit).

## Events

```json
{"event": "profile_activated", "authority_class": "A2", "tool_whitelist": ["web_search", "read_file", "write_file"], "evidence_threshold": 0.7, "timestamp": "..."}
{"event": "capability_token_issued", "token_id": "tok_001", "scope": ["src/**"], "verbs": ["read", "write"], "ttl_s": 3600, "bound_to": "run_xyz", "timestamp": "..."}
{"event": "capability_token_expired", "token_id": "tok_001", "timestamp": "..."}
```

## Integration

- **Phase Control** (PHASE_CONTROL_SPEC): Profile sets max budget per phase
- **Risk Function** (RISK_FUNCTION_SPEC): Risk V can demote profile at runtime
- **Measurement Integrity** (MEASUREMENT_INTEGRITY_SPEC): Untrusted tools restricted by profile
- **Control Theory** (CONTROL_THEORY_SPEC): Authority class sets P_t ceiling
