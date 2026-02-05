# VS Code Extension UX Specification

## Version 0.1 — Inline, Contextual, Unobtrusive

### Companion to: WebUI UX Spec, CLI UX Spec

---

## Executive Summary

The VS Code extension should make governance visible without being intrusive. Developers should see decisions and constraints in context, catch violations as they happen, and resolve them without leaving the editor.

**Target State:** Governance is ambient — visible when relevant, invisible when not. You can code for an hour without thinking about the governor until it saves you from a mistake.

**Success Metric:** Developer can work a full session using only VS Code. CLI is optional, not required.

---

## 1. Design Principles

### 1.1 Ambient, Not Intrusive

- Governance indicators are subtle until relevant
- Violations demand attention; healthy state does not
- No popups unless user action is required

### 1.2 Contextual Information

- Decisions/constraints shown where they apply
- Hover for details, don't clutter the view
- History and rationale one click away

### 1.3 Inline Resolution

- Fix violations without opening terminals
- Resolution UI appears in editor context
- Results visible immediately

### 1.4 Progressive Disclosure

- Status bar: health indicator only
- Gutter: markers for governed code
- Hover: details on demand
- Panel: full management interface

---

## 2. Visual Elements

### 2.1 Status Bar

Minimal indicator in status bar:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ... other items ...  │  Governor: ✓ 4 │  ... other items ...                │
└──────────────────────────────────────────────────────────────────────────────┘
```

States:

| Icon | Meaning |
|------|---------|
| `✓ 4` | Healthy, 4 decisions/constraints active |
| `⚠ 1` | 1 pending violation |
| `✗ 3` | 3 unresolved violations |
| `○` | Governor disabled for this workspace |
| `⟳` | Checking... |

**Click behavior:**
- Click → Open Governor panel
- Right-click → Quick menu (enable/disable, open settings)

### 2.2 Gutter Indicators

Icons in the editor gutter next to line numbers:

```
    1 │   def authenticate(user):
  ● 2 │       # Decision: Using JWT, not sessions
    3 │       token = create_jwt(user)
    4 │       return token
    5 │
    6 │   def get_users():
  ⚠ 7 │       return db.execute("SELECT * FROM users")
    8 │
  ◆ 9 │   # Constraint: All API responses use this format
   10 │   def api_response(data):
```

| Icon | Meaning | Color |
|------|---------|-------|
| `●` | Decision applies here | Blue |
| `◆` | Constraint applies here | Purple |
| `⚠` | Violation detected | Yellow/Orange |
| `✗` | Unresolved violation | Red |
| `✓` | Recently fixed | Green (fades) |

**Icon behavior:**
- Hover → Show summary
- Click → Show full details + actions

### 2.3 Inline Decorations

Subtle text decorations for governed code:

```python
def authenticate(user):
    token = create_jwt(user)  # ← JWT decision
    return token
```

The `# ← JWT decision` is a faded inline decoration, not actual code. Shows only when cursor is on that line or nearby.

**Configuration:**
- Can be disabled in settings
- Opacity configurable
- Show always / on hover / never

### 2.4 Squiggles for Violations

Violations show as squiggly underlines (like errors/warnings):

```python
def get_users():
    return db.execute("SELECT * FROM users")
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~
           ⚠ Violates: "No raw SQL (use ORM)"
```

Squiggle color matches severity:
- Yellow: Warning (can proceed)
- Red: Block (must resolve)

---

## 3. Hover Information

### 3.1 Decision Hover

Hovering over a governed line shows:

```
┌─────────────────────────────────────────────────────────┐
│ 📌 Decision: Using JWT for authentication               │
├─────────────────────────────────────────────────────────┤
│ Recorded: 2024-01-15                                    │
│ Rationale: "Stateless, scales horizontally, team       │
│            has experience"                              │
│                                                         │
│ Alternatives considered:                                │
│   • Sessions (rejected: requires sticky sessions)       │
│   • OAuth only (rejected: need internal auth too)       │
├─────────────────────────────────────────────────────────┤
│ [View in Ledger]  [Edit]  [Remove]                     │
└─────────────────────────────────────────────────────────┘
```

### 3.2 Constraint Hover

```
┌─────────────────────────────────────────────────────────┐
│ 🚫 Constraint: No raw SQL                               │
├─────────────────────────────────────────────────────────┤
│ Use the ORM for all database queries.                   │
│                                                         │
│ Blocked patterns:                                       │
│   • db.execute(                                         │
│   • cursor.execute(                                     │
│   • raw SQL strings                                     │
│                                                         │
│ Applies to: src/**/*.py                                │
├─────────────────────────────────────────────────────────┤
│ [Edit Constraint]  [Disable]                           │
└─────────────────────────────────────────────────────────┘
```

### 3.3 Violation Hover

```
┌─────────────────────────────────────────────────────────┐
│ ⚠️ Violation: Raw SQL detected                          │
├─────────────────────────────────────────────────────────┤
│ This code:                                              │
│   db.execute("SELECT * FROM users")                     │
│                                                         │
│ Violates:                                               │
│   🚫 "No raw SQL (use ORM)"                            │
│                                                         │
│ Suggested fix:                                          │
│   User.query.all()                                      │
├─────────────────────────────────────────────────────────┤
│ [Apply Fix]  [Update Constraint]  [Allow Once]         │
└─────────────────────────────────────────────────────────┘
```

---

## 4. CodeLens Integration

### 4.1 Decision CodeLens

Above functions/classes with relevant decisions:

```python
# 📌 JWT authentication | View decision
def authenticate(user):
    token = create_jwt(user)
    return token
```

The CodeLens line is clickable:
- Click "JWT authentication" → Jump to decision in ledger
- Click "View decision" → Expand inline details

### 4.2 Violation CodeLens

Above lines with violations:

```python
# ⚠️ Violates: No raw SQL | Fix | Allow | Update Constraint
def get_users():
    return db.execute("SELECT * FROM users")
```

**Actions:**
- Fix → Apply suggested fix
- Allow → Log exception, remove violation
- Update Constraint → Edit the constraint

### 4.3 File-Level CodeLens

At top of file if file-wide decisions apply:

```python
# 📌 3 decisions apply to this file | View all
# api/routes.py

from flask import Flask
...
```

---

## 5. Problems Panel Integration

### 5.1 Governor Problems

Violations appear in VS Code's Problems panel:

```
PROBLEMS  OUTPUT  DEBUG CONSOLE  TERMINAL

Filter: Governor ▼

  ⚠ api/users.py
    Line 7: Raw SQL violates "No raw SQL (use ORM)"
    
  ⚠ api/auth.py  
    Line 23: Missing error handling violates "All endpoints handle errors"
```

**Behavior:**
- Click → Jump to violation
- Right-click → Resolution options
- Integrates with existing problem workflow

### 5.2 Severity Mapping

| Governor Severity | VS Code Severity |
|-------------------|------------------|
| Block (reject) | Error |
| Warn | Warning |
| Info | Information |

---

## 6. Governor Panel

### 6.1 Panel Location

- Activity Bar icon (left sidebar)
- Or: Explorer pane section
- Keyboard: `Cmd/Ctrl + Shift + G` (configurable)

### 6.2 Panel Structure

```
┌─────────────────────────────────────────┐
│ GOVERNOR                           [⚙]  │
├─────────────────────────────────────────┤
│                                         │
│ ▼ Decisions (4)                         │
│   ├── 📌 REST API (not GraphQL)         │
│   ├── 📌 JWT authentication             │
│   ├── 📌 PostgreSQL                     │
│   └── 📌 Monorepo structure             │
│   [+ Add Decision]                      │
│                                         │
│ ▼ Constraints (2)                       │
│   ├── 🚫 No Redux                       │
│   └── 🚫 No raw SQL                     │
│   [+ Add Constraint]                    │
│                                         │
│ ▼ Violations (1)                        │
│   └── ⚠ api/users.py:7 - Raw SQL       │
│                                         │
│ ▼ Recent Activity                       │
│   ├── ✓ Fixed: GraphQL import (2m ago) │
│   ├── 📌 Added: JWT decision (1h ago)  │
│   └── ⚠ Blocked: Raw SQL (just now)    │
│   [View Full Ledger]                    │
│                                         │
├─────────────────────────────────────────┤
│ Status: ✓ Healthy                       │
│ Last check: 30 seconds ago              │
└─────────────────────────────────────────┘
```

### 6.3 Panel Actions

**Tree item actions (on hover):**
- Decisions: Edit, Remove, Go to code
- Constraints: Edit, Disable, Remove
- Violations: Fix, Allow, Go to code

**Panel header actions:**
- Refresh
- Settings
- Collapse all

### 6.4 Add Decision Dialog

Triggered from panel or command palette:

```
┌─────────────────────────────────────────────────────────────┐
│ Add Decision                                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Decision:                                                   │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Using PostgreSQL for all persistent storage             │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Rationale:                                                  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Team expertise, ACID compliance, good ecosystem         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Scope: ◉ Project-wide  ○ Specific paths                    │
│                                                             │
│                              [Cancel]  [Add Decision]       │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Command Palette

### 7.1 Commands

Prefix: `Governor:`

```
Governor: Add Decision
Governor: Add Constraint
Governor: Check Current File
Governor: Check Selection
Governor: Check Workspace
Governor: View Ledger
Governor: Resolve Violation
Governor: Resolve All Violations
Governor: Open Panel
Governor: Toggle Gutter Icons
Governor: Toggle Inline Decorations
Governor: Enable Governor
Governor: Disable Governor
Governor: Show Decision at Cursor
Governor: Show Constraint at Cursor
```

### 7.2 Quick Actions

For common actions, no prefix needed when in context:

```
> resolve violation
  Governor: Resolve Violation

> add decision
  Governor: Add Decision
```

---

## 8. Inline Violation Resolution

### 8.1 Quick Fix Integration

Violations integrate with VS Code's Quick Fix (`Cmd/Ctrl + .`):

```python
def get_users():
    return db.execute("SELECT * FROM users")
           └── 💡 Quick Fix available

Quick Fix menu:
┌─────────────────────────────────────────┐
│ Governor: Apply suggested fix           │
│ Governor: Allow this violation          │
│ Governor: Update constraint             │
│ Governor: Disable constraint for file   │
│ ─────────────────────────────────────── │
│ Extract to variable                     │
│ ... other VS Code suggestions ...       │
└─────────────────────────────────────────┘
```

### 8.2 Suggested Fixes

When governor can suggest a fix:

```python
# Before:
return db.execute("SELECT * FROM users")

# Quick Fix: "Apply suggested fix"
# After:
return User.query.all()
```

If no automatic fix available, Quick Fix shows:
- "Allow this violation (log exception)"
- "Update constraint"
- "Disable constraint for this file"

### 8.3 Multi-Violation Resolution

When file has multiple violations:

```
> Governor: Resolve All Violations

Resolving 3 violations in api/users.py:

1. Line 7: Raw SQL
   [Fix] [Allow] [Skip]

2. Line 15: Missing error handling  
   [Fix] [Allow] [Skip]

3. Line 23: Deprecated import
   [Fix] [Allow] [Skip]

[Fix All] [Allow All] [Cancel]
```

---

## 9. File Watcher Integration

### 9.1 Real-Time Checking

Governor checks files:
- On save (default)
- On change (configurable, may be slow)
- On focus (when switching to file)

### 9.2 Check Indicators

While checking:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  ... other items ...  │  Governor: ⟳ Checking... │  ... other items ...      │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 9.3 Batch Operations

For large changes (git checkout, paste), governor batches checks to avoid lag.

---

## 10. Git Integration

### 10.1 Pre-Commit Check

If git hooks installed, governor checks staged files:

```
┌─────────────────────────────────────────────────────────────┐
│ Governor: Pre-commit check failed                           │
├─────────────────────────────────────────────────────────────┤
│ 2 violations in staged files:                               │
│                                                             │
│   ⚠ api/users.py:7 - Raw SQL                               │
│   ⚠ api/auth.py:23 - Missing error handling                │
│                                                             │
│ [Resolve Now]  [Commit Anyway]  [Cancel]                   │
└─────────────────────────────────────────────────────────────┘
```

### 10.2 Diff View Annotations

In diff view, show which changes trigger violations:

```diff
  def get_users():
-     return User.query.all()
+     return db.execute("SELECT * FROM users")  ⚠ Violates: No raw SQL
```

---

## 11. Settings

### 11.1 Extension Settings

```json
{
  "governor.enable": true,
  "governor.checkOnSave": true,
  "governor.checkOnChange": false,
  "governor.showGutterIcons": true,
  "governor.showInlineDecorations": true,
  "governor.showCodeLens": true,
  "governor.decorationOpacity": 0.6,
  "governor.problemsIntegration": true,
  "governor.statusBarPosition": "right",
  "governor.mode": "code"
}
```

### 11.2 Settings UI

Accessible from:
- Governor panel gear icon
- Command palette: `Governor: Open Settings`
- VS Code settings search: "governor"

---

## 12. Keybindings

### 12.1 Default Keybindings

| Action | Mac | Windows/Linux |
|--------|-----|---------------|
| Open Governor Panel | `Cmd+Shift+G` | `Ctrl+Shift+G` |
| Resolve Violation at Cursor | `Cmd+.` (Quick Fix) | `Ctrl+.` |
| Add Decision | `Cmd+Shift+D` | `Ctrl+Shift+D` |
| Check Current File | `Cmd+Shift+C` | `Ctrl+Shift+C` |

### 12.2 Customization

All keybindings customizable via VS Code keybindings.json.

---

## 13. Notifications

### 13.1 Notification Types

| Event | Notification Type |
|-------|------------------|
| Violation found | Status bar update (no popup) |
| Commit blocked | Modal dialog |
| Decision added | Brief toast |
| Constraint violated repeatedly | Suggestion toast |

### 13.2 Notification Preferences

```json
{
  "governor.notifications.violations": "statusBar",  // statusBar, toast, none
  "governor.notifications.commitBlocked": "modal",   // modal, toast
  "governor.notifications.decisionsAdded": "toast"   // toast, none
}
```

---

## 14. Performance Considerations

### 14.1 Large Files

- Skip files > 1MB by default
- Configurable threshold
- Always skip binary files

### 14.2 Large Workspaces

- Only check open files by default
- Full workspace scan on demand
- Incremental checks on file change

### 14.3 Debouncing

- Check on change: 500ms debounce
- Check on save: immediate
- Batch rapid changes

---

## 15. Fiction Mode (Bonus)

### 15.1 Markdown/Text Support

For fiction writers using VS Code:

- Same gutter indicators
- Character name highlighting
- World rule checking
- Tone analysis (sidebar)

### 15.2 Fiction Panel Variant

```
┌─────────────────────────────────────────┐
│ GOVERNOR (Fiction)                 [⚙]  │
├─────────────────────────────────────────┤
│                                         │
│ ▼ Characters (3)                        │
│   ├── 👤 Elena Vasquez                  │
│   ├── 👤 Marcus Chen                    │
│   └── 👤 Vera Okonkwo                   │
│   [+ Add Character]                     │
│                                         │
│ ▼ World Rules (5)                       │
│   ├── 🌍 Magic requires words           │
│   └── ... 4 more                        │
│   [+ Add Rule]                          │
│                                         │
│ ...                                     │
└─────────────────────────────────────────┘
```

---

## 16. Success Metrics

| Metric | Target |
|--------|--------|
| Violations resolved without leaving editor | > 95% |
| Time to understand a violation | < 5 seconds |
| Hover → resolution | < 3 clicks |
| Users who disable extension | < 10% |
| Performance impact on editor | < 50ms per check |

---

## 17. Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-03 | Initial spec |

---

*"Governance is ambient — visible when relevant, invisible when not."*

*"You can code for an hour without thinking about the governor until it saves you from a mistake."*

*"Fix violations without leaving the editor."*
