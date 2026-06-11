# Constellation Zoning — Source Notes / Excavation Bed (2026-06-11)

**Status: excavation bed, NOT doctrine, NOT a chatlog, NOT a spec.** This is the
uncompressed companion to the curated `docs/constellation-zoning.md`. The placard
is in `docs/`; the bones are here. Its whole job is to keep the high-entropy
material — sharp specimens, ugly state names, rejected tempting designs, the
phrasings that carry the charge — from being smoothed into enterprise-architecture
incense by the time it reaches the map.

If `docs/constellation-zoning.md` and this file ever disagree, **this file is the
older, less-compressed witness** — but the docs file is the navigable one. Neither
is binding (see caveats at the bottom).

Provenance: a long design conversation between the operator, Claude Fable (web),
and ChatGPT. All three are operator-tuned — the two models have been baking in
the ecosystem, the papers, and the Lean kernel for months — so this is
**me-flavored, design-aligned thinking that converged**, not random model drift.
It is still *relay* (two models building on a shared aesthetic), so it wants an
independent non-relay pass before any of it becomes binding. That's a promotion
gate, not a verdict on quality.

---

## The throughline

There is one move under everything in this conversation, applied recursively
across five domains. Worth stating plainly because the taxonomy in the placard
can hide it:

> **Every convenience that bundles or smooths erases a refusal someone needs.
> The discipline is to keep refusals atomic, visible, and downstream of evidence
> — and to make every conversion either preserve structure, explicitly drop it,
> or refuse.**

The operator's compression of the whole project, said in passing and worth
keeping:

> **Half the project is just making laundering stop wearing a polo shilt.**

Same sin in every domain, only the costume changes:

```
observation        → authority        (the meta-plan's trapdoor)
bundle             → witness          ("security-witness", custody soup w/ a badge)
fungible pool      → spendable budget (provenance dies at deposit)
refund             → reversal         (a time machine that breaks custody)
version number     → compatibility    (producer fiat verified by vibes)
orchestrator       → sovereign        (helm-for-the-constitution)
re-validation      → fresh token      (eligibility re-asserted, not capacity reborn)
```

The spine is the **no-unifier result**: there is no mega-witness, no "security
event" blob, no consensus cosplay. Atomic testimony plus bridge custody. The
constellation's own skepticism applies reflexively — *convergence from a shared
upstream is one observation wearing three hats* — which is why this very document
carries a relay caveat about itself.

And it all bottoms out in **two gravity centers**: standing and bounded time.
Refunds need standing. Schemas need standing. Deletion needs standing. Clawback
needs standing. And everything needs an attested clock. Two centers, a lot of
principled plumbing between them, neither yet a dedicated witnessed plane.

The stop condition that keeps this from being infinitely productive:

> **The grain of witnessing is the grain of refusal.** A competence (or a
> component, or a witness kind) deserves to exist iff there's a real scenario
> where you can attest one half while refusing the other. No demonstrated refusal
> the current grain can't express → no new kind. *Standing before spendability,
> applied to the ontology itself.*

Over-splitting is the same sin as over-bundling, sign flipped. Both import error.

---

## Keeper phrases (verbatim-ish)

These carry the charge. They are the difference between the doc being useful and
the doc being incense. Preserved close to how they were said.

- *Convergence from a shared upstream is one observation wearing three hats.*
- *Make laundering stop wearing a polo shirt.*
- *A lease is not a proof; it is a priced assumption with a timer.*
- *A version label names a node; a bridge receipt names the admissible path
  between nodes.*
- *Fungibility is a silent unifier.*
- *Quarantine is not reversal; it is the ledger learning that a prior admission
  is now disputed.*
- *Standing is not possession of a token; it is a living relation reconstructed
  from stale observations.*
- *Witness competence: a witness is competent over claim classes, scoped to an
  observation surface, bounded by time, and silent outside that competence.*
- *Trust asserted is not trust witnessed.*
- *Self-report is a signed artifact, not a witnessed one. A party cannot witness
  its own act.*
- *Attention is a verdict, not a testimony.*
- *Standing-before-spendability is not merely an ordering claim — it is a claim
  that the ordering was observed and bounded.*
- *Dead watcher + self-liveness = immaculate silence. Very tasteful fraud.*
- *The system bottoming out in fiat is not the shame. The shame is pretending the
  turtle signed an affidavit.*
- *Fiat is admissible when declared and marked, and corrosive when costumed.*
- *DR is where governance systems go to lie.*
- *Informal pruning of an evidence locker is the most corrosive silent conversion
  available — it converts absence of evidence into evidence of absence,
  retroactively.*
- *The deployment tool is not allowed to become the sovereign by accident.*
- *A missing organ earns construction only when an actual refusal cannot be
  expressed without it.*
- *Atoms in the type system, molecules in the API, no opaque composites.*
- *Co-location is fine; co-mingling is the crime.*
- *Don't put both keys in the same drawer.*
- *Version everything, trust no version number.*

The funny-but-load-bearing ones (the humor is doing real compression work —
each names a failure mode you'll recognize on sight):

- *custody soup with a badge* — the bundled witness
- *consensus cosplay with better stationery* — divergence claiming independence
- *Redis with a monocle* — Linear Accountant if it becomes a balance counter
- *Standing II: Electric Regret* — what "just add reservations" turns LA into
- *the incident report as a grave marker* — TOCTOU killing exactly-once silently
- *PagerDuty Gothic* — an impostor and a dead grant wearing the same incident tag
- *a small monarchy with YAML* — a control plane that can edit its own audit trail
- *a constitutional crisis in a Patagonia vest* — automated control plane as
  amendment vector
- *the compost heap that invoices you* — slop recursion (agents writing tasks for
  agents)
- *enterprise-architecture incense* — what the placard becomes if it loses these
- *`foo-2` is already applying with a new mustache* — disbarment without continuity

---

## Anti-smoothing pairs (the bad → better that keeps prose honest)

These are the highest-value specimens. Each is a refusal you lose the moment you
write the "bad" version. Keep them; they are the unit test for the doctrine.

```
bad:    P has standing
better: grant G appeared valid in authority A's records, as observed by
        witness W at T, model_age Δ, under coverage C

bad:    security-witness says "secure enough"
better: identity_binding + temporal_order + absence_in_window(W) + degraded_mode,
        bridged thus — a named molecule that decomposes on demand

bad:    refund restores the unit
better: a compensation authority (standing-bearing) deposits a NEW unit
        referencing the failed exercise; the spent unit stays spent

bad:    the accountant picked some units, don't worry
better: input_selection_basis: selector_policy_ref (named, versioned, authorized)

bad:    balance = 7
better: unit_001 live (under standing A); unit_002 spent into E17;
        unit_003 expired at T; unit_004 spent_outcome_unknown

bad:    api_version: v2 (trust me, it changed compatibly)
better: v1_to_v2_bridge { preserved / transformed / dropped / defaulted /
        refusal_cases / contract_test_refs / migration_receipt_ref }

bad:    no event observed in window W → therefore silence
better: no event in W AND watcher demonstrably alive+observing W with coverage C,
        liveness attested on a SEPARATE plane

bad:    we watched the things we remembered to name → nothing relevant lapsed
better: lapse_bounded_over: [P1,P2,P3]; precondition_completeness:
        declared_not_witnessed; open_world_residual: unbounded

bad:    these three independent observers agree
better: these three attestations agree on fields F (independence is a separate
        provenance claim, or it's an unlicensed assumption — marked as such)

bad:    a human credential was exercised → a human was in the loop
better: challenge issued + response received within interval I + response carried
        novel content (a credential proves a credential, not attention)
```

---

## Ugly state names & schema fragments (verbatim-ish — these ARE the design)

The refusal lives in the name. Smoothing the name to something pleasant is how
the refusal dies. Keep these spiky.

```
standing_observed_but_lapse_unbounded     # the honest "valid but actually not"
standing_before_spendability_not_bounded  # the demo-shaped refusal
spent_outcome_unknown(exercise_ref)        # terminal UNIT state; not optimism bait
disbarment_advisory_no_continuity_enforcement
coverage_basis: declared_not_enforced ; side_paths_possible: true
clock_basis: unbounded ; gap_check: advisory   # vs ntp_bounded(±x) → enforceable
precondition_completeness: fiat_declared_not_witnessed
open_world_residual: unbounded
degenerate_fit / partial / unavailable / invalid   # quality, never zero

# conservation partition (every unit is exactly one):
{ live,
  spent(exercise_ref),
  spent_outcome_unknown(exercise_ref),
  expired(expiry_ref),
  quarantined(taint_ref),
  destroyed(clawback_ref),
  compensated_by(new_unit_ref) }

# the two-clock exercise receipt:
standing_observed_at=T1, model_age=Δ1
capacity_committed_at=T2, model_age=Δ2
exercise_at=T3
gap(T1,T2,T3) visible
clock_basis=...

# the standing molecule (forbidden as an atom):
standing_observation_v1 = registry_observation + identity_binding
  + temporal_order + staleness + authority_scope

# the derivative-standing product label (must say which one ran):
exercise_time_chain_walk      # expensive, fresher, stronger
grant_time_chain_assumption   # cheaper, weaker, bounded-propagation assumed
```

---

## Rejected / tempting-wrong designs (the catches, with who caught what)

The dialectic matters here: each of these is a design that *looked right* and got
refused, and the refusal is the evidence. Who caught it is part of the record —
not credit-keeping, but because the catches show the failure mode is non-obvious
(it survived one or two smart passes before someone flinched).

- **`security-witness` as a peer of `disk-witness`.** Tempting because "security
  events" feel like a category. Refused: it's a *scope*, not a competence — most
  security claims are identity + temporal + absence bundled, and the bundling is
  where custody leaks. (ChatGPT raised; both agreed instantly.)

- **`attention-witness`.** Fable caught `human-witness` about to grow legs, then
  *planted the same seed one row down* with `attention-witness`. Attention isn't
  observable — only proxies (challenge/response/cadence/entropy). Demoted to
  `challenge-response-witness`; the vacuity of the honest version IS the finding.
  (Fable caught its own re-growth — the little bastard grows legs even while
  you're warning about legs.)

- **`operator-attestation` in the witness column.** Tempting because `nq attest`
  feels like witnessing. Refused: self-report is a *signed* claim, not a
  *witnessed* one — it enters the claim plane and can only be *promoted* by an
  independent witness, never enters as testimony about itself. (Fable; the cut
  that "a party cannot witness its own act.")

- **`divergence-witness` attesting independence.** Tempting because you want to
  say "N independent observers agreed." Refused: it can attest agreement *shape*;
  independence is upstream provenance or an unlicensed assumption. The witness
  claiming "three independent observers" is one observation in a topology-expert
  hat. (Fable; reflexive application of the relay skepticism.)

- **`lapse_guard` meaning "lapse is bounded."** Tempting closed-world read.
  Refused: it can only mean "bounded over *this declared set*"; the enumeration
  itself is fiat-adjacent and the open-world residual stays unbounded. Coverage
  claim quietly promoted to a completeness claim = the next blob.

- **Standing lease to close the TOCTOU gap.** Tempting because it "freezes"
  standing for the exercise. Refused: a lease is itself a standing-shaped object
  with its own lapse, staleness, revocation lag — it re-imports the whole problem
  with a shorter Δ. Bounding-and-pricing the gap is the floor, and the floor is
  enough. (Fable flagged it pre-emptively as the 2am temptation.)

- **Fungible capacity pool.** Tempting for cheap denominations. Refused: it's a
  silent unifier — kills the "standing A's capacity is exhausted" refusal,
  cross-subsidy by erasure. If you want it, it's an *explicit minting bridge* that
  drops provenance with a receipt. **Note the live dissent:** Fable flagged that
  both models are provenance-maximalists by temperament and the *cost* side of
  UTXO-everything (fragmentation, split/merge machinery, receipt bloat at volume)
  had no advocate — explicitly said "hand this to DeepSeek with instructions to be
  unpleasant about it." That dissent is unresolved and should be honored before
  UTXO-default is treated as settled.

- **Refund as un-spend.** Tempting and intuitive. Refused: a time machine that
  breaks append-only custody. A refund is a new deposit by a standing-bearing
  compensation authority. And the third state — spent, outcome *unknown* — must be
  first-class terminal, because most exactly-once systems "handle" in-doubt by
  lying in one direction.

- **`denomination` as an innocent field.** Snuck into the schema. Caught
  (DeepSeek's round): it brings change-making, which brings split/merge/lineage-
  fanout — an entire subsystem. MVP answer: `denomination = 1`, atomic units,
  accept the unit-count cost. The anti-goblin rule: *any field implying split,
  merge, selection, lease, or side-channel mutation is not an innocent field; it
  is a future subsystem.*

- **Auto-selecting spend inputs (`earliest_expiry_first`, FIFO).** Tempting as an
  implementation detail. Caught: it has the ledger *choosing* whose provenance
  funds which action — fungibility re-entering at spend time. `explicit_input_only`
  is the honest default; selectors are named policy referenced in the receipt.

- **Helm-for-this / a fleet control plane.** The operator reached for it
  reflexively and *flinched* — and the flinch was correct. A control plane that
  pushes config to every gate is a super-authority, the exact concentration Wicket
  forbids. Config push is a conversion; the control plane never shares a host with
  the evidence plane; Ansible/Nornir (operator-attested fiat) until a forcing
  case. (Already zoned as the genesis-class rule in endgame-synthesis — recorded
  here because the *flinch* is the teachable moment.)

- **`spent_outcome_unknown` as a non-terminal "retry later" state.** Tempting.
  Refined (DeepSeek): the *unit* is terminal (custody halts at spend); the
  *exercise evidence file* stays open to late termination testimony. Two state
  machines, not one. Putting the mutability on the unit was the error.

---

## Per-organ excavation (raw notes, charge intact)

Material that the placard summarizes but shouldn't fully absorb. Read these when
the table row feels too tidy.

### Witnesses

The honest table has a "may NOT attest" column for a reason — the negative space
is where the refusals live. `temporal` may attest ordering and clock basis but
NOT authorization; `absence` may attest no-event-in-W but NOT global
nonexistence; `presence` may attest an actor was there but NOT intent; `capacity`
may attest resource-state-at-commit but NOT permission; `degradation` may attest
operating mode but NOT safety; `termination` may attest halted-vs-silent but NOT
success. Strip the negative column and every row quietly re-grows into a bundle.

`security_posture_v1` is the canonical *good* molecule: identity_binding +
temporal_order + absence_in_window(W) + degraded_mode, explicit bridge recipe,
refusable at each constituent, decomposable for audit. The doctrine against
mega-witnesses is against bundles that *can't* be taken apart and that emit
authority-shaped prose — not against ergonomics.

Deployment separation is load-bearing in exactly three places (where one
competence checks another's failure mode): absence ↔ its coverage receipt;
divergence ↔ its independence evidence; operator-claim ↔ presence/interaction
witnesses. Everywhere else, co-location is fine.

### Standing

Lapse is the monster because it's the one conversion with *no event at the
boundary*. Expiry is self-evident from the grant. Revocation is at least
event-shaped. Lapse — sponsor left, parent workload retired, granting authority
itself lost standing, class definition changed, precondition evidence expired —
just stops being true, silently. Standing systems that don't model lapse have a
fourth state called "valid but actually not" discovered forensically. The
countermeasure (absence-witnesses on declared preconditions) drags in the whole
coverage apparatus, which is correct and nobody does it.

The regress is load-bearing, not a footnote: *who has standing to grant standing?*
It doesn't bottom out in evidence; it bottoms out in a root grant that is fiat.
The system is **more** trustworthy if the root carries a receipt reading
`basis: fiat` in tasteful font than if it's laundered through self-referential
ceremony. AG already has the type (`FiatAdmissibility`).

Class-vs-instance is a perfect refusal split: *the grant is void* (governance
failure) vs *the grant is fine but this instance's membership is unproven*
(identity/provenance failure). Collapse them and an impostor and a dead grant
wear the same incident tag.

### Linear Accountant

The thing that makes it an *accountant* not a *counter* is the conservation
invariant as the audit object — and the ledger **cannot be the final witness that
it balances** (gate-bearing code doesn't testify on its own behalf).
Reconciliation is an absence-witness on a separate plane: "no unit in an
unexplained state, no duplicate live/spent assignment, no conservation breach
observed, window W, coverage C." And that coverage is only real if there's a
*single append path* — any side door (manual SQL, migration script, admin
rewrite, emergency fix) means the coverage field is fiat and must say so, because
the interesting breaches happen exactly where the witness is blind.

Quarantine ≠ destruction. Retroactive invalidity (a deposit made under standing
later discovered lapsed-at-deposit-time) needs a bucket. But taint *annotates*,
never *reverses* — units already spent from a tainted deposit get their exercises
annotated `funded_by_later_tainted_capacity`, not unspent. Clawback (destroying
live capacity) is a standing-gated authority exercise, not an accounting op.

The freeze queue is a shadow ledger — a second ledger in the basement, a
liability book of promises-to-spend with its own ordering and its own staleness
(the standing observations backing queued intents age during the freeze). Thaw
must **re-observe**, never replay frozen-era intents against thaw-era reality.
Refuse-during-freeze (typed as a *mode* refusal, so audits don't misread it as a
standing or capacity failure) is the clean MVP answer.

### The deferred organs (Fable's lifecycle scan)

The two that matter *now* (refusal already inexpressible): **retraction
transport** and **verdict seam**. Everything else waits for a forcing case.

Retraction: negative news has different transport semantics — a lost assertion is
missed work; a lost retraction is *unauthorized exercise*. Fan-out requires a
*reliance index* (who is currently relying), which nobody keeps. CRL-vs-OCSP is
the graveyard: revocation treated as an afterthought of the assertion system,
forever. The bounded-revocation-lag assumptions Standing and LA already lean on
have **no mechanism underneath them.**

Verdict: "verdict = downstream, not witness-owned" has been doctrine since round
one — but downstream *where*? If the layer that consumes receipts and renders
judgment (acceptable gap, sufficient coverage, taint disposition, thaw approval)
is uncustodied, the whole apparatus is immaculate evidence terminating in an
unaudited judge. AG is enforcement, not adjudication. Either mark the seam
("verdicts exit the custody domain here") or build a component whose receipts are
judgments. The unmarked third option is the rot.

Restore-from-backup is the apocalypse-with-no-liturgy: a registry restored from a
3-day-old snapshot doesn't create *one* open-world lapse, it time-travels an
entire authority's ledger — invalidating coverage claims, absence testimony, and
model-age fields across every component that observed it, *simultaneously*. Needs
restoration-as-typed-fiat-event: epoch increment, blast-radius declaration, every
dependent coverage claim marked discontinuous.

Schema evolution is the same conversion doctrine one level up, operating on the
*historical evidence base itself*. The bad move is silent defaulting (v1 lacked X;
v3 requires X; consumer invents `X="unknown"`; downstream treats unknown as
acceptable) — the no-unifier violation eating its own records. Migration of
historical receipts is mass conversion → wants mass receipts.

---

## The operator's framing (why this isn't just caution)

Recorded because it reframes the relay caveat correctly:

- These are *the operator's* Claude and ChatGPT — months in the ecosystem, the
  papers, the Lean kernel. If it's slop, it's *high-quality, me-flavored slop*
  that converged with where the design was already going.
- The standing design bias is **fail-closed**, which means the team tends to
  **over-conservative** design and implementation — that has been a real problem.
  So part of the job of this material is to **release the brakes a little**: the
  zoning is permission to *recognize* surfaces early, not a moratorium.
- The relay caveat is therefore a *promotion gate* ("wants a non-relay pass before
  it binds"), not a quality verdict and not a reason to compress the specimens out
  of existence. Scout the land so you can lay foundations / set zoning — that was
  the operator's frame, and it's the right one.

---

## Caveats (kept, because they're true)

- **Relay, not corroboration.** Two models, shared aesthetic. The internal
  Fable-vs-ChatGPT adversarial pass is necessary but not sufficient — it's two
  hats critiquing the third inside the same aesthetic. Wants one genuinely
  outside pass (operator, or `codex-exec` framed to refute, grounded in
  `file:line`) before anything here is promoted to binding doctrine or a filed
  spec. The unresolved UTXO-cost dissent is the first thing that outside pass
  should be mean about.
- **Ownership stays put.** Witness grammar is NQ's. Standing semantics are
  `~/git/standing`'s. Capacity internals are `~/git/linearaccountant`'s. AG
  records the scouting; it does not ratify or rename those surfaces (cf.
  `memory/constellation_constraint.md`: local grammar > shared vocabulary).
- **Not specs, not components.** Nothing here is authorized. Reserved candidate
  names live in the placard; filing any as a full gap spec, or building any
  organ, gates on a forcing case per `~/.claude/CLAUDE.md` § YAGNI scope.

---

## Second-round excavation (2026-06-11 appendix — Notary / transport / reflex / instrument)

The operator's "first pass" appendix to endgame. The recap front-matter is already
captured above; these are the genuinely-new bones. (A second pass follows; a third
confound may still surface.)

### Throughline extension

The instrument turn is the same throughline arriving at its destination: once the
apparatus is instrument-grade, the doctrine stops *arguing* and starts *showing*.

> **The apparatus exists so that refusals are expressible and conversions are visible.**
> Once instrument-grade, it stops sounding like philosophy and starts sounding like
> **incident review with better nouns** — which, annoyingly, may be the whole genre.

The new domains (logs, transport, real-time) each got answered by the *same* move:
find the silent conversion, name it, make it refuse. Logs: self-report → observation.
Transport: claim-exchange → shared residence. Real-time: don't make the apparatus
faster, pre-position the authority. None minted a new primitive except Notary, and
Notary only because it had a refusal nothing else could speak.

### Keeper phrases (new)

- *Fast systems don't make fast decisions; they execute slow decisions quickly.*
- *Log admission happens at sealing time, not reading time.* (custody cannot be
  retrofitted; later promotion of an unsealed line is laundering)
- *The index is never the evidence; the sealed segment is.*
- *State crosses boundaries as claims, never as shared residence.*
- *The broker may deliver bytes; it may not provide custody.*
- *NQ testifies about events; Notary notarizes continuity.*
- *Capacity is the leash on autonomy* — the reflex can't run away because it runs out.
- *You verify the box, not the decisions* (Simplex / runtime assurance).
- *An instrument doesn't argue — it shows you.*

Funny-but-load-bearing (new):

- *Congratulations. You invented a log system by refusing to build a log system.*
- *Toddler with scissors, but the scissors are foam and the room is padded* — the reflex envelope
- *Gravity is a demanding product manager* — why aerospace got to runtime-assurance first
- *Cohabitation with no lease and a suspicious smell from the crawlspace* — shared mutable Redis state
- *Tiny little bureaucrat with a hash chain and no dreams* — Notary's scope
- *Finally, one thing not demanding a constitution, a blood oath, and a small notarized skull* — the transport pipe
- *If it acts, call a priest* — the last line of Notary's anti-scope-creep label
- *Vibes with JSON* — trusting a parsed Elastic field as evidence

### Ugly state names / fields (new — keep spiky)

```
basis: unwitnessed_self_report     # the action receipt for log-triggered automation that skipped promotion
custody_class: diary_grade          # logs before promotion; the lower evidence class
sealed-silent over stream/window    # the honest "no error logged" — bounded, not global
promotion_status: not_promoted
coverage_basis: declared_not_enforced ; side_paths_possible: true   # (shared with LA reconciliation)
# reflex plane:
reflex_disarmed | reflex_budget_exhausted | reflex_rule_expired
trigger_unpromoted | confession_deadline_missed | revert_deadline_missed
mode: disarmed                      # frozen reflex plane refuses; does not queue
# notary segment skeleton (the custody object — NOT the corpus):
segment_id, producer_id, stream_id, first_seq, last_seq, prev_segment_hash,
segment_hash, sealed_at, clock_basis, line_count, byte_count, gap_state, storage_uri
```

### Anti-smoothing pairs (new)

```
bad:    no error logged → therefore nothing happened
better: segment S covered stream X T1..T2, seq N..M continuous, sealed at T3,
        no match in verified segment bytes → sealed-silent over declared window

bad:    Elastic field says user_id=123, therefore evidence
better: query index → retrieve raw segment → verify hash + chain → extract original
        bytes → then promote the line as claim evidence (index is a finding aid)

bad:    log says disk full → remediation deletes files
better: action receipt carries basis: unwitnessed_self_report, custody_class:
        diary_grade, promotion_status: not_promoted (or route through promotion first)

bad:    two systems share a Redis key ("exchange")
better: WLP claims over Redis-as-transport (the pipe may lie; the endpoints receipt)

bad:    queue ack = the exercise completed
better: ack is delivery, not custody; completion is its own receipt

bad:    make the apparatus fast enough for real-time
better: arm slowly (full custody), act quickly (reflex), confess on deadline,
        expire by default, escalate on budget exhaustion
```

### Rejected / tempting-wrong designs (new catches)

- **"Give logs to NQ as many tiny alerts."** Refused: blends two witness moments
  (alert-at-emission vs log-at-seal) and two integrity primitives (item authenticity
  vs continuity) into one component. The operator's hesitation to hand it to NQ was
  the right call. (Operator caught it; Fable confirmed the shape.)
- **"log-witness as a new witness kind."** Refused: it's not a witness kind, it's a
  new *seam* — a promotion gate at the locker's edge. The atoms are all existing NQ
  competences (temporal_order, absence_in_window, identity_binding); only the
  boundary is new.
- **"Trust the parsed/indexed document."** Refused: grok/field-extraction/coercion/
  truncation make the indexed doc a derived post-seal artifact. Verify raw segment.
- **"Redis as shared mutable state."** Refused: the implicit pool reintroduced one
  layer up — a free-standing bridge with a Redis key for a name. Redis-as-transport
  is fine; Redis-as-shared-memory is the custody basement.
- **"FastWicket™ / make adjudication fast."** Refused: you don't make the apparatus
  faster, you pre-position the authority. Adjudication moves to design-time; runtime
  carries no judgment, only execution of pre-rendered judgment. The constellation
  answered the real-time wildcard *compositionally* — no new organ. That's the
  load-bearing test passing.
- **Standing lease for the reflex** (the 2am temptation, again): a lease is still a
  standing-shaped object with its own lapse. The reflex's leash is *capacity
  exhaustion + default-revert expiry*, not a frozen standing token.

### Per-organ excavation (new)

**Notary.** The store-side transformation goblin is the place to be rudest to
Elastic: parsed fields, indexed documents, labels, coerced/truncated values are all
derived artifacts post-seal. Loki maps cleaner (stores the raw line with labels
bolted on; its chunk model rhymes with segments) but the zoning reg is one line
either way: *the index is never the evidence; the sealed segment is.* The elegant
bonus: gaps become **detectable absence** that falls out of the chain integrity for
free, instead of a bolted-on coverage claim. And the retrospective trap: a log sits
inert for months then gets promoted to evidence in an incident review — if the
segment wasn't sealed contemporaneously, that promotion is laundering. *Admission at
sealing time, not reading time.* Custody over the spine, not the corpus; the bulk
stays in cheap swappable storage where it belongs.

**Transport.** The end-to-end argument (Saltzer 1984) is the whole justification:
custody at the endpoints (WLP), the pipe allowed to lie. Rabbit at-least-once and
Redis best-effort are *different lies*; WLP is indifferent to which it rides. The one
hand to keep on the wheel: "exchange" hides two custody classes — claim-travel
(fine) vs shared-residence (the pool again). The reward for getting it right: vendor
swap stops being a custody event; the broker is plumbing.

**Reflex.** The composition is almost smug: Standing pre-grants, LA bounds blast
radius (capacity = leash), Expiry auto-reverts (default-revert: failure mode is
"stopped," not "ran forever"), Absence-witnesses police the confessions (missing
receipt = the alarm), Freeze disarms (mode: disarmed, no queue). DDoS is the perfect
specimen because overblocking legit traffic is how mitigation *becomes* the attack —
default-revert is the difference between a hiccup and a self-inflicted outage.
Aerospace got here first (Simplex/runtime-assurance) because gravity is a demanding
product manager: verify the envelope, not the controller's wisdom.

### Confounds on record

1. **Witness competence has a live downstream consumer.** `~/git/nq-root/nq-security-witness`
   was started and *then* these witness-competence decisions landed — so that doctrine
   reshapes an already-built component. Operator's read: "not wasted work, changes the
   shape." NQ-side; AG records the pointer only.
2. **This is the first pass.** A second appendix follows once this is in; a possible
   third confound is still to be dug up. The placard and this file are open for at
   least one more round.

---

## Pointer

Placard: `docs/constellation-zoning.md` (curated map, navigable, also PROVISIONAL).
Kernel it sharpens: `working/directional-invariants.md` (invariant 1),
`docs/agent-governor-meta-plan.md` (planes), `working/endgame-synthesis-2026-06-10.md`
(genesis-class rule). LA packet boundary: `working/linear-accountant-handoff.md`.

> Keep the placard for the map. Keep this for the bones. The placard tells you
> where the seams are; the bones are where the evidence that they're real lives.
