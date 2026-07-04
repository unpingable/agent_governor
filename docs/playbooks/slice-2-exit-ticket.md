# Governed Playbooks — Slice 2 exit ticket

**Done 2026-06-24** (gov loop, branch `feat/playbooks-gov-loop`). Local dependency closure +
`dependency_closure_digest`. Files: `closure.py` (new), `spec.py` + `canonical.py` (minimal
edits for the optional `imports` field), `__init__.py` (exports), `tests/playbooks/test_closure.py`
(20 tests). Playbooks suite **50 passed, exit 0**.

## What was built

- **`imports:`** — an optional top-level field of **opaque local refs** (strings; NOT
  filesystem paths — the playbook layer never interprets a ref). Absent/empty → `()` and
  **omitted from the canonical form**. Duplicate refs and non-string refs refuse at parse
  (`PlaybookSchemaError`).
- **`resolve_closure(root, resolver)`** — an **injected** resolver `ref -> source | None`
  (no filesystem walk, no network, no registry, no `latest`, no globbing, no dynamic
  discovery). Builds the transitive set of resolved specs. Missing ref → `ImportNotFoundError`;
  cycle (a spec reaches itself) → `ImportCycleError`; diamond (shared dep) → **deduped**, not
  refused. Membership is keyed by resolved `playbook_spec_digest`.
- **`dependency_closure_digest(closure)`** — SHA-256 over a version-bound basis of
  `root_digest` + the **canonically-sorted** member digests. Stable under import order;
  changes when any resolved member's content changes.

## The pinned invariant (regression, not "probably")

> Adding the optional `imports` field must not change the digest of import-less playbooks.

`test_import_less_digest_is_byte_unchanged_from_slice0` asserts the **golden** canonical bytes,
`playbook_spec_digest`, and `certified_kind_measurement_digest` captured *before* Slice 2:

```
spec digest : 4444d9d06ca40e1b06e6274b907a6ec65e78f5621052508b561eca1a0027a234
cert digest : 7de8cb8badb447761173b8562da6a30e05d270a5a73f0f96e34fc107c8ac11fd
```

Per the operator's "option 1": **no canonical/digest-basis version bump** — semantics for
import-less playbooks are unchanged, so `imports` is omitted-when-empty and the versions stay
`v0`. The byte-identity holds by construction and is pinned.

## The boundary (no free smoothie)

Two facts kept separate, each pinned by a test:

- `playbook_spec_digest` = the **authored** spec, including its import **refs** ("I reference
  X"). Changing which refs → root digest changes (`test_root_spec_digest_changes_when_import_ref_text_changes`).
- `dependency_closure_digest` = root + the **resolved** dependency set ("X resolved to these
  bytes"). Changing X's **content** moves the closure digest but **leaves the root spec digest
  unchanged** (`test_imported_content_change_moves_closure_not_root_spec_digest`). The closure
  digest is never the root spec digest (`test_closure_digest_is_not_the_root_spec_digest`).

Design note: import **declaration order is not semantic** (imports are a set — sorted in the
canonical form), so reorder leaves both root and closure digests unchanged
(`test_import_declaration_order_is_not_semantic`). Steps remain ordered (a sequence).

## Acceptance (all pinned)

import-less golden unchanged · `imports: []` normalized to absent · one local import resolves ·
transitive resolves · diamond dedups · missing refuses · duplicate refuses · cycle (direct +
indirect) refuses · closure digest order-stable · closure digest content-sensitive · root spec
digest changes on ref-text change · imported-content change moves closure not root.

## Intentionally NOT implemented (deferred, named)

- **Wicket / Standing / LA / runtime authority** — STOP LINE before Slice 3. The three digests
  (`playbook_spec_digest`, `certified_kind_measurement_digest`, `dependency_closure_digest`)
  now all exist as **measurements**; Slice 3 is where Wicket consumes them as *evidence* — the
  first runtime-adjacent seam, reserved for fresh eyes.
- No registry / remote fetch / scheduling / `latest` / dynamic resolution / globbing — refs are
  opaque and resolution is entirely the injected resolver's job.
- A concrete production resolver (filesystem-backed, content-addressed store, etc.) — out of
  scope; tests use an in-memory dict resolver.

## Next possible slice

**Slice 3 — Wicket consumes the three measurements as evidence** (do NOT start without fresh
eyes): Wicket subject/evidence carries the digests; absent/mismatched measurement refuses
admission; the frontend measurement does **not** become authority; Wicket stays procedural.
