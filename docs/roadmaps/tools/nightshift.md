# Roadmap — nightshift × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/nightshift` (HEAD `01a65bf`, 2026-06-12) · Docket: governor-atlas
constellation case · AG seam: `src/governor/nightshift_adapter.py` (+
`specs/gaps/GOV_GAP_NIGHTSHIFT_ADAPTER_001.md`) · First natural Governor dogfood

## 1. Contract snapshot — what AG assumes today

- Three RPC methods: `nightshift_check_policy`, `nightshift_record_receipt`,
  `nightshift_authorize_transition`.
- Frozen verdict map: `PASS→ALLOW`, `BLOCK→DENY`, `ESCALATE→REQUIRE_APPROVAL`,
  `WARN→DOWNGRADE`. Authority ladder `observe|advise|stage|request|apply|publish`
  (observe/advise run governor-free; higher levels gate).
- v4 receipts: `RecordReceiptRequest.unsettled` = tuple of `NonDischargeClaim`,
  closed enum {AUTHORITY, EVIDENCE_SUFFICIENCY, FRESHNESS, SCOPE, STANDING,
  CONSUMER_RELIANCE}.
- MVP-A path witnessed end-to-end (NS cook → Wicket → WLP; NS refuses to cook on
  NQ receipt status ≠ verified; WLP warranty refused on freshness-unsettled).

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| Only the FRESHNESS NonDischargeKind has a wired refusal rule; the other five are accepted-but-unenforced | working note `nightshift-governor-unsettled-integration-state.md` (2026-06-09) | MED |
| Governor CLI renders `unsettled` as raw JSON dump (no text mode) | same note | LOW |
| Receipt emission reachable only via flags ("configured-only"); default watchbill is governor-blind **by design** (Option 3) | same note | INFO (design choice, not drift) |

## 3. Named gaps (non-binding)

- `NS_UNSETTLED_KINDS_UNWIRED` — AUTHORITY / EVIDENCE_SUFFICIENCY / SCOPE /
  STANDING / CONSUMER_RELIANCE refusal rules scoped but not implemented.
- `NS_UNSETTLED_CLI_RENDERING` — operator-facing text rendering of unsettled
  claims.

## 4. Slices

### R-NS-1 — remaining NonDischargeKind refusal rules (authority sandwich)
tier: conceptual → mechanical → review · executor: fable/codex/codex-exec · prereq: []
- purpose: each of the five unwired kinds gets an explicit rule (refuse / downgrade / pass-with-record), designed once, executed per-kind.
- files: src/governor/nightshift_adapter.py; tests/test_nightshift_adapter.py.
- tests: `python3 -m pytest tests/test_nightshift_adapter.py -v` exit 0; one pin per kind, incl. the negative (unknown kind never silently passes).
- refusal mode: closed NonDischargeClaim enum only — no new kinds; unknown kind → typed refusal (allowlist doctrine).
- receipt shape: per-kind commit citing the design slice + the 2026-06-09 working note.
- stop condition: a kind whose correct rule needs NS-side semantics not yet defined — obstruction note naming the kind; do not guess NS intent.

### R-NS-2 — CLI text rendering of unsettled
tier: mechanical · executor: local-qwen · prereq: [R-NS-1 design half]
- purpose: `governor` CLI renders unsettled claims as labeled text, not raw JSON.
- files: the CLI render path identified in the design half (expected: cli.py nightshift section).
- tests: `python3 -m pytest tests/test_nightshift_adapter.py -v` exit 0 + a render pin (kind name appears in output).
- refusal mode: n/a (display).
- receipt shape: one commit.
- stop condition: rendering requires schema change — obstruction note.

### R-NS-3 — receipt-emission default-path question
tier: conceptual · executor: fable → operator · prereq: [R-NS-1]
- purpose: decide whether the governor-blind default watchbill remains the default once all six kinds enforce (Option 3 was chosen when only FRESHNESS worked).
- files: DECISIONS entry in the reconciliation campaign; NS-side change only after ruling.
- tests: n/a (decision).
- refusal mode: n/a.
- receipt shape: DECISIONS entry.
- stop condition: this is a question, not a build — no flag-flipping.

## 5. Do-not-build

- No new NonDischargeClaim kinds (closed enum is the contract).
- No flipping the governor-blind watchbill default without the R-NS-3 ruling.
- No NS-side edits from AG without coordinating in NS idiom (cross-repo standing
  doctrine).

## 6. Operator questions

- R-NS-3 (default watchbill posture) — filed when R-NS-1 completes.
