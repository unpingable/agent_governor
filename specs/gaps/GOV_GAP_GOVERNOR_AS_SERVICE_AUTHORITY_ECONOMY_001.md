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

## Scale is root-distance, not feature scale (the export/adoption axis)

Added 2026-06-13 (three-context, post-wrap). Once the governor is a cap-bounded subject
under a named root, the question "how big does AG get?" stops being a feature-ladder and
becomes one axis:

> **AG scale is root-distance scale: how far from the enforcement root did this receipt
> travel, and what strength survived the trip?**

This collapses the roadmap to **two builds, then receipts travel**:

- **3.x — the machine.** Governor-as-a-service under a root you control: kernel-held
  linear cap ledger, WLP witnessing, LA forbidding double-spend, the six laws. Mechanical
  refusal is possible *because you own the enforcement root*. This is the bootstrap; it
  does **not** wait on any external adoption.
- **3.5 — the language.** A portable receipt grammar that carries **root lineage** so the
  same receipt is legible outside AG. Not a new sovereignty model — an export ABI.

There is **no 4.x / 5.x to build.** "Federated AG," "treaty AG," "provider/sovereign
adoption" are not versions or features — they are **landing conditions**: the strength a
3.5 receipt *has* when it lands at distance, computed by whoever catches it. The instant a
3.5 receipt exists it already spans the whole axis at once.

### Force is consumer-relative — the receipt names its root, the reader does the trig

The load-bearing correction (and it caught this filing's own first design): **enforcement
strength cannot be a field the emitter stamps.** Strength is a *relation*, not an intrinsic
property —

```text
strength = f(reader_root, receipt_root_lineage, adoption_relation)
```

A distance is between two points; it cannot be a property of one endpoint. The same
receipt is *mechanical refusal* to the root that issued/adopted it, *treaty evidence* to a
contracted partner, *audit evidence* to a regulator, *observer-only* to a stranger, and
*meaningless* to an untrusting root — **simultaneously, no contradiction.** So a stamped
`enforcement_basis: mechanical_refusal` is the `effective:true` / `complete:true` footgun
at the grammar layer: the field built to *prevent* laundering would itself launder (a 4.x
node inflates "treaty" → "mechanical" by typing the stronger word). It is a fresh hat on
the `weak_property_strong_property` enemy shape, and the axis caught it by pointing back at
the field design.

**The receipt carries FACTS, never a force-conclusion:**

```json
{
  "issuer_root": "...",
  "adoption_root_lineage": "...",
  "witness_chain": "...",
  "cap_lineage": "...",
  "subject_scope": "...",
  "action_envelope": "...",
  "receipt_hash": "..."
}
```

The reader derives the strength from *its own* root-relationship:

```text
same enforcement root        -> mechanical refusal
subordinate accepted root    -> locally / tenant enforceable
contracted external root     -> treaty evidence
unknown / unadopted root     -> observer evidence
conflicting root             -> inadmissible / untrusted
```

### The central invariant

> **Receipts do not declare their own force. They declare their root. Force is derived by
> the reader.** — *the receipt names its root; the reader does the trig.*

This is the cross-root open question (above) resolved into grammar: cross-root strength is
not granted by the issuer, it is *computed by the consumer* from the named root lineage —
the same allowlist-from-your-own-root discipline, at the receipt layer. (Composes with
`docs/doctrine/weak_property_strong_property.md`; "receipt is not force" and "treaty is not
enforcement" are rows in that table.)

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
on a scope owned by root B? **Partially resolved by the root-distance grammar above
(2026-06-13):** cross-root strength is not granted by the issuer — it is *computed by the
consumer* from the named root lineage (same-root → mechanical; contract-root → treaty;
unknown/conflicting → observer/inadmissible). What remains open is the *mechanical*
cross-root case (root B actually enforcing root A's receipt), which requires an explicit,
witnessed inter-root grant — the allowlist-authority discipline at the root boundary. The
grammar makes the *evidence* portable; the *enforcement* across roots is still a later
forcing case.

## Related work / external positioning (the seam is crowded — position precisely)

Added 2026-06-13 after a literature pass corrected an earlier "empty seam" belief. The
agent-governance corner **lit up across 2025–2026**; this is not open wilderness. Position
AG as the *checked authority substrate*, not as a competitor to the now-published
certificate frameworks.

**The near-twin (the cite, not a rival to ignore): "Proof-Carrying Agent Actions" (PCAA),
arXiv 2606.04104, Zexun Wang / Ond Holdings, 2026-06-02.** Beat-for-beat close to the
governor-as-service / PCAR shape: a runtime-neutral **action certificate** (not a vendor
session record), five checkpoints (pre-action admissibility · action open · assumption
capture · approval · outcome closure), a portable action envelope, runtime/approval
receipts, replay-ready proof closure, and an explicit three-way authority split (workspace
/ runtime / external governor). Treat it as the related-work anchor.

**What survives as AG's distinctive seam** — confirmed against the PCAA v1 HTML
(structured read 2026-06-13; *this is one LLM read of v1, not a checked fact — a careful
full-body read of 2606.04104 is the real confirmation, still owed*):

1. **Root-distance / reader-derived force.** PCAA **stamps** the enforceability class
   `ε(a) ∈ {pre_execution_gate, observe_only, delegated_runtime_control,
   runtime_controlled}` *on the envelope, by the issuer*. It has no "root," no
   reader-relative force, no adoption-root vs enforcement-root split; authority is a fixed
   hierarchy, not a distance. AG's axis — *force = f(reader_root, receipt_root_lineage,
   adoption_relation)* — is absent. **And PCAA's stamped `ε(a)` is itself an instance of
   the writer-stamped-force footgun** this gap's "Scale is root-distance" section names
   (`weak_property_strong_property`): so AG does not merely sit adjacent, it identifies a
   specific weakness in the leading near-twin. *(Hold this "PCAA stamps, doesn't derive"
   claim as appears-to pending the full read; if it inverts, so does the sharpened
   contribution.)*
2. **Checked, not typed.** PCAA states it "does not currently implement a full conformal
   pipeline in the product" — framework/schema-typed, no formal verification / theorem
   proving / kernel enforcement. AG's contribution is the *mechanically discharged refusal
   surface*: the invariants that actually refuse laundering, replay, self-promotion,
   effect-bit fraud, stale authority, and governance-cap double-spend (receipt_kernel's 13
   invariants; the Lean admissibility kernel above). **"PCAA names the obligations; AG
   makes the obligations executable."** *Typed is not checkable* — and the gap between
   claiming the shape and discharging it is the graveyard of failing cases, not a
   related-work paragraph.

**Adjacent convergence (per the operator's abstract survey 2026-06-13; not independently
fetched here):** Verifiability-First signed per-action receipts in append-only logs (Dec);
the intent/enforcement split as a theorem — model supplies intent, a deterministic gate
outside the model supplies enforcement (Feb); Dawn Song's group on **source-relative
validity** — same action legitimate or violation by *who produced the instruction* (Mar).
Note the precise distinction: source-relative validity is the **producer** end of "valid
to whom" (provenance of the instruction); AG's root-distance is the **consumer** end
(force graded by the reader's relation to the issuing root). Both are "valid to whom," at
opposite ends — the producer end is now occupied; the consumer end is AG's. Also in the
neighborhood: Agentic JWT (agent identity as a hash of prompt/tools/config), AGENT-C
(tool-call-sequence contracts), DID principal-anchoring, and the industry stack (A2A,
AP2's cryptographic user-intent proofs, ERC-8004 trustless-agent registries).

**Corrected novelty stack (do NOT claim novelty on occupied terms):**
- *Not novel:* action certificates, portable envelopes, runtime-neutral agent governance,
  replay-ready proof bundles, approval receipts, observer-vs-pre-execution coverage
  disclosure.
- *Sharper / possibly novel:* `receipt force ≠ receipt content`; force reader-derived from
  root relation; adoption-root vs enforcement-root; treaty-evidence vs mechanical-refusal;
  no writer-stamped enforcement strength; governance-cap succession as linear transfer
  authorized above contenders; **checked discharge over typed framework.**
- *Stylistically AG:* governor demoted from sovereign to cap-bearing subject; WLP as
  witness-not-throne; LA as exactly-once wall for the authority-to-govern; heterogeneous
  model review as the anti-laundering interferometer.

The corrected framing, one line:

> PCAA establishes portable certificate-bearing action governance (typed). AG addresses
> the next problem: when such certificates cross roots, their authority strength must be
> *derived by the consumer*, not asserted by the producer — and the obligations must be
> *mechanically discharged*, not described.

**Skim table (survives a hostile read).** The relation is *correction, not parallel lane*
— stated cold: **AG is not a competing system; it is a checked critique of the authority
semantics that PCAA-style certificates risk leaving emitter-stamped.** ("Risk leaving,"
not "leaves" — pending the full-body read; if PCAA turns out to *derive* rather than
*stamp* `ε(a)`, this softens toward parallel.)

| Claim | PCAA | AG |
|---|---|---|
| Portable action envelope | yes | yes |
| Enforceability classes | emitter/envelope-stamped (`ε(a)`) | reader-derived from root relation *(appears-to; pending full-body read)* |
| Formal / mechanical discharge | "does not currently implement a full conformal pipeline" (paper) | refusal cases + Lean admissibility kernel + receipt_kernel invariants + tests |
| Authority succession | framework-level | linear cap transfer + cold above-contender authorization (Law 6) |

Reference-implementation status, like standing, is **adopted, not declared** — which is
exactly why the move is to ship the smallest specimen that *discharges* what others
*describe*, not to claim the lane. (Your own doctrine, one more time.)

**Owed next action — a read, not a build.** Read PCAA 2606.04104 full-body like a source
(not a horoscope): the enforceability-class section, the authority-model / hierarchy
section, the definition of *who assigns* `ε(a)` (issuer- / runtime- / verifier- /
consumer-stamped), and whether any root / adoption / enforcement relation appears
materially (not as vibes). The only verdicts allowed afterward are boring:
**confirmed | inverted | ambiguous-needs-closer-pass.** Not "we win," not "we're doomed,"
not a new roadmap. Until that pass, every claim in this section stays **appears-to** — the
discipline holding *there* is the whole point. The smallest sharp specimen (force cannot
be self-declared: reader derives from root relation, kernel grants effect only where cap
lineage discharges) is the post-confirmation artifact, deliberately NOT pre-built here
because it would rest on the unconfirmed enforceability row.

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
handle. **Post-wrap addendum (2026-06-13): the "Scale is root-distance" section** —
ChatGPT proposed the scale table + a stamped `enforcement_basis` field; Claude-web caught
the field as the effect-bit footgun (strength is consumer-relative; *the receipt names its
root, the reader does the trig*) and collapsed the version-ladder to two builds + landing
conditions. The discarded part — a literal 4.x/5.x feature ladder — is deliberately NOT
scribed per operator instruction. The short form:

> The kernel is the declared enforcement root; the governor is a cap-bearing subject;
> WLP is the witness surface; LA prevents the authority-to-govern from being
> double-spent. Federation finally reaches the last component that thought it was the
> exception.
