# Cartography intake candidates — reconcile later (filed 2026-06-14)

`~/git/cartography` (the May constellation-coordinator venue) was **archived 2026-06-14**
(`cartography/README.md` status header). It was ~90% closed history (the 5-tool MVP-A demo,
public-doc drafts, external-review intake — doctrine candidates already adopted verbatim into
NS/Wicket/NQ/Continuity). Patterns that mattered to AG were already reworked here under new
names (`state-aperture-lag` → [[feedback_completion_redshift]]; `verifier-wicket-overlap` and
the cartographer/clerk role → `docs/constellation-zoning.md` / `constellation-wire-plan.md`).

Two coordination notes were **orphaned**: they were parked "awaiting cartographer curation," a
role that was abandoned when coordination moved to per-repo Claudes + this AG session. They are
filed here as **AG intake candidates** — handles for review, NOT authorization to build (YAGNI
scope: name early, ratify lazily). Reconcile when an AG forcing case appears, not before.

## Candidate 1 — Remote Standing Boundary (cross-tool)
- Source: `cartography/coordination/nq-REMOTE_STANDING_BOUNDARY.md` (NQ-Claude, 2026-05-27).
- What: a shared primitive for remote calls across the constellation — five layers (identity /
  authz / standing / transport / receipt-audit), four exposure profiles (homelab_public_readonly,
  private_local, authenticated_remote, component_peer), a `StandingResolver` interface, and
  standing-bearing receipt fields.
- AG status: **AG's own side is already covered** — `docs/constellation-zoning.md`, the
  networking-patterns memory ("zoo closed 2026-06-12"), and `standing_client.py`. What is
  ownerless is the *cross-tool* doctrine (the version that NQ/NS/Wicket all compose against).
- Reconcile trigger: a cross-host AG forcing case (per `constellation_networking_patterns` memory,
  build is gated on the first cross-host forcing case — not co-location). Until then: pointer only.
- Intake question when it fires: does AG's zoning already *contain* the cross-tool boundary, or is
  there a residual the zoning doesn't name? (Likely the former — check before importing anything.)

## Candidate 2 — Self-Subject Collapse (shared gap)
- Source: `cartography/coordination/SELF-SUBJECT-COLLAPSE.md` (2026-05-28).
- What: the failure mode where a subject cannot reconcile a finding about itself and no external
  reconciler exists. Three forcing instances: NS (may not resolve a finding whose subject is NS),
  NQ-on-NQ (Tier 0, no external reconciler), agent_gov (the `GOV_GAP_BASIS_001` family). Promotion
  was gated on an operator choice between three resolution paths (architectural artifact / routing
  convention / intentional dangling) — never chosen.
- AG status: **AG's instance appears already answered, unnamed** — operator-fiat standing is the
  external reconciler for AG self-promotion (P3.1 activation + P4 promotion both *require* an
  operator basis precisely because AG cannot be its own promoter). Confirm this reading holds
  before doing anything.
- Reconcile trigger: if AG ever needs to record *why* operator-basis is structurally required (a
  "self-subject collapse → operator is the external reconciler" doctrine note), this is the
  upstream provenance to cite. Otherwise it stays NS/NQ's shared gap to own.

## Not taken
- `cartography/coordination/wlp-notes-as-wire-layer-for-standing-boundary.md` — WLP-side concern,
  left parked under the general archive (not an AG intake candidate).
