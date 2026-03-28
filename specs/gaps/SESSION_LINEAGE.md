## MAUDE_GAP_SESSION_BRANCH_PROMOTION_001

**Title:** Session lineage and branch promotion
**Status:** Gap spec
**Scope:** Maude / supervisor layer
**Out of scope:** Governor core, except optional policy vocabulary and receipts for governed promotion actions

### Problem

Maude needs a way to preserve useful work from exploratory branches without pretending divergent conversational histories are one coherent session.

Users will fork work for reasons like:

* trying alternate implementation paths
* testing different prompts/models
* isolating risky edits
* exploring a diagnosis without polluting the parent thread

Today, the "return path" from child branch to parent is manual and lossy. The operator has to read the child session, remember what mattered, and reintroduce it into the parent by hand. That is annoying, error-prone, and exactly the sort of thing machines are good at making less stupid.

What Maude needs is **structured promotion**, not transcript merge.

---

## Thesis

A child session should be able to propose **promotable artifacts** back into its parent. The parent may selectively adopt those artifacts. Raw transcript splicing is forbidden.

---

## Goals

1. Represent session lineage as a DAG.
2. Allow child sessions to produce structured promotion candidates.
3. Allow parent sessions to selectively adopt:

   * summaries
   * facts
   * decisions
   * todos
   * code diffs
   * test results
   * other typed artifacts
4. Emit auditable promotion receipts.
5. Keep conversation history honest. No fake chronology.
6. Align session branching with git/worktree branching where possible.

---

## Non-goals

1. **No transcript merge.**
   We are not interleaving two raw chat histories and calling that "merged."

2. **No shared mutable session state.**
   Child sessions do not silently mutate parent state.

3. **No permission inheritance from child to parent.**
   A child discovering or receiving permission does not grant that permission upstream.

4. **No governor-native session ontology.**
   Governor may govern promotion actions, but session lineage belongs in Maude.

5. **No automatic code application by default.**
   Promotion may include a diff artifact, but adoption of code remains explicit.

---

## Why this belongs in Maude, not Governor

This is workflow semantics, not enforcement semantics.

Governor should answer questions like:

* is this promotion action allowed?
* does this scope require confirmation?
* what receipt should be emitted?

Maude should answer questions like:

* what is the parent/child relationship?
* what artifacts did this branch produce?
* what should be adopted?
* how should imported state be rendered?

If this goes into Governor proper, the kernel starts learning chat/workbench ontology. That road ends in bloated nonsense.

---

## Terms

### Session

A single conversational/workflow branch with its own transcript, derived state, workspace mapping, and governance context.

### Root session

The topmost ancestor in a lineage tree.

### Child session

A session forked from another session at a specific event boundary.

### Promotion candidate

A typed bundle of artifacts proposed by a source session for adoption into a target session.

### Promotion

The act of importing selected artifacts from a child into a parent.

### Synthetic checkpoint

A single parent-session message/event recording what was imported from a child.

---

## Requirements

### Functional requirements

#### R1. Session DAG

Maude SHALL model session lineage as a DAG with:

* `session_id`
* `root_session_id`
* `parent_session_id`
* `forked_from_event_id`
* `workspace_ref`
* `summary_head_id`
* `policy_context_id`

#### R2. Typed promotable artifacts

A child session SHALL be able to produce promotion candidates containing zero or more of:

* summary
* facts
* decisions
* todos
* diff references
* test results
* attachments/artifacts

#### R3. Explicit promotion scope

Each promotion candidate SHALL declare its scope explicitly.

Allowed scopes:

* `summary`
* `facts`
* `decisions`
* `todos`
* `diff`
* `test_results`
* `artifacts`

Disallowed by default:

* `raw_transcript`
* `permissions`
* implicit memory transfer
* hidden model-internal reasoning state

#### R4. Selective adoption

The parent SHALL be able to adopt only a subset of a candidate's artifacts.

#### R5. Promotion receipt

Every accepted or partially accepted promotion SHALL emit a receipt describing:

* source session
* target session
* requested scope
* applied scope
* imported artifacts
* rejected artifacts
* conflicts
* actor
* timestamp
* hash chain linkage where applicable

#### R6. Synthetic checkpoint

A successful promotion SHALL create a synthetic checkpoint event in the target session summarizing imported artifacts.

#### R7. Conflict surfacing

Maude SHALL detect and surface typed conflicts where possible.

#### R8. Workspace awareness

If the session is associated with git, Maude SHOULD align child sessions with worktrees or branches and SHOULD record diff provenance against a concrete base.

---

## Invariants

### I1. Transcript immutability

Raw transcript history is append-only and session-local.

### I2. No fake chronology

Promoted artifacts must appear in the parent as an imported checkpoint, not as backfilled messages.

### I3. Parent authority

Child sessions may propose. Parent sessions decide.

### I4. Explicit scope or nothing

No silent artifact transfer.

### I5. Permissions do not flow upstream

Governance state is not imported through promotion unless explicitly designed later, and even then should probably be viewed with suspicion.

### I6. Promotion is reviewable

Any artifact capable of mutating code or accepted state must be reviewable before adoption.

---

## Data model sketch

### Session

```json
{
  "session_id": "sess_01H...",
  "root_session_id": "sess_root",
  "parent_session_id": "sess_parent",
  "forked_from_event_id": "evt_01H...",
  "title": "investigate patch drift",
  "created_at": "2026-03-27T22:11:00Z",
  "model": "local|codex|claude-code",
  "workspace_ref": {
    "repo_id": "repo_01",
    "worktree_path": "/repo/.worktrees/patch-drift-a",
    "git_branch": "maude/patch-drift-a"
  },
  "policy_context_id": "pol_01",
  "summary_head_id": "sum_01",
  "status": "active"
}
```

### Fact

```json
{
  "fact_id": "fact_01",
  "text": "CRLF normalization affects hunk matching",
  "evidence_refs": ["toolrun_14", "diff_02"],
  "status": "proposed"
}
```

### Decision

```json
{
  "decision_id": "dec_01",
  "text": "Normalize lines before matching, preserve original line endings on write",
  "rationale": "improves matching without altering file semantics",
  "status": "proposed"
}
```

### Promotion candidate

```json
{
  "candidate_id": "promocand_01",
  "source_session_id": "sess_child",
  "target_session_id": "sess_parent",
  "created_at": "2026-03-27T22:18:00Z",
  "scope": {
    "summary": true,
    "facts": true,
    "decisions": true,
    "todos": false,
    "diff": true,
    "test_results": true,
    "raw_transcript": false,
    "permissions": false
  },
  "artifacts": {
    "summary_id": "sum_09",
    "fact_ids": ["fact_01"],
    "decision_ids": ["dec_01"],
    "diff_ref": "git:abc123..def456",
    "test_run_ids": ["testrun_07"]
  },
  "conflicts": [],
  "status": "draft"
}
```

### Promotion receipt

```json
{
  "receipt_type": "session_promotion",
  "receipt_id": "rcpt_01",
  "timestamp": "2026-03-27T22:20:00Z",
  "source_session_id": "sess_child",
  "target_session_id": "sess_parent",
  "candidate_id": "promocand_01",
  "requested_scope": {
    "summary": true,
    "facts": true,
    "decisions": true,
    "diff": true,
    "test_results": true
  },
  "applied_scope": {
    "summary": true,
    "facts": true,
    "decisions": false,
    "diff": true,
    "test_results": true
  },
  "imported_artifacts": [
    {"type": "summary", "id": "sum_09"},
    {"type": "fact", "id": "fact_01"},
    {"type": "diff", "id": "git:abc123..def456"},
    {"type": "test_results", "id": "testrun_07"}
  ],
  "rejected_artifacts": [
    {"type": "decision", "id": "dec_01", "reason": "conflicts with accepted parent decision"}
  ],
  "conflicts": [],
  "actor": "user",
  "hash_prev": "..."
}
```

---

## Conflict model

Conflicts should be typed.

### Conflict kinds

* `fact_conflict`
* `decision_conflict`
* `artifact_conflict`
* `workspace_conflict`
* `staleness_conflict`
* `policy_conflict`

### Example

```json
{
  "conflict_id": "conf_01",
  "kind": "decision_conflict",
  "source_ref": "dec_child_03",
  "target_ref": "dec_parent_09",
  "reason": "child recommends sqlite cache; parent accepted in-memory only for current scope",
  "severity": "warn"
}
```

Not every conflict blocks. Some just need to be visible so reality can continue to exist.

---

## UX / command surface

### Forking

* `/fork`
* `/fork --title "try fuzzy hunk matching"`
* `/fork --worktree`

### Inspection

* `/lineage`
* `/compare <session-a> <session-b>`
* `/show-promotions`
* `/show-conflicts`

### Promotion

* `/promote <child-session>`
* `/promote <child-session> --scope summary,facts,decisions`
* `/promote <child-session> --summary-only`
* `/promote <child-session> --diff-only`

### Selective adoption

* `/adopt fact <fact-id>`
* `/adopt decision <decision-id>`
* `/adopt diff <diff-ref>`
* `/reject fact <fact-id>`
* `/supersede decision <old-id> --with <new-id>`

Avoid `/merge-session`. That phrase invites the wrong mental model.

---

## Parent checkpoint rendering

On promotion, Maude SHALL create a synthetic checkpoint message in the parent session, for example:

```markdown
Imported from child session `patch-drift-a`

Summary:
- Child branch identified CRLF normalization as a contributor to patch mismatch.
- Candidate fix passed 12 regression tests.

Imported artifacts:
- summary `sum_09`
- fact `fact_01`
- diff `git:abc123..def456`
- test run `testrun_07`

Rejected artifacts:
- decision `dec_01` (conflicts with accepted parent decision)

Open conflicts:
- sibling branch `patch-drift-b` recommends fuzzy scoring instead
```

This preserves continuity without falsifying history.

---

## Policy / Governor integration

This feature does not belong in Governor proper, but promotion actions may be governed.

Optional policy vocabulary:

* `session.promote.summary`
* `session.promote.facts`
* `session.promote.decisions`
* `session.promote.todos`
* `session.promote.diff`
* `session.promote.test_results`
* `session.promote.artifacts`

Suggested posture:

* summary/facts/todos: low risk
* decisions: medium risk
* diff: high risk
* anything auto-applying changes: higher risk, likely confirmation-gated

Governor's job here is to decide whether promotion actions are allowed and to emit receipts. Maude owns the lineage model.

---

## Minimal vertical slice

### Phase 1

1. Fork session with parent/child linkage.
2. Associate child with optional worktree.
3. Produce promotion candidate containing:

   * summary
   * facts
   * decisions
   * diff ref
   * test result ref
4. Review candidate in parent.
5. Accept full or partial scope.
6. Emit receipt.
7. Add synthetic checkpoint to parent.

### Phase 2

1. Typed conflict detection.
2. Session comparison view.
3. Supersede/reject semantics.
4. Staleness checks against git base or summary head.

### Phase 3

1. Cross-branch synthesis.
2. Rank child branches by evidentiary strength.
3. Multi-branch promotion into a single parent checkpoint.
4. "Best available path" recommendations.

---

## Acceptance criteria

### AC1. Honest lineage

Given a parent session and a forked child session, Maude can show their lineage relationship without rewriting transcript history.

### AC2. Promotion candidate generation

A child session can produce a typed promotion candidate containing at least summary, fact, decision, diff ref, and test results.

### AC3. Partial adoption

A parent can accept only part of a promotion candidate.

### AC4. Receipt emission

A successful adoption emits a promotion receipt containing requested scope, applied scope, imported artifacts, and rejected artifacts.

### AC5. Checkpoint creation

A successful adoption creates a synthetic checkpoint in the parent.

### AC6. No raw transcript merge

There is no code path that interleaves raw child transcript messages into the parent transcript.

### AC7. Git-aware diff provenance

When a repo exists, diff promotion includes base/target provenance sufficient to evaluate staleness or applicability.

### AC8. Policy hookability

Promotion actions can be surfaced to Governor as governed activities without embedding session lineage semantics into Governor.

---

## Risks

1. **Over-modeling.**
   Easy to turn this into a tiny PLM system because apparently suffering is irresistible.

2. **Ambiguous facts/decisions.**
   If artifact typing is too loose, promotion becomes mushy and annoying.

3. **Workspace drift.**
   A child diff may be stale by the time the parent wants it.

4. **User expectation confusion.**
   If the UI says "merge," users will expect transcript splicing and automatic reconciliation.

---

## Recommended defaults

* `/fork` should prefer a new worktree when in a git repo.
* `/promote` should default to:

  * summary
  * facts
  * decisions
  * test results
* diff adoption should be opt-in
* raw transcript import should be unsupported
* imported checkpoint messages should be clearly marked as imported

---

## Open questions

1. Should facts and decisions be first-class objects in the session store, or initially just typed annotations over summaries?
2. Should sibling comparison be textual, structural, or both?
3. Should promotion candidates be generated only on demand, or also suggested automatically when a child branch becomes "interesting"?
4. How much of this should be available in TUI only versus CLI subcommands?
5. Should multi-branch synthesis wait until Phase 3, or is there a narrow useful slice earlier?

---

## Bottom line

The right primitive is **branch promotion**, not merge.

Maude should preserve lineage, compare branch outputs, and let the parent selectively adopt typed artifacts under receipt. Governor may govern those actions, but it should not grow a theory of session genealogy just because the UI wants a return path.

That way you get the useful part of "merge" without constructing a haunted notebook and calling it progress.
