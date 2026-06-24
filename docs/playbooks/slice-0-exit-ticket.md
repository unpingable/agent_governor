# Governed Playbooks — Slice 0 exit ticket

**Done 2026-06-24** (branch `feat/playbooks-slice-0`, off `main`). Track B, the first
code of the `governor.playbooks` measurement layer. Scope held brutally small:
**bytes → canonical spec → digest. Measurement only.** No Wicket / Standing / LA /
certified_kind / dependency closure / ConvergenceFence / receipt-role.

Files: `src/governor/playbooks/{__init__,spec,canonical,digest}.py`,
`tests/playbooks/test_playbook_digest.py` (23 tests, exit 0).

## What the canonical form is

`parse_playbook(source)` → typed `PlaybookSpec` (restricted-YAML loader, pyyaml — an
already-declared dep, `pyyaml>=6.0`; no new dependency). The spec is projected to a
canonical mapping `{schema, kind, name, steps: [{id, action, target}]}` and serialized
with the repo's `gate_receipt.canonical_json` (**sorted keys, recursive; compact
separators; ASCII-safe**). Consequence: source formatting, quoting, comments, and
**mapping key order** are normalized away; **step order is preserved** (it is semantic —
reordering steps is a different procedure, and the tests pin that).

## The digest algorithm

`playbook_spec_digest(spec)` = **SHA-256 hex** (`gate_receipt.content_hash`) over
`canonical_json(digest_basis(spec))`, where the **basis** is:

```
{ "digest_basis":      "playbook-digest.v0",
  "parser_version":    "playbook-parser.v0",
  "canonical_version": "playbook-canonical.v0",
  "spec":              <canonical mapping> }
```

The three version tags are bound **into** the hash, so a change to how bytes are parsed
or canonicalized necessarily changes the digest — the digest never silently means two
things. `digest_basis()` is exported (not just hashed) so the version-binding is testable
and reviewable. This is a measurement: "which authored bytes were certified", nothing more.

## Acceptance (all pinned by tests)

- fixture parses; canonical bytes deterministic; equivalent formatting (incl. flow style)
  → same digest; semantic change (target / name / **step order**) → different digest.
- unsupported constructs **refuse with a typed error**, never coerce:
  `RestrictedYAMLError` for anchors / aliases / merge keys (`<<`) / duplicate keys /
  custom-or-unsafe tags; `PlaybookSchemaError` for unknown/missing keys, wrong types,
  unknown schema, non-list / empty steps, unknown step keys, non-mapping top level.

## Intentionally NOT implemented (deferred, named — not authorization to build)

- **certification / `certified_kind`** — Slice 1 (a `receipt_role=measurement` receipt).
- **dependency closure / `dependency_closure_digest`** — Slice 2.
- **Wicket / Standing / LA wiring** — Slice 3 (Wicket consumes the measurements as
  *evidence*). RunRequest-onward cites AG; this layer mints only the digest.
- **reactors / pipelines / imports / sub-playbooks** — not in the v0 schema; must not leak
  in by accident. Only `governed-playbook.v0` and `{schema, kind, name, steps[{id, action,
  target}]}` are known.
- **Implicit-bool / coercion handling** is enforced at the **typed boundary** (string
  fields refuse coerced non-strings, e.g. `name: true`), *not* by a full
  no-implicit-resolver YAML loader. The fuller restricted-resolver is deferred; the typed
  refusal is sufficient for v0 and is tested.
- ConvergenceFence, field-level receipt diff, docs reconciliation — out of scope.
