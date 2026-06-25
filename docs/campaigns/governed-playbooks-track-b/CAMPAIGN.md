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

## Loop state (2026-06-25)

All three frontend-native measurements exist as digests (S0/S1/S2) and Wicket now consumes them as
**evidence, not authority** (S3). The Track A forcing-case watch (evidence wanting to cross into
activation/supervisor/grant-use) was held: it **did not fire** — evidence coherence is decidable
upstream of the authority gate, as a pure function over the measurement objects. The natural ingress
into Track A is the *spend* slice (Slice 4 candidate: a playbook admission that consumes LA capacity),
not this evidence seam.

## Exit

The loop ends when Track B's measurement surface is complete and Wicket consumes it as evidence (S0–S3),
or when a slice surfaces a forcing question that needs operator fiat. **Reached: Slices 0–3 done
2026-06-25.** Slice 4 (playbook-governed *spend* → Track A ingress) is the next stop line and needs
operator go.
