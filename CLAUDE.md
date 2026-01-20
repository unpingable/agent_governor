# CLAUDE.md - Instructions for Claude Code

## Project Overview

This is the **Epistemic Governor** - a constraint system for agentic coding tools. The irony is not lost: you're building the tool that will eventually constrain you.

Current state: proof-of-concept (`src/governor/`). Target state: write-gating CLI (`BUILD_SPEC.md`).

## Build Commands

```bash
# Install in dev mode
pip install -e . --break-system-packages

# Run tests
pytest tests/ -v

# Run demo
python demo.py
```

## Architecture Rules (Non-Negotiable)

1. **NLAI: Language is a proposal, not an authority.**
   - Agents provide *pointers* (file paths, commands to run)
   - Governor produces *receipts* (hashed proof of verification)
   - Never trust agent-provided "evidence"

2. **Gate, not memory.**
   - The goal is write-blocking, not advisory logging
   - No file mutations without verified proposals
   - If it can be routed around, it will be

3. **Two ledgers: facts vs decisions.**
   - `facts/` = empirical, auto-decays when files change
   - `decisions/` = normative, persists until explicitly revised
   - Don't mix these. "Tests pass" is a fact. "We use React" is a decision.

4. **Typed claims, not prose.**
   - Claims are structured: `ClaimType.FILE_EXISTS`, `ClaimType.TESTS_PASS`, etc.
   - No free-form string assertions
   - If the claim type doesn't exist, add it to the enum first

## File Structure

```
src/governor/
├── __init__.py      # Public API exports
├── core.py          # AgentGovernor class (v0.1, will be refactored)
├── ledger.py        # CodebaseLedger (v0.1, will split to facts/decisions)
├── validators.py    # Evidence validators (v0.1, will become verifiers)
├── types.py         # Data classes, enums
│
# To be added per BUILD_SPEC.md:
├── receipts.py      # FileSnapshot, CmdRun, DiffReceipt
├── producers.py     # Receipt-producing functions
├── claims.py        # ClaimType enum, Claim dataclass
├── ledgers.py       # FactLedger, DecisionLedger (replaces ledger.py)
├── fsm.py           # State machine: DRAFT→PROPOSE→VERIFY→APPLY
├── verifiers.py     # Receipt-producing verifiers (replaces validators.py)
└── cli.py           # Click CLI: governor init/propose/verify/apply
```

## Current Task Sequence

Follow `BUILD_SPEC.md` steps in order. Each step has a testable artifact.

**Phase 1 (Weekend MVP):**
1. Receipt objects → `receipts.py`
2. Receipt producers → `producers.py`
3. Typed claims → `claims.py`
4. Split ledgers → `ledgers.py`
5. FSM → `fsm.py`
6. Verifiers → `verifiers.py`
7. CLI skeleton → `cli.py`

Don't skip ahead. Each step depends on the previous.

## Code Conventions

- Python 3.10+ (use `|` for union types, not `Union`)
- Dataclasses for all data objects
- Type hints everywhere
- No runtime dependencies beyond stdlib (except Click for CLI)
- Tests go in `tests/test_<module>.py`

## Common Mistakes to Avoid

1. **Don't let agents provide evidence directly.**
   ```python
   # WRONG - agent can lie
   def propose(claim: str, evidence: Evidence): ...
   
   # RIGHT - agent provides pointers, governor verifies
   def propose(claim: Claim, pointers: list[str]): ...
   ```

2. **Don't use free-form strings for claims.**
   ```python
   # WRONG - unstructured, hard to validate
   propose(claim="I think the tests pass")
   
   # RIGHT - typed, machine-checkable
   propose(claim=Claim(type=ClaimType.TESTS_PASS, command=["pytest"]))
   ```

3. **Don't mix facts and decisions.**
   ```python
   # WRONG - treating preference as theorem
   facts.add("we use React")
   
   # RIGHT - normative choice in decisions ledger
   decisions.add(Decision(topic="framework", choice="react"))
   ```

4. **Don't make it advisory.**
   ```python
   # WRONG - can be ignored
   if not governor.approve(patch):
       logger.warning("Governor rejected patch")
       apply_patch_anyway(patch)  # oops
   
   # RIGHT - gate is mandatory
   if not governor.approve(patch):
       raise GovernorRejection(patch, reason)
   ```

## Testing Philosophy

Every new module needs tests that prove:
1. Happy path works
2. Invalid input is rejected with clear error
3. Edge cases are handled (empty input, missing files, etc.)

Run tests after every change: `pytest tests/ -v`

## Git Conventions

- Commit messages: `[module] description`
- Example: `[receipts] add FileSnapshot dataclass`
- Don't commit `.governor/rejections.log` (it's local debugging)

## When You're Stuck

1. Re-read `BUILD_SPEC.md` for the step you're on
2. Check `demo.py` for how the v0.1 API works
3. Look at `tests/test_governor.py` for examples
4. The existing code in `core.py`, `ledger.py`, `validators.py` is v0.1 - it works but will be refactored

## The Meta-Constraint

You are building a tool to constrain AI coding agents. Apply its principles to yourself:
- Don't claim a file exists without checking
- Don't claim tests pass without running them
- Don't contradict architectural decisions in BUILD_SPEC.md
- Cite your receipts.
