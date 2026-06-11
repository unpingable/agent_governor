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

## Two operating disciplines

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
6. **More canon pending.** This appendix (Notary / transport / reflex / instrument)
   is the operator's *first pass*; a second pass follows once this is in, and the
   operator flagged a possible third confound still to be dug up. Treat this file
   as open for at least one more appendix.

---

## Cross-references

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
