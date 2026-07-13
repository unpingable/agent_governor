# Design — S6: first-class `execution_request:` plan block (versioned contract)

> STATUS: RATIFIED direction + migration model (operator, 2026-07-13). This is
> the design/adjudication note the grant-use design doc
> (`design-grant-use-gate.md`) said S6 must have "in a fresh context, NOT a
> tail-of-session addition." It locks the versioned-contract change both repos
> build against. Supersedes the one-paragraph S6 stub in the slice plan.

## The doctrinal sentence (operator, 2026-07-13)

> **Approval attaches to plan bytes, not reconstructed intent; schema migration
> creates a successor artifact rather than revising an approved predecessor.**

Everything below is a mechanical consequence of that sentence.

## What S6 is (and is not)

**Is:** make the plan→request boundary *explicit and checkable in the plan*.
Introduce one first-class block —

```yaml
execution_request:
  write_paths: ["crates/nightshiftd/src/**", "crates/nightshiftd/tests/**"]
  commands:
    - {program: cargo, argv_prefix: [test]}
    - {program: cargo, argv_prefix: [build]}
  network: denied
  git: denied
  horizon: run
```

— and **retire the inferred boundary**: the top-level `scope_allowlist` field
and the silent projection of shell commands out of the referenced RationCard.

**Is not:** a new authority source. A plan still only *requests*; only
`activate()` (the daemon) *mints*. The block is copy-with-citation from AG
objects, subject to the same §7 constraint-projection discipline that already
governs v0 (see below). It does not arm anything (`enforcement:
declared-effects-only` is unchanged).

## Why it is not optional cleanup

Today the request is reconstructed from two legacy sources, neither of which
names itself as "the request":

| effect | v0 source (inferred) | v1 source (declared) |
|--------|----------------------|----------------------|
| write paths | top-level `scope_allowlist` | `execution_request.write_paths` |
| commands | `allowed_shell_commands` read out of the RationCard digest at projection time (`_commands_from_ration`) | `execution_request.commands` (structured, in the plan) |
| network/git | hardcoded `denied` in the projector | `execution_request.network/git` (explicit, still capped) |
| horizon | hardcoded `"run"` in the projector | `execution_request.horizon` (requested, still validated at mint) |

The v0 commands never appear in the plan at all — they are pulled from a
referenced digest during projection. That is the "inferred through legacy
fields" the grant-use doctrine names: the thing the operator approves (the plan
bytes) does not legibly contain the thing that gets granted (the commands).
S6 makes the request visible in the artifact under approval.

## Estate (verified 2026-07-13, both repos)

- **maude is not further along.** It has S4a projection
  (`maude/src/maude/plan/execution_request.py`), S4b runner-attach, S4c-minimal
  diagnostic — exactly what the grant-use build status records. There is **no**
  `execution_request:` block and **no** `plan_version: 1` in maude. What exists
  is the legacy-reading projector S6 replaces.
- **The AG daemon stays boring.** `runtime.grant.activate`
  (`daemon.py:3481`) receives an *already-projected* `execution_request` dict
  and mints from it. S6 changes *how the request becomes explicit* (maude-side
  parse/projection), **not what AG receives on the wire.** The daemon RPC and
  `execution_grant.py` are untouched. That the wire boundary absorbs this change
  with zero daemon edits is evidence it was placed correctly.
- **§7 copy-with-citation already exists** (`plan-envelope-v0.md` §7): every
  AG-originated enforced constraint records BOTH its resolved value AND its
  source digest in `governance.projected`, verified three-valued
  (`verified` / `governance_ref_mismatch` / `unverified`). S6 **preserves**
  this: the `execution_request` values still originate in AG objects (RationCard
  shell allowlist, plan scope), so they are still cited in
  `governance.projected` and verified against their source. The retirement is of
  the *inference* (projector silently reading the ration), not of the *authority
  binding* (the declared commands must still match the cited ration, or
  `governance_ref_mismatch`).

## Migration — version-discriminate, freeze NS-1 (RATIFIED)

The discriminator is the **value** of the already-existing `plan_version` field:

- `plan_version: 1` → **v1 path.** Top-level `scope_allowlist` **forbidden**
  (its presence under v1 is a refusal — no within-plan two-sources). The
  `execution_request:` block is **required iff a `governance` block is present**
  — a governed plan's request must be legible in the bytes the operator
  approves; an ungoverned plan mints no grant, so the block is optional (and its
  absence means an uncompressed run, exactly as an absent v0 `scope_allowlist`
  did).
- `plan_version: 0` → **v0 path, gated by a closed frozen allowlist.** Decodes
  via the legacy projector **iff** the plan's `plan_ref` is an explicit member
  of the frozen set. A v0 plan whose hash is not frozen **refuses** — you cannot
  author new v0 plans.
- **missing `plan_version`** → **refuse.** "Unversioned means legacy" is exactly
  the permanent ambiguity generator we are closing.
- **any other value** → **refuse.**

All four refusals reuse the existing **`invalid_plan_envelope`** class with a
discriminating detail string (`plan_version_missing` / `_unknown` / `_retired` /
`legacy_field_under_v1` as detail tokens, not new classes). The refusal
vocabulary stays closed — the parser already maps unknown `plan_version` to
`invalid_plan_envelope`, and S6 keeps that convention rather than minting
version-specific classes.

### The microscopic aperture

The frozen-v0 allowlist is a closed, explicit set of `plan_ref`s. Its sole
member:

```
NS-1 (committed candidate specimen):
  sha256:da241bc77f8b209c3a25a21866fbde22f2a8b799d1ea3b61d588a727849a1b47
```

Consequences, all intended:

- **NS-1's bytes are never touched.** The historical fact — *NS-1 was compiled
  and executed under the v0 inferred-request contract* — stays true and
  un-rewritten. No re-approval ceremony over already-executed bytes.
- **The freeze is currently inert by design.** The committed NS-1 is
  `governance_status: candidate`, so admission refuses it
  (`governance_not_approved`) before projection is ever reached. The frozen
  entry records NS-1's v0 *identity and decoding semantics*; it is not a live
  re-run affordance (NS-1 already ran; re-running is not a goal). If a genuinely
  approved v0 artifact ever needed replay, its hash is added to the frozen set
  by an explicit operator act — never by an unversioned fallback.
- **Even NS-1's own re-approval must become a successor.** Promoting NS-1 to
  `approved` changes its bytes → changes its `plan_ref` → leaves the frozen set
  → refuses as a retired v0 plan. To run the same intent again it must be
  re-authored as a v1 successor. The doctrinal sentence falls out mechanically:
  a re-approved NS-1 is a *new artifact*, not a revised predecessor.
- **The v0 projector survives only as a historical decoder** — not an authoring
  surface, not a fallback. New authorship is v1-only.

### The v1 successor specimen

Rather than rewrite NS-1, S6 ships a **new** specimen expressing the same
intended operation with a fresh identity, hash, and approval record
(`specimens/ns-1r-refusal-registry-v1/`). It is the v1 reference specimen and
the integration witness for S6. It is *not* NS-1 — it inherits the intent, not
the approval.

## Cross-repo split (RATIFIED — AG drives both, maude's idiom)

**maude** (plan-envelope authority):
- v1 plan-envelope schema (`execution_request:` block on `PlanEnvelope`).
- parser version dispatch (v1 / frozen-v0 / refuse).
- explicit-request projection (reads the block; no ration inference).
- frozen-v0 decoder (closed allowlist; legacy projector retained behind it).
- `plan-envelope-v1.md` spec.
- refusal tests: unversioned, non-frozen-v0, unknown-version, v1-without-block,
  legacy-fields-under-v1; plus frozen-NS-1-still-decodes-v0.

**AG** (grant-use design + specimen custody):
- this design/adjudication note.
- confirmation the daemon wire request is unchanged (no daemon edits).
- frozen NS-1 registration (the hash above, recorded here + wherever maude
  reads the frozen set — single source of truth, cited across the seam).
- the v1 successor specimen + its new approval record.
- cross-repo integration evidence (v1 specimen → maude parse → projection →
  `runtime.grant.activate` → grant, end to end).

## §7 preservation — the block is still copy-with-citation

Under v1 the plan author copies the RationCard's allowed shell commands and the
approved scope into `execution_request`, AND records the source in
`governance.projected` exactly as v0 required. The **intended** three-valued
discipline:

- `execution_request.commands` disagrees with the cited RationCard →
  `governance_ref_mismatch`.
- an `execution_request` value originating in an AG object with no
  `governance.projected` citation → `invalid_plan_envelope` (the §7 exhaustive
  rule is unchanged: every AG-originated enforced value cites its source).
- an uncheckable citation on a *governed, approved* run → refuses
  (`governance_approval_unverified`).

> **Implementation status (corrected after the S6 sandwich, 2026-07-13):** the
> **value-comparison** of a projected `execution_request` field against its
> cited source is **specified but not yet implemented** — admission today
> presence-checks the citation and digest-resolves the source, but does not
> verify declared-⊆-allowed. This is a **pre-existing** §7 gap (v0's
> `scope_allowlist` projection was presence-only too), surfaced by the refuter
> and recorded in `GAP-s6-sandwich-authority-findings.md` (finding 1) for an
> operator ruling. Until built, the citation is structurally present but not
> value-load-bearing; the operator's approval of the visible plan bytes is the
> operative authority, not the ration cross-check.

So S6 moves the request into the plan and keeps the citation *structure* intact;
the value-verification that would make the citation load-bearing is the named
follow-up. Legibility up (commands visible in the approved bytes); the machine
cross-check against the ration is scheduled, not yet enforced.

## Sandwich placement

The versioned-contract change is delicate at exactly one seam: **parser version
dispatch + the frozen allowlist**. That is where a migration quietly grows a
precedence rule or an unversioned fallback. The adversarial sandwich (Opus +
independent refuter, per the grant-use discipline) targets:

1. **Fallback smuggling** — can any unversioned or unknown-version plan reach a
   decode path? (Must refuse.)
2. **Frozen-set widening** — can a non-frozen `plan_version: 0` plan decode?
   (Must refuse.) Can the frozen check be bypassed by hash confusion
   (prefix/normalization)?
3. **Two-sources window** — can a v1 plan carry legacy `scope_allowlist` and
   have it silently win, or blend, with `execution_request`? (Must
   `invalid_plan_envelope`.)
4. **Citation bypass** — can `execution_request.commands` diverge from the cited
   RationCard and still project? (Must `governance_ref_mismatch`.)
5. **Horizon/axis creep** — can the plan request a broader `horizon` or a denied
   axis and have activation honor it silently? (Must cap at mint; record in
   `unmet_axes`.)

## Non-goals (S6)

- No change to the AG daemon RPC or `execution_grant.py` (wire unchanged).
- No arming of substrate effects (`declared-effects-only` stays).
- No multi-actor attribution (S5d), no full grant panel (S4c-full).
- No blanket v0→v1 corpus migration — the frozen set holds exactly the one
  extant artifact; growth is by explicit operator act only.
