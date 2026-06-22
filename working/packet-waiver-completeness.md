# Task Packet: Waiver-admission completeness

**Status: DRAFT — sealed envelope, NOT cleared for execution.** Drafted 2026-06-22.
Ready-to-run when the operator says go. Format: `docs/reference/task-packet-template.md`.
Design basis: `docs/cross-tool/organ-separation-and-refusal-closure-note.md` § "The one
open completeness item". This is **completeness debt on an already-open surface**
(waiver/override exists), not new scope.

## Pre-flight finding (already done — do not re-investigate)

The primitives the design exchange thought were missing mostly exist:

- `gate_receipt.py`: `VERDICT_PROCEED = "proceed"` is already a distinct verdict from
  `VERDICT_PASS = "pass"`. Clean-vs-waiver admission is **partly typed already**.
- `gate_receipt.py` (v4): a **non-discharge / `unsettled`** field already records "what a
  verdict explicitly leaves unsettled." This **is** the home for the load-bearing non-claim
  ("waiver admission does not certify clean antecedents were satisfied"). Do not invent a
  new field.
- `overrides.py`: `OverrideReceipt` (scoped/expiring/receipted, carries `violation_snapshot`).
- `admissibility.py`: `Waiver` (by/reason, S2/S3 assumption gate).

So the work is **wiring + pinning**, not building a mechanism.

## 1. Objective

Guarantee that any admission granted *despite* an unsatisfied antecedent (override / waiver
/ proceed) is (a) verdict-distinct from a clean pass, (b) carries an explicit non-claim in
the `unsettled` field naming what was NOT certified, and (c) is refusable by a consumer. Add
pinning tests proving **no silent override path** — no override/waiver route can yield a bare
`VERDICT_PASS` with an empty `unsettled` block.

## 2. Scope fence (path allowlist)

- `src/governor/overrides.py`
- `src/governor/admissibility.py` (only the waiver→receipt emission path)
- `src/governor/gate_receipt.py` (only if an `unsettled` reason-kind constant for the
  clean-antecedents non-claim is genuinely absent — additive constant only)
- `tests/test_overrides.py`, `tests/test_admissibility.py`, and one new
  `tests/test_waiver_admission_completeness.py`
- ONE consumer read-path file to add an `accepts_waiver_admitted` refusal — confirm the
  minimal consumer at run time (candidate: `constraint_compiler.py` or `status_rollup.py`,
  whichever already branches on verdict). Touch exactly one.

## 3. Forbidden moves

- **No admission-interface redesign.** Do NOT re-route waiver "through the kernel as an
  admitted act" — that is the parked larger item, explicitly out of scope.
- No new planner / refusal-closure / obligation engine.
- No new ledger or reservation work; do not touch `activation.py`, `reservations.py`,
  `storage.py`. (Single-use-waiver-as-spendable is a *separate* future packet.)
- No widening of `VALID_VERDICTS` or any other closed vocabulary beyond, at most, one
  additive `unsettled` reason-kind constant — and flag even that for review.
- No fan-out / no spawning sub-agents.
- No "while I'm here" doctrine migration, renames, or formatting sweeps.
- No commit, no push. Leave the working tree for operator review.

## 4. Verification commands (from repo root, exact)

```
pytest tests/test_overrides.py tests/test_admissibility.py tests/test_waiver_admission_completeness.py -q ; echo "EXIT=$?"
```

Run bare; the **observed exit code is the verdict** (memory
`feedback_never_pipe_test_runner_through_tail` / global Verification discipline). Do NOT pipe
the runner through `tail`/`grep`. `EXIT=0` is the only pass.

## 5. Expected verify output / known-green baseline

- Before any change: `pytest tests/test_overrides.py tests/test_admissibility.py -q` →
  `EXIT=0`, existing suites green. Capture this baseline first.
- After: all three files green, `EXIT=0`. The new test file must contain at least the four
  pins in §6. **Additive tests only**; do not modify or weaken existing pins in
  `test_overrides.py` / `test_admissibility.py` without flagging in the handback.

## 6. Acceptance criteria (each independently checkable)

1. Every override/waiver-granted admission emits `VERDICT_PROCEED` (or an equally distinct
   verdict), **never** `VERDICT_PASS`. Pin: construct an override admission, assert verdict ≠
   `pass`.
2. That receipt's `unsettled` block contains an entry whose meaning is "clean antecedents
   not certified by this admission." Pin: assert the entry is present and non-empty.
3. A consumer can be configured `accepts_waiver_admitted=False` and, given a proceed/waiver
   receipt, refuses it (emits a refusal, does not rely). Pin: one consumer test, both
   branches (accepts → relies; refuses → refusal).
4. **No silent path:** a property/enumeration test asserting that no override/waiver code
   path produces `(verdict==pass AND unsettled empty)`. This is the anti-laundering pin —
   the whole point of the packet.

## 7. Reversibility / rollback

Fully revertible: `git checkout` the touched files. No migrations, no irreversible steps, no
persisted state changes (override/waiver stores already exist; this adds fields/tests, not
schema rewrites). If an `unsettled` constant is added, it is additive and back-compatible.

## 8. Stop-and-ask clauses

- Stop if making criterion 1 or 2 hold would require changing the admission interface or any
  file outside the fence → that is the parked "route through kernel" item; hand back.
- Stop if no consumer currently branches on verdict (criterion 3 has no minimal home) →
  hand back rather than building a new consumer surface.
- Stop if a baseline suite is red *before* changes → report, do not "fix while here."
- Stop if a verify fails and one retry doesn't resolve it.
- Stop if satisfying "no silent path" reveals an existing silent path in shipped code →
  report it as a finding; do not silently patch load-bearing behavior without flagging.

## 9. Source authority

Operator fiat 2026-06-22 ("yeah, I think you should draft"), scoping the waiver-completeness
item from the organ-separation note. Drafted, not executed, per operator + reviewer
agreement ("draft the packet, don't execute it").

## 10. Model tier attempted

HEAVY (Opus). Cross-module wiring + pinning-test authorship + one consumer-refusal branch.
The non-claim semantics (criterion 2) and the no-silent-path framing (criterion 4) are the
judgment-bearing parts; the rest is mechanical. Not a downgrade candidate until the
no-silent-path pin exists and is green (it converts the judgment into a checkable claim).
