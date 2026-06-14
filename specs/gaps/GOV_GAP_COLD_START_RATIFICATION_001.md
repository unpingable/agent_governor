# GOV_GAP_COLD_START_RATIFICATION_001

## Title

A warm context may not admit, ratify, or present its own authority-changing case.
Authority-changing diffs must be re-derived by a **fresh controller context** from
inherited receipts only. **Coldness is not a property a context may claim — it is a
construction constraint on the channel graph.** Enforce the break; don't badge it.

## Status

Gap spec — **candidate doctrine + enforcement-surface name. No invariant, validator,
receipt type, or runtime check is ratified by this filing.** Converged design captured
2026-06-13 (operator + ChatGPT + Claude-web, at P4 entry); the recursion is that
cold-start was the *practice* the operator handed this Claude two turns earlier
([[feedback_inherit_receipts_not_warm_intentions]]), here promoted to a candidate *gate*.
Earns its keep when a forcing case shows a warm context ratifying its own
authority-changing case with nothing structural to stop it. Until then: name early,
ratify lazily, build only on a forcing case.

## Origin

P4 is the first concrete forcing pressure: P4 promotion is **precedent-setting authority
conversion** (trial value → `ControlBaseline`), and the session that *drafts* the
promotion is exactly the session that would *ratify* it. The keeper, stated three ways:

> No session may ratify the authority change it emotionally wants to complete.
> Enforce the break; don't badge it.
> No signed claim substitutes for the witness it claims to be.

## Boundary law

This is **No Negative Clearance, across time.** "I am cold now / prior intention
excluded" is the temporal form of "absence of objection proves authorization": a claim of
the very property the claimant cannot verify, because the warmth is precisely what stops
it noticing. Coldness can therefore not be *attested* by the warm context — it must be
*enforced by construction*.

Sibling to [`GOV_GAP_STATE_REENTRY_PROTOCOL_001`] (corrective authority monotonicity:
*what transitions are admissible after failure*). Same family, different chokepoint: this
gap is about the **epistemic independence of the ratifying context**, not the
authority-set delta. Both are NLAI: a self-report is not the witness it names.

## What exists (partial coverage)

1. **`docs/loop-protocol.md` §9 "Independence rule" (the closest rhyme):** *"warm
   self-audit suffices for mechanized checks; at chunk boundaries and before
   custody-affecting ratification, AUDIT runs in a fresh context (new session; probes +
   ratified docs + receipts only, no warm narrative). The instance that drifted is the
   instance least equipped to notice."* — This is the **right principle as prose
   discipline**. It is the *badge*, not the *break*: nothing emits a checkable receipt
   that the fresh-context break actually happened, nothing mechanically detects when the
   rule fires, and nothing *refuses* a warm context that ratifies anyway.
2. **`session_continuity` / runtime session forking** — can spawn a fresh context, but
   has no channel-policy fence (a fork can inherit warm scratch state).
3. **The validator supersession ceremony** (`standing/validator.py`) — proves a new
   authority carries a receipt produced under the prior; it does **not** constrain whether
   the *context producing that receipt* was cold.
4. **[[feedback_inherit_receipts_not_warm_intentions]]** — the operator-side practice
   ("resume cold from receipts; warm operator is weather, cold receipt review is verdict").
   Practice, not gate.

## What the gap names (candidate; not authorized to build)

### 1. Coldness as a channel-graph constraint, not a claimed property

The gate must **impose the break**, not accept a self-asserted coldness receipt. The
`AuthorityTransitionRequest` is handed to a **freshly-spawned controller context whose
only inputs are the inherited receipts**, with **no channel** to the warm session's
working state. Then "excludes prior intention" is not a self-report — it is true *because
the cold context never had access to it*.

### 2. `ColdStartBreakReceipt` — attests the break, not the exclusion

```
ColdStartBreakReceipt:
  request_hash               # the AuthorityTransitionRequest under review
  inherited_receipts_hash    # the receipts-only input set
  fresh_context_id
  warm_context_id
  channel_policy: receipts_only
  forbidden_inputs:          # what the channel graph excluded BY CONSTRUCTION
    - warm transcript
    - warm scratch state
    - unreceipted draft state
    - conversational continuation channel
  result:
    - cold context was spawned
    - request was reconstructed from receipts only
```

It attests **that the break happened** (fresh context, receipts-only, no warm-state
channel) — which is *checkable*. It must NOT assert "I was unbiased / I forgot the vibes
/ I excluded intention" — astrology with a signature block. Don't let the dog certify it
dropped the leash; build it so the leash isn't reachable.

### 3. Mechanical trigger — derived, not enumerated

```
cold_start_required(diff) :=
      diff alters a capability
  OR  diff alters a kernel invariant
  OR  diff changes what the system may decide
```

Everything authority-changing (promotion, ratification, supersession, admission-rule
edits, refusal-semantics edits) falls out as "changes decision power"; docs/test-repair/
janitor work falls out free as "touches no authority." The enumerated trigger list
(promote / ratify / supersede / close-audit-as-relied-upon / resume-after-halt /
doctrine-or-invariant-or-admission-or-refusal edit) is a **pre-cap stub** — useful
scaffolding, *to be derived once caps exist, not enshrined* (same move as
decomposition-caps; cf. `GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001`).

### 4. Two actors, two cold-boot mechanisms

- **Controller coldness — enforce by construction.** Fresh process, receipts-only channel
  policy. Fully mechanizable.
- **Operator coldness — approximate by cadence + receipts-only re-presentation.** There
  is no fresh James; the one who drafted the promotion warm is the one who ratifies it.
  The cold controller is the **fresh-eyes prosthetic the human cannot be**: it re-derives
  the case from receipts so the warm operator ratifies a **cold presentation**, not their
  own draft. This is the weaker link and the real job of the cold controller — never let
  the warm party present to itself.

### 5. The governor rule

> A warm controller may *prepare* an `AuthorityTransitionRequest`.
> It may not admit, ratify, or *present* its own authority-changing case.
> Authority-changing diffs must be re-derived by a fresh controller context from inherited
> receipts only.
> The operator may ratify only the cold controller's reconstructed case — not the warm
> session's draft or intention.

## Negative tests (the gate's real artifact)

```
warm session emits ColdStartReceipt claiming "prior intention excluded"
   => REFUSED: self-attested coldness (no break receipt; coldness is not claimable)
fresh context spawned but given the warm transcript
   => REFUSED: warm-state channel present (channel_policy violated)
fresh context spawned receipts-only, but the transition diff touches a capability
   and bypasses the cold gate
   => REFUSED: missing ColdStartBreakReceipt
docs-only change touches no capability / kernel invariant
   => cold gate NOT required (no false positive)
doctrine edit changes refusal semantics
   => cold gate required (mechanical trigger fires)
```

## Acceptance criteria

This gap is closed (to candidate-ratified or to enforced) when:

1. The mechanical trigger predicate is stated against a real capability/kernel-invariant
   surface (depends on caps existing — pre-cap stub until then).
2. At least one forcing case is found where a warm context can ratify its own
   authority-changing case with nothing structural preventing it (else stays doctrine /
   anti-regression handle, like its STATE_REENTRY sibling).
3. If built: `ColdStartBreakReceipt` attests only the construction facts (checkable),
   never the exclusions; the gate refuses a self-asserted coldness receipt; the five
   negative tests pass.
4. loop-protocol §9 Independence rule is upgraded from prose to a receipt-backed
   construction constraint (or explicitly left as prose with this gap recording why).

## Non-goals

- **Not ambient ceremony.** Cold-start is a *transition gate* at authority-changing
  boundaries, never a universal tax on routine slices. Ambient ceremony becomes
  bureaucracy; transition-gated ceremony becomes load-bearing paranoia.
- **Not a new corrective primitive** (STATE_REENTRY's jurisdiction).
- **Not an operator-fresh-spawn fantasy** — operator coldness is approximated, never
  constructed.
- **Not authorized implementation.** This filing names the surface; build waits on a
  forcing case and on caps for the mechanical trigger.

## Relationship to other gaps

- **GOV_GAP_STATE_REENTRY_PROTOCOL_001** — sibling. That gap: post-failure authority
  monotonicity (the `AuthorizedSet` cannot grow from its own failure). This gap: the
  ratifying context must be independent of the case it ratifies. Both are
  No-Negative-Clearance instances at different chokepoints.
- **GOV_GAP_BASIS_FOR_BINDING_SEMANTICS_001** — the signed-is-not-witnessed family. A
  cold-start gate that *accepts* a self-asserted coldness receipt is the form-vs-content
  failure (a warm session wearing a cold badge) — exactly the failure that gap names, here
  at the cold-start layer.
- **Decomposition-caps closure** (`GOV_GAP_DECOMPOSITION_COMPLETENESS_CAPABILITY_CLOSURE_001`)
  — the trigger detector borrows its shape: complete-by-construction over the capability
  surface, not an enumerated list.

## Provenance

Converged 2026-06-13 at P4 entry across three contexts. The recursion is the point:
cold-start was the practice this Claude was handed two turns before
([[feedback_inherit_receipts_not_warm_intentions]]); promoting it from practice to gate is
the convention→encoded move ([[feedback_allowlist_authority_blocklist_detection]] family),
and it must pass its own bar — a cold-start gate that badges instead of breaks is just a
warm session in a cold costume. "Enforce the break; don't badge it" is the keeper line.
