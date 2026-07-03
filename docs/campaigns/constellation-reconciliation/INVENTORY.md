# Inventory — constellation reconciliation (prosecutor report)

**Status:** SKELETON (2026-07-02). Sections fill as slices land (see
[NEXT.md](NEXT.md)); A8 assembles the final report; A9 reviews it adversarially.
Nothing in this file authorizes anything.

## 1. Handoff surfaces found (A1 — executed 2026-07-02)

| path | exists | sha256-12 | last-commit | verdict/notes |
|------|--------|-----------|-------------|---------------|
| docs/REENTRY.md | YES | dc748b1f4a92 | 5bc6b8a 2026-07-01 | ✓ matches description; IDENTICAL bytes on main and this branch |
| working/linear-accountant-handoff.md | YES | e9e9455ba631 | 026603b 2026-06-03 | ✓ matches (§9 handoff-shape response) |
| docs/architecture/claim-custody-spine.md | YES | 50ba5bff657a | 5f7e87f 2026-06-10 | ✓ matches (receipt chain via GateReceiptSystem) |
| specs/gaps/GOV_GAP_STATE_REENTRY_PROTOCOL_001.md | YES | 96b8876cd854 | 3522b27 2026-05-03 | ✓ matches |
| docs/playbooks/live-adapter-allowlist-review.md | **NO (this branch)** | — | — | on conveyor branch only; superseded fossil w/ 11 inherited ration-card terms |
| src/governor/playbooks/handoff_renderer.py | **NO (this branch)** | — | — | on conveyor branch only (S6, `4022f22` LOCAL per REENTRY) |
| docs/playbooks/next-gate-selection-review.md | **NO (this branch)** | — | — | on conveyor branch only |
| docs/playbooks/* (9 further docs) | **NO (this branch)** | — | — | entire docs/playbooks/ dir is conveyor-branch content |

**Critical finding (branch visibility):** the playbook handoff surfaces exist
only on `feat/playbooks-synthetic-conveyor`; this branch and that one are
PARALLEL lanes (~46 conveyor commits not here; neither ancestor of the other).
`docs/REENTRY.md` is byte-identical on both branches **but references files
that exist only on the conveyor branch** — a reader on main-lineage branches
follows pointers into absence. Resolves at merge; until then REENTRY.md's
implicit claim "these paths exist" is true only on one lane. (Recorded, not
fixed — fixing = merging, which has its own checkpoint.)

Cross-references: all docs/roadmaps/README.md ↔ campaign ↔ tools/*.md links
resolve (17/17 tool files, 4/4 campaigns, ROUTING/PARKED/CONSOLIDATION).

Additional handoff-describing docs found (grep "handoff", not in the claimed
set): working/handoff-2026-07-02-roadmap-program.md, docs/constellation-zoning.md,
docs/interfaces/cli.md, docs/loop-protocol.md, docs/RECEIPT_SNAPSHOT_001.md,
docs/reference/internal-ops-glossary.md — swept by A2.

**Contradictions (verbatim, per stop condition):**
1. Campaign NEXT.md A1 says "docs/playbooks/handoff-renderer surfaces" (a docs/
   path); REENTRY.md line 56 places it at `handoff_renderer.py` (src). The
   docs/ path never existed — the slice text inherited an imprecise pointer.
2. The HandoffPacket seal contract ("content-sealed sha256(canonical_body),
   tamper-evident … NO authority-permitting surface") is documented **only in
   REENTRY.md prose** — no ratifiable spec doc describes the seal. Narrative
   custody of a load-bearing format. → feeds §4 minimal changes.

## 2. Stale or misleading language (A2, A7)

### A2 — distinguish-pairs sweep (executed 2026-07-02, codex-exec adversarial, 9 docs inlined; zoning deferred)

Sweep verdict: **"Most doctrine docs are disciplined; the CLI reference is the
main laundering surface."** Cleanest doc: linear-accountant-handoff.md. 13
findings + 3 unclassified; dispositions:

| finding (condensed) | pair | disposition |
|---|---|---|
| spine doc "emits authorized GateReceipt" / "emits granted GateReceipt (la_outcome=Granted)" | 2, 5 | **FIXED** (A4/A2 patch commit): receipts now RECORD verdicts; capability named as the LA token |
| handoff note styled as the decision record; push rule as prose | 3 | **FIXED**: note names itself summary-not-record; DECISIONS files win |
| cli.md: "Apply verified proposal" (1) · resolve/rule/except wording as if CLI = ruling (3, ×3) · override creation without named authority (1) · anchor `--type canon` (6) · `autonomous run` blurs consumer/actor (4 — sweep's WORST) · `tune --apply` (1) · glossary PROPOSED-name-in-copy (1) | 1,3,4,6 | **UPGRADED per A9**: user-facing prose is itself a laundering surface regardless of the gates behind it. Disposition raised from fix-on-touch to a NAMED mechanical slice (backlog `cli-reference-wording-pass` — local-qwen-eligible work order: reword the 9 quoted labels per the standing rule, no semantic changes). `autonomous run` + `anchor --type canon` additionally flagged to the governed-shell campaign. |
| unclassified: loop-protocol "explanatory…wins" self-contradiction; RECEIPT_SNAPSHOT status contradiction; cli.md "everything is a command" flatten | — | recorded; loop-protocol wording fix-on-touch |

### A7 — UI/client drift record (executed 2026-07-02; record only, no fixes)

| surface | claim on record | measured 2026-07-02 | disposition |
|---|---|---|---|
| guvnah COMPAT.md | requires `>=2.3.2 <2.4.0` | AG at 2.8.1 → hard-refuses | moot: **RETIRED** (Q-A7); pin stays broken by ruling |
| phosphor COMPAT.md | "tested against Governor >=2.3.0" | **R-PHOS-1: 481/481 tests green vs 2.8.1** incl. all 10 parity tripwires; zero install/collection failures | COMPAT.md text is stale-pessimistic; effective pyproject floor is vacuous `>=0.1.0` — the real pin is whatever sync-deps.sh copies at Docker build. Evidence now exists for a pin decision at R-PHOS-2; no bump performed |
| maude RPC client | 43 methods assumed live | **R-MAUDE-1: 30/31 present; `proposals.json` GONE** (maude client/rpc.py:574 calls it inside operator_snapshot; daemon registry lacks it) | silent-drift specimen — exactly the failure class ag_shell_client (GS-8/9) kills by construction; no repair (client is replaced by GS-9) |
| maude COMPAT | requires `>=2.3.1 <2.4.0` | not re-tested (superseded by GS-9 path) | record only |

Distinguish-pair note (amended per A9): the pin rows are liveness drift; the
dead `proposals.json` sits inside maude's operator_snapshot RENDERING — the
snapshot is testimony for the operator's eyes, and nothing consumes it as
operator authority (daemon-side operator.snapshot is a separate, live method),
but the report should not have called the category closed without saying so. The laundering-relevant finding in this section is §1's
contradiction 2 (HandoffPacket seal specified only in REENTRY prose).

## 3. Constellation doctrine mismatches (A3a/A3b, A4)

### A3b — AG-AUDIT-CHECKLIST adjudication (executed 2026-07-02, against lean HEAD `762967c` / v7.0.0)

Checklist: `~/git/lean/docs/AG-AUDIT-CHECKLIST.md` (itself CANDIDATE,
documentation-only — findings are theorem-named smells, not convictions).
Grades per its reporting discipline: **screen** (smell) vs **wall** (path
should not exist). Evidence basis: §A3a tables.

| # | checklist item | theorem | verdict |
|---|---|---|---|
| 1 | Universal evidence currency | `EvidenceCurrencyFree`, `UniversalStamp` [SCRATCH-resident v6] | **PASS.** No receipt kind funds every gate: each seam demands its own upstream kind (standing digest → wicket; admission receipt → LA request; grant receipt → consume). The shared GateReceipt FORMAT is not a currency (format ≠ funding). No confidence-like claim-blind signal accepted anywhere (confidence_sanity invariant + grounding audit refuse it). Judgment flag per the named false negative: `parent_receipt_ids` is broad linkage vocabulary — linkage, not funding; keep it that way. |
| 2 | Universal crossroads | `MasterFree`, `UniversalCrossroads` | **PASS (screen-grade note).** No stage converts every artifact class. The gate-receipt STORE is an index hub, but payloads do not convert through it (the checklist's own benign-router false-positive caveat applies). cooked_context_orchestrator composes ONE lane, not every pair. |
| 3 | Midpoint matching | `index_connectivity_does_not_imply_derivability` [1.0-adjacent v4] | **PASS at code level; one DOC-level firing.** Implemented hops match field-for-field (WicketVerdict.receipt_id → admission_receipt_id → LA eligibility_reference; §3a.2). The firing: the external packet's assumed wicket→kernel verdict map (authorized→PASS…) was an index-level diagram whose midpoints DON'T match the implemented shape — caught by B1 (pickup INVENTORY). The theorem's exact failure mode, at documentation altitude. |
| 4 | Provenance rooting | `eentail_iff_read_rooted`, `Recall ⊬ Reliance` | **PASS.** Chains enumerate to marked roots (standing digest / NQ finding_id / closed origin_mode / EXPLICIT operator-fiat bootstrap — the discipline-compliant "explicit assumption" root). One evidence per hop via parent_receipt_ids; `governor why` walks it. No reliance rooted in confidence signals found. |
| 5 | Refresh/renewal | `refresh_is_inexpressible` (F1) | **SCREEN-GRADE FINDING (F-A3b-1).** No receipt re-stamping found; TTL revalidation acquires NEW evidence (compliant); standing_spendability's two-clock gate IS the `use k ≤ r` freshness-ordering shape. BUT: session-continuity capsules "resume intent + constraints + AUTHORITY" across sessions — authority carried forward in a capsule is a copy-forward lane if consumed without re-verification at resume. Nothing in the extracted schema FORCES re-verification on capsule resume. Minimal change → §4. |
| 6 | Burden shedding | `caveat_dropping_is_inexpressible` (F3) | **PASS.** Wicket's `gap` caveat survives as the typed `admission_gap_accounted` refusal kind (caveat-as-vocabulary, the strong form). Compaction drops leave per-item content-hash tombstones (§3a.5); pending violations live outside the compacted stream. Dual-emission (gate_receipt ∥ receipt_v1 bridge) preserves verdicts 1:1 by design — flag: any future divergence between the two emissions is a caveat-shedding lane; the bridge must stay lossless. |
| 7 | Linearity | `one_receipt_cannot_license_two_discharges` (SEQ2/3) | **SCREEN-GRADE FINDING (F-A3b-2).** Spend-side linearity is solid (LA consumption_event_id exactly-once; durable-spend content-addressed key; Standing terminal Used). But REQUEST-side: nothing AG-side refuses ONE admission receipt funding TWO capacity requests (`eligibility_reference` reuse unfenced; request idempotency_key optional and LA-side, §3a.4). One receipt may currently license two discharges at the wicket→LA hop. Named-gap → §4; cross-repo (LA contract) so record-first, no unilateral fence. |
| 8 | Checkpoint custody | `checkpoint_mints_nothing`, `settlement_preserves_live_multiplicity` | **PASS.** Compaction output contains nothing the input lacked (receipts ABOUT drops, not resolutions); DroppedItem is per-item so multiplicity survives; blob purge keeps hashes forever (hash_retention=-1) with BLOB_EXPIRE events; RecoveryStore cleanup leaves the tombstone. |

**Adjudication summary:** no wall-grade findings; two screen-grade findings
(F-A3b-1 capsule-authority refresh lane; F-A3b-2 admission-receipt request-side
linearity); one doc-level midpoint firing already recorded via B1. Citation
tiers honored: v6/SCRATCH screens used as SCREENS only.

### A3a appendix — schema extraction for the Lean checklist (executed 2026-07-02)

#### 3a.1 Receipt-kind × gate matrix

| Gate | Emission site | Verdicts | Evidence multiuse |
|-----------|---------------|----------------------|-------------------|
| evidence_gate | evidence_gate.py:1020 | pass, warn, block | subject_hash reused by receipt_v1_bridge.py:1065; evidence_hash reused at receipt_v1_bridge.py:344 |
| standing_seam | standing_client.py:244 (refusal) / :305 (pass) | block / pass | cited_standing_receipt_id consumed by wicket_client.py:169; side-channel `_last_verified_receipt_id` consumed at wicket_client.py:486 |
| wicket_seam | wicket_client.py:328 (refusal) / :393 (pass) | block / pass | receipt_id consumed by linear_accountant_client.py:663; parent from standing verify wicket_client.py:492 |
| la_seam | linear_accountant_client.py:474 / :540 / :595 | block / pass(grant) / pass(consume) | admission_receipt_id in evidence; consume cites prior grant :860 |
| standing_spendability_seam | standing_spendability.py:296 | pass, block | parent_receipt_ids threaded :288 |

#### 3a.2 Hop-chain midpoint fields

| Field | Emitting | Consuming | Join identity |
|------------|----------------|-----------------|----------------|
| parent_receipt_ids | standing_client.py:236 (empty = origin) | wicket_client.py:312-314; la_client:468-469; spendability:288 | exact receipt_id string in list |
| cited_standing_receipt_id | standing_client.py:239 | la_client:680; wicket_client:316 | exact string |
| standing_receipt_id | wicket_client.py:170 (CookedContext) | standing_client.py:315; **LA does not consume it (no_surface)** | standing service receipt id |
| admission_receipt_id | wicket_client.py:195 (WicketVerdict.receipt_id) | la_client:277 → LA `eligibility_reference` :728 | exact receipt_id → becomes LA field |
| parent_grant_receipt_id | la_client:756 (GrantedResult) | consume() :797 → parent :860 | exact grant receipt_id |
| finding_id | cooked_context_orchestrator (NQ FindingSnapshot) | standing_client:318; wicket_client:407 | exact string or None (origin if absent) |

#### 3a.3 Evidence-chain roots

| Root kind | File:line | Marking |
|-----------|-----------|-------------------|
| standing receipt (remote) | standing_client.py:350 (verify lookup) | StandingReceiptRef.digest (sha256) + kind |
| NQ finding origin | cooked_context_orchestrator.py:407 | optional finding_id; absent → CLI/stub origin :154-155 |
| origin_mode (AG-internal) | orchestrator :154-180 | CLOSED_ORIGIN_MODES membership, validated at construction :196 |
| origin_mode (NQ-sourced) | orchestrator :160-163 | consumed VERBATIM from FindingSnapshot; no AG synthesis |
| chain terminus | standing_client.py:236 | empty parent_receipt_ids = origin |

#### 3a.4 Single-use consumption points

| Mechanism | Key | File:line | Replay refusal |
|-----------|-----------------|-----------|-------------------|
| LA consumption_event_id | caller-supplied string | la_client:284 → :825 | AlreadyConsumed → :872 `already_consumed` |
| LA idempotency_key (request) | optional caller string | la_client:280 → :731 | **no_surface AG-side** — LA responsibility |
| DurableSpendLedger.consume | content-addressed authority-bound key | playbooks/durable_spend.py | refuses before LA call (conveyor branch) |
| Standing activate exactly-once | **no_surface** in extracted set | — | (activation.py office lives on parked 1b branch) |

#### 3a.5 Compaction/settlement jobs

| Job | Preserves | Drops | Tombstone |
|-----|-------------------|-----------------|--------------------------|
| ContextCompactor.compact() | decisions/anchors/constraints/authority/intent + recent turns | older turns | CompactionReceipt + DroppedItem.content_hash per drop (context_compact.py:231-288) |
| receipt_kernel purge_expired() | blob metadata (sha256, len, created_at) → EXPIRED_HASH_ONLY | blob bytes | BLOB_EXPIRE event per blob (retention.py:128-148); hashes forever if hash_retention=-1 |
| RecoveryStore | content_hash → file mapping | originals after TTL | recovery_store_path in receipt; cleanup by mtime :479 |

## 4. Minimal changes recommended (A8 — assembled 2026-07-02)

Executed during the campaign (each separately committed):
1. ✅ Spine-doc receipt wording + LA-token custody line (A2 findings 1-2).
2. ✅ Handoff note summary-not-record header (A2 findings 3-4).
3. ✅ claim-custody-spine NQ basis-lifecycle section (A4: stale-as-live,
   witness clock, retirement gap — the three named NQ gaps now doc-visible at
   the consuming seam).
4. ✅ ROADMAP.md supersession (A6, program setup).
5. ✅ Memory-index relocation corrections (A5 — closes the PATH corrections
   only; session memory is context, not canon, and no authority question was
   open in this item's scope).

Recommended, NOT executed (each is a named record; build gates apply):
6. **HandoffPacket seal spec** (§1 contradiction 2): promote the seal contract
   from REENTRY prose to a short ratifiable spec — belongs on the CONVEYOR
   branch beside handoff_renderer.py; one page, no behavior change.
7. **F-A3b-1** — session-continuity resume must state (doc-level first) that
   capsule-carried AUTHORITY is context, not admission: re-verification at
   resume is the rule. Named-gap record filed as backlog stub `capsule-authority-reverify` (declared_state, NON-authoritative — a stub is a name, not a work authorization). Per A9: the capsule docs' own use of the word AUTHORITY for carried state is itself the conflation; the stub's acceptance criteria lead with renaming/reframing that vocabulary.
8. **F-A3b-2** — admission-receipt request-side linearity (one wicket pass
   funding N LA capacity requests): cross-repo contract question (LA frozen
   v0); record-first. Named-gap record filed as backlog stub `admission-receipt-linearity` (declared_state, NON-authoritative).
9. **cli.md standing rule** (A2): imperative labels never name authority
   outcomes; apply on next touch of each section, not as a sweep.
10. **loop-protocol.md** self-contradiction ("explanatory…wins") fix-on-touch.

## 5. Do-not-build-yet list (A8)

Seeded from the campaign Forbidden section; grows only by evidence:

- Bounded autopilot (any form).
- Sandbox playbook promotion to operational use.
- NQ retirement-trigger wiring, stale-basis consumption logic, witness-clock
  adapter changes (named in tools/nq.md §4 as FUTURE build slices — not this
  campaign).
- UI pin bumps / shell revivals ahead of the Q-A7 / Q-C2 rulings.
- Any new refusal vocabulary not forced by a named mismatch.

## 6. Consolidation memo (C1 evidence + C2 adjudication)

### C1 evidence (executed 2026-07-02)

**Candidate #2 — wicket-guard → wicket:** wicket-guard: 500 source LOC across
5 files (lib/main/diff/surfaces/cook), **1 commit** (2026-05-13, v0.0.1),
1 test file. Its cook.rs imports wicket's model types directly; wicket already
has its own cook.rs (12KB) + examples/grants/. **Consumers: 13 references,
ALL documentation/citation — ZERO code imports** (no Cargo.toml dep, no `use
wicket_guard` anywhere). Absorption site exists: `wicket/examples/` (e.g.
`cook_from_diff/`), with diff.rs/surfaces.rs as harvestable utilities.

**Candidate #5 — read-plane trio:** spine (DeclarationSource→DeclaredManifest,
YAML manifests, closed status vocab, `refusal.py` FORBIDS legitimacy verbs
{ratified, governed, valid, admitted, authorized, witnessed, certified,
approved, supported, promoted}); governor-atlas (claimdocs case repo: 2 cases,
19 receipts, wired/specified/derived/candidate modes — AG internals only);
state_index_export.v0 (AG prose/declared scanner, "a record is not proof; a
status is not authority"). **Pairwise overlap: NONE found — no artifact type
indexed by more than one system; all three carry explicit anti-laundering
disclaimers.** Ingress points cleanly separated; all three will grow toward
each other (the risk is future, not present).

### C2 adjudication (2026-07-02 — recommendations only; operator rules)

**#2 wicket-guard → RECOMMEND: absorb into wicket** (harvest-then-retire
variant). Criteria check: no distinct authority surface (it cooks INTO
wicket's own types), no distinct implementation surface (same language, same
kernel, one commit of life), no contamination surface (zero independent
consumers). Default-shared applies; operator inclination (2026-07-02) already
pointed here. Execution shape when ruled: move cook/diff/surfaces into
`wicket/examples/` or a wicket module, port the founding regression test,
LINEAGE note in the emptied repo (or graveyard w/ LINEAGE). → DECISIONS
Q-C2-2.

**#5 read-plane trio → RECOMMEND: keep all three separate; write the boundary
note** (R-SPINE-1). Criteria check: three genuinely distinct scopes
(constellation reading / AG-architecture claims / AG-repo state), zero
overlap TODAY, disclaimers enforced as a lexical guard in code (spine's refusal.py blocks
legitimacy VERBS — real enforcement, but lexical: it is not a proof of
semantic authority separation, per A9). The one real risk is convergent growth — the boundary note
names what each may never index and the citation direction between them.
→ DECISIONS Q-C2-5.
