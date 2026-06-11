# Next steps — builder ratchet (queued, not acted on)

Filed 2026-06-10 after Tick 2. Recording only — no implementation. Three forward threads,
in rough priority order.

## 1. Tock 2 — session-attributable promotion (forced by GAP-N)

See `working/candidate-tock-2-session-attributable-promotion.md`. The concrete next
tock. Plan with Fable/Opus (subtle failure mode); execution may downgrade.

## 2. Model ladder as fit-for-purpose ensemble routing

Tick 2 confirmed downgradeability is real (Sonnet shipped from a sharp packet). The
ladder is not just cheap→expensive; it's **fit-for-purpose ensemble routing**. Four
executor/reviewer classes, each answering a *distinct question*:

```
Qwen (local, Mac mini):  Can a cheap local executor perform this mechanical packet?
Sonnet:                  Can a mid-tier agent ship this implementation w/o judgment calls?
Codex / Gemini:          Does an INDEPENDENT agent find the same patch / gap / concern?
Opus / Fable:            What is the right plan, boundary, or doctrine interpretation?
```

**Anti-zoo rule:** add another model ONLY when it answers a distinct question. Avoid five
raccoons fighting over one keyboard.

**Codex/Gemini are cross-checkers, not default executors:**
```
After Sonnet ships:
- Codex reviews diff for missed tests / unsafe changes
- Gemini reviews packet ambiguity / alternate implementation
- Neither may edit unless explicitly assigned
```

**Tick-report addendum (extends the packet verdict):**
```
Model used:
Why this tier:
Could a lower tier have done it:
Independent reviewer used:
Reviewer disagreement:
Next downgrade target:
```

**Baby-step for Tick 3** (ladder is earned by attempts, not declared):
```
Try Qwen (mini appliance) first on a very mechanical cargo item.
If Qwen stalls or drifts, escalate to Sonnet.
If Sonnet ships, optionally ask Codex/Gemini for read-only review.
Record where each tier failed or helped.
```
Composes with memory `feedback_model_tier_routing` and the Tier-0 appliance
(`working/tier0-appliance-mini.md`, Qwen `qwen2.5:3b` live at `192.168.69.15:11435`).

**Codex standing (parked):** Codex's three roles (chat / reviewer / executor) now have a
formal standing model — `working/CODEX_RATCHET_STANDING_GAP.md`. Kernel rule: *capability
does not imply standing; each role earns standing at its consumption boundary.* Build
order when thawed: reviewer first (smallest ratchet-safe increment), then chat reporting,
then executor adapter (only on a forcing case). **No generic "Codex adapter" — chat asks,
reviewer judges, executor mutates.**

## 3. Cross-project GAP-SPEC dependency sweep (Fable-lane audit)

Two scopes, both **audit only — map, not fixes. No implementation, no commits, no
BuildPetition schema, no speculative pipeline features.**

**3a. Broad:** sweep all GAP SPECS across constellation projects (agent_gov
`working/GOV_GAP_*` + `specs/gaps/`, NQ `docs/working/gaps/` ~40, others) and sort out
**inter-gap dependencies** — which gap blocks which, across repos. Deliverable: a
cross-project gap-dependency map. (Note: respect per-repo Claude ownership — map deps,
don't edit other repos' gaps. memory `feedback_cross_repo_pm`.)
> **Partly DONE 2026-06-10:** the gap-backlog VALIDATION pass ran (codex inventory's 234
> entries verified against repo state) — `working/gap-backlog-triage-2026-06-10.md`.
> Result: inventory ~40% mislabeled (140 CONFIRMED / 70 STALE / 20 WRONG / 4 NEEDS-HUMAN);
> systematic error classes characterized; 4 NEEDS-HUMAN operator calls surfaced. Still
> NOT done: inter-gap *dependency* mapping (which gap blocks which) — the triage validated
> status, not deps.

**3b. Scoped (do first): builder-ratchet readiness audit.** Inspect the tick/tock
campaign, Maude supervision path, NQ promoted-patch state, agent_gov artifacts, backlog
candidates. Questions: what's dirty/promoted/uncommitted/doc-only? what deps should've
been groomed before each tick? which gaps are true blockers vs adjacent debt? what's the
minimal readiness checklist before future ticks? what's safe Tick 3 cargo? what must NOT
be touched yet? Three tables:
```
1. Current-state inventory: repo | dirty files | promoted artifacts | docs | tests-last-known | risk
2. Gap triage:             gap | source tick | severity | blocker? | proposed tock? | defer reason
3. Backlog readiness:      candidate | deps | blast | revert | test cmd | model tier | ready y/n
```
Keep the distinction sharp: Tock candidates (cite a tick gap) vs pre-tick rake grooming
vs future ladder-climbing. **Do not let "go through everything" become "fix everything."
It's a map.**

## Guardrails (all threads)

- No implementation / commits / pushes from the audit threads.
- Tick/tock rule holds: a tock must cite a tick gap.
- Unblock surgically; don't turn inspection into a campaign.
