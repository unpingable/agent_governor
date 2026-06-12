# Demo-2 "correctly bored" + the operator's chair — design record

**Status: design record + backlog handles (operator-directed write-down,
2026-06-12 evening). Everything here is POST-LAUNCH; queue discipline is half
the content.** Source: operator + ChatGPT ("Chatty") + Fable session.
Operator context: launch item 5 becomes 5.1–5.n (README ratchet, deliberately
paranoid); item 6 (Show HN) acknowledged scary; more building may precede it.

Grounding survey (2026-06-12, this machine): `~/git/guvnah` ✓ (Electron+Svelte
cockpit, daemon as stdio child), `~/git/maude` ✓ (terminal operator UI),
**`gov-webui` ✗ not cloned locally** (remote: github.com/unpingable/governor_webui),
**`vscode-governor` ✗ not cloned locally** (remote exists). Daemon-side contract
tests live in this repo (`integration/test_contract_*.py`). The séance correction:
the webui-refresh probe starts with a `git clone`, not a test run.

---

## 1. Demo-2 — the correctly-bored governed loop

The pitch line: **"The dashboard is empty. The receipt log is not."**

Setting: the linode VM — labelwatch/driftwatch containers + the NQ instance
already there. A governed loop watches local NQ and acts on alerts. Three
acts, and the *first* is the doctrinal centerpiece, not the warm-up:

### Act 1 — correctly bored (the centerpiece)

Every monitoring demo shows alerts firing; nobody demos **typed silence**.
A green dashboard is ambiguous by construction — it cannot distinguish
"everything's fine" from "the watcher is dead" from "noise already
adjudicated." A green dashboard is not evidence; it is a mood. The loop
receiving normal WAL pressure emits receipted boredom:

```text
observed_event: driftwatch_wal_pressure
classification: known_baseline
policy_ref: driftwatch_baseline.v0
action: none
coverage: intact
reason: within admitted bounds
```

Demo line: *nothing happened, and here are the receipts proving nothing was
supposed to happen.* Quiet is a claim with coverage — sealed-silence vs.
silence, on camera. The no-op receipt matters as much as the remediation
receipt; possibly more. Baseline state ≠ green/empty dash, and the governed
loop knows the difference.

### Act 2 — bounded reflex

**Type the chaos first.** The deliberate kill carries a declaration — same
species as a maintenance window: declared fact, standing-backed, scoped,
time-bounded:

```text
chaos_drill.v0:
  target: driftwatch container
  action: stop
  scope: one container
  window: 10 min
  expected_observation: service_down
```

The container death is still *observed* (it really died); the *cause* is
declared. Receipts carry both → the morning audit distinguishes drill-induced
from wild incidents, and repeated drill-kills don't poison incident
statistics. The remediation runs identically either way — the typing is for
the record, not the reflex.

Loop response: alert observed → `policy_ref: driftwatch_remediation.v0` →
pre-authorized standing → restart container → `remediation_attempt_1` →
recovered. The reflex plane instantiated without a theory dump: pre-staged
authority, real action, no consultation.

### Act 3 — exhaustion / escalation (the killer SRE beat)

Keep killing the container. The loop must not become a restart daemon with
delusions of grandeur:

```text
attempt 1: restart
attempt 2: restart
attempt 3: restart REFUSED / budget exhausted
classification: persistent external interference or failed remediation
action: halt automation, escalate to human (full attempt trail attached)
```

The loop remediates once, maybe twice, then **refuses to keep pretending
repeated failure is progress** — "this exceeds my license to flounder."
Exhaustion-typed (the agent did nothing inadmissible), the anti-flail design
(§11.1) and the attention ledger in one beat. The exact auto-remediation
pathology every SRE in the audience has personally survived, refused on
camera.

### Receipt vocabulary (drawer-ready)

```text
baseline_observed.v0        known_baseline_noop.v0
chaos_drill_declared.v0     alert_observed.v0
reflex_action_authorized.v0 remediation_attempt.v0
remediation_succeeded.v0    remediation_budget_exhausted.v0
human_escalation.v0         coverage_intact.v0 / coverage_gap.v0
```

### v0 surface (deliberately small)

**Colocate; dodge networking entirely.** Loop runs ON the linode watching
local NQ: `NQ local feed → governed loop → local docker/systemd action →
receipts back to NQ`. Zero cross-host dependency; the watch-from-another-box
version is the N2 crosstalk payoff later, not a prerequisite. Five pieces:
baseline classifier (policy_ref required), reflex action runner (scoped to
the one container, receipt-emitting), retry/blast-radius budget (exhaustion
receipt), chaos declaration, **recorded canonical run** (asciinema — live
rerun only if you feel like angering the demo gods).

### Why it's quarantined behind launch (tier-2-high, post-launch FIRST)

Not low-value — **too good; it will eat the room.** Building it IS building
reflex-v0, the LA retry/blast-radius template's first real ledger, baseline
policy custody (first policy-register residents in anger), chaos-drill
typing, and the escalation receipt path — a lot of organs in a trench coat.
It's the forcing case three filed organs have been waiting for, which makes
it the obvious first big thing the loop eats post-launch. The demo IS the
construction receipt — building/testing/running it is one ladder. Pleasing
recursion: the governed loop's first major post-launch project is the demo
*of the governed loop*, under its own budgets, emitting confusion receipts
about constructing its own portrait. Frame those too.

Demo sequence: Demo 1 = custody/refusal/proof seam (the murder hallway,
SHIPPED). Demo 2 = correctly bored / reflex / exhaustion. Demo 3 = museum /
RKL / constellation tour (unseated from slot 2; it keeps).

---

## 2. The viewer — refresh the witness surface, don't build a demo UI

The guvnah rediscovery (and its lesson, §5): the surface split was ratified,
implemented, and contract-tested months ago. Disposition table:

| Surface | Role |
|---|---|
| **gov-webui** | per-daemon demo/operator dashboard — **demo-2's viewer**, colocated on the linode |
| **guvnah** | desktop cockpit → re-scoped to the operator's chair (§4); revive on its own forcing case + operator joy |
| **maude** | terminal/operator interface (working) |
| **vscode-governor** | sleepy little gremlin; let it sleep honorably |
| **phosphor** | fleet/crosstalk surface, enters at N2 when multiple instances exist |

**The slice is `webui-vocabulary-refresh`, not "make dashboard."** The
clients predate this month's vocabulary — expected rot: `loop_receipt`,
`audit_receipt`, `origin_mode`, `confusion_receipt`, `clock_witness`,
`policy_ref`, `coverage_gap`, `known_baseline_noop`, `remediation_attempt`,
`budget_exhausted`. Probe before architecture: clone gov-webui (NOT on this
machine — see grounding survey), run the contract tests, learn exactly which
RPC surfaces rotted. Maybe it renders generic JSON tolerably and needs only
labels/grouping/filters and a few receipt-specific cards. Present James must
stop trying to out-design Past James while standing on Past James's roof.

Don't revive all five: reviving surfaces because they exist is the quarry;
reviving them because a demo points at them is the chisel.

---

## 3. The component register — one source, two projections

The hub's topology map and guvnah's constellation panel must project from
**one register** — that's the anti-séance mechanism. Card schema (supersedes
the hub v1 five-field skeleton when next touched):

```text
name / role / status: active|dormant|deprecated|unknown / surface type
canonical repo+path / contract+schema version / last verified
known drift / next forcing case
```

> **The launch site doubles as the operator's loop.json.** Public map,
> private re-entry probe, same artifact class.

Two audiences, one artifact: strangers ("what is this constellation?") and
future-you ("what exists, what's dormant, what's stale, where do I touch
it?"). This would have prevented the guvnah séance — and the séance is the
proof of need: **the estate has exceeded human ambient recall**, which is not
a personal flaw; it is literally the failure class the system addresses. The
operator is now one of the operators.

---

## 4. Guvnah v2 — the operator's chair

Honest budget line first: "I like the idea and want to see what it looks
like" is legitimate fuel, and it points at a genuine hole. webui = per-daemon
surface; phosphor = future fleet surface; maude = working console. Missing:
**the surface for the role this month defined the operator into —
ratification authority and attention-budget holder.** Guvnah v1 was a daemon
cockpit. **Guvnah v2 is where the human-in-the-loop sits.** Design follows
from that sentence:

- **Center of screen = the nod queue, not metrics.** Custody-affecting forks,
  HALT_FOR_RATIFICATION, deviation receipts awaiting ruling, batched
  clarifications — each a *decision card*: what's asked, why it blocks,
  evidence links, options with consequences, one-tap ratify/override/park.
  Success metric: the morning audit takes five minutes from the couch. Most
  dashboards are activity theater; this is an inbox of authority.
- **Default state = correctly bored, with evidence** (demo-2's insight on the
  operator's own glass). Not green tiles (a mood), not an empty void
  (ambiguous): "Nothing needs you — 0 pending nods, coverage intact 4/4
  instances, last heartbeats ⟨times⟩, 14 events classified known-baseline
  overnight, 0 deviations." Empty-state copy: *"I would prefer not to bother
  you."* — with receipts proving the preference is informed. Bartleby as a UI
  state.
- **Loop panel = loop.json, alive.** Phase, current slice, transition
  receipts, backlog depth by tier, and the **burn-per-progress sparkline** —
  the flail detector made glanceable; one curve says productive-or-
  archaeological before reading a receipt. Confusion receipts amber;
  correlated confusion red.
- **Constellation panel = the component register rendered** (§3; same source
  as the public site). Click a node → recent receipts + policy refs.
- **Budgets panel — including the dash metering itself.** LA ledgers, retry/
  confusion budgets, model-window state — and the attention ledger *spent by
  the dash*: "interruptions today: 1/5." Every push is an interrupt drawn
  against the operator's budget; a dashboard that accounts for its own cost
  enforces the notification ladder structurally (escalations per ladder,
  clarifications batched, never a drip). The differentiator from every
  pager-shaped product ever built.
- **Doctrinally load-bearing: guvnah is the presence surface.** Keep
  "observes, doesn't generate" (chat namespace stays dark), but nods through
  guvnah carry **operator-present provenance** — the inverse of the
  maude-orchestration bug (agents must not enter through presence-implying
  surfaces; a human at the desktop keyboard is the closest thing to presence
  evidence the system has). Optionally freshness-checked (ratify button
  requires live interaction, not a stale session) — presence-witness,
  lightweight, honest about its evidence model. The day-one witness table
  gets its presence surface.

**The design spec is operator-owned, not loop-delegable** — the operator
designing the operator's chair is the point (and the fun). The loop builds
it afterward.

---

## 5. What the chair forces, in two grades

**Seeing remote NQ = the cheap force, already designed.** Guvnah needs
testimony, not connections: N0–N2/N3 crosstalk replicates streams inward to
the local NQ; guvnah queries the replica. Eventual consistency is fine for an
operator map — better than fine, because honesty falls out of existing
doctrine: **every remote claim renders with its model age** ("plex: coverage
intact, *as of 4m ago*"). The chair displaying the staleness of its own
picture is clock-witness discipline as UI; no dashboard on earth does this
and the receipts already carry the fields. Consequence: **N0–N2 is now a
guvnah dependency, not merely tier-2-high** — its forcing case fully arrived
from "the chair needs to see the estate," which is how forcing cases are
supposed to arrive.

**Acting at distance = the expensive force, with a beautiful first key.** A
nod on a remote HALT is an operator-attested claim traveling OUTWARD → signed
envelopes → X1 → the standing-granted-key ceremony. **The inaugural grant is
the operator's own ratification key — the first standing-backed identity on
the wire.** Root fiat becoming the first signed speaker is the right
bootstrap order: the key hierarchy starts where the authority actually
starts; every component key after is downstream of an existing precedent.

**Phased path (guvnah waits on none of it):**

```text
Phase 1 — local chair:  sushi-k's own loop/repos/budgets/nod queue; zero
          network; linode visible via interim means, MARKED interim.
Phase 2 — fleet eyes:   forces N0–N2/N3; heartbeats + selected streams
          replicate inward; topology panel live with model ages; demo-2's
          correctly-bored view watchable from the chair.
Phase 3 — remote nod:   forces X1; operator key granted; signed ratification
          envelopes outbound. Honest interim until then: guvnah SURFACES the
          remote HALT; the nod happens over ssh; the receipt records
          cli_origin. Degraded, marked, true.
```

Sequencing: launch → N0–N2 (guvnah dependency) → guvnah phase 2 + demo-2
(they share the linode work) → X1 when the first remote HALT actually demands
a couch-nod. The chair pulls the network forward exactly as far as sight
requires and not one envelope further. The want stays fun; the forcing stays
honest.
