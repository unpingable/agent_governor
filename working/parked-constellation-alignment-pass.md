# Parked — Constellation Alignment Pass

**Status (2026-06-10): UNPARKED with bilingual refinement.** Operator
directive after sprint commit + endgame synthesis: the legal→ops rename
pass moves to active before any Maude/LA dispatcher wiring begins (step
2 of the endgame sequence at
`working/endgame-synthesis-2026-06-10.md`). Reduces ambiguity before the
custody-affecting step.

**Critical refinement:** the rename pass is NOT a rip-and-replace. It is
**bilingual maintenance** — internal/theory names stay at their native
homes (papers, doctrine docs, other repos' SPECs, cross-claude
continuity), and ops names appear on consumer-facing surfaces (CLI,
errors, dashboards, README). The translation surface itself is the
artifact, not a one-way transformation. The living glossary at
`docs/reference/internal-ops-glossary.md` carries the canonical mapping.

Other claudes (papers, standing, wicket, nq, scheduler, continuity) are
writing the internal vocabulary in parallel. AG cannot unilaterally
rename the shared terms. The bilingual discipline is how the
constellation maintains coherence across the rename without forcing a
synchronized rewrite.

The original parked content below is preserved as historical context;
sections marked **(superseded by bilingual refinement)** are now
handled through the glossary, not through the original
"replace everywhere" framing.

---

(Original parked content follows.)

---

**Original status: parked / TODO-much-later. Not a gap spec. Not ratified doctrine.
Not authorization to rename.**

A naming-discipline pass across runtime-facing surfaces of AG / NS /
Wicket / WLP / Continuity / NQ / Labelwatch. Filed 2026-06-09 as deposit
into the parking lot, explicitly *not* to be executed now.

## Why parked

> Do not spend Friday-level model firepower on naming hygiene while the
> pipe is still leaking in exciting new ways.

The right priority is:

1. Wire the path.
2. Get one accepted crossing.
3. Get one refused crossing.
4. Record both.
5. Make sure arrival / admission / mutation / receipt remain separate.

Term cleanup comes after there is a living organism to rename. Names
should be extracted from the working seam, not imposed on it from the
haunted jurisprudence cloud.

## Goal (when this fires)

Rename **runtime-facing** surfaces toward operational language without
deleting the theory / legal layer. Legal vocabulary can explain the
invariant; operational vocabulary should *carry* the invariant.

The split:

| Keep legal-ish               | Rename operationally   |
| ---------------------------- | ---------------------- |
| Papers, theory notes, essays | CLI flags              |
| Scratch doctrine docs        | API fields             |
| Historical analogies         | crate/module names     |
| "Why this matters" sections  | receipts, JSON, routes |
| Glossary crosswalk           | dashboards / UI labels |

The danger of legal names in code: they invite readers to argue with the
analogy instead of inspecting the mechanism. "Is this really mandamus?"
becomes the bike shed. Meanwhile the actual invariant — *a sufficient
claim cannot be stalled forever without a recorded blocker and progress
path* — wants an ops name (`bounded_progress`, `stall_duty`, etc.) that
can survive contact with logs.

## Do now (binding subset of the pass)

These are *now-binding* rules even though the alignment pass is parked.
They prevent the parking lot from filling up with new debt while waiting:

1. **Preserve existing meanings.** Do not opportunistically rename in
   passing.
2. **Avoid inventing new refusal kinds.** The current refusal set is
   already in scope: `blocked`, `refused`, `stale`, `unwitnessed`,
   `unchecked`, `out_of_scope`, `unsettled`, `not_counted`, `not_checked`,
   `not_judged`. New buckets need a forcing case, not Friday-night vibes.
   Composes with [[altitude_axis_deferred]] (same shape: don't expand
   typed primitives without grounded need).
3. **Keep wiring moving.** Naming polish never blocks an in-flight
   crossing. Receipt-shape work, gate wiring, packet shape — those come
   first.

## Later pass (the actual rename)

When this fires (forcing cases below), do this much and no more.

### Glossary mapping

| Legal / theory term  | Runtime / ops term                                |
| -------------------- | ------------------------------------------------- |
| admissibility        | admission, acceptance                             |
| standing             | caller_fit, receiver_fit, scope_fit               |
| jurisdiction         | authority_scope, route_scope, consumer_scope      |
| mandamus             | bounded_progress, stall_duty, must_advance        |
| conversion           | promotion, authority_upgrade, effect_upgrade      |
| refusal propagation  | blocker_propagation, dependency_block             |
| custody              | source_chain, handoff_chain, provenance           |
| estoppel, etc.       | quarantine to papers unless specific reason       |

### Words that stay (no rename)

- **refusal** — operational enough already.
- **receipt** — perfect. Legal-ish but infra-native.
- **witness** — already systems language.
- **scope** — already operational.
- **freshness** — already operational.

### Role alignment by authority (not mythology)

Avoid robe-wearing-magistrate role names. Align by write power:

```
producer       emits claims
witness        observes external state
admitter       decides whether claim may enter scope
gate           blocks or permits mutation
mutator        performs effect
recorder       writes receipts
auditor        compares receipts / state after the fact
governor       applies policy / budgets / horizons
```

### Crossing anatomy as the spine

For the AG → NS → Wicket → WLP → Continuity pipeline, the actual
operational crossing carries the names:

```
AG          claim producer / source actor
NS          packetizer / posture annotator
Wicket      admission evaluator
WLP         receiver gate / mutation boundary
Continuity  receipt recorder / handoff ledger
Governor    policy / horizon / budget evaluator
```

### Standard outcome shape (closed set, like the artifact-kind table)

```
accepted
accepted_with_scope
refused
blocked
stale
out_of_scope
unwitnessed
unchecked
unsettled
```

New outcomes enter via gap spec, not by accretion.

## Unification thesis

The real win is **not one perfect terminology** — it is:

> Same boundary shape everywhere. Same failure shape everywhere. Same
> receipt shape everywhere.

Every subsystem should be able to answer five questions:

1. What did I receive?
2. What did I check?
3. What scope did I grant or deny?
4. What effect did I permit or block?
5. What receipt did I write?

That's the standard. Names can improve later. The actual win is making
all the machinery expose the same joints.

## Boring-ops register (avoid SRE perfume)

Bias toward older, plainer nouns. Less McKinsey-YAML, more crontab.

| Avoid-ish     | Prefer                                     |
| ------------- | ------------------------------------------ |
| telemetry     | status, state, report, probe output        |
| observability | inspection, audit, witness, check          |
| signal        | finding, event, condition *(but see note)* |
| incident      | fault, failure, outage, violation          |
| remediation   | repair, fix, clear, recover                |
| policy engine | ruleset, gate, admission check             |
| workflow      | job, run, pass, handoff                    |
| evaluation    | check, verify, test, inspect               |
| artifact      | file, receipt, record, packet              |
| compliance    | conformance, required state, allowed state |

Emotional register target:

> crontab, syslog, lockfile, exit code, spool dir, receipt, gate

Not:

> platform reliability intelligence telemetry substrate

(The second one is how a YAML file joins McKinsey.)

**Note on `signal`:** AG already has a Signal Plane (`signals/`,
`SignalEnvelope`, GATE_CHECK_SUMMARY, etc.) as a load-bearing concept.
"Signal" is grandfathered in AG kernel; the avoid-list applies to *new*
runtime surfaces and to docs/dashboards, not to retroactive renames of
the existing instrumentation spine.

**Kept SRE-adjacent term:** `health` — `health_check`, `health_state`,
`unhealthy`, `degraded` are operationally understood, not too cursed.

## Constitution-as-pressure-test (legal layer kept, demoted)

Do **not** delete the legalistic concepts. They do theory work. Demote
them from primary runtime vocabulary; keep them as pressure tests:

> Did anything gain authority without a witnessed promotion?
>
> Did anything mutate because it merely arrived?
>
> Did anything refuse without a receipt?
>
> Did anything stall without a blocker?

The constitution stays. The runtime wears boots.

## Forcing cases for promotion (when this fires)

- A user-visible surface (CLI flag, API field, dashboard label, receipt
  schema field) where legal/theory naming is producing measurable bike
  shed cost or onboarding friction.
- A cross-repo coordination moment where AG / NS / Wicket / WLP /
  Continuity / NQ have to agree on a shared schema field name and the
  legal name and ops name diverge enough to cause integration drift.
- The unification thesis (same boundary shape, same failure shape, same
  receipt shape) requires a typed cross-module vocabulary that can no
  longer be maintained as parallel glossaries.

None of these is live as of 2026-06-09. Park.

## Cross-references

- `docs/agent-governor-meta-plan.md` — binding verbs vs observing verbs
  is the *same shape* this alignment pass works at, one level up.
  Operational verbs carrying invariants is the core move.
- `working/sentinel-observation-not-authority.md` — the constitution
  pressure-test (above) is the sentinel surface restated in legal
  vocabulary.
- `memory/altitude_axis_deferred.md` — sibling discipline: don't expand
  typed primitives without forcing case.
- `memory/relational_role_induction_keepers.md` — handle ≠ standing;
  relational language ≠ evidence. Composes with the role-alignment
  discipline (above).

## Non-goals

- Not a directive to start the rename pass.
- Not a deprecation of any current legal-ish vocabulary.
- Not a cross-repo coordination move. AG-side parking only.
- Not a redefinition of refusal kinds, outcome enums, or role types.
- Not a commitment to typed `ArtifactKind` / `UseKind` / `Role` enums in
  code. Forcing case still gates per `~/.claude/CLAUDE.md` § YAGNI.
