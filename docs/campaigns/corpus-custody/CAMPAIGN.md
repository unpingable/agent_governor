# Campaign — corpus custody (Packet C; resolves Q-B3)

Status: **ACTIVE 2026-07-02 night.** Opened directly after B2's ruling *"the
corpus is the contract"* made corpus custody constitutional. Resolves Q-B3
(pickup DECISIONS) and gates B5 (the 9 missing corpus cases).

Capsule: [C0-inventory.md](C0-inventory.md) · [custody-model.md](custody-model.md)
(C1 taxonomy + C2 admission/mutation rule) · [C4-b5-unlock.md](C4-b5-unlock.md)
(unblock verdict). Guard code + the Q-B3 refinement land in the pickup capsule
and the corpus itself.

## Question

> "The corpus is the contract" — so by what explicit signal does a checked-in
> file BECOME contract, and what stops "file exists in the corpus dir" from
> silently meaning "file has authority"?

## The trap this packet exists to prevent

**"corpus is the contract" must not mutate into "fixtures are scripture."**
Constitutional substrate needs explicit admission, not authority-by-presence.
Composes with the constellation "index is never evidence" / "findability is
not legitimacy" doctrine: a corpus directory INDEXES cases; it does not MINT
their authority.

## Load-bearing facts (established before drafting the model)

- AG already runs a well-custodied golden corpus: `golden/corpus/*.json`
  (schema `agent_governor.corpus.v1`), driven by `tests/test_corpus_contract.py`
  — which runs the LIVE cooked-context chain per case and asserts the frozen
  `expected_verdict` (7 closed VERDICT_FIELDS), enforces closed-world coverage
  over `SUPPORTED_SCENARIOS`, excludes content-addressed receipt ids, and
  pins Wall-1 (every case non-operational). Its docstring already states the
  discipline: *"updating a golden becomes a deliberate reviewed act, never a
  silent regeneration."*
- transition-kernel `vectors/legacy/*.json` is the **same 9 cases,
  byte-identical**, same schema — duplicated with **no declared sovereign and
  no sync guard**. Divergence today would be silent.
- **Neither copy carries a `custody_class` field.** Contract-ness is currently
  implicit (membership + the coverage test). That implicit rule is the
  laundering surface this packet closes.

## Boundary / non-goals (packet C)

- No GS-2b/4/5/6 (governed-shell) work.
- No wicket-guard absorption unless C0–C3 prove it's required for custody.
- No B5 case authoring until C4 says UNBLOCKED / PARTIALLY (with which cases).
- No local-qwen wording pass except to RECORD a laundering issue found here.
- No generalized governance engine, no migration theater — the first guard is
  boring and sharp (additive field + one validator).

## Review protocol

Sandwich (as Packet B): draft the custody object → codex-exec adversarial
review specifically for corpus laundering (authority by path; generated
artifact becoming contract; expected outputs silently changing doctrine;
retired/disputed still funding verdicts; helper-as-hidden-authority; docs
narrating custody with no executable consequence) → treat any laundering
finding as a BLOCKER, amend the object (not the prose) → re-review until
MERGE-SAFE. Every test verdict through `governor verify-run`.
