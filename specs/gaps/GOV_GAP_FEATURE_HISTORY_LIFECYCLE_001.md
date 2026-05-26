# GOV_GAP_FEATURE_HISTORY_LIFECYCLE_001

Status: draft
Owner: Governor
Type: hygiene / documentation-substrate gap
Drafted: 2026-05-26
Closure condition: built-in (see §10)

## 1. Problem

`.claude/rules/feature-history.md` is a monotonic additive log. Nothing
ever leaves it. Features are appended as they ship; supersession
relationships are sometimes noted inline; retirement is never recorded.

The visible symptom is sprawl — the file has accumulated 100+ entries
and continues to grow. The symptom invites a reorg reflex (move things
around, tighten the prose, add headers).

The disease is structural, not cosmetic: **there is no retirement
signal**. Without one, "the file is long" and "the file is current" are
indistinguishable from the inside. An outside reader cannot tell what's
load-bearing now from what was load-bearing at some point. An inside
reader (this Claude, a fresh session) can recover the answer by reading
the code, but the file itself has stopped doing the work its index is
supposed to do — pointing at what matters *now*.

This is the same shape as the gap-naming-without-gap-closing pattern:
naming is a good working tool and a terrible deliverable unless a
closure mechanism exists. `feature-history.md` is the dual case —
shipping is a good working signal and a terrible filing rule unless a
retirement mechanism exists.

A reorg without a retirement mechanism produces tidy sprawl. Same
disease, more metadata.

## 2. Goal

Add a retirement mechanism to `feature-history.md` and run one focused
classification pass over current contents.

In v1:

- a forward-looking lifecycle taxonomy (bins) with stranger-classifiable
  criteria,
- a cheap operational retirement step (section break, not file split),
- a sample-then-execute discipline (criteria fixed before mechanical
  classification),
- one execution pass over current contents.

## 3. Non-goals

This gap does **not** propose:

- a project plan (this is a focused cleanup with bounded scope, not a
  project),
- a doc reorg beyond the section break (path-scoped rules +
  load-on-demand `feature-history.md` already do most of the legibility
  work for inside readers; the cold-visitor case is real but is a
  separate problem),
- promoting the lifecycle taxonomy to a typed receipt axis (see
  `[[altitude_axis_deferred]]` — existing primitives grip the relevant
  collapses),
- using the cleanup pass as a vehicle for an unwritten roadmap decision
  (see §8 honesty clause),
- using retirement as authorization for code deletion or doctrinal
  invalidation (see §7.2 retirement brake),
- lifting the discipline to NQ or other repos in this pass (deferred to
  §9; AG-first).

## 4. Core principle

**Name early. Ratify lazily. Retire operationally.**

The first two phrases are existing AG / global doctrine ("name early,
ratify lazily"). This gap adds the third because the AG-sprawl problem
shows what happens when only the first two are practiced: names
accumulate, ratification stays light, but nothing ever leaves, and the
substrate becomes a graveyard with no grave markers.

The failure mode this rule defends against: treating shipping as
permanent residency. A feature that ships is a feature that earned its
place in the load-bearing set *at the time it shipped*. Whether it
remains load-bearing is a separate question that the substrate
currently has no way to ask.

## 5. The three bins (forward-looking, trajectory-based)

The classification taxonomy is **trajectory-based**, not
state-based. State-based ("retired" / "load-bearing" / "questionable")
describes what each entry *is*; trajectory-based describes where each
entry *goes next*.

Initial bins:

1. **3.x platform** — items that are part of the platform / runtime
   governance direction. Not merely "next release"; specifically
   platform-as-service shape. Seed criteria in §5.1; criteria must be
   writable independently of reading `feature-history.md` (§6).
2. **current research** — items that are live exploration but not on
   the platform path. Includes load-bearing-but-questionable.
3. **candidate substrate** — items that exist as substrate for later
   promotion or absorption but are not currently on either of the above
   trajectories. (Previously phrased as "feature branch"; renamed to
   avoid Git-topology confusion — this is lifecycle posture, not
   branching strategy.)

Implicit fourth path: **retire**. Anything that fits none of the three
bins under stranger-classifiable criteria retires. Retirement is the
operational step that distinguishes this taxonomy from existing
state-based descriptions. Retirement is an *orientation signal*, not a
deletion instruction — see §7.2.

Promotion path: `current research` → `candidate substrate` → `3.x
platform`.
Retirement path: anything that drops out of all three.

## 5.1 Seed 3.x platform criteria

The criteria below were drafted **independently of current
`feature-history.md` contents**, seeded from prior AG roadmap context
(five-artifact runtime governance ontology, public gate /
Wicket-fixture discipline, 2.8.1 known-good → next-platform boundary).
They are subject to §6.2 sample testing before being treated as
ratified.

The framing: **3.x is platform / runtime governance, not "next
release."** Items in 3.x participate in AG operating as a durable
service.

### Include in 3.x platform if it satisfies at least one of:

1. **Live governance surface.** Directly gates, transitions,
   constrains, authorizes, recovers, supervises, or emits receipts at
   the daemon / RPC / hook / runtime layer. Analysis layers and
   voice/output constraints that *feed* governance but do not gate
   live activity belong to `candidate substrate`, not `3.x platform`.

2. **Five-artifact ontology participation.** Produces, consumes,
   validates, displays, or constrains one of: `MeasurementSnapshot`,
   `TransitionProposal`, `AuthorityReceipt`, `RecoveryPlanReceipt`,
   `ResetReceipt`.

3. **Public gate / fixture-reproducible boundary.** Candidate public
   AG gate whose behavior is demonstrable via Wicket-style fixtures
   and stable verdict mapping, or whose non-admissibility status is
   explicitly documented.

4. **Service/platform operation.** Supports AG as a durable service
   rather than a local experiment: daemon behavior, session
   supervision, tool interception, custody scoring, regime detection,
   override handling, hysteresis, sunset clauses, scar tissue,
   vocabulary drift, claim diffing.

5. **Known-good → next bridge.** Required to move from the 2.8.1
   known-good bundle into the next coherent platform shape.

### Live-wiring qualifier

**Offline-analysis features** (e.g., trace analysis, system
identification, signal discovery with proposal output) classify as
`current research` unless they are wired into live platform behavior
(auto-apply, runtime feedback loop, automatic receipt emission).
Productized CLI surface for an offline tool does not by itself
promote to `3.x platform`. The qualifier applies whether or not an
include criterion above otherwise fires.

### Exclude from 3.x platform if it is:

1. Interesting doctrine with no live governance surface.
2. A one-off exploratory feature with no live consumer.
3. A research probe whose value is conceptual rather than
   platform-operational.
4. A legacy implementation detail superseded by newer primitives.
   *(Per §7.2, supersession-driven retirement is a separate decision;
   this criterion fires only when the entry has no live consumer at
   HEAD. Possible-supersession alone does not justify exclusion from
   the bin assigned by criteria.)*
5. A feature that only matters because `feature-history.md` remembers
   it. (This last one is the knife. If the only argument for inclusion
   is "we built it and wrote it down," it is not 3.x.)

If §6.2 sample classification shows these criteria do not survive
edge cases, re-cut before executing. If criteria cannot be drafted
independently at all — i.e., if every candidate criterion collapses
to "the stuff in `feature-history.md` that feels shippable" — §8
fires.

### Sharpening provenance

The "live governance surface" wording (include 1) and the
live-wiring qualifier above were added 2026-05-26 after §6.2 sample
classification surfaced edge-case ambiguity on Puppet Mode,
Interferometry, and Convergence Auto-Tuning. Sample classification
recorded at `working/feature-history-sample-classification.md`. The
original criterion text (less specific "live governance of activity,
transitions, tools, sessions, overrides, leases, recovery, or
containment state") classified the obvious anchors cleanly but
handed off too much judgment to the classifier on middle-layer
features. Sharpening narrows the cut without changing the bin
taxonomy.

## 6. Discipline tests

### 6.1 Criteria-first

The 3.x criteria must be drafted **before re-opening
`feature-history.md`** for the classification pass. If criteria are
written after surveying current contents, they reverse-engineer from
existing entries and the stranger-classifiability test is undercut.

The honest version of this discipline: if the criteria-first pass
reveals that "3.x" cannot be defined independently of what's in the bin
("3.x is the stuff that feels shippable"), then the cleanup pass has
correctly surfaced that **3.x is currently undefined** — and the gap
doc records that finding and the cleanup pass is blocked pending a
roadmap decision elsewhere. Do not smuggle a roadmap decision through
cleanup work.

This is the load-bearing test. The other two are easier.

### 6.2 Sample-then-execute

After criteria are drafted, classify 5-10 sample entries to test the
criteria against edge cases **before** committing to the criteria across
all current entries.

Sample selection is **deliberately edge-loaded**, not random:

- oldest entries (Phase 1-3 build-spec items),
- newest entries (Standing C1-C5),
- genuinely ambiguous items (candidate list: Puppet Mode,
  Interferometry, Convergence Auto-Tuning, Boil Control — items
  where the bin is not obvious on inspection).

Random sampling mostly hits unambiguous cases and produces
satisfying-feeling validation without stressing the criteria. Edge-case
sampling finds the weaknesses before commitment.

If the criteria collapse on samples, re-cut criteria. If they hold,
proceed to execution.

### 6.3 Mechanical execution

Once criteria pass sample testing, the execution pass is mechanical —
the judgment happens once (in the criteria), not 100+ times (per
entry). If the execution pass starts feeling like fresh judgment per
entry, the criteria didn't hold and the discipline has slipped; stop
and re-cut.

## 7. Retirement operation (v1)

### 7.1 Mechanism

Cheapest reversible option: **in-file section break**.

`feature-history.md` gains two top-level sections:

- `## Live` — items in one of the three bins (3.x platform / current
  research / candidate substrate).
- `## Retired` — items that fit none of the three bins.

Retired entries carry a retirement header with a closed-ish reason
prefix:

```
### Feature name [RETIRED YYYY-MM-DD: REASON_PREFIX — optional short note]
```

Closed-ish reason vocabulary (extend deliberately, not casually):

- `SUPERSEDED_BY: X` — explicit successor exists.
- `ABSORBED_INTO: Y` — folded into a larger feature, no longer a
  separate entry.
- `NO_LIVE_CONSUMER` — code may exist but nothing depends on it.
- `EXPLORATORY_ONLY` — built as a probe, never promoted to load-bearing.
- `ROADMAP_DROPPED` — explicit decision elsewhere to drop this
  direction.
- `DUPLICATE_OF: Z` — same surface as another entry, this one
  retired.
- `MOVED_TO_RESEARCH` — was treated as shipped, is actually live
  research; entry stays retired but the work continues under the
  research bin via a separate entry if appropriate.
- `UNKNOWN_AFTER_AUDIT` — could not be classified with confidence;
  retired pending re-audit.

Prefix is required. Optional note after `—` is free-form prose, kept
short. Pure prose without prefix is forbidden — prose-only rots and
the future sweep won't be grep-able.

The section break is preferred over file split (`feature-history.md` +
`feature-history-archive.md`) for v1 because:

- it is reversible — if a "retired" entry turns out to still be wired,
  promoting it back to `## Live` is a single edit;
- a file split is harder to walk back if mis-classification surfaces
  under wear;
- the path-scoped loading machinery already handles
  `feature-history.md` as a load-on-demand file, so size is not the
  primary concern.

Upgrade to file split is a v2 decision, deferred to evidence that the
section break does not compose.

### 7.2 Retirement is an orientation signal, not a deletion instruction

**Retirement does not imply code deletion or doctrinal invalidation.**

A retired entry may still describe:

- code that exists and runs,
- doctrine that mattered historically and may matter again,
- a feature that can be revived if the trajectory shifts,
- substrate that produced real insight even if it's not on the live
  path.

Retirement only means: **this is not part of the live orientation set
under the current trajectory criteria.**

This brake exists because "retired" is structurally tempting as a
sneaky authority operation — a way to declare something dead by
filing it. The retirement signal is *for orientation*, not for
permission to delete, invalidate, or override. Code-level decisions
about deletion or rewrite belong elsewhere (the codebase, separate
gap specs for specific superseded subsystems, scar/shield mechanics)
and are not authorized by the act of moving an entry into `## Retired`.

If an entry is retired and the underlying code should also go, that's
a separate decision recorded in a separate artifact.

## 8. Honesty clause

If the criteria-first pass (§6.1) reveals that "3.x" cannot be defined
independently of current contents, this gap is **not closed**. The gap
doc records the finding:

> "3.x criteria attempted; surfaced that 3.x scope is undefined;
> cleanup pass blocked pending scope decision."

The cleanup pass does not proceed. The gap doc converts from "cleanup"
to "roadmap-blocker-surfaced," and the unblocking work is the next
step — at which point criteria can be drafted honestly, the gap can be
re-opened, and the sample-then-execute discipline applies.

This clause exists because the cleanup pass is structurally tempting as
a vehicle for laundering a roadmap decision. The vehicle must be
explicitly refused.

## 9. Composition

This discipline is plausibly liftable to other repos (NQ has been
mentioned as sprawling similarly). Lift is **deferred** to:

1. Successful execution of this gap in AG.
2. Evidence that the same disease (additive log, no retirement signal)
   exists in the target repo.
3. Stranger-classifiable criteria for the target repo's bins (its
   trajectory taxonomy may differ from AG's 3.x / research / feature
   branch).

Promotion follows the standard pattern: do it once locally, see if it
holds, then lift the *invariant* (name early, ratify lazily, retire
operationally) — not the specific bins. NQ's bins will be NQ's.

See `[[global_doctrine_promotion_added.md]]` for the general
promotion-reduces-local-burden rule.

## 10. Closure condition (built-in)

This gap closes when:

1. `feature-history.md` has `## Live` / `## Retired` section break with
   retirement headers on retired entries;
2. the 3.x criteria are drafted, captured in this doc (§5), and have
   survived sample-classification on the §6.2 edge cases;
3. the execution pass has completed and all current entries are
   classified into one of the three bins or `## Retired`;
4. the closure commit links this gap doc.

The gap doc demonstrates the lifecycle it defines: it names the gap,
captures the criteria, holds the sample classifications, and *closes
itself* when the work commits. This is the self-application that
distinguishes it from gap docs that name indefinite gaps.

If §8 (honesty clause) fires instead, the gap converts to
"roadmap-blocker-surfaced" status and closure is deferred to the
unblocking work.

## 11. Acceptance criteria

Status: **met** (2026-05-26) pending closure commit.

1. ✓ Section break in `feature-history.md` with retirement headers
   carrying date + reason for each retired entry. *(Two retired
   entries: VS Code Extension, WebUI Backend Toggle, both with
   `ABSORBED_INTO` prefix.)*
2. ✓ 3.x criteria drafted in §5.1 of this doc, independent of
   `feature-history.md`'s current contents. Sharpened 2026-05-26
   after sample classification (see §5.1 "Sharpening provenance").
3. ✓ Sample classifications recorded at
   `working/feature-history-sample-classification.md`. Criteria held
   on 7/10 obvious anchors; sharpening resolved the 3 weak cases.
4. ✓ All 103 current `feature-history.md` entries classified: 83 in
   3.x platform, 4 in current research, 14 in candidate substrate,
   2 retired.
5. **Pending**: closure commit referencing this gap.

§8 honesty clause did not fire — 3.x criteria were stranger-
classifiable and survived sample testing with text-level sharpening,
not a recut.

## 12. Open questions

1. **Bin ordering within `## Live`.** *(Resolved 2026-05-26.)*
   - Chose **subgrouped** by bin (`### 3.x platform`, `### current
     research`, `### candidate substrate`). Within each subgroup,
     entries retain original chronological order. Legibility win
     outweighs the small additional structure cost.

2. **Retirement reason vocabulary.** *(Resolved in §7.1.)*
   - Closed-ish prefix vocabulary chosen (`SUPERSEDED_BY`,
     `ABSORBED_INTO`, `NO_LIVE_CONSUMER`, `EXPLORATORY_ONLY`,
     `ROADMAP_DROPPED`, `DUPLICATE_OF`, `MOVED_TO_RESEARCH`,
     `UNKNOWN_AFTER_AUDIT`), optional free-form note after `—`.
   - Open residual: whether the vocabulary holds in practice or
     accumulates rare-use prefixes that should be merged. Re-audit
     after execution pass.

3. **`feature-history.md` outside-reader case.**
   - The cold-visitor concern is real but is acknowledged out of scope
     in §3. A future gap may address `feature-history.md` legibility
     for outside readers (likely a 2.x problem — see external review
     framing). Tracked separately.

4. **Lift to NQ.**
   - Deferred to §9 conditions. NQ likely surfaces during its own
     cleanup attempt and the invariant gets promoted then, not now.

5. **Composition with `implementation-summary.md`.**
   - The boot index points at `feature-history.md` and acknowledges
     additive growth. After this pass, the boot index may want to
     update its pointer to call out the live/retired split explicitly.
     Cosmetic; defer.

## 13. Follow-up audits surfaced during execution

The execution pass surfaced two questions explicitly out of scope
for this gap, captured at the bottom of `feature-history.md` and
here for visibility:

1. **Boil Control supersession.** Classified as `3.x platform` by
   criteria; whether the entry is functionally superseded by the
   newer Regime/Ultrastability/Homeostat/Coupling family is a
   separate audit. Per §7.2, supersession is not authorized by bin
   assignment alone.

2. **Test infrastructure home.** Strategic Test Suites / QA Harness
   / Maude Contract Tests / Test Hardening all classified as
   `candidate substrate` because the bins have no native "permanent
   supporting infrastructure" category. If recurrent, the bins may
   want a fifth category or `candidate substrate` may need to
   explicitly include durable test/CI infrastructure. Re-audit if
   the gap pattern repeats elsewhere.

Several conservative classifications (Direction Tracking, Claim
Diff, Claim Signals, Tainted Claim Similarity → `candidate
substrate`) reflect uncertainty about whether their surfaces are
user-invoked or auto-fired at runtime. Promote individually if
grep confirms automatic firing.

## 14. One-sentence summary

`feature-history.md` is an additive log with no retirement signal;
this gap adds the signal, applies it once, and closes itself when the
cleanup commits.
