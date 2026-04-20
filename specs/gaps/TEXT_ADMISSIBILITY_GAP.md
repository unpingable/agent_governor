# TEXT_ADMISSIBILITY_GAP

## Status
Proposed (2026-04-20)

## Origin

Surfaced when a user tried to paste an adversarial-Unicode test artifact
into this session. Anthropic's API-layer ingress filter rejected the
paste before it reached the model. The governor never saw the bytes.

That is the wound. Provider refusal is not governor refusal, but today
the governor behaves as if it were: it has no standing over text
artifacts whose identity lives *below* the Python `str` it receives.

Drafted in session against an external model ("chatty"). Framing and
layer distinctions owe to that exchange.

## Thesis

The governor currently trusts the decoded `str` as the thing-that-arrived.
That is too late in the pipeline. Once a byte sequence has crossed into a
Python `str`, the governor has already lost:

- original bytes
- encoding (declared vs. inferred vs. fallback)
- decode failure semantics
- the exact subject that a receipt should hash

For text artifacts subject to adversarial construction — zero-width
joiners, bidi controls, mixed-script confusables, combining-mark
overlays, supplementary-plane chars, invalid-UTF-8 edge cases — this
means the governor can produce receipts that *collide under visual
equivalence* while the underlying bytes differ. That breaks
content-addressing as a security property.

This gap is not about sanitization. It is about **standing and
lineage** for text as a governed artifact.

## Three Layers That Must Not Collapse

The spec treats these as distinct from the start. Collapsing any two
into one reproduces the current bug.

1. **Artifact identity** — what bytes arrived.
2. **Text interpretation** — how those bytes decoded (encoding,
   success/fail, replacement strategy, derived normalized forms).
3. **Decision equivalence** — which representation had standing when
   the governor judged two artifacts the "same."

## What Exists

- `provenance_labels.py` — source_class and sensitivity tagging of tool
  outputs. Does not touch bytes or decode.
- `security.py` — pattern-based vulnerability detection on decoded
  strings. Not Unicode-aware.
- `egress_gate.py` — outbound payload classification. Classifier is
  regex over decoded text.
- `gate_receipt.py` — content-addressed receipts. Hash subject is
  whatever the caller hands it, currently assumed to be a decoded
  string. This is the sharpest edge.
- `receipt_kernel` redaction hook — 13 secret patterns over decoded
  text. Also not Unicode-aware.

None of these treat raw bytes as a first-class governed object.

## What Is Missing

- Submitted bytes as first-class governed artifact.
- Decode provenance: declared encoding, inferred encoding, success
  status, replacement-char count, surrogate/noncharacter presence.
- Derived text lineage: NFC, NFKC, casefold, skeleton, each recorded
  as a derived form of the same artifact, never as the artifact itself.
- Equivalence-regime tracking: every comparison records which
  normalization was used to judge sameness.
- Field-sensitive hostile-text policy: the same character is not
  equally dangerous in a filename, an approval token, an actor ID,
  or a freeform note.

## Invariants

1. **Hash subject is submitted bytes when bytes are available.**
   Decoded text and normalized forms are derived artifacts. They may
   be *included* in a receipt, but they are not the *subject* of its
   identity hash.

2. **Detection is factual. Policy is contextual.** Feature extraction
   (contains ZWJ at position X, contains Cyrillic `а` in mostly-Latin
   string, NFKC changes code points, skeleton collides with known
   identifier) is a receiptable fact independent of field. Severity is
   a separate layer that binds facts to field context.

3. **Receipts must record which representation had standing.** A
   decision that uses NFKC-skeleton equivalence and a decision that
   uses exact-byte equality are different decisions. The receipt
   records which regime was used.

4. **Provider refusal is not governor refusal.** The governor's ability
   to receipt, inspect, warn on, and hash a text artifact MUST NOT
   depend on whether an upstream provider admitted it. Fixtures are
   loaded from repo bytes, not from model I/O.

## Acceptance Criteria

- Fixture corpus exists in-repo, stored as bytes (hex / base64 / `\u`
  escapes / golden files loaded as `bytes`) — never as pasted glyphs.
  Corpus covers: zero-width chars, bidi controls, mixed-script
  confusables, combining-mark density, supplementary-plane chars,
  invalid UTF-8, surrogate pairs, normalization divergence.
- Every fixture has: raw bytes, declared encoding, decode result,
  expected feature report, expected NFC/NFKC/casefold/skeleton forms,
  expected byte-identity hash.
- Receipts preserve: `submitted_bytes_hash`, `encoding`,
  `decode_status`, `derived_forms` (keyed by normalization regime),
  `suspicious_features`, `comparison_regime_used`.
- Warnings surface with field context (filename vs. approval token vs.
  freeform note).
- Two visually indistinguishable but byte-distinct inputs produce
  distinct receipt identities.
- Local text-analysis layer answers all of the above without any LLM
  call.

## Non-Goals

- Not a universal text sanitizer. The governor does not rewrite user
  input into "safe" form.
- Not a provider-bypass scheme. If Anthropic or any upstream refuses
  to admit the bytes, the governor's job ends at local receipting,
  not at smuggling.
- Not an LLM benchmark. This is parser/validator work, not reasoning
  evaluation.
- Not a replacement for existing security pattern checks. This sits
  *under* them by giving them a stable byte-level subject.

## Failure Examples (How We Get Owned Without This)

Each of these is a decision the governor currently cannot distinguish
from its benign twin:

1. **Homoglyph approval-token collision.** An approval token using
   Cyrillic `а` (U+0430) matches a receipt that expected Latin `a`
   (U+0061) under NFKC-skeleton equivalence. Byte hashes differ;
   skeleton hashes collide. Governor approves.

2. **Bidi path confusion.** A filename containing RLO (U+202E) renders
   as `safe.txt` but refers to `txt.exe`. Content-addressed receipt
   over the decoded display form collides with the receipt for the
   actual executable path.

3. **Zero-width token mutation.** An actor ID with a ZWJ (U+200D)
   inserted mid-string decodes to a superficially-identical `str`.
   Governor's actor-identity checks compare decoded strings; byte
   identity would catch it.

4. **Normalized-hash aliasing.** Two distinct artifacts — one NFC, one
   NFD — produce identical content hashes after implicit normalization.
   Receipt store believes they are the same artifact; byte-level
   identity disagrees.

Each case has the same shape: the governor's decision rule used an
equivalence regime (skeleton / display / decoded-str / implicit-NFC)
whose collapse set was larger than it knew.

## Suggested Module Split

- `textscan/bytes.py` — decode with provenance preservation
- `textscan/features.py` — invisible chars, bidi, script mixing,
  confusables, combining density
- `textscan/normalize.py` — NFC/NFKC/casefold/skeleton as derived
  forms (never destructive)
- `textscan/policy.py` — field-context severity
- `tests/fixtures/hostile_text/*.json` — corpus + expected outputs

## Implementation Note

This is a task where Opus is a poor fit: handling raw hostile-Unicode
corpora through a chat tool reproduces the exact provider-ingress
problem the spec is trying to route around. Recommended path is to
hand this spec to a supervised Gemini CLI or Codex session via the
runtime supervisor, so byte fixtures are handled in-repo rather than
across a filtered wire.

## Worked Example: Specifying This Across a Filtered Wire

This spec was itself developed against a coding assistant whose API
ingress filter rejected the adversarial-Unicode specimen we wanted to
discuss. We never transmitted a live specimen to the model. We
described the specimen and encoded the shape of the problem in prose.

That is not a bug in the assistant. For a general-purpose coding
assistant, normalize-or-reject at ingress is a correct default — the
users mostly do not want to debug invisible characters arriving via
prompt injection. But it is exactly the default the governor **must
not inherit**, because the governor's job is to preserve the
distinction the assistant's layer is correctly erasing.

Different layers have different correct defaults. The admissibility
boundary is the place where that disagreement becomes legible.

The meta-observation worth preserving: the upstream filter is itself
an instance of unauthorized normalization at an API boundary —
collapsing "raw" and "interpretive" into one field, silently, without
a policy artifact saying "this is where normalization happens and
why." From the governor's perspective, that normalization should have
a receipt. From the assistant's perspective, that is absurd overhead.
Both positions are defensible. The defensibility is exactly why the
boundary needs to be legible, not assumed.

### Transmit-across-filtered-wire patterns

The next implementer will hit the same wall when trying to dogfood
this spec through a general-purpose assistant. Use the same
workarounds the governor's own test suite will need anyway:

- **Hex byte arrays.** `bytes.fromhex("...")` — never trust the
  source file's text pipeline to round-trip cursed bytes.
- **`\u` / `\U` escapes.** In source: `"\u202ebadpath.exe"`. Readable,
  diffable, not a paste hazard.
- **Base64-encoded test vectors.** For multi-character fixtures and
  invalid UTF-8 sequences. Decode at test-load time, never at edit
  time.
- **Golden files loaded as `bytes`.** Binary-mode reads only. Do not
  let YAML/JSON parsers touch fixture content; store the bytes
  themselves and carry expected-output JSON alongside.
- **Explicit "do not normalize" wrappers.** When a fixture must cross
  a layer that might normalize, wrap as `{"codepoints":
  ["U+202E", "U+0074", ...]}` and reconstruct locally. Less pure, but
  survives the transit.
- **Human-readable diagnostic renderings as a separate artifact.** A
  fixture is bytes; its human-facing display is a derived artifact
  with its own file, never a substitute.

Rule of thumb: **the fixture's canonical form is whatever a layer
that wants to help cannot silently corrupt.** For this work that is
hex, escapes, or base64 — never the glyph itself.

## Open Questions

- Does `gate_receipt.py` need a schema bump to accommodate the new
  receipt fields, or is this accretive (optional fields)?
- Where does the byte-identity hash sit relative to
  `HashRef` (`hash_ref.py`) — is this a new hash namespace or a
  different `alg` on the existing type?
- What is the right default policy when bytes are *not* available
  (e.g., received over a transport that already decoded)? Record the
  gap explicitly? Refuse to receipt? Receipt with
  `decode_status="upstream"` and a loss flag?
- Fiction/nonfiction governors accept freeform prose where
  field-sensitive severity is dominated by "freeform note." Do they
  get a permissive default, or is the policy layer the only place
  this is expressed?
