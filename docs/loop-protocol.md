# Loop Protocol — governed orchestration FSM

Ratified 2026-06-11 (claude-web handoff + ChatGPT custody hardening + Fable
interface-discipline amendment + operator consolidation). This document is
**explanatory**; the canonical loop state is `.governor/loop.json`. When this
prose and that file disagree about protocol, this document wins; when
`loop.json` and repo reality disagree, **live probes win** (§6).

## Why this exists (diagnosis, kept short)

The plan→dispatch→execute→review→patch loop worked, then died during an intake
flood, because its state was **ambient** (in a session's context) rather than
**witnessed** (on disk with re-entry probes). A prose summary of the loop is
testimony without a re-entry procedure. The fix is the constellation's own
medicine, self-administered: the loop is a small governed FSM with durable
state, receipted transitions, and an audit phase. Self-reference as admission
control, not aesthetic.

The master-control instance's job is **dispatch-and-verify against ratified
documents, NOT re-planning**. Plans are written down (wire plan, launch plan,
specimen specs, zoning); the failure mode to guard is the master re-deriving
decisions that are already ratified.

## 1. The loop-state artifact

`.governor/loop.json` — canonical, boring, parseable. Fields:

```
phase                 PLAN | DISPATCH | EXECUTE | REVIEW | AUDIT
current_slice         id or null (null only while AUDIT/PLAN reconciles)
candidate_next_slice  typed quarantine for a suspect/unadjudicated proposal —
                      neither blessed nor deleted; the audit adjudicates it
slice_spec            path(s) to the ratified spec the slice implements
acceptance            pointer to acceptance criteria (usually the backlog item)
blocked_on            ratification | nothing | named dependency
next_action           the single first thing a cold session does
last_verified_commit  git sha loop-state was last verified against
last_updated          ISO timestamp + session_id
wip_limit             1 (see §8 for what counts)
dirty_tree_allowed    false; dirty_tree_scope names the load-bearing paths
                      (working/ notes are deliberately unstaged — out of scope)
re_entry_probes       commands a cold session runs to orient (≤5, mechanical)
```

Markdown projections of loop state, if any, are explanatory only. The JSON is
the head; the receipts (§6) are the custody trail.

## 2. FSM rules

- **WIP limit = 1.** One governed slice in flight. Everything else → backlog.
- **Each phase exits by receipt** (under `.governor/loop-receipts/`):
  PLAN → next slice selected FROM the ratified backlog (never invented fresh);
  DISPATCH → assignment recorded; EXECUTE → tests green or failure named;
  REVIEW → verdict recorded; AUDIT → conformance verdict (§9).
- **Session exit obligation:** NO session ends without updating loop-state.
  A session that doesn't is a silent conversion — the update is part of the
  work, not cleanup.
- **Intake lane:** new ideas, chat dumps, zoning candidates NEVER interrupt the
  in-flight slice. They get one backlog entry with a pointer; the slice
  continues. Bartleby posture: prefer not to, until the slice completes.
  Intake may append backlog entries ONLY. It may not change phase,
  current_slice, acceptance, or next_action. Intake claiming urgency must name
  the violated invariant and receive ratification; otherwise: parked. (The trap
  is not distraction; the trap is *relevance*.)

## 3. Worker dispatch

- Workers (sub-claude / codex / qwen) receive: slice spec path, acceptance
  tests, and the loop-state pointer. They return: diff + completion receipt
  (what passed, what's open). **They do not see the backlog.**
- Master verifies receipts against acceptance tests before REVIEW exits.
  Grep over trust — the standing house rule.

## 6. Custody hardening

- `.governor/loop.json` is canonical; markdown is explanatory.
- **State ≠ receipts.** The state file is the current head; append-only
  transition receipts under `.governor/loop-receipts/` are how we got here.
  (NOT `.governor/receipts/` — that name is the runtime governor's.)
- > **Loop-state is a claim. Re-entry probes are the admissibility test.**
- When loop-state and repo reality disagree, **live probes win**; update
  loop-state and emit a stale-state receipt. Not "code wins" — code can hold
  half-landed work and ceremonial green; what wins is observed repo state
  under declared probes.
- `last_verified_commit`: if HEAD differs on cold start, run re-entry probes
  before dispatch. Distinguishes accurate / stale / aspirational /
  raccoon-copied loop-state.

## 7. Interface discipline (amended)

> **Surfaces are not authority. Origin class and unit class are authority.**

- Agents MAY drive maude/phosphor/any TUI **when the surface is the object
  under test** (developing, debugging, drilling) — such sessions emit
  drill/cli-class dispatches through the origin fence and cannot confer
  operational consequence (enforced by the type split + spend wall, not by
  this paragraph).
- Loop ORCHESTRATION never runs through a UI session: loop state lives in
  `loop.json` + receipts only; orchestration dispatches go through the
  protocol surface with actor provenance. No loop transition may depend on
  TUI session state — anyone's.
- If a capability needed for orchestration exists only in a TUI, that is not
  permission to use the TUI; it is a slice to extract the capability to the
  shared dispatcher surface.
- Loop-as-governed-workflow (FSM in AG proper, ledger-backed) is filed as a
  W2 promotion under the wiring invariant: it replaces the loop.json mechanism
  without changing phases, probes, or receipts. The file-based loop is
  authoritative v0 until that promotion's forcing case.

## 8. Backlog protocol — constellation-wide

- **Single global governed backlog** under `.governor/backlog/`, one JSON file
  per admitted item:
  `{id, repo, kind, spec_ref?, forcing_case?, priority_tier, expires?, status}`.
- **WIP-1 is global for governed slices.** Raw intake, probes, and drill
  traffic may occur but may not mutate loop phase / current_slice /
  next_action. **The membrane is mutation, not size:** exempt activity is
  non-mutating by construction (probes read; drills are operationally inert
  through the origin fence; intake appends to backlog only). Anything that
  would mutate the governed plane — land a diff, alter a spec, touch loop
  state, change anything a receipt would need to explain — is admitted work,
  no minimum size. "It was just a probe" is how 400-line diffs arrive at 2am
  wearing a trench coat.
- **Slice kinds:**
  - `spec_slice`: input is doctrine / zoning text / incident notes / backlog
    ambiguity; output is a ratifiable gap spec with acceptance criteria.
  - `build_slice`: input is a ratified spec with acceptance criteria; output
    is diff + tests + receipt.
- **Admission:** build slices require a ratified gap spec. Doctrine without
  acceptance criteria enters only as a spec_slice. Unmodeled work is not
  admitted.
- **Priority:**
  1. W1 items in ratified order until W1 exit criteria;
  2. forcing-case items (a named refusal that can't currently be expressed);
  3. expiring debt;
  4. ordinary debt;
  5. tidiness.
- PLAN auto-selects by this order. Operator ratification is required only for
  custody-affecting, cross-repo-schema, public-release, or Zenodo-touching
  slices — the existing ratification boundary, unchanged.

## 9. AUDIT phase — plan conformance, not QA

Cycle: `PLAN → DISPATCH → EXECUTE → REVIEW → AUDIT → PLAN`.
**Cold start is an AUDIT invocation** (re-entry unified with the cycle, not a
special case).

AUDIT checks, mechanized where possible:

1. **State conformance** — `loop.json` claims vs live probes; HEAD vs
   `last_verified_commit` (else probes run before dispatch); dirty tree
   accounted for within `dirty_tree_scope`.
2. **Plan conformance** — the closed slice and the proposed next slice vs the
   ratified documents (W1 order, backlog priority rule). Deviation requires a
   **deviation receipt with named evidence**; drift with a receipt is a
   decision; drift without one is the thing that killed the loop. Undocumented
   deviation = HALT for operator ratification.
3. **Obligation conformance** (the Paper-27 check: reconciliation can restore
   desired state while silently degrading obligations) — required receipts
   exist; corpus/register updates exist where required; pinning/negative
   tests present and green; closed-world obligations intact. A successful
   patch that degraded evidence/custody is a **deviation, not a pass**.

Output: append-only audit receipt — `pass | deviations_named[] |
halt_for_ratification` — summarized in one compact block to the operator each
cycle (the loop's heartbeat). Probes are executed at audit time and their live
output recorded; transcribing earlier findings into receipt form is the
ceremonial-audit failure mode.

**Independence rule:** warm self-audit suffices for mechanized checks; at chunk
boundaries and before custody-affecting ratification, AUDIT runs in a fresh
context (new session; probes + ratified docs + receipts only, no warm
narrative). The instance that drifted is the instance least equipped to notice.

## 10. Restart seed + selection rule (2026-06-11 restart)

Seeded in AUDIT — not PLAN, not a pre-selected slice. The restart followed a
stale/contradictory recommendation, so the first durable state must not
pretend a slice was already selected; the first action is reconciliation, and
the suspect recommendation rides as `candidate_next_slice`, quarantined.

Selection rule after probes:
1. refused-spend script / show surface missing → `current_slice = W1 item 3`;
2. item 3 exists but proof seam missing/unwired → `current_slice = W1 item 4`;
3. both genuinely done with evidence → `current_slice = W1 item 5` (OPA shim);
4. ambiguous → `HALT_FOR_RATIFICATION` — ambiguity at selection time is where
   process drift breeds.

Item-4 acceptance gate (operator-ratified at plan review): item 4's acceptance
is not "proof_seam.py exists and tests pass" (cargo) but "the refusal class
maps to the Lean theorem that actually licenses it." A known doubt about that
mapping (`proof-seam-citation-reconciliation`) means item 4 is open *in the
acceptance sense* until resolved — selection branch 2 applies.

## Doctrine

| Verdict | Question |
|---|---|
| **Cargo verdict** | Did the slice pass? |
| **Process verdict** | Was this the slice the ratified plan allowed us to do next? |

> Cargo success must not launder process drift.

- *I would prefer not to* — the Bartleby posture: intake waits for the slice.
- *A gap is a difference between compatible clock witnesses, not numbers.*
- *Loop-state is a claim; re-entry probes are the admissibility test.*
- *Surfaces are not authority. Origin class and unit class are authority.*
