# Next Session: Quorum State Machine

## Summary

New module `src/governor/quorum.py` — multi-agent consensus protocol for claim
commitment. Proposals requiring quorum collect votes from eligible agents,
enforce stability windows, and gate FSM transitions.

**TODO.md items covered:**
- Temporal quorum protocol (line 615)
- Δt budgets per claim type (line 627)
- Quorum state machine (line 649)

## Architecture Decision: Separate QuorumState + FSM Guard

After reviewing the existing modules, the cleanest approach is:

1. **Quorum as a standalone module** (not embedded in fsm.py)
2. **Votes are NOT objections** — they're a parallel concept (positive consensus, not dissent)
3. **DissentLedger blocks commit** if objections exist; **QuorumManager requires consensus** before verify
4. **Both gates must pass**: no blocking objections AND quorum reached
5. **TTL integration**: consensus has a volatility class, old consensus expires

## Dependencies (all exist)

| Module | What we use |
|--------|-------------|
| `dissent.py` | `DissentLedger.can_commit()` — hard block check |
| `ttl.py` | `VolatilityClass`, `TTLPolicy` — consensus freshness |
| `permissions.py` | `AgentPermissions.can_propose_decisions` — voter eligibility |
| `fsm.py` | `ProposalState` — state enum (extend with UNDER_REVIEW) |

## Core Types

```python
class ClaimType(str, Enum):
    """Claim types with Δt budgets."""
    MATH = "math"           # Δt=1s, k=2, reversible
    CODE = "code"           # Δt=10s, k=1-2, mostly reversible
    STATIC_FACT = "static_fact"  # Δt=30-120s, k=2-3, usually irreversible
    VOLATILE_FACT = "volatile_fact"  # Δt=60-300s, k=3+, irreversible
    PROCEDURE = "procedure"  # Δt=300s+, k=3+, dangerous
    JUDGMENT = "judgment"    # Δt=600s+, k=3+, human-in-loop

class VoteVerdict(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ABSTAIN = "abstain"

class QuorumStatus(str, Enum):
    COLLECTING = "collecting"    # Gathering votes
    STABILIZING = "stabilizing"  # Δt window (must remain stable)
    REACHED = "reached"          # Consensus achieved
    FAILED = "failed"            # Not enough votes or too many rejections
    EXPIRED = "expired"          # TTL expired on consensus
    CONTESTED = "contested"      # Was reached, then objection filed

@dataclass
class QuorumPolicy:
    """Per-claim-type policy."""
    claim_type: ClaimType
    min_voters: int           # k agents required
    approval_threshold: float # fraction needed (e.g., 0.67)
    delta_t: timedelta        # stability window
    volatility: VolatilityClass  # TTL for consensus
    requires_human: bool = False

@dataclass
class Vote:
    vote_id: str
    proposal_id: str
    agent_id: str
    verdict: VoteVerdict
    reason: str
    evidence: list[EvidencePointer]
    timestamp: datetime

@dataclass
class QuorumState:
    """Tracks consensus progress for a single proposal."""
    proposal_id: str
    policy: QuorumPolicy
    status: QuorumStatus
    votes: dict[str, Vote]   # agent_id → Vote
    created_at: datetime
    stabilized_at: datetime | None  # when consensus first reached

    # Properties:
    # approval_count, rejection_count, abstain_count
    # approval_ratio
    # has_quorum: bool (enough voters + threshold met)
    # is_stable: bool (Δt window elapsed since consensus)
    # can_commit: bool (has_quorum AND is_stable AND no dissent blocks)

class QuorumManager:
    """Manages quorum states for all proposals."""

    def create_quorum(proposal_id, claim_type, ...) -> QuorumState
    def cast_vote(proposal_id, agent_id, verdict, reason, evidence) -> Vote
    def check_status(proposal_id) -> QuorumStatus
    def can_proceed(proposal_id, dissent_ledger) -> (bool, list[str])
    def enforce_ttl(ttl_manager) -> list[str]  # expired proposal IDs
    def get_policy(claim_type) -> QuorumPolicy
```

## Default Policies (from TODO.md Δt budgets)

| ClaimType | Δt | k | Threshold | Volatility | Human? |
|-----------|-----|---|-----------|------------|--------|
| MATH | 1s | 2 | 0.5 | PERMANENT | No |
| CODE | 10s | 1 | 0.5 | STABLE | No |
| STATIC_FACT | 120s | 2 | 0.67 | MODERATE | No |
| VOLATILE_FACT | 300s | 3 | 0.67 | VOLATILE | No |
| PROCEDURE | 300s | 3 | 0.75 | MODERATE | No |
| JUDGMENT | 600s | 3 | 0.75 | STABLE | Yes |

## State Transitions

```
COLLECTING ──(enough votes + threshold met)──→ STABILIZING
STABILIZING ──(Δt window elapsed)──→ REACHED
STABILIZING ──(new REJECT vote)──→ COLLECTING  (reset stability clock)
REACHED ──(dissent filed)──→ CONTESTED
CONTESTED ──(dissent resolved)──→ REACHED
COLLECTING ──(timeout / insufficient votes)──→ FAILED
REACHED ──(TTL expired)──→ EXPIRED
```

## Integration Points

1. **FSM guard**: `QuorumManager.can_proceed()` called before PROPOSED → VERIFIED
2. **Dissent check**: `can_proceed()` internally calls `dissent_ledger.can_commit()`
3. **TTL tracking**: When REACHED, track consensus with `ttl_manager.track()`
4. **Permissions**: Filter eligible voters via `permission_manager.get_permissions()`

## Test Structure (~80 tests)

| Test Class | Focus |
|------------|-------|
| TestClaimTypeEnum | All 6 types, string values |
| TestVoteVerdict | 3 verdicts |
| TestQuorumStatus | 6 statuses |
| TestQuorumPolicy | Creation, defaults, per-type policies |
| TestVote | Creation, to_dict |
| TestQuorumState | Status, approval counting, threshold, stability |
| TestQuorumManager | Create, vote, check, lifecycle |
| TestStabilityWindow | Δt enforcement, clock reset on reject |
| TestDissentIntegration | can_proceed with dissent blocks |
| TestTTLIntegration | Consensus expiry |
| TestDefaultPolicies | All 6 claim types have correct params |
| TestEdgeCases | Duplicate votes, invalid agents, empty quorum |

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/governor/quorum.py` | CREATE (~400 lines) |
| `tests/test_quorum.py` | CREATE (~600 lines) |
| `src/governor/__init__.py` | EDIT (add exports) |
| `src/governor/cli.py` | EDIT (add `governor quorum` group) |
| `CLAUDE.md` | EDIT (add to tables) |
| `TODO.md` | EDIT (mark 3 items complete) |

## CLI Commands

```
governor quorum status <proposal_id>   # Show quorum state
governor quorum vote <proposal_id>     # Cast a vote
governor quorum policy <claim_type>    # Show policy for claim type
governor quorum policies               # List all policies
governor quorum history                # Show recent quorum activity
```

## Implementation Order

1. Enums + dataclasses (ClaimType, VoteVerdict, QuorumStatus, QuorumPolicy, Vote, QuorumState)
2. Default policies dict
3. QuorumState logic (approval counting, threshold, stability window)
4. QuorumManager (create, vote, check, lifecycle)
5. Integration functions (can_proceed with dissent, TTL tracking)
6. Tests
7. CLI commands
8. Exports + docs
