---
plan_version: 1
goal: "NS-2: explicit Candidate authority level between Advise and Stage — name the split 'fresh enough to run' vs 'approved to promote'; ungoverned ceiling caps at Candidate; docs line: fresh -> candidate; Governor approval -> stage/apply"
workspace: "/home/jbeck/git/nightshift"
submitter_kind: human
plan_origin: imported_from_review
provenance:
  author: "operator"
  ref: "nightshift-functional-mvp NS-2"
harness: claude_code
execution_request:
  write_paths:
    - "crates/nightshiftd/src/*"
    - "crates/nightshiftd/tests/*"
    - "docs/architecture/*"
  commands:
    - {program: cargo, argv_prefix: [test]}
    - {program: cargo, argv_prefix: [build]}
  network: denied
  git: denied
  horizon: run
steps:
  - "Read crates/nightshiftd/src/agenda.rs (AuthorityLevel enum: Observe, Advise, Stage, Request, Apply, Publish, Escalate) and crates/nightshiftd/src/pipeline.rs (effective_ceiling at ~line 1287, which caps above-Advise to Advise when no_governor)"
  - "Add variant Candidate to AuthorityLevel strictly between Advise and Stage (derives include Ord — variant ORDER is the semantics; serde snake_case gives wire token 'candidate'). Fix every match that becomes non-exhaustive; do not add a catch-all arm"
  - "Change effective_ceiling: when no_governor, declared levels above Candidate cap at Candidate (was: above Advise capped at Advise). Advise and Observe pass through unchanged. This RENAMES the ungoverned plateau — one rung up in the order, still strictly below Stage, so no effect authority is introduced"
  - "Update the existing effective_ceiling tests to pin the new cap (lowers_to_candidate_without_governor); add tests: Candidate sits strictly between Advise and Stage in Ord; Candidate serializes as 'candidate' and round-trips; existing packets (which never contain 'candidate') still deserialize"
  - "Add one line to docs/architecture/DESIGN.md where promotion/authority levels are described: 'fresh -> candidate; Governor approval -> stage/apply' (a fresh ungoverned run's output is a candidate; Stage and above require Governor approval)"
acceptance_criteria:
  - "cargo test green (all existing 180 + new tests)"
  - "AuthorityLevel::Candidate exists, Advise < Candidate < Stage under Ord, wire token 'candidate'"
  - "effective_ceiling(X, no_governor=true) == Candidate for every X > Candidate; Advise/Observe unchanged; no_governor=false is a no-op"
  - "Diff confined to crates/nightshiftd/{src,tests} + docs/architecture/"
stop_conditions:
  budget_tokens: 120000
  forbidden_paths: ["deploy/**", "scripts/**", ".governor/**", "docs/working/**", "docs/operator/**", "docs/theory/**"]
  halt_if: "AuthorityLevel is anywhere persisted or compared by numeric discriminant rather than name/Ord (inserting a variant would silently renumber), or the change would alter behavior at or above Stage, or any governor-present path changes"
governance:
  authority_system: ag
  playbook_id: "feat.nightshift-candidate-authority"
  playbook_digest: "sha256:b0f87b912481b5a93e027bd44b4a9bf5b0430f482e2af898454a4a77293a097b"
  ration_card_digest: "sha256:c7b487acac4250b733be69fd829517220ee21f3b5ed90df7cc66f0948c7d19d0"
  governance_status: candidate
  projected:
    execution_request.write_paths: "ration_card:sha256:c7b487acac4250b733be69fd829517220ee21f3b5ed90df7cc66f0948c7d19d0"
    execution_request.commands: "ration_card:sha256:c7b487acac4250b733be69fd829517220ee21f3b5ed90df7cc66f0948c7d19d0"
---

Specimen 2 of the nightshift-functional-mvp campaign — the second governed
build packet for a SMALLER MODEL under maude supervision, authored as a
**plan_version 1** envelope from birth (S6 first-class `execution_request`;
S7 ration-citation containment: every request dimension above is
copy-with-citation from the RationCard named in `governance`, so
`execution_request ⊆ cited_ration` holds by construction).

The deliverable names nightshift's missing rung: today an ungoverned run's
ceiling silently collapses to `Advise`, which conflates "we can only advise"
with "this output is a candidate awaiting approval". `Candidate` makes the
second thing a first-class level — *fresh enough to run* is not *approved to
promote* — and becomes the vocabulary NS-5's plan-envelope exporter maps onto
maude's `candidate` posture. One deliberate semantic change rides in this
plan: the ungoverned ceiling moves one rung up (Advise → Candidate), still
strictly below Stage — no effect authority is introduced, and the operator
approves that rename by approving these bytes.

This envelope is **born `candidate`** (M-1 admission rule): maude's admission
REFUSES it (`governance_not_approved`) until the operator's approval act
promotes the status and cites an external witness whose content binds these
exact plan bytes (see README — the witness carries `plan_ref =
sha256(plan.md bytes)` per the approval-binds-plan_ref seam, so NS-1's
approval-custody gap cannot recur here). A status field is never its own
evidence.

Model note: the model pin (`--model …`) is an operator run-time decision on
the maude command line — deliberately not a field in this envelope. A plan
must not dictate spend.
