# Maude product boundary — maude 3.0 (executes R-MAUDE-3)

**Status:** RATIFIED (2026-07-02, operator-paired; the "deferred operator
conversation" from `docs/roadmaps/tools/maude.md` §0, held and decided).
Campaign: `docs/campaigns/governed-shell/`.

## Role

Maude is the **terminal-native operator shell for supervised agent runtimes
and cross-tool decision workflows** (OpenClaw/Hermes-shaped). AG is one
authority substrate maude invokes — not maude's product boundary.

> Maude runs the room. AG decides what the room is allowed to claim.

## Ownership split (settled by evidence, not by external framing)

| maude owns | AG owns |
|---|---|
| operator interaction; the desk | refusal semantics; refusal placement |
| decision-queue rendering + triage | the decision sources + the one mutation door |
| session lifecycle DRIVING (over RPC) | the supervisor FSM; tool interception |
| transcript/event rendering; receipt rail | receipts; the event ledger (sole writer) |
| branch/fork/promotion UX | promotion custody + baseline fencing; lab gate |
| steering input (send_input conduit UI) | the adapters (BELOW the authority gate) |
| envelope display; widen one-liner | scope.escalate; scars; budgets; timeouts |
| refusal→route map (proposes moves) | what refuses, and why |

The exploration settled the one contested assignment: **provider/model
adapters stay AG.** They are how AG supervises (unix-socket hooks, settings
injection, event mapping) — they sit below the authority gate, and a shell
that owns them owns the interception point. Maude gets
`runtime.adapters.list` introspection and honest capability degradation,
nothing more. (This refutes the "maude owns model/provider adapters" line
from the external packet — the room does not get to rewire the walls.)

Boundary rule, both directions: maude may orchestrate and render decisions;
it must not become the authority source. AG may refuse or authorize
authority-bearing transitions; it must not become the whole terminal runtime.

## Maude 3.0 — fork-in-place refactor (not a rewrite)

~40-50% of maude v2.4 survives with real test coverage; throwing away a
tested transport + client + state machine to rewrite a TUI is vanity.
Breaking-changes freedom applies (alpha, ~zero users): call it 3.0.

**Keep** (evolved):
- `MaudeSession` state machine → generalized to a keyed dict of sessions
  (kill the single `active_supervised_id`).
- Intent parser → pruned of PLAN/BUILD intents; feeds the command line.
- The supervised-loop UX patterns: y/n quick keys, timeout countdown,
  COMMUNICATE-red highlighting, syntax-colored diff, ASCII lineage tree.

**Delete:**
- In-repo transport + RPC client (`src/maude/client/`) → replaced by
  `libs/ag_shell_client` (GS-8/GS-9). Kills the triplicated framing/
  socket-path code and the MAUDE_RPC_SURFACE_UNPINNED hazard by construction
  (maude pins the package; the package is CI-tested against the daemon).

**Replace** — app.py (1,515 lines) decomposes into three seams:
- **ScreenManager** — queue home · session view · sessions board · diff view
  + overlay stack (why / help / palette).
- **CommandRegistry** — command objects replacing the if/elif intent
  dispatch.
- **DecisionFeedController** — owns the watch connection, the local decision
  cache, and envelope→keymap resolution. The ONE component that understands
  the decision envelope.

## The PLAN/BUILD verdict (ratified: CUT)

The spec-lock chat paradigm does not survive as a shell feature. What
survives is its *idea*, relocated to where it is enforceable:

- "lock understanding before acting" → **AG's admissibility moment** —
  HELD launches with VoI-ranked questions in the queue (shell renders,
  AG holds).
- "plan first" → an **autopilot-profile property**, not a modal shell state.

Chat-with-governor as a maude screen is cut from v3 scope (D-GS-2). If it is
missed, it returns later as its own recorded decision — not as a leftover.

## Deferred (named, not built)

- The broader terminal-agent-control-plane product conversation beyond this
  boundary (multi-runtime hosting ambitions, etc.) stays deferred; this
  document is the boundary, not a build authorization for everything inside
  it.
- Session reattach after daemon restart: verify-first (D-GS-7) — supervisor's
  `resume_session` is pause-only today; the desk works without reattach
  (dead-with-daemon sessions render as exited).
- Multi-party approval, MCP server in maude, DAG viz beyond lineage v1:
  campaign Forbidden.
