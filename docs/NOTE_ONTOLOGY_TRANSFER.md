# Ontology Transfer: ATProto Governance Layer

The 5-artifact ontology (MeasurementSnapshot, TransitionProposal, AuthorityReceipt,
RecoveryPlanReceipt, ResetReceipt) from `specs/gaps/3X_BRAIN_DUMP.md` generalizes
beyond LLM runtimes.

A worked example applying it to Bluesky/ATProto infrastructure (PDS + relay layers)
is in `papers/specifications/atproto_governance_transfer_proof.md`.

Key finding: ATProto has identity + integrity (DIDs, signed commits, CIDs) but no
governance receipts. The artifact ontology maps cleanly. Failure geometry generalizes
to multi-signal abuse patterns. "Containment without erasure" is a novel capability
that neither current moderation systems nor ATProto's existing infrastructure provide.

This is a generalization proof, not a roadmap.
