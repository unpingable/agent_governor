# Session Continuity Specification

## Version 0.2 — Capsule-Based Session Management

```yaml
status: canonical
implemented: true
module: src/governor/session_continuity.py
tests: tests/test_session_continuity.py (57 tests)
depends_on:
  - Fiction Governor (existing)
  - Nonfiction Governor (existing)
  - GovernorContextManager (existing)
blocking:
  - Long-form writing workflows
  - Multi-day writing sessions
  - Fork/branch narrative experiments
```

---

## Executive Summary

Session continuity is **not chat replay**. It is capsule-based restoration of intent, constraints, and authority state.

**Core distinction:**

| Chat Replay | Capsule Resume |
|-------------|----------------|
| Resume conversation | Resume intent + constraints + authority |
| Load transcript | Load ledger + workspace |
| Vibe reconstruction | Explicit anchor restoration |
| Hope context survives | Know what must survive |

**Core principle**: Coherence isn't optional — it's the product. Writers need to return to exactly where they left off, with all *governance state* intact. Not just the conversation.

---

## 1. The Problem

Current state:
- Each conversation starts fresh
- Canon, character state, and decisions are lost
- Writers must re-explain context every session
- No way to experiment with alternate directions

This makes the governor unusable for serious long-form writing.

---

## 2. Three-Layer Model

```
┌─────────────────────────────────────────────┐
│  Layer 1: Ledger (small, durable)           │
│  - Facts, decisions, anchors                │
│  - Already exists in .governor/             │
│  - Always persisted                         │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│  Layer 2: Workspace (medium)                │
│  - Current working state                    │
│  - Character positions, active threads      │
│  - Scene-in-progress, active constraints    │
│  - Loaded on resume                         │
└─────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────┐
│  Layer 3: Transcript (optional, archive)    │
│  - Raw conversation history                 │
│  - Load on demand, not default              │
│  - For auditing, not context                │
└─────────────────────────────────────────────┘
```

**Resume loads Layer 1 + Layer 2.** Transcript is archive, not working context.

---

## 3. What Must Survive vs What Can Be Dropped

This is the critical design decision. Get it wrong and you've built chat replay.

### Must Survive (Non-Negotiable)

| Item | Why |
|------|-----|
| Decisions | Normative — can't be re-derived from conversation |
| Active constraints | Required for governance to function |
| Anchors | Continuity enforcement depends on them |
| Authority state | Who approved what, with what scope |
| Intent | What are we trying to accomplish |
| Active thread/character state | Current working context |

### Can Be Dropped (With Receipt)

| Item | Condition |
|------|-----------|
| Detailed reasoning | Can be re-derived if needed |
| Rejected options | Brief summary sufficient |
| Raw transcript | Load on demand, not by default |
| Exploration history | Not essential for continuation |

### Must Never Be Reconstructed

| Anti-pattern | Why it's wrong |
|--------------|----------------|
| "Vibe reconstruction" | You can't infer constraints from tone |
| "Context guessing" | Authority state must be explicit |
| "Summary-based resume" | Summaries lose structural information |

---

## 4. Session Types

```python
@dataclass
class WritingSession:
    """A resumable writing session."""

    session_id: str
    name: str               # Human-readable, e.g. "chapter-5-draft"
    mode: str               # "fiction" | "nonfiction"
    created_at: datetime
    last_active: datetime
    parent_id: str | None   # For forks
    is_mainline: bool       # True if this is the "real" version
    checkpoint_count: int

    # Layer 1 reference
    ledger_path: Path

    # Layer 2 state
    workspace: WorkspaceState

@dataclass
class WorkspaceState:
    """Current working state (Layer 2)."""

    active_thread_ids: list[str]
    active_character_ids: list[str]
    scene_in_progress: SceneState | None
    active_constraints: list[str]
    cursor_position: CursorPosition | None  # Where we left off
```

---

## 4. CLI Interface

```bash
# List sessions
governor fiction sessions                    # List all sessions
governor fiction sessions --active           # Show last active
governor fiction sessions --forks            # Show fork tree

# Resume session
governor fiction resume <session>            # Reattach to ledger + workspace
governor fiction resume --last               # Resume most recent

# Checkpoint
governor fiction checkpoint                  # Save current state
governor fiction checkpoint --name "before-twist"  # Named checkpoint

# Fork
governor fiction fork                        # Branch from current state
governor fiction fork --name "alternate-ending"
governor fiction fork --from <checkpoint>    # Fork from earlier checkpoint

# Promote
governor fiction promote <session>           # This fork is now mainline
governor fiction promote --confirm           # Require explicit confirmation

# Create new session
governor fiction new <name>                  # Start fresh session
governor fiction new --from-ledger           # New session, keep ledger

# Session info
governor fiction session show <session>      # Full session details
governor fiction session diff <a> <b>        # Diff two sessions
```

---

## 5. Resume Semantics

When resuming a session:

1. **Load Layer 1 (Ledger)**
   - Facts, decisions, anchors
   - Canon events, character definitions
   - This should be fast (already SQLite)

2. **Load Layer 2 (Workspace)**
   - Active threads and characters
   - Scene-in-progress state
   - Active constraints
   - Cursor position (where we left off)

3. **Validate State**
   - Check for staleness (files changed?)
   - Warn on conflicts with current files
   - Don't silently load stale state

4. **Restore Context**
   - Inject system prompt with active constraints
   - Load relevant character/thread context
   - Don't load full transcript (too much context)

---

## 6. Fork Semantics

Forks create a new session branching from the current state.

```
         checkpoint-1
              │
              ▼
    ┌─────────────────┐
    │  mainline       │
    │  (session-1)    │
    └────────┬────────┘
             │
       fork point
        ╱         ╲
       ▼           ▼
┌─────────────┐  ┌─────────────┐
│  mainline   │  │  fork       │
│  continues  │  │  (session-2)│
└─────────────┘  └─────────────┘
```

**Fork rules:**
- Forks inherit Layer 1 (ledger) at fork point
- Forks get independent Layer 2 (workspace)
- Changes in fork don't affect mainline
- Promote makes a fork the new mainline

---

## 7. Promotion Semantics

Promotion makes a fork the new "real" version.

**Safety requirements:**
- Explicit human confirmation required
- Clear warning about what changes
- Old mainline preserved (demoted, not deleted)
- Audit trail of promotion

```bash
$ governor fiction promote alternate-ending
WARNING: This will make 'alternate-ending' the mainline.
Current mainline 'chapter-5-draft' will be archived.

Changes from mainline:
  - 3 new canon events
  - Character 'Alex' fate changed
  - 2 decisions differ

Proceed? [y/N]
```

---

## 8. Failure Modes to Prevent

| Failure | Prevention |
|---------|------------|
| Wrong session loaded | Human-readable names, last-active timestamps |
| Fork confusion | Clear fork tree visualization |
| Old draft revival | Staleness warnings, explicit resume |
| Silent mainline change | Require `--confirm` for promotion |
| Lost work | Auto-checkpoint on significant changes |
| Context pollution | Clean workspace separation |

---

## 9. Storage

```
.governor/
├── sessions/
│   ├── index.json           # Session metadata index
│   ├── session-abc123/
│   │   ├── meta.json        # Session metadata
│   │   ├── workspace.json   # Layer 2 state
│   │   └── checkpoints/
│   │       ├── cp-001.json
│   │       └── cp-002.json
│   └── session-def456/
│       └── ...
└── ledger.db                # Shared Layer 1 (existing)
```

---

## 10. Integration Points

### Fiction Governor

```python
class FictionGovernor:
    def resume_session(self, session_id: str) -> WritingSession:
        """Resume a writing session."""
        ...

    def checkpoint(self, name: str | None = None) -> Checkpoint:
        """Save current state."""
        ...

    def fork(self, name: str | None = None) -> WritingSession:
        """Create a branch from current state."""
        ...
```

### WebUI

- Session selector dropdown
- Fork tree visualization
- Checkpoint history panel
- Resume button on dashboard

### GovernorHooks

System prompt includes:
- Active session name
- Fork status (mainline or fork)
- Relevant workspace context

---

## 11. Success Criteria

| Criterion | Test |
|-----------|------|
| Resume loads state | Close and reopen, state intact |
| Fork isolation | Changes in fork don't affect mainline |
| Checkpoint restore | Can return to earlier checkpoint |
| Promotion works | Fork becomes mainline, old preserved |
| Staleness detection | Warns if files changed since last session |
| Human-readable names | Sessions have meaningful names |
| Timestamps accurate | Last-active updates on every action |

---

## 12. Implementation Notes

### What Exists

- `GovernorContextManager` — Per-project context isolation
- `SessionManager` — Execution session management
- Fiction Governor ledger persistence
- SQLite backend for facts/decisions

### What Needs Building

| Component | Effort |
|-----------|--------|
| WritingSession dataclass | Small |
| WorkspaceState dataclass | Small |
| SessionStore (persistence) | Medium |
| Resume logic | Medium |
| Fork/checkpoint logic | Medium |
| CLI commands | Small |
| WebUI integration | Medium |

Total: ~600-800 lines of new code.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec |
| 0.2 | 2026-02-05 | Implemented: SessionStore, SessionManager, CLI commands, 57 tests |
