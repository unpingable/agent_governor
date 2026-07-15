# Candidate — constellation composer (demo-able specimen, not composer product)

**ID:** `constellation-composer-specimen`
**Filed:** 2026-07-15 (operator: "pencil this in lightly")
**Status:** **CANDIDATE — named, not ratified.** Filing is a handle for
review, not authorization to build. In particular this does NOT amend the
ratified public-mvp campaign envelope; whether it joins the launch DoD is a
separate operator ratification.
**Theory in progress:** `~/git/skunkworks/ux-design/` (codex-authored:
`constellation-composer-witness-ux-2026-07-15.md`,
`IMPLICIT_SCOPE_AUDIT_2026-07-15.md`,
`ux-scope-kernel-throughlines-2026-07-15.md`) — external drafts, candidate
input, no authority.

## The thesis (why this is launch-shaped and not procrastination)

The MVP story today: *"here are several governed components and some
carefully curated demonstrations."* The missing premise: **these tools do
not operate over "the enterprise"; they operate over an explicitly composed
and governed system model** — and that composition currently lives only in
the operator's head and repository doctrine. The audience lacks the
instrument needed to see that the existing tools belong to one system. The
composer is that instrument:

> Here is the system boundary they jointly reason about, and here is how an
> operator declares it.

## The fence (load-bearing)

**Demo-able composer, not composer product.** For MVP it needs exactly:

1. declare a bounded system scope;
2. place components and typed relationships;
3. distinguish observed facts from operator assertions;
4. show authority/evidence/custody boundaries;
5. export a stable machine-readable specimen consumable by one or two
   existing tools;
6. visibly refuse under-specified or contradictory scope.

It does **NOT** need: discovery, reconciliation, live inventory sync, graph
editing worthy of actual CAD, NetBox integration, collaborative state, or a
generalized schema marketplace. That way lies another quarter.

Item 3 is the constellation's own law surfacing in the UI (observed facts vs
operator assertions = testimony vs standing); item 6 is admissibility as UX
(a composer that renders contradictory scope without refusing would be the
first constellation surface to launder). Item 5's export specimen is an
architectural surface (wire format / cross-tool vocabulary) — per YAGNI
scope it gets named early and designed under review, not improvised.

## The demo shape (brutally constrained)

Load one prebuilt "Trek-scale deployment" specimen → alter a boundary or
authority edge → show how NQ/Maude/Nightshift's answers **change — or refuse
to change**. A demo with a thesis, not another dashboard wearing epaulettes.

Guvnah variant of the same beat: load specimen constellation → inspect and
edit one boundary → ratify the change → show downstream consequence/refusal
in another tool.

## The guvnah pivot (candidate identity resolution)

Guvnah becomes **the operator's system-modeling seat**, not another
governor — "a bigger pivot than what I did to maude":

- **Composer declares the system** — components, boundaries, relationships,
  scopes, authority domains.
- **Guvnah is the human-facing chair** where that model is reviewed, edited,
  challenged, and ratified.
- **AG remains execution governance.** **NQ interrogates the declared
  system.** **Maude turns bounded intent into plans against it.**
  **Nightshift operates over the same declared scope after hours.**

The chair's object of work is **the constellation model itself**: *"This is
the owl. These are its edges. These are the parts that count. These are the
claims I'm willing to stand behind."*

**Recorded tension, not resolved here:** Q-A7 (2026-07-02) ruled guvnah v1
RETIRED (specimen only); `guvnah-v2-operators-chair` sits queued post-launch
as a vague console concept. This pivot would re-scope v2 around a concrete
object. Whether that is a v2 re-scope or a fresh surface is an operator
ruling at pickup time; nothing in this filing amends Q-A7.

## Delivery surface — open question (operator noodling, 2026-07-15, same day)

Operator: guvnah "might want to be both app + web (chrome+firefox support) —
right now I think I was focused on app." Plus: "what to do with govwebui and
clerk, if anything" — and, rediscovered mid-thought, the VS Code extension.

**The full human-facing surface inventory** (the operator's own head dropped
one — which is this candidate's thesis demonstrating itself):

| Surface | Substrate | Standing ruling (2026-07-02, `docs/roadmaps/CONSOLIDATION.md`) |
|---|---|---|
| maude | terminal TUI | KEEP — terminal-native operator shell (live, proven by NS-1) |
| gov-webui → **phosphor** | web | KEEP + REFRAME — web-native lane host (ops-casework lane = near-term cockpit) |
| clerk | Electron | parked assistant shell (kept, inactive) |
| guvnah v1 | Electron-ish/stdio | RETIRE (Q-A7 — "premature surface area") |
| vscode-governor | editor extension | separate repo; `docs/CLIENT_ECOSYSTEM.md` narrative STALE (census D3) |

**The substrate question for the seat, unruled:** if the chair wants
app + web, note the constellation already owns (a) a ruled web-native host —
phosphor, where chrome+firefox support is free because it's just the web —
and (b) a parked Electron shell — clerk — that is the obvious app-shell donor
if a desktop app is genuinely needed. Candidate shapes, none ruled:

1. **Seat as a phosphor lane** (web-first; cheapest; both browsers free;
   clerk stays parked; "guvnah" survives as the lane's name or not at all).
2. **Seat as resurrected guvnah app** consuming the same model; web later —
   re-opens Q-A7 and doubles the surface early.
3. **Both as two parallel builds** — the "another quarter" fence says no.
4. **Guvnah as one codebase, two distributions** — web-native core serving
   a webui (chrome+firefox free) AND wrapped in an app shell.
   **← OPERATOR LEAN (2026-07-15, same day; a lean, not a ruling).**
   Distinct from shape 3: this is one surface rendered twice, not two
   surfaces — so it survives the fence IF the core is genuinely web-first
   and the app shell is a wrapper, never a fork. Consequences to rule at
   ratification: (a) **clerk's app-shell-donor role evaporates**, but its
   disposition stays "parked, kept" — operator provenance (2026-07-15):
   clerk was a POC for governed chat, an early MVP-demo idea from before
   the realization that "I was building a platform, not a bunch of random
   tools"; "maybe it finds another use later." Historically load-bearing
   (the artifact the platform lesson was learned on), not
   retirement-leaning; no consolidation-table change needed;
   (b) **phosphor stays purpose-focused on what it does now**
   (operator, same exchange) — web-native lane host, ops-casework lane; the
   seat is a sibling surface, not a phosphor lane, and no shared-hosting
   arrangement is contemplated; (c) the demo-able MVP specimen should ship
   as the WEB rendering first (zero install for the launch audience), app
   shell after — the shell is distribution, not product.

Whatever the ruling, the daemon-authority invariant is unchanged: clients
are views; the composer MODEL and its export specimen are the product, and
they must not care which chrome renders them. Deciding the model/specimen
first makes the substrate question cheap; deciding substrate first makes it
expensive. `CLIENT_ECOSYSTEM.md` (already marked STALE) is where the
eventual ruling should land, not new prose here.

## Category note — "CAD for operational systems" (operator + chatty, 2026-07-15, same day)

Operator: "I'm basically pulling ops-work into the kind of context-heavy
engineering that actual formal engineering disciplines use — using CAD as a
point of reference is basically not an exaggeration." Chatty concurred: the
category holds because the composer would do what real engineering tools do —
authored model distinct from observed reality; constraints/interfaces/
tolerances/admissible transitions; compile to consumer-specific artifacts;
detect invalid structure pre-deployment; intended-vs-measured comparison;
revisions/cuts/provenance; changes legible in downstream consequences. The
pipeline: `design model → validation → ratified revision → compiled
projections → realized system → inspection evidence → deviation analysis`.
Not merely infrastructure CAD — the modeled object includes authority,
identity, topology, dependencies, evidence requirements, operational
boundaries, degraded states, permitted effects, unresolved obligations.
Candidate deeper category: "systems assurance CAD" / "operational systems
engineering workbench"; the CMDB contrast ("here are some records about
things" vs "here is the governed design, the witnesses competent to measure
it, where measurement diverges, and the consequences of change"). From
folklore ("Dave knows that tag means production except the old cluster") to
engineering ("asserted in revision R, validated under constraint set C,
projected to NQ as P, contradicted by witness set W").

**AG-side observation (drafter): the constellation already built the verbs;
the composer is only the missing noun.** Authored-vs-observed = the
facts/decisions split (day-one NLAI) + origin_mode + external attachment;
constraints/transitions = the FSMs + standing validator + closed
vocabularies; compile-to-artifacts = claimc / NS-5 exporter /
state_index_export; pre-deploy structure check = admissibility/preflight/
wicket; intended-vs-measured = NQ witnesses + drift/staleness (the
2026-07-15 six-axis audit's prose-vs-stub divergence WAS deviation
analysis); revisions/provenance = supersession ceremony + S6
successor-not-revision + append-only dispositions. **The usual CAD
inversion:** in MCAD the geometry kernel was the hard part and constraints
came a generation later; here the constraint kernel is built (16,996 tests)
and the geometry/topology model is the easy part — which is why the six-need
fence is credible.

**Closer cousin: EDA, not MCAD.** DRC = the composer refusing contradictory
scope; tape-out ceremony = ratification/minting; **LVS
(layout-versus-schematic) = declared model vs witnessed reality WITH a
refusal verdict** — "the measured system diverges from revision R" is an LVS
failure, and the discipline that failing LVS means you don't ship is the
cultural import.

**Vocabulary hygiene (pencil line):** CAD is the outward CATEGORY, never the
wire vocabulary. The export specimen speaks constellation grammar
(admission, custody, witness, standing); "CAD"/"assurance workbench" stays
on the positioning layer. Local grammar > shared vocabulary — conceptual
dependency on the analogy is the named failure mode.

## Enforcement is claim-relative, not domain-relative (2026-07-15)

**A drafter error, corrected and worth keeping as the correction.** The
drafter proposed `domain → witness strength` ("ops and code can gate;
authoring can only advise"). Chatty refuted: **witness strength is
claim-relative.** Code has weak witnesses (tests can encode the same mistaken
assumption as the implementation; snapshots prove consistency with yesterday,
not correctness; typecheck proves what the type system expresses; a Lean
theorem proves the stated model, not that the model describes the intended
world). Authoring has hard ones (cited text exists at the claimed location; a
date contradicts an established timeline; a character is in two places; a
quotation differs from source; a required disclosure is absent). Only the
*semantic* claims — "this motivation is believable", "this argument follows",
"this voice is consistent" — are testimony-typed.

**The repo already knew this; the drafter was behind the code** (verified
2026-07-15):

- `libs/receipt_kernel/.../oracle_independence.py` grades witnesses on an
  independence ladder: **0 local same-host (e.g. pytest on the dev machine)
  → 1 same-org CI → 2 cross-org CI → 3 independent third-party.** Local
  pytest is the WEAKEST class — the "code gates" intuition graded by the
  kernel itself.
- `claims_evidence_binding` binds evidence **per factual claim**;
  `epistemic_mode_requirements` gates by mode. Claim-relative enforcement is
  already constitutional.
- Authoring hard witnesses already ship: `nonfiction_governor/doi.py`
  (citation exists at claimed location, CrossRef/DataCite),
  `governor/chrono.py` (dates), `governor/identity.py` (names),
  `fiction_governor/guardrails.py` (**C1–C3 hard constraints** vs **P1–P4
  soft penalties** — fiction already splits gate-able from advisory).

**Determination shape (candidate, NOT built):**

```text
claim kind + witness bundle + independence + coverage
+ reproducibility + authority + consequence class
    → permissible enforcement
```

Candidate closed vocabulary — **name only; minting it is custody-affecting
(cross-module vocabulary) and needs its own ruling**:

```text
EnforcementClass = DescriptiveOnly | Advisory | RequiresReview | Blocking
```

**Earned per compiled claim, never assigned wholesale to a domain.** Same law
as the week's other three closures (novel string ≠ new mode; novel value ≠
new state; skew ≠ stale): the class is derived from evidence, not declared by
category.

## Three-layer split (candidate architecture — resolves phosphor)

- **Composer** — declares entities, relations, constraints, claims, witness
  requirements, cuts, projections. Domain-neutral kernel.
- **Domain packs** — local ontology + admissible witness types per domain
  (ops, code, fiction, nonfiction). This is `local grammar > shared
  vocabulary` applied: the kernel stays neutral, each pack keeps its own
  grammar. See `constellation_constraint` doctrine.
- **Phosphor** — hosts the human workflow: lanes, inspection surfaces,
  drafting, review, ratification, consequence display. **The workbench over a
  model-and-witness kernel** — not "the universal framework for every kind of
  thought". This salvages phosphor's generality claim by removing it: it
  renders lanes; it never carries the kernel's domain-generality.

So fiction is not a tab bolted onto an ops product:

```text
Composer model kind: narrative continuity
Phosphor lane:       fiction casework
Witness pack:        manuscript + canon + timeline + human review
```

```text
Composer model kind: software artifact
Phosphor lane:       implementation casework
Witness pack:        compiler + tests + verifier + repository history
```

## Fiction is state-tracking, not taste (operator + chatty, 2026-07-15)

Operator (from Erin's complaint about ChatGPT/Claude losing canon while
drafting): "there are STILL hard constraints in fiction." Chatty: losing canon
is **not a taste failure, it is a state-tracking failure** — and *"Claude
deciding a character suddenly knows something they never witnessed is
basically an unauthorized projection across an epistemic boundary. Same
crime, nicer prose."*

**That is this constellation's core crime exactly** — assertion converted to
relied-upon fact with no witness path. A character's knowledge state is
standing; witnessing an event is the evidence; inferring knowledge without a
transmission path is laundering. The fiction governor's job and AG's job are
the same job.

Hard state a story carries: who knows what and when; who is alive, present,
injured, married, missing, lying; dates, distances, travel time, ages; object
custody; established world rules; POV visibility; promises made on-page;
whether a reveal contradicts prior text or merely recontextualizes it.

```text
hard constraint:     Character A was not present for event X.
derived constraint:  A cannot know X unless a transmission path exists.
soft judgment:       Would that path feel dramatically satisfying?
```

First two gate; the third needs human review. So a fiction model is not "a
bible" — it is `entities + temporal state + knowledge state + relationship
state + world constraints + textual evidence + unresolved obligations`, and
the tool can then classify: **contradiction** (violates canon) ·
**unsupported addition** (no textual basis yet) · **legal extension** (new,
consistent) · **interpretive ambiguity** (multiple readings) · **style
concern** (advisory only).

Erin's complaint is the authoring-domain equivalent of *"the dashboard was
green but the service was dead."* Different scenery, same missing discipline.

**And the fiction pack largely exists already (verified 2026-07-15 —
completion-redshift, fifth instance today).** `fiction_governor/types.py:595`
`Belief` already carries `character` · `belief` · `is_true` (world truth vs
character belief — the epistemic split) · `learned_at_chapter` (temporal
index) · `source` (**the transmission path**: "witnessed" / "told by X" /
"assumed") · `invalidated_at_chapter`. Its docstring: exists to catch
"impossible reactions, **premature knowledge**, and emotional responses that
assume facts not yet learned." The hard/derived ladder above is already
schema; `bible.py` is the decisions ledger and `canon.py` the facts ledger.

The real gap is two small things — **and it is this week's law a fifth
time**: (1) `source` is a **free-form string** (`types.py:620`,
`cli.py:1875`) where a closed vocabulary belongs — `TransmissionPath =
Witnessed{event} | ToldBy{character, scene} | Inferred | Assumed`; (2) **no
interlock** validates `source="witnessed"` against canon presence (verified:
zero matches). Fiction has the schema and not the gate. That is a closed
vocab + one verifier, not a subsystem — which is more evidence the
domain-pack layer is a re-labelling of what got built, not a new build.

Operator disposition (2026-07-15): **fiction is NOT deprecated** — "Erin
still wants a fiction authoring tool; even if that's not front-and-center,
I'm not deprecating it." A named live consumer is a forcing case in waiting;
a future audit must not retire the module for being off the ops hot path.

## Why ops is still the launch domain

Not because the kernel is secretly ops-only — because ops is the best **stress
test**: richest mix of authored design, heterogeneous external witnesses,
consequential disagreement, authority boundaries, and real refusal value.

**Generality stays an architectural fact, never a homepage claim.** Let people
notice the same machine governs code and authored corpora *after* they have
seen it do something difficult and concrete. Otherwise you become "a platform
nobody asked for, now featuring four pastel tabs."

## Sequencing rule — prove neutrality, never declare it (2026-07-15)

Operator reached for "phosphor updated for all domains"; withdrew it
unprompted ("I got greedy with 'all domains'. It's just that coding is also
important, but that deserves its own slice"). Chatty's statement of the rule:

> Domain-neutral kernel does NOT mean one universal slice with a dropdown.
> **Prove domain-neutrality by building multiple narrow slices, not by
> declaring it.** Abstraction after the third instance.

```text
shared composer kernel          NOT:  all domains
    ├── fiction slice                     └── generic metadata soup
    ├── code slice
    └── research slice
```

Each pack: its own ontology, witness pack, refusal semantics, UX. Sketched
(candidate stubs `composer-pack-code`, `composer-pack-research`):

| pack | local ontology |
|---|---|
| fiction | canon state · character knowledge · chronology · object custody · POV boundaries · hard continuity constraints · soft narrative penalties |
| code | source/artifact identity · build graph · specification and invariants · compiler/test/verifier witnesses · dependency and version constraints · change impact · release authority |
| research | claims · sources · citation location · evidentiary support · methodological constraints · competing interpretations · retraction/supersession · confidence and unresolved questions |

**Instance 1 is BUILT (fiction, 2026-07-15):** `fiction_governor/knowledge.py`
— closed `TransmissionPath` + `KnowledgeVerifier` adjudicating belief paths
against canon presence and chapter order. Erin's canon-loss failure is now a
typed finding. Instances 2 and 3 are named, unbuilt, and each needs its own
forcing case. **Only after three does extraction of what genuinely repeats
become admissible** — and the fiction build already suggests what will
repeat: a closed path/basis vocabulary, a presence-or-equivalent check, and
the gap-vs-violation split.

Note the fiction slice needed **no new UI at all** — which is the sequencing
rule paying immediately: the gate is the product; phosphor renders it later,
if ever.

## Gates before any build

1. **Operator ratification** of scope + whether it enters the launch DoD
   (the six-needs list above is the candidate boundary).
2. **Hostile-to-features review of the MVP definition** before slice 1 —
   operator's own warning: "you will enjoy building it far too much."
   Adversarial pass on the SPEC, not just the code.
3. Export-specimen schema named as its own reviewed record (candidate wire
   format; consumers: pick 1–2 of NQ/maude/nightshift, not all).
4. Read-only first; "minimally editable" only if the demo beat requires the
   ratify-a-boundary step.

## Non-binding sequencing sketch

Sits AFTER the current operator remainder (push window, launch acts, NS-2
run) and composes with — possibly replaces the front of — the quarantined
demo-2 arc. It does not gate NS-3..6.
