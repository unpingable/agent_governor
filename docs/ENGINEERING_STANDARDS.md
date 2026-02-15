# Engineering Standards

Standards for the Agent Governor codebase. If it isn't enforced by tooling or a review checklist, it doesn't belong here.

## 1. Non-Negotiable Invariants

These are project-specific. Violating any of these is a blocking defect.

**Authority never lives in the UI.**
UI sends intent; the daemon/server derives and validates authority. `principal_id` defaults to `"local"` server-side. No client-supplied authority field is trusted.

**Absence is restrictive.**
A missing axis means locked, not open. Wildcard must be explicit `"*"`. No implicit permissioning via `.get()` defaults on authority-bearing fields.

**Escalation is one axis, one rung.**
Multi-axis widening in a single request must be split or denied. The expanding-rings ladder (`resource → service → region → environment → tenant`) defines the rungs.

**Time is typed.**
ISO 8601 UTC with `Z` suffix (no local offsets). Interval inclusion is explicit (`start < end`, both bounds stated). Canonical format: `datetime.now(timezone.utc).isoformat()`. Timestamps are metadata, never identity (not part of content-addressed hashes).

**Every persisted blob has `schema_version`.**
`to_dict()` writes it. `from_dict()` checks it: reject `v > CURRENT` with `ValueError`; handle `v < CURRENT` with explicit migration or safe defaults. No silent `.get()` defaults for normative fields.

**Receipts use canonical JSON and deterministic hashing.**
All hashing goes through `canonical_json()` (sorted keys, compact separators, ASCII-safe). `subject_hash` includes a kind tag. Nondeterministic fields (timestamps, UUIDs) are metadata, never identity.

## 2. Toolchain

| Tool | Purpose | Config |
|------|---------|--------|
| ruff | Linter + formatter | `pyproject.toml [tool.ruff]` |
| pytest | Tests | `pyproject.toml [tool.pytest.ini_options]` |
| pre-commit | Hook runner | `.pre-commit-config.yaml` (TODO) |

### CI Gates (all must pass to merge)

```
ruff check src/ tests/            # Lint
ruff format --check src/ tests/   # Format
python3 -m pytest tests/ -x -q    # Tests
```

### Planned (not yet enforced)

- `mypy --strict` on kernel modules (`gate_receipt`, `scope`, `correlator_telemetry`, `daemon`, `evidence_gate`, `continuity`)
- `pre-commit` hook config wiring ruff + pytest smoke

### Ruff Configuration

Target: Python 3.10+, 100-char line length. Current lint rules select `"F"` (pyflakes). Expand to include:

```toml
select = [
    "F",    # pyflakes
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "I",    # isort
    "UP",   # pyupgrade (e.g., use | union syntax)
]
```

This is the floor. Add rules when they catch real bugs; remove rules that produce only noise.

## 3. Serialization and Schema Rules

Every module that persists state to disk follows the same pattern:

### Writing

```python
MYMODULE_SCHEMA_VERSION = 1

def to_dict(self) -> dict[str, Any]:
    return {
        "schema_version": MYMODULE_SCHEMA_VERSION,
        # ... fields
    }
```

### Reading

```python
@classmethod
def from_dict(cls, d: dict[str, Any]) -> MyModule:
    v = d.get("schema_version", 0)  # Missing → legacy v0
    if v > MYMODULE_SCHEMA_VERSION:
        raise ValueError(
            f"... schema version {v} is newer than supported "
            f"({MYMODULE_SCHEMA_VERSION}). Upgrade governor."
        )
    if v < MYMODULE_SCHEMA_VERSION:
        logger.debug("Migrating ... from v%d to v%d", v, MYMODULE_SCHEMA_VERSION)
    # ... explicit field extraction with typed defaults
```

### Rules

- `schema_version` is always an integer, always present in serialized output.
- Future versions hard-fail. Old versions migrate or use explicit defaults.
- `.get()` with a default is fine for optional metadata (e.g., `principal_id`) **only if the default cannot affect a gate verdict**. Yes/no test: "Could changing this default flip a pass to a block?" If yes, it's normative — extract it explicitly and fail on missing.
- Canonical JSON (`canonical_json()` from `gate_receipt.py`) is the only serialization path for anything that gets hashed. Never `json.dumps()` ad-hoc for hash inputs.
- Bump `schema_version` when you change the field set or semantics. Don't bump for additive optional metadata.

### Enforcement

These rules are mechanically enforced by `tests/test_standards.py`:

- **Schema version tripwire**: Any module with a `_SCHEMA_VERSION` constant must be registered in the test. The test verifies `to_dict()` emits it and `from_dict()` rejects future versions.
- **Authority default guard**: Kernel modules are scanned for `.get()` calls on authority-bearing fields (`verdict`, `allowed`, `severity`, `required`, `forbidden`, `constraint_class`, `risk_level`). Unreviewed defaults fail the test; reviewed-safe usages go in an explicit allowlist with expiry dates. Expired allowlist entries fail until re-reviewed.
- **Doc-test sync**: The test verifies this doc mentions every registered versioned type and has a Known Gaps section.

### Versioned Types (enforced)

| Module | Constant | Class |
|--------|----------|-------|
| `gate_receipt` | `RECEIPT_SCHEMA_VERSION` | `GateReceipt` |
| `correlator_telemetry` | `CORRELATOR_SCHEMA_VERSION` | `CorrelatorTelemetry` |
| `scope` | `SCOPE_SCHEMA_VERSION` | `ScopeGovernor` |
| `semantic_stability` | `STABILITY_SCHEMA_VERSION` | `StabilityAuditResult` |

### Known Gaps

11 older persisted types (`EpistemicLedger`, `RegimeDetector`, `ScarLedger`, `PuppetRegistry`, `IntentFormSchema`, `AnchorRegistry`, `Capsule`, `TelemetryEvent`, `ResearchLedger`, `AutoTuner`, `ExecutionState`) predate the schema version discipline. They have `to_dict`/`from_dict` but no `schema_version`. These are tracked as backlog — add versioning when each module is next modified.

## 4. Testing Standards

### Naming

Test names state the invariant or denial reason:

```python
def test_absence_restrictive_missing_axis_denied(self): ...
def test_axis_smuggling_rejected(self): ...
def test_future_schema_version_rejected(self): ...
def test_escalation_two_axes_denied(self): ...
```

Not: `test_scope_1`, `test_check_works`, `test_basic`.

### Required Coverage Per Gate/Module

| Category | Required |
|----------|----------|
| Allow path (happy path) | At least one |
| Deny path (each denial reason) | One per structured denial reason |
| Edge cases (empty input, boundary values) | At least one |
| Roundtrip (serialize → deserialize → equal) | One if persisted |
| Schema version (legacy load, future rejection) | One each if persisted |

### Test Categories

- **Unit tests**: One module, mocked dependencies. The default.
- **Scenario tests**: Multi-step workflows (propose → escalate → use → receipt). Named `TestScenarios` or `TestEndToEnd`.
- **Property tests**: Containment, hashing determinism, idempotency. Use where combinatorics matter.
- **Smoke tests**: `@pytest.mark.smoke`. Subprocess + real filesystem. Must pass on fresh clone.
- **Scale tests**: `@pytest.mark.scale`. Performance bounds. Generous thresholds.

### Anti-Patterns

- Don't test framework behavior (e.g., "does dataclass equality work").
- Don't write tests that only pass when external services are running (mark `skipUnless`).
- Don't use `time.sleep()` for synchronization; use events or polling with timeout.

## 5. Code Conventions

- Python 3.10+. Use `X | Y` for unions, not `Union[X, Y]`.
- Dataclasses for all data objects. `frozen=True` for receipts and immutable state.
- Type hints on all public functions. Internal helpers: use judgment.
- No wildcard imports. No circular imports at module level.
- Imports: stdlib → third-party → local. Let `ruff` (`I` rules) sort them.
- Logging: `logger = logging.getLogger(__name__)` at module top. No `print()` in library code.
- Errors: structured `ValueError`/`TypeError` with a message that names the constraint violated. No bare `raise Exception`.

## 6. PR Checklist

Before marking a PR ready for review:

- [ ] `ruff check` and `ruff format --check` pass
- [ ] All new/modified tests pass (`pytest -x`)
- [ ] No new `.get()` defaults on authority-bearing or normative fields
- [ ] Persisted state includes `schema_version` with `from_dict` enforcement
- [ ] Deny paths tested (not just happy paths)
- [ ] Receipts emitted for gate decisions (no silent discard)
- [ ] Daemon RPC method count in `daemon.py` comment matches reality
- [ ] `implementation-summary.md` updated if adding a new module/feature

## 7. Definition of Done

A new gate, policy module, or persisted subsystem is done when:

1. Invariants are listed (what it enforces, what it rejects).
2. Denial reasons are structured (enum or constant, not free-form strings).
3. Receipt fields are defined (gate name, verdict values, subject_kind).
4. Schema versioning is included if any state is persisted.
5. Tests cover: allow + each deny reason + edge cases + roundtrip.
6. CLI commands (if any) are documented in `.claude/rules/cli-reference.md`.
7. Daemon RPC methods (if any) are wired and tested at handler level.
