# Decisions — transition-kernel pickup

## B-series sign-off questions (filed 2026-07-02, roadmap program resume)

### Q-B1 — confirm + push Standing 1a/1a-bis  **(RESOLVED BY EVIDENCE 2026-07-02)**
B1 verified both commits **already on `origin/main`** (`git branch -r
--contains` → origin/main for `1e62ba9` and `f101c55`) — the push half was
done before this question was filed (the 06-23 "unpushed" record had gone
stale). The confirm half is satisfied by the existing capsule record: STATUS
and NEXT already name these commits as the DONE implementations of ratified
D010/D010a/D010c. **B4/Slice 1b is UNBLOCKED** — and B1 further found its
implementation already committed on `feat/transition-kernel-slice-1b`
(24acd8f + f003519), so B4 executes as verify-and-adopt.

### Q-B3 — corpus custody home  **(RESOLVED 2026-07-02, Packet C — recommendation OVERTURNED)**
The earlier recommendation ("transition-kernel remains custodian") was too eager.
Packet C (docs/campaigns/corpus-custody/) found the 9 cases already exist as AG
golden corpus (`golden/corpus/*.json`, schema `agent_governor.corpus.v1`),
**byte-identical** to transition-kernel `vectors/legacy/`, and that the LIVE
cooked-context contract test lives in AG. Revised, evidence-driven model:
- **AG `golden/corpus/` is the admission source** — admission is explicit only
  there (closed-world coverage ceremony + live-chain verdict match).
- **transition-kernel `vectors/legacy/` is a conformance mirror** — proves
  byte-identity, may NOT mutate expected behavior locally.
- **Sync/identity guard shipped:** `golden/corpus/MANIFEST.json` (admission
  record: custody_class + sha256 per case) + `tests/test_corpus_custody.py`
  (fences unadmitted files, verifies hashes, couples the verdict test to the
  manifest funding set, checks the mirror byte-identity when present). Reviewed
  via the sandwich (codex-exec BLOCK → structural fixes → re-review).
Durable rule: **authority lives where admission is explicit; mirrors prove
identity; implementations don't crown their fixtures.** Later migration to a
neutral registry is allowed but is a custody EVENT. Full model + per-case B5
adjudication: docs/campaigns/corpus-custody/{custody-model,C4-b5-unlock}.md.

**B5 status (C4): PARTIALLY BLOCKED — not on custody.** None of B5's 9 target
refusals are producible by the corpus live-chain yet (it emits 6 kinds; B5 needs
scope_mismatch/token_*/freshness-variants which need drill scenarios or a
refusal-typing decision first). B5 re-scopes to "build the scenario → freeze the
verdict → admit," gated by the guard. The continuation specimen routes to the
transition-kernel frontier corpus, not golden/corpus.

### Q-B4 — sequencing of the two mint-boundary efforts  **(OPEN, default named)**
Recommendation: B4 (Python adapter Slice 1b) lands before Rust-kernel resume work
— it is unblocked, fully specified, and its receipts become corpus feedstock.
Default on silence: recommendation stands.

### Q-B7 — v7 CANDIDATE exposure  **(OPEN, default named)**
Recommendation: draft the AG JSON-schema lane against Lean v7's CANDIDATE fields
now, explicitly non-binding until v7 ratifies. Default on silence: draft in
`working/`, promote nothing.

## D010 — transition-kernel pickup boundary  **(RATIFIED 2026-06-23, Model X)**

Status: **RATIFIED** (operator, 2026-06-23). The scope-locus fork was decided **Model X**:
**Standing owns spend-time scope-mismatch refusal.** The `AGGrantAdapter` may only *inherit*
Standing's grant-use verdicts; it must **not** synthesize scope authority from carried grant
fields. Model Y (adapter-local scope matching) is acceptable **only** as a temporary
diagnostic specimen to demonstrate the gap — never to authorize mint/continuation in
production.

Ratified rule (verbatim intent): *Standing decides whether the grant authorizes the attempted
act; AG only consumes that decision at the mint boundary.* The adapter must inherit all five
refusals (expiry, replay, spent-token, subject-binding, **scope-mismatch**) and must not mint
or continue from carried scope fields alone.

- **decision:** AG does **not** pick up the transition kernel at `ag_admit`, self-correction,
  or repair-provider wiring — those are transport/admission rails. Pickup begins **only at the
  mint boundary**, when AG requires a Standing-issued grant token to mint or continue governed
  actor/session/step authority.
- **default_action:** build the first pickup as a narrow adapter
  `StandingGrantToken → AGGrantAdapter → existing AG mint/admission path`, at the cleanest seam
  (`activation.py` Office 2, replacing `standing_ok: bool`).
- **forbidden:** no global AG rewrite; no planner/conductor semantics change; no self-hosting-first;
  no accepting AG-local trust as equivalent to a Standing grant; no unstamped actor/session/step
  continuation.
- **requires_human_if:** token spend semantics are unclear; grant scope cannot be mapped to AG
  authority scope; the adapter would alter conductor/admission projection; pickup requires new
  kernel vocabulary.
- **evidence:** [INVENTORY.md](INVENTORY.md) (verdict B); operator seed 2026-06-23.

### Resolved fork — scope-mismatch refusal locus → **Model X**

Decided 2026-06-23. Standing closes its own token; the alternative (Model Y, adapter-local
matching) was rejected as authority because it makes AG the scope adjudicator — "trusted
construction with a nicer hat." It survives only as a non-authorizing diagnostic.

### D010c — `standing.grant_use.v1` has asymmetric custody  (RATIFIED 2026-06-23)

The JSON witness packet for `grant use`. **`used`**: `receipt_digest` REQUIRED,
`receipt_kind: "grant_used"`; AG may record the digest as `standing_basis`. **`refused`**:
`refusal_class` REQUIRED (closed set: `scope_mismatch | expired | already_spent | replay |
subject_mismatch | not_found`), `receipt_digest: null`, `receipt_kind: null`; AG must mint
nothing. Preserves Standing's invariant (no transition → no Standing receipt); a non-consuming
refusal is the *absence* of a transition, so there is no receipt to cite. **Not weaker** — AG
never mints on a refusal, so there is no authority to custody.

AG must distinguish three cases (load-bearing — no JSON raincoat):
1. `used` + digest → verified standing basis; may mint.
2. `refused` + typed class + null digest → verified Standing refusal; must not mint.
3. invalid / missing / unparseable / transport failure → **no verified result**; must not mint,
   but must **not** claim Standing refused.

Refusal-witness receipts (Model A) are parked as a **separate future Standing custody campaign**
(are they receipts/events/observations? content-addressed? same chain? spammable? part of token
custody?) — explicitly NOT a CLI-flag tweak.

### D010a — scope check is non-consuming (no DoS primitive)

A scope mismatch **must be checked BEFORE spend** and **must NOT consume the grant** (it emits
a refusal receipt, leaves the token unspent) — unless Standing adopts an explicit "failed
presentation burns tokens" doctrine. Otherwise any wrong-target presentation becomes a
denial-of-service primitive against a single-use grant. (Operator catch, 2026-06-23.)
