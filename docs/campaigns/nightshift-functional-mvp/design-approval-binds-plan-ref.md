# Design spec_slice: approval binds plan_ref

**Status:** spec_slice — **RATIFIED 2026-07-13 (operator ruling).** Contract
shape + migration disposition ruled below. Next gate: escape-count pass over
this ruled spec (zero escapes) → build_slice with mandatory codex-exec (or
substitute) sandwich. Custody-affecting ratification received per §8.

**Source finding:** `GAP-s6-sandwich-authority-findings.md` Finding 2 (codex
Critical, 2026-07-13). **Backlog stub:** `.governor/backlog/approval-binds-plan-ref.json`.

## The Problem (pre-existing v0 behavior, not S6/S7 regression)

A governed plan cites `approval_ref`. Admission checks that the ref *resolves*
to witness bytes (and, if `sha256:`, that they hash to it) — but **never that
the approval act names `env.plan_ref`**. So Plan B can cite Plan A's approval
witness and admit: **approval replay.** The doctrine "approval attaches to plan
bytes" is literally violated — today the witness attaches to nothing verifiable
about the plan it is admitting.

This is a distinct threat model from S6/S7. S7 made *ration citation* mean what
it already claimed (`execution_request ⊆ cited_ration`). This slice changes what
*approval* means. It must not be disguised as S7 cleanup.

## RULED contract (operator, 2026-07-13): witness carries plan_ref

**The binding lives in the attested witness bytes, NOT in the `approval_ref`
naming convention.** `approval_ref` is a *locator*; making its string grammar
authoritative would turn parsing convention into custody and leave room for
aliasing / normalization / refactoring to change semantics accidentally.
Rejected shape (ii).

```
plan
  └── approval_ref ──resolves once──▶ approval witness (bytes)
                                       ├── witness_version
                                       ├── decision
                                       └── exact plan_ref  ( = sha256(plan bytes) )
```

**Admission verifies (all five):**
1. the witness is authentic and structurally valid;
2. its `decision` authorizes execution;
3. `witness.plan_ref == sha256(exact current plan bytes)`;
4. the *same immutable witness bytes* are used throughout admission (resolve
   once, don't re-fetch);
5. replaying that witness beside any *other* plan refuses.

**Grounding (where this lands):** `daemon.py:~3518` already does check (1) —
`sha256(witness_bytes) == approval_witness_digest`. Today it then activates. The
build adds checks (2)+(3): parse witness content, verify `decision` authorizes
and `witness.plan_ref == request.source_plan_digest` (the plan-byte digest).
Check (4) = compute over the one `witness_bytes` already resolved; (5) is the
negative test.

**Hash-cycle caveat (pinned, operator):** ensure `approval_ref` can be allocated
independently of witness content. If `approval_ref` were itself a content digest
of the witness bytes AND the witness must contain `plan_ref`, that risks a hash
cycle. **Resolution — no fixed-point cleverness:** use a stable witness identity
+ separately verified witness bytes. *Note: the current design is already
cycle-free* — `approval_witness_digest` is a digest of the witness bytes (which
carry `plan_ref`), while `plan_ref` is an independent digest of the *plan* bytes;
neither depends on the other. The build must not introduce a cycle by, e.g.,
folding the witness digest into the plan or vice-versa.

**Narrow-slice invariant (the whole slice, one line):**
> An approval witness authorizes exactly one plan identity because its attested
> content names that plan's exact byte hash.

No ration changes, no execution semantics, no generalized approval ontology, no
semantic meaning smuggled into reference strings.

## Ripple (why this is its own slice, not a patch)

- The NS-1 / NS-1R approval procedure (README steps) changes — a witness minted
  the old way won't carry the binding.
- Operator tooling that mints witnesses changes.
- **Migration — RULED (operator, 2026-07-13):**
  - Existing *execution receipts* remain valid **historical evidence** (not
    re-litigated).
  - Existing *legacy approval witnesses* do **NOT** authorize arbitrary new
    admissions (an unbound legacy witness cannot admit a plan post-fix).
  - Do **not** rewrite NS-1 or NS-1R in place (frozen bytes stay frozen).
  - If either must run again: create a **successor plan** with a new
    `approval_ref` and a bound witness (composes with the S6 successor ruling).
  - A frozen legacy `(plan_ref, approval-witness-digest)` pair may be retained
    **only if a real compatibility requirement exists** — do not add that
    aperture merely to avoid creating a successor.

## Acceptance criteria (finalized under the ruling)

1. A plan citing an approval witness whose attested `plan_ref` ≠ the plan's own
   byte hash is **refused at admission** with a typed, closed-vocabulary refusal
   (`approval_plan_ref_mismatch` — this slice mints/exercises it).
2. A plan whose witness correctly names its own `plan_ref` admits (positive twin).
3. The NS-1 replay specimen (a witness authentic for one plan, presented beside
   another) is **refused** after the fix — the regression that pins the threat.
4. A witness missing/malformed `plan_ref` or `decision` refuses (structural
   validity, check 1/2) — not a silent pass.
5. **Migration:** a legacy (pre-binding) witness does not admit any plan post-fix
   (no silent grandfather); NS-1/NS-1R bytes are untouched; a re-run path is a
   successor plan + bound witness. No `(plan_ref, witness-digest)` compat
   aperture is added absent a named requirement.
6. The check reads the *same* resolved witness bytes as the authenticity check
   (no re-fetch between digest-match and plan_ref-match — TOCTOU closed).
7. **Sandwich:** mandatory adversarial review of the admission change (codex-exec,
   or the fresh-no-context-agent substitute — codex sandbox dead on this host).
   Exit codes observed; no ceremonial green.

## Non-goals

- Not a general approval ontology. Not ration-schema expansion. Not supervisor /
  execution arming. Not testimony adapters. Not rewriting NS-1's history (frozen
  v0 bytes stay frozen; migration makes successors).

## Validation provenance

- **Gate 1 — operator ratification (custody-affecting, §8): DONE 2026-07-13.**
  Contract shape ruled = witness-carries-plan_ref (shape (ii) rejected);
  migration disposition ruled = no grandfather aperture, successors not in-place
  rewrites. Hash-cycle caveat pinned.
- **Gate 2 — escape-count pass over this ruled spec:** required to read 0
  escapes before the build_slice dispatches. Pending.
