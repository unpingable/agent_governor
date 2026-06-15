# Operator decision — observer vocabulary + excavation-vs-YAGNI (2026-06-14)

> **Scope:** primary enactment is **Lean-side** (the Lean-Claude mints the noun + keeps
> the excavation breadcrumb in its repo). This is AG's **consumer-side record** — kept
> because Decision 1 touches the global CLAUDE.md "Scope vs coverage" lead added today and
> Decision 2 governs the `Force` fossil in AG's P4.0g spike note. AG records and consumes;
> it does not enact the mint.

Breaks a deadlock where both Claudes deferred to each other ("no, *you* say the vows").
The fix: **separate ratification decisions from progress decisions.** You do not need the
final noun to keep moving; you only need to stop "noun undecided" from being read as "all
observer work frozen." That was the actual deadlock.

## Decision 1 — global doctrine: HOLD
**HOLD** promotion of `excavation-vs-YAGNI` to global `~/.claude/CLAUDE.md`.
Reason: it is correct, but it has fired **once**. Candidate until a second independent
recurrence (doctrine-promotion: candidate until repeated). Keep the local breadcrumb (it
lives in the lean repo: `~/git/lean/working/excavation-vs-yagni.md`).
AG-side note: it composes with the **"Scope vs coverage"** lead added to global CLAUDE.md
today (same YAGNI family — invented-foundation vs excavated-repeated-structure; fence:
*earned ≠ public*). Recognized, **not** promoted. Re-evaluate on the next firing.

## Decision 2 — shared observer noun: DO NOT MINT, record provisional
Do **not** mint shared observer vocabulary yet. Record a provisional preference so the
loop stops re-litigating:

> **Provisional Lean-facing neutral noun: `VerdictFor : Consumer → Artifact → Verdict`**

Rationale:
- names the **output**, not the metaphysics;
- **codomain-aware** — works for `Allowed | Denied | Unknown` (a verdict, not a stamp);
- consumer-indexed (`VerdictFor consumer artifact`) avoids producer-stamp implication;
- avoids the overloading of `Force` (enforcement), `Admits` (AG-specific), `Adjudicates`
  (courtroom weight), `Relies` (positive-only).

Fallback: **`AssignsVerdict`** is acceptable.
`Relies` is **paper prose / reliance-specific application lemmas only**, NOT the nucleus:
the codomain includes negative/unknown, so `Relies consumer artifact = Denied` reads as
"relies on a denial" — a semantic oil slick. Reserve it.

The current scratch `Force` label is a **fossil**, not a ratified noun. The neutral noun
is decided at module-mint, not now.

## Decision 3 — continue fenced progress only
Permitted: scratch aggregation (`Scratch/ObserverPacket.lean`), compile/audit, codex
precheck on substantive new Lean, non-register claim sketch.
Forbidden until ratification: shared/foundation module mint, `LeanProofs.lean` wiring,
`CLAIM-REGISTER.md` promotion, global CLAUDE.md doctrine promotion.

## The principle (so this doesn't recur)
Ratification decisions (mint the noun, promote to global, enter the register) wait for the
operator in the room. Progress decisions (scratch, audit, sketch, record provisional) do
not. An undecided ratification never freezes fenced progress.
