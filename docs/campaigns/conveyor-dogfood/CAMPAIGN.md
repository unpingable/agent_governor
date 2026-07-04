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
