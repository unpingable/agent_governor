# Next — reconciliation slices (A-series + C-series)

Order: A1 → A2; A3a → A3b; A4–A7 and C1 independent; everything → C2 → A8 → A9.
Every slice follows the six-field shape (`docs/roadmaps/ROUTING.md` §2).

### A1 — surface-inventory verification
tier: mechanical · executor: codex · prereq: []
- purpose: every claimed handoff surface exists on disk (or its absence is recorded), so the report cross-examines reality, not memory.
- files: read-only sweep of docs/REENTRY.md, working/linear-accountant-handoff.md, docs/architecture/claim-custody-spine.md, specs/gaps/GOV_GAP_STATE_REENTRY_PROTOCOL_001.md, docs/playbooks/live-adapter-allowlist-review.md, docs/playbooks/handoff-renderer surfaces, MEMORY.md-referenced paths; output table → INVENTORY.md §1.
- tests: `test -f <path>` per surface + `sha256sum` recorded; branch check `git show main:docs/REENTRY.md >/dev/null; echo $?` expected 0 (verified present on main 2026-07-02 — the earlier "phantom" was branch visibility).
- refusal mode: n/a (testimony only); missing surface recorded as `absent`, never silently skipped.
- receipt shape: INVENTORY.md §1 table (path · exists · sha256 · last-commit) in one commit.
- stop condition: any surface whose content contradicts its index description — STOP, record verbatim, do not reinterpret.

### A2 — distinguish-pairs language sweep
tier: review · executor: codex-exec · prereq: [A1]
- purpose: find every place handoff language blurs one of the six pairs (proposal/authorization, receipt/authority, generated-text/operator-decision, sandbox/live-actor, grant/spent-capability, memory/canon).
- files: the A1 surface set + docs/playbooks/*.md handoff sections; output findings table → INVENTORY.md §2.
- tests: rubric-driven; acceptance = every finding carries file:line + pair-ID + quoted text; zero findings without quotes.
- refusal mode: n/a (report-only; may not fix).
- receipt shape: findings table, one commit; each finding cites the pair it blurs.
- stop condition: rubric ambiguity (a finding fits no pair) — file it under `unclassified` with quote; do not invent a seventh pair.

### A3a — schema extraction for the Lean checklist
tier: mechanical · executor: codex · prereq: []
- purpose: mechanical tables the 8 AG-AUDIT-CHECKLIST items need, extracted without judgment.
- files: read src/governor/{gate_receipt,receipt_v1_bridge,evidence_gate,wicket_client,linear_accountant_client,standing_client,context_compact}.py + libs/receipt_kernel; output: receipt-kind×gate matrix, hop-chain midpoint fields, evidence-chain roots, single-use consumption points, compaction/settlement jobs → INVENTORY.md §3 appendix.
- tests: each table row cites file:line; `python3 -c` import checks for named symbols exit 0.
- refusal mode: n/a.
- receipt shape: appendix tables, one commit.
- stop condition: a checklist item's subject has no corresponding AG schema element — record `no_surface`, do not stretch an analogy.

### A3b — Lean checklist adjudication
tier: conceptual · executor: fable · prereq: [A3a]
- purpose: apply `~/git/lean/docs/AG-AUDIT-CHECKLIST.md` items 1–8 over A3a's tables; per finding name the theorem, and grade screen (detects) vs wall (prevents).
- files: INVENTORY.md §3.
- tests: every finding cites Lean module + theorem + tier marker ([1.0]/ANNEX/SCRATCH); SCRATCH citations marked pilot-only.
- refusal mode: findings may NAME missing refusals; may not add them (that would be machinery — file a gap instead).
- receipt shape: §3 adjudication, one commit citing lean repo HEAD hash.
- stop condition: a checklist item requires new AG vocabulary to even state the finding — file gap-name only, mark for operator.

### A4 — NQ drift gap-naming
tier: conceptual · executor: fable · prereq: []
- purpose: name the three BASIS_STALE_CONTRACT drifts as gaps and patch the docs that misstate NQ's lifecycle.
- files: docs/architecture/claim-custody-spine.md (NQ leg), docs/roadmaps/tools/nq.md (§3 names: NQ_RETIREMENT_TRIGGER_UNWIRED, NQ_STALE_BASIS_LIVE_CONDITION, NQ_WITNESS_CLOCK_ADMISSIBILITY); promotion to specs/gaps/ only if a build slice later cites one.
- tests: doc patches only; `git diff --stat` confined to named files.
- refusal mode: names refusal-relevant conditions (stale-basis consumption) without wiring them.
- receipt shape: one commit citing NQ BASIS_STALE_CONTRACT.md + commits 3249fe1/22cbd3f/c1dd7d3.
- stop condition: any patch that would change adapter *behavior* — that's the nq.md roadmap's build slices, not this campaign.

### A5 — memory-index correction
tier: mechanical · executor: local-qwen · prereq: []
- purpose: correct the custody/cadence/dossier/clerk repo references — they are PARKED in ~/git/backburner (relocation), not standalone live repos.
- files: ~/.claude/projects/-home-jbeck-git-agent-gov/memory/{MEMORY.md,custody_repo.md,cadence_repo.md,dossier_repo.md,admissibility_family.md} + any AG doc referencing them as live paths (grep `~/git/custody|~/git/cadence|~/git/dossier` in docs/).
- tests: `grep -rn 'git/custody\|git/cadence\|git/dossier' docs/ | wc -l` → 0 uncorrected; memory files point at backburner + PARKED.md.
- refusal mode: n/a.
- receipt shape: one commit (AG side) + memory file edits noted in STATUS.
- stop condition: a reference that appears LOAD-BEARING (code import, adapter path) rather than prose — STOP, obstruction note; none expected.

### A6 — ROADMAP.md supersession rewrite
tier: mechanical · executor: local-qwen · prereq: []
- purpose: root ROADMAP.md stops testifying stale plans; points at docs/roadmaps/README.md.
- files: ROADMAP.md (rewrite to ~15-line supersession pointer; fossil stays in git history).
- tests: `wc -l ROADMAP.md` ≤ 25; contains `docs/roadmaps/README.md`; `git log --follow ROADMAP.md` intact.
- refusal mode: n/a.
- receipt shape: separate commit, cited by A8.
- stop condition: none (fully specified). [EXECUTED with program setup 2026-07-02 — see STATUS.]

### A7 — UI-pin drift record
tier: mechanical · executor: codex · prereq: []
- purpose: record (not fix) the UI version-pin breakage so the disposition question is decided on evidence.
- files: INVENTORY.md §2 rows + DECISIONS.md Q-A7 (guvnah `>=2.3.2 <2.4.0` vs AG 2.8.1 = breaking; phosphor `>=2.3.0`, 5/88 RPC + direct-import split-brain).
- tests: quotes from guvnah/COMPAT.md + gov-webui/COMPAT.md + AG pyproject version, each with path.
- refusal mode: n/a.
- receipt shape: one commit citing both COMPAT.md files.
- stop condition: temptation to bump a pin — that is guvnah/phosphor roadmap work gated on the disposition ruling.

### C1 — consolidation evidence assembly
tier: mechanical · executor: codex · prereq: []
- purpose: per CONSOLIDATION.md candidate (9 rows), gather usage/import/staleness evidence — no judgments.
- files: read-only across ~/git; output evidence table per candidate → INVENTORY.md §6 appendix (RPC coverage counts, import graphs, HEAD dates, duplicate-HEAD verification for gov-webui, both wlp READMEs quoted).
- tests: every evidence cell carries a path or command output; `git -C ~/git/backburner/gov-webui rev-parse HEAD` vs `git -C ~/git/gov-webui rev-parse HEAD` recorded.
- refusal mode: n/a.
- receipt shape: appendix, one commit.
- stop condition: evidence requiring a repo not on disk — record `unverifiable`, move on.

### C2 — consolidation adjudication memo
tier: conceptual · executor: fable · prereq: [C1, A7]
- purpose: apply the CONSOLIDATION.md criteria to C1 evidence; produce per-candidate recommendations (keep-separate / absorb-into-X / harvest-then-retire / rename) with the criterion cited.
- files: INVENTORY.md §6 + DECISIONS.md (one question per candidate for operator ruling).
- tests: every recommendation cites a criterion (1/2/3) or names why default-shared applies; NO merge is executed.
- refusal mode: recommendations only — custody-affecting verdicts are operator-only.
- receipt shape: memo commit; DECISIONS entries created, all status OPEN.
- stop condition: any candidate where evidence is genuinely balanced — recommend "no verdict, revisit at <named trigger>" rather than forcing a call.

### A8 — prosecutor report assembly
tier: conceptual · executor: fable · prereq: [A1,A2,A3b,A4,A5,A6,A7,C2]
- purpose: assemble INVENTORY.md into the packet deliverable: surfaces / stale language / doctrine mismatch / minimal changes / do-not-build / commit citations.
- files: INVENTORY.md (final form), plus ratification flips (`**Status:** RATIFIED`) for docs/roadmaps/tools/{nq,standing,wicket,lean,transition-kernel}.md if their §1–§2 survived audit.
- tests: every claim in the report traces to an A/C-slice commit; do-not-build list explicitly re-states the campaign Forbidden section plus anything discovered.
- refusal mode: report may recommend; may not authorize.
- receipt shape: report commit; per-roadmap ratification flips in the same commit, each citing the audit slice that confirmed it.
- stop condition: a finding that requires new machinery to fix — goes on the do-not-build list with a named gap, not into a build slice.

### A9 — adversarial review of the report
tier: review · executor: codex-exec · prereq: [A8]
- purpose: attack A8 for over-claiming, missed pair-conflations, and machinery smuggled past "doc patches + named gaps".
- files: INVENTORY.md (read); findings → STATUS.md review block.
- tests: refute-first rubric; file:line; <400 words; explicit verdict per report section.
- refusal mode: n/a (report-only).
- receipt shape: review block appended, one commit.
- stop condition: n/a — review completes or reports inability.
