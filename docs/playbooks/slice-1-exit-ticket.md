# Governed Playbooks — Slice 1 exit ticket

**Done 2026-06-24** (gov loop, branch `feat/playbooks-gov-loop`). `certified_kind` as a
**measurement, not authority**. Files: `src/governor/playbooks/certify.py`,
`__init__.py` (exports), `tests/playbooks/test_certify.py` (10 tests; suite 33 green, exit 0).

## What was built

`governor.playbooks.certify`:
- `certify(spec) -> CertifiedKindMeasurement` — the **checker** reads a parsed `PlaybookSpec`,
  runs the kind's structural invariants, and emits `certified_kind` only if they hold. The
  certified kind is *earned from the checker*, never copied off the artifact's `kind:` self-claim.
- `CertifiedKindMeasurement` (frozen): `certified_kind`, `claimed_kind` (distinct, recorded),
  `playbook_spec_digest` (the bound Slice 0 digest), `checker_version`, `parser_version`,
  `canonical_version`, `checks` (the invariant vocabulary confirmed).
- `certified_kind_measurement_digest(m)` — SHA-256 over a version-bound `measurement_basis(m)`
  (exposed for reviewability). This is the digest Slice 3's Wicket consumes as **evidence**.

v0 knows one kind: `procedure`. Its invariant is **unique step ids** (`step_ids_unique`;
shape/non-empty is the parser's job). `_KIND_CHECKERS` is a dispatch table — a second kind
plugs in without touching `certify()`.

## Acceptance (pinned)

- claimed_kind is author assertion only; an unknown claimed_kind (`kind: pipeline`) parses but
  **refuses certification** (`UnsupportedKindError`); a claimed `procedure` with duplicate ids
  refuses (`KindCheckError`) — the self-claim never earns a certified_kind.
- checker emits `certified_kind`; deterministic (same spec → same measurement digest).
- certification binds `playbook_spec_digest` + parser/canonical/checker versions; a semantic
  byte change moves the measurement digest; equivalent formatting does not.
- measurement semantics: the result exposes no `admit/authorize/permit/grant/allow/approve` —
  inert evidence, tested. No receipt emitted, no organ touched.

## Intentionally NOT implemented (deferred, named)

- **Authority of any kind** — no Wicket/Standing/LA, no admission, no runtime permission. This
  is the spine sentence: *certification is admissible evidence for Wicket, not authority.*
- **A second kind with divergent dispatch** — v0 has one kind; the claimed≠certified machinery
  is structural (separate fields, checker-emitted) but not yet exercised across kinds. Adding
  `pipeline`/`reactor` invariants is a later slice (and gated on the ConvergenceFence footing
  for those kinds).
- **No receipt-role wiring** — the measurement is a typed object + digest; emitting it as a
  `receipt_role=measurement` GateReceipt is Slice 3's concern, not here.
- dependency closure (Slice 2), Wicket evidence consumption (Slice 3), field-level diff.

## Next possible slice

**Slice 2 — `dependency_closure_digest`** (local only): root-only + local-import closure;
missing import refuses; canonical order; digest changes with imported content. No network, no
`latest`, no dynamic resolution, no registry.
