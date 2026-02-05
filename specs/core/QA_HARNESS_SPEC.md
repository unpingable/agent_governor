# QA Harness Specification

## Version 0.1 — Self-Validating Test Infrastructure

```yaml
status: gap
implemented: false
depends_on:
  - KERNEL_CONSTRAINTS_SPEC.md
  - EPISTEMIC_STACK_SPEC.md
blocking:
  - CI/CD integration
  - Release confidence
estimated_scope: medium
```

---

## Executive Summary

The QA Harness provides **self-validating test infrastructure** that catches bugs the unit tests miss. The system that governs AI agents should be able to pass its own gates.

**Marketing sentence**: "A system that can't pass its own gates has no business governing anything else."

---

## 1. Build Priority

| Priority | Component | Effort | Value | Notes |
|----------|-----------|--------|-------|-------|
| 1 | CLI Smoke Harness | Low | High | Catches dumbest bugs first |
| 2 | Self-Governance | Medium | Very High | QA tool + demo + marketing |
| 3 | Serialization Roundtrip | Low | Medium | Catches bugs 6 months from now |
| 4 | Cross-Module Lifecycle | Medium | High | Proves seams hold |
| ∞ | Mutation Testing | High | High | Deferred — high compute |

---

## 2. Component Specifications

### 2.1 CLI Smoke Harness

**Purpose**: Verify all CLI commands execute without crashing.

**Scope**:
- Every `governor` subcommand
- Every `fiction-gov` subcommand
- Every `nonfiction-gov` subcommand
- Every `ops-gov` subcommand

**Implementation**:
```python
def test_cli_smoke():
    """Every CLI command should at least parse and not crash."""
    commands = [
        "governor --help",
        "governor init --help",
        "governor propose --help",
        # ... all commands from cli-reference.md
    ]
    for cmd in commands:
        result = subprocess.run(cmd.split(), capture_output=True)
        assert result.returncode in {0, 1, 2}  # 0=success, 1=expected error, 2=usage
        assert "Traceback" not in result.stderr.decode()
```

**Automation**: Run on every PR, block merge on failure.

---

### 2.2 Self-Governance

**Purpose**: The governor validates its own outputs.

**Core Test**:
```python
def test_self_governance():
    """Governor must pass its own gates."""
    # Initialize governor
    gov = Governor()

    # Generate some output (e.g., a commit message, a code change)
    output = generate_test_output()

    # Run through governor gates
    result = gov.check(output)

    # Must pass
    assert result.is_valid, f"Governor failed its own gates: {result.violations}"
```

**Scenarios**:
1. Commit messages must pass claim-evidence coupling
2. Code changes must pass security verifier
3. Documentation must pass structural constraints
4. Test outputs must pass epistemic grounding

**The Invariant**: If the governor's own artifacts can't pass the governor, something is wrong with either the artifacts or the gates.

---

### 2.3 Serialization Roundtrip Sweep

**Purpose**: Every serializable type survives `to_dict()` → `from_dict()` → `to_dict()`.

**Implementation**:
```python
SERIALIZABLE_TYPES = [
    GroundedClaim,
    QuorumState,
    Objection,
    TTLPolicy,
    ToneVector,
    RegimeVector,
    # ... all @dataclass types with to_dict/from_dict
]

@pytest.mark.parametrize("cls", SERIALIZABLE_TYPES)
def test_roundtrip(cls):
    """Serialization must be lossless."""
    instance = create_valid_instance(cls)
    serialized = instance.to_dict()
    deserialized = cls.from_dict(serialized)
    reserialized = deserialized.to_dict()
    assert serialized == reserialized
```

**Automation**: Run nightly, alert on failure.

---

### 2.4 Cross-Module Lifecycle Test

**Purpose**: Prove the seams hold — claims flow correctly through the full stack.

**Lifecycle Under Test**:
```
Signal extraction → Claim creation → Quorum voting →
TTL assignment → Audit pipeline → Dissent handling →
Status transitions → Snapshot diffing → Decay/expiry
```

**Implementation**:
```python
def test_claim_lifecycle():
    """Full claim lifecycle through all modules."""
    # 1. Extract signal
    text = "The server responds in under 100ms."
    signals = SignalExtractor().extract(text)

    # 2. Create claim
    ledger = EpistemicLedger()
    claim = ledger.create_claim(
        content=signals[0].text,
        provenance=Provenance.ASSUMED,
    )

    # 3. Attach evidence
    evidence = EvidenceRef(type=EvidenceType.TOOL_TRACE, locator="...")
    ledger.attach_evidence(claim.id, evidence)

    # 4. Submit for quorum
    quorum = QuorumManager()
    proposal = quorum.create_proposal(claim.id, ClaimType.VOLATILE_FACT)

    # 5. Vote
    quorum.vote(proposal.id, agent_id="agent-1", verdict=VoteVerdict.APPROVE)
    quorum.vote(proposal.id, agent_id="agent-2", verdict=VoteVerdict.APPROVE)

    # 6. Check status progression
    assert quorum.get_status(proposal.id) == QuorumStatus.STABILIZING

    # 7. Wait for Δt (or mock time)
    quorum.advance_time(delta_t)
    assert quorum.get_status(proposal.id) == QuorumStatus.REACHED

    # 8. Run audit
    audit = AuditPipeline()
    result = audit.audit(claim.id)
    assert result.status == GroundingStatus.GROUNDED

    # 9. Take snapshot, modify, diff
    snapshot1 = ledger.snapshot()
    ledger.update_confidence(claim.id, 0.9)
    snapshot2 = ledger.snapshot()
    diff = ClaimDiffer().diff(snapshot1, snapshot2)
    assert len(diff.violations) == 0  # Confidence change with evidence is OK

    # 10. TTL decay
    ttl = TTLManager()
    ttl.advance_time(claim.ttl + timedelta(hours=1))
    assert ledger.get(claim.id).status == ClaimStatus.STALE
```

**Automation**: Run on every PR touching epistemic modules.

---

## 3. Test Infrastructure Requirements

### 3.1 Fixtures

```python
# Shared fixtures for QA harness
@pytest.fixture
def fresh_governor():
    """Clean governor instance with temp directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Governor(root=tmpdir)

@pytest.fixture
def populated_ledger():
    """Ledger with sample claims across all statuses."""
    ledger = EpistemicLedger(":memory:")
    # Populate with representative claims
    yield ledger
```

### 3.2 Time Mocking

```python
@pytest.fixture
def mock_time():
    """Control time for TTL/Δt tests."""
    with freeze_time("2026-02-05 12:00:00") as frozen:
        yield frozen
```

### 3.3 Output Capture

```python
def capture_cli(args: list[str]) -> tuple[int, str, str]:
    """Run CLI and capture output."""
    result = subprocess.run(
        ["governor"] + args,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr
```

---

## 4. Success Criteria

| Component | Pass Condition |
|-----------|----------------|
| CLI Smoke | Zero tracebacks across all commands |
| Self-Governance | Governor artifacts pass governor gates |
| Roundtrip | 100% of serializable types survive roundtrip |
| Lifecycle | Claims traverse full stack without corruption |

---

## 5. Implementation Order

1. **CLI Smoke Harness** (`tests/test_qa_cli_smoke.py`)
   - Extract command list from cli-reference.md
   - Run each with --help
   - Assert no tracebacks

2. **Self-Governance** (`tests/test_qa_self_governance.py`)
   - Test commit messages
   - Test code changes
   - Test documentation

3. **Roundtrip Sweep** (`tests/test_qa_roundtrip.py`)
   - Enumerate all serializable types
   - Generate valid instances
   - Assert roundtrip equality

4. **Lifecycle Test** (`tests/test_qa_lifecycle.py`)
   - Full claim flow
   - All module integrations
   - Time-based transitions

---

## 6. Deferred: Mutation Testing

**What it is**: Automatically mutate code (flip conditions, change operators) and verify tests catch the mutations.

**Why deferred**: High compute cost, better ROI after other harnesses exist.

**When to build**: After CI has capacity, and after the other harnesses prove stable.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec |
