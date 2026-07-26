# Campaign card — AG-classic Reference Freeze

> **Supersession note (2026-07-26):** the three-beat sequencing below ("AG-ng
> specified from the stabilized classic") was overtaken by events — AG ng is
> live and is the canonical authority office (it authorized the completed
> four-office pilot). This card's "comparative arm … not as legacy" vocabulary
> was not ratified and is superseded where it conflicts with the recorded
> disposition: agent_gov is the **legacy/historical** authority implementation,
> maintained, with retained live diagnostic helpers (see the README banner).
> The card remains filed as the honest proposal it was; its freeze mechanics,
> if ever ratified, would need re-scoping against that disposition.

> **STATUS: PROPOSED — NOT RATIFIED.** Filed 2026-07-18 from an operator-directed planning
> pass. Planner output — NOT authority. This card is a handle for review, not authorization
> to build. **Nothing below S0 may execute until an explicit operator ratification act**,
> which is also the act that registers the campaign in `.governor/campaigns/` and selects
> the first slice in `.governor/loop.json` (selection = operator act; loop is parked in
> PLAN with `current_slice: null`).
>
> Program position: this is **beat 1** of the three-beat sequence (Lean cooked → bring
> AG-classic up to speed → AG-ng specified from the stabilized classic). The Lean gate
> cleared 2026-07-18 (v14 pushed; DOI audit in progress). Ratifying this campaign does
> NOT ratify the AG-ng program — that remains a separate, explicit operator call.

## Vocabulary this card authors

These names exist in operator memory but nowhere in the repo until this card lands:

- **AG-classic** — this repository's Python system: the reference implementation of the
  governed-admissibility lineage. Stays pure-Python. After the freeze it persists as a
  maintained *comparative arm* (does a pure-Python implementation fail differently than a
  Rust one?), not as legacy.
- **AG-ng** — the planned Rust-first productized successor (own repo, own history, built
  from the earned Admissibility Calculus). Not this campaign. Not this repo.
- **Beat 1 — "bring classic up to speed"** — this campaign: make AG-classic a clean,
  truthful, executable reference so AG-ng and the public Calculus can be specified
  against it without archaeology.

## Question

> Can AG-classic be made a clean, truthful, executable reference — every public behavior
> either contract-frozen, roster-pinned, or explicitly disclaimed — such that AG-ng and
> the public Admissibility Calculus can be specified against it without archaeology?

## Boundary law

**Freeze locks the reference surface; it does not retire classic.** The transition-kernel
stop-lines (`docs/campaigns/transition-kernel-pickup/CAMPAIGN.md` §stop-lines) remain
binding: Python remains reference / explicit observable fallback; no silent Rust→Python
fallback; Rust is not the truth mint. Classic remains runnable and maintained as the
deliberate comparative arm.

**Non-claims:** not a modernization campaign; not a retrofit of successor semantics into
classic; not a production-readiness push; not a deprecation apocalypse; not an attempt to
erase intentional classic asymmetries.

## Invariants (hard boundaries)

1. Preserve current behavior unless a mismatch is demonstrably a **bug**, an **incomplete
   contract**, or a **documentation overclaim**.
2. Correspondence questions are classification, never implementation requirements.
3. Completeness debt is finished only where the frozen reference would otherwise be
   **false or ambiguous** — never because a surface exists.
4. Historical receipt and API identity is preserved. No schema rewrites, no re-hashing of
   stored artifacts.
5. Every slice exits by receipt; greens by observed exit code (`governor verify-run`,
   loop-protocol §3).

## Forbidden (smuggling = stop and re-scope)

- No Rust implementation. No Lean changes. No AG-ng work. No transition-kernel code
  changes (a cross-repo *doc-sync handoff note* is permitted; the edit is that repo's act).
- No backporting successor architecture into classic.
- No broad standing→MC code/API/schema rename (see §4 — three documented verbatim
  constraints forbid it).
- No new authority semantics, providers, systemd, mandate, federation, LA, Constellation,
  or UI work opened under "completeness" cover.

---

## §1 Behavioral freeze — the frozen executable contract

The authoritative surface, organized into four tiers. The tier map becomes a new
declaration doc, **`docs/REFERENCE_CONTRACT.md`** (S1 deliverable — the falsifiable shape
the rest of the campaign is judged against).

**Tier 1 — byte-frozen executable contract** (exists; freeze confirms + repairs prose):
- Golden decision corpus `golden/corpus/` — 13 specimens (`agent_governor.corpus.v1`),
  `MANIFEST.json` (per-case sha256, all `custody_class: contract`), pinning the 7 verdict
  fields + Wall-1 fence (`operational=false` corpus-wide) + closed-world scenario
  coverage. Tests: `tests/test_corpus_contract.py`, `tests/test_corpus_custody.py`.
- Closed vocabularies: 12 `refusal_kind` (`linear_accountant_client.CLOSED_REFUSAL_KINDS`),
  5 `refusing_seam`, 3 `outcome`.
- Cross-repo differential: transition-kernel `vectors/legacy/` byte-identity mirror,
  `scripts/differential.py` (Rust ≡ frozen contract ≡ live Python), `scripts/verify_mirror.py`.
- Demo acts incl. hero specimen: `demo/refused-spend.sh` / `interrogate.sh` /
  `opa-contrast.sh` + `tests/test_demo_*.py` (two-clock temporal-lapse refusal).

**Tier 2 — schema/version-guarded contract** (executable; freeze pins versions as
final-for-classic):
- Gate receipt schema v4 (`gate_receipt.py:RECEIPT_SCHEMA_VERSION`) + golden traces
  (`tests/fixtures/golden_traces/`).
- Standing validator v0.4.0 + envelope corpus (`tests/fixtures/standing_envelopes/`,
  3 good / 14 bad named-`ViolationCode` fixtures) + the v0.1.0→v0.4.0 supersession
  ceremony (`docs/doctrine/decisions/validator-v0_*.md`).
- Signal envelope 0.4.0 (`signals/envelope.py`) + fixture corpus; canonical-JSON rules;
  receipt_kernel contract (`docs/RECEIPT_KERNEL_CONTRACT.md`); `work_container.v1`;
  `schemas/*.v1.json`.

**Tier 3 — roster-pinned public surface** (new work — pin the roster, not golden-freeze
the behavior):
- CLI surface (~125 commands) and daemon JSON-RPC (99 methods, `PROTOCOL_VERSION = "1.0"`).
  Behavior-tested today but no frozen roster manifest. S3 adds one manifest + pinning test
  each: a removed/renamed command or method fails a test; *additions* are refused by the
  maintenance-only rule, not by the test.

**Tier 4 — explicitly outside the frozen contract** (historical/disclaimed):
- `current research` + `candidate substrate` bins of `feature-history.md`; experimental
  CLI groups (`evasion`, `temporal`, `stability`); playbooks conveyor (unarmed by design,
  safe ≠ live); GAP-3 frontier vectors. Hard disclaimer in `REFERENCE_CONTRACT.md`, no tests.

**Known drift already qualifying for repair under the preservation rule:**

| Drift | Truth | Repair |
|---|---|---|
| `golden/README.md` says 9 corpus cases | 13 since 2026-07-03 | fix prose (S2) |
| transition-kernel `README.md`/`CONTRACT.md` say 9 | 13 mirrored | cross-repo doc-sync **handoff note** only (S2) |
| `docs/VERSIONING.md` lists Receipt schema 2 | code is v4 | fix table (S2) |
| `proof_seam.py` header cites retired Lean tiers (ANNEX/[1.0] pre-v13) | v13 retired those lanes; v14 ratified `Admissibility.Calculus` | reconcile header vocabulary (S4, ledger-first) |

## §2 Calculus correspondence — the ledger

Deliverable: **`docs/reference/calculus-correspondence.md`** — the first AG-side
correspondence ledger (crosswalks currently live only in `~/git/lean/docs/`; the nearest
AG-side artifact is the `PROOF_SEAM` dict in `src/governor/proof_seam.py`).

- **Pin:** authored against Lean **v14-pushed**, marked *candidate-pinned*; gate G4
  requires re-pin against **Lean-at-DOI**. The ledger records the pin (version + commit +
  claim-register hash) explicitly.
- **Row classification (closed vocabulary):** `exact` · `narrow-adapter` ·
  `intentional non-correspondence` · `superseded` · `illegal-lift (must never be inferred)`.
  Every Tier-1/Tier-2 behavior gets a row; zero unclassified rows at gate time.
- **Seed rows:** the 3 live `PROOF_SEAM` cites (+ aliases); the 2 `NO_KERNEL_THEOREM`
  honest gaps (`already_consumed`, `origin_not_operational`) carried as explicit
  no-theorem rows, never given borrowed citations; Wall-1 origin fence; two-clock
  standing-spendability ↔ `Freshness.expired_not_fresh`; standing validator chain rules;
  recomposition/laundering refusal.
- **Fences:** a `narrow-adapter` or `non-correspondence` row does not open a build slice.
  No Lean edits. The `proof_seam.py` reconciliation (S4) updates *tier vocabulary only*;
  changing *which* theorems are cited requires a ledger row first. (Backlog
  `proof-seam-citation-reconciliation` is marked done — S4 verifies its coverage before
  touching anything.)

## §3 Completeness debt — triage

Principle: finish only where the frozen reference would otherwise be false or ambiguous.

**Finish:**
- Stale contract prose (drift table, §1).
- **GAP-M — Gemini adapter fail-open** (`runtime/adapters/gemini_cli.py`, fail-opens on
  socket error): *recommended* finish — fail-closed pre-tool gating is a guarantee-typed
  claim of the reference; one fail-open adapter falsifies the conjunctive guarantee.
  Fallback if operator declines: demote the adapter to Tier 4 with a hard disclaimer.
  → DECISIONS.md D1.

**Refuse / deprecate (terminal disposition forbids the work):**
- GS-2b remainder (`admissibility_question` source + HELD-launch state) — already
  re-tiered as authority-semantics; permanently parked with disclaimer.
- P4 workflow-kernel promotion/expiry — successor-era work; refused in classic.

**Retain as bounded historical behavior + hard disclaimer:**
- `a1-lane-restriction-4a` (lane observe-only; 4a deliberately unbuilt — intentional asymmetry).
- `capsule-authority-reverify` (doc fence F-A3b-1 exists; code fence was forcing-case-gated).
- Wall 2 / `candidate-la-unit-class-fence` (cross-repo LA contract change; named, not built).
- H2/C11 seccomp + live sandbox dispatch (playbooks; unarmed by construction).
- Deferred v3 gap specs; GAP-3 frontier vectors; workflow-kernel bootstrap limits.

**Not this campaign's to close silently:** the **R1–R4 inexpressibility rulings**
(custody-affecting, unruled, the program's top unruled item). → DECISIONS.md D2.

## §4 Vocabulary — standing → MC

**No code/API/schema rename.** Three documented constraints independently forbid it: the
lexicon's "never rename native homes" discipline (`docs/reference/constellation-lexicon.md`),
the external `~/git/standing` repo owning the term, and the LA roadmap's "standing
prohibitions, **verbatim** — no field renames." Nothing found suggests the old vocabulary
prevents truthful reference use.

Deliverable instead (S6): **`docs/reference/mc-crosswalk.md`** (+ one lexicon pointer
line): *MC (Mandate Custody) is the successor name for the standing/mandate concept; in
AG-classic and its receipts the term is and remains `standing`; historical receipt and API
identity is preserved; AG-ng adopts MC natively.* No compatibility alias in code — an
alias is new API surface, which the terminal disposition forbids.

## §5 Freeze gates (terminal; each exits by receipt via `governor verify-run`)

- **G1 — Corpus & differential:** corpus contract + custody tests green (bare exit codes);
  transition-kernel `differential.py` 3-way green at pinned SHAs both sides;
  `verify_mirror.py` byte-identity green; corpus prose counts match data everywhere.
- **G2 — Public behavior completeness:** CLI + RPC roster manifests exist with pinning
  tests green; every public surface in exactly one tier of `REFERENCE_CONTRACT.md`; zero
  unclassified surfaces.
- **G3 — Documentation truthfulness:** all named drift fixed; a truthfulness sweep over
  `docs/` + `feature-history.md` finds no claim of a capability that is not demonstrably
  true (each finding fixed or moved to a disclaimer); receipts for the sweep.
- **G4 — Correspondence:** ledger complete — every Tier-1/2 behavior classified in the
  closed 5-class vocabulary; illegal-lift rows explicit; **pinned to Lean-at-DOI**
  (candidate pin insufficient to pass).
- **G5 — Custody & release:** full suite green via observed exit code; `git-gov check`
  green; release tagged (name per D5) with receipts; corpus MANIFEST hashes recorded in
  the release note.
- **G6 — Maintenance-only declaration:** terminal-disposition text landed in
  `README`/`docs`, `PROGRAM_LEDGER.md`, `feature-history.md`, and agent guidance
  (`CLAUDE.md`/`AGENTS.md`) — classic intake restricted to contract-preserving bug fixes;
  AG-ng named as successor; comparative-arm purpose stated (frozen ≠ dead).

## Definition of "reference-ready"

> AG-classic is **reference-ready** when every public behavior is exactly one of:
> (a) part of the frozen executable contract (golden/pinned/version-guarded, Tiers 1–2),
> (b) roster-pinned and behavior-tested (Tier 3), or (c) explicitly disclaimed as bounded
> historical behavior (Tier 4); all six gates G1–G6 hold with receipts; the correspondence
> ledger classifies every frozen behavior against the Calculus at the Lean DOI pin with no
> unclassified rows; and a tagged release exists whose documentation contains no known
> overclaim. Truthful, not modernized.

## §6 Terminal disposition

After G6: **no new authority semantics; no new provider, systemd, mandate, federation,
LA, Constellation, or UI work in classic; bug fixes only where needed to preserve the
frozen contract; AG-ng is the successor.** Classic persists as the pure-Python comparative
arm. Operationalized: the maintenance-only declaration is consulted by loop AUDIT —
future backlog intake for classic refuses new-surface slices by rule, not by memory.

## Provenance

Operator brief 2026-07-18 (this pass). Grounding: `direction_ag_ng_rust_split` memory
(three-beat sequence, Lean gate cleared 2026-07-18);
`docs/campaigns/transition-kernel-pickup/CAMPAIGN.md` stop-lines;
`docs/constellation-wire-plan.md` ("the golden corpus is the frozen contract");
repo census 2026-07-18 (corpus/differential inventory, drift list, debt inventory,
vocabulary constraints). Plan file: `~/.claude/plans/stand-up-a-bounded-refactored-balloon.md`.
