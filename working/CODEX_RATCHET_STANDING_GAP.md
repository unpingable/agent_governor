# CODEX_RATCHET_STANDING_GAP

**Status: PARKED full-surface candidate. No immediate build.** Filed 2026-06-10
(operator-authored). Disposition + build order at the bottom.

## Kernel rule

> **Codex capability does not imply Codex standing.**
> Each role must earn standing separately at the boundary where its output is consumed.

## Claim

Codex exists in the estate as partial, role-specific surfaces, but does **not** yet have
a complete ratchet-standing model across its three intended roles. The gap is **not**
"Codex is unavailable" — Codex is available. The gap is that Codex participation is not
yet normalized into tick/packet/verdict semantics across all three roles, and the
existing surfaces must not be allowed to imply standing for roles they do not satisfy.

## Current state (grounded 2026-06-10)

| Codex role | Current status | Standing problem |
|---|---|---|
| **Chat / interferometry** | Exists: `CodexBackend` (`src/governor/chat_bridge.py:910`), `codex exec --json`; daemon auto-detects codex on PATH | Not a tick participant by itself |
| **Independent reviewer** | Exists operationally: the `codex-exec` skill (adversarial / Lean review), memory `feedback_codex_for_adversarial_review` | Not yet wired as a ratchet **verdict input** |
| **Supervised executor** | **Missing** from `src/governor/runtime/adapters/` (only `claude_code`, `gemini_cli`) | Cannot be selected as a gated executor under tick supervision |

Feasibility note: codex CLI has `--sandbox` modes, execpolicy `.rules`, approval
escalation, a hook system, and `--json` JSONL events — enough machinery to *support* an
executor adapter when thawed, but that capability is **not** standing (kernel rule).

## Forbidden promotions (explicitly inadmissible)

- Chat backend existence does **not** imply reviewer standing.
- Reviewer success does **not** imply executor standing.
- `codex exec --json` availability does **not** imply tick-packet participation.
- Sandbox / approval / hook support in the Codex CLI does **not** imply estate
  supervision until adapted and witnessed.
- A Codex review verdict may *inform* a tick packet, but does **not** authorize treating
  Codex as a code-writing runtime.
- A Codex executor run, once implemented, must be distinguished from Codex reviewer
  output in packet/verdict accounting.

## Desired end state (role identity preserved)

### 1. Chat / interferometry standing
Codex usable as a chat backend for model comparison, operator interrogation, non-tick
exploratory work. Acceptance:
- Codex chat output captured with backend identity.
- JSONL parsing failures classified explicitly.
- Chat/interferometry output not treated as tick execution or review evidence unless
  separately routed through those surfaces.
- UI/daemon can report Codex availability without implying ratchet standing.

### 2. Independent reviewer standing
Codex invokable as a read-only independent reviewer over shipped diffs, Lean changes,
packet contents, or candidate tick outputs. Acceptance:
- Tick can invoke Codex in reviewer mode **after** executor output exists.
- Reviewer mode is read-only / constrained to non-mutating review.
- Review output captured into the tick packet with model/backend identity.
- Review verdicts classify at least: **pass, concern, blocker, tool failure, timeout,
  refusal/unavailable**.
- Reviewer verdicts advisory unless a policy explicitly gates on them.
- Reviewer output cannot mutate the workspace or satisfy executor obligations.

### 3. Supervised executor standing
Codex may eventually run as a supervised executor tier, parallel to `claude_code` /
`gemini_cli`. Acceptance:
- Selectable through the same supervised runtime adapter interface as existing executors.
- Pre-tool gate applies before filesystem/process/network-affecting actions.
- Sandbox, execpolicy, approval escalation, hook behavior mapped into estate
  supervision semantics.
- Codex JSONL/events captured into the tick packet.
- Mutations attributable to Codex executor identity.
- Refusals, tool failures, policy denials, sandbox escalations classified distinctly.
- Tick verdict distinguishes Codex-as-executor from Codex-as-reviewer.
- Executor standing granted **only after** a witnessed minimal-mutation tick AND a
  negative-control refusal.

## Non-goal

Do **not** collapse these into a generic "Codex adapter." Three separable roles, three
authorities: **chat asks, reviewer judges, executor mutates.** The adapter family must
preserve that distinction.

## Disposition

Parked full-surface candidate. No immediate build. Likely build order when thawed:

1. **Reviewer standing first** — Codex already shows value as an adversarial reviewer;
   smallest ratchet-safe increment. (Wires into the two-verdict ratchet as an
   independent-reviewer input; see `working/next-steps-builder-ratchet.md` §2.)
2. **Normalize chat/interferometry reporting** — make existing Codex backend
   availability visible without overclaim.
3. **Supervised executor adapter** — only after a concrete forcing case requires Codex
   to mutate code under tick supervision.

## Composes with

- `working/next-steps-builder-ratchet.md` §2 (model-ladder ensemble routing: Codex/Gemini
  as cross-checkers, not default executors) — this gap formalizes Codex's standing model.
- memory `feedback_codex_for_adversarial_review` (the reviewer role's existing value).
- memory `feedback_model_tier_routing` (the ladder this slots into).
- The kernel rule is an instance of the estate's anti-laundering discipline:
  capability ≠ standing; standing is earned at the consumption boundary.
