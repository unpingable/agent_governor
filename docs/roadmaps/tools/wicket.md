# Roadmap — wicket × AG

**Status:** DRAFT (2026-07-02; ratifies after reconciliation slice A8)
Repo: `~/git/wicket` (HEAD `468883c`, 2026-06-25; SPEC v0.3) · Docket:
governor-atlas constellation case (Wicket edge)

## 1. Contract snapshot — what AG assumes today

- Verdict taxonomy (SPEC §7): `authorized | denied | gap | advisory_only |
  unaccounted`. Frozen AG mapping (transition-kernel packet):
  authorized→PASS · denied→BLOCK · gap→WARN · advisory_only→OBSERVE ·
  unaccounted→ERROR.
- `src/governor/wicket_client.py`: `CookedContext` mirrors SPEC §4 named fields
  (actor_standing, scope_assertion, precedence, revocation, claimed_basis, …)
  plus the AG-side bridge `standing_receipt_id`; AG refuses pre-call
  (`standing_required`, `dangling_receipt_reference`) with downstream call-count
  zero (S1 invariant).
- Playbook admission seam (Slice 3): evidence coherence gates BEFORE the Standing
  seam; binding failure → `playbook_evidence_unbound`; evidence is `observe`,
  authority is `pass`, nothing promotes observe→pass.
- Cook-translation-authority maxim: the cook may translate testimony into policy
  vocabulary; testimony may not choose vocabulary.

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| Fixture corpus is thin: `examples/grants/` holds 2 files — insufficient as the shared Lean/Rust/Python corpus | exploration sweep 2026-07-02 | MED (feeds B3/B5) |
| `standing_receipt_id` not yet absorbed into wicket SPEC (anticipated v0.4); AG remains the seam | `WICKET_REMOTE_STANDING_ADAPTER_GAP.md` | LOW (planned) |

## 3. Named gaps (non-binding)

- `WICKET_SPEC_V04_ABSORPTION_FOLLOW` — when wicket v0.4 lands, AG's S1 pre-call
  gate may collapse into wicket's own refusal paths; until then AG's bridge is
  load-bearing and must not be removed.

## 4. Slices

### R-WICKET-1 — fixture corpus growth (wicket-side, AG-coordinated)
tier: mechanical · executor: codex · prereq: [B2 (invariant map enumerates cases), Q-B3 ruled]
- purpose: wicket's own contract fixtures grow to cover its verdict taxonomy and refusal paths; cross-referenced from the shared differential corpus, not merged into it (B3 recommendation).
- files: `~/git/wicket/examples/grants/cases/**` (wicket idiom; AG crosses in sibling's idiom per standing doctrine).
- tests: wicket's own test harness green (`cargo test` in wicket, real exit code); each fixture named for its verdict/refusal.
- refusal mode: fixtures exercise wicket's closed verdict set — no new verdicts.
- receipt shape: wicket-side commits; AG-side pointer row in the pickup INVENTORY corpus section.
- stop condition: a fixture requires SPEC change — STOP (that is wicket v0.4 work, not corpus work).

### R-WICKET-2 — v0.4 absorption follow
tier: mechanical · executor: codex · prereq: [wicket SPEC v0.4 released]
- purpose: re-audit AG's S1 pre-call gate against v0.4; retire the AG bridge only if wicket now refuses missing/dangling standing itself.
- files: src/governor/wicket_client.py; tests/test_wicket_playbook_admission.py.
- tests: `python3 -m pytest tests/test_wicket_playbook_admission.py -v` exit 0 with call-count-zero invariant preserved.
- refusal mode: refusal locus may MOVE (AG→wicket); it must never disappear.
- receipt shape: commit citing the v0.4 SPEC diff.
- stop condition: v0.4 semantics differ from the gap note's anticipation — obstruction note, re-tier to conceptual.

## 5. Do-not-build

- Wicket does not become a second policy language unless fixtures force it
  (packet stop-line, verbatim).
- No AG-side verdict additions; `unaccounted` stays reserved.
- No removing the AG S1 bridge ahead of v0.4 absorption evidence.

## 6. Operator questions

None wicket-specific. Corpus custody is Q-B3 (pickup DECISIONS.md).
