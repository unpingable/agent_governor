# Slim Mode Specification

## Version 0.1 — Single-Developer Governance for High-Iteration Workflows

```yaml
status: gap
implemented: false
depends_on:
  - cli.py               # Click CLI
  - ledgers.py           # FactLedger, DecisionLedger
  - continuity.py        # AnchorRegistry, ContinuityChecker
  - spine.py             # Spine, SpineManager
  - invariant_store.py   # InvariantSpec, InvariantStore
  - envelopes.py         # Operating modes
  - claude_hooks.py      # HookConfig, Claude CLI integration
  - check.py             # Unified check aggregation
  - CONSTRAINT_COMPILER_SPEC.md
blocking: practical self-governance, solo developer adoption
estimated_scope: medium
```

### Companion to: CONSTRAINT_COMPILER_SPEC.md, DETECTOR_INTEGRATION_SPEC.md

---

## Executive Summary

The governor is designed for adversarial multi-agent coordination: typed claims, receipt-producing verification, transactional ledgers, quorum consensus. This ceremony is correct for high-stakes, multi-actor deployments. It is punishing for the most common use case: **one developer, one AI agent (Claude Code or Codex), fast iteration**.

The result is that the governor's own developers don't use the full workflow on themselves — the value is real (decisions, anchors, invariants, spines), but the overhead-to-insight ratio is wrong for solo work.

Slim Mode is a **governed subset** optimized for single-developer, high-iteration workflows. It keeps the parts that prevent real drift (decisions, anchors, structure locks, test gates) and drops the parts that exist for multi-agent adversarial scenarios (proposals, receipts, quorum, leases, epochs). It runs inside Claude Code / Codex sessions as a lightweight sidecar, not a ceremony.

**Design principle**: The governor should be as easy to use on itself as it is to build.

---

## 1. The Problem

### 1.1 The Ceremony Tax

A single architectural decision in the current workflow:

```bash
governor propose --claim "Using React for frontend" --topic framework
governor verify 1
governor apply 1
```

Three commands, manual ID tracking, receipt generation, FSM transitions. For a solo developer who just wants to record "we decided X," this is overhead with no adversarial threat to justify it.

### 1.2 What Solo Developers Actually Need

| Need | Current Governor Feature | Ceremony Cost |
|------|------------------------|---------------|
| Record decisions that shouldn't be contradicted | Decision ledger | 3 commands per decision |
| Lock text constraints (canon, invariants) | Continuity anchors | Verbose CLI, manual IDs |
| Prevent file structure sprawl | Spines | Full lock/activate workflow |
| Ensure tests pass before commit | Invariants | Define + check lifecycle |
| Check code for security + continuity | `governor check` | **Already streamlined** |
| Track what changed and why | Git + telemetry | Separate from governance |

### 1.3 What Solo Developers Don't Need

- Proposal/verify/apply FSM (no adversarial actor to gate)
- Receipts with cryptographic hashes (trust model is "I trust myself")
- Quorum, leases, epochs (single actor)
- Agent registration, permissions, heartbeats (one agent)
- Claim types with formal schemas (decisions are conversational)

### 1.4 The Integration Gap

Claude Code and Codex work in tight loops: prompt → generate → review → iterate. The governor needs to live *inside* that loop, not beside it. Currently:

- Claude hooks exist (`claude_hooks.py`) but enforce full ceremony
- `governor check` works inline but only covers security + continuity
- No way to say "record this decision" without the 3-command dance
- No way to seed constraints from a conversation without leaving the flow

---

## 2. The Solution

### 2.1 Slim Mode Envelope

A new operating envelope alongside `strict` and `exploratory`:

```python
class Envelope(Enum):
    STRICT = "strict"             # Full ceremony, all receipts
    EXPLORATORY = "exploratory"   # Receipts optional, conflicts allowed
    SLIM = "slim"                 # Single-dev: decisions + anchors + checks, no proposals
```

Slim mode enables:
- Direct decision recording (no propose/verify/apply)
- Direct anchor creation (no formal claim lifecycle)
- Inline checking (`governor check`) on every save / pre-commit
- Spine and invariant enforcement (structure and test gates)
- Telemetry (lightweight, for self-audit)

Slim mode disables:
- Proposal FSM (decisions are recorded directly, not proposed)
- Receipt generation (trust model assumes honest single actor)
- Quorum, leases, epochs, agent registration
- Formal claim types (free-text decisions are acceptable)

### 2.2 One-Line Commands

Replace the 3-command ceremony with single-line operations:

```bash
# Decisions
governor decide "Authentication uses JWT"                    # Record decision immediately
governor decide "No ORM — raw SQL with parameterized queries" --topic database
governor decide --retract "Authentication uses JWT"          # Retract with audit trail
governor decisions                                           # List (existing command)

# Anchors
governor anchor "Elena has green eyes" --type canon --severity reject
governor anchor "No eval() calls" --type prohibition --severity reject --scope "src/**"
governor anchor --remove elena-eyes

# Structure
governor lock src/governor/                                  # Lock directory structure (spine shorthand)
governor unlock src/governor/ --confirm

# Invariants
governor must-pass "python3 -m pytest tests/ -x"            # Register test gate
governor must-exist src/governor/__init__.py                 # Register file gate

# Checking (already works)
governor check src/governor/constraint_compiler.py

# Status (unified slim view)
governor slim status                                         # Decisions + anchors + invariants + spine summary
```

Each command is a single verb, immediate effect, no IDs to track.

### 2.3 Claude Code Integration

Slim mode integrates with Claude Code via hooks (`claude_hooks.py`) that run automatically:

#### Pre-Tool Hook (Before File Write)

```bash
# Runs before Claude Code writes a file
governor check "$FILE" --format json --slim
```

If the check finds anchor violations or spine violations, Claude Code sees the structured output and can self-correct before writing.

#### Post-Tool Hook (After File Write)

```bash
# Runs after Claude Code writes a file
governor check "$FILE" --format json --slim --post
```

Reports violations but doesn't block (Claude Code has already written). Logs for audit.

#### Session Start Hook

```bash
# Runs when Claude Code starts a session
governor slim status --json
```

Provides Claude Code with the current constraint surface — decisions, anchors, invariants, active spine. This is a lightweight version of constraint compilation (CONSTRAINT_COMPILER_SPEC.md) that fits in the system prompt.

### 2.4 Codex Integration

Codex operates differently — it runs sandboxed, doesn't have persistent hooks. Slim mode for Codex:

```bash
# In AGENTS.md or system prompt, include:
governor slim status --oneliner

# Output (fits in a system prompt preamble):
# DECISIONS: JWT auth, no ORM, React frontend (3 active)
# ANCHORS: no eval(), Elena green eyes (2 reject-severity)
# INVARIANTS: pytest must pass, __init__.py must exist
# SPINE: src/governor/ locked (no new files without .py)
```

Codex gets the constraints as text. The governor checks output post-hoc via `governor check`.

### 2.5 Slim Status View

```bash
$ governor slim status

Envelope: slim (single-developer)

Decisions (3):
  • Authentication uses JWT [topic: auth]
  • No ORM — raw SQL with parameterized queries [topic: database]
  • React frontend [topic: framework]

Anchors (2):
  • [reject] No eval() calls (scope: src/**)
  • [reject] Elena has green eyes (type: canon)

Invariants (2):
  • [test] python3 -m pytest tests/ -x
  • [file-exists] src/governor/__init__.py

Spine: src/governor/ (locked)

Last check: 2m ago — clean
```

One screen, everything that matters, no noise.

---

## 3. Decision Recording in Slim Mode

### 3.1 Direct Write

In slim mode, `governor decide` writes directly to the decision ledger without the propose/verify/apply dance:

```python
def decide(text: str, topic: str | None = None, retract: bool = False):
    """Record or retract a decision. No proposal FSM. Direct ledger write."""
```

This is safe because:
- Single developer = no adversarial claim injection
- Contradiction detection still runs (the ledger checks for conflicts)
- Retraction requires explicit `--retract` (no silent overwrites)
- Audit trail preserved (timestamp, text, who)

### 3.2 Contradiction Detection Survives

Even without proposals, the decision ledger still detects contradictions:

```bash
$ governor decide "Vue frontend" --topic framework
ERROR: Contradicts existing decision on 'framework':
  "React frontend" (recorded 2025-06-01)

Use --retract to retract the prior decision first, or --force to override.
```

The `--force` flag is deliberate — it records the override with a timestamp and reason, not silently.

### 3.3 Decision Sources

Decisions can come from:
- CLI (`governor decide "..."`)
- Claude Code conversation (via hook: "Record decision: ...")
- CLAUDE.md / AGENTS.md (parsed at session start)
- Spec files (anchor decisions extracted from specs)

---

## 4. Upgrade Path

### 4.1 Slim → Strict

When a project grows from solo to team, slim mode decisions and anchors are **fully compatible** with strict mode:

```bash
# Switch envelope
governor envelope strict

# Existing decisions become the decision ledger (already there)
# Existing anchors become the anchor registry (already there)
# Existing invariants become the invariant store (already there)
# New changes now require propose/verify/apply
```

No migration, no re-entry. Slim mode is a strict subset of strict mode.

### 4.2 Strict → Slim

Going the other direction (team → solo branch):

```bash
governor envelope slim
# Proposals in-flight are abandoned (warning emitted)
# Decision/anchor/invariant state preserved
# Single-dev workflow enabled
```

---

## 5. What Slim Mode Is Not

- **Not exploratory mode.** Exploratory mode relaxes evidence requirements but keeps the ceremony. Slim mode drops the ceremony but keeps the constraints.
- **Not ungoverned.** Decisions still detect contradictions. Anchors still block violations. Invariants still gate commits. Spines still lock structure. The governor is still a governor — it just doesn't make you fill out paperwork.
- **Not multi-agent.** If a second agent or developer enters the picture, upgrade to strict. Slim mode's trust model assumes one honest actor.
- **Not advisory.** `governor check` in slim mode still blocks on reject-severity anchors and failed invariants. The gate is real.

---

## 6. Design Constraints

1. **Zero new data structures.** Slim mode uses existing ledgers, anchors, invariants, spines. The only new thing is the CLI sugar and the envelope setting.
2. **Upgrade-safe.** Everything recorded in slim mode is valid strict-mode state. No migration needed.
3. **One-screen status.** The `slim status` view must fit in a terminal without scrolling. If it doesn't, you have too many constraints (which is its own signal).
4. **Hook-friendly.** Every slim operation must be expressible as a single CLI call with JSON output, suitable for Claude Code hooks.
5. **No new dependencies.** Pure CLI sugar over existing subsystems.

---

## 7. Integration Points

| Existing System | Slim Mode Interaction |
|----------------|----------------------|
| `claude_hooks.py` | Pre/post tool hooks call `governor check --slim` |
| `check.py` | Already works; slim mode adds decision/anchor context to output |
| `continuity.py` | Anchors created via `governor anchor` use existing AnchorRegistry |
| `spine.py` | `governor lock` is shorthand for spine lock + activate |
| `invariant_store.py` | `governor must-pass` / `governor must-exist` use existing InvariantStore |
| `ledgers.py` | `governor decide` writes directly to DecisionLedger |
| `CONSTRAINT_COMPILER_SPEC.md` | `slim status --json` is a lightweight constraint compilation |
| `telemetry.py` | Slim mode emits lightweight events (decision recorded, check ran, violation found) |

---

## 8. Relationship to Existing Specs

| Spec | Relationship |
|------|-------------|
| `CONSTRAINT_COMPILER_SPEC.md` | `slim status` is a minimal constraint projection; full compiler for multi-agent |
| `DETECTOR_INTEGRATION_SPEC.md` | Detector signals attach to slim-mode checks (supplementary evidence) |
| `COMMITMENT_TRANSPORT_SPEC.md` | Slim status output is itself a compression — transport validator can check it |
| `SPECTRAL_STABILITY_SPEC.md` | Solo developer = single-layer topology, ρ(M) trivially < 1 |
| `SCALAR_COLLAPSE_SPEC.md` | Slim mode's reduced metric surface is collapse-resistant by simplicity |

---

## 9. Open Questions

1. **Decision parsing from conversation.** Can Claude Code detect "let's use JWT for auth" in conversation and auto-suggest `governor decide`? This would make governance feel like note-taking, not ceremony. Risk: false positives on casual statements.

2. **Anchor inference from specs.** The 2.0 specs contain many implicit anchors ("hard block at ρ≥1", "compiler must be pure"). Should `governor slim seed --from specs/` extract these automatically?

3. **Pre-commit in slim mode.** Should the pre-commit hook enforce invariants (test gates) in slim mode? Argument for: prevents "I'll fix the tests later" drift. Argument against: slows iteration. Candidate: enforce on main branch, skip on feature branches.

4. **Slim mode for teams.** What if the team is small (2-3 people) and trusted? Is there a "slim-team" mode that keeps contradiction detection and adds lightweight attribution but still skips full ceremony? Or is that just exploratory mode with better UX?
