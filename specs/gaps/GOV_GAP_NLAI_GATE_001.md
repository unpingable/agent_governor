# GOV_GAP_NLAI_GATE_001: NLAI Kernel Extraction

**Status**: External ship only — `nlai 0.3.0` on PyPI in `~/git/nlai`. In-repo
extraction (Phase 1 `libs/nlai/`) and governor consumption (Phase 3) did NOT
happen. Governor still uses inline `canonical_json`, `Receipt`, claim
extraction. The kernel-boundary motivation remains live debt; the package
shipped, but the architectural seam it was meant to force has not been cut.
**Category**: Architecture / distribution
**Priority**: Medium — adoption vector satisfied externally; 3.x kernel
boundary still open

## What It Is

A standalone, zero-dependency Python library that implements the irreducible
NLAI mechanism: claims require evidence, decisions produce receipts, anchors
enforce continuity, violations resolve deterministically.

**Package name:** `nlai` (PyPI: `nlai`, import: `nlai`)

```python
from nlai import gate, Anchor

result = gate("All tests pass and the code is thread-safe.")
# result.verdict = "block"
# result.receipt.receipt_id = "sha256:..."
# result.claims = [("tests pass", UNSUPPORTED), ("thread-safe", UNSUPPORTED)]
```

This is not a "minimal governor." It is the kernel the governor builds on.
Same law, smaller jurisdiction.

## What It Is Not

- No daemon, no socket, no RPC
- No regime detection, homeostat, boil control, jurisdictions
- No routing, lanes, sybil resistance, puppet mode
- No writing modules, fiction/nonfiction governors
- No UI, CLI beyond maybe a one-command entry point
- No adaptive policy, no orchestration
- No external dependencies (stdlib only, like receipt_kernel)
- No `config` parameter on `gate()` in v0 (see design note below)

## Why

Two problems solved at once:

1. **Adoption**: "200K lines? I could use a regex." They're wrong, but the
   perception is real. `pip install nlai` with 1,000 lines and a 10-second
   demo kills the objection.

2. **Architecture**: 3.x needs a real kernel boundary anyway. Extracting now
   forces the boundary to be explicit rather than implicit.

## Public API

The entire surface:

```python
# The gate function — text in, verdict + receipt out
gate(text, *, anchors=None) -> GateResult

# Data types
GateResult(verdict, receipt, claims, violations)
Receipt(receipt_id, schema_version, gate, verdict, subject_hash, evidence_hash, timestamp)
Anchor(id, description, severity, constraint_class, required, forbidden)
Claim(text, status, evidence_kind)
Violation(anchor_id, description, severity)

# Utilities
canonical_json(obj) -> str
content_hash(data: bytes, *, alg="sha256") -> str
verify_receipt(receipt) -> bool
```

If the API needs more than this to feel whole, the boundary is too fuzzy.

### Design note: no `config` parameter in v0

The original draft had `gate(text, *, anchors=None, config=None)`. The `config`
slot is where half the runtime sneaks back in via import side-effect wearing
sunglasses. Removed for v0. If configuration becomes necessary, it must be a
small frozen dataclass with an explicit, short field list — not an open dict.

## Semantic Invariants

These are non-negotiable. The kernel must not be a reinterpretation.

1. **Same receipt hashing** — `canonical_json` produces identical output to
   `governor.gate_receipt.canonical_json`. Same sort order, same separators,
   same encoding. Golden fixtures shared.

2. **Same verdict semantics** — "block" means block, "pass" means pass,
   "observe" means observe. No "lite mode" weaker verdicts.

3. **Same anchor/violation meaning** — an anchor violation in nlai
   means the same thing as in governor. Same severity levels, same
   constraint classes (invariant vs preference).

4. **Same claim extraction** — see Claim Extraction Boundary below.

5. **Receipt identity** — `receipt_id = H(canonical_json(hashable fields))`.
   Content-addressed, timestamp excluded. Same as governor.

6. **Receipt schema version** — `Receipt` includes `schema_version: int`
   from the first release. `to_dict()` emits it, `from_dict()` rejects
   future versions. This is non-negotiable before PyPI publication.

## Claim Extraction Boundary

Governor's `claim_signals.py` extracts 4 signal types: assertive statements,
dates/temporal, entities/quantities, and hedged/qualified claims. The kernel
extracts **assertive statements only** (the core "is this a claim?" check).

v0 claim classes:

| Class | Included | Example |
|-------|----------|---------|
| `ASSERTIVE` | Yes | "Tests pass", "The code is thread-safe" |
| `HEDGED` | Yes (detected, classified as weak) | "I think tests pass" |
| `DATE_TEMPORAL` | No (governor-only) | "Updated yesterday" |
| `ENTITY_QUANTITY` | No (governor-only) | "Handles 10k requests" |

Compatibility contract: any text that nlai classifies as `ASSERTIVE` must
also be classified as assertive by governor's `SignalExtractor`. The reverse
is not required (governor may extract more). nlai is a **strict subset**,
not a reinterpretation.

If nlai says "this is a claim," governor must agree. If nlai says "no claim
found," governor may still find one (via entity/quantity/temporal extraction).
This is a one-way compatibility requirement.

## Source Files to Extract From

| nlai module | Governor source | What to extract |
|-------------|----------------|-----------------|
| `canonical.py` | `gate_receipt.py` | `canonical_json`, content hashing |
| `receipt.py` | `gate_receipt.py` | `Receipt` (with schema_version), `create_receipt` |
| `gate.py` | `evidence_gate.py` | `check()` core logic, claim extraction |
| `anchors.py` | `continuity.py` | `Anchor` dataclass, `check_text()` |
| `resolver.py` | `violation_resolver.py` | `Violation`, resolution actions |
| `claims.py` | `claim_signals.py` | Assertive statement detection only |

## What Gets Simplified

- `EvidenceGate` has oracle integration, custody scoring, exit shape checking.
  The kernel gets: claim extraction + anchor checking + receipt emission.
  No oracles in v0 (oracles are governor-runtime concerns).

- `continuity.py` has CorrectionLadder, ConvergenceExecutor, mode-specific
  bridges. The kernel gets: Anchor dataclass + **lexical anchor matching**
  (required/forbidden substring and pattern checks against text).

- `violation_resolver.py` has persistent state, exception records, interactive
  resolution. The kernel gets: Violation dataclass + verdict determination.

- `claim_signals.py` has date/entity/quantity extraction. The kernel gets:
  assertive statement detection only (see Claim Extraction Boundary above).

## Test Strategy

### Golden fixture sharing

Governor's golden fixtures for receipt hashing and canonical JSON are
**vendored into nlai's test suite as snapshot copies**. This means:

- `libs/nlai/tests/fixtures/` contains copies of the relevant governor goldens
- A CI job in governor verifies nlai goldens match governor goldens (parity check)
- nlai's own test suite is fully standalone (no governor import)
- When governor updates a golden, the CI parity check fails, forcing an
  explicit update in nlai (not silent drift)

### Test categories

- `test_canonical.py` — determinism, hash stability, golden bytes
- `test_receipt.py` — create, verify, content-addressing, schema_version
- `test_gate.py` — verdict correctness, claim detection, anchor violations
- `test_anchors.py` — lexical matching, severity, constraint_class
- `test_golden.py` — vendored fixture parity with governor
- `test_roundtrip.py` — serialize/deserialize, future version rejection

### Compatibility property

`nlai.gate(text)` must produce the same verdict as `governor gate check text`
when both have the same anchors and the text contains only assertive claims.
Texts with entity/quantity/temporal claims may differ (governor extracts more).

## File Layout

```
libs/nlai/
├── pyproject.toml              # stdlib-only, zero deps
├── README.md                   # The 10-second demo
├── src/nlai/
│   ├── __init__.py             # gate, Anchor, Receipt, Claim, Violation
│   ├── canonical.py            # canonical_json, content_hash
│   ├── receipt.py              # Receipt, create_receipt, verify_receipt
│   ├── gate.py                 # gate() — the one function
│   ├── anchors.py              # Anchor, check_text (lexical matching)
│   ├── claims.py               # assertive statement detection
│   └── resolver.py             # Violation, verdict from violations
└── tests/
    ├── fixtures/               # Vendored golden snapshots from governor
    ├── test_canonical.py       # Determinism, hash stability
    ├── test_receipt.py         # Create, verify, content-addressing
    ├── test_gate.py            # Verdict correctness, claim detection
    ├── test_anchors.py         # Lexical matching, severity
    ├── test_golden.py          # Fixture parity with governor
    └── test_roundtrip.py       # Serialize/deserialize
```

## Relationship to Governor

Governor depends on nlai (or re-exports from it). Not the reverse.

```
nlai (kernel)
    ↑
governor (runtime + policy + orchestration)
    ↑
plugins / clerk / phosphor (distribution surfaces)
```

Phase 1: extract into `libs/nlai/` (same repo, like receipt_kernel).
Phase 2: if boundary is stable, publish to PyPI as `nlai`.
Phase 3: governor imports from nlai instead of inline.

## Naming

`nlai` on PyPI. `nlai` as Python package. Four letters, thesis on the tin.

Not "mini-governor", not "governor-lite", not "governor-core."
The name IS the principle: language is a proposal, not an authority.

The README subtitle does the explanatory work the name doesn't:
**"NLAI: evidence-gated claims, continuity anchors, and receipts for agent
workflows."**

## Anti-Goals

- **No behavior drift** — the kernel is not a reinterpretation of governor
  semantics. It is the same semantics with less machinery.
- **No forked docs** — "this is the kernel the governor builds on" is the
  story everywhere. One concept, two scopes.
- **No "lite mode"** — verdicts are verdicts. No weaker enforcement because
  the package is smaller.
- **No clever demo syntax** over semantic clarity. Auditability > ergonomics.
- **No config smuggling** — no open dict/kwargs that let the runtime sneak
  back in. Frozen dataclass or nothing.

## Estimated Scope

- ~1,000 lines of implementation (extracted + simplified)
- ~500 lines of tests
- Weekend-sized job — the hard code already exists
- The spec is the hard part (this document)

## Origin

Identified during v2.7.0 plugin dogfooding. The 200K-line repo is an adoption
barrier. The NLAI thesis is simple enough to fit in a tiny library. The 3.x
architecture needs this boundary anyway. Solving both at once.
