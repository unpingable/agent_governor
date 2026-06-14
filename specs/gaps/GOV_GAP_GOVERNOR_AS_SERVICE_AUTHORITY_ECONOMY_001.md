# GOV_GAP_GOVERNOR_AS_SERVICE_AUTHORITY_ECONOMY_001

## Title

AG 3.x "governor-as-a-service" is not a deployment convenience — it is the substrate
that makes the governor **governable**. Demote the governor from sovereign to a
cap-bearing *subject* inside a kernel-enforced authority economy: kernel owns a linear
capability ledger, WLP is the witness seam, LA enforces non-double-spend of the
*authority-to-govern*, and the governor becomes effectual only by holding the relevant
cap — never by self-assertion.

## Status

**Candidate / long-range architecture record. Authorizes NO build.** Filed 2026-06-13
from a three-context design synthesis (operator + ChatGPT + Claude-web). This is a
"name early, ratify lazily" record per the YAGNI-scope discipline: the retrofit cost of
discovering this shape *after* consumers grow against a monolithic governor is exactly
the cost curve that justifies a record now. Marked candidate/non-binding; any
implementation is custody-affecting (it restructures who holds authority) and requires
operator fiat + supersession ceremony, not ordinary slice work.

First forcing pressure is already visible: P4 self-anneal (blue-green successor) and the
"govern a second runtime" case both *presuppose* this shape. Until one of those is live
work, this stays a handle for review.

## The keystone theorem

> **Governor-as-a-service is what makes the governor governable.**

A monolithic governor cannot be fused by the kernel, cold-started by construction, or
denied its own self-granted authority — because it *is* the kernel; there is nothing
above it to withhold a cap. The moment the governor is a cap-bounded, kernel-routed,
WLP-witnessed service, the kernel can: withhold the mutation cap (the **fuse**), require
a cold-context cap (**cold-start**), and refuse to regrant caps the governor tries to
self-mint (the **self-anneal leash**). Every doctrine landed in the last campaign
silently presupposed this. 3.x is not a separate track — **it is the substrate the
doctrine was waiting for.**

## The separation of powers (do not collapse)

```text
Operator / Ratification Root
  declares a kernel lineage as the enforcement root for an authority domain

Kernel / LA
  owns the linear capability ledger; enforces linearity; refuses double-spend;
  derives effectuality from cap possession (NOT from a flag)

Governor Service
  emits admission/refusal/baseline TESTIMONY; may HOLD GovernanceCap(scope);
  cannot self-grant it

WLP
  witnesses launch, action envelopes, revocations, cutovers — the witness seam,
  NOT the throne and NOT the enforcer

Driftwatch / Observatory
  monitors governor behavior through its WLP emissions (capless, testimony-only)
```

Collapse any two and you have rebuilt the sovereign blob — "a tiny sovereign that
notarizes its own passports." The governor must not be the kernel; **WLP must not be the
kernel either** (the same eviction, one seam over).

## The six laws (ratified-shape candidates)

1. **No writable effect bit.** `effective:true` is never a field the governor (or a
   shadow) writes — that is the `complete:true` soul-growing boolean again. Effect is
   *derived from live cap possession*: `effectual(action) := emitter holds the required
   cap ∧ cap scope matches ∧ cap fresh/unrevoked ∧ launch lineage matches ∧ WLP
   witnessed the envelope`. `effective:false` may exist as a computed annotation, never
   as an input.
2. **Governance authority is linear.** `GovernanceCap(scope)` is an LA resource: held by
   at most one authority lineage, consumed/revoked at cutover, re-minted only by an
   admitted transition ceremony, never duplicated. "Two effectual governors for one
   scope" is not a special fork rule — it is **double-spend of `GovernanceCap(scope)`**,
   refused by the existing LA spend wall.
3. **Shadow governors are capless.** They may observe, diagnose, recommend, emit
   candidate verdicts, and build comparison evidence. They cannot mutate. No "almost
   governing"; no margin-monarchies.
4. **Cutover is cap transfer.** Revoke the old governance cap, grant the new, witness
   both, prove no overlapping effectual authority.
5. **Kernel root is declared, not self-proven — and the regress bottoms at fiat, named.**
   Content-addressing + append-only gives *auditability*, not authority. "Tamper-evident"
   must not quietly become "authorized" (else Git is a constitution and GitHub is the
   Vatican) — this is the `weak_property_strong_property` enemy shape, caught live. The
   root is legitimized by *declared adoption* and made *accountable* by immutability. The
   un-derivability does not vanish; it **moves up to the declarer**, which is itself
   ungrounded — genesis-fiat, "because I say so," Standing's exactly-one-per-instance. The
   mature posture is not "no unwitnessed thing exists" (theology) but **exactly one
   unwitnessed root per authority instance, named**, with everything else proving lineage
   back to it or refusing. Honest bottom: *adopted by fiat, constrained by immutability,
   accountable through receipts.*

6. **Succession is authorized above the contenders.** Linearity (Law 2) forbids two
   simultaneous cap-holders, but is silent on *who may move the cap* — and that silence is
   where a candidate co-authors its own activation (a perfectly linear coup; excellent
   stationery; still a coup). Neither incumbent (would ratify the change it wants to
   complete) nor candidate (self-grant) may authorize the transfer. Authorization comes
   from the **named ratification root, through a cold context, receipts-only**. This is the
   No-Negative-Clearance-over-time keeper in executable clothing; without it the linearity
   holds and the *succession* still launders.

   *Two refinements this filing pins on Law 6:*
   - **Cold succession inherits the cold-start two-actor limit.** Per
     `GOV_GAP_COLD_START_RATIFICATION_001`: controller coldness is constructible (fresh
     process, receipts-only); **operator coldness is not** (no fresh James) — only
     approximated by cadence + receipts-only re-presentation. So Law 6's "cold context" is
     a fresh *controller* that re-derives the succession case from receipts and presents
     it; the *operator* ratifies that cold presentation, never their own warm draft. Law 6
     is exactly as cold as the cold-start machinery makes it, no more.
   - **Genesis is succession-from-null.** The first governor's installation has no
     incumbent and no candidate; "above both contenders" degenerates to "the named root,
     directly." Genesis is the one cutover authorized by Law 5's fiat itself — a receipted,
     non-transitive exemption (the validator-v0.1.0 bootstrap pattern), not an open door.

### The doctrine→mechanism table (why this is implementable, not devotional)

| Doctrine (already landed/filed) | Service/kernel form |
|---|---|
| Fuse (`GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001`) | kernel withholds the mutation cap |
| Cold start (`GOV_GAP_COLD_START_RATIFICATION_001`) | successor spawned receipts-only, no warm-state channel |
| Self-anneal leash (cross-tool receipt-sovereignty note) | candidate governor cannot grant itself authority |
| No Negative Clearance over time (`…STATE_REENTRY…`) | incumbent cannot ratify the transition that empowers its successor |
| Operator halt | cap revocation, not a magic emergency hatch |
| ControlBaseline promotion (`…CONTROL_BASELINE…`) | blue-green cutover by cap re-grant |
| Driftwatch-on-labelers | Driftwatch-on-governor (its WLP emissions are its behavioral surface) |

### Consequence that falls out: self-anneal can never self-promote

Law 6 makes "the system improved itself" structurally impossible — and that is the
intended end of the mysticism, not a limitation. A candidate governor can be spawned,
shadowed (`effective:false`, derived from holding no cap), compared, and accumulate
evidence **autonomously**; it can *never* promote itself, because the cutover requires a
cold ratification above both contenders. "Self-anneal" is therefore a misnomer: it is
**operator-anneal over candidate-generated proposals** — the system proposes and shadows
itself, the human gates every activation from cold context. This is the campaign cut-list
"no auto-apply" rule reaching its terminal form: the leash is not a policy the governor
honors, it is a cap the governor structurally cannot grant itself.

## What this composes from in-tree (the part that says "not greenfield")

These are the load-bearing observations this filing adds beyond the synthesis — each
connects the new shape to a mechanism that **already exists**, so 3.x is composition,
not invention:

1. **The GovernanceCap lease-freshness IS the two-clock gate we already shipped.**
   The `CapabilityLease` freshness window (valid-when-issued, void-when-exercised) is
   exactly `standing_spendability.py` / `clock_witness.py` lifted to the meta-cap. So
   "AG-down → kernel refuses" is **not automatic**: a stale-but-unexpired lease keeps the
   governor effectual until its horizon, and the *refusal at the horizon* is the
   `StandingSpendabilityGate` two-clock check. 3.x needs no new freshness primitive — it
   lifts the existing seam. *A gap is a difference between compatible clock witnesses, not
   numbers* — at the governance-cap layer too.

2. **The genesis GovernanceCap is the validator-bootstrap pattern.** Law 4 covers
   *cutover* (transfer) but not *genesis* (the first mint, where there is no prior lineage
   to revoke from). This is the same bootstrap-fail-closed hole the standing validator
   solved at v0.1.0: one bounded, *receipted, non-transitive* operator-fiat sanctioned
   hole (`src/governor/standing/validator.py` `_verify_bootstrap`). The genesis cap must
   be exactly that — not an open door, a single witnessed exemption.

3. **The cutover underlap is self-healing because refuse is the safe state.** The
   synthesis guards *overlap* (fork refusal) but skips *underlap* — the window between
   revoke-old and grant-new where a scope has zero effectual governor. That window is
   safe: a scope with no `GovernanceCap` refuses all mutations (fail-closed). Underlap
   costs availability, never admissibility — consistent with *recomposition's only verb
   is refuse*. (Overlap is the dangerous one; LA linearity forecloses it.)

4. **Driftwatch-on-governor needs a *heterogeneous* shadow.** A captured governor shapes
   its WLP emissions to look clean (the correlator capture problem —
   `correlator_telemetry.py`, generated-contradiction suppression). A homogeneous shadow
   waves through the same overclaim — exactly the interferometry independence axis
   Claude-web invoked for model review, applied one seam over: incumbent vs shadow must be
   *different lineage/implementation* to catch co-captured WLP. Cooperative-redundancy
   independence scoring (`independence.py`) already types this.

5. **Cap classes are a closed, absence-restrictive allowlist — not a taxonomy.** Caps
   gate authority transitions, so per the zoning doctrine
   (`docs/constellation-zoning.md` §3) the class set
   {observe · diagnose · recommend · admit · mutate · revoke · transition · seal} must be
   a CLOSED enum; an action requesting an unlisted class is a typed refusal, not
   "unknown → allow." (Detectors over open spaces may blocklist; this is a gate over
   authority — it allowlists.)

6. **The kernel's entire governance job is the five lease-validity checks = the narrow
   Rust kernel already ruled licensable.** The kernel consuming a `LaunchReceipt` checks
   exactly: structurally valid · issued by the pinned lineage · matches binary/kernel/
   config hash · fresh · requested action ⊆ admitted cap surface. That five-check
   predicate is small enough to be the post-launch Rust decision kernel of
   `[[rust_kernel_port_ruling]]` / `GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001`. Everything
   else stays above-kernel in Python. The golden receipt corpus is the contract.

## One correction this filing pins (anti-overclaim)

The governor **can** act in the dumb Unix sense (write files, fork, log, summon YAML).
You do not *prevent* darkness; you make it *non-authoritative*. The correct statement is:

> A governor action has no effect unless it is WLP-witnessed and kernel-admitted.
> An unwitnessed action may exist; it has no standing; an unwitnessed mutation is
> refused / quarantined / non-relying.

(Stated because the synthesis itself slipped "can't act in the dark" → "impossible" and
a heterogeneous reviewer caught it — the bad-evidence-can-exist-but-cannot-launder theme,
pointed at the governor itself. `signed-is-not-witnessed`, applied to the signer.)

## Non-goals

- **Not an AG rewrite.** Orchestration, policy loading, receipt plumbing, CLI/API glue
  stay Python and above-kernel ("move the mint, not the metropolis").
- **Not a kernel-interface / packaging decision** (PyO3 vs sidecar vs CLI) — that is
  `GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001`'s open question.
- **Not "WLP controls everything."** WLP witnesses; the kernel/LA enforces.
- **Not authorized implementation.** Build waits on a forcing case (first second-runtime
  or first blue-green self-anneal) and operator fiat. This is custody-affecting.

## Forcing case / acceptance

Earns promotion from candidate when one is true and live:
1. AG must govern a runtime it is not embedded in (the second consumer), OR
2. P4 self-anneal needs a real blue-green cutover (successor service shadowing the WLP
   stream, `effective:false`, compared, cut over by cap re-grant), OR
3. The fuse / cold-start / leash gaps reach implementation and discover they cannot be
   enforced without a cap the kernel can withhold from the governor.

When live, the acceptance work is: the cap-class closed enum; the derived effect
predicate (no writable bit); the `GovernanceCap` LA resource + double-spend refusal test;
the cutover ceremony (revoke→grant→witness, overlap-refused, underlap-fail-closed); the
**succession-authorization gate (Law 6): cutover refused unless authorized by the named
root through a cold controller presentation, neither incumbent nor candidate self-ratifying**;
the genesis bootstrap exemption (receipted, non-transitive); and the five-check kernel
lease validator.

### Open question this filing does NOT resolve

**Cross-root / multi-instance authority.** Law 5 lands "one named root per authority
*instance*." A federated constellation then has *N* named roots (no meta-sovereign — that
would rebuild the monolith). Unaddressed: what happens when a governor under root A acts
on a scope owned by root B? Candidate answer (not ratified): cross-root action is refused
unless an explicit, witnessed inter-root grant exists — i.e. the same allowlist-authority
discipline at the root boundary. Flagged, not decided; it is the federation seam and
belongs to a later forcing case.

## Relationship to other gaps

- `GOV_GAP_AUTHORITY_KERNEL_SUBSTRATE_001` — *where* the mint lives (Rust timing). This
  gap is *the control structure* the mint sits inside. Siblings.
- `GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001` — the fuse is the first concrete cap the kernel
  must be able to withhold; this gap is why withholding is possible at all.
- `GOV_GAP_COLD_START_RATIFICATION_001` — cold-start is *how you spin the successor
  service*; the two were the same mechanism.
- `GOV_GAP_CONTROL_BASELINE_001` — blue-green cutover = baseline promotion by cap
  re-grant.
- `GOV_GAP_STATE_REENTRY_PROTOCOL_001` — No Negative Clearance; here: an incumbent cannot
  ratify its successor's empowering transition.
- `specs/core/SELF_GOVERNANCE_SPEC.md` — the §3.x Service Boundary carve-out the crosswalk
  left spec-side; this gap is its long-range shape. Pluralizable/shadow/revocable
  governor = the spec's executor/proposer separation, federated.
- `~/git/wlp` (`[[wlp_protocol]]`), `~/git/linearaccountant` (`[[linearaccountant_repo]]`),
  `~/git/standing` (`[[standing_integration]]`) — the witness seam, the linear-spend
  enforcer, and the freshness/identity substrate this composes.

## Provenance

Three-context synthesis 2026-06-13, during P4 entry, while the operator was conferring
externally ("baiting" the engagement). ChatGPT supplied the service/WLP/kernel split and
the throne-is-not-WLP and root-is-declared-not-immutable corrections; Claude-web supplied
the sovereign-to-subject framing, the blue-green-is-cold-start collapse, the
heterogeneous-reviewer catch on "can't act in the dark," the regress-bottoms-at-fiat
sharpening, and **Law 6 (succession authorization)**; the LA-lift of the plural-governor
invariant and the derived-effect-bit footgun came from the cross-model exchange. The
recurring weak→strong error caught across the exchange is named in
`docs/doctrine/weak_property_strong_property.md` (the enemy shape; NLAI generalized). This
filing (Claude, AG-side) adds the in-tree composition points, the anti-overclaim pin, the
cold-succession/genesis refinements on Law 6, the self-anneal-can-never-self-promote
consequence, and the cross-root open question; and scribes the whole as a candidate
handle. The short form:

> The kernel is the declared enforcement root; the governor is a cap-bearing subject;
> WLP is the witness surface; LA prevents the authority-to-govern from being
> double-spent. Federation finally reaches the last component that thought it was the
> exception.
