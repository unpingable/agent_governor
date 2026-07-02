# Roadmap — phosphor (gov-webui) × AG

**Status:** DRAFT (2026-07-02; role reframed per Q-C2-1 amendment, same day —
supersedes the morning's "retire or narrow to read/status")
Repo: `~/git/agent_gov_ui/gov-webui` (HEAD `2eaed6d`, 2026-03-28; v0.5.0) · Docket:
governor-atlas constellation case · (backburner duplicate checkout removed by
operator 2026-07-02 — this path is canonical)

## 0. Role (operator reframe, 2026-07-02)

Phosphor is the **web-native operator shell for dedicated workflow lanes** —
the web equivalent of maude's terminal role, NOT a generic Governor dashboard
(guvnah occupied that shape and is retired as premature surface area). AG is
one governed substrate Phosphor can invoke; AG is not Phosphor's whole product
boundary. The existing lanes (chat, builders, read/status) are evidence of the
correct product shape: **focused workflows, not universal daemon control.**

Candidate lane (named, not built): **`ops-casework`** — a web-native operations
casework lane over NQ, Nightshift, AG, and ticketing. The lane presents
findings as operator cases: NQ evidence + basis lifecycle (basis state
unknown/stale/retired, witness clock, source/witness generation); Nightshift
verdict + unsettled claims; AG authority/refusal/receipt state; linked ticket
ownership and action history; the next safe operator move.

**Boundary rule:** Phosphor renders and routes casework. It does not mint
authority, testify evidence, classify operational unsettledness, or make
ticket state authoritative. NQ testifies. Nightshift classifies. AG governs
authority and receipts. Ticketing coordinates work. **The operator decides.**

Relation to `nq-operator` (Q-A7 successor direction): the phosphor lane is the
**near-term home** for ops casework; a standalone greenfield `nq-operator`
remains a possible future product boundary only if the lane outgrows the shell.
One of them, not both, at any given time.

**Governed-session lane (2026-07-02):** phosphor's FIRST new lane is the web
mirror of maude's desk — queue/session/board over `ag_shell_client`,
RPC-only (begins split-brain retirement). Design:
`docs/design/governed-shell/phosphor-lanes.md`; build: governed-shell
campaign GS-16 (registry) + GS-17 (lane).

## 1. Contract snapshot — what AG assumes today

- Split-brain architecture (its ARCHITECTURE.md): chat path over daemon RPC
  (5 methods: `chat.send`, `chat.stream`, `commit.pending`, `chat.models`,
  `chat.backend`); read/status path via **direct Python imports** from the
  governor package, enforced by parity tripwire tests (`test_parity.py`).
- COMPAT.md: tested against Governor `>=2.3.0`; RPC protocol v1.0; StatusRollup
  v1; ViewModel v2; Receipt v2.
- Builders (code/research) are Phase 0: best-effort preflight, `subprocess.run()`
  with no sandbox, labeled not-for-production.

## 2. Observed drift (dated)

| claim | evidence | severity |
|---|---|---|
| AG is at 2.8.1; phosphor tested against >=2.3.0, idle since 2026-03-28 | pyproject.toml both repos; COMPAT.md | HIGH |
| Direct-import read path binds phosphor to AG internals across 5 minor versions — parity tests haven't run against 2.8.1 | ARCHITECTURE.md split-brain | HIGH |
| Only 5/88 RPC methods used; new namespaces invisible to it | daemon.py registry | INFO |

## 3. Named gaps (non-binding)

- `PHOSPHOR_COMPAT_UNVERIFIED_281` — nobody has run phosphor against AG 2.8.1;
  the direct-import path is the likely break point.
- `PHOSPHOR_OPS_CASEWORK_LANE` — the candidate lane in §0; opens at R-PHOS-2.

## 4. Slices (sequencing is load-bearing: 0 → 1 → 2 → 3)

### R-PHOS-0 — disposition/role patch  **(EXECUTED 2026-07-02 — this file)**
tier: conceptual · executor: fable · prereq: []
- purpose: record the reframe (web lane host, not dashboard) so later slices inherit the boundary rule instead of the retired framing.
- files: this file; CONSOLIDATION.md #1; reconciliation DECISIONS Q-C2-1 amendment.
- tests: n/a (doc). · refusal mode: n/a. · receipt shape: the rulings-pass commit.
- stop condition: n/a — done.

### R-PHOS-1 — compat audit vs AG 2.8.1 (record, don't fix)
tier: mechanical · executor: codex · prereq: []
- purpose: run phosphor's own test suite (incl. test_parity.py) against AG 2.8.1; record pass/fail per suite — evidence for lane-host repair scoping.
- files: read-only in ~/git/agent_gov_ui/gov-webui; results → reconciliation INVENTORY §2 (A7 rows).
- tests: phosphor's suite invoked bare, real exit codes recorded per suite (no piped tails).
- refusal mode: n/a (audit).
- receipt shape: one commit with the verbatim run log digest.
- stop condition: suite won't even collect (import errors) — record that AS the finding; do not patch imports.

### R-PHOS-2 — ops-casework lane design (design-only)
tier: conceptual · executor: fable + operator-paired · prereq: [R-PHOS-1]
**(MACHINERY HALF DELIVERED 2026-07-02:** the lane abstraction is designed in
`docs/design/governed-shell/phosphor-lanes.md` and builds as governed-shell
GS-16; the decision envelope already carries `refs[]` for casework. THIS
slice retains the CONTENT half — case-card ontology, source boundaries,
next-safe-move surface — which stays operator-owned.)
- purpose: define the lane contract before any code: case card model, source boundaries (which fields come from NQ export vs Nightshift verdicts vs AG receipts vs ticketing), refusal/receipt rendering, and the "next safe operator move" surface. This names a product boundary — the ontology gets nailed to the table before a mechanical executor builds cards.
- files: design doc (phosphor-side or working/ note first); no daemon pin bump, no direct-import expansion, no NQ/ticketing integration in this slice.
- tests: n/a (design); the contract enumerates R-PHOS-3's work orders.
- refusal mode: the §0 boundary rule is the acceptance frame — any design where the lane mints/testifies/classifies fails.
- receipt shape: design-doc commit citing nq.finding_snapshot.v1, NS unsettled enum, AG receipt shapes.
- stop condition: the contract needs a field none of the four substrates can honestly supply — name it as a substrate gap (their roadmaps), don't synthesize it in the UI.

### R-PHOS-3 — lane implementation (blocked)
tier: mechanical · executor: codex · prereq: [R-PHOS-2, compat repairs scoped from R-PHOS-1]
- purpose: build the lane per the R-PHOS-2 contract — cards after ontology.
- files/tests: enumerated by R-PHOS-2.
- refusal mode: renders substrate refusals verbatim; adds none.
- receipt shape: phosphor-side commits citing the lane contract.
- stop condition: any deviation from the lane contract — obstruction note, back to R-PHOS-2.

## 5. Do-not-build

- No generic-dashboard direction, ever (that was guvnah; it's retired).
- No version-pin bump ahead of R-PHOS-1 evidence.
- No Phase-1 builder sandboxing inside this program (builders are a separate
  lane question, untouched by the casework work).
- No new daemon endpoints justified solely by phosphor's direct-import
  workaround.
- The lane never becomes authoritative for tickets, evidence, classification,
  or authority (§0 boundary rule, verbatim).

## 6. Operator questions

None open. Q-C2-1 as amended 2026-07-02: phosphor = web-native lane host;
candidate ops-casework lane; audit → design → build sequencing.
