# Status — nightshift-functional-mvp

Card ratified 2026-07-05. Gap assessment done (65% of lane exists; 6+1 packets).

## Current disposition — NS-1 LANDED, operator-amended (2026-07-15)

This section supersedes the 2026-07-14 custody-successor state below without
deleting it. **NS-1 custody is CLOSED: nightshift `e71303f`** (base `01a65bf`,
6 files, 487 insertions, local — NOT pushed). The preserved pre-amendment
implementation is retained unchanged at
`~/preservation/nightshift/ns1/2026-07-14/` (patch sha256 `b78940ac…`,
re-verified at integration) as evidence of what was amended.

The kept diff was integrated from the existing dirty tree, not re-applied:
`git diff --full-index` at `01a65bf` was proven byte-identical to the
preserved patch before anything was touched.

**Operator amendment (2026-07-15) — skew is not staleness.** Integration
review found the promoted implementation mapped `LivenessVerdict::Skewed` onto
`RefusalKind::LivenessStale` and synthesized a `threshold_seconds` from
opts/default to fill the shape. That is a false typed claim: `liveness.rs`
documents skew as "an epistemic hole, not freshness", and `verdict_for`
returns `Skewed` on negative age *before* any threshold comparison — so the
reported threshold took no part in the verdict and the free-text `blocked[]`
beside it never renders one. A closed refusal registry that launders an
unrepresentable case into a near-miss defeats its own purpose, so the operator
refused it and ruled a narrow amendment rather than landing as-is:

1. `LivenessSkewed { age_seconds }` added as a distinct closed variant;
   `Skewed` maps to it. Each variant carries only values its verdict produced.
2. The mapping was extracted to `pipeline::refusal_for_verdict` — the real
   function `liveness_gate_failed` calls — because the shipped pipeline tests
   were tautological (they re-implemented the mapping in the test body and
   asserted it against itself; deleting production would have left them green).
3. Packet-level acceptance tests added in `tests/liveness_pipeline.rs` (a
   sixth file, beyond the plan's five — real pipeline-produced packets need
   that harness) proving stale AND skew each carry the correct typed refusal
   *and* their free-text `blocked[]`, in packet JSON. Both new skew tests were
   falsified against the pre-amendment mapping before being trusted.

Verification: `cargo test -p nightshiftd` → 180 unit (168 at base + 12),
`liveness_pipeline` 6, all other targets green; `cargo clippy --all-targets`
clean. Pre-existing and untouched: `drill_runner_all_green` fails 3/6 — its
skip guard errors instead of skipping when AG's `python3 -m
governor.drill_runner` is absent. Identical failures reproduce on a clean
worktree at `01a65bf` with NS-1 absent, so they are baseline evidence, not
NS-1 regressions. Same class as the `nq_cli` skip-path hardening (`40ee42b`);
not repaired in this slice.

State axes: admission=`ratified`; selection=`unselected`;
plan_approval=`ns1_unverifiable_exact_artifact_impl_amended_by_operator_ns2_6_not_attached`;
runtime_activity=`inactive`;
effect_authority=`not_evidenced_for_unselected_packets`;
custody=`ns1_closed_unpushed` (NS-1 landed at `e71303f`; S1–S7 are closed;
NS-2..6 are not built).

**Approval custody is NOT closed by this landing (audit correction 2026-07-15).**
NS-1's exact approved plan bytes were never preserved: the tracked `plan.md`
still reads `governance_status: candidate` and the `operator_plan_approved_2026-07-09`
witness named by the run history is absent from the specimen directory. The
landed code additionally *exceeds* that tracked plan — four `RefusalKind`
variants where the plan specified three — under a direct operator ruling that
no plan artifact records. The `plan_approval` axis therefore stays
`unverifiable_exact_artifact`; the amendment is recorded as an implementation
fact, not as approval evidence. Under the S6 ruling (approval attaches to plan
bytes; migration creates a successor, not a revision) a conforming record would
be an NS-1R successor — NOT an edit to these bytes. Whether a direct operator
ruling substitutes for a plan artifact is an open semantic question; it is
reported, not resolved here.

Doctrine kept from this slice: a closed refusal registry earns its name only
if an unrepresentable refusal forces a new variant. The cheap failure is not
a missing variant — it is a plausible neighboring one.

## Current disposition — custody successor (2026-07-14) [SUPERSEDED 2026-07-15]

This section supersedes the earlier "NS-1 staged / awaiting operator" state
without deleting that staging history. **NS-1 implementation is built and
verified, but its custody is not closed:** the governed run exited
successfully and the operator kept its diff
(`.governor/runtime/sess_3a2ea5348a85_events.jsonl`, seq 271
`session_exited`, seq 274 `promotion_resolved` with `decision=approved`; status
commit `e276115`). As remeasured on 2026-07-14, `~/git/nightshift` at
`01a65bf` still carries the exact five promoted files as an uncommitted
337-insertion diff. The remaining NS-1 delta is therefore commit/landing
custody, not implementation. The grant-use track S1–S7 is also closed. NS-2..6 remain
inside the ratified campaign envelope and are queued, but none is selected as
`NEXT`; each exact packet retains the campaign's queue-latch and plan-approval
witness gate.

State axes: admission=`ratified`; selection=`unselected`;
plan_approval=`ns1_unverifiable_ns2_6_not_attached`;
runtime_activity=`inactive`;
effect_authority=`not_evidenced_for_unselected_packets`; custody=`partial` (NS-1 is verified+kept but
uncommitted; S1–S7 are closed; NS-2..6 are not built).

## Done

- **NS-0 DONE (2026-07-05):** the model pin threads end-to-end — maude
  `run <plan.md> --model X` (maude `442703e`, tests + refusal path) →
  `runtime.session.create` `harness_args` (strings-only, fail-closed; AG
  `f51e866`) → `SessionRecord` → `LaunchConfig.args` → claude CLI argv
  (adapter already extended cmd). Model choice = operator's run-time spend
  decision, never plan-envelope content. Both suites green.

- **NS-1 STAGED (2026-07-05 staged; 2026-07-09 REPAIRED, candidate):**
  `specimens/ns-1-refusal-registry/` — the first governed build packet, a
  **live maude-supervised run**, staged for operator approval. All artifacts
  authored + digested via the REAL landed classes; staging receipts
  (re-verified 2026-07-09):
  - playbook.yaml → `parse_playbook` = `PlaybookSpec` (`sha256:0c0f0973…`)
  - ration_card.json → `RationCard`, locked axes hold, shell allowlist
    `cargo test`/`cargo build` (`sha256:90ea2a86…`)
  - plan.md → parses in maude's envelope parser; admission **REFUSES**
    `governance_not_approved` even with the witness resolver pointed at the
    dir (born-candidate rule holds — only the operator's approval act clears
    it). This refusal is the on-path staging receipt.
  - **post-flip dry-run (throwaway copy):** `governance_status: approved` +
    `approval_ref` → admission PASSES, `governed=True`, three citations
    (`playbook_digest`/`ration_card_digest`/`approval_ref`) all `verified`.
    The operator's act will admit; the post-approval path is proven sound.

- **NS-1 dry-run caught a real defect (2026-07-09), specimen repaired.**
  A pre-flip dry-run on a throwaway copy found the original `queue.json`
  (synthetic-conveyor `PlaybookQueue`) was a dead limb on a live-run
  specimen: (a) `maude run` never calls the queue parser — off the execution
  path entirely; (b) internally impossible — `subprocess: true` (needed for
  `cargo test`) under `mode: synthetic_conveyor` requires fully-closed
  authority, so latching `operator_approved: true` would NOT have cleared it
  (`authority_not_closed` waited underneath the reported `not_operator_
  approved`). The documented flip would have broken in the operator's hands.
  Fix: `queue.json` removed, the `queued_playbook_ref` projection dropped
  from `plan.md`, README staging receipts + flip procedure rewritten to the
  pure live-run path. The synthetic-conveyor queue seam stays demonstrated
  by the CD-4B corpus + refusal gallery — it just doesn't belong here.

## Awaiting operator (NS-1 approval)

> **Historical gate record, superseded 2026-07-10.** The procedure below is
> retained as the pre-run approval history. The completed run and kept
> promotion are recorded in the immediately following section and in the
> current-disposition successor above.

Approval procedure in `specimens/ns-1-refusal-registry/README.md`: create
witness file (`operator_plan_approved_<date>`) → promote plan
(`governance_status: approved` + `approval_ref` naming the witness) →
`maude run …/ns-1-refusal-registry/plan.md --model claude-haiku-4-5` →
approve/deny tool calls → `report <sid>` → keep/discard. If haiku fails the
packet twice, escalate the MODEL (sonnet), never the authority.

## NS-1 FIRST LIVE RUN — DONE (2026-07-10)

Operator approved (witness `operator_plan_approved_2026-07-09` + plan
promoted to `governance_status: approved`) and ran
`maude run …/plan.md --model claude-haiku-4-5`.

**Cargo verdict — the dogfood's core claim PROVEN:** haiku carried the Rust.
Cargo went green; operator KEPT the diff. A smaller model, supervised
through the governed loop, produced the `RefusalKind` work. NS-1's thesis
(small model + governance loop can carry real work) holds.

**Three integration bugs surfaced + fixed live** (none visible to unit tests
or the screen-mount smoke — the dogfood earned its keep):
1. socket-path derivation mismatch (env/cwd) — worked around (run both from
   `~/git/agent_gov`); public-MVP papercut, discovery/print-the-dir fix owed.
2. intent classifier dropped `--model` → chat → crash. NS-0 taught the
   runner but not the classifier. Fixed: maude `c1e96aa` (+regression).
3. `RichLog.write(end=)` crashed on `tool_call_proposed` — would have killed
   the TUI on the first tool call. Fixed: maude `3b05786` (+regression).

**Dogfood verdict — not thin, OVERBEARING.** The loop works; the human
factors are demonstrated almost adversarially. Friction scales with
interaction count, not risk (twenty `cargo test` approvals train the
operator to mash `y`). Two things pinned (operator: "pin that for later"):
- **Approval compression** — the bounded-class grant already exists as the
  RationCard; the supervisor ignores it and re-prompts per-invocation.
  Fix = honor the approved envelope, escalate only on material change.
- **maude operator-surface UX** — named tool states, CURRENT DECISION
  priority, collapse-by-tool-call, separate audit pane, lease display.
- Bug: `Y`≠`y` case-sensitivity surfaced a stale `claude-3-haiku` model id.
Full pin: `candidate-approval-compression.md` (this dir). NOT built —
doctrine ("attention is a custody class"; "compress non-authority-changing
transitions") is the durable part.

## Grant-use track (approval compression)

Built out as slices S1–S7 in `design-grant-use-gate.md` (the pinned
approval-compression direction, `candidate-approval-compression.md`). State
(2026-07-13): **S1–S7 DONE.** S6 CLOSED (first-class `execution_request` block,
versioned contract, frozen NS-1 — maude `a48df3b` / AG `4a63032`). **S7 DONE**
(Ration Citation Containment — the citation is now load-bearing,
`execution_request ⊆ cited_ration`; single verified read; frozen v0 untouched —
maude `ae4cf8a` / AG `16f1b9f`). One authority finding parked:
approval-binds-plan-bytes (`GAP-s6-sandwich-authority-findings.md`, finding 2).

## Queued

NS-2..6 to be authored as maude governed plans (`specimens/ns-*/`) now that
the NS-1 loop is proven. NS-3 and NS-5 carry the adversarial sandwich
(fail-closed gate refactor; vocabulary-boundary plan-envelope exporter).
Open question for the operator: author NS-2..6 first, or land approval-
compression first so the deeper packets aren't a `y`-mashing marathon?
