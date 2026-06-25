# Live-Adapter Allowlist Review — GATE before any live external-agent code

> **Ration card exists. No one has eaten with it yet.**

This is a **review gate**, not an implementation doc. Before a single line of
live-adapter code (a `RationedAgentRunner` backed by a real Claude Code / Gemini
runtime), the ration-card terms below must get a **fresh-eyes operator pass**.
"Mechanical wiring to live Claude Code" is the sentence engraved above many small
craters; the contract is done, but the *terms* are a human decision.

Scope of the first live slice (do NOT exceed): **live adapter binding, sandbox
only, one-shot only, no loop.** Bounded autopilot is explicitly NOT next.

The mechanism that enforces these terms already exists and is tested
(`src/governor/playbooks/ration_card.py`, `tests/test_ration_card_dispatch.py`).
This doc fills in the *values* the first real card will carry, and surfaces the
open questions. Each row is a decision to ratify, defer, or tighten.

| Term | S7 mechanism (already enforced) | First-card PROPOSED value | Operator decision |
|------|----------------------------------|---------------------------|-------------------|
| **Allowed agent** | `RationCard.agent_id`, exact match | one named runner (e.g. a sandboxed Claude Code instance) — TBD | ☐ |
| **Allowed commands** | `RationCard.allowed_shell_commands`, request ⊆ card | read/list/test only (no mutators) — TBD enumerate | ☐ |
| **Allowed paths** | `RationCard.allowed_write_paths`, request ⊆ card AND agent output ⊆ card | one known generated-report path under a sandbox dir — TBD | ☐ |
| **Forbidden writes** | absence-restrictive: anything not listed is refused | everything except the one report path | ☐ |
| **Git** | `git_allowed` locked False by type | no commit / push / merge (cannot be opened in this slice) | ☐ (locked) |
| **Doctrine** | `doctrine_writes_allowed` locked False by type | no edits (cannot be opened) | ☐ (locked) |
| **Network** | `network_allowed` locked False by type | none (cannot be opened) | ☐ (locked) |
| **Transcript handling** | report carries `transcript_digest` only; raw text never in a receipt | confirm digest-only is acceptable; where (if anywhere) the raw transcript is retained, and under what retention | ☐ |
| **Kill / refusal** | `refusal_check` consulted first; refusal wins before any spend | what drives the kill switch in the live binding (operator signal? file flag? timeout?) | ☐ |
| **Replay behavior** | durable spend gate refuses a replayed spend → `DispatchNotRun`, runner not called | confirm: a crashed/partial live dispatch fail-closes its retry (no double-dispatch); is that the right bias for a live agent? | ☐ |
| **Receipt expectations** | dispatch report is `verdict=observe`, `non_authoritative=True`, fails `is_authority_admission_receipt`, cites the LA consume as parent | confirm the report is the ONLY artifact that escapes the dispatch, and it is inert | ☐ |

## Open questions for the fresh-eyes pass

1. **Sandbox boundary.** What is the actual sandbox (cwd, fs jail, container)? The
   card constrains *declared* writes and fences *observed* writes ⊆ the allowlist,
   but Python cannot truly jail a subprocess — the sandbox is the real cage, the
   card is the contract. Where does the cage come from?
2. **Transcript trust.** The transcript is the agent's self-report. It is reduced
   to a digest and marked non-authoritative — but if anything ever *reads* the
   transcript content (a human, a summarizer), that read must not launder the
   transcript into a claim. Is the transcript ever consumed downstream, and if so,
   by what, under what non-authority discipline?
3. **One-shot completion.** "Drive the one task to completion" — what defines
   completion for the live runner, and what is the deadline / kill on a runner that
   never completes? (The `refusal_check` is a kill switch, but a hung runner needs a
   timeout, not just a veto.)
4. **Origin mode.** A live dispatch under `stub_origin` is a `DemonstratedConsumed`
   (structure shown, operational effect fenced). A *real* operational dispatch would
   need `observed` origin and `confer_operational_effect`. The first live slice
   should almost certainly stay non-operational (demonstration) — confirm.

## What this gate does NOT cover

- The bounded autopilot loop (a separate, later, also-gated slice).
- Any card that opens git / doctrine / network / non-observe output (locked by type
  in this slice; opening them is a future ratified change with its own review).

## Exit of this review

When every row above has an operator decision and the four open questions are
answered, the live-adapter binding may be written — and only then, sandbox-only,
one-shot-only, no loop.
