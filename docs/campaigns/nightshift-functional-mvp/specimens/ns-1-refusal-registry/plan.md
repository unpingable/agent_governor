---
plan_version: 0
goal: "NS-1: closed RefusalKind enum + typed refusal field on nightshift's Packet (free-text stays display-only)"
workspace: "/home/jbeck/git/nightshift"
submitter_kind: human
plan_origin: imported_from_review
provenance:
  author: "operator"
  ref: "nightshift-functional-mvp NS-1"
harness: claude_code
scope_allowlist:
  - "crates/nightshiftd/src/**"
  - "crates/nightshiftd/tests/**"
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
    scope_allowlist: "ration_card:sha256:90ea2a86c71034c7f244399ee80da2f470c97afa54218094b20f9377611c7b69"
    stop_conditions.forbidden_paths: "queued_playbook:nightshift-functional-mvp-ns1/feat.nightshift-refusal-registry"
---

Specimen 1 of the nightshift-functional-mvp campaign — the first governed
build packet executed by a SMALLER MODEL under maude supervision (the
dogfood). This envelope was compiled by the integrator session and is
therefore **born `candidate`** per the M-1 admission rule: a compiler
cannot approve its own plan by writing the word.

The queue item in this directory is `operator_approved: false` and the
real parser REFUSES to construct it (staging receipt in README.md —
"provenance does not grant approval"). The operator's flip is the only
thing that changes that.

Model note: the model pin (`--model claude-haiku-4-5`) is applied at run
time by the operator on the maude command line — it is deliberately NOT a
field in this envelope. A plan must not dictate spend.
