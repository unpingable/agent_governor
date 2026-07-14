# Design spec_slice: approval binds plan_ref

**Status: BUILT + CLOSED 2026-07-14.** Contract ruled (witness carries plan_ref,
seam B: AG re-hashes exact plan bytes), pins folded, escape-count 6→0, built,
adversarial sandwich 0 findings, suites bare AG 16875 / maude 360. Receipts:
AG `5a0bca3`, maude `e5fd7f1`. See "Build outcome" at the tail. The ruling +
pins below are the record; history retained.

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

**Grounding (where this lands) — see the Seam ruling (B) below; this note is
superseded by it.** `daemon.py:~3518` already does check (1) —
`sha256(witness_bytes) == approval_witness_digest`. The build does NOT trust the
caller-supplied `source_plan_digest` as the plan identity (escape #3). Per seam
ruling B, `execution_request` carries the exact `plan_bytes`; AG computes
`actual_plan_ref = sha256(plan_bytes)` itself and requires
`witness.plan_ref == actual_plan_ref == source_plan_digest` (the caller digest
is a consistency assertion only). Check (4) = one resolved, snapshotted
`witness_bytes` copy; (5) is the negative regression.

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

## Build pins (folded 2026-07-14, resolving the 4 engineering escapes)

- **Witness wire format (#1):** `witness_bytes` is UTF-8 JSON, a single object
  with (at least) `{"witness_version": str, "decision": str, "plan_ref":
  "sha256:<64hex>"}`. AG **parses the exact received bytes** (`json.loads`) and
  **never re-serializes** — the authenticity digest and `actual_plan_ref` are
  over original bytes (pin 1). The three keys must be present with correct
  types; extra keys tolerated (forward-compat); wrong shape → invalid.
- **`decision` vocabulary (#2):** closed. `decision == "approve"` authorizes;
  any other value → refuse (does not authorize).
- **`witness_version` (#6):** known set `{"approval-witness/v1"}`; unknown → refuse.
- **Mandatory bytes (#5, fail-closed):** BOTH `plan_bytes` and `witness_bytes`
  must be present and non-empty for a v1 grant activation. Absent/empty → refuse.
  (Closes the daemon's `if witness_bytes is not None` fail-open.)
- **Size bound (pin 8):** `plan_bytes` ≤ 1 MiB, `witness_bytes` ≤ 64 KiB. Over → refuse.
- **Refusal vocabulary (closed, 2 kinds):**
  - `approval_plan_ref_mismatch` — the triple `source_plan_digest ==
    sha256(plan_bytes) == witness.plan_ref` is not all-identical (the replay
    defense; the slice's named refusal).
  - `approval_witness_invalid` — every structural failure: missing/empty bytes,
    size exceeded, authenticity digest ≠ `sha256(witness_bytes)`, non-JSON,
    missing/mistyped keys, unknown `witness_version`, `decision != "approve"`.
- **Placement:** the pure verifier `verify_approval_binds_plan(...)` runs in the
  daemon's `runtime_grant_activate` (THE authority checkpoint, `daemon.py:3481`)
  **before** `activate_execution_grant`; it snapshots both byte blobs to
  immutable `bytes` at entry and reads them once (pins 2 + 6, TOCTOU closed).

## Non-goals

- Not a general approval ontology. Not ration-schema expansion. Not supervisor /
  execution arming. Not testimony adapters. Not rewriting NS-1's history (frozen
  v0 bytes stay frozen; migration makes successors).

## Validation provenance

- **Gate 1 — operator ratification (custody-affecting, §8): DONE 2026-07-13.**
  Contract shape ruled = witness-carries-plan_ref (shape (ii) rejected);
  migration disposition ruled = no grandfather aperture, successors not in-place
  rewrites. Hash-cycle caveat pinned.
- **Gate 2 — escape-count pass (2026-07-13): 6 escapes → seam RULED (B),
  build-ready.** The load-bearing #3/#4 became the seam decision, ruled B
  (see "Seam ruling" section); the other 4 are pinnable engineering (below).
- **Gate 2b — confirmatory escape-count on the fully-pinned spec (2026-07-14):
  0 escapes.** Verifier fully specified; all three replay paths (attacker
  controls source_plan_digest / witness content beside another plan / omits
  bytes) closed. One boundary-clarity residual, NOT a build-wrong: the
  `sha256(witness_bytes) == approval_witness_digest` check is **integrity, not
  authenticity** — a *forged* (not replayed) witness that self-hashes is an
  upstream operator-minting concern, explicitly out of scope (non-goals: not
  testimony adapters; witness authenticity is established where witnesses are
  minted, NOT here). Wording corrected so no implementer reads "authentic" as
  "vetted by AG." Digest-format pin: all three digests compared in the same
  `sha256:<64hex>` form (normalize before compare); mismatch fails closed.
  - **#1 witness content format** — no wire format pinned (JSON? canonical-JSON?
    key names? encoding? `witness_bytes` is str-or-bytes at daemon L3520). *Pin
    at build:* canonical-JSON, keys `{witness_version, decision, plan_ref}`,
    UTF-8; the digest is over those exact bytes. (Changes operator minting
    tooling — already in Ripple.)
  - **#2 `decision` vocabulary** — no closed set for "authorizes execution."
    *Pin at build:* closed vocabulary, `decision == "approve"` authorizes; any
    other value refuses (mirrors AC1's closed refusal).
  - **#5 `witness_bytes` optional → fail-OPEN** — daemon L3519 runs the check
    only `if witness_bytes is not None`; omit the witness and all binding skips.
    *Pin at build:* witness_bytes MANDATORY for any plan requiring approval;
    absent → refuse (fail-closed). This is arguably a latent bug in the current
    code independent of this slice.
  - **#6 `witness_version`** — shown, unchecked. *Pin at build:* known version
    required; unknown → refuse.
  - **#3 + #4 — the replay hole survives, and the fix is NOT AG-local (SEAM
    DECISION, operator/architecture).** The ruled check is
    `witness.plan_ref == sha256(exact current plan bytes)`. But the plan bytes
    live at the plan-admission site (`admit_for_execution`, **maude-side**;
    `work_container.py:601` computes `plan_ref = sha256(plan_bytes)`). AG's
    daemon handler (L3505) only receives a **caller-supplied** `source_plan_digest`
    — it has no plan bytes to hash. So `witness.plan_ref == source_plan_digest`
    is satisfiable by an attacker who sets `source_plan_digest = witness.plan_ref`
    while running a different plan. **The grounding note in this spec that said
    "== request.source_plan_digest" was wrong — it weakened the ruling.** The
    real question the ruling did not resolve: **where is
    `witness.plan_ref == sha256(plan_bytes)` enforced, and does AG verify it
    independently or trust maude's upstream admission?**
    - Placing it only in maude's `admit_for_execution` = AG trusts a maude-supplied
      digest for an authority decision, which cuts against "AG decides what the
      room may claim."
    - Having AG re-hash requires the plan bytes to cross to AG's grant-binding
      step (a wire-contract change), so AG independently verifies.
    This is a cross-repo authority-placement decision (custody-adjacent).
    **RULED (operator, 2026-07-13): B — AG re-hashes over exact bytes.** See the
    "Seam ruling" section below.
  - **Not escaping:** hash-cycle caveat (clear negative guard); TOCTOU/resolve-once
    (AC6 + single witness_bytes copy).

## Seam ruling (operator, 2026-07-13): B — AG re-hashes over exact bytes

**Chosen: B.** AG re-hashes the exact plan bytes supplied with the grant-binding
request. **Not B′** (AG verifies a content-addressed reference): B′ solves
"don't trust maude's digest" by trusting an as-yet-unruled retrieval substrate
(resolver identity/availability, immutable-retrieval semantics, custody of
returned bytes, disappearance behavior, a new TOCTOU seam) — that is trust
relocation, not verification. **A is out** — if maude alone verifies the
relation, AG accepts maude's conclusion about an authority predicate rather than
adjudicating it.

### The contract

```text
maude reads exact plan bytes once
  → computes its local plan_ref
  → sends exact immutable plan_bytes + approval witness_bytes to AG

AG (grant-binding):
  actual_plan_ref = sha256(plan_bytes)          # AG's own hash of the bytes it was given
  require source_plan_digest == actual_plan_ref  # caller digest is a CONSISTENCY ASSERTION, never the authority basis
  require witness.plan_ref     == actual_plan_ref
  require witness decision / version / authenticity valid
  mint or refuse
```

The caller-supplied digest becomes a **consistency assertion**, never the
authority basis. Authority-critical identity is established by AG over the exact
bytes, independently.

### Pins (required before/for build)

1. Hash the **original bytes**, not parsed or reserialized YAML.
2. **Snapshot both `plan_bytes` and `witness_bytes` to immutable bytes
   immediately** at request construction — a digest-verified *mutable* buffer is
   not a frozen witness (repeat firing of the S7 mutable-verified-buffer scar;
   `~/.claude/.../scar_mutable_verified_buffer.md`). Mutation after request
   construction cannot change either hash input.
3. Refuse if either `plan_bytes` or `witness_bytes` is absent for the new
   witness version (fail-closed — closes escape #5's fail-open guard).
4. Refuse unless claimed digest, AG-computed digest, and `witness.plan_ref` are
   **all three identical**.
5. Replaying Plan A's witness with Plan B bytes refuses **even if the caller
   lies about `source_plan_digest`** (the load-bearing regression).
6. Unknown witness versions refuse (escape #6).
7. Legacy (pre-binding) witnesses do not silently enter the new path
   (composes with the migration ruling — no grandfather aperture).
8. A sane **size bound** on transmitted plan bytes ("plans, not Blu-rays").

### The general principle (candidate doctrine — composes with predicate-witness)

> Authority-critical identity is established by AG over exact evidence bytes
> presented in the adjudication request. References and caller-supplied digests
> may locate or cross-check evidence, but cannot substitute for independent
> verification.

Firing case for why the ceremony mattered: the escape-count caught code that
would *visually* implement the ruling while *semantically* checking an
attacker-controlled restatement of it (`witness.plan_ref == source_plan_digest`,
both caller-supplied) — the kind of check that looks reassuring in review.

### B′ later (transport optimization only)

B′ can become a *carriage* optimization once the constellation has a governed
content-addressed artifact service whose contract AG is authorized to rely upon.
The logical rule stays B — AG obtains bytes and hashes them independently; only
the transport changes. Not now; not part of this slice.

**Wire-contract implication (for the build):** `execution_request` (maude→AG)
must carry `plan_bytes` (bounded), not just `source_plan_digest`. That is a
plan-envelope contract change coordinated with maude — flagged, sequenced in the
build, not done unilaterally.

## Build outcome (2026-07-14) — DONE, all gates green

- **AG (authority):** `src/governor/runtime/approval_binding.py` — pure
  `verify_approval_binds_plan()` implementing seam B (AG re-hashes exact
  plan_bytes; `source_plan_digest == sha256(plan_bytes) == witness.plan_ref`,
  all normalized; two closed refusals; snapshot-to-immutable; mandatory
  fail-closed; size bounds). Wired into `daemon.py` `runtime_grant_activate`
  BEFORE `activate_execution_grant`, replacing the `if witness_bytes is not
  None` fail-open. `witness_verified` → `plan_binding_verified`.
- **maude (wire lockstep):** `execution_request` now carries the exact
  `plan_bytes` — `PlanEnvelope.source_text` (the bytes `plan_ref` hashes) →
  `GrantActivationCall.plan_bytes` → `runtime_grant_activate(plan_bytes=…)` →
  daemon `params["plan_bytes"]`. maude computes nothing AG trusts; AG re-hashes.
- **Tests:** `tests/test_approval_binding.py` (18 — positive twin, replay-refused
  even when the caller lies about source_plan_digest, missing/oversized/malformed/
  unknown-version/non-approve/non-bytes all → closed refusals) + daemon
  `test_approval_replay_refused_at_rpc` + `test_missing_plan_bytes_refused_fail_closed`
  + updated grant fixtures/harness. Suites bare: **AG 16875 passed**, **maude 360
  passed**.
- **Sandwich:** fresh-agent adversarial review → **0 exploitable findings**
  (replay requires a SHA-256 collision). Its one non-exploitable note (dict as
  evidence bytes → raw TypeError) hardened to `approval_witness_invalid`.
- **Migration:** unchanged legacy path refuses (mandatory bytes, no grandfather);
  NS-1/NS-1R bytes untouched; a re-run is a successor plan. Witness *content*
  format (`{witness_version, decision, plan_ref}`) is operator-minting tooling —
  AG parses it; producing bound witnesses for real NS runs is downstream.

## Witness producer (completeness follow-on, 2026-07-14)

The slice above defined the witness *format* AG enforces but left nothing that
*produced* one — inert for real runs until the operator can mint a bound
witness. Now shipped:

- `src/governor/runtime/approval_witness.py` — `build_approval_witness(plan, decision)`
  mints the bound witness (`plan_ref = sha256(plan bytes)`, canonical JSON,
  reuses the verifier's version/decision constants — no format drift);
  `write_approval_witness(...)` writes it to the witness directory maude's
  resolver reads, keyed by `sanitize_ref(approval_ref)` (mirrors
  `maude/plan/witness.py`); refuses to overwrite an existing approval act.
- CLI: `governor runtime approve-plan <plan_file> --ref <approval_ref>
  --witness-dir <dir> [--decision approve]` — running it IS the operator's
  approval act.
- **Round-trip invariant (the load-bearing test):** a witness minted for plan P
  verifies for P and refuses beside any other plan (`tests/test_approval_witness.py`,
  11 tests incl. the CLI). **Cross-repo drive PASSED:** AG producer → maude's
  real `parse_plan_envelope` + `project_execution_request` → AG verifier accepts,
  all three `plan_ref`s identical; replay refuses. maude is unchanged (its
  resolver is format-agnostic — it returns bytes; the witness format is AG
  semantics).
- **Still downstream (not this):** witness *authenticity* (that a witness
  reflects a recorded, authorized operator decision — signing/attestation) is
  standing/testimony territory. Running the producer is the approval act; a
  governed signing layer is future work, per the slice non-goals.
