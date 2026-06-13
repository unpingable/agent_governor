# Cross-tool design note: decomposition completeness is capability closure

## Status

**PROVISIONAL design note + blocker.** Filed 2026-06-13 (operator + interferometry,
after P3.2 landed enforcing recomposition). The front-end mirror to
`rung-activation-four-office-note.md`: that note is how one activation
*recomposes*; this note is why a recomposition's verdict is only as sound as the
decomposition it accounts. Records the doctrine BEFORE further decompose/recompose
work can let a helper innocently emit `decomposition_complete = True`. The
capability-kernel integration it points at is FUTURE work (composes with
`receipt-sovereignty-microkernel-note.md` — boundaries become kernel-granted
capabilities); this note installs the *refusal* and the *receipt-shape discipline*
now. Gap: `specs/gaps/GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001.md`.

## The hole this closes

P3.2 landed enforcing recomposition: `account_boundaries` refuses a run where an
**admitted** boundary went unaccounted (a declared slice silently dropped). But
that is only one of two dual laundering modes:

```
recomposition laundering (CLOSED by P3.2):
  a boundary WAS admitted at decompose, then silently dropped at recompose.

decomposition laundering (OPEN — this note):
  a real boundary was NEVER admitted at decompose,
  so account_boundaries sees no missing disposition,
  and recomposition declares the whole clean.
```

You cannot catch an omitted boundary by checking that all *declared* ones are
accounted — the omitted one isn't there to be missed. This is the closed-world
problem the verifier solves for facts, one level up: **who guarantees the boundary
*set* is closed?** Confirmed mechanically: `account_boundaries(['A','B'], {...all
completed}) → admissible`, regardless of a real boundary `C` that no one declared
(`tests/test_decomposition_closure_limit.py` pins this as the known limit).

> **Recomposition soundness is conditional on decomposition completeness, and
> nothing in AG-alone discharges that condition while boundaries are *declared*.**

## The fix: declared boundaries → granted capabilities

Declared surfaces are omittable; a slice can touch something its plan never named.
The microkernel move (from the receipt-sovereignty note), pointed at the front
end, closes it: **make boundaries capabilities.** A slice's boundary set stops
being "the surfaces it declared" and becomes "the caps the kernel granted it" —
complete by construction, because the kernel won't forward a message over an
ungranted cap and knows exactly which caps it issued.

Push it all the way: not just resource caps but **decision caps** — "may classify
findings in venue V" is a capability too. Then everything a slice may do, surface
and decision alike, is a held cap; the boundary set is exhaustively the cap set;
and recomposition's "complete admitted set" stops being an assumption and becomes
the kernel's grant record.

```
decomposition = the caps the kernel granted
execution     = a slice may exercise only held caps (ungranted = unsendable)
recomposition = every granted cap's exercise produced a disposition / custody
```

Decomposition and recomposition turn out to be two ends of one capability ledger.
The asymmetry collapses; recomposition was the back half of the ledger all along.

## Two completeness layers — only one is mechanical

Do not let "best-effort" become a procedural fog machine. Completeness has two
axes, and the valve is on BOTH — `enumeration` *is* the closure half, so pre-
capability-kernel AG-alone owns neither as `complete`:

1. **Enumeration completeness** — *the boundary set is closed.* Closure holds only
   when boundaries are kernel-granted capabilities (boundary set == grant set).
   That is mechanical *given a capability kernel* — but the kernel does not exist
   yet. With merely *declared* boundaries (today) the honest value is
   `enumeration: declared` (basis `declared_boundaries`): "I accounted for every
   boundary I was *told about*", which is **not** closure. `enumeration: complete`
   is reserved behind capability-kernel grant-ledger evidence. An omitted boundary
   is an *enumeration* failure, not a coverage one — this is the axis the blind
   spot was actually about.

2. **Coverage completeness** — *the granted caps and their rules close over the
   plan's intended effects with no gaps, no contradictions, and no in-cap
   composition that produces an out-of-scope effect.* A constraint problem.
   AG-alone is **best-effort**; the completeness evidence is verifier/Z3 (bounded)
   or Lean (inductive, cited) or genuine operator ratification.

> Before the capability kernel, AG can account **declared** boundaries; it cannot
> prove boundary **closure**. So AG-alone is `enumeration: declared, coverage:
> best_effort` — two qualified values, **zero bare completes**.

### Receipt-shape discipline (the anti-fog valve)

A best-effort check MUST emit the same receipt shape as a verified one, marked
honestly, so a later verifier/kernel wiring can diff what AG-alone would have
missed (convertibility, not co-location). The honest AG-alone block vs a
coverage-verified one:

```
decomposition_check:  (AG-alone, honest)    decomposition_check:  (coverage solved)
  enumeration:      declared                  enumeration:      declared
  enumeration_basis: declared_boundaries      enumeration_basis: declared_boundaries
  coverage:         best_effort               coverage:         complete
  verifier:         absent                    verifier:         z3
  proof_tier:       ag_only                   proof_tier:       bounded_constraint
  coverage_upgrade_owed: true                 solver_evidence: {solver_verdict_ref: …}
                                              coverage_upgrade_owed: false
```

The valve is symmetric and enforced by type (`decomposition_completeness.py`) —
EVERY path to `complete` carries a structured evidence object with a provenance
ref, never a bare enum string:
- `enumeration: complete` requires `CapabilityClosureEvidence` (a grant-set ref);
  AG-alone's own code has no producer (it never constructs one).
- `coverage: complete` requires one of: `z3`+`bounded_constraint`+a structured
  `SolverCoverageEvidence`; `lean_citation`+`theorem_cited`+a structured
  `TheoremCoverageEvidence`; or `operator_ratified`+a structured
  `OperatorRatification` (a receipt ref, **not** a self-set flag — a model is not
  a principal). Bare `verifier`/`proof_tier` strings are never sufficient.

These are evidence-shaped *sockets*: the ref is required and validated; whether it
is *genuine* (a real solver verdict, theorem, kernel grant, operator receipt) is
custody-anchoring — a later producer-swap rung, not a semantic retrofit. In one
process a caller can still construct the objects (the documented bootstrap-custody
substrate limit, same as P3.1); what is fenced *here* is the shape and the
unrepresentability of the bare-scalar lie.

**There is no bare `decomposition_complete` boolean** — completeness is always two
qualified axes, so the scalar lie is unrepresentable. The field semantics:
`declared != complete`, `best_effort != discharged`,
`operator_ratified != self_asserted`. That bare `complete: true` is where the worm
enters the apple, files a Jira, and becomes staff engineer.

## Prep-before-ingest: the admission gate

A plan containing a gate that won't decompose is **inadmissible to ingest**, not
run-with-a-warning-taped-on. Ingest is a rung transition — the 0→1 into the plan —
so the prep pass runs on the same machinery as every other transition (no new
mechanism; it is the rung-activation gate pointed at the plan boundary):

```
prep   -> decomposition eligibility check
ingest -> rung transition (0 -> 1, the plan enters jurisdiction)
an open indecomposable-gate claim BLOCKS ingest
operator (or authorized party) discharges -> fresh eligibility
```

The "won't fully decompose" flag is an ingest-gating **NonDischargeClaim**
(kind `indecomposable_gate`, blocks `plan_ingest`). It also gives the earlier loose
end a home: deciding *what is "programmatic enough to be a gate"* is a ratified
judgment with no obvious owner — the prep pass is that owner. The operator, at
prep, sorts the decomposable gates (caps + verifier handle them downstream) from
the ones they will own as judgment. **Triage at prep, enforce at runtime.**

### The planner may not clear its own indecomposable flags

The sharpest trap. The flag is operator-owned, NOT planner-clearable by re-running
prep until green — else prep is a CAPTCHA the planner beats by manufacturing fake
sub-gates that each pass the checker while the real judgment stays hidden
(over-classify-as-programmatic, one level up).

```
planner MAY propose a decomposition that resolves the judgment.
planner MAY NOT self-certify that it did.
proposing is fine; ratifying your own resolution is not.
```

The classification "this can be handled as a gate" is itself an **assert-standing**
surface (the asker does not grant its own entitlement).

## Verifier placement: builds gates, does not choose what becomes one

The verifier (`~/git/verifier`, Z3 sidecar) is the right tool for the *programmatic*
slice — `required_caps ⊆ held_caps` is a constraint problem, composable as gates.
But it is a boundary checker over typed IR, not an oracle/judge: it reserves
`authorized` for upstream authority kernels and only classifies admissibility.

```
verifier CAN check:                       verifier CANNOT decide:
  required_caps ⊆ held_caps                 what caps should have been requested
  exercised_caps ⊆ granted_caps             where the right authority seam is
  ∀ cap exercised: has_disposition(cap)     whether a judgment is gate-able
  ∀ bridge requested: bridge ∈ granted      who has standing to compile the rule
  A_allowed ∧ B_allowed ∧ seam(A,B)
```

Two constraints, both ported from earlier turns:

1. **Composition is not conjunction.** `A allowed ∧ B allowed` does NOT give
   `A;B admissible` — that is no-free-standing-bridge wearing a logic gate (a
   little Boolean money printer). The seam must be reified as its own rule:
   `A ∧ B ∧ seam(A,B)`. By the caps-are-boundaries logic the seam is a boundary,
   hence a cap, hence a rule the verifier checks — never an emergent property of
   conjunction.

2. **`verifier.allowed` is evidence, not authority.** "Verifier green" can never
   become "this decomposition was legitimate." It says only: given the cap grant
   and rules supplied, the proposed claim does not violate them.

### Z3 synchronous, Lean cited

```
Z3:   synchronous prep gate — bounded cap/rule constraints, subset checks,
      seam constraints, contradiction checks. Cheap enough to block ingest on.
Lean: cited, already-proven theorem/refusal-class — a CI/build artifact, NOT a
      live ingest-path proof. A gate needing a NEW Lean proof is flagged/deferred
      to the operator, never blocked-on. The heavy tier contributes citations to
      prep, never latency.
```

Lean on the ingest path is architecture cosplay — the live path cites proven
theorems, it does not discover them while the operator wonders why the plan is
"almost done proving decidable equality for sadness."

## Standalone AG

May co-host offices; may NOT collapse conversions. Best-effort coverage checks
emit the same receipt shape with `coverage: best_effort` / `verifier: absent` so
future verifier integration diffs what AG-alone missed. Co-location is allowed; a
silent `best_effort → complete` conversion is the crime.

## The honest residual (so this isn't oversold)

Caps nail **completeness**, not **partition**. They guarantee no invisible
boundary, but not that you cut the slices at the right authority joints. A slice
holding caps for both `read_config` and `deploy_prod` is *complete* — both are
caps, both get accounted — and still badly *partitioned*, because those want
different rungs with different ratification. Where to draw the slice is a judgment
caps can't make for you, and it is exactly the thing that cannot become a gate.
That judgment is the operator's residue, surfaced at prep.

Track grant-vs-exercise to make the smell visible (decomposition *quality*, not
just safety):

```
granted_not_exercised      -> unused authority / maybe overbroad slice (warn)
exercised_with_disposition -> normal
attempted_ungranted        -> hard refusal / decomposition failure
exercised_without_receipt  -> custody failure
```

## Doctrine lines

- Declared boundaries are pleadable. Granted capabilities are accountable.
- Decomposition grants caps. Recomposition accounts caps.
- A seam is a boundary, not the shadow cast by two passing checks.
- Enumeration is mechanical. Coverage is evidentiary.
- Prep before ingest. Triage before execution.
- The planner may propose gates; it may not certify that judgment disappeared.
- Z3 gates bounded constraints. Lean licenses classes. The operator owns the residue.
- Verifier builds gates; it does not choose what may become a gate.

## The knife

> **You cannot audit the absence of an omitted boundary. You can only make
> omission unexecutable.**
