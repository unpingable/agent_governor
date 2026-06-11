# Launch & Demo Plan — the slab the demo sits on

**Status: internal planning, NOT published.** Owner: this Claude now holds the
documentation side (agent_gov docs + unpingable.com), replacing the separate
site-Claude that drifted out of sync. Public/private separation: this file is the
public-facing-but-unpublished *plan*; the personal/launch-psychology material from
the source conversation was deliberately kept out of git (operational distillation
in memory only). Provenance: operator + Claude Fable + ChatGPT relay — positioning
judgments are taste (relay caveat applies), but observables ("this README lacks a
worked example") are bankable: convergence on observables is cheap corroboration,
convergence on judgments is two hats.

## The gate — demonstrability, not completeness

> **One vertical slice that visibly refuses beats ten components that exist.**

Talk in earnest when a stranger can reproduce one end-to-end refusal in <15 min.
Outside humans are the **missing witness class** — by the project's own doctrine the
in-house interferometer (operator + models on overlapping training soup) is relay;
external hostile eyes are part of the apparatus, not a marketing phase. "Ready" is a
receding horizon; the grain-of-refusal rule applies to publicity too.

## The demo — one incident, three descents (Columbo, not Jobs)

The differentiator is **not refusal** (every linter / admission controller / RBAC
deny / CI gate refuses — "we built a thing that says no" is the least differentiated
claim in infrastructure, and Wicket+GitHub Actions already showed it). It is a
**contrast**: a refusal conventional stacks don't make *first-class*.

- **Act 1 — behavior.** A legitimate action traverses the full gauntlet and **passes**
  (receipts at every hop — a system that only says no is a brick). Then a
  *credentialed impostor* — valid signature, valid token, valid role, plausible
  operator/action, everything ordinary infra likes is green — is **refused**, the
  receipt naming the missing custody distinction (signed-but-not-witnessed /
  standing-lapsed-in-the-gap / authorized-but-no-spendable-capacity /
  capacity-present-but-provenance-wrong). *Good-looking thing denied because
  good-looking is not admissible.*
- **Act 2 — evidence ("just one more thing").** Interrogate the **same** incident —
  SQL against the receipts, custody chain reconstructed from evidence not logs (NQ's
  party trick): what happened to X, why refused, which predicate failed, what the
  naive gate admitted.
- **Act 3 — necessity ("just one more thing").** The receipt's theorem field → the
  Lean proof that licenses the refusal *class*. **Honest framing (load-bearing):**
  theorem proves the *class boundary / admissibility invariant*; receipt proves the
  *instance facts*; the link is the artifact. NOT "Lean proved production safe" (the
  blazer-shaped grave). The receipt can then say: *this is not a discretionary policy
  denial; it is the refusal required by this custody discipline.*

Behavior → evidence → necessity. Same incident the whole way down; the audience's
model **compounds** instead of resetting. Three descents into one incident, NOT three
demos (three demos = a seminar; the 4th is always for you, not the audience).

**Best specimen = temporal** (everyone's been bitten by a stale yes): standing checked
at t=40, horizon expires t=50, spend at t=51; naive auth says yes, custody says no;
receipt shows both clocks and the gap. Dodges philosophical fog; maps to every cache /
lease / session / CI-status / deploy-approval in the industry.

**Columbo is the whole personality:** "Just one more thing, sir — you said the standing
was checked, and it was, I've got it right here… it's just that the observation was
forty seconds old, and the spend happened at second fifty-one." Unglamorous, obsessed
with receipts, catching liars whose paperwork is immaculate. Old raincoat, not black
turtleneck.

### Pinned demo scope (humiliatingly visible — everything else files a forcing case)

```
valid-looking action / stale standing / custody refusal / synthetic evidence fenced / receipt / proof seam
```

**Integrity tripwire:** make damn sure it can't pass/refuse for the *wrong* reason
(the BA3 `LA_ONLY` bypass class). A public refusal that fires because a hidden internal
ledger short-circuited the path is exactly the irony the universe enjoys.

## OPA contrast — objection pre-answer, NOT a new act

Composition beats argument: "we're not an alternative to OPA, we're what OPA stands
on." OPA is a verdict engine; it evaluates the world it's handed and **nothing attests
the input document** (`input.user.role:"admin"` is unwitnessed self-report in a
structured costume). Rego *can* check freshness if you feed it freshness — the fair
critique is not "OPA can't express it," it's that OPA cannot establish the custody of
its own inputs.

Demo beat: same incident, OPA correctly returns `allow` over a stale input (garbage
custody in, immaculate verdict out); custody refuses **upstream** — not because the
policy was wrong but because its premises failed preflight. Then OPA's verdict itself
gets a receipt (policy version, input provenance, decision) and enters the evidence
plane instead of evaporating into a decision log.

- Layering sentence: **policy engines decide over claims; custody systems decide
  whether those claims may become premises.**
- This concretizes the deferred **verdict/adjudication seam** with an off-the-shelf
  part — policy decides downstream; custody governs what it gets to decide over.
- **Scope:** ~100-line shim, demo-grade, Act 2.5 / diagram + FAQ — NOT a product
  surface. "OPA integration as supported surface" is a post-launch forcing case.
  Avoid the policy-adapter zoo (OPA → Cedar → admission controller → NATO).

## The site — unpingable.com as the lab front door

- **unpingable.com** = lab / instruments / receipts / demos. **neutral.zone** = essays.
  Cross-linked, deliberately distinct. No microsite sprawl — `agent-governor-site` is a
  parked domain (two commits + a CNAME); fold it in.
- **Do NOT make "Agent Governor" the umbrella.** AG is the action-control organ. The
  umbrella is the **custody discipline / admissibility stack**. Over-centering AG makes
  the whole thing read as another "AI agent governance framework" — the cursed sludge
  pit. Root claim: *consequential systems need typed custody between observation,
  interpretation, authority, action, memory, and refusal.*
- **Spine:** thesis ¶ → watch-a-spend-refused → receipt → topology → proof surface →
  organs. The demo is the Rosetta Stone; everything hangs off it.
- **Topology page, not a repo list.** Render the Lean conversion graph: nodes =
  components, edges = the interesting part ("observation becomes claim", "standing ≠
  spendability", "spend refused without capacity"). IA mirrors the system's actual
  architecture — the most on-brand move available; solves the gestalt problem
  structurally instead of with marketing copy.
- **Component skeleton (brutally regular):** what claim it handles / what it refuses /
  what artifact proves that / status (operational | research | zoned) / repo / one real
  receipt. "What it refuses" is the differentiator — market **boundedness**, not
  capabilities. The receipt is the hero artifact (receipts look like what honesty looks
  like).
- **Thesis draft:** *Modern systems often decide faster than their evidence stays
  valid. This lab builds custody machinery for claims, standing, capacity,
  authorization, and refusal — running code plus proof artifacts that preserve
  distinctions ordinary infrastructure collapses.*
- **Button:** "Watch authorization fail to become spendability."

## Specimen-at-front discipline (mechanizable ratchet)

Diagnosed pattern: artifacts aren't bad, they're under-specified at first contact; the
operator's self-grade runs ~**one severity level pessimistic** (site "weak" = missing
one thesis ¶; README "shit" = missing one example). A consistent bias is the
correctable kind — **gate it, don't fix the mood**.

**README specimen gate v0** (dumb on purpose — no "doc quality framework", that's how
July summons NATO). A repo passes if:
- README has `## Example | Quickstart | Specimen | 30-second run` **before** the first
  deep doctrine section (Architecture / Invariants / Philosophy / What-this-is-not);
- `examples/` has ≥1 runnable input; `golden/` or `tests/` has its expected output;
- README has one command that runs it (user-facing, not `pytest`).

> The README's specimen is the repo's receipt. You'd never ship a component without
> receipts; same rule one layer up. **Ratchet:** new/touched public repo must put a
> specimen before doctrine. (Could become a wicket-guard-shaped lint.)

First target: **`verifier`** README — **DONE 2026-06-11** (`~/git/verifier` commit
`0155f5c`): added a "30-second specimen" (the stale-standing denial) above the
doctrine, `examples/stale-standing-denied.json` + golden, and `tests/test_examples.py`
pinning the README's verdict to real tool output. Quickstart now produces a verdict,
not just `pytest`. Verifier is NOT D0-critical and the Z3 idea, while liked, isn't
needed for the demo — specimen + golden, no new scope.

**TODO — sweep the rest of the public constellation READMEs for the same fix**
(specimen-at-front before doctrine + a runnable command). One repo at a time, as I'm
in them; same minimal shape as verifier (one worked example + golden/pin, no logic
touched). Skip: papers, lean, atproto-nutrition (operator-fenced, no writes).
Candidate order by launch-visibility: the repos that will be linked from the
unpingable hub first. Lowest-glamour, but it's the ratchet that stops the operator's
~1-severity-pessimistic self-grade from gating first contact (see
`memory/feedback_specimen_at_front`).

## Limits page (not FAQ) + objection harness

A **Limits page** states the strongest case *against* the work in the author's own
voice — for this project that's the thesis demonstrated on itself (the system that
refuses overclaiming refuses its own). FAQ reads as a nervous man rehearsing in a
mirror; Limits reads as boundary documentation. Sections: what it doesn't prove / what
it costs / what must be trusted / what happens when witnesses are wrong / what
conventional tools already do well / where it's the wrong tool / current maturity.
Anti-sales line: *If you only need an authorization check, use an authorization check.*

**Forbidden launch adverbs** (overclaiming lives in the adverbs — do an adverbial
read; each trips a goblin with a subpoena): *provably, automatically, seamlessly,
trustlessly, safely, correctly, completely.*

**Objection harness** (format: objection / steelman / what the demo claims / what it
doesn't / artifact to point at / one-sentence reply). The hardest ones are the real
ones — meet them in rehearsal:
- *Isn't this just OPA / admission control?* → policy decides over premises; this
  receipts whether premises were admissible. Their distinction is policy glue; this is
  custody structure (first-class, typed, receipted, queryable, proof-linked). OPA runs
  happily *inside* it.
- *Why Lean?* → theorem proves the class boundary, not the instance event.
- *Why not just logs / isn't this event sourcing?* → event sourcing preserves what
  happened; this types what each record is *competent to claim*. A log of self-reports
  is a diary, not evidence.
- *What does it cost?* → moves cost from postmortem reconstruction into runtime custody
  (same trade as TLS / structured logging). Don't imply zero — HN smells it.
- *What's the TCB?* → it *relocates* trust, doesn't eliminate it. New TCB = locker +
  sealer + clock authority — small, boring, enumerable. "Trust with a bill of
  materials." (Anyone claiming trustlessness gets eaten.)
- *What if the witness is wrong?* → false testimony, but attributable (which witness,
  when, what coverage → quarantine). "Bad with a return address." Same answer to
  forged/stale receipts.
- *Where's it in production?* → research lab with working instruments + proofs, not a
  product seeking deployments. "Lab notebook, not an oracle." Don't imply scale.

## Recognition ammo — "your current abstraction is feral"

Not a new act; a one-liner for the exact audience, because it makes them
involuntarily recognize the shape rather than sells them an abstraction. The
discovery runs *backwards*: every engineering domain already runs **linear
accountants** — fungible, unreceipted, silently-lapsing ones. A token bucket is an
LA with anonymous units, no provenance, unwitnessed expiry; TCP's congestion window
is a capacity ledger adjusted by loss testimony; a battery BMS is a ledger over
coulombs with no custody trail. The knife for the SRE thread:

> **Your error budget is a Linear Accountant with anonymous tokens, unwitnessed
> deposits, political spending, and vibes-based blame attribution.**

Deposited by fiat (the SLO — a *declared* fact), consumed by incidents, **frozen
when exhausted** (the feature freeze is literally freeze/thaw semantics, deployed
industry-wide with nobody writing down the conservation invariant), replenished on
window roll (expiry-plus-new-deposit). And *whose deploys spent the budget?* is the
fungibility/cross-subsidy problem — anonymous units, no spend names its inputs, so
it's unanswerable by construction and settled by politics. Provenanced units answer
it with arithmetic. The "who is this for" answer was in the back pocket the whole
time: everyone already running these ledgers untyped, which is everyone. (Doctrine
home: `docs/constellation-zoning.md` §LA — "LA is metabolic, not juridical.")

## Show HN gate — control the linearization point

HN is **adversarial validation with a comment box** (the missing external witness
class), not publicity. Death-by-shrug ("interesting, but I'm not sure what this is")
is worse than criticism. Deliberate Show HN on a **chosen morning** > organic ambush:
you pick the moment, field the OPA question calmly in your own comments with receipts
(worth more credibility than the post). Pseudonymity (unpingable) already pre-bounds
blast radius. Organic feels safer but is operationally worse — you lose sequencing,
the one thing the apparatus respects.

Gate (all true before posting): one command runs it / incident legible in 30s /
receipt is the hero artifact / proof link precise / OPA objection pre-answered /
AI-governance-grift objection pre-answered / one obvious page to link (the demo page).

Title: dry + specific, not clever — e.g. *"Show HN: Typed receipts for why an
authorized action still can't run"* or *"…authorization passes but spendability is
refused."* Comment posture: dry, blade at the claim not the commenter; concede what's
true (OPA can encode freshness; Lean doesn't prove production safe; overkill for many
systems) then state the narrow real claim.

## Sequencing

1. **Simulated evidence fence — predicate DONE** 2026-06-11 (`ab6d196`,
   `operational_admission`, allowlist `{observed}`, 27 tests incl. pinning). NQ owns
   declared; AG fences its own receipts. Remaining: wire it in (folded into D0 below).
2. Finish **D0** as the public refusal specimen (temporal incident; integrity tripwire).
   - **First code = the fence wiring** (custody-affecting authority-path change): in
     `cooked_context_orchestrator`, the success path that returns `ConsumedResult`
     (effect allowed) must first pass `operational_admission(origin_mode)` — a
     synthetic/drill/replay chain must refuse to reach operational consequence. Its
     own focused slice; not a tail-of-session slam.
   - **Build the demo cases AS golden-corpus entries** (`input → verdict` pairs).
     Per `memory/rust_kernel_port_ruling`, the corpus — not the Python source — is
     the kernel contract; the socket-cut + corpus is the launch-serving "do now" that
     converts the eventual Rust port from a rewrite into a frozen-contract fill.
     "The receipt converged faster than the program." The demo trio (valid passes /
     credentialed-impostor refused / temporal lapse) seeds it directly.
3. Hub **dumb but structurally right** (thesis ¶ + topology map with stubs).
4. One polished **demo page** (+ OPA contrast diagram, Limits page).
5. **Specimen ratchet** pass over public READMEs (start: `verifier`).
6. THEN deliberate **Show HN** on a chosen morning.

Not "finish the system." Not "document everything." Just: one refusal reproducible by
a stranger, with its premises fenced and its proof seam clickable.

## Cross-references

- `docs/constellation-zoning.md` — the map this plan is the slab for; §Evidence classes
  (the launch-blocking simulated class), §Notary, the deferred verdict seam (OPA fills it).
- `working/directional-invariants.md` — "authorized does not route to safe" is the
  theorem the Act-3 proof seam cites.
- Memory: `docs_ownership` (this Claude owns the doc side), `launch_posture`,
  `feedback_specimen_at_front`.
