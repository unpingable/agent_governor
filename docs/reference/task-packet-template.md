# Task Packet Template

**Status: PROVISIONAL** (landed 2026-06-10, not yet ratified; refined per-tick by the
model-suitability evidence each tick records). Glossary status vocabulary:
`docs/reference/internal-ops-glossary.md`.

A **task packet** is the brief handed to a builder (a supervised agent session, or
eventually a cheaper/local model). Its job is to carry enough structure that the
*weakest model that could do the work* can do it **safely** — without semantic drift,
without needing the operator to fill gaps mid-run, and with a self-checkable
definition of done.

This is the lever in the downgradeability ratchet
(`working/campaign-tick-tock-builder-ratchet.md` § Standing objectives; memory
`feedback_model_tier_routing`): when a weaker model can't run a packet safely, the fix
is usually a **missing packet field, not a bigger model**.

> Intelligence we can move out of the model and into the packet is intelligence we
> stop paying frontier prices for.

## Fields

Seed instance: Tick 1's brief (`.tick/tick01-task.txt`). The three gaps that brief
exposed (retro-recorded in `working/tick-01-nq-masthead.md` deliverable 6) are baked
into the fields below as the first round of template improvement.

1. **Objective** — one or two sentences. What changes and why, in the executor's terms.
2. **Scope fence** — explicit path allowlist (e.g. "only `crates/nq-monitor/src/...`
   and `crates/nq-monitor/tests/`"). The fence must be *expressible to whatever gates
   the session*, not just live in the operator's head (Tick 1 GAP-C/L: a file-granular
   fence can't tell "added a test" from "weakened a pin" — see field 5).
3. **Forbidden moves** — the never-do list. Commits, pushes, network fetches, touching
   files outside the fence, widening closed vocabularies, implementing adjacent
   proposals. Be concrete; "don't break things" is not a forbidden move.
4. **Verification commands** — the *exact* command(s), copy-pasteable, run from a stated
   cwd. Each with its **expected outcome** (see below). For Tick 1 this was
   `cargo test --all --locked` from the repo root.
5. **Expected verify output / known-green baseline** — the string or shape a *pass*
   produces (e.g. "all suites `test result: ok`, exit 0"), so the executor can
   *self-check against a known baseline* rather than *assert* success. This is the
   single biggest downgrade-safety field: it converts "tests pass" from testimony into
   a checkable claim (NLAI applied to the packet). If a step modifies pinning tests,
   say so explicitly: "additive tests only; do not modify existing pins without
   flagging."
6. **Acceptance criteria** — numbered, each independently checkable. Style seed: Tock 1's
   acceptance table (`working/tock-01-fail-closed-gate.md`) — one row per criterion,
   each with its own evidence.
7. **Reversibility / rollback** — how to undo if a step goes wrong. For revertible
   workspaces: "git checkout the touched files." For anything irreversible: say so up
   front and mark it stop-and-ask (field 8).
8. **Stop-and-ask clauses** — "stop and ask if X." The explicit list of conditions under
   which the executor must halt and hand back rather than improvise: ambiguity in the
   spec, a needed change outside the fence, an irreversible step, a failing verify it
   can't resolve in one retry.
9. **Source authority** — where the work item came from (operator fiat, a backlog
   item, a cited gap). Recorded so a later audit can answer "who authorized this?"
10. **Model tier attempted** — which tier this packet is being handed to (see rubric).
    Recorded so the suitability block can report drift/sufficiency against intent.

## Sizing rubric

Mapped to the **existing** `ModelTier` names in `src/governor/routing.py:38-63`
(`LOCAL`/`FAST`/`STANDARD`/`HEAVY`). This is a **prose checklist for humans writing
packets, not a typed enum to dispatch on** — do not promote it into code as an
`ArtifactKind`/`TaskKind` enum (tripwire: memory `feedback_kind_fit_is_guard_not_enum`).
Difficulty is one axis; `feedback_model_temperaments` is the orthogonal *direction*
axis.

- **LOCAL** (Qwen-class on the Tier-0 mini appliance, or similar): mechanical, fully
  fenced, single file or module, verify is one known-green command. Fixtures, grep/
  report passes, enum widening, format/lint fixes, docstring sweeps. No naming or
  vocabulary decisions; no cross-module reasoning.
- **FAST / STANDARD** (Sonnet-class): ordinary implementation inside a clear fence;
  tests exist or are fully specified in the packet; the shape of the change is known.
  Tick 1's fenced, test-pinned UI patch is borderline STANDARD and a live downgrade
  candidate. No vocabulary/naming decisions.
- **HEAVY** (Opus): cross-module plumbing, test repair, refactors, tracker/docs
  maintenance — most Tock-class implementation work (e.g. Tock 1's fail-closed gate).
- **Fable / operator** (not a tier — an escalation): conceptual seams, gap-list
  interpretation, "is this laundering?", HIGH-cadence ratification, post-run synthesis,
  weird architectural judgment. Never the baseline hammer.

## The downgrade test

For any packet, ask:

> Could a weaker/cheaper/local model execute this packet without semantic drift?

If **no**, the next move is to name the **missing packet field** (almost always: a
fuzzy fence, a missing expected-output baseline, an unstated forbidden move, or a
judgment call smuggled into the cargo) — *then* decide whether the work is genuinely
conceptual (escalate) or just under-specified (improve the packet). Record the answer
in the tick's **packet verdict** (the model-suitability block — campaign card § "Tick
deliverables: three verdicts"); accumulated answers are what later license building the
model ladder.

## Not built (deliberately)

- No packet *schema* in code, no validator, no enum. This is a prose template.
- No scheduler / router wiring. `routing.py` + `lanes.py` already hold `ModelTier` and
  `LANE_CONTRACTS` (library-only); wiring them is a later ratchet leg opened only after
  several ticks of suitability evidence — not speculatively (memory
  `feedback_yagni_scope`).

## Composes with

- `working/campaign-tick-tock-builder-ratchet.md` — standing objectives + the
  two-verdict ratchet. A packet's acceptance criteria feed the **cargo verdict**; the
  **dogfood verdict** is operator-side and never delegated to the executor — an agent
  grading the pipeline that gates it would be self-amendment-adjacent.
- memory `feedback_model_tier_routing` — the routing rule of thumb this serves.
- memory `feedback_model_temperaments` — the direction axis (this is the cost axis).
- memory `feedback_kind_fit_is_guard_not_enum` — why the rubric stays prose.
- `docs/reference/internal-ops-glossary.md` — status vocabulary; and the
  documents-vs-procedures pin (a packet is a *procedure-shaped* artifact: it binds
  action to condition — though packet ≠ ratified procedure).
