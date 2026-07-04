# Inventory / crosswalk — transition-kernel pickup (reduction)

Date: 2026-06-23. Reduction mode only — no implementation. Two cross-repo inventories
(Standing: `~/git/standing`; AG mint boundary: `/home/jbeck/git/agent_gov`).

## Verdict: **(B)** — an honest Standing grant-token exists, but one named refusal is missing: **spend-time scope matching**

Standing issues a real grant-token (`Grant` + the SQLite store *is* the enforcement layer)
that refuses **4 of the 5** load-bearing classes itself, with typed errors + content-addressed
receipts — a consumer inherits real refusals, not stored fields it must police. The fifth,
scope-mismatch-at-spend, is not refused by Standing and is exactly the "has scope-ish fields
≠ may mint" demon. So: close, but not fully present by the operator's own rule.

## Standing side — what it issues (`~/git/standing`)

`Grant { id, subject: Principal, scope: GrantScope{action,target}, issued_at, expires_at }`
(`crates/standing-grant/src/grant.rs:30`), persisted with `state`, `latest_receipt_digest`
(CAS head), `expires_at`. Mint boundary: `GrantAction::Request → GrantMachine::issue →
store.record_transition(Issued)` (`standing-cli/src/main.rs:394`).

| Load-bearing refusal | Standing refuses it itself? | Mechanism (verbatim) |
|---|---|---|
| **expiry** | YES | `StoreError::GrantExpired` once `now >= expires_at` (`standing-store/src/lib.rs:429`) |
| **single-spend** | YES | terminal `Used` FSM (zero transitions) + CAS on `latest_receipt_digest` (`lifecycle.rs:62`, `lib.rs:461`) |
| **replay** | YES | `jti`+audience replay guard → `ReplayDetected` (`standing-identity` `replay.rs:31`) |
| **subject/binding** | YES | `Unauthorized` if `actor.principal.id != grant.subject_id` (`lib.rs:413`) |
| **scope (mismatch at spend)** | **NO** | scope bound at issue + carried on the receipt chain, but `grant use` names no action/target (`main.rs:202`) → no `ScopeMismatch` refusal at consumption |

Other properties present: issuer/authority (operator-fiat genesis root, exactly-one,
`policy_hash` pinned at issue); provenance (content-addressed `Receipt` digest, hash-chained).
Caveat: identity is HMAC-over-shared-secret (`IDENTITY-SCARS.md`) — bounds the *strength* of
the refusals, not their presence.

Smallest shape to close the gap: give Standing's `transition()` (the `Used` path) the
attempted `(action, target)` and refuse `StoreError::ScopeMismatch{granted, attempted}` when
it differs from the grant's bound `GrantScope`.

## AG side — where AG mints/continues authority (the pickup boundary)

VALIDATE-only surfaces (not mint): `standing_client.py` (`StandingClient.verify()` — a
SPEC-honoring consumer stub, "replace with real cross-repo client when wiring lands"),
`standing/` validator package (validates chains, never issues).

**Live MINT/CONTINUE boundaries** (`runtime/supervisor.py`) — the D010 target:

| Boundary | Authorizes | Basis TODAY |
|---|---|---|
| `create_session` (`supervisor.py:257`) | a session exists / is supervised | AG-local fiat; effect budget = LA grant |
| `fork_session` (`supervisor.py:413`) | child continues parent authority | prior local `approved` promotion — **no standing** |
| `_handle_tool_proposed` (`supervisor.py:614`) | a WRITE step crosses to effect | LA consume on hot path; continuation grant is **AG-internal** |
| `activate` Office 2 (`activation.py:449`) | rung-activation act-standing | **`standing_ok: bool` fiat**; `external_standing_receipt` carried-not-parsed |

**Cleanest seam for `StandingGrantToken → AGGrantAdapter`:** `activation.py` Office 2
(`activation.py:449`). It is already an isolated, transactional "act-standing" office with a
typed refusal (`REFUSED_NO_STANDING`), a reserved receipt field (`standing_basis`, line 496),
and a constellation-mode contract that already expects an external standing receipt id. The
adapter would replace the `standing_ok: bool` parameter with a verified `StandingGrantToken`.
(The supervisor boundaries are higher *value* — they are the actual actor/session/step
authority — but harder: three boundaries on the hot path. Activation is the cleanest *first*
demonstration of the pattern.)

## Crosswalk: clean-map / missing / would-launder-if-inferred

- **Maps cleanly** (Standing already refuses; AG inherits): issuer, subject-binding, expiry,
  single-spend/replay, provenance/receipt-id. AG's `REFUSED_NO_STANDING` ↔ Standing's
  `GrantNotFound`; AG's exactly-once-spend office ↔ Standing's terminal `Used`.
- **Missing (named):** spend-time **scope-mismatch** refusal. Standing binds scope but does
  not adjudicate it at consumption.
- **Would be laundering if inferred:** treating "a Standing grant exists / is unspent" as "a
  grant **for this act/target** exists." That inference is the demon — it converts a scope
  *field* into mint authority without anyone refusing a mismatch.

## The one unresolved fork (exhibit both, do not axiomatize — CLAUDE.md debugging discipline)

Where does spend-time scope-mismatch refusal live?

- **Model X — Standing's job.** The token is not fully present until Standing refuses
  `ScopeMismatch` at spend. Honors the operator's rule literally ("refuse scope … without AG
  inventing locally"). Cost: a cross-repo Standing change before AG adapts.
- **Model Y — the consumer's job at the mint boundary.** The scope *value* is Standing-attested
  (issued, content-addressed, on the chain); matching an attested scope against the requested
  act is ordinary consumer behavior (cf. a JWT `aud`/`scope` claim). Not laundering, because AG
  invents no scope — it only applies an attested one. Cost: AG performs the match; the
  refusal's *locus* is AG, which is precisely what the operator's rule is wary of.

This fork is the ratification question for D010 and decides Slice 1's shape (see NEXT.md).
Recommendation: do not let scope-match be *implicit* either way — it must be an explicit,
receipted refusal with a named locus.

---

## Three worlds (B1, executed 2026-07-02)

### World 1 — AG parked branch `feat/transition-kernel-slice-1b`
Two commits past main: `24acd8f` (Step A: `standing_grant_use.py`, 501 lines —
GrantUsed/GrantRefused/NoVerifiedResult, ResolvedBinary ENV→PATH→cargo,
injectable SubprocessRunner, SCHEMA_GRANT_USE_V1, 5 RECOGNIZED_REFUSAL_CLASSES,
7 NO_VERIFIED_RESULT_REASONS) and `f003519` (Step B: activation.py Office 2
consumes verified Standing; +453 test lines across test_standing_grant_use /
test_activation). **Slice 1b (=B4) is IMPLEMENTED on this branch** — the
capsule's "ACTIVE NEXT" understated it; B4 is now verify-and-adopt, not build.

### World 2 — `~/git/transition-kernel` (HEAD `5cd7eb0`, 2026-06-18)
Corpus = `vectors/legacy/` ×9: 01-valid-passes · 02-no-standing-refused ·
03-standing-unverifiable-refused · 04-admission-denied-refused ·
05-gap-accounted · 06-replay-refused · 07-synthetic-evidence-fenced ·
08-temporal-lapse-refused · 09-temporal-lapse-twin-passes.
**Differential run 2026-07-02: `python3 scripts/differential.py` → "[differential]
9 cases; 0 unaccepted divergence(s)", EXIT=0.** Summit `stage3b2-first-effect`
(`1a688eb`): "first replay-legible bounded effect through the live AG
supervisor." Lean feedstock: Scratch/NoFreeContinuation.lean authored
(docs/LEAN_OBLIGATIONS.md GAP-2, operational gate SHIPPED C1–C4; Lean is
design evidence, not verified reduction).

### World 3 — `~/git/standing` (HEAD `d1883c3`, 2026-06-25)
**`1e62ba9` and `f101c55` are PUSHED — both contained in `origin/main`.**
The "unpushed / custody hazard" record (STATUS 2026-06-23, echoed 2026-07-02
morning) is stale. 1e62ba9: ScopeMismatch refusal non-consuming +
`transition_scoped()` + grant-use `--action`/`--target` (+190 lines).
f101c55: `grant use --json` → standing.grant_use.v1 packet, closed
refusal_class set, unmapped errors stay prose (+191 lines).

### Contract-surface correction (feeds B2)
The packet's proposed verdict map (authorized→PASS, denied→BLOCK, gap→WARN,
advisory_only→OBSERVE, unaccounted→ERROR) is **NOT the implemented shape**.
Wicket SPEC §7 owns {authorized, advisory_only, denied, gap, unaccounted}
(hard vs soft rejection states). The kernel does not emit wicket verdicts —
it composes office outputs and mints outcomes {consumed, refused,
gap_accounted, escalated} with the 12-kind S4-lite refusal enum
(transition_core.rs, wire via as_str()) + 5 refusing seams (standing /
standing_spendability / la / wicket / proposal_validator). The SHARED
vocabulary across Lean/Rust/Python is the refusal enum + seam names; wicket
verdicts remain wicket's. The corpus is the contract; the packet's map is
recorded as a refuted assumption, not retrofitted.

### Corpus coverage gaps (B5 enumeration seed)
No corpus case exercises: **scope_mismatch** (kind exists in the enum; refusal
now implemented in Standing 1e62ba9), **token_expired / token_revoked /
unknown_token** (LA-side kinds), **standing_expired** distinct from
temporal-lapse, stale-basis-as-live (NQ BASIS_STALE v0). Freshness IS covered
(08/09 pair). → B5 slices, one case each, after Q-B3.

---

## Invariant survival map (B2 — re-derived cold 2026-07-04, Fable pass)

Supersedes the 2026-07-02 draft **in place** (the draft predated the B5 quartet,
corpus 13, and B4 adoption, was missing three enumerated rows, and carried two
tier errors — marked ⚠ below). Ground truth: B1 (above) + Packet C custody +
B5 quartet (corpus 13) + B4 (Slice 1b on main, verify-run receipt `59cf2553`).
The shared Lean/Rust/Python vocabulary is the **12-kind refusal enum + 5
refusing seams + 4 outcomes** (`transition_core.rs:86-97`, `:124-128`); wicket
verdicts stay wicket's; **the corpus is the contract** — differential re-run
this pass: **13 cases, 0 unaccepted divergences, EXIT=0**.

Lean read at HEAD **`84d6d24`** (2026-07-03; three scratch commits past the
roadmap snapshot `762967c`). Tiers are the repo's own per-file `Custody-Class`
headers — **verified per file this pass, not assumed from directory**:
PUBLIC-SHIPPED [1.0] (8 public modules per the `AdmissibilityKernels`
aggregator) · ANNEX (compiled support; cannot ratify) · SCRATCH (pilot-only) ·
UNRATIFIED-CANDIDATE (uncitable).

| invariant (operational statement) | Lean source (tier) | Rust surface | corpus case | status |
|---|---|---|---|---|
| authorized ⟺ every office green; one refusing office refuses the transition | `authorized_iff_all_green` (`Authority.lean:116`) [1.0] | office composition → outcome `consumed` only when standing+admission+capacity all pass | 01 + 02/04 | **covered** |
| no-basis / advisory basis never authorizes | Authority verdict algebra [1.0] | wicket office input; `gap` → outcome `gap_accounted` (accounted, never authority) | 05 | **covered** |
| revoked basis cannot be an authorized step | `revoked_basis_cannot_be_authorized_step` (`Execution.lean:133`) [1.0] | refusal kind `token_revoked` (la_seam) | **case 11** | **covered (B5 A-2)** |
| freshness is metric-time on compatible witnesses; lapse refuses | Freshness [1.0] — **five** negative theorems: `expired_not_fresh` / `not_yet_valid_not_fresh` / `incoherent_not_fresh` / `not_precedes_not_fresh` / `divergence_excessive_not_fresh` (`Time.le` is opaque, so the two `TemporallyCoherent` failure directions are structurally distinct) | `standing_before_spendability_not_bounded` + typed `freshness_subcase` (spendability seam; `standing_spendability.py:77-86`) | 08/09 + subcase (08 = `expired`, asserted) | **CLOSED (B5 A-5, covered_by_single_kind)** — ruling 2026-07-03 keeps the single refusal kind; Lean variants ride the machine-readable `freshness_subcase`. Note: AG's 4-value subcase enum folds BOTH incoherence directions into `incoherent_interval` — recorded in the granularity gap below, not a corpus blocker. |
| single-spend / replay refuses before effect | ⚠ tier corrected: `one_receipt_cannot_license_two_discharges` (`Scratch/ExecutionObligationSequent.lean:219`) is **Custody-Class: SCRATCH** — the draft's "[v4-resident]" overstated it; no ANNEX-or-better receipt-linearity wall exists (BoundedCalculi `ObligationResidue` covers residue persistence, not the two-discharge wall) | `already_consumed`; durable-spend write-ahead; Standing terminal `Used` FSM upstream | 06 | **covered (spend side) operationally** — corpus + implementation pins carry the authority; the Lean warrant is pilot-tier (promotion candidate, not a blocker) |
| request-side linearity: one admission receipt funds ONE capacity request | same SCRATCH sequent family | **UNFENCED** (reconciliation F-A3b-2: eligibility_reference reuse unrefused AG-side; idempotency_key optional) | **NONE** | **gap — code AND corpus**; cross-repo (LA contract), record-first |
| spend-time scope mismatch refuses non-consuming | D010 Model X (ratified); Standing `1e62ba9` | refusal kind `scope_mismatch` (la_seam variant); Standing-store variant now **on main** via Slice 1b (B4, receipt `59cf2553`) | **case 10** | **covered (B5 A-1)** — gauntlet LA-side variant; the Standing-store variant is a separate surface, adopted |
| synthetic/non-observed evidence cannot confer operational effect | WitnessInvariance-adjacent [1.0]; **`PredicateWitnessSeparation` ANNEX** (promoted from Scratch 2026-06-27 — "predicate satisfaction ≠ witness" is the origin-fence doctrine's nearest compiled warrant); AG origin fence doctrine | origin_mode allowlist; `DemonstratedConsumed` type split | 07 | **covered** |
| a successful act does not authorize the next breath | NoFreeContinuation (`Scratch/`, header: SCRATCH/CANDIDATE — informs a consumer, not public-surface) | continuation grant burn (C1–C4 shipped; specimens/continuation-trajectory) | outside golden corpus | **routed** — the trajectory specimen belongs to transition-kernel's FRONTIER corpus (different verdict shape), not golden/corpus (B5 work-order; resolves the draft's "consider promoting" note) |
| corrective = down-edge; corrective moves cannot widen authority | Corrective [1.0]: `corrective_not_forward` / `corrective_not_neutral` (down-edge), `corrective_no_authority_laundering` + `corrective_monotone` (cannot widen) | **no_surface** — kernel does not model corrective moves | — | honest no_surface; do not stretch |
| checkpoint/compaction mints nothing | `checkpoint_mints_nothing` (`BoundedCalculi/CheckpointSettlement.lean`) ANNEX | AG-side concern (reconciliation A3b item 8: PASS); kernel receipts are append-only | — | covered outside kernel |
| stale basis is live-but-distinct (NQ BASIS_STALE v0, post-corpus) | — (NQ contract, not Lean) | **no mapping yet** — open question: stale-basis at cook time maps to `admission_gap_accounted`? or refuses upstream of the kernel? | **NONE** | **B5 design question first, then case** — do NOT mint a 13th refusal kind without operator |
| refusals name the offender | v5/v6 typed `CheckResult` (`Scratch/FiniteSupportChecker.lean`, header: SCRATCH — pilot only) | refusal carries kind + refusing_seam + verbatim offending values | throughout | pilot-grade check via B6; not a wall claim |
| finitary exhaustively-matched verdict enums | the 1.0 load-bearing typed-verdict API [1.0]: `Authority.{Basis,Precedence,Standing,Authority}Verdict`, `SurfaceAuthorization.Verdict` — finitary inductives, refusal theorems per constructor; checker-side v6 `CheckResult` (SCRATCH, pilot) | `RefusalKind` (12) / `RefusingSeam` (5) / outcomes (4) as closed enums, exhaustive `match`, closed `as_str()` wire vocabulary | all 13 + `MANIFEST.json` closed-world admission (custody guard fences unadmitted files) | **covered** — a novel kind is unrepresentable in-type; a novel wire string is a typed error, never coerced (allowlist-authority doctrine) |
| Standing / LA / kernel / receipts separation (no organ adjudicates another's seam) | **no citable Lean warrant** — `NoFreeStandingBridge` exists but is UNRATIFIED-CANDIDATE (⚠ uncitable per tier rule); authority is ratified constellation doctrine (D010 Model X: AG inherits, never adjudicates; LA never-mints; zoning) | every refusal names its `refusing_seam` (5 seams); Slice 1b type split `GrantUsed \| GrantRefused \| NoVerifiedResult` on main | seam attribution spans the corpus: 02/03 (standing) · 04 (wicket) · 10–13 (la) · 08/09 (spendability) | **covered operationally** — misattribution guard: `no_verified_result` never claims Standing refused (D010c three-way). Lean warrant = honest gap (candidate exists; do not lean on it) |
| citation tiers themselves ([1.0] / ANNEX / SCRATCH / CANDIDATE; annex cannot ratify) | the lean repo's per-file `Custody-Class` header discipline + the `AdmissibilityKernels` aggregator scope fence; AG mirror: `docs/roadmaps/tools/lean.md` | **none** — a citation/review discipline, not a runtime type | n/a | **enforced by review, not by type** (honest) — refusal mode: down-tier cite used as authority → finding (R-LEAN-2); fired **twice in this very pass** (single-spend row; separation row) |

**Stop condition: not triggered.** Every invariant above is statable in the
existing kernel vocabulary (12 kinds + 5 seams + 4 outcomes + typed receipt
diagnostics); no `requires_operator` filing needed. The two open design
questions (request-side linearity fence; stale-basis mapping) were already
filed and remain design-first, not vocabulary mints.

**B5 enumeration (updated 2026-07-04):** (1)–(4) scope_mismatch /
token_revoked / token_expired / unknown_token — **DONE** (A-1..A-4, corpus
10–13); (5)/(6) freshness not_yet_valid / incoherent_interval — **closed as
the granularity alignment gap** (ruling #1: single kind + subcase; new cases
only if the window model is enriched); (7) request-side linearity — blocked on
the LA fence design; (8) stale-basis — blocked on its mapping design; (9)
continuation specimen — **routed to the transition-kernel frontier corpus**,
out of golden/corpus scope.

**B3 note:** the custodian recommendation (transition-kernel repo owns
differential.py + corpus; wicket fixtures cross-referenced; AG contributes via
the v7 schema lane — now LIVE, v7.0.0 tagged) stands as filed in Q-B3; B5
executes there once ruled.

## Pilot: v6 finite-support checker over the corpus (B6, executed 2026-07-04)

**Non-binding oracle run — SCRATCH tier, uncitable as authority** (lean
`v6.0.0`, `Scratch/FiniteSupportChecker.lean`, `Custody-Class: SCRATCH`;
read at HEAD `84d6d24`). Per the checker's own scope fence it judges ONE
thing: finite-support resource counting over the resident liberal/linear
normalization skeleton. The pilot asks where that face binds against the
13-case corpus and where it is blind — divergences on excluded axes are the
fence working, not bugs.

**Method.** The counts-only decider `firstDeficient (reads supply : List J)`
was evaluated over each case's resource skeleton;
`firstDeficient_decides_check` licenses the counts-only verdict as the
checker's verdict (offender identity across the two reporters is NOT
claimed, per the module's honesty note). Invocation (verbatim):
`lake build LeanProofs.Scratch.FiniteSupportChecker` → "Build completed
successfully (23 jobs)", exit 0; `lake env lean <harness>.lean` → 13 `#eval`
lines, EXIT=0.

**Mapping convention (declared, load-bearing).** Labels = AUTHORITY
artifacts the scenario *semantically mints* (issuance-convention): supply
iff an issuance record exists; adjudication state (expired / revoked /
mis-scoped) does NOT remove a minted artifact — filtering supply by
adjudication would smuggle the kernel's own judgment into the oracle.
Reads = the gauntlet chain's demands `[standing_grant, admission_receipt,
capacity_token]` (+ a second `capacity_token` in the replay case). Refusal
upstream ⇒ downstream never minted (chain order verified in
`cooked_context_orchestrator._run_chain`: standing → wicket → spendability
gate at step 1.5 **pre-grant** → LA request → LA consume). Disclosed
sensitivities: case 03's cited-but-unverifiable digest and case 13's
LA-unknown token have NO issuance record (absent), though 13's drill *stub*
mechanically grants-then-disclaims; case 05's gap record is not authority,
so it is not supply; a scoped-label alternative encoding (labels carrying
`(action,target)`) was rejected as mapping-massage — it would force
agreement on case 10 by encoding the adjudication into the alphabet.

**Results (verbatim `firstDeficient` output vs frozen corpus verdicts):**

| case | firstDeficient | kernel expected | verdict |
|---|---|---|---|
| 01 valid | `none` | consumed | **agree** |
| 02 no-standing | `some "standing_grant"` | refused `standing_required` | **agree** (offender = refused artifact) |
| 03 standing-unverifiable | `some "standing_grant"` | refused `standing_expired` | **agree** — but counts collapse 02/03: the typed distinction (never-cited vs cited-but-unverifiable) is invisible to counting |
| 04 wicket-denied | `some "admission_receipt"` | refused `admission_denied` | **agree** (denial ⇒ never minted) |
| 05 gap-accounted | `some "admission_receipt"` | `gap_accounted`, consumed=true | **DIVERGE (expected)** — the checker's binary vocabulary cannot express "proceed with accounted debt"; it refuses what the kernel deliberately admits as accounted gap |
| 06 replay | `some "capacity_token"` | refused `already_consumed` | **agree** (linearity home turf) |
| 07 synthetic-fenced | `none` | consumed (Demonstrated) | **agree** on outcome; the operational/demonstrated type split is outside checker vocabulary |
| 08 temporal-lapse | `some "capacity_token"` | refused `standing_before_spendability_not_bounded` | **agree on verdict, DERIVATIVE locus** — the kernel names the cause (lapsed standing observation, spendability seam); the checker names the downstream absence it produced (token never granted) |
| 09 lapse-twin | `none` | consumed | **agree** |
| 10 scope-mismatch | `none` | refused `scope_mismatch` | **DIVERGE (expected)** — scope adjudication of a minted token is not a count |
| 11 token-revoked | `none` | refused `token_revoked` | **DIVERGE (expected)** — revocation is state, not absence |
| 12 token-expired | `none` | refused `token_expired` | **DIVERGE (expected)** — temporal adjudication, not a count |
| 13 unknown-token | encoding-dependent — `some "capacity_token"` (semantic-ledger) / `none` (stub-mechanics; both run, EXIT=0) | refused `unknown_token` | **encoding-dependent (both exhibited, per codex review)** — under production semantics `unknown_token` is an LA ledger lookup-miss (no issuance record for the *presented* token → absence → agree); under the drill's stub mechanics the request step DID grant before consume disclaimed (→ minted → diverge). The stub cannot witness the distinction; the corpus case description ("a token LA does not recognize") is the semantic ground truth, but the counts-face membership of `unknown_token` is claimed only conditional on that reading. |

**Findings.**
1. **8 unconditional verdict agreements, 4 expected divergences
   {05, 10, 11, 12}, 1 encoding-dependent case (13), 0 unexpected under
   either encoding.** The divergences fall exactly on the axes the v6
   scope fence excludes: outcome vocabulary beyond ok/refuse
   (gap-accounting) and adjudication of minted artifacts (scope /
   revocation / expiry). The refusal enum splits into a **counts-shaped
   face** (`standing_required`, `admission_denied`, `already_consumed`,
   absence-surfaced `standing_expired`; `unknown_token` conditional on the
   semantic-ledger reading) and an **adjudication-shaped face**
   (`scope_mismatch`, `token_revoked`, `token_expired`,
   `standing_before_spendability_not_bounded`, `admission_gap_accounted`).
   The split is at the VERDICT level and is *consistent with* the B2 map's
   axis assignments — counts cannot see causes, so this is compatibility
   evidence, not empirical confirmation of the typed-cause decomposition.
2. **Typed refusals carry information counting cannot** (02 vs 03 collapse
   to the same offender) — corroborates the B2 "refusals name the offender"
   row from the other direction: the kernel's vocabulary is strictly finer
   than resource accounting.
3. **Offender-naming degrades under cascades** (case 08): a counts-only
   oracle structurally names the *downstream absence*, not the *upstream
   cause*. Offender fidelity is a kernel property, not a checker property.
4. **Not load-bearing, and no temptation recorded**: SCRATCH tier, one
   policy pair, non-binding. If Lean later promotes the checker family, the
   counts-shaped face above is the candidate oracle surface; the
   adjudication face can never be, at any tier.

**Review trail (sandwich).** codex-exec adversarial pass #1: environmental
BLOCK (broken bwrap sandbox — no file access; retried with inlined
material). Pass #2: substantive **BLOCK** — case 13's encoding contradicted
the declared issuance convention under the drill's stub mechanics, and the
counts/adjudication decomposition was overclaimed as empirical. Resolved by
exhibiting BOTH case-13 encodings with verbatim runs (CorrectiveBoundary
methodological move: model-dependence exhibited, not axiomatized) and
downgrading finding 1 to verdict-level compatibility evidence. Codex also
confirmed the remaining arithmetic consistent ("the blocker is not Lean
arithmetic").

## Roadmap gap: Freshness refusal granularity (filed 2026-07-03, ruling #1)

Current AG closure keeps `standing_before_spendability_not_bounded` as a single
refusal kind, with the Lean Freshness variants preserved in structured receipt
fields as `freshness_subcase ∈ {expired, not_yet_valid, divergence_excessive,
incoherent_interval}`. This closes the corpus rows because the distinction is
machine-readable and receipt-backed, not prose-only (the two-clock gate reaches
`expired`; case 08 asserts it; `standing_spendability.py` + tests pin it).

However, AG's closed refusal vocabulary remains coarser than the Lean Freshness
model, and the current two-clock gate only PRODUCES `expired` — the other three
subcases need window inputs (issued time / skew / max-divergence / an explicit
interval) the gate does not carry.

**B2 refinement (2026-07-04, lean HEAD `84d6d24`):** the mismatch is 5-vs-4,
not 4-vs-4 — Lean Freshness [1.0] proves **five** negative theorems, because
`Time.le` is kept opaque (no order axioms) so the two `TemporallyCoherent`
failure directions are structurally distinct: `incoherent_not_fresh`
(`expires ≤ issued`) and `not_precedes_not_fresh` (`¬ (issued ≤ expires)`).
AG's `incoherent_interval` subcase folds both. Any future subcase→kind split
should decide explicitly whether the two directions stay folded (they collapse
in a total order, which AG's monotonic readings satisfy) — fold-by-argument,
not fold-by-oversight. A future evidence-driven slice may (a) enrich
the window model to produce the other subcases, and/or (b) split the single
refusal kind into four typed kinds IF a consumer needs to route differently
(expired→renewal, not_yet_valid→wait/retry, divergence_excessive→clock/witness
repair, incoherent_interval→producer bug). Until a consumer needs it, this is an
**alignment gap, not an implementation blocker**. Gap stub:
`.governor/backlog/freshness-granularity.json`.
