# Campaign — conveyor dogfood ("infrastructure, used as such")

**Filed:** 2026-07-04. **Operator seed:** "if I've built infrastructure, not
just another harness, it's time to use it as such."

## What this campaign is

Composes three built pieces into a working governed-execution loop and proves
it on boring, self-referential work:

- **AG playbook conveyor** (landed from `feat/playbooks-gov-loop` +
  `feat/playbooks-synthetic-conveyor` — see [LANDING.md](LANDING.md)) — the
  governance/admissibility object: QueuedPlaybook (per-item
  `operator_approved` latch, path fences), ReviewPacket (`used ≤ granted`
  structural), ReviewPacketValidator, sealed HandoffRenderer,
  ActorOutputNormalizer (actor cannot green its own gate), RationCard
  (allowlists + locked axes), durable/replay-safe spend, Wicket
  admission-as-evidence.
- **maude M-1 plan envelope** (`~/git/agent_gov_ui/maude/docs/specs/
  plan-envelope-v0.md`, CANDIDATE) — the execution-instance object: what exact
  approved work instance runs, where, by what backend, under what local
  constraints, with what receipts.
- **governed-shell decision desk** (maude GS-10b legs 1–3c; GS-11 data layer)
  — the operator's approval/visibility surface.

The loop:

> backlog item → (compile) candidate plan envelope citing AG playbook law by
> digest → explicit operator approval → bounded run → review packet → **two
> separate receipt surfaces** (AG governance exercise ∥ maude envelope
> enforcement).

## Core invariants (operator-ratified 2026-07-04, verbatim intent)

1. **Maude can manufacture candidate structure. It cannot manufacture
   authority.** A maude-generated plan is never self-authorizing; authority
   enters via operator approval of the envelope and/or already-minted AG
   admission, cited by digest — separately named.
2. **AG authorizes/bounds the work SHAPE; maude enforces the approved run
   INSTANCE.** A valid AG playbook does not prove maude enforcement; a
   successful maude run does not prove AG playbook semantics. One run, two
   test surfaces, two receipt surfaces — neither self-certifies the other.
3. **Hybrid envelope (ruling #1).** M-1 stays maude's execution-instance
   contract and gains a `governance:` binding block citing AG law by
   digest/ref — never by importing AG internals. Constraint-projection rule:
   when maude enforces constraints originating in AG, the envelope records
   BOTH the resolved constraints enforced AND the AG object/digest they were
   projected from. "M-1 is the ticket with teeth; AG is the law that made the
   ticket valid."
4. **Branches are staging, not jurisprudence (ruling #2).** No dogfood run may
   cite unlanded branch law. Landing ≠ operational promotion — surface
   classification lives in [LANDING.md](LANDING.md); C11/seccomp/H2-dependent
   paths stay inert; no live sandbox/autopilot authority is implied by merge.
5. **No approval-by-narration.** A candidate plan is not executable until
   resolved by explicit operator action (conveyor `operator_approved` latch or
   M-1 human-submitter inline approval; synthetic submitters are zero-resolve
   — propose only).
6. **Oatmeal first (ruling #4).** Specimen ladder: (1) `state-index-roadmap-
   kind` (pure-AG, mutating, self-referential) → (2) playbook docs
   normalization (maude-driven, two surfaces) → later: Night Shift, cross-repo.
   First runs must not touch: v7 promotion, C2 rulings, LA fence, GS-2b
   admissibility, daemon contract changes, app.py surgery, doctrinal judgment.

## Architecture framing (operator, 2026-07-04 — strategy context, NOT a fence change)

**Maude is the DevOps frontend for governed infrastructure work.** Not an
agent harness, not Night Shift, not NQ, not AG — the operator/execution desk
where bounded infrastructure work becomes visible, approvable, executable,
and receipted.

Layer split (the eventual product shape):

| organ | answers |
|---|---|
| **AG** | is this work admissibly bounded? (playbooks, ration cards, review packets, authority boundaries) |
| **maude** | execute this approved bounded work instance (envelopes, runs, receipts, obstructions, operator decisions) |
| **NQ** | did the world actually change/recover? (pre/post witnesses) |
| **Night Shift** | is this eligible to run unattended? |
| **Porter** (later) | what ran where, with what transcript/artifact custody? |
| **Human** | promote / rule / approve where authority is needed |

Existing ops tools (Ansible/Salt/systemd/docker/ssh) remain execution
**backends** — maude manages approved infrastructure work; it does not
generally manage servers. Eventual workflow targets: release deploys, server
updates, restarts, config refreshes, certificate rotation, drift repair,
rollback/verification, chaos experiments under declared blast radius — each
with NQ pre/post witnesses and known-rollback fences.

**Promotion ladder (each rung explicit; clearing a rung promotes the PATTERN,
never grants general execution authority):**
1. CD-2 — one tiny self-maintenance mutation through the conveyor (this
   campaign's specimen 1);
2. CD-4-class — second AG chore (docs normalization);
3. maude M-2 compiles/loads envelopes citing AG conveyor objects;
4. maude executes only approved conveyor-backed envelopes;
5. cross-repo dogfood (AG queue item with a target_repo ≠ AG);
6. NQ-backed service specimen (remediation with pre/post witnesses);
7. Night Shift consumes the same approved-envelope machinery unattended;
8. real ops (deploys/updates/restarts/rollbacks/drift repair).

What clearing CD-2 means, verbatim intent: *"this queue/fence/approval/review
shape is admissible enough to reuse for the next bounded specimen"* — never
"the system may now decide and execute work." Work intake shifts from
"Claude, please clean this up" to "Queue `chore.foo` under playbook X with
these paths/tests/stops, output ReviewPacket only."

**End-state legibility (operator, 2026-07-04):** the mature loop is
Claude-as-middle-manager driving maude with good plans (the M-1
`synthetic_agent` contract: compile, propose, zero-resolve — writes the memos,
cannot sign the checks), and then **humans driving the same machinery without
the custom vocabulary**. The internal law keeps its precise names
(QueuedPlaybook, ReviewPacket, ration card); the DESK must translate them
into ordinary work language — "approve this bounded task," "review what came
back," a plan as plain markdown. Vocabulary opacity at the operator surface
is a defect, not a mystique. This is an acceptance criterion for maude's
screens and M-4's run report, not a new slice here.

## Stop-lines (campaign-wide)

- Maude plan selection counting as authorization → STOP.
- AG playbook validity used as evidence that maude enforced the run (or vice
  versa) → STOP.
- Any slice needing a new daemon RPC / feed decision kind / kernel refusal
  kind → out of scope here (CT-1 / M-7 lane, own ratification gate).
- Specimen drift into taxonomy redesign or doctrine interpretation → STOP,
  obstruction note per ROUTING.md.

## Slices

See [NEXT.md](NEXT.md) (six-field shape per `docs/roadmaps/ROUTING.md`).
Status: [STATUS.md](STATUS.md). Rulings: [DECISIONS.md](DECISIONS.md).
Landing record: [LANDING.md](LANDING.md).
