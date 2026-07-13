---
plan_version: 1
goal: "NS-1R (S6 v1 successor): closed RefusalKind enum + typed refusal field on nightshift's Packet (free-text stays display-only)"
workspace: "/home/jbeck/git/nightshift"
submitter_kind: human
plan_origin: imported_from_review
provenance:
  author: "operator"
  ref: "nightshift-functional-mvp NS-1 → S6 v1 successor"
harness: claude_code
execution_request:
  write_paths:
    - "crates/nightshiftd/src/*"
    - "crates/nightshiftd/tests/*"
  commands:
    - {program: cargo, argv_prefix: [test]}
    - {program: cargo, argv_prefix: [build]}
  network: denied
  git: denied
  horizon: run
steps:
  - "Read crates/nightshiftd/src/packet.rs (Packet struct) and the liveness-gate failure path in crates/nightshiftd/src/pipeline.rs (liveness_gate_failed)"
  - "Define a closed enum RefusalKind in packet.rs: LivenessStale { age_seconds, threshold_seconds }, BasisInvalidated, PreflightHeld — serde-serializable, no catch-all Other variant"
  - "Add optional field `refusal: Option<RefusalKind>` to Packet; None everywhere except refusal paths"
  - "Populate refusal = LivenessStale{..} in liveness_gate_failed, carrying the same numbers the free-text blocked[] string already renders; the free-text stays untouched as display"
  - "Add tests: stale-gate packet carries typed LivenessStale with correct fields; fresh path carries refusal: None; serialization round-trips"
acceptance_criteria:
  - "cargo test green (all existing 168 + new tests)"
  - "Stale-witness packet JSON contains the typed refusal object AND the original free-text blocked[] entry"
  - "Diff confined to crates/nightshiftd/{src,tests}"
stop_conditions:
  budget_tokens: 120000
  forbidden_paths: ["docs/**", "deploy/**", "scripts/**", ".governor/**"]
  halt_if: "the enum would require changing liveness-gate semantics, or removing/altering the free-text display strings"
governance:
  authority_system: ag
  playbook_id: "feat.nightshift-refusal-registry"
  playbook_digest: "sha256:0c0f0973f21ad3d8fb93b24e688fc4290971729dcdb9af9fec7915c07bac03a3"
  ration_card_digest: "sha256:90ea2a86c71034c7f244399ee80da2f470c97afa54218094b20f9377611c7b69"
  governance_status: candidate
  projected:
    execution_request.write_paths: "ration_card:sha256:90ea2a86c71034c7f244399ee80da2f470c97afa54218094b20f9377611c7b69"
    execution_request.commands: "ration_card:sha256:90ea2a86c71034c7f244399ee80da2f470c97afa54218094b20f9377611c7b69"
---

NS-1R — the **v1 successor** to the NS-1 refusal-registry specimen, authored for
S6 (first-class `execution_request` block). It expresses the same intended
operation as NS-1 but is **not the same approved plan**: NS-1 was compiled and
executed under the v0 inferred-request contract, and its bytes stay frozen and
untouched. Per the S6 doctrine —

> Approval attaches to plan bytes, not reconstructed intent; schema migration
> creates a successor artifact rather than revising an approved predecessor.

— NS-1R has a fresh identity, a fresh `plan_ref`, and will carry its own
approval act. It inherits NS-1's intent, not NS-1's approval.

**What v1 changed here.** The request is now legible in the plan bytes the
operator approves: `execution_request.write_paths` (replacing the top-level
`scope_allowlist`) and `execution_request.commands` (structured `{program,
argv_prefix}`, replacing the shell commands that v0 silently pulled out of the
RationCard at projection time). Both are copy-with-citation from the same
RationCard (`sha256:90ea2a86…`) and cited in `governance.projected`, so the §7
verification still binds them to their AG source — legibility up, authority
binding intact.

This envelope is **born `candidate`** (M-1 admission rule): maude's admission
REFUSES it (`governance_not_approved`) until the operator's approval act
promotes the status and cites an external witness. A status field is never its
own evidence. See `README.md` for the approval + dry-run procedure.

Model note: the model pin (`--model …`) is an operator run-time decision on the
maude command line — deliberately not a field in this envelope. A plan must not
dictate spend.
