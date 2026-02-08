# Maude Rename Specification

## Version 0.1 — Find Better Nomenclature for maude_lite.py

```yaml
status: implemented
implemented: true
depends_on:
  - maude_lite.py
  - SLIM_MODE_SPEC.md
blocking: nothing (cosmetic, bundle with 2.0)
estimated_scope: small
```

---

## The Problem

`maude_lite.py` is named after an offhand joke alias that an AI agent took literally and built 101 tests around. The name "Maude" references the Maude formal verification system (Meseguer's rewriting logic), but nobody outside that niche will make the connection. Everyone else hears a person's name.

This is, ironically, a textbook NLAI violation: language was treated as authority. An informal proposal ("let's call it Maude for fun") became a committed module name because the agent didn't distinguish intent from instruction.

### What the module actually does

Evidence-gated coding harness. Kernel-only constraint surface: HARD claims require evidence, contradictions persist, failures are loud. Claim extraction, evidence linking, custody scoring (Ap x Ip x Fp).

### What it should be called

Something that describes the function, not an in-joke. Candidates (non-exhaustive):

| Candidate | Rationale | Risk |
|-----------|-----------|------|
| `evidence_gate.py` | Describes the mechanism directly | Bland but accurate |
| `custody.py` | Describes the scoring model (Ap x Ip x Fp) | Conflicts with legal connotations |
| `kernel_gate.py` | "Kernel constraints" is already the spec name | Aligns with KERNEL_CONSTRAINTS_SPEC |
| `claim_gate.py` | Evidence-gated claim checking | Clear, boring, correct |
| `harness.py` | "Evidence-gated coding harness" is the subtitle | Too generic |

The CLI command `governor lite` should also be renamed to match. With slim mode (SLIM_MODE_SPEC.md), `governor lite check` becomes `governor check --slim` anyway, so this is partly a dead-code cleanup.

---

## Scope

1. Rename `src/governor/maude_lite.py` → TBD
2. Rename `tests/test_maude_lite.py` → match
3. Update CLI command `governor lite` → match
4. Update all internal imports and references
5. Update `CLAUDE.md`, `.claude/rules/`, spec cross-references
6. Preserve git blame via `git mv`

---

## Historical Note

The name "Maude" originated as a friendly CLI alias during an informal session. The agent interpreted it as a naming decision and committed to it — 101 tests, a full module, CLI commands, spec references, and documentation. This is cited internally as an example of why NLAI matters: proposals that sound like decisions get treated as decisions unless the system enforces the distinction.
