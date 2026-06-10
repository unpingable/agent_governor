# Candidate — Tock 2: session-attributable promotion

Status: **SHIPPED 2026-06-10** → `working/tock-02-session-attributable-promotion.md`
(refuse-dirty-first + per-path revert; 16 tests, 499-test regression sweep green).
Forcing gap: **GAP-N** (Tick 2,
`working/tick-02-nq-host-detail.md`). Cited by the tick/tock rule (tock must cite a tick
gap). Do not implement until opened.

## The gap (GAP-N)

Promotion/rejection operates on the **whole working-tree diff**, not on changes
attributable to the current supervised session. On a dirty tree this makes session
custody fake:

- Tick 2's promotion bundle listed 5 files; only 2 were the session's work — the other 3
  were Tick 1's uncommitted residue.
- `promote` would mint a record claiming files the session never touched.
- `reject` runs `git checkout -- . && git clean -fd` → **destroys pre-existing
  uncommitted work** (both ticks).

> Promotion over a whole-tree diff means Maude cannot safely answer "what did this run
> produce?" once multiple ticks share a working tree. This blocks repeatability, not just
> cosmetics.

## Tock 2 shape (operator-provided)

```
Goal: Promotion/rejection must operate only on changes attributable to the current
supervised session, or refuse to launch/promote on a dirty tree.

Acceptance:
1. Session start records baseline tree state.
2. Event-ledger touched paths are used to compute candidate promotion scope.
3. Promotion bundle excludes pre-existing dirty files.
4. Reject cannot destroy pre-existing work.
5. Dirty-tree-at-launch either: hard-refuses, OR records an explicit pre-existing
   dirty set and fences it from promote/reject.
6. Promotion record names included/excluded paths.
7. Tests cover back-to-back ticks on a dirty tree.
```

## Operator bias: refuse dirty tree FIRST

Cheapest strong-custody fix, since GAP-N came from back-to-back uncommitted ticks:

```
dirty tree at session start → refuse, unless --allow-dirty-with-baseline
```

Earn smarter session-scoped attribution (ledger touched-paths → bundle) later. The
supervisor already records tool-call paths in the event ledger, so attribution is
feasible — but the bias is: crude refusal now, smart attribution when warranted.

## Planning note (model ladder)

Plan the Tock 2 packet with **Fable/Opus** — the failure mode is subtle (custody +
destructive-reject hazard). *Execution* can downgrade (Sonnet may ship it from a good
packet, as Tick 2 proved). This is the ladder appearing on schedule: judgment-tier
plans, mid-tier executes. See `working/next-steps-builder-ratchet.md`.

## Relation to other gaps

- Distinct from GAP-C (fence lives in operator's head) and GAP-J (thin promotion
  record). GAP-N is about promotion **scoping** — only surfaces on a tree that wasn't
  clean at session start.
- Does NOT supersede GAP-A/Tock 1 (fail-closed gate, shipped). This is the *next* tock.
