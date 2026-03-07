# GOV_GAP_NLAI_GATE_001: NLAI Gate Kernel Extraction

**Status**: Scoped, ready to extract
**Category**: Architecture / distribution
**Priority**: High — adoption vector + 3.x kernel boundary

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
gate(text, *, anchors=None, config=None) -> GateResult

# Data types
GateResult(verdict, receipt, claims, violations)
Receipt(receipt_id, gate, verdict, subject_hash, evidence_hash, timestamp)
Anchor(id, description, severity, constraint_class, required, forbidden)
Claim(text, status, evidence_kind)
Violation(anchor_id, description, severity)

# Utilities
canonical_json(obj) -> str
content_hash(data: bytes, *, alg="sha256") -> str
verify_receipt(receipt) -> bool
```

If the API needs more than this to feel whole, the boundary is too fuzzy.

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

4. **Same claim extraction** — uses the same signal extraction logic
   (or a simplified subset that is strictly compatible).

5. **Receipt identity** — `receipt_id = H(canonical_json(hashable fields))`.
   Content-addressed, timestamp excluded. Same as governor.

## Source Files to Extract From

| nlai module | Governor source | What to extract |
|-----------------|----------------|-----------------|
| `canonical.py` | `gate_receipt.py` | `canonical_json`, content hashing |
| `receipt.py` | `gate_receipt.py` | `GateReceipt` (simplified), `create_receipt` |
| `gate.py` | `evidence_gate.py` | `check()` core logic, claim extraction |
| `anchors.py` | `continuity.py` | `Anchor` dataclass, `check_text()` |
| `resolver.py` | `violation_resolver.py` | `Violation`, resolution actions |
| `claims.py` | `claim_signals.py` | `SignalExtractor` (simplified) |

## What Gets Simplified

- `EvidenceGate` has oracle integration, custody scoring, exit shape checking.
  The kernel gets: claim extraction + anchor checking + receipt emission.
  No oracles in v0 (oracles are governor-runtime concerns).

- `continuity.py` has CorrectionLadder, ConvergenceExecutor, mode-specific
  bridges. The kernel gets: Anchor dataclass + simple text matching.

- `violation_resolver.py` has persistent state, exception records, interactive
  resolution. The kernel gets: Violation dataclass + verdict determination.

- `claim_signals.py` has date/entity/quantity extraction. The kernel gets:
  assertive statement detection (the core "is this a claim?" check).

## Test Strategy

- Golden fixtures shared with governor (same inputs → same receipts/verdicts)
- Extraction is correct iff `nlai.gate(text)` produces the same verdict
  and compatible receipt as `governor gate check text`
- Standalone test suite (no governor dependency in tests)
- Property: `canonical_json` determinism (same as governor's existing tests)

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
│   ├── anchors.py              # Anchor, check_text
│   ├── claims.py               # claim extraction (simplified)
│   └── resolver.py             # Violation, verdict from violations
└── tests/
    ├── test_canonical.py       # Determinism, hash stability
    ├── test_receipt.py         # Create, verify, content-addressing
    ├── test_gate.py            # Verdict correctness, claim detection
    ├── test_anchors.py         # Anchor matching, severity
    ├── test_golden.py          # Shared fixtures with governor
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

## Anti-Goals

- **No behavior drift** — the kernel is not a reinterpretation of governor
  semantics. It is the same semantics with less machinery.
- **No forked docs** — "this is the kernel the governor builds on" is the
  story everywhere. One concept, two scopes.
- **No "lite mode"** — verdicts are verdicts. No weaker enforcement because
  the package is smaller.
- **No clever demo syntax** over semantic clarity. Auditability > ergonomics.

## Estimated Scope

- ~1,000 lines of implementation (extracted + simplified)
- ~500 lines of tests
- Weekend-sized job — the hard code already exists
- The spec is the hard part (this document)

## Origin

Identified during v2.7.0 plugin dogfooding. The 200K-line repo is an adoption
barrier. The NLAI thesis is simple enough to fit in a tiny library. The 3.x
architecture needs this boundary anyway. Solving both at once.
