# GOV_GAP_ACT_TWO_RECEIPT_INTERROGATION_001

## Title

The launch demo's Act 2 — "just one more thing": interrogate the SAME incident's
receipts and reconstruct the custody chain from evidence, not logs. The missing
runnable beat between Act 1 (the refusal) and Act 3 (the proof seam).

## Status

Gap spec — **proposed, awaiting one-nod ratification.** Output of the
`act-two-receipt-interrogation` spec_slice (loop receipts
`2026-06-11T235706Z.plan` / `.dispatch`). **No build is authorized by this
filing**; the build_slice enters the backlog only after ratified acceptance
criteria + loop AUDIT selection.

## Origin

`working/launch-plan-2026-06-11.md` §Act 2 names the beat ("SQL against the
receipts, custody chain reconstructed from evidence not logs — what happened to
X, why refused, which predicate failed, what the naive gate admitted") but no W1
item claimed it. Surfaced by the loop's cold-start audit
(`2026-06-11T231101Z.audit`): machinery exists, runnable beat unbuilt, admitted
as a tier-1 spec_slice per §8 (doctrine paragraph without acceptance criteria
cannot enter as build work).

Why it matters: without Act 2 the hero specimen reads as *"AG said no because AG
says no."* Act 2 is where it becomes *"AG can show you the exact premise that
failed, from the receipts, with provenance intact."* The difference between a
doctrine artifact and a demo artifact.

## The corpse (fixed, not optional)

Act 2 interrogates the **frozen hero incident** — the receipt set the Act-1 demo
(`demo/refused-spend.sh`) leaves on disk — NOT a fresh scenario. Per run root:

```
<root>/twin/receipts/gate_receipts.jsonl       5 receipts: standing pass → wicket pass
<root>/twin/evidence/<xx>/<sha256>.json          → spendability pass → LA grant → LA consume
<root>/impostor/receipts/gate_receipts.jsonl   3 receipts: standing pass → wicket pass
<root>/impostor/evidence/<xx>/<sha256>.json      → spendability BLOCK
```

(Receipt schema v4: `receipt_id`, `gate`, `verdict`, `evidence_hash`,
`subject_hash`, `policy_hash`, `timestamp`, `receipt_role`, `unsettled`.
Evidence bundles are content-addressed; the refusal's bundle carries the full
murder hallway: `refusal_kind`, `gap_basis{kind,source,epoch,start_ns,end_ns}`,
`gap_ns`, `bound_ns`, `overage_ns`, `lapse_coverage`, `origin_mode`, display-only
`wall`.) Plus, from Act 2.5: the OPA verdict receipt (`opa_rcpt_*`, content-
addressed, `input_provenance: unwitnessed_self_report`) — the naive gate's own
conclusion about the same incident, queryable beside custody's.

## What exists (probed live 2026-06-11, not presumed)

1. **`governor why <receipt_id>`** (`src/governor/why.py`) walks a receipt's
   parent chain and renders: the origin banner (`DRILL  chain origin: 'drill'
   (NQ-side mint provenance — receipt does NOT carry an observed-condition
   witness)`), per-hop verdict/gate/id lines, and an **honest dangling
   terminus** (`MISSING  no receipt found for cited id nq_fnd_…; chain
   terminates at this gap`). Verified four hops deep on the twin:
   consume → grant → wicket → standing → MISSING(NQ finding).
2. **`governor receipts --id <id> --evidence`** dumps the receipt plus its full
   evidence bundle (murder hallway included). Verified against a live demo run.
3. **The provenance cameo already renders**: `origin_mode: drill` is in every
   bundle and `why` banners it — the demo's own evidence is visibly typed.
   The thesis cameos in its own demo; do not hide it.
4. The Act-1 demo leaves all of the above on disk and prints the root path.

## What needs building (all small; this is a beat, not a subsystem)

1. **Un-orphan the refusal.** `StandingSpendabilityGate._emit` hardcodes
   `parent_receipt_ids: []` (standing_spendability.py — "the orchestrator
   threads parents at the chain level", but the orchestrator doesn't for this
   seam). Result: `why <refusal_id>` is single-hop while the twin's consume
   walks four. **Mechanism (pinned):** the gate's `check()` gains an optional
   `parent_receipt_ids: list[str]` parameter threaded into `_emit`; the
   orchestrator passes the wicket receipt id. Post-emission patching of stored
   receipts is FORBIDDEN (receipts are content-addressed and append-only);
   changing the emission is the only admissible mechanism. Target chain:
   refusal → wicket → standing → MISSING(finding terminus).
   Corpus-safe: `test_corpus_entry_receipt_block_matches` subset-matches frozen
   keys; `parent_receipt_ids` is not pinned in `expected_receipt_block`.
   (Verify; if any pin trips, updating the golden is a deliberate reviewed act.)
2. **Make the demo stores CLI-reachable without a shim.** The CLI resolves
   `<root>/.governor/…`; the demo writes `<run>/receipts/…` directly — today
   interrogation requires a symlink shim (probed). Cheapest fix: demo writes
   each run at `<run>/.governor/…`. Also fix the stale hint `refused-spend.sh`
   prints ("point GOVERNOR_DIR at a run subdir" — the CLI reads no such env
   var); replace with exact copy-pasteable commands:
   `governor --root <run> why <refusal_id>`.
3. **Persist the OPA verdict receipt.** `demo_opa_contrast` builds it in memory
   and renders it; nothing lands on disk. **Path (pinned):**
   `<root>/opa_verdict_receipt.json` — stable filename, content-addressed
   `receipt_id` inside the body (stable name so the interrogation finds it
   without globbing; integrity comes from the id, not the filename). NOT into
   `gate_receipts.jsonl` — it is not a gate receipt; jamming it into the store
   would launder kinds. Then Act 2 can query the policy engine's own verdict
   sitting in the evidence plane.
4. **The beat itself: `demo/interrogate.sh`** (+ a thin
   `src/governor/demo_interrogate.py` if needed for assertions).
   **Invocation (pinned):** accepts an optional Act-1 root argument; given one,
   interrogates it; given none, runs the Act-1 entry itself first and prints
   that it did so (the stranger path stays one command). Walks the five
   questions below as *question → command → answer*, asserting expected fields
   (integrity-tripwire style: exit nonzero if any answer is wrong — an
   interrogation that passes for the wrong reason fails loudly).
   **Transcript shape (pinned, minimal):** per question — a `Q<n>:` line, the
   exact `$ governor …` command (copy-pasteable), the relevant output lines,
   and a `✓/✗` assertion line; then a final Integrity block mirroring Act 1's.
   No further format guarantees (byte-determinism explicitly not required).

## Acceptance criteria — the questions ARE the criteria

Each question maps to a runnable query with asserted output. All five run
against the same corpse.

| # | Question | Query | Must show |
|---|----------|-------|-----------|
| 1 | What happened to the spend? | `governor --root <impostor> why <refusal_id>` | `REFUSED standing_before_spendability_not_bounded` at `standing_spendability_seam`; chain walks refusal → wicket(pass) → standing(pass) → honest MISSING terminus |
| 2 | Why was it refused? | `governor --root <impostor> receipts --id <refusal_id> --evidence` | `refusal_kind=standing_before_spendability_not_bounded`, `lapse_coverage=exceeded_horizon` |
| 3 | Which predicate failed? | same evidence bundle | `gap_ns=11000000000 > bound_ns=10000000000`, `overage_ns=1000000000` |
| 4 | Which evidence was stale, under which clock witness? | same evidence bundle | `gap_basis{kind=monotonic, source=process_monotonic, epoch=boot:demo-single-host, start_ns, end_ns}`; `wall.role=display_only` (never the gap basis) |
| 5 | What did the naive gate conclude about the same incident? | read the persisted `opa_rcpt_*` receipt | `decision` (allow when engine ran / null honestly when not), `input_provenance=unwitnessed_self_report`, `policy_hash`, `input_hash` |

Plus three cross-cutting criteria:

- **Provenance visible (the cameo):** the transcript shows `origin_mode: drill`
  and the `why` DRILL banner — the audience sees that even the demo's own
  evidence is typed and fenced (`operational=false`).
- **Negative case (honest absence):** interrogating a nonexistent/dangling
  receipt id renders *not found / MISSING* — never an inferred answer. (The
  twin's NQ-finding terminus and the D3 `dangling_receipt_reference` path are
  the existing behavior to pin, plus one query for a fabricated id.)
- **User-visible transcript:** the beat's output is a readable
  question→command→answer transcript a stranger can replay by pasting the
  printed commands. Byte-determinism is NOT required (receipt timestamps vary);
  the assertions are on fields, not bytes.

Composition: Act 1 → Act 2 run on the SAME root (`refused-spend.sh` prints it;
`interrogate.sh` accepts it); Act 2 question 5 consumes Act 2.5's receipt;
Act 3 (the proof seam) is already rendered from `refusal_kind` — the acts chain
without re-staging the incident.

## The seam, named

- **AG owns the runnable beat**: JSONL receipt store + content-addressed
  evidence + `governor why` / `governor receipts` — sufficient for all five
  questions. The beat ships AG-only.
- **NQ's "SQL against the receipts" party trick is NOT a dependency.** It is
  named here as a *future extraction/fork*: if the launch beat wants literal
  SQL, the path is loading the JSONL into SQLite at demo time or the
  receipt_kernel store (which drills do not currently write) — both are
  post-launch forcing-case territory, neither blocks this beat.

## Non-goals

- No dashboard, no TUI, no query language, no new long-lived CLI surface
  (at most one demo script + assertions module, mirroring `refused-spend`).
- No receipt_kernel migration for drills; no NQ import.
- No fresh scenario; the corpse is the frozen pair.
- Not a product surface — demo-grade, same discipline as Act 1 and Act 2.5.

## Open questions (for the ratifying nod — each carries a default; silence
ratifies the default, an explicit word overrides)

1. Store layout fix — **default: demo writes `<run>/.governor/…`** (zero CLI
   change). Alternative: a `--governor-dir` CLI flag (wider surface; NOT
   preferred).
2. `interrogate.sh` shape — **default: standalone script** (acts stay
   separately runnable). Alternative: a `--interrogate` flag on
   `refused-spend.sh`.
3. OPA receipt path printed by `opa-contrast.sh` like Act 1 prints its root —
   **default: yes** (one echo line).

## Validation provenance

Codex flat-pass (artifact-only, no doctrine preamble) run 2026-06-11,
codex-cli 0.139.0. Its five named ambiguities (store layout, interrogate
invocation, OPA receipt path, transcript format, parent-threading mechanism)
were patched into the pins above; its predicted first-pass mistakes all named
things the spec already forbids (OPA receipt into the gate store; SQL as
dependency; fresh scenario; byte-determinism; hiding origin_mode) — fences
confirmed legible to a cold reader.
