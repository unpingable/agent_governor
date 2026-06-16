# Endgame Synthesis — Maude as Supervised Runtime, LA at the Dispatcher

**Status: doctrine deposit, NOT a build directive.** Recognition record
of the workflow the constellation has been assembling toward. Filed
2026-06-10 after the standing-before-spendability MVP sprint committed,
during a conversation with Fable. Operator framing: *"I was going to
start with the language change (legal → ops) but instead I got something
awesome to show you."*

This file is a recognition artifact. It captures the shape so it is
findable before anything else here moves. No agents are dispatched off
this file; no slice plans are drafted off it. The next move is whatever
the operator says is next, which is not necessarily anything from this
list.

## The recognition

> **Maude already is the supervised agent runtime.**

Not conceptually — actually. Per its existing surface:

```
governed process
tool-call interception
approval / denial
timeout-deny
diff review
promote / reject
workspace revert
```

The missing layer is not "build agent framework #4, spiritually worse
this time." It is:

> **Who answers the approval prompt?**

The whole constellation built across this sprint and the ones before it
exists to answer that question without turning into vibes.

## The endgame workflow

```
operator-curated backlog item
  → nightshift watchbill intent
  → standing grant
  → wicket admission
  → linear accountant capacity
  → maude governed session
  → branch + diff + receipt chain
  → phosphor morning review queue
```

Every node in that chain already exists, either as production code or as
ratified doctrine.

## The constitutional rule (directional custody)

The earlier framing of this rule was "no self-amendment" with a list of
genesis-class surfaces. The operator sharpened the rule 2026-06-10 to
its underlying *why*, which is cleaner because it explains rather than
asserts:

> **A system that can act through gates must not rewrite those gates
> while acting through them.**
>
> Downstream capability cannot mutate upstream authorization while
> inside the downstream flow. This is not superstition about config
> files; it is directional custody — the directional kernel from
> `working/directional-invariants.md` applied to the self-amendment
> case.

Operationally, the rule still names the surfaces it protects:

Genesis-class surfaces (morning review / operator fiat / always):

- standing
- linear_accountant
- wicket
- AG enforcement path
- receipt schemas
- classification policy itself
- doctrine files (this list among them)
- Maude approval policy itself

Outside the fence, work flows. Inside, nothing moves without explicit
operator ratification. This is the anti-courthouse-renovation clause.
Without it, the inmates are just installing better lighting in the
evidence locker.

This rule composes one level up with the invariant from
`working/sentinel-observation-not-authority.md` (observation does not
mint authority) and the directional kernel from
`working/directional-invariants.md` (no later-stage artifact may supply
an earlier-stage authority condition). The genesis-class rule is the
self-amendment case of the same shape: the system, having gained the
ability to act through gates, must not gain the ability to rewrite
those gates while acting.

## LA at the tool-call dispatcher (the thaw)

The frozen reference boundary on Linear Accountant named its own thaw
trigger: *"a real agent stack wanting consume() at its tool-call
dispatcher."* Maude's interception point IS a tool-call dispatcher.

The operator-sharpened framing 2026-06-10 makes BA3's thaw trigger
concrete:

> **Maude write-tool approval IS the convertible spend boundary.**
>
> When Maude approval permits a write tool, that permission must consume
> LA capacity, or the approval path is unmetered consequence.

The wiring shape:

```
write_tool_call approval
  → consume(capacity)
  → emit receipt
  → allow / deny
```

The correct metering point is the **approved consequential tool call**.
Not per session. Not per backlog item alone. Per the consequential
write.

Failure modes become legible:

```
retry storm    → budget exhaustion (receipted)
runaway session → budget exhaustion (receipted)
unclear action → timeout / queue
gate mutation   → genesis stop
```

This re-positions `working/post-mvp-debt-ba3-hardshort-to-la.md`. The
"convertible spend path appears" trigger that the BA3 bypass contract
named — the moment AG's internal authoritative ledgers must hard-short
to LA — now has a concrete address: **Maude's write-tool approval
boundary.** When the wiring at that boundary lands, BA3 hard-short
becomes the operative slice, not the parked debt note.

## Policy-mode = the authority-effect rule with consequence

The pin landed earlier 2026-06-10
(`memory/feedback_artifact_authority_classification.md`) becomes the
policy-mode approval engine:

```
authority_effect = none / low / descriptive
  → auto-approve under scoped grant
  → land + report

authority_effect = doctrine surface / binding vocabulary / consumer contract
  → auto-approve if scoped grant + tests + no gate touch
  → otherwise queue for morning

authority_effect = unknown / unclassifiable
  → timeout / queue for morning

authority_effect = HIGH / custody-affecting / implementing /
                  externally binding / GENESIS-class
  → deny unattended; require operator fiat
```

The classification taxonomy stops being self-discipline and becomes the
approval engine. This is the moment the kabuki becomes useful: the
"do not ask permission" rule at the low band, the "stop and ask" rule
at the high band, both become the same line of code in Maude's
policy-mode dispatcher.

## The trap (no slop recursion)

> **Operator-curated intents only.** No agent writing tasks for agents
> as its own substrate.

Allowed sources for backlog items:

- Operator-written note
- NQ finding (witness-layer, not model-layer)
- Explicit watchbill
- Human-curated backlog item

NOT allowed:

- Model-generated improvement suggestions consumed as backlog
- Model prioritization of its own prior suggestions
- Agent-to-agent task delegation

That's slop recursion wearing a tiny hard hat — the compost heap that
invoices you. **The §3b LLM-placement table gained a ninth must-not
2026-06-10:**

> The LLM must not be **the source of its own work.** The LLM may
> propose edits within an operator-curated intent, but it must not mint
> new backlog items, expand its own mandate, or create follow-on work
> for other unattended agents.

That closes the slop flywheel.

## Phosphor is the morning paper

Do not build a third tool.

```
Maude          per-session supervision substrate
Nightshift     work orchestration / scheduler
Standing       entitlement mint (~/git/standing)
Wicket         admissibility preflight (~/git/wicket)
LA             capacity / spendability (~/git/linearaccountant)
NQ + AG        witness + enforcement
Phosphor       cockpit / morning review queue
```

The morning queue is a Phosphor surface (not a new tool):

```
overnight proposals
diffs
receipts
why-chains
budget consumed
denials / timeouts / queued unknowns
promotion buttons
reject + revert lineage
```

The night shift runs, Hermes files, Scrooge counts, the witness watches,
and the morning brings a receipted paper trail.

## Sequence (operator-proposed, not committed)

```
1. Finish gauntlet show surface.                          [DONE — sprint committed 2026-06-10]
2. Wire LA consume() into Maude write-tool approval.      [future]
3. Add standing policy-mode approval classes.             [future]
4. Add unattended-safe deny/queue behavior.               [future]
5. Represent backlog items as nightshift watchbill intents. [future]
6. Render Maude proposal packets in Phosphor morning queue. [future]
```

Each step is small. No new metaphysics. Connect the already-existing
nerve endings.

**Every step 2–6 is custody-affecting** (per the authority-effect rule);
none of them moves without explicit operator fiat. This file does not
authorize any of them. It records that the shape is recognized.

## The product sentence

> Operator-curated work is executed by governed agents under standing,
> metered at action boundaries, witnessed at every consequential step,
> and returned as receipted proposals.

That is the machine. It is not "agents autonomously improve software"
(slop). It is not "AI governance platform" (slop with a logo). It is the
specific workflow above.

## Cross-references

- `memory/feedback_artifact_authority_classification.md` — the rule that
  becomes the policy-mode approval engine
- `working/post-mvp-debt-ba3-hardshort-to-la.md` — the trigger this
  endgame fires (LA at Maude's dispatcher)
- `working/sentinel-observation-not-authority.md` — composes with the
  genesis-class rule one level up
- `working/directional-invariants.md` — directional kernel; the
  genesis-class rule is the self-amendment case
- `memory/maude_dogfood_gap.md` — Maude already exists; the gap this
  synthesis names is policy-mode + LA wiring, not new infrastructure
- `memory/standing_integration.md` — standing as the entitlement-mint
  upstream
- `memory/linearaccountant_repo.md` — LA's "convertible spend path
  appears" trigger; Maude's dispatcher is the address
- `memory/scheduler_repo.md` — nightshift as work orchestration
- `docs/agent-governor-meta-plan.md` — the §3b actuation pin's LLM
  placement table is the per-class approval rule one level down
- `working/parked-constellation-alignment-pass.md` — when the legal→ops
  rename pass fires, "morning paper" / "watchbill intent" / "Scrooge"
  vocabulary should be checked against the operational-noun discipline

## What this file is not

- Not a sprint plan.
- Not authorization to wire LA into Maude.
- Not authorization to build policy-mode classes.
- Not authorization to ship a "demo" of the overnight workflow.
- Not a marketing artifact. The product sentence above is for internal
  recognition, not for pitch decks.
- Not a doctrine ratification. The genesis-class rule is filed as
  proposed-doctrine pending operator fiat at the moment any of steps 2–6
  fires; this file proposes the rule, does not ratify it.

The operator's pacing governs. The legal→ops rename pass was deferred
to file this; whatever the operator picks next is the next move.
