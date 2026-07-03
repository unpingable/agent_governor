# Corpus custody model (C1 taxonomy + C2 admission/mutation rule)

**Status:** DRAFT for the review sandwich (2026-07-02 night). Prose-first: the
schema change it justifies is one additive field + one validator, no migration.
Scope: the decision-kernel corpus (`golden/corpus/` in AG, mirrored as
`vectors/legacy/` in transition-kernel). Not a general governance engine.

## The one rule everything else serves

> **Membership is not authority.** A file living in a corpus directory is an
> `example` until it explicitly declares itself contract AND is admitted by the
> coverage ceremony. "corpus is the contract" names the admitted set — never
> the directory listing.

This is the "index is never evidence" doctrine applied to fixtures: the corpus
dir *indexes* cases; the `custody_class` field + the coverage test *admit*
them. Presence funds nothing.

## C1 — Custody taxonomy (closed set: `custody_class`)

A new required field `custody_class` on `agent_governor.corpus.v1` (additive;
existing entries retrofit to `contract` — see C2 for why that retrofit is
itself the admission event). Closed vocabulary:

| class | funds live verdicts? | meaning | mutation cost |
|---|---|---|---|
| `contract` | **YES** | admissible source of expected behavior; a code change that diverges is a BUG; the case's `expected_verdict` is doctrine | deliberate reviewed act citing why (a decision ref); loud test failure forces intent |
| `example` | no | illustrative/demo; runs for smoke but does not gate doctrine | edit freely; not a doctrine change |
| `regression` | YES (narrow) | guards one past bug/corner; gates, but does not alone DEFINE the rule (it defends, doesn't declare) | reviewed; cite the scar it guards |
| `retired` | **no (fenced)** | preserved for history/replay; **must not fund an active verdict** | may not re-enter `contract` without fresh admission |
| `disputed` | **no (fenced)** | known unresolved semantic conflict; loud; parked until resolved | resolution is a decision, not an edit |
| `generated` | derived only | produced from a declared sovereign source; authority DERIVES, never independent; drift from source is a generator bug, not new doctrine | regenerate from source; never hand-edit |

Default on a missing/unknown `custody_class`: **the validator refuses** (unknown
status is not admitted — allowlist discipline). No silent default to `contract`.

## Admission source & conformance mirror (the Q-B3 refinement)

The durable rule (operator, 2026-07-02) — NOT "whoever validates it owns it":

> **Authority lives where admission is explicit. Mirrors must prove identity.
> Implementations don't get to crown their fixtures.**

One admitted corpus; repo-local mirrors; every consumer proves it is consuming
the *admitted* corpus, not inventing local scripture. Applied to the two
byte-identical copies:

- **Admission source: AG `golden/corpus/`.** Not because AG "owns" it, but
  because admission is currently EXPLICIT only here — the closed-world coverage
  ceremony + the live cooked-context contract test are the admission gate, and
  they live in AG. A verdict is admitted by passing that ceremony.
- **Conformance mirror: transition-kernel `vectors/legacy/`.** Its job is to
  prove *"Rust behavior matches the admitted AG corpus"* — not to own the cases
  because the repo boundary feels tidier. It is a mirror that must PROVE
  identity, never an independent master. **transition-kernel must not mutate
  expected behavior locally** — a local edit to a mirror case is a custody
  violation, caught by the guard (C3), not a valid doctrine change.

**This overturns Q-B3's prior recommendation** ("transition-kernel owns the
corpus") — Packet C found that guess too eager: relocating custody now would
separate the corpus from the only place admission is explicit. Later migration
to a neutral registry / shared corpus package IS allowed, but it would be a
**custody EVENT** (an admission move, reviewed), not a housekeeping shuffle.

The load-bearing missing object is therefore the **sync/identity guard**: AG
case ids + content hashes; mirror hashes; fail if the mirror diverges silently;
no local expected-behavior mutation without upstream admission. That guard (not
a repo relocation) is what makes "the corpus is the contract" honest.

## This document is the custody act (not a private judgment)

The classification below is not enumeration — it is the custody DECISION, and a
custody decision cannot live in an operator's head or a model's vibespace. It
lands here as an adjudicated artifact, goes through the review sandwich
(codex-exec adversarial, laundering findings are blockers), and its verdicts are
recorded in the campaign DECISIONS. Raw surface-enumeration was delegated (C0);
the judgment is written down and reviewable.

## C2 — Admission & mutation rule

**What admits a case as `contract`:** ALL of —
1. it declares `custody_class: contract`;
2. its `input.scenario` is in `SUPPORTED_SCENARIOS` (the closed-world set —
   this is the admission ceremony: a scenario cannot ship without a frozen
   verdict, and a verdict cannot exist for an unsupported scenario);
3. its `expected_verdict` matched the live chain at freeze time (proven by
   `test_corpus_contract.py` at commit).

The coverage-closure test IS the admission gate — there is no separate registry
to launder around. Admission is structural, not a sticker.

**What identifies custody class:** the explicit `custody_class` field. Nothing
else — not filename, not directory, not "it's been here a while."

**Active vs retired/disputed:** the field value. The validator excludes
`retired` and `disputed` from BOTH the coverage set and the verdict-funding
set. A retired case that a test still consumes as expected-behavior fails the
guard loudly.

**What is required to MUTATE expected behavior:** editing a `contract` case's
`expected_verdict` must be a deliberate, reviewed commit whose message cites the
decision that changed the behavior. The existing test already forces the edit to
be *intentional* (it fails loudly on drift, saying "update the golden
deliberately"); custody adds that the intent must be *attributable* — the scar
is "never a silent regeneration." A regeneration script that rewrites goldens to
match current code is FORBIDDEN for `contract`/`regression` (it would launder a
bug into doctrine); it is the only licensed update path for `generated`.

**What stops a generated artifact becoming authority by being checked in:**
`custody_class: generated` + a `derived_from` pointer to the sovereign; the
guard asserts the generated bytes match the source. A `generated` file never
funds a verdict on its own authority — it borrows the sovereign's.

**What stops stale/superseded cases funding verdicts:** `retired`/`disputed` are
fenced by the validator from the funding + coverage sets; the fence is
executable (C3), not a comment.

## Known boundaries (codex-exec review, recorded not pretended-away)

The guard is boring and sharp, which means it has honest edges. Recording them
(A9 discipline: do not narrate a risk closed):

- **Coordinated manifest+verdict edit.** A commit that changes an
  `expected_verdict`, updates its manifest hash, and keeps `custody_class:
  contract` passes the hash check. It does NOT pass the live-chain match in
  `test_corpus_contract.py` (now coupled to consume only funding cases) unless
  the reference implementation actually produces the new verdict — so you can
  launder bytes but not a verdict the code won't emit. The residue (changing a
  verdict the code DOES emit, e.g. co-drifting classifier + golden) is stopped
  only by reviewed, attributed mutation (C2). No hash closes this; it is a
  review boundary.
- **Mirror skip in isolated CI.** Byte-identity is checked only when the
  transition-kernel repo is on disk; bare AG unit-CI skips WITH a reason.
  Mirror-identity is a constellation-integration check (or a mirror-side check
  transition-kernel owns against this manifest) — not an AG-isolated-CI promise.
- **`admitted_by` is a breadcrumb, not the gate.** The admission signal is
  structural (funding-class + hash-match + live-chain-match + covered scenario),
  never the manifest's prose. The guard does not trust the string.

The load-bearing fix from the review (findings 1-3): the verdict test now
consumes ONLY manifest funding cases, so directory membership funds nothing and
retired/disputed are fenced at the point of consumption, not by a tautology.
`generated` is fail-closed (requires `derived_from` + source-byte match).

## Helper-as-hidden-authority (named; C0 confirms extent)

A distinct laundering channel: contract semantics encoded in TEST HELPERS
rather than corpus cases — e.g. `_used_packet()` / `_refused_packet()` /
`FakeRunner` encoding the `standing.grant_use.v1` packet shape, or a helper
whose return value silently defines an expected verdict. A helper is
`example`-grade by nature (it illustrates); when its output is asserted AS the
contract, authority has leaked out of the admitted corpus into un-admitted code.
Custody rule: **the expected verdict must live in a `contract` corpus case, not
in a helper's constants.** Helpers may CONSTRUCT inputs; they may not BE the
expected output. C0 enumerates where this currently happens; C3's guard flags
the reachable cases; genuinely-structural helper contracts (packet schema) get
a named follow-up, not a silent pass.
