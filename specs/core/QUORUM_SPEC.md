# Multi-Agent Quorum Specification (2.1)

```yaml
status: planning
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, DEPLOYMENT_PROFILES_SPEC, METRICS_SPEC]
note: Extends existing quorum.py with severity-based gating, Byzantine-lite model, two-man rule
```

## Overview

Multi-agent coordination implies quorums. Not full Byzantine (PBFT), but "Byzantine-lite" — disagreement alone ≠ Byzantine, but we must handle compromised components (poisoned tools, injected docs, tampered caches).

## Quorum Rules

For S3 claims, require:
- ≥ k independent evidence domains
- ≥ k confirmations
- Where k = f + 1 (f = assumed faulty/adversarial agents)

```python
@dataclass
class QuorumRequirement:
    min_confirmations: int
    min_evidence_domains: int
    require_independence: bool  # Different tool domains / model families

S3_QUORUM = QuorumRequirement(
    min_confirmations=2,
    min_evidence_domains=2,
    require_independence=True
)

def check_quorum(claim: Claim, confirmations: List[Confirmation]) -> bool:
    if claim.severity != Severity.S3:
        return True  # No quorum for S1/S2

    # Count independent confirmations
    domains = set(c.evidence_domain for c in confirmations)
    models = set(c.model_family for c in confirmations if c.model_family)

    return (
        len(confirmations) >= S3_QUORUM.min_confirmations and
        len(domains) >= S3_QUORUM.min_evidence_domains and
        (not S3_QUORUM.require_independence or len(models) >= 2)
    )
```

## Independence Constraints

To reduce correlated failure:
- Different tool domains (web vs local vs API)
- Different model families (if multi-model)
- Different sandboxes/contexts

```python
@dataclass
class Confirmation:
    claim_id: str
    confirmer: str           # agent/model ID
    model_family: str        # "claude", "gpt", "gemini", etc.
    evidence_domain: str     # "web", "local_file", "api", "computation"
    evidence: Evidence
    confidence: float
    timestamp: datetime
```

## Two-Man Rule for S3 Actions

```
action_allowed ⟺ cap_human(H) ∧ cap_independent_confirmer(H)
```

Where H = hash of action proposal.

```python
def check_two_man_rule(action: Action, ledger: Ledger) -> bool:
    if action.severity != Severity.S3:
        return True

    proposal_hash = hash_action(action)

    human_approval = ledger.find_event(
        type="approval",
        proposal_hash=proposal_hash,
        approver_type="human"
    )
    independent_confirmation = ledger.find_event(
        type="confirmation",
        proposal_hash=proposal_hash,
        confirmer_type="independent"  # Different from proposer
    )

    return human_approval is not None and independent_confirmation is not None
```

## Disagreement Handling

When agents disagree:
1. Route to targeted adjudication (additional checks on disputed claims)
2. Require evidence, not prose consensus
3. Log disagreement with rationales

## Events

```json
{"event": "quorum_check", "claim_id": "c_042", "severity": "S3", "confirmations": 2, "domains": ["web", "local_file"], "models": ["claude", "gpt"], "result": "passed", "timestamp": "..."}
{"event": "quorum_disagreement", "claim_id": "c_042", "confirmations": 1, "rejections": 1, "action": "adjudication_requested", "timestamp": "..."}
{"event": "adjudication_check", "claim_id": "c_042", "check_type": "independent_verification", "result": "confirmed", "timestamp": "..."}
{"event": "two_man_rule_check", "proposal_hash": "abc123", "human_approval": true, "independent_confirmation": true, "result": "passed", "timestamp": "..."}
```

## Relationship to Existing quorum.py

The existing `quorum.py` implements multi-agent consensus with Δt stability windows, claim-type policies, dissent/TTL integration, risk levels, and fingerprint gating. This 2.1 spec extends it with:

1. **Severity-based gating** (S1/S2/S3 classification)
2. **Byzantine-lite model** (compromised component handling)
3. **Two-man rule** (human + independent confirmer for S3)
4. **Evidence domain independence** (cross-domain confirmation)
5. **Adjudication routing** (targeted re-checks on disputes)

## Integration

- **Deployment Profiles** (DEPLOYMENT_PROFILES_SPEC): Authority class sets quorum requirements
- **Metrics** (METRICS_SPEC): Quorum results feed coverage computation
- **Existing independence.py**: Method-level independence scoring feeds quorum independence check
- **Existing sybil.py**: Bloc detection gates quorum participation
