---
audience: repo-local
status: draft
---

# GOV_GAP_CONTINUITY_HYGIENE_001

Status: draft
Owner: Governor
Type: hygiene / passive-enforcement gap
Drafted: 2026-04-20

## 1. Problem

Continuity exists, but continuity usage is currently discretionary. In
practice that means continuity-sensitive work is often performed from
local thread state alone. The tool is available; the path does not
require or even reliably encourage its use.

This creates four recurring failure classes:

1. **Cross-session amnesia** — prior project state exists but is not
   consulted.
2. **Silent supersession** — a new conclusion replaces an older one
   without parentage or explicit supersede linkage.
3. **Local-only reliance** — the agent makes rely-like claims or
   recommendations from current-context memory alone.
4. **Writeback omission** — a session produces durable state worth
   preserving, but no continuity commit happens.

The issue is not storage correctness. The issue is that continuity is
not yet on the hot path.

## 2. Goal

Make continuity hygiene structural and visible for continuity-sensitive
actions.

In v1, the system should:

- automatically preflight continuity on selected action classes,
- receipt whether preflight happened and what it found,
- emit hygiene findings when continuity-sensitive work proceeds without
  continuity basis,
- remain passive: no denials, no hard failures.

## 3. Non-goals

This gap does **not** propose:

- requiring continuity for all interactions,
- merging Governor and Continuity into one subsystem,
- blocking observe-only work,
- relying on model self-report such as "memory mattered here,"
- declaring final admissibility rules before passive-mode evidence
  exists.

## 3A. V1 scope note

This gap addresses continuity hygiene on **governed daemon/client paths
only**.

It does **not** solve chat-path continuity omission, which is currently
the dominant practical failure mode. Chat-path interception,
classification, and receipting remain follow-on work and are tracked as
an open question (Q7) rather than implied by this gap.

Filing the boundary explicitly because the spec would otherwise quietly
overpromise on the failure mode that motivated it. v1 instruments the
surface where action classes can be inferred mechanically; chat-path
hygiene wants its own gap once daemon-path evidence exists.

## 4. Core principle

**The path remembers Continuity on the agent's behalf.**

Continuity hygiene is enforced by wrapper / hot-path behavior, not by
prompt etiquette or model goodwill. The model is not asked to remember
that continuity matters; the surface infers continuity-sensitivity from
the action class and acts on the model's behalf.

## 4A. Cross-references

This gap builds on already-shipped Governor machinery and must not
introduce parallel concepts.

- **Standing classes / doctrine** (`docs/doctrine/standing_and_receipts.md`,
  ADR 0006). Continuity hygiene is relevant at the point where work
  crosses from OBSERVE / INTERPRET into RECOMMEND / AUTHORIZE-shaped
  reliance. The load-bearing boundary is not "memory is useful," but
  "prior-state consultation matters to the legitimacy of the action."
  Continuity hygiene fires above the RECOMMEND threshold; pure observe
  and pure interpret stay cheap.

- **`session_continuity.py`**. This gap is partly about moving session
  continuity from discretionary usage (CLI commands, ad hoc capsule
  resume) to hot-path usage on selected governed surfaces. The storage
  and retrieval primitives already exist; what is missing is the
  governance contract around when consultation is expected.

- **`gate_receipt.py`**. Continuity hygiene artifacts must be emitted
  through the existing content-addressed receipt path using a dedicated
  gate value (`gate="continuity_hygiene"`), **not** a parallel ad hoc
  receipt format. The illustrative shape in §8 below is the *evidence
  bundle* for such a receipt, not a new receipt class.

- **External Continuity MCP scope**. The `agent_gov` continuity scope
  is the read/write target. This spec governs the contract between
  governor and that scope; it does not redefine continuity storage
  semantics.

- **Hook integration seam — `contctl`, not MCP**. Claude Code hooks
  fire shell commands, so model-side hook integration runs through a
  `contctl preflight --scope <s> --action <action_class>` verb (sugar
  over `memory_query_latest` + `memory_explain` that emits the
  hygiene receipt shape), not MCP. MCP remains the model-facing tool
  surface; daemon RPC remains the cross-project client surface; the
  hook seam is a third path that needs its own thin wrapper. This is
  wrapper work, still Governor-jurisdiction.

## 5. Architectural boundary

This gap spans both Continuity and Governor, but the responsibilities
remain distinct:

### Continuity owns

- query / retrieve / commit / supersede mechanics,
- storage and retrieval surfaces,
- basis object representation.

### Governor owns

- which action classes require continuity hygiene,
- how continuity preflight/writeback are receipted,
- which omissions are findings,
- later: which omissions become inadmissible.

The system must not collapse "continuity available" into "continuity
consulted," or "continuity consulted" into "continuity relied upon."

**Governor classifies; Continuity returns rows.** Conflict, taint,
basis-adequacy, and rely-class judgments are Governor-side derivations
over the rows Continuity returns. Continuity does not return verdicts;
Governor does not store memory.

## 6. Action classes

Continuity hygiene only applies to explicitly continuity-sensitive
action classes.

Initial candidate classes:

1. `resume_project_state` — continuing an already-running project, repo
   task, spec thread, or draft line of work.
2. `prior_decision_claim` — asserting that "we decided," "we already
   established," "the current plan is," etc.
3. `supersede_prior_conclusion` — refining, replacing, or narrowing an
   earlier claim or recommendation.
4. `cross_time_delegation` — packaging state for later self / agent /
   handoff use.
5. `rely_like_recommendation` — recommendations or plans whose
   legitimacy depends on prior state, not just current prompt contents.
6. `session_close_writeback_candidate` — sessions that produced project
   state likely worth preserving durably.

Observe-only discussion and fresh brainstorming are out of scope for v1
unless they cross into one of the above classes.

## 6A. Action classification surface

In v1, continuity-sensitive action classification is attached to
**governed daemon/RPC verbs via static metadata**, analogous to existing
verb metadata such as the `mutating=True` flag passed to
`dispatcher.register()`.

```python
# Illustrative — not yet implemented:
dispatcher.register(
    "session.resume",
    sessions_resume,
    mutating=True,
    continuity_class="resume_project_state",
)
```

This is a **mechanical inference surface, not a model self-report
surface**. The model never declares its own action class. The wrapper
reads the verb's metadata, runs preflight if a class is set, emits the
receipt, and proceeds.

Verbs without a `continuity_class` annotation are treated as
`not_applicable` — preflight does not run, no receipt emitted. This
keeps the cost localized: only deliberately-annotated verbs incur
continuity overhead.

Open residual question (Q1): whether later policy artifacts may refine
or override the default class map for specific verbs, callers, or
session contexts. Answer deferred to passive-mode evidence.

## 7. Passive-mode protocol

### 7.1 Preflight

For continuity-sensitive actions, the governed path performs a
continuity preflight before action execution.

Preflight attempts to:

- resolve subject and scope,
- query Continuity for matching basis,
- classify the result,
- attach the result metadata to the action context,
- emit a continuity-hygiene observe receipt.

Preflight result enum (Continuity-returnable):

- `hit`
- `miss`
- `not_applicable`
- `lookup_failed`

`conflict` is **not** in this enum. Conflict (e.g., multiple latest
entries with divergent supersede chains) is a Governor-side
classification over the rows Continuity returns, and surfaces as the
`CONTINUITY_BASIS_CONFLICT` finding (§9), not as a preflight result.

**Concrete mapping to the existing Continuity MCP surface:**

- preflight query = `memory_query_latest(scope, kind, ...)` with the
  scope filter derived from the action's subject/scope.
- rely-class signal = `memory_explain(memory_id).rely_ok` — already
  computed by Continuity from premise status / taint, so Governor's
  `RELY_WITHOUT_CONTINUITY_BASIS` finding maps directly onto a
  `rely_ok=false` reading rather than reinventing the judgment.
- writeback / supersede = existing `memory_observe` + `memory_commit`
  with the `supersedes` field, per the established convention.

The substrate is already adequate. This gap is about wiring it onto
the hot path, not extending it.

### 7.2 Action execution

The underlying action proceeds regardless of preflight result in
passive mode.

No denial occurs in v1.

### 7.3 Postflight

After action execution, the governed path evaluates whether the
interaction produced continuity-worthy state.

Postflight classifies:

- whether writeback is suggested,
- whether writeback occurred,
- whether supersede linkage is required,
- whether reliance exceeded available basis.

A second continuity-hygiene receipt is emitted, or the preflight
receipt is updated if the implementation prefers a single artifact
(see Q3).

## 8. Receipt model

Continuity hygiene receipts are emitted through `gate_receipt.py` with
`gate="continuity_hygiene"` and `verdict="observe"` in passive mode.
They are **observe-class** artifacts: they record what continuity
hygiene did or did not happen around an action; they do not themselves
authorize anything.

The structured detail is carried in the evidence bundle, content-
addressed via `evidence_hash`. Illustrative bundle shape:

```json
{
  "receipt_role": "continuity_hygiene",
  "standing_class": "observe",
  "subject": {
    "type": "project",
    "id": "agent_governor"
  },
  "scope": "repo:agent_governor",
  "action_class": "resume_project_state",
  "preflight": {
    "attempted": true,
    "result": "hit",
    "basis_ids": ["cont_123"],
    "conflict": false
  },
  "postflight": {
    "writeback_candidate": true,
    "writeback_performed": false,
    "supersede_required": false
  },
  "findings": [
    {
      "code": "WRITEBACK_CANDIDATE_UNCOMMITTED",
      "severity": "info"
    }
  ]
}
```

Exact field names are open. The load-bearing point is that the bundle
must distinguish:

- preflight attempted vs skipped,
- continuity found vs not found,
- continuity found vs relied upon,
- writeback candidate vs writeback performed.

## 9. Findings taxonomy

Initial finding codes:

### Preflight findings

- `CONTINUITY_PREFLIGHT_SKIPPED`
- `CONTINUITY_BASIS_MISSING`
- `CONTINUITY_BASIS_CONFLICT`
- `CONTINUITY_LOOKUP_FAILED`

### Reliance findings

- `RELY_WITHOUT_CONTINUITY_BASIS`
- `CROSS_SESSION_CLAIM_LOCAL_ONLY`
- `SUPERSESSION_WITHOUT_PARENT`

### Postflight findings

- `WRITEBACK_CANDIDATE_UNCOMMITTED`
- `SUPERSEDE_CANDIDATE_UNRECORDED`

These are hygiene findings, not fault declarations. Passive mode is for
visibility first.

## 10. Triggering rules

The system does not ask the model whether continuity matters. The
system infers opportunity from the action surface (see §6A).

Initial trigger rule:

- If a governed daemon RPC verb is annotated with a `continuity_class`,
  continuity preflight runs automatically on every invocation of that
  verb unless the call explicitly carries `continuity_class="not_applicable"`
  in its metadata.

Examples (assuming verbs are appropriately annotated):

- `session.resume` → trigger (`resume_project_state`)
- `session.create` → no trigger (fresh state)
- `intent.compile` for an existing project context → trigger
  (`prior_decision_claim`)
- `task.claim` on a brand-new scope → no trigger
- `task.claim` that supersedes an open reservation → trigger
  (`supersede_prior_conclusion`)

## 11. Passive-mode output

Passive mode must make skipped hygiene visible without becoming
bureaucratic sludge.

At minimum:

- continuity-hygiene receipts exist for triggered actions,
- findings are queryable through the standard `governor receipts`
  surface (`--gate continuity_hygiene`),
- a report or summary can answer:
  - where continuity would have mattered,
  - where it was found,
  - where it was absent,
  - where writeback was skipped.

This gives the project real evidence about failure frequency before any
hard policy is ratified.

## 12. Policy ratchet

This gap proposes a staged ratchet, not immediate enforcement.

### Phase 0 — manual etiquette (current state)

Continuity use is purely optional and remembered ad hoc.

### Phase 1 — passive (this gap)

Auto-preflight + receipts + findings. No warnings or denials.

### Phase 2 — surfaced warning

Governor surfaces continuity-hygiene warnings on selected action
classes.

### Phase 3 — selective admissibility

Some action classes become inadmissible without continuity preflight or
explicit override.

Candidate future classes for selective admissibility:

- superseding prior project guidance,
- resuming project state with claims about prior decisions,
- cross-time delegation artifacts intended for reliance.

Observe-only or purely local ideation remains cheap.

## 13. Why Governor, not only Continuity

Continuity exposes storage and lookup APIs, but it cannot by itself
decide when absence of continuity basis matters.

That question is constitutional:

- when is prior-state consultation expected,
- when does omission become receiptable,
- when does omission later become inadmissible.

Those are Governor questions. Continuity provides the substrate;
Governor provides the contract.

## 14. Open questions

1. **Policy overlays on top of static action classification**
   - 6A answers the v1 surface (daemon RPC verb metadata).
   - Open: whether later policy artifacts may refine or override the
     default class map for specific verbs, callers, or session
     contexts. Defer to passive-mode evidence.

2. **Subject/scope derivation**
   - How much can be inferred mechanically from verb args?
   - When must caller supply subject hints?

3. **Receipt granularity**
   - One combined preflight+postflight receipt, or two separate
     artifacts?

4. **Writeback suggestion**
   - Purely rule-based in v1, or model-assisted with a hard floor of
     mechanical triggers?

5. **Conflict handling**
   - Passive-only finding in v1, or should `CONTINUITY_BASIS_CONFLICT`
     force explicit override once warnings exist?

6. **Session-close behavior**
   - Should session-close writeback candidates be generated
     automatically, or only on tagged project sessions?

7. **Chat-path interception**
   - How should continuity-sensitive conversational turns be detected
     and receipted outside discrete daemon verbs?
   - Is chat-path hygiene a wrapper concern, a client concern, or a
     separate governed surface?
   - This is the dominant practical failure mode but is explicitly
     out of v1 scope (see §3A). Likely to need its own follow-on
     gap once daemon-path passive evidence exists.

## 15. Acceptance criteria for this gap

This gap is closed when the repo has:

1. a continuity-sensitive action classification surface attached to
   daemon RPC verbs (per §6A);
2. passive continuity preflight on at least one governed path;
3. continuity-hygiene observe receipts emitted via `gate_receipt.py`
   with `gate="continuity_hygiene"`;
4. a stable initial finding taxonomy (per §9);
5. tests proving:
   - preflight runs when expected,
   - non-sensitive (unannotated) actions remain cheap,
   - receipts distinguish hit/miss/skip/conflict,
   - postflight can mark writeback candidates;
6. at least one query surface for continuity-hygiene findings (e.g.,
   `governor receipts --gate continuity_hygiene`).

Build-order placement is deliberately deferred — this gap has not
earned a spot in `GAP_BUILD_ORDER.md` yet. It is instrumentation of a
suspected hygiene failure, not a ratified dependency. Promote when
passive-mode evidence justifies a phase 2/3 ratchet.

## 16. Expected effect

Success does not mean "the model always remembers continuity."

Success means:

- forgetting continuity becomes visible,
- reliance without basis becomes measurable,
- writeback omission becomes queryable,
- future admissibility policy can be grounded in receipts instead of
  annoyance.

## 17. One-sentence summary

Continuity stores memory. Governor makes memory hygiene part of the
governed surface.
