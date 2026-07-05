# Ratification memo — work-container contract v1

> **STATUS: MEMO — prepares an operator act; ratifies nothing itself.**
> public-mvp Sprint 4, packet 14. Assembled 2026-07-05 by the campaign
> integrator (Fable). The act requested at the end is the operator's alone.

## 1. What is proposed for ratification

The four contract documents + four schemas, at these exact bytes
(sha256 prefixes, HEAD `fe560e6`):

| Artifact | Digest |
|---|---|
| `docs/api/work-container-contract.md` | `306de9007aed2d58…` |
| `docs/api/provider-integration.md` | `6c6ab1d43c4b1ec4…` |
| `docs/api/agent-integration.md` | `115a4deb86a1f3c3…` |
| `schemas/work_container.v1.json` | `af1dedb12fa0c9aa…` |
| `schemas/provider_descriptor.v1.json` | `fbf7f334ed164e77…` |
| `schemas/provider_run_receipt.v1.json` | `a242dbaaa83f368d…` |
| `schemas/provider_obstruction.v1.json` | `3000a742f5fa25e0…` |

Current status line (all): *"DRAFT / CANDIDATE — non-binding until ratified
AND a first conforming implementation exists."*

## 2. Evidence chain

1. **Live shape proven (projection direction).** CD-4B run
   `sess_aabb2a056f9f` (2026-07-04): governed plan admitted with all four
   citations verified; supervised run to `supervised keep` on a
   validator-clean ReviewPacket. `project_cd4b_work_container()` projects
   that proven run into a schema-valid sealed container —
   `specimens/cd4-docs-normalize/work_container.v1.json`; every field traces
   to a shipped object. 14 pins in `tests/test_work_container.py`
   (registry-independence, provider-success≠admission, seal-mismatch
   fail-closed).
2. **Admission is resolvable, not narrative (S4b).**
   `work_container_bridge.py`: admission = first-class `GateReceipt`
   (gate `work_admission`), `admission_ref = sha256:<receipt_id>`;
   `resolve_admission` refuses unless the receipt's evidence binds the
   container's WHOLE basis (forged container cannot borrow a receipt).
   Self-verifiable pair: `work_container.s4b.json` +
   `admission_receipt.json` (cross-check re-verified live 2026-07-05,
   specimens/README.md). 37 tests; two codex adversarial passes at build
   time (F1/F2 closed).
3. **First provider, structurally.** `provider_descriptors.py` +
   `provider_registry.py` (Slice 2/3): the `claude_code` descriptor is
   registered; registration verifies STRUCTURAL conformance only and is
   fail-closed on any authority claim (`authority_claims: []` enforced,
   `maxItems: 0` in schema). Maude is deliberately NOT a provider
   (exclusion recorded at S3).
4. **Live supervised evidence for the provider itself.** claude_code is the
   only live supervised backend; CD-4B ran through it; maude desk surfaces
   live-daemon-verified 2026-07-05 (`receipts-s2-maude-smoke.md`).

## 3. What the evidence does NOT show (the honest wrinkle)

Contract §6 (provider-integration) distinguishes **structural** conformance
(descriptor shape, verified at registration) from **runtime** conformance
(live evidence that the provider accepts a `work_container.v1` on the wire
and returns `provider_run_receipt.v1`). The **consumption direction is not
yet demonstrated**: CD-4B's container was *projected from* the proven run;
no dispatcher has yet handed a container *to* claude_code and consumed its
run receipt. S4 wiring ("live governed_dispatch consuming a WorkContainer
to route a run") remains gated, as does everything behind the cage.

Declaring claude_code "conforming" without qualification would launder
projection evidence into consumption evidence. The recommendation below
therefore names the grade.

## 4. Invariant-language checklist (must survive ratification verbatim)

- "A schema-valid WorkContainer is NEVER admission; reliance requires
  re-verifying the AG gate receipt." (schema comment + contract)
- "An agent can ask. A provider can perform. Only AG can admit."
- "Decomposition must preserve custody. Recomposition must not create
  authority."
- Provider status vocabulary: lifecycle only; never
  `refused`/`held`/`inadmissible`; `ag_review` always null from providers.
- `authority_claims: []` (maxItems 0) on every descriptor.
- Conformance ≠ trust ≠ admission ≠ standing (§6 list).

Ratification edits ONLY status lines; if any edit would touch a sentence
above, stop and re-review.

## 5. Options

**A — Ratify v1 with graded conformance (RECOMMENDED).** Status lines
become: *"v1 — RATIFIED <date> (operator). First provider: `claude_code`,
STRUCTURALLY conformant (registered, fail-closed) with live supervised
evidence via CD-4B (`sess_aabb2a056f9f`); RUNTIME (container-consumption)
conformance not yet demonstrated — gated on S4 dispatch wiring. Schema
changes from here are versioned (v1 → v2), not silent."* Matches the
evidence exactly; gives external consumers a stable v1 shape to build
against; keeps the consumption gate visible.

**B — Ratify shapes only, defer any provider declaration.** Weaker public
story (the DoD's "exactly one conforming provider" unmet); safest wording.

**C — Stay DRAFT.** Blocks DoD item 5 and the S5 front-door claim that the
interop surface is stable.

## 6. The operator act (if A)

1. Edit the status block in the 4 docs + 4 schemas to the Option-A wording
   (one commit, operator-authored or operator-approved).
2. That commit message is the ratification record; cite this memo's path +
   the digest table above.
3. Post-act: campaign STATUS updates DoD item 5 to met-with-grade; the S5
   front door quotes the graded wording, never "conforming" bare.

Until the act happens, everything above remains CANDIDATE.
