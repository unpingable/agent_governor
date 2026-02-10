# Agent Governor 2.0 — Instrumented Execution Specification

## Version 0.1 — Append-Only Evidence System

```yaml
status: implemented
implemented: true
depends_on:
  - claims.py
  - receipts.py
  - epistemic.py
  - interferometry.py
  - telemetry.py
  - claim_diff.py
blocking:
  - Cross-model comparison workflows
  - Forensic audit trails
  - CI/CD evidence gating
estimated_scope: large
```

---

## Executive Summary

AG2 is an instrumented execution + evidence system for AI-assisted work. It records runs as replayable event streams, extracts structured claims with evidence pointers, compares claim-sets across models and time, and renders falsifiable reports.

**Design Principle**: Constraints are the product. Profile is a UX dial, not an escape hatch.

---

## 1. System Invariants (Non-Negotiable)

```yaml
invariants:
  I0_append_only_events: Events MUST be immutable once written.
  I1_content_addressed_artifacts: Artifacts stored by hash; receipts include hash + size + mime.
  I2_replayable: Run contains enough provenance to replay under best-effort conditions.
  I3_no_naked_conclusions: Reports MUST NOT assert findings without evidence_refs.
  I4_profiles_do_not_disable_anchors: Repo anchors ALWAYS win; profile only changes severity.
  I5_no_orphan_claims: Every claim links to event/artifact, or is explicitly hypothesis.
  I6_hints_cannot_create_evidence: Model hints can only SELECT from captured receipts.
```

---

## 2. On-Disk Layout

```
.agent_gov/
├── store/                     # content-addressed blobs
│   └── sha256/ab/cd/<hash>
├── runs/<run_id>/
│   ├── manifest.json
│   ├── events.jsonl
│   ├── receipts.jsonl
│   ├── claims.jsonl
│   └── reports/
│       ├── report.json
│       └── report.md
```

---

## 3. Run Manifest

```python
@dataclass
class RunManifest:
    run_id: str                    # uuidv7
    created_at: datetime
    actor: Actor                   # human | agent | pipeline
    environment: Environment       # os, hostname, cwd, timezone
    repo: RepoState               # url, git_sha, dirty, branch
    config: RunConfig             # profile, anchors_hash, toolchain_versions
    inputs: RunInputs             # task_id, prompt_hash, seed
    models: list[ModelSpec]       # name, provider, version, parameters_hash
```

---

## 4. Event Model

Events are append-only JSONL.

```python
class EventKind(str, Enum):
    PROMPT_SENT = "prompt_sent"
    MODEL_OUTPUT = "model_output"
    TOOL_INVOCATION = "tool_invocation"
    TOOL_RESULT = "tool_result"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    GIT_DIFF = "git_diff"
    COMMAND_EXEC = "command_exec"
    TEST_RUN = "test_run"
    LINTER_RUN = "linter_run"
    POLICY_DECISION = "policy_decision"
    ERROR = "error"

@dataclass
class Event:
    event_id: str
    ts: datetime
    run_id: str
    kind: EventKind
    actor: Actor
    parent_event_id: str | None
    payload: dict
    receipt_refs: list[str]
```

**Receipt emission rules:**
- Payload > 4KB → store as artifact + receipt
- Tool stdout/stderr → MUST be artifact
- file_write → MUST include before/after or patch receipt

---

## 5. Claim Schema

```python
class ClaimModality(str, Enum):
    ASSERT = "assert"       # evidence required
    INFER = "infer"         # derived from other claims
    PLAN = "plan"           # future intent
    HYPOTHESIS = "hypothesis"  # notes required, evidence optional

class ClaimType(str, Enum):
    ACTION_PERFORMED = "action_performed"
    FILE_CHANGED = "file_changed"
    TEST_RESULT = "test_result"
    LINTER_RESULT = "linter_result"
    BUILD_RESULT = "build_result"
    INVARIANT_SATISFIED = "invariant_satisfied"
    INVARIANT_VIOLATED = "invariant_violated"
    COMPLETION_CLAIM = "completion_claim"

@dataclass
class AG2Claim:
    claim_id: str
    ts: datetime
    run_id: str
    source: ClaimSource          # kind, event_id, model
    modality: ClaimModality
    type: ClaimType
    subject: str                 # normalized entity
    predicate: str               # small vocab: changed, passed, failed, exists
    object: str | None           # hash, status, rule id
    scope: ClaimScope            # repo_sha, path, symbol, command
    evidence_refs: list[str]     # receipt_ids
    confidence: float | None
    notes: str | None
```

**Hard rules:**
- `modality=ASSERT` MUST have `evidence_refs` (≥1)
- `modality=HYPOTHESIS` MAY omit evidence but MUST have notes
- `COMPLETION_CLAIM` MUST be backed by test_result or explicit waiver

---

## 6. Tool Parsers

```python
class ToolParser(Protocol):
    def parse(self, receipts: list[Receipt], exit_code: int) -> list[AG2Claim]: ...

# Required parsers:
# - PytestParser: test_result claims from pytest output
# - MypyParser: linter_result claims from mypy output
# - RuffParser: linter_result claims from ruff output
```

Minimal requirement: overall pass/fail + evidence pointer.

---

## 7. Model Output Contract

Models emit structured claim blocks:

```yaml
AG2_CLAIMS:
  - type: action_performed
    subject: repo
    predicate: modified
    object: "patch"
    scope: {path: "src/foo.py"}
    evidence_hint: "see git diff"
```

Parser maps `evidence_hint` to receipts from nearby events. Hints cannot create evidence.

---

## 8. Claim Diff

```python
class DiffFinding(str, Enum):
    CONTRADICTION = "contradiction"          # same key, opposing predicate
    MISSING_EVIDENCE = "missing_evidence"    # assert without evidence_refs
    PHANTOM_ACTION = "phantom_action"        # claims action, no receipt
    UNSUPPORTED_SUCCESS = "unsupported_success"  # completion without test
    DRIFT = "drift"                          # invariant flip across runs

@dataclass
class ClaimDiffResult:
    left_run_id: str
    right_run_id: str
    findings: list[DiffFinding]
    match_key: tuple[str, ...]  # (type, subject, predicate, scope.path, scope.symbol)
```

---

## 9. Reports

```python
@dataclass
class AG2Report:
    report_id: str
    run_ids: list[str]
    generated_at: datetime
    findings: list[Finding]      # kind, severity, claim_refs, evidence_refs, summary
    invariants_satisfied: list[str]
    invariants_violated: list[str]
    provenance: ReportProvenance  # spec_version, generator_version
```

Markdown is a VIEW of JSON, never separate truth.

---

## 10. Waivers

```python
@dataclass
class Waiver:
    waiver_id: str
    rule_id: str
    scope: str                   # path glob or symbol
    reason: str                  # required
    expires: datetime
    created_by: str
    created_at: datetime
```

Waivers become receipts. The system keeps a ledger of "we chose risk."

---

## 11. Profiles and Views

**Profiles** = enforcement behavior (what blocks):
- `greenfield`: system invariants block, findings warn
- `strict`: findings block
- `forensic`: capture only, no gating

**Views** = presentation (what shows):
- `exec`: verdict + blockers only
- `dev`: blockers + actionable warns + code pointers
- `forensic`: full timeline + receipts

---

## 12. CLI

```bash
ag2 run                              # Start instrumented run
ag2 status                           # Verdict + blockers only
ag2 verify <run_id>                  # Check hashes, refs, invariants
ag2 extract-claims <run_id>          # Run parsers + model block extraction
ag2 diff --left <id> --right <id>    # Emit diff JSON
ag2 report --diff <diff.json>        # Emit report JSON + MD
ag2 replay <run_id>                  # Best-effort replay
ag2 waiver create --rule <id> --scope <glob> --reason "..."
ag2 waiver list
```

---

## 13. Acceptance Criteria

```yaml
v0_capture:
  - run manifest + events + receipts + hash store
  - ag2 verify passes

v0_claims:
  - pytest/mypy/ruff parsers emit claims with evidence
  - no_orphan_claims enforced

v0_diff:
  - contradictions + unsupported_success + phantom_action implemented

v0_report:
  - report.json + report.md generated deterministically

v0_qa:
  - T0_min_run, T1_pytest_pass, T2_phantom_action, T3_unsupported_success, T4_cross_model_contradiction automated
```

---

## 14. Reuse from v1.0

| v1.0 Module | AG2 Usage |
|-------------|-----------|
| receipts.py | Receipt dataclasses, hash computation |
| epistemic.py | Evidence references, confidence model |
| claim_diff.py | Diff logic, match keys |
| interferometry.py | Cross-model comparison harness |
| telemetry.py | JSONL event logging, structured output |
| check.py | Finding aggregation |
| profiles.py | Profile switching |

---

## 15. Open Questions

1. **Subruns**: Separate runs per model, or nested under parent?
2. **Retention**: When do runs age out? Do claims survive blob cleanup?
3. **Streaming**: Real-time event emission vs batch?

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec from agentv2.md |
