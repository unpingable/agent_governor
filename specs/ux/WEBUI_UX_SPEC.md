# WebUI UX Specification

## Version 0.1 — Mode-Specific Dashboards

### Companion to: Fiction Mode User Guide, Maude Profile Specs

---

## Executive Summary

The WebUI currently works but feels like a CLI with a chat window attached. Users interact with the governor through text commands in the chat.

**Target State:** Mode-specific visual dashboards where the governor is a visible collaborator, not a hidden command processor.

**Success Metric:** Author can write fiction for 30 minutes without asking developer a question.

---

## 1. Design Principles

### 1.1 Dashboard, Not CLI

Users should never type `governor` or `maude` commands unless they want to. Every common action has a visual affordance.

### 1.2 Mode-Specific Surfaces

Fiction and Code modes are different products sharing an engine. The UI should reflect that:

| Mode | Mental Model | Primary Objects |
|------|--------------|-----------------|
| Fiction | "My story bible" | Characters, World Rules, Boundaries, Tone |
| Code | "My architectural decisions" | Decisions, Constraints, Verifications |

### 1.3 Progressive Disclosure

- **Level 0:** Chat works without touching any panels
- **Level 1:** Side panel shows current constraints, recent catches
- **Level 2:** Clicking into items reveals details
- **Level 3:** Advanced settings exist but are hidden by default

### 1.4 Violations Are Conversations, Not Errors

When something gets blocked, it's not a red error screen. It's a choice the user makes. The UI should present it as a decision point, not a failure.

---

## 2. Layout Structure

### 2.1 Overall Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Header: Project/Story selector │ Mode indicator │ Settings │ User     │
├───────────────────────────────────┬─────────────────────────────────────┤
│                                   │                                     │
│                                   │                                     │
│         Governor Panel            │           Chat Area                 │
│         (collapsible)             │                                     │
│         ~300px                    │           (flex grow)               │
│                                   │                                     │
│                                   │                                     │
│                                   │                                     │
│                                   ├─────────────────────────────────────┤
│                                   │           Input Area                │
└───────────────────────────────────┴─────────────────────────────────────┘
```

### 2.2 Responsive Behavior

- **Desktop (>1200px):** Panel always visible, chat full width
- **Tablet (768-1200px):** Panel collapsible, defaults open
- **Mobile (<768px):** Panel as bottom sheet or separate tab

### 2.3 Panel Toggle

- Button in header or edge of panel
- Keyboard shortcut: `Cmd/Ctrl + \`
- Panel state persists across sessions

---

## 3. Fiction Mode Panel

### 3.1 Panel Structure

```
┌─────────────────────────────────────┐
│  📚 Story: [Untitled ▼] [+ New]     │
├─────────────────────────────────────┤
│                                     │
│  ▼ Characters (3)                   │
│  ┌─────────────────────────────┐    │
│  │ ● Elena Vasquez             │    │
│  │   Green eyes, black hair    │    │
│  │   [Edit] [Disable]          │    │
│  ├─────────────────────────────┤    │
│  │ ● Marcus Chen               │    │
│  │   Never uses violence       │    │
│  │   [Edit] [Disable]          │    │
│  ├─────────────────────────────┤    │
│  │ ○ Vera (disabled)           │    │
│  │   [Enable] [Remove]         │    │
│  └─────────────────────────────┘    │
│  [+ Add Character]                  │
│                                     │
│  ▼ World Rules (2)                  │
│  ┌─────────────────────────────┐    │
│  │ Magic requires spoken words │    │
│  │ Technology: 1920s level     │    │
│  └─────────────────────────────┘    │
│  [+ Add Rule]                       │
│                                     │
│  ▼ Boundaries (1)                   │
│  ┌─────────────────────────────┐    │
│  │ 🚫 No graphic violence      │    │
│  └─────────────────────────────┘    │
│  [+ Add Boundary]                   │
│                                     │
│  ▼ Tone                             │
│  ┌─────────────────────────────┐    │
│  │ Style: [Literary ▼]         │    │
│  │                             │    │
│  │ Dark ○───●─────○ Light      │    │
│  │ Sparse ○─────●───○ Dense    │    │
│  └─────────────────────────────┘    │
│                                     │
├─────────────────────────────────────┤
│  ▼ Recent Catches (2)               │
│  ┌─────────────────────────────┐    │
│  │ ⚠ "Elena's blue eyes"       │    │
│  │   → Fixed (10 min ago)      │    │
│  ├─────────────────────────────┤    │
│  │ ✓ "Marcus attacked"         │    │
│  │   → Allowed: dream sequence │    │
│  └─────────────────────────────┘    │
│  [View All History]                 │
│                                     │
└─────────────────────────────────────┘
```

### 3.2 Characters Section

**Add Character Dialog:**

```
┌─────────────────────────────────────────────────────────────┐
│  Add Character                                         [X]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Name: [________________________]                           │
│                                                             │
│  Physical Description:                                      │
│  [___________________________________________________]     │
│  [___________________________________________________]     │
│                                                             │
│  Personality / Voice:                                       │
│  [___________________________________________________]     │
│  [___________________________________________________]     │
│                                                             │
│  Things they would NEVER do:                                │
│  [___________________________________________________]     │
│                                                             │
│  ☐ Strict mode (block on any violation)                    │
│  ☑ Standard mode (block on contradictions)                 │
│                                                             │
│                            [Cancel]  [Add Character]        │
└─────────────────────────────────────────────────────────────┘
```

**Fields map to anchors:**
- Physical Description → `assertion` anchor
- Personality/Voice → `character` anchor  
- Things they would NEVER do → `prohibition` anchor

User never sees "anchor" or "assertion" — just character traits.

### 3.3 World Rules Section

**Add Rule Dialog:**

```
┌─────────────────────────────────────────────────────────────┐
│  Add World Rule                                        [X]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Rule: [_______________________________________________]    │
│                                                             │
│  Examples or details (optional):                            │
│  [___________________________________________________]     │
│                                                             │
│  Category: [Magic ▼]  (Magic / Technology / Society /       │
│                        Geography / History / Other)         │
│                                                             │
│                                 [Cancel]  [Add Rule]        │
└─────────────────────────────────────────────────────────────┘
```

### 3.4 Boundaries Section

**Add Boundary Dialog:**

```
┌─────────────────────────────────────────────────────────────┐
│  Add Boundary                                          [X]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  The AI should never:                                       │
│  [___________________________________________________]     │
│                                                             │
│  Specific phrases to block (optional):                      │
│  [___________________________________________________]     │
│  (comma-separated)                                          │
│                                                             │
│  Severity:                                                  │
│  ◉ Block and ask me (recommended)                          │
│  ○ Warn but continue                                        │
│                                                             │
│                               [Cancel]  [Add Boundary]      │
└─────────────────────────────────────────────────────────────┘
```

### 3.5 Tone Section

**Preset Styles:**
- Literary
- Commercial
- Young Adult
- Dark/Gritty
- Light/Humorous
- Custom

**Sliders:**
- Dark ↔ Light
- Sparse ↔ Dense  
- Fast ↔ Slow (pacing)
- Close ↔ Distant (narrative distance)

Sliders map to tone envelope values internally. User never sees "envelope" or numeric ranges.

### 3.6 Recent Catches Section

Shows last 5-10 violations with:
- What was caught (truncated quote)
- What it conflicted with
- Resolution (Fixed / Canon Updated / Allowed)
- Timestamp

Click → expands to full detail.

"View All History" → full audit log.

---

## 4. Code Mode Panel

### 4.1 Panel Structure

```
┌─────────────────────────────────────┐
│  📁 Project: [agent-gov ▼] [+ New]  │
├─────────────────────────────────────┤
│                                     │
│  ▼ Decisions (4)                    │
│  ┌─────────────────────────────┐    │
│  │ ● REST API (not GraphQL)    │    │
│  │   2024-01-15                │    │
│  │   [Edit] [View Rationale]   │    │
│  ├─────────────────────────────┤    │
│  │ ● PostgreSQL for persistence│    │
│  │   2024-01-10                │    │
│  ├─────────────────────────────┤    │
│  │ ● Monorepo structure        │    │
│  │   2024-01-08                │    │
│  └─────────────────────────────┘    │
│  [+ Add Decision]                   │
│                                     │
│  ▼ Constraints (2)                  │
│  ┌─────────────────────────────┐    │
│  │ 🚫 No Redux                 │    │
│  │ 🚫 No raw SQL (use ORM)     │    │
│  └─────────────────────────────┘    │
│  [+ Add Constraint]                 │
│                                     │
│  ▼ Verification                     │
│  ┌─────────────────────────────┐    │
│  │ ☑ Run tests before commit   │    │
│  │ ☑ Type check                │    │
│  │ ☑ Lint                      │    │
│  │ ☐ Build                     │    │
│  └─────────────────────────────┘    │
│                                     │
├─────────────────────────────────────┤
│  ▼ Recent (3)                       │
│  ┌─────────────────────────────┐    │
│  │ ✗ "Using GraphQL"           │    │
│  │   Contradicts REST decision │    │
│  ├─────────────────────────────┤    │
│  │ ✓ Tests pass                │    │
│  │   Receipt: a7f3c2...        │    │
│  ├─────────────────────────────┤    │
│  │ ✓ Commit verified           │    │
│  │   3 files, all receipts     │    │
│  └─────────────────────────────┘    │
│  [View Ledger]                      │
│                                     │
└─────────────────────────────────────┘
```

### 4.2 Decisions Section

**Add Decision Dialog:**

```
┌─────────────────────────────────────────────────────────────┐
│  Add Architectural Decision                            [X]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Decision: [___________________________________________]    │
│  (e.g., "Using REST API, not GraphQL")                      │
│                                                             │
│  Rationale:                                                 │
│  [___________________________________________________]     │
│  [___________________________________________________]     │
│                                                             │
│  Alternatives considered (optional):                        │
│  [___________________________________________________]     │
│                                                             │
│  Scope: ◉ Project-wide  ○ Specific paths: [________]       │
│                                                             │
│                              [Cancel]  [Record Decision]    │
└─────────────────────────────────────────────────────────────┘
```

Decisions are normative (persist). They go to the decisions ledger.

### 4.3 Constraints Section

**Add Constraint Dialog:**

```
┌─────────────────────────────────────────────────────────────┐
│  Add Constraint                                        [X]  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  The agent should never:                                    │
│  [___________________________________________________]     │
│                                                             │
│  Patterns to catch (optional):                              │
│  [___________________________________________________]     │
│  (comma-separated: "Redux", "createStore", etc.)            │
│                                                             │
│  Applies to: ◉ All files  ○ Only: [src/**/*.ts____]        │
│                                                             │
│                                [Cancel]  [Add Constraint]   │
└─────────────────────────────────────────────────────────────┘
```

### 4.4 Verification Section

Checkboxes for verification steps. Each maps to a verifier:

| Checkbox | Verifier | Receipt Type |
|----------|----------|--------------|
| Run tests | `pytest` / `npm test` | CmdRun |
| Type check | `mypy` / `tsc` | CmdRun |
| Lint | `ruff` / `eslint` | CmdRun |
| Build | `make` / `npm build` | CmdRun |

Checked items run automatically before writes are allowed.

### 4.5 Ledger View

"View Ledger" opens a modal or separate view:

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Ledger                                                            [X]  │
├─────────────────────────────────────────────────────────────────────────┤
│  Filter: [All ▼]  [Facts | Decisions | Rejections]    Search: [______] │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  2024-01-20 14:32 │ DECISION │ Using REST API                          │
│                   │          │ Rationale: "Simpler, team knows it"     │
│                   │          │ Alternatives: GraphQL, gRPC             │
│  ─────────────────┼──────────┼─────────────────────────────────────    │
│  2024-01-20 15:01 │ FACT     │ File created: src/api/routes.py         │
│                   │          │ Receipt: a7f3c2d8...                    │
│  ─────────────────┼──────────┼─────────────────────────────────────    │
│  2024-01-20 15:45 │ REJECTED │ "Using GraphQL for efficiency"          │
│                   │          │ Contradicts: REST API decision          │
│                   │          │ Resolution: Fix (regenerated)           │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Violation Resolution Modal

### 5.1 Design

When a violation is detected, instead of text in chat, show a modal:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   ⚠️  Output blocked                                                    │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ "Elena's blue eyes sparkled in the lamplight"                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   Conflicts with:                                                       │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ 👤 Elena: "Green eyes, not blue"                                │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│   ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────────────┐   │
│   │                 │ │                 │ │                         │   │
│   │    🔄 Fix       │ │  📝 Update      │ │    ✓ Allow Once         │   │
│   │                 │ │     Canon       │ │                         │   │
│   │   Rewrite to    │ │                 │ │   Log as intentional    │   │
│   │   match canon   │ │  Elena now has  │ │   (dream, flashback,    │   │
│   │                 │ │   blue eyes     │ │    unreliable narrator) │   │
│   │                 │ │                 │ │                         │   │
│   └─────────────────┘ └─────────────────┘ └─────────────────────────┘   │
│                                                                         │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ ☐ Remember this choice for similar violations                   │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│                                              [Cancel and Edit Myself]   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 5.2 Behavior

| Button | Action | Result |
|--------|--------|--------|
| Fix | Regenerate with constraint | New output respecting anchor |
| Update Canon | Modify the anchor | Anchor updated, original output allowed |
| Allow Once | Log exception | Output allowed, exception recorded |
| Cancel | Close modal | User edits input manually |

### 5.3 Remember Choice

If checked, similar violations auto-resolve the same way. Useful for:
- Intentional stylistic choices
- Recurring patterns that aren't really violations

Creates a "learned exception" that can be viewed/removed in settings.

### 5.4 Multiple Violations

If output triggers multiple violations, show them stacked:

```
┌─────────────────────────────────────────────────────────────┐
│  ⚠️  2 issues found                                         │
├─────────────────────────────────────────────────────────────┤
│  1. "Elena's blue eyes" → Conflicts with: green eyes        │
│     [Fix] [Update Canon] [Allow]                            │
├─────────────────────────────────────────────────────────────┤
│  2. "Marcus punched the wall" → Conflicts with: no violence │
│     [Fix] [Update Canon] [Allow]                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [Fix All] [Cancel]                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. Settings & Preferences

### 6.1 Accessible From

- Gear icon in header
- Panel overflow menu
- Keyboard: `Cmd/Ctrl + ,`

### 6.2 Settings Structure

```
┌─────────────────────────────────────────────────────────────┐
│  Settings                                              [X]  │
├────────────────┬────────────────────────────────────────────┤
│                │                                            │
│  General       │  Mode: ◉ Fiction  ○ Code                  │
│                │                                            │
│  Appearance    │  Default project: [____________▼]          │
│                │                                            │
│  Governance    │  ☑ Show panel by default                  │
│                │  ☑ Sound on violation                     │
│  Advanced      │  ☐ Auto-fix minor violations              │
│                │                                            │
│  Import/Export │                                            │
│                │                                            │
└────────────────┴────────────────────────────────────────────┘
```

### 6.3 Governance Settings

- Strictness level (how sensitive violation detection is)
- Default resolution (what happens if user ignores modal)
- Learned exceptions (view/remove auto-resolved patterns)
- Blocked phrases (global, across all anchors)

### 6.4 Import/Export

- Export story bible / decisions as YAML
- Import from file
- Sync across devices (future)

---

## 7. Onboarding Flow

### 7.1 First Launch

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Welcome to Governor                                       │
│                                                             │
│   What are you working on?                                  │
│                                                             │
│   ┌─────────────────────┐  ┌─────────────────────┐         │
│   │                     │  │                     │         │
│   │   📚 Fiction        │  │   💻 Code           │         │
│   │                     │  │                     │         │
│   │   Novel, stories,   │  │   Software, APIs,   │         │
│   │   creative writing  │  │   technical work    │         │
│   │                     │  │                     │         │
│   └─────────────────────┘  └─────────────────────┘         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Fiction Quick Setup

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   Let's set up your story                                   │
│                                                             │
│   Story name: [______________________________]              │
│                                                             │
│   Add your main character:                                  │
│   Name: [______________________________]                    │
│   Key trait: [______________________________]               │
│                                                             │
│   Any topics to avoid?                                      │
│   [______________________________]                          │
│                                                             │
│   [Skip for now]                    [Start Writing →]       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.3 First Violation (Guided)

First time a violation occurs, add explanation:

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   🎓 This is a catch!                                       │
│                                                             │
│   The AI wrote something that contradicts your story.       │
│   This is the governor doing its job.                       │
│                                                             │
│   You have three choices:                                   │
│                                                             │
│   • Fix — AI tries again, respecting your rules             │
│   • Update — Change your rules to match this                │
│   • Allow — Let it through this once (it's intentional)     │
│                                                             │
│   [Got it, show me the choices]                             │
│                                                             │
│   ☐ Don't show this explanation again                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 8. Implementation Notes

### 8.1 State Management

- Panel state (open/closed, scroll position) persists in localStorage
- Anchors/decisions sync with `.governor/` backend
- Optimistic UI updates with rollback on failure

### 8.2 Real-Time Updates

- When anchor added via CLI, panel updates
- When violation resolved in chat, "Recent Catches" updates
- WebSocket or polling for sync

### 8.3 Accessibility

- All modals keyboard-navigable
- Focus trap in modals
- Screen reader announcements for violations
- High contrast mode support

### 8.4 Mobile Considerations

- Panel becomes bottom sheet on mobile
- Violation modal becomes full-screen
- Touch-friendly button sizes (min 44px)

---

## 9. Success Metrics

| Metric | Target |
|--------|--------|
| Time to first anchor (new user) | < 2 minutes |
| Violation resolution without help text | > 90% of users |
| Panel usage (opened at least once per session) | > 70% |
| Violations resolved via modal (not CLI) | > 95% for fiction users |
| 30-minute unassisted session | Achievable by non-technical users |

---

## 10. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-03 | Initial spec |

---

*"The user never sees 'anchor' or 'assertion' — just character traits."*

*"Violations are conversations, not errors."*

*"Can she use it for 30 minutes without asking a question?"*
