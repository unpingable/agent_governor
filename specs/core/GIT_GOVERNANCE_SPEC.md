# Git Governance Specification

## Version 0.1 — Integrity Invariants at Commit Boundaries

```yaml
status: gap
implemented: false
depends_on:
  - KERNEL_CONSTRAINTS_SPEC.md
  - hooks.py (pre-commit integration)
blocking:
  - Release provenance verification
  - Cross-artifact integrity checks
estimated_scope: small
```

---

## Executive Summary

Git governance enforces **integrity invariants** at commit and tag boundaries while leaving **workflow preferences** to agents and humans. The governor is not a repo nanny — it validates provenance, not culture.

**Core Principle**: Profile controls how loud violations are, not whether invariants exist. Invariants are always checked. Greenfield warns, anchored blocks.

---

## 1. What Governor Enforces (Hard Invariants)

These are integrity checks where silent failure ruins provenance.

### 1.1 Artifact Integrity

**Rule**: No untracked or generated artifacts in commits unless explicitly allowed.

```yaml
# .governor/git_policy.yaml
artifact_rules:
  always_ignored:
    - "*.pyc"
    - "__pycache__/"
    - "*.egg-info/"
    - "dist/"
    - "build/"

  always_tracked:
    - "*.lock"  # lockfiles must be committed
    - "poetry.lock"
    - "package-lock.json"

  require_explicit:
    - "*.pdf"   # must be in allowlist or ignored
    - "*.whl"
```

**Violation**: Commit contains artifact that is neither in `always_tracked` nor `always_ignored` and not in explicit allowlist.

**Rationale**: "Sometimes tracked, sometimes not" artifacts break reproducibility and provenance.

---

### 1.2 Cross-Index Integrity

**Rule**: If metadata claims X, X must exist.

| Metadata Claim | Required Verification |
|----------------|----------------------|
| DOI in `metadata.yaml` | DOI appears in paper header or README |
| Repo URL in paper | URL matches actual repository |
| Version tag claimed | Git tag exists |
| "Tests in repo" | Tagged commit has passing tests |
| Zenodo record | Record exists and links back |

```python
@dataclass
class CrossIndexCheck:
    source: str           # Where the claim is made
    claim_type: str       # What is claimed
    target: str           # What must exist
    verification: str     # How to verify
```

**Violation**: Claimed artifact or reference does not exist or does not match.

---

### 1.3 Tagging Discipline

**Rule**: Claimed artifacts require tags before they're called "confirmed."

```yaml
tagging_rules:
  paper_release:
    pattern: "paper-YYYY-MM-DD"
    requires:
      - metadata.yaml valid
      - all cross-index checks pass
      - no untracked artifacts

  version_release:
    pattern: "v{semver}"
    requires:
      - CHANGELOG updated
      - version in pyproject.toml matches tag
      - tests pass
```

**Violation**: Attempting to claim a release without the required tag, or tag exists without required conditions.

---

### 1.4 Pre-Commit Provenance Checks

**Rule**: Lightweight validation before commit is allowed.

| Check | What It Validates |
|-------|-------------------|
| YAML validity | `metadata.yaml` parses without error |
| Required keys | Configured keys are present |
| Date parsing | Dates in expected format |
| No tab/indent breakage | Whitespace consistency |
| No secrets | Patterns from security verifier |

```python
class PreCommitCheck:
    def check_metadata_yaml(self, path: Path) -> list[Violation]:
        """Validate metadata.yaml structure and content."""
        ...

    def check_required_keys(self, data: dict, required: list[str]) -> list[Violation]:
        """Ensure required keys are present."""
        ...

    def check_dates(self, data: dict, date_fields: list[str]) -> list[Violation]:
        """Validate date formats."""
        ...
```

---

## 2. What Governor Does NOT Enforce (Soft / UX)

These are workflow preferences left to agents, config, or team taste.

| Preference | Why Not Enforced |
|------------|------------------|
| Branch naming conventions | Culture, not integrity |
| Commit message style | Culture, not integrity |
| Squash vs rebase | Workflow preference |
| PR etiquette / templates | Team process |
| When to push vs work locally | Developer choice |

**Rationale**: Enforcing these turns Governor into an annoying nanny. They don't affect provenance or reproducibility.

---

## 3. Profile-Based Severity

Invariants are always checked. Profiles control response severity.

| Profile | Artifact Integrity | Cross-Index | Tagging | Pre-Commit |
|---------|-------------------|-------------|---------|------------|
| greenfield | warn | warn | warn | warn |
| established | warn | block | warn | block |
| production | block | block | block | block |
| hotfix | warn | block | defer | block |

```python
class GitGovernanceConfig:
    profile: str
    severity_overrides: dict[str, Severity]

    def get_severity(self, check_type: str) -> Severity:
        if check_type in self.severity_overrides:
            return self.severity_overrides[check_type]
        return PROFILE_DEFAULTS[self.profile][check_type]
```

---

## 4. Integration Points

### 4.1 With Existing Pre-Commit Hook

`src/governor/hooks.py` already implements pre-commit integration. Git governance extends this:

```python
# In hooks.py
def pre_commit_hook(staged_files: list[Path]) -> HookResult:
    results = []

    # Existing checks
    results.extend(security_check(staged_files))
    results.extend(continuity_check(staged_files))

    # Git governance checks (new)
    results.extend(artifact_integrity_check(staged_files))
    results.extend(metadata_check(staged_files))

    return aggregate_results(results)
```

### 4.2 With Tagging (New)

```bash
# Hook into git tag
governor git tag-check v1.0.0  # Verify tag conditions
governor git tag-create v1.0.0 --verify  # Create only if conditions met
```

### 4.3 With Cross-Index Validation (New)

```bash
governor git cross-index check  # Validate all cross-references
governor git cross-index fix    # Suggest fixes for violations
```

---

## 5. CLI Commands (Proposed)

```bash
# Artifact integrity
governor git artifacts check          # Check for policy violations
governor git artifacts allow <path>   # Add to explicit allowlist

# Cross-index
governor git cross-index check        # Validate cross-references
governor git cross-index show         # List all claimed references

# Tagging
governor git tag check <tag>          # Verify tag conditions
governor git tag create <tag>         # Create with verification

# Pre-commit
governor git pre-commit install       # Install git hooks
governor git pre-commit run           # Run checks manually
```

---

## 6. Configuration

```yaml
# .governor/git_policy.yaml
profile: established

artifact_rules:
  always_ignored: [...]
  always_tracked: [...]
  require_explicit: [...]
  allowlist: [...]

cross_index:
  enabled: true
  checks:
    - doi_in_readme
    - repo_url_matches
    - version_tags_exist

tagging:
  patterns:
    paper: "paper-{date}"
    release: "v{semver}"
  requirements:
    paper: [metadata_valid, cross_index_pass]
    release: [changelog_updated, version_matches, tests_pass]

pre_commit:
  metadata_yaml: true
  required_keys: [title, date, version]
  date_format: "YYYY-MM-DD"
  secrets_check: true
```

---

## 7. Implementation Notes

### 7.1 What Exists

- `hooks.py` — Pre-commit hook infrastructure
- `security.py` — Secret detection patterns
- `continuity.py` — Anchor checking

### 7.2 What Needs Building

| Component | Effort | Priority |
|-----------|--------|----------|
| Artifact integrity checker | Small | High |
| Cross-index validator | Medium | Medium |
| Tag verification | Small | Medium |
| CLI commands | Small | High |
| Configuration schema | Small | High |

### 7.3 Reusable Primitives

- Secret patterns from `security.py`
- Hook infrastructure from `hooks.py`
- YAML validation patterns from existing config loading
- Git operations via `subprocess` (already used in hooks)

---

## 8. Success Criteria

| Criterion | Test |
|-----------|------|
| Artifact violations caught | Commit with untracked PDF blocked |
| Cross-index validated | Claimed DOI that doesn't exist flagged |
| Tags verified | Tag without required conditions blocked |
| Pre-commit works | Invalid metadata.yaml blocks commit |
| Profile severity works | Greenfield warns, production blocks |

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec |
