# Perforce Support Specification

## Version 0.1 — Integrity Invariants on Explicit Authority

```yaml
status: gap
implemented: false
depends_on:
  - KERNEL_CONSTRAINTS_SPEC.md
  - GIT_GOVERNANCE_SPEC.md
blocking:
  - Enterprise/studio adoption
  - DoD/regulated environment support
estimated_scope: medium
```

---

## Executive Summary

Perforce support applies the same integrity invariants as Git governance, but on a substrate that already admits authority exists. P4's explicit changelists, file-level locking, and immutable history map directly to Governor's principles.

**Core Insight**: Git culture hides authority in vibes. Perforce admits it exists. Governor just makes that explicit.

**Scope**: Narrow and invariant-focused. Not enterprise compliance theater.

---

## 1. Why Perforce Fits Governor

Perforce is already opinionated about things Git hand-waves:

| P4 Feature | Governor Alignment |
|------------|-------------------|
| Single source of truth | Authority ≠ narrative |
| Explicit changelists | Typed claims, not prose |
| File-level locking | No silent conflicts |
| Central immutable history | Scar tissue > vibes |

This is why AAA studios, chip fabs, and DoD contractors use it. Not because it's fun. Because it hurts in the right places.

---

## 2. Governor × Perforce Leverage Points

### 2.1 Changelist Integrity

**Rule**: Metadata claims must correspond to files in the changelist.

```python
@dataclass
class ChangelistIntegrityCheck:
    changelist: int
    metadata_claims: list[str]      # What metadata says exists
    files_in_cl: list[str]          # What's actually in the CL
    referenced_cls: list[int]       # Prior CLs referenced

def verify_changelist_integrity(cl: int) -> list[Violation]:
    """
    If paper/metadata says 'artifact exists':
    - CL must include it, OR
    - CL must reference prior CL containing it
    """
    ...
```

**Violation**: Claimed artifact not in changelist and not in referenced prior changelist.

---

### 2.2 Lock Semantics

**Rule**: Locked files are authoritative state, not suggestions.

```python
class LockSemantics:
    def check_lock_authority(self, file: str) -> LockState:
        """
        If file is locked:
        - Governor treats lock holder as authority
        - Other agents cannot 'reason past' the lock
        - Claims about locked files require lock holder confirmation
        """
        ...

    def prevent_lock_bypass(self, agent_id: str, file: str) -> bool:
        """
        Block agent from making claims about files locked by others.
        """
        ...
```

**Rationale**: Prevents two agents "reasoning" past each other on the same file.

---

### 2.3 Immutable Release Changelists

**Rule**: Tagged release CLs become read-only.

```python
class ReleaseChangelistPolicy:
    immutable_tags: list[str] = ["published", "preprint", "archival", "release"]

    def mark_immutable(self, cl: int, tag: str) -> None:
        """Once tagged, CL cannot be modified unless explicitly forked."""
        ...

    def check_modification_attempt(self, cl: int) -> Violation | None:
        """Block modifications to immutable CLs."""
        ...

    def fork_for_correction(self, cl: int, reason: str) -> int:
        """Create new CL that supersedes immutable one, with audit trail."""
        ...
```

**Violation**: Attempting to modify a changelist tagged as immutable.

---

### 2.4 Depot ↔ DOI Mapping

**Rule**: DOI corresponds to depot path + changelist number. No ambiguity.

```python
@dataclass
class DepotDOIMapping:
    doi: str
    depot_path: str
    changelist: int
    timestamp: datetime

    def verify(self) -> bool:
        """
        Verify:
        - DOI resolves
        - Depot path exists
        - Changelist contains expected content
        - Content hash matches DOI metadata
        """
        ...
```

**Invariant**: One DOI = one depot path + one changelist. Forever.

---

## 3. What NOT To Do

| Anti-Pattern | Why Forbidden |
|--------------|---------------|
| Recreate P4 triggers as moral judgments | Governor enforces integrity, not culture |
| Enforce naming conventions | Workflow preference, not provenance |
| Enforce workflow rituals | Perforce already has enough priests |
| Duplicate P4 admin functionality | Use P4's native tools |

---

## 4. Integration Architecture

### 4.1 P4 Command Interface

```python
class P4Client:
    """Thin wrapper around p4 CLI."""

    def get_changelist(self, cl: int) -> Changelist:
        """p4 describe -s {cl}"""
        ...

    def get_files_in_cl(self, cl: int) -> list[str]:
        """p4 files @={cl}"""
        ...

    def get_lock_status(self, file: str) -> LockState | None:
        """p4 opened -a {file}"""
        ...

    def get_labels(self, cl: int) -> list[str]:
        """p4 labels @{cl}"""
        ...
```

### 4.2 Governor Adapter

```python
class PerforceGovernorAdapter:
    """Adapts Governor invariants to P4 substrate."""

    def __init__(self, p4: P4Client, config: P4GovernanceConfig):
        self.p4 = p4
        self.config = config

    def pre_submit_check(self, cl: int) -> list[Violation]:
        """Run all integrity checks before p4 submit."""
        violations = []
        violations.extend(self.check_changelist_integrity(cl))
        violations.extend(self.check_lock_semantics(cl))
        violations.extend(self.check_immutability(cl))
        violations.extend(self.check_doi_mapping(cl))
        return violations

    def post_submit_audit(self, cl: int) -> AuditResult:
        """Audit after submit for compliance verification."""
        ...
```

### 4.3 P4 Trigger Integration

```bash
# In P4 triggers table
submit-commit //depot/... "python /path/to/governor p4 pre-submit %changelist%"
```

```python
# CLI command
@cli.group()
def p4():
    """Perforce governance commands."""
    pass

@p4.command()
@click.argument("changelist", type=int)
def pre_submit(changelist: int):
    """Pre-submit integrity check for P4 changelist."""
    adapter = PerforceGovernorAdapter(...)
    violations = adapter.pre_submit_check(changelist)
    if violations:
        for v in violations:
            click.echo(f"VIOLATION: {v}", err=True)
        sys.exit(1)
    sys.exit(0)
```

---

## 5. Configuration

```yaml
# .governor/p4_policy.yaml
enabled: true

p4_connection:
  port: "ssl:perforce.example.com:1666"
  user: "${P4USER}"
  client: "${P4CLIENT}"

changelist_integrity:
  enabled: true
  require_metadata_match: true
  allow_prior_cl_reference: true

lock_semantics:
  enabled: true
  treat_as_authoritative: true
  block_cross_agent_claims: true

immutable_releases:
  enabled: true
  tags: ["published", "preprint", "archival", "release"]
  allow_fork_with_audit: true

doi_mapping:
  enabled: true
  depot_pattern: "//depot/papers/{doi_suffix}/..."
  require_exact_match: true
```

---

## 6. CLI Commands (Proposed)

```bash
# Changelist operations
governor p4 check <cl>              # Run all integrity checks
governor p4 pre-submit <cl>         # Pre-submit hook
governor p4 post-submit <cl>        # Post-submit audit

# Lock operations
governor p4 locks show              # Show files locked by agents
governor p4 locks check <file>      # Check lock authority

# Release operations
governor p4 release tag <cl> <tag>  # Mark CL as immutable
governor p4 release fork <cl>       # Fork immutable CL for correction

# DOI operations
governor p4 doi map <doi> <depot> <cl>   # Create mapping
governor p4 doi verify <doi>             # Verify mapping integrity
governor p4 doi list                     # List all mappings
```

---

## 7. Implementation Notes

### 7.1 What Exists

- Git governance patterns (reusable concepts)
- Pre-commit hook infrastructure
- Cross-index validation logic

### 7.2 What Needs Building

| Component | Effort | Priority |
|-----------|--------|----------|
| P4 CLI wrapper | Small | High |
| Changelist integrity checker | Small | High |
| Lock semantics enforcer | Medium | Medium |
| Immutable release manager | Small | Medium |
| DOI mapping system | Medium | Low |
| P4 trigger integration | Small | High |

### 7.3 Dependencies

- P4 CLI installed and configured
- P4 server with trigger support
- Environment variables: `P4PORT`, `P4USER`, `P4CLIENT`

---

## 8. The Real Point

If Governor supports both Git and Perforce, it proves:

> This was never about tools.
> It's about **where authority lives**.

Git culture hides authority in vibes. Perforce admits it exists. Governor makes that explicit regardless of substrate.

---

## 9. Success Criteria

| Criterion | Test |
|-----------|------|
| Changelist integrity | Metadata claim without file in CL blocked |
| Lock semantics | Cross-agent claim on locked file blocked |
| Immutable releases | Modification of tagged CL blocked |
| DOI mapping | Invalid mapping detected |
| Trigger integration | p4 submit blocked on violation |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec |
