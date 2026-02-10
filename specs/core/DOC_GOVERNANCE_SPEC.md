# Document Governance Specification

## Version 0.1 — Docs as Governed Artifacts

```yaml
status: implemented
implemented: true
depends_on:
  - continuity.py            # AnchorRegistry, ContinuityChecker
  - claim_signals.py         # SignalExtractor, assertiveness scoring
  - ttl.py                   # TTLManager, VolatilityClass, revalidation
  - COMMITMENT_TRANSPORT_SPEC.md
  - SLIM_MODE_SPEC.md
  - CONSTRAINT_COMPILER_SPEC.md
blocking: nothing (new capability track)
estimated_scope: medium-large
```

### Companion to: COMMITMENT_TRANSPORT_SPEC.md, SLIM_MODE_SPEC.md

---

## Executive Summary

Documentation rots. Not because people are lazy, but because docs make claims that the system doesn't enforce. A runbook says "restart service X" but service X was renamed. A design doc says "we use JWT" but the auth module switched to sessions. An architecture page says "never touch the billing table directly" but nobody checks.

The governor already enforces that *agents* can't make ungrounded claims. This spec extends the same principle to *documents*: docs are governed artifacts that declare scope, link to live systems, and decay when their assumptions drift.

**Core principle**: Docs don't become trustworthy because they're well-written. They become trustworthy because they can't say things the system won't back.

**What the governor does**: Constrain what docs are allowed to claim, track when claims go stale, and surface authority violations. **What the governor does NOT do**: Write docs, enforce style, or generate content.

---

## 1. The Problem

### 1.1 How Docs Fail

| Failure Mode | Mechanism | Governor Analog |
|-------------|-----------|-----------------|
| **Silent rot** | Referenced artifacts change; doc doesn't | Fact decay without revalidation |
| **Authority laundering** | Wiki page treated as policy without evidence | Provenance laundering (claim_diff) |
| **Commitment shear** | Summary drops edge cases and prohibitions | Representational invariance (Paper 11) |
| **Orphan authority** | Doc claims authority over systems it's not connected to | Claims without evidence |
| **Zombie docs** | Outdated doc cited as current truth | Stale facts without TTL |

These are the same failure modes the governor detects in agent claims — just slower and quieter.

### 1.2 Why Existing Tools Don't Help

- **Confluence / wikis**: No staleness detection, no authority scoping, no commitment tracking. Pages accumulate forever.
- **Static site generators**: Render markdown, don't validate claims. Dead links are the only failure they catch.
- **Obsidian / Logseq**: Graph structure helps with linking, but has no concept of authority scope, commitment preservation, or temporal validity.
- **Linters / vale**: Check prose style, not semantic obligations. "Use active voice" doesn't catch "this doc dropped a safety constraint."

---

## 2. The Solution

### 2.1 Doc Registration

Documents become governed artifacts by registration:

```bash
# Register a doc with scope and authority level
governor doc register runbook/deploy-v2.md \
  --scope procedural \
  --links src/deploy/ panel:grafana/deploy \
  --ttl 90d

# Register an authoritative doc (higher scrutiny)
governor doc register architecture/auth-design.md \
  --scope authoritative \
  --links src/auth/ decisions:auth \
  --ttl 180d
```

```python
@dataclass
class GovDoc:
    """A governed document artifact."""
    doc_id: str              # Content-addressed
    path: str                # File path
    scope: DocScope          # What this doc is allowed to do
    links: list[DocLink]     # Live artifacts this doc connects to
    ttl: timedelta | None    # How long before staleness check
    registered_at: datetime
    last_verified: datetime
    status: DocStatus        # CURRENT, STALE, HISTORICAL, UNSAFE

class DocScope(Enum):
    DESCRIPTIVE = "descriptive"       # "What exists" — no authority claims
    PROCEDURAL = "procedural"         # "How to do X" — linked to execution
    AUTHORITATIVE = "authoritative"   # "You must / you must not" — requires evidence

class DocStatus(Enum):
    CURRENT = "current"       # Verified within TTL, links valid
    STALE = "stale"           # TTL expired or linked artifacts changed
    HISTORICAL = "historical" # Explicitly demoted, kept for reference
    UNSAFE = "unsafe"         # Authoritative doc with broken links or dropped commitments
```

### 2.2 Authority Scope Enforcement

Docs declare what they're allowed to assert:

| Scope | Allowed Assertions | Governor Check |
|-------|-------------------|---------------|
| **Descriptive** | Facts about current state ("service X runs on port 8080") | No MUST/SHALL/NEVER/REQUIRED language |
| **Procedural** | Steps to follow ("run deploy.sh, then verify health check") | Must link to at least one executable artifact |
| **Authoritative** | Obligations ("you MUST rotate keys every 90 days") | MUST/MUST_NOT claims must map to anchors, invariants, or decisions |

When a doc uses authority language (MUST, SHALL, NEVER, REQUIRED) without being scoped as `authoritative`:

```bash
$ governor doc check runbook/deploy-v2.md

WARN: Authority language in non-authoritative doc:
  Line 42: "You MUST restart the service after deploy"
  Doc scope: procedural (authority claims not permitted)
  Action: Upgrade scope to authoritative, or rephrase as guidance
```

When an authoritative doc makes claims that don't map to live constraints:

```bash
$ governor doc check architecture/auth-design.md

ERROR: Ungrounded authority claim:
  Line 18: "Authentication MUST use JWT"
  No matching decision in ledger (topic: auth)
  No matching anchor (type: requirement)
  Action: Record decision via 'governor decide', or downgrade to descriptive
```

### 2.3 Execution Adjacency

Docs that aren't connected to live artifacts rot first. Every registered doc must declare links:

```python
@dataclass
class DocLink:
    """Connection between a doc and a live artifact."""
    kind: LinkKind
    target: str            # Path, URL, panel ID, script, test, etc.
    description: str | None

class LinkKind(Enum):
    CODE = "code"          # Source file or directory
    SCRIPT = "script"      # Executable automation
    TEST = "test"          # Test file or command
    PANEL = "panel"        # Dashboard / monitoring panel
    DECISION = "decision"  # Decision ledger entry
    ANCHOR = "anchor"      # Continuity anchor
    RUNBOOK = "runbook"    # Another governed doc
```

**Adjacency rules:**
- `procedural` docs must link to at least one CODE, SCRIPT, or TEST artifact
- `authoritative` docs must link to at least one DECISION or ANCHOR
- `descriptive` docs may have zero links (reference-only, explicitly non-authoritative)
- Docs with zero links cannot be cited as authority in governor decisions

### 2.4 Temporal Validity (Staleness Detection)

Docs don't expire — their assumptions do. The governor tracks drift between doc claims and system state:

```python
def check_staleness(doc: GovDoc) -> StalenessReport:
    """Check if a doc's claims still hold."""
    # 1. TTL check: has the doc exceeded its revalidation window?
    # 2. Link check: have linked artifacts changed since last verification?
    # 3. Decision check: have referenced decisions been retracted/superseded?
    # 4. Anchor check: have referenced anchors changed?
```

When drift exceeds threshold:

```bash
$ governor doc status

architecture/auth-design.md  [STALE]
  TTL: expired 23 days ago
  Links: src/auth/login.py changed (14 commits since last verification)
  Decision: "JWT auth" still active
  Action: Re-verify or demote to historical

runbook/deploy-v2.md  [CURRENT]
  TTL: 47 days remaining
  Links: all valid, no changes since last verification
```

**Demotion cascade:**
- STALE docs are flagged but still visible
- After 2x TTL without re-verification: auto-demote to HISTORICAL
- HISTORICAL docs get a banner: "This document has not been verified against current system state"
- Authoritative docs that go STALE become UNSAFE until re-verified (authority claims from stale docs are dangerous)

### 2.5 Commitment Preservation on Generation

When docs are generated or regenerated (by AI or by tooling), the `CommitmentTransportValidator` (COMMITMENT_TRANSPORT_SPEC.md) checks that obligations survive:

```bash
# Check a regenerated doc against its source material
governor doc transport --source src/auth/ --doc architecture/auth-design.md

TRANSPORT REPORT:
  Commitments extracted from source: 12
  PRESERVED: 9
  WEAKENED: 1 (MUST → SHOULD on key rotation)
  DROPPED: 2 (error handling constraint, rate limit requirement)
  CONTRADICTED: 0

  Shear: 0.21 (WARN)
  Hard shear: 0.08 (PASS — no MUST-level drops)
```

This is the integration point with Paper 11. Generated docs that drop hard constraints are blocked.

---

## 3. Doc-as-Artifact (Receipt Production)

Registered docs emit artifacts the governor can reason about:

```python
@dataclass
class DocReceipt:
    """Verification receipt for a governed document."""
    doc_id: str
    verified_at: datetime
    status: DocStatus
    commitments_extracted: int
    links_valid: int
    links_broken: int
    authority_claims: int
    grounded_claims: int       # Claims that map to decisions/anchors
    ungrounded_claims: int     # Claims without backing
    content_hash: str
```

This means when someone says "but the docs say—", the governor can answer:

> "That document is non-authoritative, last verified 18 months ago, has 3 broken links, and drops 2 hard invariants from the source material."

---

## 4. CLI Surface

```bash
# Registration
governor doc register <path> --scope <scope> --links <targets> --ttl <duration>
governor doc unregister <path>
governor doc list                    # List registered docs with status

# Checking
governor doc check <path>           # Authority + adjacency + staleness check
governor doc check --all             # Check all registered docs
governor doc transport --source <path> --doc <path>  # Commitment transport

# Status
governor doc status                  # Summary: current/stale/historical/unsafe counts
governor doc status <path>           # Detailed status for one doc
governor doc stale                   # List stale and unsafe docs

# Maintenance
governor doc verify <path>           # Mark as re-verified (resets TTL)
governor doc demote <path>           # Manually demote to historical
governor doc promote <path>          # Promote historical back to current (requires re-check)
```

---

## 5. Export / Integration Hooks

The governor doesn't render docs — it governs them. Rendering and distribution is handled by external tools via export hooks:

### 5.1 Obsidian / Logseq

```bash
# Export governed doc metadata as frontmatter
governor doc export --format obsidian --output vault/
```

Injects YAML frontmatter into markdown files:

```yaml
---
gov_scope: authoritative
gov_status: current
gov_verified: 2025-06-01
gov_ttl: 180d
gov_links:
  - code: src/auth/
  - decision: auth:jwt
gov_commitments: 12
gov_ungrounded: 0
---
```

Obsidian/Logseq can then filter, query, and visualize governance metadata as part of their graph.

### 5.2 Static Site Generators

```bash
# Export as JSON sidecar (for Hugo, MkDocs, etc.)
governor doc export --format json --output docs/_governance/
```

Each doc gets a `<filename>.governance.json` sidecar that build scripts can use to inject banners, badges, or warnings.

### 5.3 Git Hook Integration

```bash
# Pre-commit: check that modified docs still pass governance
governor doc check --staged
```

If a committed doc change introduces ungrounded authority claims or breaks execution adjacency, the pre-commit hook flags it.

---

## 6. Design Constraints

1. **Governor doesn't write docs.** It constrains what they can claim. Authoring is human/agent work; governance is structural.
2. **Registration is opt-in.** Unregistered docs are ungoverned. This is intentional — not every text file needs governance. Only docs that claim authority or encode procedure.
3. **Staleness is physics, not shame.** Docs go STALE because linked artifacts changed, not because someone forgot to update them. The language is "unverified," not "outdated."
4. **Authority requires grounding.** MUST/SHALL/NEVER in docs must map to live constraints. This prevents "wiki as law" — authority claims without enforcement backing are just opinions.
5. **Tool-agnostic.** The governor stores governance metadata; rendering/distribution is handled by export hooks to whatever tool the user prefers.

---

## 7. Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `COMMITMENT_TRANSPORT_SPEC.md` | Generated docs validated for commitment preservation |
| `SLIM_MODE_SPEC.md` | `governor doc check` works in slim mode; `governor doc register` is a one-liner |
| `CONSTRAINT_COMPILER_SPEC.md` | Doc authority claims become compilable constraints |
| `CLI_CHAT_SPEC.md` | `governor chat` responses that reference docs can cite governance status |
| `GIT_GOVERNANCE_SPEC.md` | Doc checks integrate with git pre-commit |

---

## 8. Open Questions

1. **Auto-registration.** Should `governor doc scan` auto-detect docs in a repo and suggest registration? Risk: noise. Could limit to files with MUST/SHALL/NEVER language (authority signal detection via `claim_signals.py`).

2. **Cross-doc links.** When doc A cites doc B, and doc B goes STALE, should doc A inherit a staleness warning? This creates a graph propagation problem. Candidate: one-hop propagation only (direct citations), not transitive.

3. **Versioned docs.** Should governance track doc versions (git history) or only current state? Version tracking enables "when did this doc's claims last match reality?" but adds storage/complexity.

4. **Living docs (auto-regeneration).** Some docs should regenerate from source (API docs from code, runbook from automation). Should the governor trigger regeneration when linked artifacts change, or just flag staleness? Candidate: flag only — regeneration is the author's job.
