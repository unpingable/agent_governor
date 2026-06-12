# Constellation Zoning — Deferred Organs and One-Way Doors

**Status: signpost / zoning record. PROVISIONAL. Not doctrine, not a roadmap,
not authorization to build.** Filed 2026-06-11.

This is the companion to `docs/agent-governor-meta-plan.md`. The meta-plan names
the planes that *already exist* and the directional kernel that binds them. This
document names the organs that *do not exist yet*, marks which design doors are
one-way, and records the promotion rule that governs when a deferred organ earns
construction. It is filed at Agent Governor because AG is the first major star in
the constellation and the convening surface — **not** because AG owns the seams
described here. Ownership is marked per organ.

---

## Provenance caveat — read first

This document distills a long design conversation between the operator, Claude
Fable (web), and ChatGPT. Two of those three are language models — but they are
the operator's, months deep in this ecosystem, the papers, and the Lean kernel,
so this is **operator-shaped synthesis that converged with where the design was
already going**, not random model drift. It is still *relay*: across several
rounds the two models built on each other around a shared aesthetic, and by the
constellation's own doctrine *convergence from a shared upstream is one
observation wearing three hats.*

So read "relay, not corroboration" as **not independently ratified yet** — not as
*probably noise*. Epistemology has knobs; this one is set to "real, model-
mediated, unverified." Consequences:

- Everything here is **reference and zoning**, not verified design. None of it
  has been checked against AG's actual code. One concrete dissent is already on
  record and unresolved: the provenance-maximalist instinct (individuate
  everything, witness everything) had no *cost*-advocate at the table — the
  UTXO-everything position needs someone to be unpleasant about fragmentation and
  receipt bloat at volume before it's treated as settled.
- **No section is binding.** Promotion of any organ or rule to ratified doctrine
  requires (a) a forcing case per `~/.claude/CLAUDE.md` § YAGNI scope, and
  (b) an *independent, non-LLM-relay* review pass (operator, or `codex-exec`
  framed to refute). This is a promotion gate, not a verdict on quality.
- The conversation already ran one internal adversarial pass (Fable refuting
  ChatGPT; the relay warning is Fable's). Necessary but not sufficient — two hats
  critiquing the third, still inside the shared aesthetic.

A note on direction. The standing design bias here is **fail-closed**, which has
historically pushed the work *over*-conservative. The zoning below is permission
to *recognize* surfaces early — not a moratorium. Releasing that brake a little
is part of the point.

The material is kept because forgetting it would create retrofit cost on
architectural surfaces (witness grammar, standing semantics, capacity custody,
schema evolution) where that cost rises with usage spread. Naming early is cheap;
the zoning is the cheap-now, brutal-later category.

## What this is / what it is not

**Is:** a map of deferred organs with one-way-door markings, per-seam ownership,
and refusal-driven promotion rules. A handle for review.

**Is not:**

- Not authorization to build any organ named here.
- Not a ratification of any vocabulary as a typed code-level primitive.
- Not a cross-repo doctrine ruling. AG cannot ratify NQ's witness grammar, the
  standing repo's lapse model, or the linear-accountant repo's internal states.
  Those repos own those seams; this file records the scouting so it is findable.
- Not a replacement for the kernel docs it composes with
  (`directional-invariants.md`, `agent-governor-meta-plan.md`,
  `endgame-synthesis-2026-06-10.md`). Those carry the load.

---

## Operating disciplines

### 1. Zoning, not construction

The valuable output of scouting is *constraints on what can be built where*, not
buildings. The session that produced this file produced zoning artifacts, not
features: `denomination = 1`, refuse-during-freeze, refunds-as-new-deposits,
terminal-unit / open-exercise, no-holds-without-a-forcing-case, fiat-marked-as-
fiat. None are features. All are deed restrictions written down while they still
cost nothing.

> Scale is a **test frame**, not a build target. You do not build the retraction
> transport; you verify the current design does not make one impossible. That is
> load-bearing pessimism, not premature engineering.

### 2. The grain of refusal governs the constellation

This is the meta-rule for the whole map, lifted from the witness-typing thread
and generalized:

> **An organ earns construction when, and only when, a real refusal cannot be
> expressed without it — not when the architecture diagram looks asymmetric.**

"What's missing?" is infinitely productive for a custody system; there is always
another seam. The grain-of-refusal rule is the stop condition. It applies
recursively: it governs whether to mint a new *witness kind* (see §Witness
competence) exactly as it governs whether to build a new *component*.

Corollary — over-splitting is the same sin as over-bundling, sign flipped:

> Over-bundling erases refusals. Over-splitting manufactures unlicensed
> structure. Both import error; the grain of refusal is the only honest stop.

### 3. Allowlist for authority, blocklist for detection

The list-polarity rule for every boundary in the constellation. One question
decides it:

> **Can the *good* set be enumerated without strangling the thing it guards?**

- **Yes** (small, ratified, slowly-changing, extension-by-ceremony) → **allowlist**:
  admit iff licensed. Admitting only known-good is checkable and complete; the
  novel value lands in a typed refusal, not in admission.
- **No** (the good set is open-ended/innovative; only the *bad* is partially
  enumerable) → **blocklist**: accepted as inherently leaky, reactive, always one
  mole behind. *Nested blocklists don't repair this — every leaf is still
  default-allow, the holes live at the seams, and a novel value sails past all
  levels. Blocklist depth is whack-a-mole with more lanes.*

The zoning rule that falls out, one line:

> **Detectors over open spaces may blocklist, because they emit testimony; gates
> over authority must allowlist, because they emit consequences.**

The asymmetry is the whole argument: a blocklist *miss* in the observation plane
means a pattern went unflagged (recoverable, evidence-shaped); a blocklist miss in
the authority plane means an **unlicensed exercise occurred** (consequence, not
evidence). Different failure classes → different list polarity.

So the constellation's **authority plane is allowlist wall-to-wall** — admissibility
("admit iff licensed"), RKL's *unmodeled-is-never-admitted*, spends naming their
input units, bridges discharging enumerated objections, ratified schema versions,
capability grants, egress domains, the `origin_mode` operational fence (§Evidence
classes). Witness competence fits too: the "may attest" column is the allowlist;
"may not attest" is *documentation, not the mechanism*. **Blocklists live only in the
observation/advisory plane** (label/drift/spam/noise heuristics over open
ecosystems) — where the good set is unenumerable by design *and the output is
evidence, not admission*.

Review smell (trips the clipboard goblin):

> **A blocklist guarding an authority transition is the alarm.** It usually means
> the boundary is drawn wrong, not that the polarity is — someone declared the good
> set unenumerable at a boundary where unenumerable good sets shouldn't exist.

Composes with grain-of-refusal: a value earns a slot in the allowlist when there's a
refusal it can't express without it; the allowlist stays small *because* it's
closed-world, and widening it is a ratified event (never an emergent default).

### One-way doors vs two-way doors

The single most important zoning distinction. A two-way door can be revised later
at bounded cost. A one-way door destroys information you can never recover.

| Decision                                   | Door     | Why                                                                 |
| ------------------------------------------ | -------- | ------------------------------------------------------------------- |
| Whether Linear Accountant gets a quarantine state | two-way | additive; can be introduced when retroactive-invalidity bites       |
| Units individuated vs. pooled (fungible)   | **one-way** | a fungible pool destroys deposit provenance permanently at deposit  |
| Refund as new-deposit vs. un-spend         | **one-way** | un-spend rewrites append-only custody; conservation becomes unauditable |
| `spent_outcome_unknown` as a first-class state | **one-way** | retrofitting it later means every prior in-doubt spend already lied |
| Embedding host-local timestamps vs. referencing a clock basis | **one-way** | once receipts embed unattested time, every gap field is retroactively numerology |
| Single append path to the evidence ledger  | **one-way** | a second write route makes every later coverage claim hole-bearing  |
| Whether fiat is marked as fiat             | **one-way** | laundered fiat cannot be un-laundered after downstream relies on it |

Zoning is the discipline of writing down which doors are which while it still
costs nothing.

---

## Deferred organs

Fable's lifecycle scan (claim born → routed → converted → exercised → retracted →
archived) surfaced organs that are conspicuously absent or thin. **None is a
build item.** Each is listed with its owner, one-way-door status, current partial
coverage, and the forcing case that would license construction.

Per grain-of-refusal: **retraction transport**, the **verdict/adjudication seam**,
and now **Notary** (the log-continuity spine) are the three where a real refusal is
*already* inexpressible today. Notary has since **graduated** — its forcing case is
found and it is becoming its own project (see §Notary below). The rest wait for their
forcing cases.

| Organ | Owner (candidate) | Forcing case to build | One-way risk | Partial coverage today |
| ----- | ----------------- | --------------------- | ------------ | ---------------------- |
| **Temporal authority / time plane** | constellation (NQ-adjacent) | a cross-host gap bound that must be *enforceable*, not advisory | high — embedded timestamps | none; each component is its own clock folklore |
| **Retraction transport** | nightshift + continuity | a relied-upon claim that lapses/revokes and must reach everyone relying on it | high — reliance index | nightshift routes assertions, not retractions; no reliance index |
| **Verdict / adjudication seam** | (unowned — mark the boundary) | a verdict consumer that renders judgment on receipts and must itself be custodied | medium | meta-plan says "verdict = downstream"; downstream is located nowhere |
| **Evidence death rites / retention** | continuity + evidence locker | the first coverage claim that spans a window someone compacted | high — informal pruning | `docs/HISTORY_BOUNDARY.md`; no tombstones, no standing-to-delete |
| **Restore-from-backup epochs** | continuity (cross-cutting) | a registry restore that time-travels an authority's ledger | high — silent rewind | none; no story for "the world rewound" |
| **Schema / interface evolution** | cross-cutting (every `_v1`) | a `v1` receipt read by a `v3` consumer that silent-defaults a missing field | high — historical evidence base | `docs/VERSIONING.md`, `specs/gaps/CROSS_DOMAIN_SCHEMA_GAP.md` |
| **Fleet control plane** | (deferred; deed-restricted) | more than one gate-bearing system needing coordinated config | high — super-authority | **already zoned** — see `endgame-synthesis` genesis-class rule |
| **Notary / log-continuity spine** | new project (locker-adjacent, NOT NQ) | **FOUND** — "no error logged" can't distinguish sealed-silence / gap / rotation / index-fail / parser-loss / laundering | high — ingestion-as-admission | none; logs ungoverned. **Graduated → §Notary** |

### Notes per organ

**Temporal authority.** Everything in three rounds of conversation leans on
clock basis, model age, observation windows, gap bounds, expiry, coverage
intervals — and none of it is witnessed by a dedicated competence. A time plane
need not be NTP-grandiose: one component whose sole competence is attesting clock
basis and interval claims, that everyone else's receipts *reference* instead of
embedding host-local timestamps. Without it, every `acceptable_gap` and
`model_age` field is a number wearing a time costume.

**Retraction transport (refusal-already-inexpressible).** Lapse, revocation,
taint, disbarment, freeze — the conversation generated a stream of "this stopped
being true" facts. Negative news has different transport semantics than positive
claims: different urgency, different failure cost (a lost assertion is missed
work; a lost *retraction* is unauthorized exercise), different fan-out (everyone
*currently relying* — which requires a reliance index nobody keeps). The
CRL-vs-OCSP graveyard is the cautionary tale: revocation treated as an
afterthought of the assertion system, forever. The bounded-revocation-lag
assumptions that Standing and Linear Accountant lean on **have no mechanism
underneath them today.**

**Verdict / adjudication seam (refusal-already-inexpressible).** "Verdict =
downstream, not witness-owned" has been doctrine since the first round. But
*downstream where?* Witnesses attest, gates refuse, ledgers conserve — then some
layer consumes receipts and renders judgments (acceptable gap, sufficient
coverage, taint disposition, thaw approval). If that layer is uncustodied, the
apparatus drains into an ungoverned policy engine: immaculate evidence
terminating in an unaudited judge. **AG is enforcement, not adjudication** — the
gate that acts on a verdict is not the court that produced it, and collapsing
them is an authority-separation violation by AG's own Wicket logic. Resolution is
binary and either answer is fine *if marked*: (a) adjudication is deliberately
out of scope, and the boundary is a labeled seam — "verdicts exit the custody
domain here"; or (b) a component whose receipts are judgments (policy version
applied, inputs consumed, verdict rendered, by what standing). The unmarked third
option is the rot.

**Evidence death rites.** Deletion is the most dangerous operation in a custody
system and currently has no type. Informal pruning of an evidence locker is the
most corrosive silent conversion available, because it retroactively converts
*absence of evidence* into *evidence of absence*. Wants: retention policy,
standing-to-delete, tombstones attesting what was removed, by whom, under what
authority.

**Restore-from-backup.** A registry restored from a three-day-old snapshot does
not create one open-world lapse — it time-travels an entire authority's ledger,
invalidating coverage claims, absence testimony, and model-age fields across
every component that observed it, simultaneously. The honest design: restoration
as a **typed fiat event** — epoch increment, blast-radius declaration, every
dependent coverage claim marked discontinuous. DR is where governance systems go
to lie.

**Schema evolution.** Everything is `_v1`, which means `_v2` is coming, and a
`v1` receipt read by a `v3` consumer is a conversion like any other — except it
happens to the historical evidence base itself. AG's constitutional rule covers
gate-bearing code; **gate-bearing formats are the same threat with worse
visibility.** See §Versioned interfaces.

**Fleet control plane — already zoned, do not re-derive.** The reflex to reach
for orchestration ("helm for this") and the flinch that follows are both correct:
a control plane that can push config to every gate at once is a super-authority,
the exact concentration Wicket exists to forbid. This is *already captured* as
the genesis-class self-amendment rule in `endgame-synthesis-2026-06-10.md`. The
one zoning sentence worth restating: **config push is a conversion** (standing,
receipts, refusals) and **the control plane never shares a failure domain with
the evidence plane.** Until a forcing case arrives, the principled answer is an
operator-run playbook (Ansible/Nornir) — that is operator-attested fiat in a
tasteful font, which beats an automated control plane wearing a governance
costume. Observation of the fleet (a Phosphor cockpit) can centralize early; the
*write* path cannot.

---

## Component zoning notes

These sharpen or extend existing kernel doctrine. Each is owned by another repo;
AG records the durable cuts so cross-fence work can cite one place.

### Witness competence (owner: NQ)

The load-bearing reframe: **witnesses are typed by evidentiary competence, not by
topical domain.** "security-witness" is a category error — a convenience bundle.
Most security claims are composites (identity observed + at time/order T + under
mode M + with/without human presence + no forbidden conversion in window W);
calling that one witness kind is custody soup with a badge.

```
domain     = what part of the estate was observed   (a scope)
competence = what kind of claim the observer may attest
bridge     = how atomic attestations compose into usable claims
verdict    = downstream, NOT witness-owned
```

Candidate atomic competence table (each row: may attest / may **not** attest):

| Witness kind     | May attest                          | May NOT attest          |
| ---------------- | ----------------------------------- | ----------------------- |
| temporal-order   | ordering, clock basis, interval     | authorization           |
| absence-in-window| no observed event in window W       | global nonexistence     |
| staleness        | age of consumed model/data          | correctness             |
| presence         | actor/process observably present    | intent / attention      |
| capacity-at-commit| resource state at commit           | permission              |
| degradation      | operating mode/context at decision  | safety                  |
| divergence       | agreement *shape* of N attestations | independence of the N   |
| termination      | completed/halted vs. went silent    | success                 |
| identity-binding | a credential/identity was bound     | the actor's intent      |

Four sharp cuts the table encodes (each is a refusal the bundle would erase):

1. **Attention is not testimony.** You cannot witness attention — only proxies
   (challenge issued and answered within interval I; input cadence; response
   carried novel content, not a button press). An "attention-witness" is the next
   little bastard about to grow legs; the honest version is
   *challenge-response-witness*. Attention is a verdict, not a testimony.
2. **Operator-attestation is claim-plane, not witness-plane.** Self-report is a
   *signed* artifact, not a *witnessed* one. It enters as a claim-kind that an
   independent witness can *promote* (presence corroborates it, temporal-order
   orders it); it never enters the evidence plane as testimony about itself. "A
   party cannot witness its own act" is the refusal being preserved.
3. **Divergence attests shape, not independence.** A divergence-witness reporting
   "three independent observers" is one observation wearing a topology-expert hat.
   It may attest that N attestations differ/match on fields F; independence is a
   provenance claim established upstream, or it stays an unlicensed assumption,
   marked as such.
4. **Absence needs a coverage receipt.** "No event in W" is worthless without
   "and I was demonstrably observing W with coverage C." A dead watcher that is
   also its own liveness authority manufactures immaculate silence — silent
   failure laundered into positive evidence of silence. The watcher's liveness is
   attested on a *separate plane*, never self-claimed inline.

Two structural rules:

- **Type modularity ≠ deployment modularity.** One process may emit temporal,
  presence, and termination attestations. Co-location is fine; co-*mingling* is
  the crime — they must be separately typed, separately refusable, separately
  bridged. **Exception (deployment separation becomes load-bearing):** any pair
  where one competence exists to check the other's failure mode must not share a
  host — absence-witness ↔ its coverage receipt; divergence ↔ its independence
  evidence; operator-claim ↔ the presence/interaction witnesses that corroborate
  it. Don't put both keys in the same drawer.
- **Atoms in the type system, molecules in the API.** Opaque composites are the
  enemy; *decomposable* composites are ergonomics. A named, versioned molecule
  with a fixed bridge recipe that decomposes on demand
  (`security_posture_v1 = identity_binding + temporal_order + absence_in_window(W)
  + degraded_mode`, bridged thus) is fine. The rule: every molecule must compile
  down to atoms plus bridges with nothing left over.

Minting rule (grain of refusal applied to the ontology): a new witness kind is
admissible only when there exists a real refusal the existing grain cannot
express without overclaiming or collapsing distinct failures. The eight/nine-row
table is probably close to the right grain already; production refusals drive
splits, not architectural symmetry.

### Standing as a living relation (owner: `~/git/standing`)

This sharpens directional-invariant 1 (*observation may raise standing, may not
satisfy it*) with genuinely new structure. The correction:

> **Standing is not witnessed directly. Standing is reconstructed from witnessed
> observations of records, identity, time, and freshness.** "standing-witness"
> should be forbidden as an atom.

So `standing_observation` is a **molecule**:

```
standing_observation_v1 =
  registry_observation + identity_binding + temporal_order
  + staleness/model_age + authority_scope
```

and its receipt admits exactly what it saw ("grant G appeared valid in authority
A's records, as observed by W at T, model age Δ, under coverage C") — never the
authority-shaped prose "P has standing."

**Lapse is the monster.** Expiry is self-evident (temporal-witness handles it).
Revocation is a positive, witnessable event. But **lapse** — standing going void
because a *precondition* decayed (sponsor departed, parent workload retired,
granting authority itself lost standing) — has no event at the boundary where
the standing is consumed. Nothing fires; the grant silently converts valid →
void. This is `NoSilentConversion` in its purest form. The honest receipt state
is not "valid" but `standing_observed_but_lapse_unbounded`, which names the exact
rot. The only countermeasure is absence-witnesses on the declared preconditions —
which drags in the coverage-receipt apparatus — and the guard can only ever bound
lapse *over the declared set*:

```
lapse_bounded_over: [P1, P2, P3]
precondition_basis: declared_by_authority   # fiat-adjacent; mark it
precondition_completeness: declared_not_witnessed
open_world_residual: unbounded
```

Promoting a coverage claim into a completeness claim is the next blob.

**Standing-before-spendability must be bounded, not merely ordered.** The
exercise-time receipt wants *two clocks and a clock basis*, or the gap math is
decoration:

```
standing_observed_at = T1 ; model_age = Δ1
capacity_committed_at = T2 ; model_age = Δ2
exercise_at = T3
gap(T1,T2,T3) visible
clock_basis = ntp_bounded(±x)  | unbounded → gap_check: advisory
```

Witnesses expose the murder hallway; *policy* (downstream) decides the acceptable
gap. The demo-shaped refusal: `refuse spend: standing_before_spendability_not_
bounded` because clock_basis unbounded / chain was grant-time-only / lapse
coverage missing / class standing exists but instance membership unproven.

> **Refined at build time (2026-06-12).** The sketch above puts the gap on a
> wall clock with an NTP bound (`ntp_bounded(±x)`, unbounded → advisory). The
> shipped gate (`standing_spendability.py`) narrowed to the *sound* case: the gap
> is computed over compatible **monotonic** clock witnesses (`gap_basis.kind ==
> "monotonic"`, a named `source` + `epoch`), because wall clocks step backward
> under NTP correction and a gap across a step is garbage with an ISO 8601 smile.
> Wall time becomes a *different object* (`WallWitness`, display-only or a
> freshness basis), never the gap basis. *A gap is a difference between compatible
> clock witnesses, not numbers.* The wall-clock freshness model sketched here
> (three-valued over ±x bounds) is the spec'd follow-on
> (`working/clock-witness-spec.md`), not the gap predicate.

Three more cuts:

- **Derivative standing needs product labels.** `exercise_time_chain_walk`
  (each hop checked at exercise, expensive, fresher, stronger) and
  `grant_time_chain_assumption` (checked at grant, bounded-propagation assumed,
  cheaper, weaker) are *different evidentiary products*. The receipt must say
  which one ran. Each hop is a typed conversion wanting a bridge receipt, not
  transitive trust.
- **Class standing ≠ instance membership.** Two refusal surfaces that must not
  bundle: *the standing is void* vs. *the standing is fine but this instance's
  membership claim is unproven* (image digest, launch provenance). Collapse them
  and a lapsed grant is indistinguishable from an impostor.
- **Disbarment against ephemeral actors is advisory unless continuity is
  modeled.** Pseudonymous re-entry is free (`foo-2` applies with a new mustache).
  Either Standing tracks actor continuity across identities (hard, itself a
  provenance claim) or disbarment is honestly documented as advisory. Pretending
  it is enforced is the worst option and the industry default.

**Root standing is fiat.** It does not bottom out in evidence; it bottoms out in
a root grant that is fiat. The system is *more* trustworthy if that root carries
a receipt reading `basis: fiat` in tasteful font than if it is laundered through
self-referential ceremony to look witnessed. AG already has the type
(`FiatAdmissibility`). Fiat is admissible when declared and marked, corrosive
when costumed.

**The lease trap.** Holding standing constant for the exercise duration — a
standing lease — does not close the TOCTOU gap. A lease is itself a
standing-shaped object with its own lapse surface, staleness, and revocation lag;
it re-imports the whole problem with a shorter Δ and one more receipt layer.
*A lease is not a proof; it is a priced assumption with a timer.* Bounding-and-
pricing the gap is the floor, and the floor is enough.

### Linear Accountant — internal MVP zoning (owner: `~/git/linearaccountant`)

The packet/integration boundary is already captured in
`working/linear-accountant-handoff.md` (AG requests capacity, never mints). These
are the *internal* one-way-door constraints for the accountant itself, recorded
here as zoning because AG participated in deriving them.

The thing that makes it an *accountant* rather than a *counter*: a balance
destroys the distinctions the system exists to preserve. Linear logic gives you
individuals with lineage, not a quantity.

> **Fungibility is a silent unifier.** If deposits blend into one pool, no
> receipt can object that capacity deposited under standing A funded an action in
> service of intent B — provenance died at deposit. That also kills the refusal
> "standing A's capacity is exhausted." Default to individuated (UTXO-shaped)
> units carrying deposit provenance; spends name their inputs. Cheap fungibility,
> if ever wanted, is an *explicit minting bridge* that drops provenance with a
> receipt admitting it. Laundering as a typed, consensual operation.

MVP one-way-door constraints (boring in the right places):

```
denomination = 1 only          # no split/merge/change-making (a future subsystem)
explicit_input_only            # auto-selectors (earliest-expiry/FIFO) are named
                               #   policy, referenced in the spend receipt — not
                               #   a default; auto-selection re-blurs provenance
no holds / no reservations     # a hold is a lease → re-imports standing's lapse
no queues / no queue-replay    # a freeze queue is a shadow ledger; refuse-during-
                               #   freeze is cleaner; thaw must re-observe, never
                               #   replay frozen-era intents against thaw reality
refunds = new deposits         # never un-spend (a time machine that breaks
                               #   append-only custody). A refund is a new deposit
                               #   whose provenance points at the failed exercise,
                               #   minted by a standing-bearing compensation
                               #   authority — failures have no standing
spent_outcome_unknown          # first-class terminal UNIT state (termination
                               #   witness went silent); do not optimistically
                               #   refund or blindly retry
unit finality ≠ exercise       # the unit's state machine halts at spend; the
  knowability                  #   exercise's evidence file stays open to late
                               #   termination testimony
expiry is a terminal EVENT     # live → expired emits a receipt (clock_basis);
                               #   silent expiry is lapse with an accounting visor
quarantine is admitted         # retroactive invalidity (deposit under standing
                               #   later found lapsed-at-deposit) needs a bucket;
                               #   taint ANNOTATES, never reverses (no time
                               #   machines); clawback is a standing-gated
                               #   destructive action, not an accounting op
single append path             # reconciliation is an absence-witness on a
                               #   SEPARATE plane ("no unit in an unexplained
                               #   state, window W, coverage C"). If side doors
                               #   exist (manual SQL, migration, admin fix), the
                               #   coverage field is fiat and must say so
```

The conservation invariant is the real audit object — every unit is exactly one
of `{live, spent(ref), spent_outcome_unknown(ref), expired(ref),
quarantined(ref), destroyed(clawback_ref), compensated_by(unit_ref)}`, and the
partition sums to deposits. The ledger keeps the books; it **cannot** be the
final witness that they balance (gate-bearing code does not testify on its own
behalf).

Anti-goblin rule, taped to the monitor:

> **Any field that implies split, merge, selection, lease, or side-channel
> mutation is not an innocent field. It is a future subsystem.**

#### LA is metabolic, not juridical (zoning glyph, 2026-06-12)

The reframe that recontextualizes the whole organ. Standing / Wicket / WLP / NQ
are **courthouse** — they adjudicate, they ask *is this licensed*, they fail by
**refusal**. Linear Accountant alone is **metabolic** — it asks *is there fuel*,
a question about the world rather than about permission, and it fails by
**exhaustion**. It does not care whether the wolf has a badge; it cares whether
there is enough blood sugar to run. One organ in the constellation answers to the
world instead of to a sovereign — keep it that way; resist the gravitational pull
(the courthouse-dopamine of crisp green refusals) to juridify spend itself. The
seam you already built is correct: standing *gates* spend; standing never *is*
spend.

| Organ | Question | Fails by |
| ----- | -------- | -------- |
| Standing | Who may ask? | refusal |
| Wicket | What may cross? | refusal |
| WLP / custody | What may be believed downstream? | refusal |
| NQ | What testimony exists? | (observation gap) |
| **Linear Accountant** | **What can be spent before reality says no?** | **exhaustion** |

> **Authorization decides whether spend may *begin*. Linear accounting decides
> whether spend can *continue*.** LA is metabolic, not juridical: permission
> gates admission to spend; accounting governs exhaustion, conservation, freeze,
> thaw, and scar.

**Ledger-kind is a typed field, not a convention.** Multiple ledgers are fine;
the hazard is a ledger of one kind silently read as another (same `consume()`
signature, same receipt shape, opposite ontology). Every ledger declares its
kind — `juridical` (depletes a grant, fails by refusal) or `metabolic` (depletes
worldly capacity, fails by exhaustion). The non-substitution rule is directional:

```
juridical units MAY gate a metabolic consumption (standing-before-spendability)
juridical units may NOT satisfy metabolic capacity   (license is not fuel)
metabolic units may NOT satisfy juridical standing   (fuel is not license)
metabolic units may NOT imply juridical standing
```

Kinds compose only at declared bridges; they never cross-fund, cross-satisfy, or
collapse failure meanings. (License-as-fuel = an authorized spend against an empty
battery; fuel-as-license = "we have capacity therefore it's allowed," every bridge
exploit waving from the swamp.)

**Dual failure must stay dual (the regression magnet — put a skull on it).** The
keeper row, because every future simplifier will want to flatten it:

| Standing | Capacity | Correct result |
| -------- | -------- | -------------- |
| present | available | proceed |
| present | empty | **exhausted**, NOT refused |
| missing | available | **refused**, NOT exhausted |
| missing | empty | **refused + exhausted**, NON-collapsed |

> **At failure time, preserve ontology. A juridical defect and a metabolic defect
> may coexist; neither explains, replaces, or repairs the other.**

Flattening `missing ∧ empty` to a single `Denied` is the lie the ledger-kind field
exists to prevent: the two defects have *different remediations* (refusal →
establish standing; exhaustion → replenish/thaw/wait/repair the capacity witness),
so a collapsed verdict makes the operator fix one axis and falsely believe the
system is healthy — "the red light went away because we unplugged the dashboard."
This is Paper 27 (obligation-unsound reconciliation) wearing a hardhat: "battery
policy misconfigured" as a Jira title is the bureaucracy eating the organism in
real time. The non-collapse rule is the typed-refusal-preservation discipline
applied to the *failure channel*.

**Domain instantiations** (the generalization runs *backwards* — these domains
already run feral, unreceipted linear accountants; the upgrade path is the same
everywhere: individuate, receipt, conserve): SRE error budgets, congestion
windows / token buckets, energy and duty-cycle ledgers, route/latency capacity.
**Physical variants inherit estimator uncertainty**: a battery deposit is
*capacity testimony* from an estimator (charge per model `M`, sensor set `S`,
error band `ε`, at `t`), not ground truth, so conservation becomes "the sum stays
inside admitted tolerance," not "the sum is exact." (Paper bait for the autumn:
*Everything Is a Token Bucket and Every Token Bucket Is Lying.*)

**W2 conformance obligation (named, NOT built today).** The four-row table is a
conformance obligation, not a comment — per the golden-corpus discipline it wants
four frozen `input → verdict` entries (proceed / exhausted-not-refused /
refused-not-exhausted / **dual-uncollapsed**), with the fourth as a **negative
pinning test**: a dual-failure verdict that flattens to a single `Denied` MUST
break the contract. That is the row that rots first under refactoring pressure
(flattening is always the locally convenient move), so it most needs a standing
test guard. Owner: `~/git/linearaccountant` (ledger-kind is LA-internal capacity
semantics; AG records the zoning, does not ratify it). Composes with
`working/candidate-la-unit-class-fence.md` (Wall 2) — both are LA-internal
one-way-door constraints surfaced from AG-side derivation.

**The time axis is three kinds, not one "time budget" (the glyph earning rent).**
"Time pressure" hides three distinct failures that do NOT deplete the same way;
reconciling them into one budget is the same type error, one ontology over:

| "time budget" | kind | mechanism | failure |
| ------------- | ---- | --------- | ------- |
| throughput (can I keep up?) | **metabolic** | capacity ledger (LA) | exhausted / lagging |
| freshness (is it still current?) | **temporal** | attested clock + lapse guard | stale / lapsed |
| authority validity (is the grant still live?) | **juridical-temporal** | grant validity / standing lapse | refused / void |

> **Capacity runs out. Freshness lapses. Authority expires. Do not reconcile them
> into one "time budget."**

The tell: *if running out is about **your** resources, it's metabolic and gets a
ledger; if running out is about **the world moving on without you**, it's temporal
and gets a witness.* Time pressure is usually the second. So **do not give
deadlines a wallet** — a deadline is a property of the *claim*, not the spender
(true whether the spender is idle or melting), so it is `compare(attested_clock,
bound)`, never `consume(time_budget)`. Modeling freshness as a depletable budget
invites license-as-fuel with a clock painted on ("I have deadline-budget left,
therefore still fresh"). Freshness is the standing-lapse shape — which AG already
built as the standing-spendability gate (`standing_spendability.py`: two clocks,
mandatory `clock_basis`, lapse guard), NOT a ledger. Remediations differ and that
is the whole point: throughput exhaustion → add capacity / throttle / shard / mark
coverage gap; freshness lapse → reject stale / require new witness / widen policy
only if ratified; authority lapse → renew/regrant. Owner per kind: LA (metabolic),
the deferred temporal-authority organ (freshness), `~/git/standing` (authority).

Worked case (owner: **Notary**, not AG — recorded here because it forced the
distinction): a notary may spend a metabolic throughput budget, but freshness is
judged by an attested clock. If throughput exhaustion prevents sealing within the
freshness window, that is **dual failure** — `exhausted` + `stale/coverage_gap`,
not one tidy denial. And the non-negotiable rider for any metered watcher: budget
exhaustion emits a **coverage-gap receipt**, never a silently-degraded seal — a
watcher that drops to sampling because it got tired is forging evidence of its own
silence (the absence-witness coverage problem, one layer down). Notary's to file;
AG only records the cross-fence note.

#### Ledger templates: two-level typing, and `exhaustion`/`refusal` is the public name (2026-06-12)

LA needs default ledger templates, but boring and typed — "budget" must not become
a universal solvent (that way lies Jira with math). The fix is **two-level typing,
top question first**: not "what flavor of ledger?" but *when this fails, did the
system run **out**, or did it **refuse**?*

```
failure_class: exhaustion | refusal      # the FIRST question; the sacred discriminator
  kind (under exhaustion): capacity · quota · escrow · retry
  kind (under refusal):    blast_radius · egress · attention · suppression
```

> **A ledger must declare whether failure means "out of resource" or "outside
> authority" before it declares what it counts.**

The non-obvious calls the relay surfaced: **`blast_radius` is refusal, not fuel** —
host #11 isn't starvation, it's "the requested effect exits the authorized
envelope." **`attention` is refusal, not a battery** — "the system refuses to
externalize more interrupt cost onto the operator under this scope" (governance, not
physiology; do not optimize the human until morale improves). This keeps the sacred
four-row table un-collapsed: if `blast_radius` and `capacity` were sibling `kind`
values with no `failure_class` over them, "empty/exceeded" drifts back into one
generic failure family and the goblins get lanyards.

**Public-name discipline (operator-flagged).** The internal doctrine names are
`metabolic`/`juridical` (this glyph). The **user-facing schema is
`exhaustion`/`refusal`** — nobody types `failure_class: metabolic`. Biology stays in
the doctrine file; ops terminology faces the operator. (A good ops tool should not
wake up covered in seminar.) Same discipline that purged the legalese.

**D0 = `capacity` only** (`failure_class: exhaustion, kind: capacity`), plus `escrow`
*iff* the demo has a real reserve→commit→refund shape. No six-ledger bundle, no
template zoo — that's how clocks become calendars become fiscal policy. The rest is
template-library material (quota / retry / blast_radius / egress / attention /
suppression / evidence-query), each with explicit `failure_class` + `kind` + `unit`
+ `scope` + exhaustion/refusal verdict — filed, not built.

**The NOT-LA fence stays loud** (these are never ledgers): **freshness** (time
validity vs a clock, not spendable fuel — see the clock-witness spec
`working/clock-witness-spec.md`), **standing** (permission, not balance — keep
separable or the four-row table dies), **confidence** (no epistemic arcade tokens —
"confidence budget" is a future atrocity with clean YAML), **evidence quality**
(testimony/admissibility, not currency).

> **LA is bounded spendability *after* permission has survived custody — not
> permission itself.** (Prevents ~80% of future crimes.)

Full template library + minimum ledger/consume-receipt schemas: see
`memory/linearaccountant_repo` and the LA repo (`~/git/linearaccountant`) — owner of
the ledger internals; AG records the zoning, does not ratify it.

### Versioned interfaces are bridges, not folder names (cross-cutting)

A version number is a *signed claim about conversion behavior*, and almost nobody
witnesses it. `api_version: v2` is producer fiat — fine as metadata, useless as
custody.

```
A version is a declaration.
A compatibility test is evidence.
A migration is a conversion.
```

What is actually wanted is a bridge with a recipe, the same three honest moves
every conversion in the constellation gets — **preserve, explicitly drop, or
refuse**:

```
v1_to_v2_bridge:
  input_schema: v1 ; output_schema: v2
  preserved_fields / transformed_fields / dropped_fields / defaulted_fields
  refusal_cases
  contract_test_refs     # consumer-driven contract tests = the witness layer
  migration_receipt_ref  # historical-receipt migration is MASS conversion →
                         #   wants mass receipts, or version drift becomes the
                         #   silent unifier one level up
```

The bad move is silent defaulting (`v1` lacked X; `v2` requires X; consumer
invents `X = "unknown"`; downstream treats unknown as acceptable) — that is the
no-unifier violation operating on the evidence base itself. Stripe's date-based
versioning is the industrial example worth holding up: under the hood it is a
conversion graph — versions as nodes, explicit transformation edges between
adjacent versions, no skipping — run as a product feature.

> **Version everything, trust no version number.** A version label names a node;
> a bridge receipt names the admissible path between nodes.

Applies to receipt schemas, witness contracts, NQ preflight contracts, Standing
grant records, LA unit records, and public APIs alike.

---

## Notary — the log-continuity spine (forcing case found, 2026-06-11 appendix)

The one organ on this page that has **graduated past the grain-of-refusal gate** —
it has a real refusal current kinds cannot express, and the operator's verdict was
"guess we're building notary." Owner: **a new project, not AG** (evidence-locker-
adjacent; explicitly *not* NQ — see below). Recorded here because the constellation
needs to know it exists and what it must never become.

**The cut: alerts are item-shaped; logs are stream-shaped.** An alert is
individually meaningful, individually signable, witnessed at emission, expects a
consumer. A log is bulk, mostly noise, meaningful in aggregate or retrospect.
Shoving logs into NQ as "many tiny alerts" blends two witness moments and two
integrity primitives into one component — the exact bundling this project evicts
everywhere else. So logs are **not an NQ witness kind; they are a new seam.**

**A log line is first-person self-report** — a process narrating its own behavior is
operator-attestation with worse grammar. Signed-is-not-witnessed applies in full.
Logs therefore cannot enter the evidence plane as *observations*; they are *claims*.
Treating ingestion as admission is the unifier quietly erasing the most foundational
distinction. What's needed is a **promotion gate at the locker's edge**: self-reports
arrive *diary-grade*, get typed, get timestamps re-based against a clock basis (log
timestamps are host-local folklore — the temporal-authority hole wearing syslog
clothes), and either get promoted by independent corroboration or stay diary-grade
with that class visible in every downstream receipt. Two evidence classes, explicit
bridges, no blending.

**The integrity primitive flips.** Alerts get *item authenticity*; logs get
*continuity* — hash-chained segments, periodic sealing checkpoints, sequence
accounting. The payoff: **gaps become structurally visible.** A chain break or
sequence hole is detectable absence — the coverage receipt falls out of the
integrity primitive for free instead of being bolted on.

**The load-bearing doctrine line: admission happens at sealing time, not reading
time.** A log line read six months later is a past self-report whose custody was
either established contemporaneously or wasn't. Custody cannot be retrofitted; later
promotion of an unsealed line is laundering — a self-report from the past granted
observation status by present need. So the component is **a continuity notary, not a
log search system.** It holds custody over the *spine*, not the *corpus*.

**The store is fungible; the custody lives in the skeleton.** Elastic / Loki / S3
become untrusted bulk storage with a search engine attached — the role S3 plays in
content-addressed systems. A query result is a *claim by the store* ("these lines
existed, in this order, in segment S"), checkable by re-hashing against the seal.
**The index is never the evidence; the sealed segment is.** Store-side ingest
transformation (grok, field extraction, mapping coercion, silent truncation) makes
the *indexed document* a derived post-seal artifact — verify against the raw segment,
never the parsed representation. Vendor swap stops being a custody event: the spine
doesn't move.

**The automation rule is brutal and necessary:** *anything that acts on logs routes
through promotion first, or the action receipt carries `basis: unwitnessed_self_report`
in a font nobody can miss.* Log-triggered remediation (alert fires → files deleted)
is the weakest evidence class in the stack directly triggering exercises — self-report
converting straight to action, skipping the witness plane. Most ops automation in the
wild fails this clause, which is exactly why incidents so often start with "the
remediation made it worse."

**The forcing-case refusal** (why this one graduated): *"no error logged"* currently
cannot distinguish —

```
covered sealed silence   genuinely nothing happened, and we were watching
missing segment          the stream had a hole
rotated-away evidence    death rites — logs have been living them, badly
index failure            the finding aid lied
parser loss              the transform dropped it
self-report laundering   a diary entry promoted by present need
```

Notary gives that refusal a body: `sealed-silent over declared stream/window`.

**MVP zoning — tiny and mean.** Read append-only stream → segment by size/time →
monotonic sequence numbers → hash each segment → chain to previous → emit seal
receipt → detect rotation/truncation/gaps → checkpoint to the locker → optionally
write the segment to dumb storage. **No parsing. No alerting. No search. No
dashboard.** `promote` (line → verified claim) stays behind glass; that's where the
gremlins live.

Anti-scope-creep label (tape to monitor):

> If it parses meaning, it is not Notary. If it searches, it is not Notary.
> If it alerts, it is not Notary. If it acts, call a priest.

Notary talks to NQ (NQ consumes seal receipts; witnesses host/process state around
the sealer) but is a different organ: **NQ testifies about events; Notary notarizes
continuity.** Two witness moments (alerts at emission, logs at *seal* time), two
integrity primitives. Rotation means logs already ship with ungoverned deletion —
Notary is also the first place the evidence-death-rites problem gets a body.

### `notary-seal-v0` — the build-ready chisel (2026-06-12)

Tiny chisel, not a quarry operation. Notary touches everything, so it can become
"one more infrastructure substrate" and eat the slab. The whole v0 is one line:

> **notary v0 = seal receipt batches and make gaps visible. Nothing more.**

The one doc sentence (the zoning ward):

> **The notary does not decide whether claims are true. It seals what was
> received, in what order, under which evidence class, and emits explicit gaps
> when continuity cannot be maintained.**

```
inputs:   receipt batch · previous seal hash · sequence number · clock reading · locker id
output    seal_receipt: notary_id · sequence · batch_hash · previous_seal_hash ·
(seal):     sealed_at · input_count · evidence_class_counts · coverage_start/end
refusals: sequence_gap · previous_hash_mismatch · clock_unavailable ·
            empty_batch_unless_declared_heartbeat · synthetic_operational_mix ·
            seal_window_expired
```

`synthetic_operational_mix` / `seal_window_expired` are **launch-relevant**: the
notary enforces *simulated/demo evidence may be sealed, but only into a simulated
locker or simulated segment* — defense-in-depth on the synthetic firewall, the
same invariant guarded at the corpus (`operational=false`, the Wall-1 fence) AND
at the seal. The forcing slice that earns v0:

```
demo run emits receipts → notary seals them into a SIMULATED segment →
operational admission refuses to consult the simulated segment →
query can still show the demo chain
```

Three wins: demo artifacts fenced · receipts visibly tamper-evident · the locker
has continuity without pretending demo traffic is operational truth.

Acceptance tests (`notary-seal-v0`): seals batch with previous hash · refuses
previous-hash mismatch · refuses sequence gap · seals simulated batch as simulated
· refuses simulated batch entering operational locker · emits coverage-gap receipt
on missed sequence/window · **+ the loop-pinning negative below**.

**Damp-hallway (do NOT build in v0):** distributed notary, quorum signing, external
timestamping, transparency-log-grade inclusion proofs, key-rotation ceremony,
retention/redaction machinery, Phosphor aggregate receipts, production daemon
lifecycle, Prometheus exporter. They wait.

### nq-witness is the observability surface — and the loop must be declared open

**Critical cross-project rule.** The integration rule is NOT "every tool grows its
own Prometheus exporter" (twelve unofficial belief channels — goblin architecture).
It is **every tool emits testimony to `nq-witness`**:

```
tool-local event/state → nq-witness testimony → NQ store/query/cockpit → optional Prom/export adapters
```

Tools emit claims/testimony; `nq-witness` owns witness shape / competence /
coverage; NQ owns query / cockpit / evidence posture; Prometheus gets *derived
metrics only*, never canonical custody (a raccoon with a Grafana license). Per-tool
emission sets: **notary** → seal_created, seal_refused, sequence_gap,
previous_hash_mismatch, clock_unavailable, evidence_class_mix_refused, coverage_gap;
**verifier** → verdict_issued, invalid_input, stale_fact_denial,
missing_evidence_denial, rule_failure; **agent-governor** → proposal_received,
preflight_refused, verdict_issued, action_admitted, action_refused,
divergence_detected.

**The reflexivity fix (load-bearing — resolve before wiring).** "Every tool emits
to nq-witness" hides a fixpoint: the notary emits witness events, those events are
things someone might seal, and now the observability plane and the custody plane are
each other's inputs. Undeclared, that means *a notary outage stops sealing the
witness stream that would have reported the notary outage* — the watcher-watching-
itself trap, one altitude up (the absence-witness coverage problem, same shape every
time the evidence plane folds on itself). The cut that breaks the loop:

> **Tools emit testimony to nq-witness. nq-witness emissions are operational
> observability, NOT sealed custody. The notary seals receipts, not the witness
> stream about receipts.**

```
receipt spine:   append-only · sealed · legal/custody record · notary operates HERE
witness stream:  operational observability · best-effort / coverage-scoped ·
                 watches components · MAY cite receipts · does NOT ground them
```

nq-witness may say "I observed notary sequence gap at T" — but that observation is
not what makes the spine continuous or discontinuous; the spine's own seal/coverage
receipts do that. The witness stream may *look at* the custody plane; it may not
*become* it by recursion. The loop-pinning negative test for v0:

```
test_notary_witness_events_do_not_count_as_sealed_coverage:
  given  notary emits nq-witness testimony about a seal operation
  assert that testimony is NOT included when computing sealed receipt coverage;
         cannot repair a seal gap; cannot satisfy continuity;
         may cite a seal receipt but cannot replace one.
```

If custody over the witness stream itself is ever genuinely needed (almost
certainly not pre-launch), it is a **declared** second-order seal with its own
coverage statement (`seal_class: second_order_observability; covers: nq-witness
stream; does_not_cover: primary receipt spine`) — never an accident of everything
emitting to everything. Declared fixpoint, marked and bounded; never the silent kind
where A grounds B grounds A and both look solid until they go dark together.

Owner: **Notary** (its own project, `~/git/notary`, empty) for the seal spine;
**NQ** (`~/git/nq-root/nq`) for nq-witness. AG records (and is itself a witness
emitter per the AG set above). Disposition: build after launch, on `notary-seal-v0`'s
forcing slice; the hero clocks (the standing-spendability gate) are **already wired**
(`standing_spendability.py`, 2026-06-12), so Notary blocks nothing — it sits nearby
holding a clipboard, it does not commandeer the forklift.

---

## Transport & state exchange — the one boring pipe

The end-to-end argument (Saltzer et al., 1984) doing classical work: if WLP owns the
custody semantics (idempotency keys, sequence accounting, receipt-of-receipt, dedupe,
freshness), the transport is *allowed* to be garbage. Rabbit's at-least-once and
Redis pub/sub's best-effort are different lies; WLP rides either by assuming the pipe
lies and receipting accordingly.

> **State crosses boundaries as claims, never as shared residence.**
> **The broker may deliver bytes; it may not provide custody.**

The trap hides in the word "exchange." State traveling as *claims* (snapshots with
provenance, model age, sequence position) is WLP over any pipe. State living as a
*shared mutable blob* both parties read and write is a free-standing bridge with a
Redis key for a name — the implicit pool reintroduced one layer up. Cohabitation with
no lease and a suspicious smell from the crawlspace.

```
Allowed:    WLP over Rabbit / Redis streams / files / HTTP / regrettable shell scripts
Forbidden:  shared Redis key as truth
            shared DB table as implicit bridge
            broker offset treated as receipt
            queue ack treated as exercise completion
```

This is the one component permitted to be boring *and* disposable. Finally something
not demanding a constitution, a blood oath, and a small notarized skull.

### Networking patterns — the complete map (2026-06-12 appendix, CANDIDATE)

The cross-host conversation (operator + ChatGPT + Fable, 2026-06-12) closed the
pattern zoo. Full record with stacks, phasings (wlp W-series, identity X-series,
nq-crosstalk N-series), and anti-cathedral lists:
`working/constellation-networking-patterns-2026-06-12.md`. The carved summary:

> **Constellation networking has three primary idioms: verdict RPC, testimony
> flow, and retraction fan-out. Blob pull and subscription tail are degenerate
> testimony forms. Member/foreign is an orthogonal trust axis. Pipes provide
> delivery; signed claims provide evidence; retractions require
> reliance-indexed delivery accounting.**

| Pattern | Shape | Failure concern |
|---|---|---|
| Verdict RPC | ask → typed outcome | don't collapse transport/speaker/doctrine failures |
| Testimony flow | signed append, eventual push | preserve origin, detect gaps |
| Retraction fan-out | urgent, reliance-indexed, delivery-accounted | prevent stale authority from continuing |
| — blob pull | fetch-by-hash | integrity / availability |
| — subscription tail | standing NQ flow | bounded live observation |
| *(axis)* member/foreign | standing-backed vs no-standing | evidence class / egress effect |

Three additions to standing zoning, none of them organs:

- **Keys are standing grants** — no CA, no bearer tokens (possession is not
  standing); component identity = operator-fiat grant over an ed25519 key,
  verified by the standing machinery that already exists. *Transport may secure
  delivery, but only signed envelopes create durable speaker evidence.*
  **Tunnels secured paths; signed envelopes secure claims.**
- **Retraction transport's forcing case moved** — the organ entry above stands
  unchanged, but the moment a standing grant backs a wire key, key revocation
  IS retraction fan-out ("first key compromise," not "someday"). Interim stays
  honest: short-lived grants, bounded-lag revocation on the record.
- **Member/foreign stays orthogonal to transport** — foreign responses (MCP,
  firehoses) enter at the lowest evidence class regardless of pipe; promotion
  is a notary-gate problem. Collapsing the axis into the transport abstraction
  is "zero trust by trusting YAML."

Forcing-case status: near-term, named — labelwatch lives on the VM and the
ssh-tunnel era is ending; the forcing day is the first component leaving the
host. Until then: zoned, not built.

---

## Reflex plane — near-real-time as composition, not a new organ

The wildcard (DDoS mitigation; robotics) that the constellation answered *without
minting an organ* — which is the load-bearing test passing, not the frontier closing.

> **Fast systems don't make fast decisions; they execute slow decisions quickly.**

A 200ms null-route wasn't decided in 200ms — the decision was staged earlier as a
conditional (*if pattern P, action A, within scope S, until expiry T*). All the
expensive custody (standing observation, verdict, capacity commit) happens at *arm
time* on the deliberative plane with the full gauntlet. Runtime is reflex:
pattern-match, exercise, done. The spinal-cord model — the body doesn't consult the
brain about hot stoves, but the reflex is scoped, bounded, and the brain is told
afterward. Adjudication moves to design-time; the runtime path carries no judgment,
only execution of pre-rendered judgment.

```
arm slowly → act quickly → confess promptly → expire automatically → escalate on exhaustion
```

It assembles from parts that already exist:

```
Standing            who may arm the reflex, over what scope
Verdict             which (condition, action) pair is pre-approved
Linear Accountant   reflex budget — capacity is the leash on autonomy; exhaustion halts it
Expiry              each fast-path effect is a lease that auto-reverts unless ratified (default-revert)
Absence / coverage  every exercise must confess on deadline; a missing receipt IS the alarm
Freeze              disarms the reflex plane (mode: disarmed); it does not queue
```

Linearity hands you **bounded blast radius for free** — the reflex literally cannot
run away, because it runs out. Default-revert means the fast path's failure mode is
"stopped doing the thing," not "kept doing it forever because nobody was watching" —
for DDoS specifically, the difference between a hiccup and a self-inflicted outage
(overblocking legit traffic is how mitigation *becomes* the attack). This is the
aerospace **Simplex / runtime-assurance** architecture: an unverified performant
controller wrapped by a small verified safety envelope — you verify the *box*, not
the decisions, and the box was built with full custody at leisure. Toddler with
scissors, but the scissors are foam and the room is padded.

Receipt + refusal shapes (for the file, not a spec):

```
reflex_exercise_v1: reflex_rule_ref, armed_at, arm_receipt_ref, trigger_observed_at,
  action_exercised_at, budget_unit_spent, revert_deadline, confession_deadline,
  actual_confession_at, outcome_ref
refusals: reflex_disarmed | reflex_budget_exhausted | reflex_rule_expired |
  trigger_unpromoted | confession_deadline_missed | revert_deadline_missed
```

No component needed yet — but when the forcing case shows up, the constellation
already speaks the dialect.

---

## The instrument turn

A framing shift worth marking. Most of this page reads doctrine-shaped because the
apparatus is still being zoned. **An instrument doesn't argue — it shows you.** Not
"better policy," not "safer automation," not "AI governance" — but: *here, this claim
was observed; this conversion was attempted; this refusal preserved the seam; this
gap was unbounded; this authority was fiat; this standing was stale; this capacity
was tainted; this version bridge dropped a field.* You stop saying "systems silently
convert claims" and start saying "this one did, at 03:17, and the receipt says the
consumer accepted a stale standing observation with no clock basis and a grant-time
chain assumption mislabeled as exercise-time validation." Once instrument-grade, the
philosophy stops sounding like philosophy and starts sounding like **incident review
with better nouns** — a cockpit that catches a tasteful lie normal tooling would
flatten into green.

> **The apparatus exists so that refusals are expressible and conversions are visible.**

---

## Evidence classes — declared and simulated are not the same "not-observed"

(added 2026-06-11, second appendix)

The launch demo forced a distinction that turns out to be load-bearing well beyond
the demo. **"Not observed from the world" is not one class** — it's at least two,
with *opposite* promotion rules, and bundling them is the grain-of-refusal test
firing.

**Declared** — maintenance windows, moratoria, freeze periods, operator
attestations, planned suppressions. Fiat-shaped, issued by a standing-bearing actor,
and **operative**: it is *supposed* to participate in operational reasoning (alerts
during the window get reclassified; suppressions cite it). The sharp part: a declared
fact can be **future-tense** — nobody can witness Tuesday's maintenance window on
Monday. Declaration is the *only* door through which future-tense facts enter the
system at all, which makes declared first-class and load-bearing, not a degraded form
of witnessed. NQ already has this class.

**Simulated** — demo / test / fixture traffic. Receipt-shaped fiction that must be
**inert**: firewalled from operational reasoning, never promoted, never consulted,
never allowed to reclassify anything real. **The public demo is literally a
simulated-evidence generator** — the first stranger who runs `./demo/refused-spend.sh`
mints receipt-shaped artifacts into the same plane as real attestations unless the
fence exists. This was launch-blocking; **the fence predicate is now built** (see
*Implementation* below).

The grain-of-refusal proof that these are two classes, not one label: there exists a
scenario where you must *admit* one and *refuse* the other. A single "synthetic"
label breaks one of the two rules — either "synthetic never promotes" silently
disables maintenance windows, or "declared is operative" lets a stranger's demo
suppress real alerts. Same superficial shape, inverted consequence rule.

```
evidence_class   basis                  operative?   promotes?            future-tense?
observed         a witness saw it       yes          under standing       no
declared         standing-bearing fiat  yes          yes, under standing  yes (the only door)
derived          computation/aggregate  as a claim   only with an aggregate receipt   n/a
simulated        fixture / demo / test  NO — inert   NEVER                irrelevant
redacted         tombstoned absence     n/a          n/a                  n/a
expired          formerly admissible    no           no                   n/a
```

Firewall predicate (the actual launch fix — small):

```
simulated may demonstrate structure / test machinery / cite simulated
simulated may NOT satisfy operational standing
simulated may NOT affect operational aggregates
simulated may NOT suppress or reclassify operational events
simulated may NOT become spendable capacity
```

Owner: **shared constellation vocabulary, not AG's to ratify alone** (NQ owns the
witness-claim classes; AG owns the fence on its own gate/evidence receipts). The
table above is the abstract zoning view; the implemented reality is below.

**Implementation (2026-06-11).** Grep-before-sketch corrected the design twice:
(1) `evidence_class` is *already taken* — it's the receipt-kernel's blob redaction/
retention class (`PUBLIC`/`SEALED`), so the origin taxonomy must NOT reuse that name;
(2) the constellation *already* has the origin field: `origin_mode` on each receipt's
`evidence_bundle` (so it's already custody-bound via `evidence_hash`), with a closed
vocabulary in `cooked_context_orchestrator.py` — `NQ_ORIGIN_MODES = {observed, drill,
replay, synthetic}` + `AG_INTERNAL = {cli_origin, stub_origin}`. It was stamped and
*rendered* (`why.py`) but **never fenced**. So the build was not a new field — it was
the missing **closed-world admission predicate**: `operational_admission()` admits
**iff `origin_mode ∈ {observed}`** (allowlist, per §3); everything else refuses by
typed reason (`origin_not_operational` for recognized non-observed modes,
`origin_unrecognized` for novel strings, `origin_missing` for absent; malformed type
aborts). The offending mode rides in the result verbatim (a refused `replay` audits
differently from a refused `drill`). Mandatory pinning test ships
(`tests/test_origin_admission_fence.py`): novel string → refusal, no exceptions.
Widening the operational set is a ratified event, never a default. **Remaining for
D0:** wire `operational_admission()` into the operational-promotion call sites (the
predicate exists and is tested; enforcement at the gates is the next slice).

---

## Phosphor aggregates are uncustodied claims

The cockpit is where humans actually form beliefs about the system, and it is
currently the *least* custodied layer. Aggregation is a conversion that launders
provenance by construction: "95% of spends succeeded" is a derived claim nobody
attested, from a query nobody receipted, over an input set nobody bounded. A count
is a claim. A rate is a claim. A trend is a claim. The constellation's careful
atomic testimony funnels into a chart that's pure vibes.

The cheap fix (not launch-blocking unless Phosphor enters the demo's proof path):

```
aggregate_receipt:
  query_hash / query_template_id
  input_set_bound        (receipt range / cursor)
  computed_at
  evidence_coverage
  excluded_classes: [simulated, fixture]   # composes with evidence classes above
  result_hash
```

Then a dashboard number can be challenged back to its constituents. Until then,
dashboard aggregates are marked **derived / unreceipted** and kept off the launch
credibility path.

---

## Build-nothing zoning paragraphs (succession, redaction)

Two more from the sweep that need a sentence in the constitution, not a component:

**Root fiat succession.** In a single-operator lab, root authority is operator fiat
(cf. §Standing — "root standing is fiat"). The honest documented behavior when the
root goes silent: grants decay to their lapse horizons, no new standing is minted,
the constellation winds down to refusal mode rather than silently preserving
authority. The system should not pretend to survive its sovereign — and that should
be the *documented* state, not the *discovered* one.

**Redaction with custody (tombstones).** Append-only does not mean secrets stay
readable forever; the day a credential lands in a sealed log line, "we never delete"
stops being a virtue. Pattern (from transparency logs): tombstone receipts attesting
*something was removed, by whom, under what authority*, preserving the hash chain
around the hole. Distinct from the evidence-death-rites deferred organ (that's
retention policy; this is surgical removal with custody intact). Composes with
§Notary — rotation already deletes log segments ungoverned.

---

## Survey phase: declared done (2026-06-11)

The operator's own filter, applied: *the well doesn't run dry — it just stops being
worth the rope.* Across three days of scouting, new findings now reliably **alias to
one of two dependencies already named** — they either need **Standing** or they need
**the clock** (bounded time). When the gap analysis starts returning the same two
dependencies in new costumes, the survey is over. The land is mapped. The next move
is the **slab the demo sits on** (`working/launch-plan-2026-06-11.md`), not another
organ.

---

## The two gravity centers

The loud pattern across every organ and component: each one secretly bottoms out
in **two** things.

> Refunds need standing. Schemas need standing. Deletion needs standing.
> Clawback needs standing. And *everything* needs an attested clock.

```
gravity center 1: STANDING       (entitlement; the "who may" question)
gravity center 2: BOUNDED TIME   (clock basis, model age, coverage windows)
```

Everything else is principled plumbing between the two. That is worth knowing
before the next component is built, because it tells you where hardening effort
*compounds* (the two centers) and where it is *decoration* (plumbing that assumes
the centers without attesting them). The constellation has two centers of gravity,
not one — and neither is currently a dedicated, witnessed plane: standing lives in
`~/git/standing` but is reconstructed everywhere from stale observation, and
bounded time has no plane at all.

---

## Reserved candidate names (NOT filed)

Following the existing "name early, ratify lazily" pattern (cf. memory
`recovery_topology_candidate`, `amendment_fragment_candidate`), these names are
*reserved* as handles, not filed as gap specs. Filing a full spec now would create
architecture gravity the constellation should not yet carry.

- `GOV_GAP_TEMPORAL_AUTHORITY_001` — the time plane. Blocked on an *enforceable*
  (not advisory) cross-host gap-bound forcing case.
- `GOV_GAP_RETRACTION_TRANSPORT_001` — negative-news routing + reliance index.
  Refusal already inexpressible; closest to earning a real spec. Owner is
  nightshift + continuity, not AG.
- `GOV_GAP_VERDICT_CUSTODY_001` — adjudication seam. The decision is *where the
  boundary is marked*, not what to build; may resolve as a labeled out-of-scope
  seam rather than a component.
- `GOV_GAP_EVIDENCE_RETENTION_001` — death rites, tombstones, standing-to-delete.
  Composes with `docs/HISTORY_BOUNDARY.md`.
- `GOV_GAP_RESTORE_EPOCH_001` — DR as typed fiat event with blast-radius.

Schema evolution already has partial homes (`docs/VERSIONING.md`,
`specs/gaps/CROSS_DOMAIN_SCHEMA_GAP.md`); fleet control is already zoned by the
genesis-class rule. Neither needs a new reserved name.

**Notary** is *not* a reserved AG gap name — it graduated to its own project
candidate (locker-adjacent, not AG-owned; see §Notary). The **reflex plane** and
**transport / state-exchange** are zoning sections, not reserved names: reflex
composes from existing parts (Standing/Verdict/LA/Expiry/Absence/Freeze) and earns a
component only on a forcing case; transport is permitted to stay dumb plumbing under
WLP custody.

## Disposition

1. **No build.** Nothing here is authorized. Every organ gates on a forcing case.
2. **Independent review wanted before promotion.** Because the source is
   LLM-relay, any promotion of a reserved name to a filed spec — or any component
   construction — should first get a non-relay adversarial pass (operator review,
   or `codex-exec` framed to refute, grounded in `file:line`). The internal
   Fable-vs-ChatGPT pass does not discharge this.
3. **Watch the refusal-already-inexpressible organs.** Retraction transport and the
   verdict seam are where current gates cannot express a refusal they should;
   **Notary** was the third and has now graduated to a project. If a concrete
   specimen appears in this repo, the remaining two graduate from reserved-name to
   filed-spec first.
4. **Ownership stays put.** AG records; NQ owns witness grammar, `~/git/standing`
   owns standing semantics, `~/git/linearaccountant` owns capacity internals,
   Notary is its own (not-yet-built) project. AG may not unilaterally rename or
   ratify those surfaces (cf. constellation constraint: local grammar > shared
   vocabulary).
5. **Confound on record — witness competence has a live downstream consumer.** The
   operator started `~/git/nq-root/nq-security-witness` and *then* made the
   witness-competence decisions captured in §Witness competence (attention isn't
   testimony; operator-attestation is claim-plane; divergence attests shape not
   independence; absence needs coverage). So that section is **not purely
   deferred** — it reshapes an already-built NQ component. "Not wasted work,
   changes the shape." NQ-side concern; AG only records the pointer.
6. **Second pass is in (this is it).** The first appendix was Notary / transport /
   reflex / instrument; this second appendix added evidence classes (declared vs
   simulated), Phosphor aggregates, succession + redaction zoning paragraphs, and
   the survey-done declaration. (A "third confound" the operator half-remembered
   turned out to be thread-conflation, not a real third item — nothing owed. The
   file stays a living map regardless.)
7. **One launch-blocking build item now exists.** The **simulated evidence class +
   firewall predicate** has a forcing case (the demo mints simulated receipts) and
   must land before any public demo. It is *not* built here — capturing ≠ building —
   but it is the first item on `working/launch-plan-2026-06-11.md`'s sequence, and
   it is shared vocabulary (NQ owns declared; AG owns the class on its receipts), so
   AG cannot ratify the taxonomy unilaterally.
8. **Survey phase declared done.** New findings now alias to Standing or the clock;
   the scouting is over and the next move is the slab (the demo), per the launch
   plan. This file is a map, not a to-do list — the to-do list is the launch plan.

---

## Cross-references

The to-do list this map feeds:

- `working/launch-plan-2026-06-11.md` — the demo + site + Show HN plan (internal,
  unpublished). The slab the survey was scouting toward; carries the launch-blocking
  simulated-evidence item, the Columbo demo design, and the specimen-at-front ratchet.

Uncompressed companion (the bones under this placard):

- `working/constellation-zoning-source-notes-2026-06-11.md` — the excavation bed:
  keeper phrases, anti-smoothing bad→better pairs, ugly state names verbatim,
  rejected-tempting-design catches (with who-caught-what), and the throughline.
  Read it when a table row here feels too tidy — the sharp specimens are
  compression-resistant landmines against a future "reasonable implementation"
  that quietly erases the point.

Kernel docs this composes with (they carry the load):

- `docs/agent-governor-meta-plan.md` — the planes that exist; directional kernel;
  Z3-as-checker; wards-subtract/warrants-attest. **This file is its deferred-organ
  companion.**
- `working/directional-invariants.md` — the ten directional invariants; §Standing
  here sharpens invariant 1 (lapse, two-clocks, product labels).
- `working/endgame-synthesis-2026-06-10.md` — genesis-class self-amendment rule;
  the fleet-control organ is *already zoned* there.
- `working/linear-accountant-handoff.md` — the LA packet/integration boundary;
  §Linear Accountant here is the internal complement.

Filed gaps that already obligate corollaries named above:

- `specs/gaps/GOV_GAP_VALIDITY_SPENDABILITY_SPLIT_001.md` — eligibility ≠ capacity
  (the LA gravity-pull).
- `specs/gaps/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md` /
  `GOV_GAP_RETROACTIVE_LEGITIMATION_BOUNDARY_001.md` — post-validated ≠
  pre-authorized (the two-clocks gap).
- `specs/gaps/GOV_GAP_SEALED_OUTCOME_BOUNDARY_001.md` — construction guarantees do
  not survive serialization (schema-evolution adjacency).
- `specs/gaps/GOV_GAP_PHASE_WITNESS_MAPPING_001.md` — AG's phase witnesses; the
  witness-competence table is the upstream NQ grammar those phases map into.
- `specs/gaps/CROSS_DOMAIN_SCHEMA_GAP.md`, `docs/VERSIONING.md`,
  `docs/HISTORY_BOUNDARY.md` — partial homes for schema/retention organs.

Memory pointers: `notary_log_continuity.md` (new — the §Notary project candidate),
`linearaccountant_repo.md`, `standing_integration.md`, `wlp_protocol.md` (transport
custody owner), `phase_witness_mapping.md`, `constellation_constraint.md`,
`continuity_governor_split.md`.

---

> **A missing organ earns construction only when an actual refusal cannot be
> expressed without it. Until then: zoning, not buildings.**
