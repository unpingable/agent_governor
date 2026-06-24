# Governed Playbooks — design capture

> **Canonical home: `agent_gov` (this repo), as of 2026-06-24.** Originated in a separate
> `ag-frontend` incubator (now archived → tombstone). The move is the design's own
> conclusion: the jurisdiction map proved the "frontend" is an **inert measurement/authoring
> layer with zero authority surface**, so a separate repo only manufactured pressure to
> grow a shadow constitution. The future code home will be **`governor.playbooks`** (a
> *measurement/authoring* package — deliberately not `governor.frontend`, which would collide
> with Maude/UI). No code exists yet, by design (see `build-phases.md`: inert-first is a trap).

This directory is a **design / spec capture**, not an implementation claim. It was
written 2026-06-23 from a multi-model design conversation, to preserve the architecture
while the idea is fresh and to keep later sessions from sprinting toward "YAML parser
dopamine" over the unpoured footing.

**Nothing here is certified, ratified, implemented, or globally complete.** The whole
construction is gated on the ConvergenceFence hostile-contract proof (Phase 1). Read
these as a record for review.

## The one-sentence object

> A playbook is a reusable action claim whose steps declare what authority they need,
> what evidence they must collect, what state they may change, what refusal means, and
> what receipt proves the run. A stored playbook is **inert**; the executable unit is
> *certified spec + live standing + run plan + fresh witnesses + spend authority*.

Not Ansible. The Ansible resemblance is UX bait; the object is **governed procedure
admission**.

## Docs

- [receipt-jurisdiction-map.md](./receipt-jurisdiction-map.md) — **read this first.** The
  claim-by-claim map of each proposed seam against AG's shipped receipts, with runtime
  evidence (`git grep` + a live `governor why` walk). Proves the layer is inert
  measurement/authoring; everything RunRequest-onward cites AG. The authority for the move
  in-tree and the SL-001 decomposition / certification-is-measurement findings.
- [invariant-ledger.md](./invariant-ledger.md) — the seams in **reference-form**: each tagged
  cite / extend / reuse / decompose, plus the three frontend-native digests. The Phase-0
  oracle, rewritten from the map.
- [playbooks-build-gap.md](./playbooks-build-gap.md) — gap spec: what AG already ships vs what
  the `governor.playbooks` layer must build, acceptance criteria, cold-start slices 0–3.
- [governed-playbooks.md](./governed-playbooks.md) — the original design: four-layer object
  model, authorship≠standing matrix, claimed vs certified kind, organ chain (post-decomposition:
  Standing resolves a reference, Wicket admits, permission is conjunctive), reactor vs pipeline.
- [convergence-fence.md](./convergence-fence.md) — the load-bearing, **unproven** bridge
  (now split into L1 acyclicity + L2 confluence; see the map/ledger).
- [build-phases.md](./build-phases.md) — phasing by dangerous seam, not by object.
- [glossary.md](./glossary.md) — terms.

## Tomorrow's smell test (2026-06-24)

Let it cool first — everything is still radiating shower-neutron energy. Then ask only
three things:

1. **Does Wicket belong in the RunRequest path, or is that inventing ceremony?**
2. **Does `ConvergenceFence` close the hostile reactor cases without leaking loops into
   the pipeline?**
3. **Do the Phase-0 invariants map to existing receipt machinery, or are we quietly
   inventing a parallel constitution?**

If those pass, the thing is real enough to capture. If one fails, it fails in the right
place — early, before YAML goblin mode begins.

## Unresolved questions (carried forward)

1. Does `BoundaryContract` close the three ConvergenceFence hostile cases? (the footing)
2. Is Wicket the right repo/module home for RunRequest intake, or ceremony?
3. Which Lean owner/file should receive the bridge theorem later?
4. Which existing AG / Standing / LA / NQ receipt types can be reused vs need new ones?
   (smell-test #3 — avoid inventing a parallel constitution)
5. Where should the parser / canonical IR live later, after Phase 0/1?
6. Is the playbook "registry" a Spine edition/index, and is derived-boundary adjudication
   a Maude concern? (check before building either)
7. ~~Home of this capture?~~ **RESOLVED 2026-06-24:** lives in `agent_gov/docs/playbooks/`
   (canonical); future code under `governor.playbooks`. Authority always lived in the
   AG-organ receipts — so the spec lives with them. `ag-frontend` archived as tombstone.

## Provenance

Captured from a shower-slip insight + multi-model stress-testing (Claude / Chatty / a
stress-tester pass), 2026-06-23. The sharp distinctions are the point — do not smooth
them into generic "workflow automation."
