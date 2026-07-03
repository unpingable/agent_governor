# The governed session loop — UX design (maude 3.0 "the desk")

**Status:** RATIFIED (2026-07-02, operator-paired design; campaign
`docs/campaigns/governed-shell/`). Normative for GS-10..GS-15 and the web
mirror (GS-17).

## Thesis

Claude Code is easy because the entire product is one input box and one
stream, and decisions are one keystroke. Maude 3.0 matches that shape exactly,
then adds precisely two things it doesn't have: **a queue** (decisions that
accumulated while you weren't looking) and **a margin** (receipts that
accumulate while you are). Governance never appears as a mode or a wizard —
it appears as *items* and *ink*.

Acceptance frame for every screen: *"as easy as Claude Code while refusing
what Claude Code wouldn't."* Launch = sentence + Enter (parity). Watch =
stream (parity). Approve = `y` (parity). Steer = type at the running agent
(parity, via send_input). The deltas: murky launches cost two inline
questions (profile-tuned); lab work costs one diff review at the end;
everything leaves ink. That is the whole friction budget — and every friction
point routes somewhere.

## 1. The home surface: "the desk"

```
┌─ AG ● healthy │ envelope: established │ 2 sessions ● 1 waiting │ queue: 3 ─┐
│  QUEUE                                                                     │
│  ▸ ⚡ intervention  sess_a3f2  0:47 left   Bash: rm -rf build/  [y]es [n]o [w]hy │
│    ◆ promotion     sess_9c01  done        +214 −12, 6 files    [enter] diff     │
│    ? admissibility (launch)   —           2 questions before "migrate DB" runs  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  > _                                                          [? for keys]  │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Top strip (ambient, never interactive):** daemon health · autonomy
  envelope name (+ active widening grants with expiry) · session counts with
  waiting-on-you count · queue depth. Fed by `operator.watch`; always true.
- **Center: THE QUEUE** — the unified decision feed. Center of gravity.
- **Bottom: the command line** — single input, Claude-Code-shaped.

**Focus (D-GS-1, ratified):** queue-first when items pend; command-line when
empty. `Tab` flips. First keystroke on an empty desk is the first letter of
your task: `fix the flaky retry test in ingest/` + Enter = the whole launch
ceremony (`runtime.session.create`+`launch` with the workspace autopilot
profile + budget defaults; screen slides to the session view, streaming).

**Launch-time governance (the admissibility moment):** if AG's admissibility
assessment pushes back (high-severity unknowns), no modal appears and nothing
refuses to exist — the session is created **HELD** and the queue gains
`admissibility_question` items (VoI-ranked, answered inline with short text).
Answering the last one releases the launch. This is the surviving soul of
PLAN/BUILD spec-lock, relocated into AG and rendered as flow. Profiles tune
it: `greenfield` skips pushback, `production` forces it.

## 2. Screens (ScreenManager: four screens + overlay stack)

1. **Queue home** (`q` / `Esc` from anywhere). `j/k` select, `Enter` expand,
   item-scoped verb keys resolve (see §3).
2. **Session view** (`Enter` on a session, or `1..9`). Left ~80%: transcript —
   canonical events as a stream, tool calls collapsed to one-liners
   (expandable). Right margin: the **receipt rail** — glyphs ticking in as
   receipts land (auto-approved reads, budget ticks, scars). Bottom: steering
   line — sends `runtime.session.send_input` to the RUNNING agent; disabled
   with a visible reason when the adapter lacks the capability. Status line:
   this session's envelope —
   `established · reads auto · writes ask · comms always ask · budget ▓▓▓░ 62%`.
3. **Sessions board** (`s`). N sessions as rows: status glyph ·
   current-activity one-liner · pending-decision count · budget bar.
   **Waiting-on-you sorts to top.** You don't watch N transcripts; you watch
   one board and the queue. Transcripts are for diving.
4. **Diff view** (from a promotion item). The ONLY full-screen takeover,
   opt-in: syntax-colored unified diff + receipt margin summarizing the
   session's governance history (violations resolved, exceptions granted,
   budget spent). `y` promote / `n` reject / `w` why.

**Overlays (never steal the screen):** why chain-walk (`w` on any
item/receipt/refusal — ChainLink list with DRILL/REPLAY/SYNTHETIC render
prefixes, `j/k` walks), help (`?`), command palette (`:`).

## 3. Keybinding philosophy: the card teaches its own keys

- **Global verbs, constant everywhere:** `y` approve/yes · `n` deny/no ·
  `w` why · `q` queue · `s` sessions · `?` help · `:` command · `Tab` flip ·
  `F` fork-to-lab.
- **Item-scoped option keys are printed on the card**, sourced from the
  decision envelope's `options[].key` (`[f]ix [r]evise [p]roceed`; docket
  `[s]ustain [a]mend [g]rant-exc [v]erify [d]ismiss`). **The daemon's
  vocabulary IS the keymap** — no shell-invented verbs. Memorization
  optional; muscle memory develops for y/n.
- No chords, no leader keys, no vim modes. Text entry only in the command
  line and inline answers.

## 4. The decision moment: interrupt vs accumulate

**Interrupts** (bell + red highlight; focus-steal only on the home screen):
- COMMUNICATE-class interventions (external effects — the one thing that
  can't be walked back),
- interventions within 60s of auto-deny timeout,
- refusals that block a session's progress.

**Accumulates silently** (queue badge + receipt rail): everything else —
READ auto-approvals, receipts, budget ticks, non-blocking violations parked
to docket, finished-session promotions (work is done; no urgency).

Timeout pressure is honest: countdowns render live from the watch stream, and
AG's auto-deny-on-timeout stays AG-owned — **walking away is always safe,
never silently permissive.**

## 5. Refusals: legible + actionable

A refusal card renders exactly four things: the verbatim daemon refusal · the
gate name · `[w]hy` (chain-walk) · **the named next safe move** — from a
shell-side route map keyed on AG's CLOSED refusal vocabulary (closed set ⇒
the map is enumerable and testable, GS-13):

| refusal class | routed move |
|---|---|
| lab-gate / capability refusal | `[F]ork to lab` |
| budget exhaustion | `[F]ork with new budget` |
| scope refusal | `[e]scalate scope (receipted, time-boxed)` |
| admissibility pushback | answer inline |

Routes PROPOSE; the operator acts. A refusal that dead-ends is ceremony; a
refusal that routes is flow. Refusal semantics never leave AG.

## 6. The escape hatch (visible + receipted)

Already built as substrate: `runtime.session.fork` + lab gate + promotion
custody with baseline fencing (GAP-N). The design compresses it to one
keystroke: `F` forks into the lab envelope; such sessions carry a `⚗ lab`
badge in the strip; crossing back IS the promotion queue item + diff view.
Never silent — the promotion resolve is the receipted crossing.

## 7. Autonomy widening (graduated autonomy, v0)

The envelope is always visible (top strip + session status line). Widening is
a receipted one-liner: `: widen bash-tests 7d` → `scope.escalate` (existing:
receipted, time-boxed via ttl→expires_at) → the strip changes visibly with an
expiry badge. Scars shrink it back and that renders too (queue info item +
strip change). Zero daemon work in v0.

**v1 (PARKED, D-GS-4):** AG-minted widening offers from docket precedent
accumulation arriving as queue items. Offers must be **AG-minted, never
shell-synthesized** — a shell that decides what widening to offer has become
an authority source.

## 8. Day in the life

**08:40.** `maude`. The desk renders: `AG ● healthy · established · 2
sessions · 1 waiting · queue: 3`. Focus on the top item: a promotion from
`sess_9c01` (yesterday's lab fork). `Enter` — full diff, +214/−12, receipt
margin shows one violation fixed, one scoped exception expired at 02:00. `w`
walks the exception's chain: grant → spend → receipt. `y`. Promoted; ink in
the margin. Next: a docket case parked overnight (stale claim freshness) —
`[v]` reverify, ruled, precedent recorded. Third: an intervention that
auto-denied at timeout overnight — rendered as info, not a demand; the
session paused safely. Skim its transcript, type into the steering line:
*"skip the S3 upload, write the artifact locally instead"* — the agent
resumes on the new course. **Triage: ninety seconds, three keystrokes and a
sentence.**

**08:45.** `Tab`. `migrate the ingest DB schema to v4, dry-run first`. Enter.
The queue grows an admissibility card — production-adjacent, two questions:
*"Is downtime acceptable during dry-run? Which environment is authoritative
for v3 schema?"* Two short inline answers. The session launches
held-then-released under the `production` envelope — writes ask, comms always
ask.

**09:10.** Bell, red card: COMMUNICATE — the migration session wants to
`curl` the staging metrics endpoint. Countdown 4:58. `w`: verifying row
counts post-dry-run. `y`. Back to real work in another window; maude needs
nothing.

**12:30.** Queue: 2. A scope refusal — the session touched
`infra/terraform/`, outside envelope. The card names the gate and the route:
`[e]scalate scope`. Operator instead types `: widen infra-read 2h` —
read-only widening, receipt lands, strip shows
`established +infra-read (1:59)`. Session resumes. Second item: the steered
morning session finished — diff, `y`.

**18:00.** `s` — board quiet, one promotion. Diff, margin, `y`. Laptop
closes. Nothing in the constellation is waiting on a config file, a buried
approval, or an unreceipted grant. Everything that happened is ink; everything
that couldn't happen routed somewhere visible.

Governed — and it never once felt like ceremony.
