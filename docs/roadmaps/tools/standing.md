# Roadmap — standing × AG

**Status:** DRAFT (2026-07-02; ratifies after reconciliation slice A8)
Repo: `~/git/standing` (HEAD `d1883c3`, 2026-06-25; +2 unpushed commits) · Docket:
governor-atlas constellation case (Standing edge) · Campaign: this tool's build
lane IS `docs/campaigns/transition-kernel-pickup/` — this file does not duplicate it.

## 1. Contract snapshot — what AG assumes today

- `src/governor/standing_client.py`: SPEC-honoring stub — `verify(receipt_id) →
  StandingReceiptRef{digest, kind}` via injected verifier; refusals
  `standing_required`, `dangling_receipt_reference`. Graduates to a real
  cross-repo client **only** for the grant-use seam (pickup NEXT.md).
- `standing.grant_use.v1` witness packet (D010c asymmetric custody): `used` +
  required `receipt_digest` / `refused` + closed `refusal_class`
  (scope_mismatch | expired | already_spent | replay | subject_mismatch |
  not_found) + null digest / anything else = `no_verified_result`.
- Standing refuses all five load-bearing classes itself (expiry, single-spend,
  replay, subject-binding, scope-mismatch-at-spend) — AG inherits, never
  adjudicates (D010 Model X).
- Doctrine at HEAD: "no standing from predicate satisfaction."

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| Ratified D010 implementation (`1e62ba9` scope refusal, `f101c55` witness packet) exists only as unpushed local commits | pickup STATUS.md "Unpushed" | HIGH (custody hazard — Q-B1) |
| AG's `standing_client.py` remains a stub while the real seam is specified and unblocked | pickup NEXT.md Slice 1b | MED (that's B4, gated on Q-B1) |

## 3. Named gaps (non-binding)

- Refusal-witness receipts (Model A — receipts for non-consuming refusals) parked
  as a **separate future Standing custody campaign** (D010c note). Not AG's to open.

## 4. Slices

### B4 (= pickup Slice 1b) — StandingGrantUseClient + activation.py Office 2
See `docs/campaigns/transition-kernel-pickup/NEXT.md` — the cold-start plan is the
work order (subprocess seam via STANDING_BIN, fake-runner tests for all three
branches, Office 2 rewire, `standing_ok: bool` gone). Authority sandwich applies:
the design is done (conceptual half ratified as D010/D010a/D010c); mechanical
execution by codex; mandatory codex-exec review before merge.
prereq: [Q-B1 confirm+push]

### R-STANDING-1 — StandingClient stub graduation audit
tier: mechanical · executor: codex · prereq: [B4]
- purpose: after B4, every remaining `standing_client.py` stub call-site either uses the real seam or is explicitly marked SPEC-harness-only.
- files: src/governor/standing_client.py, wicket_client.py, cooked_context_orchestrator.py call sites.
- tests: `python3 -m pytest tests/test_wicket_playbook_admission.py tests/test_playbook_spend_chain.py -v` exit 0; grep audit table of call sites in the commit message.
- refusal mode: existing `dangling_receipt_reference` unchanged.
- receipt shape: audit commit citing B4's merge.
- stop condition: a call site whose harness/live status is ambiguous — obstruction note.

## 5. Do-not-build

- No AG-local scope adjudication as authority; no adapter-synthesized scope
  refusal; no mint/continue from carried scope fields (D010, verbatim).
- No supervisor hot-path pickup (`create_session` / `fork_session` /
  `_handle_tool_proposed`) — each needs its own forcing case + slice.
- No bearer tokens anywhere (constellation networking doctrine: keys = standing
  grants).
- No Model A refusal-witness receipts from the AG side.

## 6. Operator questions

- **Q-B1** (pickup DECISIONS.md): confirm + push `1e62ba9`/`f101c55`. Gates B4.
