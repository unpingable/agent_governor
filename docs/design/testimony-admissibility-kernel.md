# Testimony-Admissibility Court — integration note

> Promoted 2026-07-13 into `src/governor/testimony_admissibility.py` from a
> frozen wind-tunnel kernel (`~/git/5060/windtunnel/kernel.py`). AG now owns a
> pure, deterministic testimony-admissibility court. This note records what was
> promoted, the boundaries that were preserved, and the future adapter seams —
> so the runtime types are the stable contract the rest of the constellation
> plugs into, not a fascinating local directory that evaporates.

## What AG owns now

A pure judgment core: no model invocation, no prose extractor, no regex
vocabulary, no fixtures, no project (NQ/Maude/lab) configuration. It adjudicates
**structured** assertions and returns **typed** verdicts.

Governing rule: **the prompt cannot mint epistemic authority** — a request may
demand testimony only up to the strength its evidence licenses.

Three independent inputs, never collapsed into one status field:

| input | meaning | who supplies it (adapter, NOT the kernel) |
|-------|---------|-------------------------------------------|
| `required` | obligation from a task contract (the FLOOR) | a planner / **Maude** seam |
| `authorized` | ceiling from an evidence basis (the CEILING) | an evidence-store / **NQ** seam |
| `asserted` | strength extracted from generated testimony | a **model + extractor** adapter |

Two checks:
- **preflight** (before inference): `required <= authorized`. An ill-typed
  contract (`required > authorized`) refuses pre-inference and returns an
  **explicit** `DowngradeOffer` — never a silent lowering of `required`.
- **adjudication** (after): `required <= asserted <= authorized`, returning a
  `TestimonyReviewPacket` whose verdict distinguishes unsatisfiable-contract,
  under-testimony, and the three ceiling-breach (overclaim) cases.

Typed structures: `Relation`, `TestimonyContract`, `AuthorizedTestimony`,
`AssertedTestimony`, `PreflightResult`/`DowngradeOffer`, `TestimonyReviewPacket`.
Strength is a 4-level `IntEnum` (`UNKNOWN < FLOATED_CANDIDATE <
SUPPORTED_CANDIDATE < ESTABLISHED`); `Verdict` is a closed `StrEnum`.

The judgment logic is byte-for-byte the frozen wind-tunnel truth table
(`test_testimony_admissibility.py` ports it verbatim; a full 0..3³ cross-check
against the source kernel showed zero divergence).

## Boundaries preserved (what is deliberately NOT here)

- No prose extractor, regex vocabulary, model invocation, fixtures, or lab
  configuration inside the kernel (proof obligation 1 — imports stdlib only:
  `dataclasses`, `enum`).
- No NQ-specific receipt interpretation; no Maude-specific task compilation.
- `required` is never silently lowered when `required > authorized` — the
  downgrade is an explicit, separately-receipted OFFER.
- No inference is executed.
- AG's existing `ReviewPacket` (playbooks) is **not** reused — it would compress
  the three axes into a `used ≤ granted` status. `TestimonyReviewPacket` keeps
  `required` / `authorized` / `asserted` distinct.

## Future adapter seams (named, not built — this task stops at the kernel)

The kernel is the fixed point; each seam is a downstream project's adapter that
produces one typed input or consumes the packet. Sequence once the runtime types
have survived contact:

1. **NQ-authorized seam** — project specific governed-inquiry receipts into
   `AuthorizedTestimony.authorized_strength` (the ceiling) for a relation. NQ
   owns the receipt→strength projection; the kernel only receives the result.
2. **Maude-required seam** — emit declared `TestimonyContract` (the required
   floor) from a compiled task; when AG `preflight` returns
   `UNSATISFIABLE_TESTIMONY_CONTRACT`, Maude **rejects or offers the explicit
   downgrade** (consuming the `DowngradeOffer`), never auto-lowering the floor.
3. **Model + extractor seam** — turn generated prose into
   `AssertedTestimony.asserted_strength` (owned outside AG; the wind-tunnel
   `analyze.py` extractor is one such adapter, not promoted).
4. **Integration specimen** — one bounded inquiry threaded NQ → Maude →
   model/extractor → AG `TestimonyReviewPacket`. The wind-tunnel four-state
   specimen (`specimen.py`: one relation, evidence states unknown/correlation/
   candidate/established) is the **explanatory evidence** that the gate moves
   with the evidence, not the prompt — kept in the wind-tunnel repo, not
   promoted as production code.
5. **LeanProofs annex** — formalize the walls (`required <= asserted <=
   authorized`; the preflight/adjudication split) **after** the runtime types
   survive integration, not before.

## Provenance

Source: `~/git/5060/windtunnel` (`kernel.py`, `test_verdict.py` truth tables;
`specimen.py`/`analyze.py` explanatory/lab, not promoted). Local commit only.
