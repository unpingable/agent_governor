# Lean sweep — first since 2026-07-02; AG × v10 screens

**Filed:** 2026-07-15
**Status:** **FINDINGS — no fixes applied; each item needs its own ruling**
**Trigger:** the standing rule *sweep Lean on kernel-axis work*
(`memory/lean_admissibility_kernel`) fired on the `oracle_class` finding
(receipt-kernel invariants + publish boundary = kernel axis).
**Instrument:** `~/git/lean/docs/AG-AUDIT-CHECKLIST.md` — the Lean author's
own checklist, written to be applied by "the AG session (and/or codex)".
Applied as written.

## Drift: the sweep was 13 days and 3 major versions stale

| | pinned in AG | actual |
|---|---|---|
| lean HEAD | `762967c` (2026-07-02) | `c47faee` (2026-07-15) |
| lean release | v7.0.0 tagged | **v10 released 2026-07-14** |

`docs/roadmaps/tools/lean.md` still reads *"Status: RATIFIED (2026-07-02,
A8) · Repo: ~/git/lean (HEAD 762967c … v7.0.0 TAGGED same day)"*. Three
releases landed since (v10 `6918769`, plus `bdf714f` adjudication provenance,
`eb1ee75` codex audit of the paper repo). **v11 is in flight as of this
sweep** — per the citation-tier rule this sweep cites **v10 (shipped)** and
nothing from the moving target.

The roadmap's staleness is itself the finding the sweep rule exists to
prevent: AG cites a kernel it stopped watching.

## HIT — `oracle_class` has a theorem behind it now

The self-attested independence class
(`working/finding-oracle-class-self-attested-2026-07-15.md`, found by hand
hours earlier) is **exactly** what two checklist items name:

- **Check 1, F2 special case** (`fluentSystem`, `UniversalStamp`): *"does any
  confidence-like, claim-blind signal (model self-report, **score without
  provenance binding**, 'LGTM'-shaped approval) appear as accepted evidence at
  more than one unrelated gate?"* — `oracle_class` is a self-reported integer
  with no provenance binding, consumed by `oracle_independence` AND
  `release_taint`'s publish threshold. Two unrelated gates. **Yes.**
- **Check 4** (`eentail_iff_read_rooted`, `reliance_roots_in_provenance`):
  *"is any reliance decision rooted in a confidence signal rather than a
  claim-indexed provenance receipt? `HighConfidence ⊬ MayRely`"* —
  `release_taint` roots a publish decision in it. **Yes.**

That upgrades the finding from a drafter's hunch to a smell with a named
theorem. The hand-audit and the formal screen converged independently, which
is the sweep rule paying for itself.

## Codex adversarial pass — checks 5–8

Codex sandbox smoke-tested first (fixed; reads files, no approval hang).
Given checks 5–8 only, told not to re-derive 1–4. Six findings returned.
**Codex finds candidates; the AG session verifies.** Verification status is
mine, not codex's.

### VERIFIED by me

**1. `TTLManager.revalidate` refreshes without evidence** — check 5,
`refresh_is_inexpressible`. `src/governor/ttl.py:235`.

```python
def revalidate(self, claim_id: str) -> bool:
    """Mark a claim as freshly validated. Returns True if found."""
    ...
    tc.last_validated_at = datetime.now()
    tc.current_confidence = tc.original_confidence
```

Takes **only a claim_id**. Restores freshness *and* original confidence. No
evidence, no receipt, no witness. A claim gets young again by being asked to
— the textbook re-stamp the theorem says is inexpressible.

**Severity: LATENT.** The single caller (`ttl.py:609`) fires only on
`AuditDecision.ALLOW_HARD` — the orchestrated path *does* acquire new
evidence first. The caller is disciplined; the **method** is the lane. Fix
shape (same law as everything else today): `revalidate(claim_id, *,
evidence)` — make refresh unsayable without the thing that earns it.
WALL-GRADE by the formal discipline (the path exists), latent in practice.

**5. Compaction can drop governance state with no loss record** — check 8,
`checkpoint_mints_nothing`. `src/governor/context_compact.py:580,611`.

```python
preserved_decisions=conversation.decisions.copy() if self.config.always_keep_decisions else [],
preserved_anchors=... if self.config.always_keep_anchors else [],
preserved_constraints=... if self.config.always_keep_constraints else [],
```

…while `dropped_items` is populated **only** from `dropped_turns`. So with
the flags off, decisions/anchors/constraints vanish *without appearing in
dropped custody* — the loss is not merely lossy, it is unrecorded, which is
the thing this module exists to prevent.

**Severity: LATENT.** All three flags default `True` (`:165-167`), so the
shipped default is safe. Config-gated silent drop.

### REPORTED by codex, NOT yet verified by me

Recorded verbatim as candidates. Do not act on these without verification.

| # | check / theorem | path | codex's grade |
|---|---|---|---|
| 2 | 5 · `refresh_is_inexpressible` | `claims_evidence_binding.py:104` → `store_sqlite.py:386` — claims check `has_blob` = "exists (any state)", so expired hash-only evidence may satisfy binding with no remaining-validity comparison | SCREEN |
| 3 | 6 · `caveat_dropping_is_inexpressible` | `ci.py:459` — `if receipt.verdict == "pass": return True, None`; CI accepts every pass **without reading `unsettled`** (only `proceed` gets caveat screening). The checklist names this exactly: *"caveat-blind demand… burdens are decorative wherever demand is caveat-blind"* | SCREEN |
| 4 | 7 · `one_receipt_cannot_license_two_discharges` | `cooked_context_orchestrator.py:521,578` — `confer_operational_effect` returns the underlying `ConsumedResult` with no receipt book / consumed state / residual threading | WALL |
| 6 | 8 · `settlement_preserves_live_multiplicity` | `commitment_transport.py:497,564` — commitment IDs derive solely from normalized text, then `if cid in seen_ids: continue`; duplicate live obligations collapse to one | WALL |

Finding 4 deserves care on verification: `confer_operational_effect` is the
origin-fence spend wall (feature-history: *"the spend wall that accepts only
the operational type by isinstance"*). Its type-split is about **which**
consumption may confer effect; codex's claim is about **how many times** it
may be re-read. Those are different axes and both can be true.

## The meta-finding: every lane is latent

`oracle_class`, `revalidate`, and the compaction drop are all the same shape
— **safe defaults, disciplined callers, expressible violations.** Nothing is
breached today. Every one of them is walkable by a caller who simply passes
the argument or flips the flag, and nothing would testify that it happened.

That is precisely what the `*_is_inexpressible` family is about: the
discipline's claim is that the operation should not be **sayable**, not that
it happens to be unsaid. AG has been enforcing the *unsaid* half by
convention. The kernel says convention is the wrong instrument.

Same law as the day's other five instances, one level up: **an operation must
be earned by evidence, never asserted by name.** `operator_mode`, axis values,
`custody:` strings, `Belief.source`, `oracle_class` — and now `revalidate()`.

## Stop lines

- **Nothing fixed.** Every item above touches kernel invariants, the publish
  boundary, TTL semantics, or compaction custody — custody-affecting by the
  register rule. Each needs its own ruling.
- Findings 2/3/4/6 are **codex testimony, unverified** by this session. They
  are candidates.
- Checks 1–4 were applied only insofar as `oracle_class` answers them; a full
  pass over checks 1–4 (universal stamp census, crossroads, midpoint
  matching, provenance rooting per decision) is **not done**.
- The lean roadmap's v7→v10 correction is a separate mechanical update, not
  made here.
- Nothing in this sweep is filed in `~/git/lean` — per the checklist's own
  reporting discipline: *"File results in AG's own loop, not here — this repo
  holds the shapes, not the estate's testimony."*
