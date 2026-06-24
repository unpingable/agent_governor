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

- **Slice 0 — DONE** (`e3a1490`): parse → canonical → digest. `docs/playbooks/slice-0-exit-ticket.md`.
- **Slice 1 — certified_kind measurement** (`governor.playbooks.certify`): the checker emits
  `certified_kind` from a parsed spec; binds `playbook_spec_digest` + parser/canonical/checker
  versions; measurement semantics, **not authority**. Unsupported/malformed kind refuses typed.
- **Slice 2 — dependency_closure_digest** (local only): root-only + local-import closure;
  missing import refuses; canonical order; digest changes with imported content. No network,
  no `latest`, no dynamic resolution.
- **Slice 3 — Wicket consumes measurements as evidence** (runtime-adjacent; do only after 1+2
  are boring): Wicket subject/evidence carries the three digests; absent/mismatched measurement
  refuses admission; **measurement does not become authority**; Wicket stays procedural. Fresh
  eyes — first seam where "measurement" can find an authority hat in a drawer.

## Exit

The loop ends when Track B's measurement surface is complete through Slice 2 (and Slice 3 is
handed to a fresh review), or when a slice surfaces a forcing question that needs operator fiat.
