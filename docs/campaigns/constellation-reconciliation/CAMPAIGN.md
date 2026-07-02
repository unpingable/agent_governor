# Campaign — constellation reconciliation (Packet A)

Status: **FILED, not started** (2026-07-02). Execution vehicle for the AG
handoff/reconciliation packet. Alignment, not expansion.

Capsule: [INVENTORY.md](INVENTORY.md) (prosecutor report lands here) ·
[NEXT.md](NEXT.md) (slices A1–A9, C1–C2) · [DECISIONS.md](DECISIONS.md) (operator
questions) · [STATUS.md](STATUS.md). Routing per `docs/roadmaps/ROUTING.md`.

## Question

> Where does AG's handoff language/mechanics imply more authority, more
> continuity, or more operational readiness than the current constellation shape
> supports — and what is the minimal set of doc patches and named gaps that
> closes the mismatch?

## Scope

Handoff surfaces (REENTRY, LA handoff, claim-custody spine, playbook handoff
renderer docs), governed playbooks language, live-adapter allowlist fossils,
standing/wicket/transition-kernel adapter docs, borrow-ledger doctrine (as
distributed across custody audits + provenance classes), memory custody
(MEMORY.md index + memory files), operator-facing reentry.

Handoff language must distinguish, everywhere it appears:

1. proposal vs authorization
2. receipt vs authority
3. generated text vs operator decision
4. sandbox consumer vs live substrate actor
5. standing grant vs spent/borrowed capability
6. continuity/memory context vs canon/admission

## Deliverable

Prosecutor-style report in [INVENTORY.md](INVENTORY.md):

1. Existing AG handoff surfaces found (verified against disk, hashed).
2. Stale or misleading language (file:line, which distinguish-pair it blurs).
3. Mismatches with current constellation doctrine (NQ basis lifecycle, Lean
   v6/v7, Standing grant-use, wicket SPEC v0.3).
4. Minimal doc/code changes recommended (each separately committable).
5. Explicit do-not-build-yet list.
6. Consolidation recommendation memo (C2) — recommendations only.

## Forbidden (hard constraints, verbatim from the packet)

- Do not implement bounded autopilot.
- Do not promote sandbox playbooks to operational use.
- Do not collapse Governor handoff into authorization.
- Do not treat memory continuity as doctrine admission.
- Do not make generated handoff text self-authorizing.
- Do not add new doctrine unless a concrete mismatch requires it.
- Prefer patching docs and naming gaps over creating new machinery.
- (Consolidation lane) Do not execute merges/renames/archive moves — evidence and
  recommendations only; operator rules per candidate.

## Evidence base

Six-agent exploration sweep 2026-07-02 (condensed into the roadmap program docs);
`~/git/lean/docs/AG-AUDIT-CHECKLIST.md` (the 8-item Lean→AG crosswalk — A3's
anchor); NQ `docs/working/decisions/BASIS_STALE_CONTRACT.md` (ratified 2026-07-02);
`~/git/governor-atlas` constellation case (specified-vs-wired docket).
