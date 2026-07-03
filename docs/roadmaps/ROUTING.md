# ROUTING — slice tiers, executors, and the work-order discipline

**Status:** NORMATIVE for `docs/roadmaps/` (2026-07-02). Every slice in the roadmap
program (tool roadmaps, campaign NEXT files) is written against this document.

Provenance: promotes session doctrine — "tick = moves cargo; tock = cheapest model
satisfying gap; Fable for conceptual seams; codex-exec for adversarial review at
HIGH checkpoints" — into a repo-visible rule so slices can be routed without the
originating session in context.

## 1. Tiers

| tier | executor | what it may do |
|---|---|---|
| `mechanical` | local-qwen or codex CLI | execute a fully-specified work order; moves cargo |
| `review` | codex-exec (adversarial) | attack an artifact against a written rubric; may not fix, only report |
| `conceptual` | Fable (or operator-paired session) | design, name, adjudicate, mint vocabulary, resolve forks |

The tier names classify the **slice**, not the model. A conceptual slice given to a
small model does not become mechanical; it becomes wrong.

## 2. The six-field slice shape (mandatory, uniform)

Every slice everywhere in this program carries:

```
### <ID> — <name>
tier: mechanical|review|conceptual · executor: local-qwen|codex|codex-exec|fable · prereq: [<IDs>]
- purpose:        one sentence — the invariant this slice earns
- files:          enumerated paths likely touched (no "find the right place")
- tests:          verbatim command + expected exit/outcome (exit code is the verdict — never judge from piped tails)
- refusal mode:   which closed-vocabulary refusal this slice adds/exercises; a slice that
                  mints NEW refusal vocabulary is conceptual by definition
- receipt shape:  what testimony the slice leaves (receipt kind / digest fields / parent citation;
                  for doc slices: the commit and what it cites)
- stop condition: the line past which the executor STOPS and files an obstruction note
```

## 3. Mechanical eligibility checklist

A slice is `mechanical` **iff ALL of the following hold**. Failing any one bumps
the tier (usually to conceptual; to review if the work is judgment-over-rubric).

1. **Acceptance is executable.** The tests field contains a verbatim command with
   its expected exit/output, runnable by the executor without interpretation.
2. **Files are enumerated.** Every file to create or touch is named by path.
3. **No vocabulary minting.** Refusal names, receipt kinds, gap names, schema
   fields are all *given*, drawn from an existing closed set (e.g. the S4-lite
   refusal vocabulary, `standing.grant_use.v1` refusal classes, exporter kinds).
4. **No open question reachable.** No design decision or operator question can be
   encountered on the slice's happy path; all six fields hold concrete values.
5. **Bounded diff.** Doc-only, or ≤ ~150 lines against the named files.
6. **Ambiguity behavior is named.** The stop condition tells the executor what to
   do on surprise: STOP and write an obstruction note (see §5) — never improvise.

> A mechanical slice is a **work order, not a design task**. If the executor must
> decide anything beyond "did the command pass," the slice was misclassified —
> and that misclassification is itself reportable in the obstruction note.

## 4. The authority sandwich (hard rule)

Any slice whose diff touches **authority semantics** — minting, spending, refusal
*placement*, admission, custody chains — decomposes into three slices:

1. `conceptual` — design the seam; name the vocabulary; write the work order.
2. `mechanical` — execute the work order.
3. `review` — mandatory adversarial checkpoint (codex-exec) before merge:
   refute-first posture, file:line findings, <400 words.

Doc-only slices that merely *describe* authority surfaces (recording drift, naming
gaps) are not sandwiched; slices that *change* what refuses or what mints are.

## 5. Obstruction notes

When a mechanical/review executor hits its stop condition, it writes
`working/obstruction-<slice-id>.md` containing: the slice ID, what was expected,
what was found (verbatim evidence), and **no proposed fix**. The slice returns to
the routing queue for re-tiering. This is the slice-5 exit-ticket idiom
(`docs/playbooks/slice-5-exit-ticket.md`): stopping at the named line is success,
not failure.

## 6. Routing defaults

- Doc corrections with enumerated targets → local-qwen.
- Repo-spanning grep/verify/inventory work orders → codex.
- Adversarial review at HIGH checkpoints → codex-exec (see
  `.claude` codex-exec skill; refute, file:line, <400w — not autopilot).
- Anything minting vocabulary, resolving forks, or adjudicating theorems → Fable.
- When in doubt, route UP a tier. A wasted large-model call is cheaper than a
  confidently wrong small-model merge.

## 7. Receipts for doc slices

This program is documentation; its receipts are commits. Each slice = one commit,
message citing the slice ID and the evidence it relies on (file paths, sibling-repo
commits by hash, theorem names with Lean tier markers). Separately committable is
a Packet A hard constraint, honored program-wide.
