# Verified Kernel

A pure, deterministic, mechanically verifiable core for receipt math.

status: v2 work shipped (HashRef 25 tests, NaN hardening 5 tests); remaining architecture is v3

---

## Problem

The governor has five independent `canonical_json` implementations:

| Module | `allow_nan` | Hash format | Float policy | Unicode |
|--------|-------------|-------------|--------------|---------|
| `gate_receipt.py` | **missing** (default True) | bare hex | allows | no normalization |
| `signals/envelope.py` | **missing** (default True) | `sha256:` prefix | allows | no normalization |
| `receipt_kernel/envelope.py` | `False` | both (prefixed + raw) | allows | no normalization |
| `receipt_v1/canonical.py` | `False` | domain-separated | **forbids all floats** | no normalization |
| `r2wire/canonical.py` | `False` | prefixed | allows | **NFC normalization** |

Three of five get `allow_nan` right. Two don't. The hash prefix convention
disagrees across modules. Float policy ranges from "anything goes" to "hard
reject." Unicode normalization exists in exactly one place.

These are not minor style differences. They break the one property
canonical JSON exists to guarantee: **the same semantic object produces the
same bytes, always, everywhere.**

Today this doesn't cause bugs because the modules don't cross-reference
each other's hashes. But the signal plane wires signals to receipts to
activities. The moment a receipt hash computed in `gate_receipt.py` needs
to match a hash computed in `signals/envelope.py`, the divergence becomes
a bug. That moment is coming.

The deeper problem: there is no *specification* for what "canonical" means
in this system. Each module reinvented it from `json.dumps` kwargs. The
specification is the code, and the code disagrees with itself.

---

## Prior Art

**JCS (RFC 8785)**: JSON Canonicalization Scheme. Defines deterministic
JSON serialization including numeric representation (ES6 `Number.toString`
rules). Solves the float canonicalization problem but drags in a complex
number-to-string algorithm.

**CBOR (RFC 8949)**: Binary encoding with deterministic profile (Core
Deterministic Encoding). Compact, unambiguous, but not human-inspectable.
Requires CBOR libraries in every implementation language.

**Receipt Kernel invariants**: the existing 13 invariants
(`libs/receipt_kernel/src/receipt_kernel/invariants/`) already demonstrate
the pattern — pure functions checking structural properties of data,
no IO. The verified kernel generalizes this pattern to all receipt math.

**Relational invariants** (`specs/gaps/RELATIONAL_INVARIANTS.md`): the
7th invariant class, cross-trace ∀∃ properties. Orthogonal to this spec
but shares the design principle: name the category, carve the boundary,
don't build machinery yet.

---

## What "Verified" Means (and What It Doesn't)

The word "verified" here means **mechanically checkable conformance**,
not formal proof of correctness. Specifically:

1. **Deterministic**: same inputs → same outputs, always. No hidden state,
   no system clock, no randomness, no IO.

2. **Pure**: the kernel is a function from bytes to bytes. It does not
   read files, query databases, or emit signals. Callers do IO; the
   kernel does math.

3. **Canonical**: there is exactly one valid byte representation for each
   semantic value. Two implementations that produce different bytes for
   the same value are *both wrong* until one is designated canonical.

4. **Total**: every input produces either a valid output or a structured
   error. No panics, no undefined behavior, no "it depends on the
   parser."

5. **Conformance-tested**: a suite of test vectors (input bytes →
   expected output bytes) defines correctness. An implementation passes
   if and only if it produces the expected bytes for every vector.

6. **Cross-implementation**: the vectors are language-independent. Python
   and Rust (or any future implementation) must byte-agree on every
   vector. CI enforces this.

What this is *not*:

- Not a rewrite. The kernel extracts and pins what already exists.
- Not formal verification in the theorem-prover sense (that's the far end
  of the assurance ladder, not the first rung).
- Not a new type system. The kernel operates on bytes and dicts.
- Not a runtime dependency change. The kernel is stdlib-only, like
  `receipt_kernel` today.

---

## Kernel Boundary

The kernel contains exactly the functions where **determinism is a
correctness requirement**, not a nice-to-have:

### In the kernel

| Function | Current location | Why kernel |
|----------|-----------------|------------|
| `canonical_json` | 5 copies (see table above) | Hash identity depends on it |
| `content_hash` | 5 copies | Receipt identity |
| `subject_hash` | `gate_receipt.py` | Domain separation |
| `policy_hash` | `gate_receipt.py` | Config identity |
| `compute_receipt_id` | `gate_receipt.py` | Receipt identity algebra |
| `stage_transition` | `receipt_kernel/stages.py` | FSM is pure + total |
| `seal_envelope` | `receipt_kernel/envelope.py` | Hash-chain integrity |
| `verify_chain` | `receipt_kernel/invariants/` | Chain validation |

### Not in the kernel

| Function | Why not |
|----------|---------|
| `JsonlSink.emit()` | IO (file append) |
| `SignalStore.ingest()` | IO (SQLite, file read) |
| `ReceiptStore.append()` | IO (file write) |
| `EvidenceStore.put()` | IO (file write) |
| Signal derivation functions | Pure, but domain-specific — not receipt math |
| Policy evaluation | Involves configuration, not canonical math |

The kernel is the **receipt math core**. Everything that computes
identity, verifies chains, or enforces stage transitions. Everything
else is plumbing.

---

## Normative Rules

### K1. Strict JSON only

`allow_nan=False` everywhere, no exceptions. NaN, Infinity, and
-Infinity are not valid JSON (RFC 8259 §6). Any input containing them
must be rejected at parse time with a structured error, not silently
serialized into non-portable bytes.

### K2. Numeric policy: integers only in hash-relevant payloads

Floats are a portability hazard. `0.1 + 0.2 ≠ 0.3` is not a joke,
it's a hash collision waiting to happen. The kernel forbids non-integer
JSON numbers in any payload that participates in identity computation.

If you need ratios or metrics, represent them as:
- Integer numerator + integer denominator
- Fixed-point integers with explicit scale (e.g., microseconds, ppm)
- Decimal strings with a strict grammar (as JSON strings, not numbers)

`receipt_v1` already enforces this. The other modules need to catch up.

**Transition note**: signals use `value: float | None` extensively.
These values are *not* hash-relevant today (the envelope's identity is
computed from `to_canonical_bytes()` which includes the float). In 3.x,
signal values should move to fixed-point or be explicitly excluded from
hash computation. In 2.x, the pragmatic fix is `allow_nan=False` and
accept that float canonicalization is "good enough" within a single
Python version.

### K3. Hash representation: typed, prefixed, lowercase

One format: `sha256:<lowercase-hex>`. No bare hex. No uppercase. No
truncation. No "sometimes we prefix."

Domain separation (e.g., `subject_hash` prepending a kind tag) is
mandatory where cross-type collision is possible, and the separator byte
(`\x00`) is part of the spec.

### K4. Duplicate keys: reject

JSON objects with duplicate keys have parser-dependent semantics.
The kernel rejects them. (Python's `json.loads` silently takes the last
value. That's not canonical — it's an accident.)

### K5. Unicode: UTF-8, no normalization (for now)

Current state: 4 of 5 implementations do no normalization; `r2wire` does
NFC. The kernel stance: UTF-8 bytes as-is, no normalization. This means
the same logical string in NFC vs NFD form produces different hashes.
That's acceptable because:

- Receipt payloads are machine-generated (no user-typed Unicode)
- Signal IDs and field names are ASCII
- The alternative (mandatory NFC) adds a dependency and a failure mode

If cross-system Unicode interop becomes a real problem (not a theoretical
one), revisit. Until then: bytes are bytes.

### K6. Receipt ID is a closed computation

`receipt_id = H(schema_version + gate + subject_hash + evidence_hash +
policy_hash)`. The field set, field order, separator, and encoding are
part of the specification. Any change requires a schema version bump.

---

## Wire Format (3.x)

The kernel speaks bytes. Not Python dicts, not Rust structs — bytes.

A wire format makes the kernel auditable as a **protocol**, not a
codebase. It converts "some Python module forgot `allow_nan`" into
"input doesn't parse under kernel rules," which is the correct failure
mode.

### Message structure

```
KernelRequest:
  kernel_version: str
  message_type: enum (CANONICALIZE, COMPUTE_HASH, COMPUTE_RECEIPT_ID,
                       VERIFY_CHAIN, TRANSITION_STAGE)
  payload: bytes (must satisfy canonical encoding contract)

KernelResponse:
  kernel_version: str
  message_type: enum
  status: OK | ERROR
  error_code: int | None     (stable, numeric, part of spec)
  error_tag: str | None      (stable, short, part of spec)
  diagnostic: str | None     (non-normative, for humans)
  result: bytes | None
```

### Encoding choice

Canonical JSON (JCS-aligned) as wire format. Rationale:

- Human-inspectable (critical for a governance system)
- Already aligned with existing design
- Test vector generation is trivial
- Parsing cost is acceptable (kernel calls are not on the hot path)

CBOR is a valid alternative if performance matters. The key is not the
format — it's the **normative encoding spec + vectors**.

### Error codes (stable forever)

```
E001  INVALID_JSON           input is not valid JSON
E002  NAN_OR_INF             input contains NaN/Infinity
E003  DUPLICATE_KEY          input contains duplicate object keys
E004  FLOAT_IN_HASH_PAYLOAD  non-integer number in hash-relevant field
E005  UNKNOWN_MESSAGE_TYPE   unrecognized message type
E006  INVALID_STAGE          stage transition not in graph
E007  CHAIN_BROKEN           hash chain verification failed
E008  MISSING_FIELD          required field absent
E009  VERSION_MISMATCH       kernel version incompatible
```

---

## Conformance Vectors

Test vectors are the specification. An implementation is correct if and
only if it produces the expected output bytes for every vector.

### Derived from audit findings

| Vector class | What it tests | Motivated by |
|--------------|---------------|--------------|
| NaN/Inf rejection | K1 | `gate_receipt.py` and `signals/envelope.py` missing `allow_nan=False` |
| Hash prefix normalization | K3 | bare hex vs `sha256:` prefix disagreement |
| Float rejection in hash payloads | K2 | `receipt_v1` forbids, others allow |
| Duplicate key rejection | K4 | no module checks today |
| Domain-separated hashing | K3 | `subject_hash` vs bare `content_hash` |
| Receipt ID stability | K6 | schema version + field order pinning |
| Stage transition totality | FSM | every (state, event) pair has defined output |
| Chain integrity | chain | tamper detection on modified events |
| Canonical JSON round-trip | K1 | parse → canonical → parse must be identity |
| Unicode byte stability | K5 | NFC vs NFD producing different hashes |

### Vector format

```json
{
  "vector_id": "K1-nan-reject-001",
  "category": "canonical_json",
  "input": {"value": "NaN"},
  "expected_error": "E002",
  "note": "NaN is not valid JSON. Must reject, not serialize."
}
```

Vectors live in `tests/vectors/kernel/` as JSON files. CI runs them
against every implementation.

---

## Assurance Ladder

Not all assurance is equal. The ladder is ordered by cost and confidence:

| Rung | Method | What it catches | Status |
|------|--------|-----------------|--------|
| 0 | Unit tests | Basic correctness | **exists** (89 tests in receipt_kernel) |
| 1 | Golden vectors | Cross-impl disagreement | **partial** (canonical_json goldens exist) |
| 2 | Property-based tests | Edge cases humans miss | **partial** (some in strategic tests) |
| 3 | Differential fuzzing | Input-dependent divergence | **not started** |
| 4 | Model checking | State space exhaustion (FSM) | **not started** |
| 5 | Deductive proof | Mathematical certainty | **not started** (Rust + Kani or similar) |

3.x target: rungs 0–3 mandatory, rung 4 for the FSM (finite state space
makes it tractable). Rung 5 is aspirational and depends on the Rust
kernel existing.

---

## Cross-Implementation CI

The power move: Python is the **reference semantics**, Rust is the
**reference verifier**. Both speak the same wire format. CI runs
differential checks on raw bytes.

```
tests/vectors/kernel/*.json
      │
      ├── python3 -m kernel_conformance  → pass/fail
      └── cargo test --features=vectors  → pass/fail

CI gate: both must agree on every vector. Disagreement = build failure.
```

This converts the kernel from "a library" to "a protocol with
implementations." The vectors are the source of truth, not either
codebase.

---

## 2.x Hygiene Patches (immediate)

These don't require the kernel extraction. They fix the observed
divergences now:

### P1. `allow_nan=False` in gate_receipt.py

```python
# gate_receipt.py:canonical_json
json.dumps(obj, sort_keys=True, separators=(",", ":"),
           ensure_ascii=True, allow_nan=False)
```

### P2. `allow_nan=False` in signals/envelope.py

Same fix. Both modules currently inherit Python's default (`True`),
which means `float('nan')` silently serializes to `NaN` — not valid
JSON, not portable, not canonical.

### P3. Hash prefix unification

`gate_receipt.py` returns bare hex. `signals/envelope.py` returns
`sha256:` prefixed. These must agree. The prefixed form is better
(self-describing, collision-domain safe). But changing `gate_receipt.py`
now would break existing receipt IDs.

**2.x stance**: document the divergence, don't break stored receipts.
New modules must use prefixed form. 3.x kernel unifies with a version
bump.

### P4. Validator for NaN/Inf pre-hash

Add a check in `canonical_json` that rejects non-finite floats before
`json.dumps` gets a chance to serialize them. Belt and suspenders: both
`allow_nan=False` (which makes `json.dumps` raise) and an explicit
pre-check (which gives a better error message).

---

## What This Unlocks

- **Signal-to-receipt correlation**: signals reference receipt IDs,
  computed identically across modules.
- **Cross-language verification**: Rust kernel validates Python-emitted
  receipts (and vice versa).
- **Immutable test vectors**: spec changes require vector updates,
  making drift visible in review.
- **Audit as protocol**: external auditors verify the kernel by running
  vectors, not reading 60+ Python modules.
- **3.x foundation**: the self-governance spec
  (`specs/core/SELF_GOVERNANCE_SPEC.md`) needs a verified substrate.
  This is it.

---

## Relationship to Existing Specs

- **Receipt Kernel Roadmap** (`specs/gaps/RECEIPT_KERNEL_ROADMAP.md`):
  the kernel roadmap describes the receipt lifecycle. This spec describes
  the *math* underneath it.
- **Relational Invariants** (`specs/gaps/RELATIONAL_INVARIANTS.md`):
  relational properties assume single-trace properties are already
  verified. This spec ensures they are.
- **Operational SLA** (`specs/gaps/OPERATIONAL_SLA.md`): the SLA spec
  assumes timing measurements are trustworthy. This spec ensures the
  identity computations underneath are deterministic.
- **Governance Abuse Audit** (`specs/core/GOVERNANCE_ABUSE_AUDIT.md`):
  P7 (instrumentation capture) is harder when the instrumentation math
  is mechanically verified.

---

## Open Questions

1. **Float transition path**: signals use `value: float` extensively.
   Moving to fixed-point is clean but touches ~50 call sites. Worth it
   in 2.x or defer to 3.x kernel extraction?

2. **Duplicate key detection**: Python's `json.loads` doesn't reject
   duplicates. Adding detection requires either a custom parser or
   pre-parse scanning. Cost-benefit unclear for machine-generated JSON.

3. **Rust kernel timeline**: depends on whether the system gains
   external users who need cross-language verification. If it stays
   Python-only, the vectors still have value (pinning behavior against
   Python version upgrades), but the Rust kernel is less urgent.

4. **JCS compliance vs "close enough"**: full JCS (RFC 8785) includes
   a complex number-to-string algorithm. If we forbid floats in hash
   payloads (K2), we don't need it. If we allow floats, we do.
