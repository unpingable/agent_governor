# Pipeline doctrine — epistemic backoff, quorum shape, policy custody

**Status: design record (operator-directed write-down, 2026-06-12 afternoon).**
Source: operator + ChatGPT ("Chatty") + Fable design session. Operator's closing
line carries the disposition: *"this is foundational to how the constellation
pipeline should act — important stuff to not leave implicit."*
Normative landing: epistemic backoff → `docs/loop-protocol.md` §11 addendum
(applied same day); quorum shape + policy custody → zoning appendix (CANDIDATE)
+ backlog handles. This file is the full reasoning record.

The session's intuition pump (sanitized): mature cloud-compute platforms are
Rube Goldberg machines internally and work anyway — because of rigid interfaces
plus decades of operational scar tissue externalized into runbooks, alarms, and
institutional memory. **Agents have none of that unless you hand it to them as
receipts.** Clean design doesn't help an agent, because the agent doesn't
experience the design — it experiences the evidence available at the moment of
action. Otherwise it infers the shape of the beast from whichever pipe hissed
last: spaghetti plans on spaghetti code, a lasagna of bad priors. The loop's
re-entry probes already replace inference with observation; everything below
extends that same move.

---

## 1. Epistemic backoff (governed loops without a hard LA cost-cap)

**Classic backoff is the wrong template.** Exponential backoff is politeness to
a contended resource — the failure signal is "busy." Agent backoff is epistemic
humility enforced by the ledger — the failure signal is "my model of this
system is wrong," and the correct response isn't retrying slower, it's
**changing epistemic mode**. Contention ≠ confusion; conflating them is how a
confused agent turns the repo into archaeological strata.

The compact rule:

> **When retries stop producing new evidence, retry is forbidden. When
> failures produce too many kinds of evidence, mutation is forbidden.**

### Failure signature table

| Signal | Interpretation | Action |
|---|---|---|
| same failure **class** twice | not transient anymore | reclassify per failure table; stop retrying (a third try is superstition) |
| different failure classes across attempts | model mismatch (high failure entropy) | enter PROBE |
| high spend, low receipt progress | flailing | PROBE or halt |
| probe finds missing evidence | dependency gap | park / slice dependency |
| probe finds spec contradiction | bad slice | audit / recomposition |
| probe clears state but action still fails | escalate once | baseline+1 with recorded reason |

(Chatty amendment 1: failure **class** matching, never exact-string matching —
string matching rots immediately.)

### PROBE mode — a mode switch, not a retry

When acting stops informing, stop acting and start observing. PROBE is the
anti-inference posture made mandatory. Hard invariants:

```text
no mutations
no commits
no generated fixes
no "while I'm here"
read-only commands only
state inventory
receipt inspection
failure-class synthesis
```

Without the wall, every agent will "probe" by applying a patch and calling it
diagnostic — little raccoons with sudo. **The wall gets a pinning test like
every other fence:** since everything is receipted, "probe sessions emit zero
mutation receipts" is mechanically checkable from the trail after the fact.
The invariant audits itself for free; that's the difference between an
invariant and a vibe, and it costs one test.

### The LA hook — burn-per-progress

Confusion has a price signal and the ledger already sees it. A flailing agent
burns multiples of normal capacity per unit of progress (re-ingestion, tool
calls, discarded partial work). The keeper metric:

> **burn-per-progress = capacity consumed / slice-advancing receipts emitted**

Not "did it spend a lot?" but "did spending buy admissible progress?" Two
thresholds: **soft** → mandatory PROBE downshift + confusion receipt (early
warning while budget remains to act on it); **hard** → capacity checkpoint,
halt, morning audit. The ledger stops being a fuel gauge and becomes a flail
detector. Exhaustion-typed, correctly: the agent did nothing inadmissible; it
ran out of license-to-flounder.

Two counters, both metabolic in the LA sense:

```text
execution_budget  -> normal action capacity
confusion_budget  -> bounded permission-to-flounder
```

> **Confusion spend is the metabolic cost of failed model contact. It
> authorizes neither mutation nor continued retries; it triggers observation.**

### Escalation ladder

```text
retry (transient) → probe (confused) → escalate-once (baseline+1, with reason)
→ park (batched clarification) → halt
```

Tier escalation slots in exactly once, only after a PROBE pass (Chatty
amendment 2, in tasteful institutional font: **baseline+1 is ILLEGAL until
after PROBE**). Escalation is a strategy change, never a retry substitute —
"ask a bigger model the same way" is the most expensive form of shaking the
machine. Composes with §12's baseline+1 spend policy: confusion is precisely a
mistake-shape problem, which is what the +1 tier is licensed for.

### Confusion receipt (structured for decomposer feedback)

```text
confusion_receipt:
  slice_id
  attempt_count
  failure_classes_seen
  repeated_failure_classes
  distinct_failure_count
  capacity_spent
  slice_advancing_receipts
  burn_per_progress
  inferred_signature:
    transient_dead | model_mismatch | dependency_gap | spec_contradiction | unknown
  prescribed_next_mode:
    probe | escalate_once | park | halt
```

Long-game payoff: confusion receipts accumulating against a slice **class**
are evidence the decomposition is bad — the spaghetti was in the plan, not the
executor. That's calibration data for the candidate-slice compiler: the
agents' confusion becomes the spec process's instrumentation. Process
calibration, not ML training. Scar tissue accruing as typed receipts from day
one instead of decades of pages.

### Correlated confusion — the fleet-level signature

Emergent entropy at scale hits where you least expect; the per-agent design
misses one class. One agent confused on one slice = slice cut wrong or agent
floundering. **Three agents emitting confusion receipts on unrelated slices in
the same window = the environment broke** (dependency rotted, shared state went
bad, a service died) — and no per-slice probing finds it, because each agent
correctly diagnoses its local mystery while missing that the mysteries share a
cause. The morning audit (eventually phosphor) checks confusion **correlation
across slices**; correlated confusion escalates to environment-level diagnosis,
not slice-level recomposition. Cheap query; catches the class of problem that
makes naive fleets eat themselves.

### The foil (one beat of precision)

Ambient-authority agent runners (the OpenClaw shape) are the perfect contrast:
the value proposition is deleting this entire layer — full machine access,
bearer-everything (possession is the whole model), no origin typing, no
admission, no receipts; "frictionless" where the friction removed was the
fences. An agent with no burn-per-progress meter WILL flail (that's just
entropy) — and it flails with sudo and a messaging app attached. Confusion +
ambient authority is the incident generator; confusion + a metabolic cap + a
PROBE downshift is a Tuesday with receipts. Same model intelligence, opposite
blast radius. The lasagna gets kitchen access in one architecture and a
clipboard in the other.

---

## 2. Quorum shape — votes are claims with shapes, never facts with counts

Correlated confusion is exactly where badly-shaped quorum implementations bite,
fast, especially with nested decisions. Quorum math silently assumes the one
thing correlated confusion destroys: **independence of error.** A 3-of-5 vote
is evidence only insofar as the five could have failed separately. Shared
poisoned premise → the quorum converges on the same wrong answer with high
procedural confidence:

```text
5-0 = one error, redundantly serialized
```

The raw count is not confidence. It is volume. A vote counter without
provenance is a confidence-laundering appliance (very enterprise; probably has
a dashboard).

**The same-model special case is the nastiest because it looks cheap and
strong:** a quorum of the same model is one opinion sampled N times — same
weights, same priors, same blind spots, same response to the same poisoned
context. Temperature isn't independence; it's jitter on one voter. One witness
with five hats. Vaudeville, not epistemology. (Corollary already in hand: the
worker pool's substrate diversity — Claude-family / codex / qwen — is *actual*
quorum diversity, and the four NQ boxes with different power cables are a
*physical* independence substrate. Multi-model interferometry was always
quorum-with-declared-independence-classes; never let a vote-counter flatten
it.)

### Independence axes (declared, attested or marked absent)

| Axis | Why it matters |
|---|---|
| model substrate | different weights / priors / blind spots |
| toolchain | different executor / parser / harness failures |
| host | different filesystem / env / local state |
| power/network domain | physical independence for absence/liveness |
| prompt/context origin | avoids the same poisoned packet |
| dependency view | avoids the same stale config or upstream lie |

**Known shared dependencies count AGAINST independence**, not as harmless
metadata.

### Nesting is where it compounds (Paper 24 in a voting booth)

A quorum-of-quorums is stacked aggregation layers: each subset's consensus
flattens to one vote going up; margin, dissent, abstention, and correlation
class die at every level. A 3-2 squeaker and a 5-0 unanimous arrive at the
parent as identical "yes" tokens; confidence inflates with depth because each
layer treats the layer below as ground truth instead of testimony with a
shape. Three levels deep, a marginal correlated locally-contested signal
arrives as institutional certainty. The parent must see the shape:

```text
yes { margin: 3-2, independence: weak/same_substrate, dissent: [D7, D9] }
```

### Receipt shape (good vs bad)

```text
bad:   verdict = yes; votes = 5
good:  verdict_shape:
         yes=5 no=0 abstain=0 margin=5-0
         independence_classes:
           model_substrate: [claude_family]
           host_domain: [same_host]
           upstream_context: [same_prompt_bundle]
           power_domain: [unknown]
         dissent_receipts: []
         independence_attested: false
```

The second is downstream-policy-insufficient even though unanimous — which is
the point.

### Anti-rules

```text
No quorum threshold over raw counts alone.
No same-model quorum counted as independent.
No nested quorum may emit only yes/no.
No aggregation may discard dissent receipts.
No "unanimous" label without independence classes.
No action escalation until the correlated-confusion check passes.
```

Preservation rule: **aggregators may summarize; they may not erase dissent,
margin, abstention, or provenance class.** Minority reports are receipts for
where the unifier tried to get cute — refusal-preservation discipline in
voting clothes.

### Policy over shapes (form, not the exact thresholds)

```text
low-risk action:    ≥2 yes, no hard refusal
repo mutation:      yes across ≥2 model substrates; dissent preserved;
                    no shared dependency failure
external effect:    unanimity across ≥2 independence classes;
                    no unresolved abstentions/refusals
safety-critical:    independent provenance attested;
                    dissent blocks or routes to audit
```

### The 2am chain (why this is urgent, concretely)

Shared dependency rots → fleet-wide correlated confusion → confused agents
vote on the diagnosis → quorum is unanimous *because* the confusion is shared
→ nested layer treats unanimity as certainty → automated remediation fires on
the wrong cause, confidently, with receipts. Every step procedurally correct;
the chain wrong because independence was assumed and never attested. The
correlated-confusion audit check (§1) is the cheap antibody — detected
*before* anyone counts it as agreement.

### Zoning glyph (one sentence, drawer-ready)

> **Quorums are divergence witnesses: they attest agreement shape with
> provenance classes and preserved dissent. Independence is attested or
> absent; thresholds are downstream policy over shapes, never counts.**

No new organ — a constraint on a future one, the cheapest kind of architecture.
(AG-local note: `quorum.py` / `independence.py` / `sybil.py` already carry
independence scoring and Neff — the constraint above is the consumption rule
their outputs must keep satisfying; the existing modules are partial coverage,
not violations.)

---

## 3. Policy custody — the register, not The Policy Engine

The forcing question: "are we going to need a policy engine? it's basically
already happening in governor implicitly." The split that answers it:

**Policy engines already exist — plural, scoped, correctly.** verifier IS one
(rules + facts → explainable verdict, Z3 underneath); the OPA shim is a
foreign one, deliberately seated; wicket evaluates admissibility policy; LA
evaluates spend policy; the loop evaluates priority policy. Evaluation is in
the right places — local to the component competent over that claim class.
What's accreting implicitly is the **policies**: acceptable-gap bounds,
quorum-shape thresholds, tier admission rules, retry budgets, priority orders
— living as hardcoded constants, ratified prose, and config files, with no
identity, no versioning, no citation from the verdicts they produce. The
governor isn't secretly becoming a policy engine; it's secretly becoming a
**policy landfill**.

**Do NOT build The Policy Engine** (capital letters, single DSL, one
Rego-shaped courthouse). The no-unifier result predicts how it dies: one
policy calculus spanning spend, freshness, quorum shapes, tier admission, and
escalation either erases refusal surfaces or imports structure none of those
domains licensed. A spend policy and a quorum-shape policy are different
species with different evaluators. The surviving architecture is the kernel
synthesis's: **typed federation with shared custody discipline** — scoped
engines stay scoped; what they share is how policies are *kept*, not how
they're *evaluated*.

### The missing organ is small and boring: a policy register

```text
policy has identity
policy has version
policy has type
policy has ratification status
verdict cites policy@version
```

The enforcement mechanism is one line of discipline, adoptable immediately:

> **Every verdict receipt names the policy artifact and version that made the
> verdict possible.** `policy_ref: quorum_shape.repo_mutation.v0`

Receipt sketch:

```json
{
  "verdict": "refused",
  "policy_ref": "quorum_shape.repo_mutation.v0",
  "policy_digest": "sha256:...",
  "evaluator": "wicket-admission.v1",
  "inputs_ref": "...",
  "reason": "insufficient_independence_classes"
}
```

The elegant part is the forcing mechanism — extraction by citation failure:

```text
receipt cannot cite policy_ref
=> policy is implicit
=> AUDIT deviation
=> extract ONLY that policy
```

No migration death march, no "model all policy first" (how architecture teams
go to a farm upstate). Most of the register already exists as prose
(loop-protocol §§, the spend policy, §11 budgets, the murder-hallway bounds) —
the gap is IDs, versions, and refs, not content.

### Register shape (directory convention, NOT a service)

```text
policies/
  quorum_shape/
    repo_mutation.v0.md
    external_effect.v0.md
  loop_backoff/
    epistemic_backoff.v0.md
  spend/
    baseline_plus_one.v0.md
  freshness/
    murder_hallway_bounds.v0.md
```

Each artifact minimally: `policy_id, version, policy_kind,
competent_evaluator, scope, ratified_by/ratification_receipt,
inputs_required, verdicts_possible, failure/refusal classes`.

Guardrail: **policy artifacts are typed by evaluator competence** — a
quorum-shape policy cannot be evaluated by LA; a spend policy cannot be read
as an admissibility policy. Non-cathedral line: **the register stores policy
custody; evaluators remain local.** (Prevents the landfill from becoming a
courthouse — a constant risk in this project's natural habitat.)

### What this closes: the verdict plane, finally located

The constellation audit flagged it weeks ago — "verdict = downstream, invoked
everywhere, located nowhere." The answer is a federation:

```text
verdict plane =
  typed policy artifacts in a register
+ scoped evaluators (verifier, OPA shim, component-local code)
+ verdict receipts citing policy@version
```

Witnesses attest, gates refuse, ledgers conserve — and judgments become claims
with provenance, challengeable back to the exact policy version that produced
them. The postmortem split this buys:

| Failure | Meaning | Remediation |
|---|---|---|
| wrong policy | threshold/rule was bad | amend policy artifact |
| wrong evaluator | implementation bug | fix evaluator |
| wrong input evidence | witness/custody failure | repair evidence path |
| wrong policy ref | citation/custody bug | audit / receipt defect |

Without policy refs all four collapse into "the system made a bad decision,"
which is basically a scented candle.

### Disposition

- Zoning line + citation rule **now** (`policy-register-citation-discipline`
  backlog; verdicts without policy refs become an AUDIT deviation — rides into
  loop-protocol obligation conformance).
- Register as a directory convention; extraction by citation failure forever
  after. No cathedral.
- The quorum policy shapes from §2 become the register's **first
  properly-born residents** (`quorum_shape.v0`, written as versioned artifacts
  from day one instead of exhumed from code later), alongside
  `loop_backoff/epistemic_backoff.v0` (§1, normative copy in loop-protocol
  §11).
- Policies are custody-affecting by definition — ratification ceremony already
  exists; register entries use it.
