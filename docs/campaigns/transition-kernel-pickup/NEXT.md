# Next — recommended Slice 1 (named, NOT built)

Reduction is done (verdict B). Implementation is gated on one operator decision.

## Operator decision required first (the scope-locus fork)

Choose **Model X** (Standing adds spend-time `ScopeMismatch`) or **Model Y** (`AGGrantAdapter`
matches the Standing-attested scope at the mint boundary). See [DECISIONS.md](DECISIONS.md). This
ratifies D010 and selects Slice 1's shape. It is a custody/authority-boundary call → operator-fiat.

## Recommended Slice 1 (after the fork is decided)

**Target seam:** `activation.py` Office 2 (`activation.py:449`) — the cleanest, isolated,
already-typed act-standing office. Replace the `standing_ok: bool` parameter with a verified
`StandingGrantToken`. (The supervisor actor/session/step boundaries are the higher-value
follow-on slices; activation proves the pattern at low blast radius first.)

**Forcing artifact (failing test):** AG cannot activate the rung without a Standing-issued grant
token — a bare `standing_ok=True` no longer admits; a missing / expired / wrong-scope /
already-spent token refuses with the corresponding typed reason.

**If Model X:** Slice 1a is a *Standing-side* failing test + refusal: `grant use` with a
mismatched `(action,target)` → `StoreError::ScopeMismatch`. Then `AGGrantAdapter` consumes the
now-complete token (verify via the real cross-repo `StandingClient`, map Standing refusals onto
AG's: `GrantExpired`→expiry, `Unauthorized`→subject, terminal `Used`→already-spent, `GrantNotFound`
→`REFUSED_NO_STANDING`, `ScopeMismatch`→wrong-scope).

**If Model Y:** Slice 1b is the `AGGrantAdapter` at Office 2 that verifies the token AND matches
its attested `GrantScope` against the activation's `(action,target)`, refusing a mismatch locally
with an explicit receipt that records "scope matched by adapter against Standing-attested scope"
(so the locus is auditable, not laundered).

**Either way — Slice 1 invariants:**
- the adapter VERIFIES; it does not mint scope/expiry/spend refusals Standing already owns;
- the receipt records token id, scope, spend, actor/session binding, and which refusals were
  inherited vs locally applied;
- `standing_basis` (`activation.py:496`) carries the verified token id, not a bare bool;
- no change to conductor / `StepVerdict` projection / admission semantics / closed enums;
- `StandingClient` graduates from SPEC-stub to a real cross-repo client **only** for this seam.

## Hard limit

Do not touch the supervisor hot path, `fork_session`, or the `observe`-mode divergence in Slice 1.
Those are named laundering surfaces (CAMPAIGN.md) and are follow-on slices, each with its own
forcing case — not a "while I'm here."
