# GOV_GAP_QUERIED_RECEIPT_SUBSTRATE_001

## Status

**Candidate — captured 2026-06-16, NOT ratified, NOT authorized to build, does
NOT jump the queue.** A handle for later review (YAGNI-record discipline:
recognition, not authorization). Filed in `working/`, not `specs/gaps/`. No
forcing case is live. Grep-first caveat honored below: most of the *substrate*
this proposes already exists in AG; the genuinely-new pieces are the read
boundary and the office decomposition.

## Title

Receipts are event records in a queried, typed, append-only substrate — not
re-serialized markdown/JSON documents — and the **read boundary needs a receipt
of its own**: a projection (decoder output the LLM actually reasons over) is a
typed *claim* about a sealed fact, never the fact.

## Origin

Operator + ChatGPT, 2026-06-16, riffing on "could LLMs work over journald /
binary logs instead of markdown+JSON." The journald instinct is *secretly right*
about the **shape** (append-only, field-indexed, monotonic cursor, typed fields,
forward-secure sealing) and *wrong about the daemon* (journald vacuums its own
audit trail on rotation, silently drops entries under rate-limit burst, and
`-o export` is ugly enough you cave to `-o json` by the second command — every
one a violation of no-silent-anything). "Right shape, wrong daemon." The valuable
residue is the architecture, not systemd.

## The shape (thesis)

- The LLM never reads the log **as prose**. It operates through a **typed query
  boundary**: it proposes predicates / traversal (`match unit=X after cursor=C
  where MESSAGE_ID=receipt_emitted; show causal predecessors`), a boring Rust
  **broker** compiles that to a capability-limited query AST against the
  substrate. No `journalctl | grep | awk` fan-fiction; no shell strings.
- Receipts become **event records**, not documents. Markdown is commentary; JSON
  is an export costume; the authority-bearing object is a compact record with
  stable field identities + explicit lineage (`EVENT_TYPE`, `SCHEMA_ID`,
  `SUBJECT_HASH`, `DECISION`, `REASON_CODE`, `CLOCK_BASIS`, `PREDECESSOR`,
  `SIGNER`, binary `PAYLOAD`).
- Unknown fields stay **opaque** (handed to schema-specific decoders) rather than
  flattened or hallucinated; the LLM receives only typed projections.

## What ALREADY exists in AG (do NOT re-derive)

This gap is mostly *wiring existing organs*, not new substrate:

- **`libs/receipt_kernel`** — IS the "journal with the right properties that won't
  delete your history": append-only, hash-chained event ledger (SQLite WAL),
  content-addressed blob store, monotonic seq, redaction hook + retention policy,
  13 constitutional invariants. This is the "SQLite/event-store, not journald"
  conclusion already built.
- **`signal_store.py` (Signal Plane v1)** — a SQLite **projection cache** over
  instrumentation JSONL with a byte-offset cursor and a pure `project_envelope()`.
  This is *literally a projection layer that exists today and emits no projection
  receipt* — the open read-end edge, concrete.
- **`gate_receipt.py`** — content-addressed receipts (`receipt_id = H(...)`,
  canonical JSON), already the "compact typed record with stable id + lineage."
- **`clock_witness.py`** — monotonic-vs-wall basis discipline, `elapsed_ns`
  refuses incompatible bases. Directly serves the causality edge below.
- The **attestation ≠ admission** split (receipt_kernel ≠ authority kernel) and
  the **four-office rung-activation** model (`activation.py`) — the office
  decomposition below drops straight into these.

So the substrate is ~done. The deltas are: the typed query broker, the read-end
projection receipt, receipt-as-primary-artifact (demoting markdown/JSON), and the
office split.

## The load-bearing novel insight — projection receipts (the READ end)

Chatty's three "radioactive edges" all guard the **write** end (and are correct):
**(a)** log text is hostile input — returned field content marked inert, field
selection kept separate from model-generated instructions; **(b)** the
investigator must never write the evidence it investigates — read/query authority
on one channel, narrowly-bounded proposal authority on another (producers emit
records; the model does not manufacture historical observations); **(c)** the
substrate is not a truth kernel — FSS proves bytes weren't altered *after* the
write, **not** that the producer was honest *at* it. *Signed-is-not-witnessed.*

**The operator's sharpening — the read end is open, hiding inside the "benefit"
line "the LLM only receives typed projections":** a projection is a lossy,
schema-versioned transform produced by a decoder sitting *between* the sealed
record and the model, **outside the seal**. FSS covers the stored bytes; it says
nothing about whether the decoder rendered them faithfully. So the model never
reasons over the sealed fact — it reasons over a decoder's **claim about** it.
The record is immutable; the *meaning* isn't, because meaning is rebuilt at read
time by a mutable component. Run a v3 record through a v4 decoder and the fact
silently reshapes while staying sealed and "verified." **Signed-is-not-witnessed,
one layer up — and now the unwitnessed claim is the thing the model acts on.**
The Victorian medium didn't die; it moved to the decoder. Same séance, better
lighting.

**Fix (AG's own pattern, both ends of the pipe get receipts):**
- every projection carries its **source cursor + record hash** and the
  **decoder `SCHEMA_ID`**;
- **no silent up/down-convert across versions** — a record/decoder version
  mismatch fails closed, or rides an explicit **migration receipt**;
- the read boundary emits a **projection receipt**: *decoder-vX rendered record-H
  to projection-P, signed*. A projection becomes a typed *claim*, never a fact.
  Same "X is not Y" refusal family as the atlas spine. **Stored is not true.**

## Causality edge

`show causal predecessors` must traverse `PREDECESSOR` edges **only** — never
infer causality from cursor or timestamp order, or you rebuild false causality on
clocks that jump (the `clock_witness` lesson: a gap is a difference between
compatible witnesses, not numbers; wall time steps under NTP).

## Office decomposition (durability ≠ truth)

Do not let one office both *hold* the records and *vouch* for them — that rebuilds
journald-as-divine-ledger inside the constellation (same failure as
Governor-must-not-be-the-microkernel). Decompose along existing offices:

- **substrate + inheritance → Continuity.** The append-only ledger *is* the
  cross-session inheritance mechanism: the next session inherits by **querying the
  log** instead of reparsing a doc. (This makes the caution/relaxation-inflation
  fix *structural* — caution inflates because state is re-serialized and re-parsed
  each session; a queried log removes the re-parse. Continuity is the **medium,
  not the witness**.)
- **receipt semantics, verdict algebra, no-silent-convert / no-self-sustaining-
  chains invariants → NQ / verifier.**
- **issuance authority + waiver budget → standing.**
- **query AST + projection receipts + inert-field handling → the broker at the
  governor's privilege boundary.**

Consequence: a valid Clearance or Waiver is **not** a Continuity object — it's a
transaction the offices **co-sign**, which drops into the four-office
rung-activation model. **Continuity supplies durability, not truth. Stored is not
true** — signed-is-not-witnessed, one floor down at the deployment layer.

## Non-goals

- NOT journald/systemd adoption. Journald is *proof the shape exists in the wild*,
  not the daemon (it vacuums history, drops under burst — disqualifying for a
  no-silent-anything provenance system).
- NOT a new receipt substrate — `receipt_kernel` already is one. Don't rebuild it.
- NOT demoting markdown/JSON everywhere now — human-facing rendering stays; the
  claim is only that the *authority-bearing* object is the typed record, with
  prose/JSON as rendered views.
- NOT authorization to build the broker, projection receipts, or the office
  wiring. Capture only.

## Open questions

1. Does the projection-receipt obligation apply to *every* read, or only reads
   that feed a load-bearing decision? (Cost vs the no-silent-anything religion.)
2. Where does the decoder-version registry live, and who ratifies a migration
   receipt — standing, or the verifier office?
3. Is `signal_store`'s existing `project_envelope()` the first place to retrofit a
   projection receipt (smallest real forcing case), or does that over-fit the
   instrumentation plane?
4. Cross-host ordering / weak clocks: `PREDECESSOR`-only traversal needs a
   cross-host predecessor edge that doesn't smuggle in timestamp causality.
5. Binary payload schemas: who owns the schema-id namespace across the
   constellation (overlaps the NQ ops-grammar boundary)?

## Acceptance criteria (IF ever ratified + built — not now)

- The LLM cannot issue a raw query string; only a capability-limited AST compiled
  by the broker. Field content is returned marked inert.
- A read that produces a projection consumed by a decision emits a projection
  receipt binding (source record hash + cursor, decoder schema_id, output hash).
- A version-mismatched decode fails closed or carries a migration receipt — never
  a silent reshape.
- Causal traversal uses `PREDECESSOR` edges only; a test pins that timestamp/cursor
  order cannot stand in for causality.
- The investigator channel cannot write to the producer channel (separation test).
- No single office both stores and certifies a record.

## Forcing case

**None live.** Capture-only. Likeliest first real pressure: the
caution/relaxation re-serialization problem (a queried-inheritance Continuity
ledger would make that fix structural), or a second consumer of `signal_store`
projections needing to trust a rendered value. Promote to `specs/gaps/` only when
a forcing case appears AND it earns queue priority on its own — this note does not
jump the queue.
