# Campaign — governed-playbooks Track B (gov loop)

Status: **active gov loop** (2026-06-24). A governed AG development campaign over the
`governor.playbooks` measurement layer. Integration branch: `feat/playbooks-gov-loop`
(merges `docs/governed-playbooks-capture` + `feat/playbooks-slice-0`).

## The one distinction (load-bearing)

> **Use AG to govern *building* the playbook machinery. Do NOT use governed playbooks as
> authority yet.** No Ouroboros. The playbook layer mints measurements; nothing relies on
> them for permission until Slice 3 wires Wicket — and even then as *evidence*, not authority.

## Loop invariant

Each iteration: **proposal → bounded patch → focused tests → exit ticket → stop or next
bounded proposal.** Every slice must produce:

1. a narrow proposal (one slice, named files)
2. a changed-file set confined to that slice
3. focused tests (green, real exit code)
4. an exit ticket (`docs/playbooks/slice-N-exit-ticket.md`: what was built, non-goals, next)
5. **no widening beyond the slice** — the loop must be too boring to discover ambition

## Allowed

The inert measurement/authoring surface only: parser, canonical form, digests,
certified-kind *measurement*, local dependency closure. Each behind its own slice.

## Forbidden (until explicitly admitted by a later slice's scope)

No Wicket/Standing/LA/executor wiring (Slice 3 is the *first* Wicket-adjacent step, and
evidence-only); no runtime authority; no playbook execution; no registry / remote fetch /
scheduling; no `latest` / dynamic resolution; no ConvergenceFence; no field-level receipt
diff; no reactors/pipelines/imports leaking into v0.

## Slice queue

- **Slice 0 — DONE** (`e3a1490`): parse → canonical → digest. `slice-0-exit-ticket.md`.
- **Slice 1 — DONE** (`c582a7e`): `certified_kind` as a measurement (checker-emitted, binds
  the spec digest + versions, not authority). `slice-1-exit-ticket.md`.
- **Slice 2 — DONE** (`60aadd9`): local dependency closure + `dependency_closure_digest`
  (injected resolver; missing/cycle/duplicate refuse; order-stable, content-sensitive; the
  import-less golden digest is byte-pinned). `slice-2-exit-ticket.md`.
- **Slice 3 — DONE** (2026-06-25, operator go given): Wicket consumes the three measurements as
  *evidence*. `admission_evidence.py` (pure binding verifier, re-derives digests, closed reason
  vocab) + `WicketClient.check_playbook_admission` (two conjunctive gates: evidence coherence →
  authority/Standing, in that order). Authority gets `verdict="pass"` (`wicket_seam`); evidence gets
  `verdict="observe"` (`wicket_playbook_evidence`) — no path promotes observe→pass. Generic `check()`
  byte-untouched. Laundering wall pinned: coherent evidence + absent Standing → refusal. The Standing
  semantics, supervisor, activation, and executor are all untouched (stop line held). `slice-3-exit-ticket.md`.

- **Slice 4 — DONE** (2026-06-25, operator go given): playbook-governed *spend*. The orchestrator
  (`cooked_context_orchestrator.run(playbook_evidence=...)`) routes evidence → authority → LA consume.
  The Slice 4 laundering wall: the LA spend basis is the wicket-seam **pass** admission, never the
  observe evidence record (`build_authority_admission_verifier` + `is_authority_admission_receipt`).
  Failure taxonomy pinned by owner (evidence/authority/effect). Supervisor, activation, executor,
  Standing semantics untouched. `slice-4-exit-ticket.md`.
- **Slice 5 — DONE** (2026-06-25, operator go given): *durable, exactly-once spend* — the first Track A
  pickup and the **runtime-law** line. `playbooks/durable_spend.py` (`DurableSpendLedger`, write-ahead
  exactly-once, ported from activation.py's ratified Office-3 pattern) + an optional
  `DurablePlaybookSpendGate` composed post-admission/pre-LA. Boss fight pinned: same spend retried
  (new process, same ledger) refuses at `SEAM_DURABLE_SPEND` (`playbook_spend_replayed`) — **exactly
  one LA consume across both runs, no double-spend.** Spend is authority-bound (admission receipt +
  step/effect/resource/principal/amount/spec-digest); unbound spend rejected. The four non-collapses
  hold: observe≠pass, pass≠spend, spend≠execution, durability≠permission. **Deliberately did NOT touch
  `supervisor.py` or `activate()`** (fenced activate; divergent supervisor) — durability crossed via a
  new gate; supervisor-dispatch is the named obstruction → Slice 6. `slice-5-exit-ticket.md`.
- **Slice 6 — DONE** (2026-06-25, operator go given): first self-hosted governed-playbook chore —
  *dogfood execution, NOT autopilot*. `playbooks/chore.py`: `run_governed_chore` runs ONE boring
  read-only audit (`read_only_receipt_audit`) through the S3–S5 chain, dispatching the chore IFF the
  chain spent, then emitting a **non-authoritative report receipt** (`verdict=observe`, gate
  `governed_chore_report`, `non_authoritative=True`) that fails `is_authority_admission_receipt`.
  Boss fight: AG runs the chore, leaves receipts, future AG can't mistake the report for authority.
  Fifth non-collapse: **report≠authority.** Replay inherits S5 idempotency (no re-execute). Failed
  chore recorded (`ok=False`). **Supervisor watch held a 4th time:** a self-hosted chore is AG's own
  code, NOT an external-agent dispatch — `supervisor.py` is the wrong surface; it earns its forcing
  case at Slice 7 (live external agent). `slice-6-exit-ticket.md`.

## Loop state (2026-06-25)

S0–S2 measurement; S3 Wicket-as-evidence; S4 playbook spend (evidence→authority→LA-consume); **S5
durable exactly-once spend (runtime law).** Roadmap (operator, 2026-06-25): **S5 = runtime law (done);
S6 = first self-hosted chore** (AG runs ONE boring governed-playbook task end-to-end — dogfood
execution, NOT autopilot, and where the supervisor live-dispatch wiring earns its forcing case against
a real task); **S7 = bounded autopilot** (fresh Wicket admission per run, scoped/expiring Standing, LA
spend per effect, failures→receipts). The dogfood line: *"Autopilot begins when the agent can spend a
permission without remembering it."* S5 builds exactly that spend-without-remembering; S6 makes AG
*use* it on a toaster-grade chore; S7 is the ration card.

Track A status: **supervisor watch held a 4th time at S6.** The dispatch axis did NOT force
`supervisor.py` — a self-hosted chore is AG's own code, not an external-agent dispatch, so the
supervisor (which gates external Claude Code / Gemini agent sessions) is the wrong surface. Its
genuine forcing case is **S7 (bounded autopilot)**: a *live external agent* whose tool calls must
route through the governed chain. Held reasons by slice: S3 evidence-upstream · S4 shape-via-LA · S5
durability-via-new-gate · S6 self-hosted≠external-dispatch. Branch-custody: S5/S6 did NOT need
`feat/transition-kernel-slice-1b` (GrantUseResult).

## Exit

The loop ends when AG can run a bounded governed chore self-hosted (durable, replay-safe,
non-authoritative output) (S0–S6), or when a slice surfaces a forcing question that needs operator
fiat. **Reached: Slices 0–6 done 2026-06-25.** Slice 7 (bounded autopilot → a *live external agent*
on a ration card, where `supervisor.py` is finally the right surface) is the next stop line and needs
operator go.
