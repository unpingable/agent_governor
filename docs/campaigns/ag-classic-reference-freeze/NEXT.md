# NEXT — AG-classic Reference Freeze slices

> Campaign is **PROPOSED — NOT RATIFIED**. No slice may start. S0 *is* the ratification
> act. WIP-1 throughout; each slice exits by receipt per loop protocol.

| Slice | Content | Size | Status |
|---|---|---|---|
| **S0** | Ratification act: operator ratifies the card; register capsule in `.governor/campaigns/`; record in `PROGRAM_LEDGER.md`; select first slice in `.governor/loop.json`. Rules D1–D5 (or defers each explicitly). | S | BLOCKED on operator |
| **S1** | **Reference contract census** — produce `docs/REFERENCE_CONTRACT.md` (tier map, every public surface classified into exactly one tier) + authoritative drift list with file:line evidence. Read-only + one new doc. | M | not started |
| **S2** | Truthfulness repairs — fix `golden/README.md` (9→13), `docs/VERSIONING.md` (receipt schema 2→4), corpus prose; file the transition-kernel doc-sync handoff note (their repo executes it). | S | not started |
| **S3** | Roster pinning — CLI command roster manifest + daemon RPC method roster manifest + one pinning test each. | M | not started |
| **S4** | Correspondence ledger — `docs/reference/calculus-correspondence.md`, candidate-pinned to Lean v14; verify `proof-seam-citation-reconciliation` coverage; reconcile `proof_seam.py` header tier vocabulary (ledger-first; cite changes need ledger rows). | M | not started |
| **S5** | Debt triage execution — land §3 dispositions; GAP-M per D1; disclaimers written into `REFERENCE_CONTRACT.md`. | M | not started |
| **S6** | MC vocabulary crosswalk — `docs/reference/mc-crosswalk.md` + lexicon pointer line. | S | not started |
| **S7** | Gate run + release — re-pin ledger at Lean DOI; run G1–G6 with receipts; tag per D5; maintenance-only declaration; `PROGRAM_LEDGER.md` + `loop.json` terminal update. | M | not started |

## S1 in full (the smallest first implementation slice — DO NOT EXECUTE pre-ratification)

**Deliverable:** `docs/REFERENCE_CONTRACT.md`.

**Acceptance:**
1. Every surface named in `.claude/rules/cli-reference.md`, the daemon method roster
   (`daemon.py` dispatcher registrations), `feature-history.md` Live bins, and the
   schema-version constants appears in **exactly one** tier (1–4).
2. Drift list enumerated with file:line evidence (seeded from the CAMPAIGN.md §1 table;
   census may extend it).
3. Zero behavior changes; no file outside `docs/` touched.
4. Suite untouched and green by observed exit code (`governor verify-run -- pytest tests/`).

**Why first:** everything downstream (repairs, pinning, ledger, triage, gates) consumes
this census — it is the falsifiable shape the rest of the campaign is judged against.

## Slice dependencies

```
S0 ─► S1 ─► S2 ─► S7
        ├─► S3 ─────┤
        ├─► S4 ─────┤   (S4 re-pin completes inside S7, at Lean DOI)
        ├─► S5 ─────┤
        └─► S6 ─────┘
```

S2–S6 are independent of each other after S1; WIP-1 still serializes them. S7 is terminal
and requires all prior slices closed with receipts.
