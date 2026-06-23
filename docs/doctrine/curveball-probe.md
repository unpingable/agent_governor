# Curveball Probe

A **triggered review move**: test an over-smooth frame by transposing it into a remote
domain with the same *visible* structure, vary one hidden variable, and keep the break.

> **Curveball is controlled transposition used to discover the missing discriminator.**

Not "be contrarian," not "find an analogy," not "what about dragons." It is the controlled
counterexample / control-experiment move (vary one variable, hold the rest) — ancient, but
one LLMs structurally underuse because their default gradient is completion-under-local-
coherence. This doc exists to make the move *triggerable*, with guardrails.

**It is not** a Governor office, gate, receipt, or subsystem. It is a prompt/workflow operator.
Building a "Curveball Subsystem" would be the cathedral the joke is about. Keep it small.

## The strong framing: discovery, not confirmation

A curveball's job is **not** primarily to confirm "does the frame survive translation?" It is
to **reveal the hidden discriminator the frame depends on but has not named.** You do not need
to know the load-bearing variable in advance — run the frame through 2–3 adjacents and let the
over/under-match *surface* it. Breadth is cheap; precise aim is hard. Prefer breadth.

## Trigger (deliberate, never default)

Invoke when: a synthesis feels too smooth / too inevitable; reviewers converge with no live
disagreement; a decision turns on an *implicit* distinction; a frame looks portable but was
never tested outside its native domain. **Do not run by default** — mandatory curveballs decay
into ceremonial contrarianism (the very failure mode this guards against, applied recursively).

## Method

1. State the `frame_under_test`.
2. List the `visible_features` that define the pattern.
3. Pick one or more `remote_case`s sharing those visible features.
4. Transpose the frame into each.
5. **Preserve the breakage** — do not smooth it away.
6. Name the `missing_discriminator` the mismatch exposes.

A valid curveball **shares the frame's visible features and breaks on a hidden variable.**
Anything else is a novelty grenade.

## Output contract

`frame_under_test` · `visible_features` · `remote_case` · `transposition_result` · `breakage` ·
`missing_discriminator` · `decision_effect`.

**The result must not end by reconciling the analogy into harmlessness.** If the remote case
breaks the frame, the break stays visible. *This rule is the whole doctrine* — without it the
model does what models do: make the analogy pleasant, tuck it in, give it cocoa, and destroy
the evidence.

## How it differs from the other review lenses

- Critique: *is this wrong?*  · Steelman: *could this be right?*  · Red-team: *how is this attacked?*
- **Curveball: does this still mean anything after domain translation — and what discriminator
  is silently doing the work?** It forces *nonlocal* evidence; the others stay in-frame.

## Anti-patterns

Contrarianism for its own sake · remote cases that don't share the visible structure · cute
analogies that expose no discriminator · reconciliation sentences that erase the break · turning
the probe into a mandatory governance office.

## Worked example (from this repo, 2026-06-23)

- **frame_under_test:** Standing must own spend-time scope matching; AG inheriting scope locally
  is authority laundering (transition-kernel pickup, D010 Model X).
- **visible_features:** externally-issued authorization; scoped; expiring; single-use/consumption
  boundary; consumer attempts to act under it.
- **remote_case:** OAuth access tokens.
- **transposition_result:** in OAuth the *resource server* checks `aud`/`scope` locally —
  scope adjudication sits at the consumer boundary (≈ the Model Y we rejected).
- **breakage:** AG chose the *opposite* locus from the dominant deployed token pattern.
- **missing_discriminator:** AG failure is non-minting and fail-closed; a refusal produces no
  authoritative custody artifact, so AG must not be a scope authority. Standing owns the
  grant-use witness because spend-time scope match is part of the *authorization lifecycle*,
  not merely local resource enforcement.
- **decision_effect:** does NOT overturn the design; exposes the unstated defense the design
  must carry. "You owe a discriminator here," not "gotcha, you're wrong."

That is a good curveball precisely because it made the uncomfortable thing visible — *your
locus is not the industrial default* — and nobody threw it during the decision.

## Status / provenance

Candidate technique, filed where discovered (agent_gov, 2026-06-23). Cross-project in scope but
**not yet promoted** to global guidance — promote per `~/.claude/CLAUDE.md` § Doctrine promotion
only if it recurs and pays rent. Composes with the workflow quality patterns (completeness
critic, perspective-diverse verify) as one more lens, not a replacement.
