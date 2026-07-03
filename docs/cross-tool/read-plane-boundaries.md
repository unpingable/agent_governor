# Read-plane boundaries — spine / governor-atlas / state_index_export

**Status:** boundary note (2026-07-03; R-SPINE-1, resolves consolidation
candidate #5 / Q-C2-5). Three read/legibility surfaces exist in the
constellation; C1 evidence (reconciliation INVENTORY §6) found **zero indexing
overlap** between them today, with anti-laundering disclaimers enforced in code
on all three. The only real risk is convergent growth. This note fences what
each may index and what none may do — so the three stay distinct as they grow.

## The three surfaces

| surface | repo | indexes | scope |
|---|---|---|---|
| **spine** | ~/git/spine | governed material across the constellation (declaration manifests → editions) | constellation-wide READING |
| **governor-atlas** | ~/git/governor-atlas | AG's architecture as a typed claim graph (surfaces/gates/stores/edges, wired-vs-specified) | AG-INTERNAL claims |
| **state_index_export.v0** | agent_gov `src/governor/state_index_export.py` | AG's own prose/declared corpus (gaps, playbooks, campaigns, backlog) → a deterministic JSON projection | AG-REPO state |

## The shared law — none of them confers authority

All three are read planes. **Findability is not legitimacy; an index is not
evidence.** Each already enforces this in code, and must continue to:
- spine: `refusal.py` forbids the legitimacy verbs {ratified, governed, valid,
  admitted, authorized, witnessed, certified, approved, supported, promoted};
- state_index_export: "a record is not proof; a status is not authority; a
  spec_ref is a pointer, not validity"; execution_state never emitted;
- governor-atlas: mode-preserving (wired/specified/derived/candidate stay
  distinct); "spec_is_not_wired; resolved ≠ supported".

No read plane may: mint a receipt, admit a case, promote a status, or be cited
AS the authority for a decision. They point at authority; they never are it.

## What each may NOT index (the fences)

- **spine** must not scan `state_index_export`'s roots or governor-atlas's case
  graph as if it owned them — it may reference a governed artifact by manifest,
  never absorb another plane's projection as its own content.
- **governor-atlas** stays bounded to AG internals (surfaces/gates/stores). It
  must not grow into constellation-wide reading (that's spine) or become a
  status registry over AG's prose corpus (that's state_index_export).
- **state_index_export** stays an AG-repo scanner. It must not reach into other
  repos (that's a spine concern) and must not assert wired-vs-specified claims
  about AG architecture (that's governor-atlas).

## Citation direction (one-way, to prevent circular authority)

If they reference each other, the direction is: a read plane may POINT at an
artifact another plane also indexes (both can list the same doc), but no plane
consumes another's projection AS an admitted input. The sovereign of any status
is the governed artifact itself (a campaign DECISIONS ruling, a receipt, a
manifest admission) — never a read plane's index of it.

## Disposition

Keep all three separate (consolidation candidate #5 recommendation). This note
is the fence the C1 evidence called for; no merge is warranted. Revisit only if
a plane's roots are observed reaching into another's scope — that observation,
not aesthetic tidiness, would open the question.
