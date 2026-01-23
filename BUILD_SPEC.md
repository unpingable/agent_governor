# Agent Governor: Build Spec v2

## The One Rule That Makes This Real

**Any file mutation must be associated with a validated changeset receipt.**

If you don't enforce this, the tool is advisory. Advisory gets ignored.

---

## Architecture: Gate, Not Memory

```
┌─────────────────┐
│  Coding Agent   │  produces patches + pointers
└────────┬────────┘
         │ governor propose <patch>
         ▼
┌─────────────────┐
│    GOVERNOR     │  THE CHOKE POINT
│  ┌───────────┐  │
│  │ Verifiers │──┼──→ runs checks, produces receipts
│  └───────────┘  │
│  ┌───────────┐  │
│  │  Ledgers  │──┼──→ facts/ + decisions/
│  └───────────┘  │
│  ┌───────────┐  │
│  │    FSM    │──┼──→ DRAFT→PROPOSE→VERIFY→APPLY
│  └───────────┘  │
└────────┬────────┘
         │ governor apply (ONLY if verified)
         ▼
┌─────────────────┐
│   Working Tree  │  actual file writes happen here
└─────────────────┘
```

Key insight: **Agent provides pointers. Governor produces receipts.**

---

## Receipt Types (Governor-Produced)

These are the only valid evidence. Agent cannot produce these directly.

```python
@dataclass
class FileSnapshot:
    """Receipt proving file state at verification time."""
    path: str
    blob_hash: str  # SHA256 of content
    size_bytes: int
    excerpt_spans: list[tuple[int, int]] | None  # line ranges if relevant
    timestamp: datetime
    
@dataclass  
class CmdRun:
    """Receipt proving command execution."""
    command: list[str]
    exit_code: int
    stdout_hash: str
    stderr_hash: str
    cwd: str
    duration_ms: int
    timestamp: datetime

@dataclass
class DiffReceipt:
    """Receipt proving changeset content."""
    paths_touched: list[str]
    unified_diff_hash: str
    base_tree_hash: str  # git tree hash before patch
    additions: int
    deletions: int
    timestamp: datetime
```

---

## Claim Types (Structured, Not Free-Form)

Stop letting agents make prose assertions. Define the vocabulary:

```python
class ClaimType(Enum):
    FILE_EXISTS = "file_exists"           # path exists
    SYMBOL_DEFINED = "symbol_defined"     # symbol at path:span
    API_SURFACE = "api_surface"           # endpoint/signature at location
    TESTS_PASS = "tests_pass"             # command exits 0
    DECISION = "decision"                 # normative choice (framework, style)
    CHANGESET = "changeset"               # proposed file mutations

@dataclass
class Claim:
    type: ClaimType
    # Type-specific payload:
    path: str | None = None
    symbol: str | None = None
    span: tuple[int, int] | None = None
    command: list[str] | None = None
    topic: str | None = None
    choice: str | None = None
    diff: str | None = None
```

---

## Two Ledgers, Not One

### `facts/` - Empirical, Decays
- Verified state assertions backed by receipts
- **Automatically invalidated** when referenced files change
- Examples: "tests pass", "file X contains symbol Y", "API endpoint exists"

### `decisions/` - Normative, Persists  
- Policy choices that require explicit revision
- **Never auto-invalidated** - must be superseded deliberately
- Examples: "we use React", "REST not GraphQL", "tabs not spaces"

```
.governor/
├── facts/
│   ├── index.json        # active facts with receipt refs
│   └── receipts/         # actual receipt objects
├── decisions/
│   └── index.json        # active decisions with provenance
├── rejections.log        # NOT git-tracked, local debugging only
└── config.toml           # test commands, envelope settings
```

---

## FSM States (Required, Not Roadmap)

```
DRAFT ──propose──→ PROPOSED ──verify──→ VERIFIED ──apply──→ APPLIED
  ↑                    │                    │
  │                    │ reject             │ conflict
  └────────────────────┴────────────────────┘
```

- **DRAFT**: Agent speculation. Nothing persistent. Expires.
- **PROPOSED**: Structured claims + pointers submitted. Waiting for verification.
- **VERIFIED**: Governor has run checks and produced receipts. Ready to apply.
- **APPLIED**: Patch written to working tree. Facts/decisions updated.

Rejection always returns to DRAFT with structured feedback.

---

## CLI Interface (The Gate)

```bash
# Initialize governor in repo
governor init

# Agent submits a patch with claims
governor propose \
  --patch changes.patch \
  --claim "type=tests_pass,command=pytest -q" \
  --claim "type=decision,topic=framework,choice=react"

# Governor verifies (runs checks, produces receipts)
governor verify <proposal-id>

# If verified, apply the patch
governor apply <proposal-id>

# Query current state
governor facts [--topic api]
governor decisions [--topic framework]

# Show rejection history (local only)
governor rejections [--limit 20]
```

---

## Build Steps (For Claude Code / Codex)

Each step has a testable artifact. Do them in order.

### Phase 1: The Gate (Weekend MVP)

**Step 1: Receipt objects**
- Implement `FileSnapshot`, `CmdRun`, `DiffReceipt` dataclasses
- Test: Create each receipt type, serialize to JSON, deserialize
- Artifact: `src/governor/receipts.py`

**Step 2: Receipt producers**  
- `produce_file_snapshot(path) -> FileSnapshot`
- `produce_cmd_run(command, cwd) -> CmdRun`
- `produce_diff_receipt(patch_text, repo_root) -> DiffReceipt`
- Test: Each producer creates valid receipt from real inputs
- Artifact: `src/governor/producers.py`

**Step 3: Typed claims**
- Implement `ClaimType` enum and `Claim` dataclass
- Validation: claim type requires specific fields
- Test: Valid claims parse, invalid claims raise
- Artifact: `src/governor/claims.py`

**Step 4: Split ledgers**
- `FactLedger`: stores facts + receipt references
- `DecisionLedger`: stores decisions + provenance
- Test: Add fact, query fact, invalidate fact when file changes
- Artifact: `src/governor/ledgers.py`

**Step 5: FSM**
- States: DRAFT, PROPOSED, VERIFIED, APPLIED
- Transitions with guards (can't apply unverified)
- Test: State machine rejects invalid transitions
- Artifact: `src/governor/fsm.py`

**Step 6: Verifiers**
- `FileVerifier`: produces FileSnapshot if file exists
- `TestVerifier`: produces CmdRun if tests pass
- `DiffVerifier`: produces DiffReceipt, checks conflicts
- Test: Each verifier produces receipt or rejects
- Artifact: `src/governor/verifiers.py`

**Step 7: CLI skeleton**
- `governor init` - creates `.governor/`
- `governor propose --patch <file> --claim <...>` - parses, stores proposal
- `governor verify <id>` - runs verifiers, produces receipts
- `governor apply <id>` - applies patch if verified
- Test: Full flow from propose → verify → apply
- Artifact: `src/governor/cli.py`

### Phase 2: Production Hardening

**Step 8: Fact decay**
- Watch for file changes (git diff or inotify)
- Auto-invalidate facts when referenced files change
- Test: Change file, fact becomes invalid

**Step 9: Conflict detection**
- Key-value conflicts only (framework=react vs framework=vue)
- No embedding magic yet
- Test: Conflicting decision is rejected

**Step 10: Operating envelopes**
- `exploratory`: hypotheses allowed, don't commit to decisions
- `strict`: all claims require receipts
- Test: Same proposal accepted in exploratory, rejected in strict

**Step 11: Structured rejection feedback**
- Return machine-readable rejection: `{missing: [receipt_type], conflict: [decision_id]}`
- Agent can parse and retry
- Test: Rejection message contains actionable info

### Phase 3: Integration

**Step 12: Git hooks**
- pre-commit hook that requires governor approval
- Test: Commit without approval fails

**Step 13: Agent wrapper**
- Wrapper that intercepts agent file writes
- Routes through governor automatically
- Test: Agent write without proposal is blocked

**Step 14: MCP server**
- Expose governor as MCP tool
- Test: Claude can call governor through MCP

---

## Config File

```toml
# .governor/config.toml

[test]
command = ["pytest", "-q"]
timeout_seconds = 300

[envelopes]
default = "strict"

[envelopes.exploratory]
require_receipts = false
decisions_commit = false

[envelopes.strict]  
require_receipts = true
decisions_commit = true

[decay]
check_on_verify = true
```

---

## What This Prevents

| Failure Mode | How Governor Stops It |
|--------------|----------------------|
| "API exists" (hallucinated) | FileVerifier rejects - no receipt |
| "Tests pass" (lying) | TestVerifier runs tests, checks exit code |
| Agent contradicts past decision | DecisionLedger conflict detection |
| Agent drifts across sessions | Decisions persist, queried on startup |
| Silent edits without review | Gate: no writes without verified proposal |
| Stale facts used as evidence | Fact decay when files change |

---

## Success Metric

Run Claude Code on a real project with governor enabled. Count:
- Proposals rejected for missing receipts
- Proposals rejected for conflicts  
- Proposals that would have introduced bugs but didn't land

If the rejection count is > 0 and the bug count is < baseline, it's working.

---

## License

Apache-2.0
