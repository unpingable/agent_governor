# SPEC.md (Normative) — Receipt/Gate Canonicalization + Hash + Signature

**Version:** 1.1
**Date:** 2026-02-10
**Status:** Normative. If this conflicts with any other doc, **this doc wins**.

We use RFC 2119 keywords: MUST, MUST NOT, SHOULD, SHOULD NOT, MAY.

---

## 1. Scope

This spec defines:

- **Canonical byte representation** for protocol objects (receipts, gate receipts, evidence refs, etc.)
- **Hashing** of canonical bytes
- **Signing** and **verification**
- **Conformance vectors** and runner expectations

It does *not* define product behavior, UI, or policy logic beyond what's required for stable bytes.

---

## 2. Terminology

- **Object**: a JSON value expected to match a protocol schema (e.g., Receipt, GateReceipt).
- **Canonical bytes**: the exact UTF-8 byte sequence produced from an object under this spec.
- **Digest**: SHA-256 hash of canonical bytes (lowercase hex).
- **Signature**: Ed25519 signature over canonical bytes.

---

## 3. Encoding and Text Normalization

### 3.1 Encoding
Implementations **MUST** encode canonical bytes as **UTF-8**.

### 3.2 Unicode normalization
All string values **MUST** be normalized using **Unicode NFC** prior to canonicalization.

- If an implementation cannot normalize reliably, it **MUST** fail conformance for vectors requiring normalization.

---

## 4. Canonicalization

### 4.1 Canonical JSON
Canonicalization **MUST** follow **JSON Canonicalization Scheme (JCS), RFC 8785**.

Implications (non-exhaustive, but binding via RFC 8785):

- Object member names are ordered lexicographically by Unicode code points.
- No insignificant whitespace.
- Arrays preserve order.
- String escaping follows JSON rules under JCS.
- Number rendering follows JCS rules **subject to additional constraints below**.

### 4.2 Number constraints (pinned — no floats ever)

Protocol objects **MUST NOT** contain floating-point numbers.

Allowed numeric forms:
- JSON integers in **signed 64-bit range only** (`-9223372036854775808` to `9223372036854775807`)

All other numeric quantities **MUST** be represented as:
- Strings (e.g., `"0.1"`, `"123456789012345678901234567890"`)
- Fixed-point integers with explicit scale fields (e.g., `{"cents": 150}` not `{"dollars": 1.50}`)

If a disallowed numeric type is encountered, implementations **MUST** return an error and **MUST NOT** silently coerce.

Implementations **MUST** parse numbers in vectors and protocol objects with **exact integer semantics** (e.g., BigInt in JS/TS, native int in Python) and enforce the int64 range check prior to canonicalization. `JSON.parse` without BigInt handling is not conformant.

### 4.4 JSON parsing requirements

Protocol inputs **MUST** be valid **RFC 8259 JSON**. Implementations **MUST** reject:
- Duplicate object member names
- NaN, Infinity, -Infinity
- Comments (single-line or block)
- Trailing commas
- Any JSON5/JSONC extension

### 4.3 Absent vs null
Optional fields:
- **MUST** be omitted when not present (absent), not set to `null`, unless the schema explicitly allows `null` with semantic meaning.
- Conformance vectors will treat absent vs null as distinct.

---

## 5. Canonical Bytes Derivation

Given an input object:

1. Normalize all string values to **NFC**.
2. Validate against the schema's **type constraints** (at minimum: reject floats).
3. Serialize using **JCS (RFC 8785)**.
4. Encode as **UTF-8** to obtain **canonical bytes**.

The canonical bytes are the sole input to hashing.

---

## 6. Hashing

### 6.1 Digest algorithm
Digest **MUST** be computed as:

```
digest = sha256(canonical_bytes)
```

Represented as **lowercase hex** (64 characters).

For signed objects, `canonical_bytes` (and thus digest) are computed over the **signature-stripped** form as defined in §9. This makes object identity independent of signatures.

### 6.2 Object identity
When an object references another object by hash, it **MUST** reference the SHA-256 digest of the referenced object's canonical bytes (signature-stripped per §9 if the object is signed).

---

## 7. Signing

### 7.1 Signature algorithm
Signature algorithm **MUST** be **Ed25519**.

### 7.2 Signing payload (pinned)

Implementations **MUST** sign the canonical bytes directly using the keypair derived from the Ed25519 seed per RFC 8032:

```
sig = ed25519_sign(keypair_from_seed(seed), canonical_bytes)
```

Implementations **MUST NOT** sign the SHA-256 digest instead. Ed25519 hashes internally; double-hashing adds complexity without security benefit and creates "why is this double-hashed" bugs.

### 7.3 Key + signature encoding (pinned)

- Public keys **MUST** be encoded as **RFC 4648 base64** (standard alphabet, padding MUST be present) in JSON as field name `pubkey_b64`.
- Signatures **MUST** be encoded as **RFC 4648 base64** (standard alphabet, padding MUST be present) in JSON as field name `sig_b64`.
- Hashes/digests **MUST** be **lowercase hex**.

Decoders **MUST** reject missing or extra padding. No base64url. No hex for keys/sigs. No uppercase hex for hashes.

### 7.4 Verification

Verification **MUST** fail if:
- Canonicalization fails
- Hashing fails
- Signature does not verify for the canonical bytes

No "best effort." No partial success.

---

## 8. Timestamps (pinned)

If protocol objects include timestamps, they:

- **MUST** be RFC 3339 UTC with a trailing `Z`
- **MUST** include millisecond precision exactly: `YYYY-MM-DDTHH:MM:SS.sssZ`
- **MUST NOT** use offsets like `+00:00`
- **MUST NOT** omit milliseconds or vary precision

Example: `2026-02-10T14:30:00.000Z`

Normative regex: `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$`

Implementations **MUST** reject timestamps that do not match this pattern. Canonicalization treats timestamps as strings (after NFC normalization) and does not rewrite them.

---

## 9. Signature Field Handling

When computing digest or signature for an object that contains a signature field:

1. Create a deep copy of the object
2. **DELETE** the signature field entirely (not set to `null`, not set to `[]`)
3. Canonicalize the result
4. Hash/sign the canonical bytes

Implementations **MUST NOT** remove now-empty parent objects or otherwise rewrite structure beyond deleting the specified field(s). For example, if deleting `integrity.signatures` leaves `integrity: {}`, the empty object **MUST** remain.

This applies to all signed objects:
- Receipts (`integrity.signatures` → delete)
- GateReceipts (`signature` → delete)
- Trust roots (`signature` → delete)
- Constitutions (`signatures` → delete)

---

## 10. Error Handling

Implementations **MUST** surface structured errors for:
- Invalid UTF-8
- Schema/type violations (including floats)
- Normalization failures
- Canonicalization failures
- Hash/signature failures

Implementations **MUST NOT** "repair" inputs silently.

---

## 11. Conformance Vectors

### 11.1 Vector fields

Each vector **MUST** include:
- `id` (string): unique identifier
- `type` (string): `canonicalization` | `hash` | `signature` | `chain`
- `input` (object): the JSON object to process
- `expected.canonical_b64` (string): base64 of exact canonical bytes
- `expected.sha256_hex` (string): lowercase hex of SHA-256 digest

For signature vectors, also:
- `key_ref` (string): reference to test keypair
- `expected.sig_b64` (string): base64 of expected signature

### 11.2 Expected canonical bytes

`expected.canonical_b64` is the standard base64 encoding of the exact canonical bytes. Implementations must match byte-for-byte.

### 11.3 Determinism

Conformance vectors **MUST** avoid nondeterminism:
- Fixed timestamps
- Fixed IDs / nonces (explicitly provided in vector)
- Fixed key material for signing tests (test-only keys, never use in production)

---

## 12. Conformance CLI Contract

Each implementation **MUST** provide a CLI executable:

```
receipt_conform --vector <path>
```

It **MUST** emit JSON to stdout:

```json
{
  "id": "canon-0002-unicode",
  "ok": true,
  "canonical_b64": "eyJhcnIi...",
  "sha256_hex": "7c0f...",
  "sig_b64": null,
  "errors": []
}
```

Fields:
- `id` (string): vector ID
- `ok` (boolean): true if all expected fields match exactly
- `canonical_b64` (string | null): computed canonical bytes as base64
- `sha256_hex` (string | null): computed digest as lowercase hex
- `sig_b64` (string | null): computed signature as base64 (if signature vector)
- `errors` (array of strings): error messages if any step failed

Exit code:
- `0` if `ok: true`
- `1` if `ok: false` or any error

---

## 13. Minimum Required Vectors

Conformance suites **MUST** include vectors covering:

### Canonicalization edge cases
- Key ordering with similar prefixes (`{"a":1, "aa":2, "ab":3}`)
- Unicode normalization (NFC vs NFD: `cafe\u0301` as composed vs decomposed)
- Escaping: `\u0000`, quotes, backslashes, newlines
- Large integers (near int64 boundary)
- Nested arrays/objects
- Empty objects/arrays
- Optional fields: absent (omitted) vs present

### Hash vectors
- Receipt with fixed timestamp + deterministic fields
- GateReceipt referencing a subject hash

### Signature vectors
- Ed25519 with test keypair
- Verification of known-good signature

### Chain vectors
- Receipt A → Receipt B includes `hash(A)` in `prev_digest`

---

## 14. Test Keypairs

Test keypairs for conformance vectors. The seed is the 32-byte Ed25519 private key seed per RFC 8032. Implementations derive the full signing key from the seed however their library requires (e.g., libsodium uses `seed||pubkey` as 64-byte private key; Python `cryptography` and Rust `ed25519-dalek` use the 32-byte seed directly).

```json
{
  "id": "test-ed25519-01",
  "algorithm": "ed25519",
  "seed_b64": "nWGxne/9WmC6hEr0kuwsxERJxWl7MmkZcDusAxyuf2A=",
  "public_key_b64": "9VaYAYK8tHzTDUSZham/DbA/UKJ2SwKey7lPWlhJPkw="
}
```

**WARNING**: These keys are for conformance testing only. Never use in production.

---

## 15. Security Notes

- Implementations **MUST** treat canonicalization as part of the security boundary.
- If normalization or canonicalization differs across implementations, signatures become unverifiable across languages; this is a **protocol failure**.
- Avoid floats; they create cross-language divergence and signature incompatibility.
- Configurable crypto (e.g., "pick hash algorithm at runtime") breeds incompatible ecosystems. Don't do it.

---

## 16. Repo Structure

```
conformance/
  README.md
  SPEC.md                  # This document (normative)
  vectors/
    manifest.json          # Lists vectors + tags + versions
    canon/
      canon-0001-basic.json
      canon-0002-unicode.json
      canon-0003-escapes.json
      canon-0004-numbers.json
      canon-0005-absent-vs-null.json
    hash/
      hash-0101-receipt.json
      hash-0102-gatereceipt.json
    sig/
      sig-0201-ed25519.json
    chain/
      chain-0301-prev-digest.json
  keys/
    test-ed25519-01.json   # Test keypair (NEVER use in production)
  runner/
    run.py                 # Language-agnostic runner
    ref_canon.py           # Reference canonicalizer
  impl/
    python/
      receipt_conform      # CLI binary
    rust/
      receipt_conform
    go/
      receipt_conform
    ts/
      receipt_conform
```

---

## 17. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.1 | 2026-02-10 | Review pass: seed-only keypairs (RFC 8032), RFC 4648 base64 with mandatory padding, digest uses signature-stripped form (§9), no-prune rule for empty parents, reject duplicate keys/JSON5, BigInt-aware parsing, timestamp regex. |
| 1.0 | 2026-02-10 | Initial release. Pinned: sign canonical bytes, base64 for keys/sigs, hex for hashes, no floats, millisecond timestamps. |

---

*"Vectors are the authority. If your bytes don't match, you're not conformant."*
