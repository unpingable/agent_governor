---
audience: cross-project
status: active
---

# Briefings, not cockpits

Status: doctrine (interpretive, cross-project)
Audience: anyone building a surface that renders operational or governance state
under uncertainty — NQ dashboards, the atlas projects, the governor ViewModel /
dashboard-ux, Nightshift review packets, any ops console.
Purpose: name the genre these surfaces should be, steal the structure from
reported graphics, and stop making readers reverse-engineer the ontology.

> **Ops views are news apps for systems under stress.**
> **The screen should behave like an analyst, not a cockpit.**

## The reframe

Most dashboards are built like *"here is every fact the machine can emit; good
luck, mammal."* A better surface is *"here is what changed, why it matters,
what is likely causal, what is uncertain, and what action is admissible."* That
is reported-graphics logic, not instrument-panel logic.

Cockpits are for trained pilots doing continuous control. Most ops (and most
atlas reading) is **intermittent attention under uncertainty, usually while
another tab is on fire**. The surface should brief that reader, not hand them a
yoke.

## Far view / near view (the load-bearing split, from ProPublica)

Every news app needs a **far view** that tells the highest-level story and a
**near view** where the reader locates *why they should care* and *how we know*.

- **Far view** = the annotated story. For the atlas: the left-to-right
  composition map. For ops: the annotated service path / dependency DAG with
  symptoms, recent change, and admissible action marked.
- **Near view** = the receipts. Click an edge / field / node / finding to see
  source receipts, last-verified currency, contestation, owners, runbooks, and
  **what is not claimed**.

The doctrine survives — it just moves *behind the story*. **Reader sees "what
happens and why it matters"; auditor sees "claim type, currency, receipts,
contestation."** Same artifact, two depths.

## Story first, object model second

A surface is journalism with a headline, lead, and nut graf — not an interface
over a dataset. Visual hierarchy should be **bold, not coy**: contrast, scale,
typography direct attention. Too much subtlety reads as *broken*, not *refined*
(the lane-header / ghost-node failure mode). Strong design is invisible; weak
design makes the reader reverse-engineer your ontology.

## The stealable structure (any serious ops/governance screen)

```
HEADLINE       The system-level claim, in one line.
DEK / SUMMARY  Plain-language current state.
MAP / GRAPHIC  Annotated service path or dependency DAG (the far view).
EVIDENCE DRAWER  Metrics, logs, traces, deploys, incidents, receipts (near view).
ACTION BOX     Safe next actions, blocked actions, escalation boundary.
CONTESTATION   What evidence does NOT fit the current theory.
```

`CONTESTATION` is the one most dashboards omit and the one that matters most:
they silently overfit. A good view says *"this looks like payments, but
database saturation is a weak competing hypothesis"* instead of *"red panel
angry."* This is the surface honoring its own evidentiary humility — the same
discipline the witness/receipt doctrine enforces underneath.

## Position / emphasis / evidence (the rendering grammar)

- **Atlas:** position = where it sits in the machine; line = claim strength.
- **Ops:** position = where it sits in the service path; emphasis = operational
  relevance; evidence = how we know.

An ops map should not merely render the dependency graph — it should annotate
where symptoms appear, where recent change occurred, where evidence supports
causality, where action is allowed, and where uncertainty remains. That is the
difference between a topology diagram and an incident explainer.

## The reusable test

> **What would the headline be if this were a short incident article?**
> If there is no headline, the view is not ready.

Headline shapes to aim for:

- "Storage witness is stale; closure is not admissible."
- "Deploy changed the only hot path before latency rose."
- "Alert storm is one failed dependency, not twelve incidents."
- "No current witness supports this automation action."
- "Rollback is safe; schema migration is not."

## Worked example (NQ / Nightshift)

Not: *"here are all witnesses, claims, receipts, and edge states."* Instead:

```
Current posture:
  NQ sees host-storage testimony as STALE on lil-nas-x.
Impact:
  Nightshift closure confidence degraded.
Blocking fact:
  Last admissible disk-state witness is older than policy horizon.
Next safe action:
  Refresh witness, or mark closure unsupported.
```

…with the near view below (receipt X, witness Y, horizon rule Z, last-verified
time, contesting evidence). **Story first, receipts second** — and the receipts
are one click down, never gone.

## Composition with the register doctrine

- Composes with [`../visual_registers.md`](../visual_registers.md): *state
  below, pixels above; never let the pixels outrun the state.* Briefings-first
  does NOT license a confident headline the evidence can't carry. The headline
  is itself a claim — it inherits currency and contestation. A "briefing" that
  asserts past its receipts is the exact overfit this doctrine forbids.
- Composes with [`../information_architecture_registers.md`](../information_architecture_registers.md):
  far/near is the IA expression of the register split.
- Composes with the currency/claim-axis split in
  [`../../working/GOV_GAP_GOVERNED_SWEEP_PROTOCOL_001.md`](../../working/GOV_GAP_GOVERNED_SWEEP_PROTOCOL_001.md):
  a surface must render *currency* (current / stale / pending-review) in the far
  view, not present stale evidence as fresh. An atlas about evidentiary
  composition that hid its own staleness would be a compact self-own.

## The genre, named

> **Investigative explainer with an evidence drawer** — not "governance cockpit
> for people who alphabetize their anxieties."**
