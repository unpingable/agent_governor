# Campaign — governed shell (maude 3.0 + phosphor governed-session lane + shell contract)

Status: **FILED 2026-07-02; GS-0/GS-1 executed with filing.** Fills roadmap
slots **R-MAUDE-3** (maude product boundary) and the **machinery half of
R-PHOS-2** (lane abstraction; ops-casework *content* stays operator-owned).
Spans agent_gov + maude + gov-webui; AG is custody root, so the capsule lives
here.

Capsule: [NEXT.md](NEXT.md) (slices GS-0..GS-17) · [DECISIONS.md](DECISIONS.md)
(ratified calls + open items) · [STATUS.md](STATUS.md). Design docs:
`docs/design/governed-shell/{loop-ux, shell-contract-v0, maude-boundary,
phosphor-lanes}.md`. Routing per `docs/roadmaps/ROUTING.md`.

## Question

> Can governed work be as easy as ungoverned work — launch in a sentence,
> approve in a keystroke, steer by typing — while every act that matters
> leaves ink and every refusal routes somewhere visible?

## Boundary law (fixed)

**Maude runs the room. AG decides what the room is allowed to claim.**

Shells (maude terminal, phosphor web lane) orchestrate and render: session
lifecycle over RPC, decision triage, transcripts, diffs, envelopes. AG keeps
everything authority-bearing: the supervisor FSM, tool interception,
intervention timeouts + auto-deny, budget enforcement, lab gate, promotion
custody + baseline fencing, adapters (below the authority gate — shells never
touch them), refusal semantics, receipts. "AG is a kernel, not an IDE."

## Design core (detail in the four design docs)

1. **The desk:** one home screen — ambient strip / unified decision QUEUE /
   command line. Launch = one sentence + Enter. Queue-first focus (ratified).
2. **One decision feed, one mutation door:** `operator.decisions.list` +
   `operator.decisions.resolve` (routes to owning subsystems, mints nothing).
   Six closed kinds: intervention · violation · promotion · docket_case ·
   admissibility_question · operator_question.
3. **`operator.watch`** JSON-RPC notification stream (chat.delta precedent) —
   lossy accelerant; EventBus JSONL stays canonical; resume via since_seq.
4. **`runtime.session.send_input`** — steer the running agent (the
   OpenClaw/Hermes table-stakes hook; ControlAction already supports it).
5. **Admissibility as flow:** murky launches create HELD sessions + inline
   queue questions (VoI-ranked); answers release the launch. Profile-tuned.
6. **Graduated autonomy v0 = existing `scope.escalate`** (receipted,
   time-boxed) surfaced as `: widen <scope> <ttl>`; envelope always visible.
   AG-minted widening offers PARKED to a successor campaign (ratified).
7. **Escape hatch = fork-to-lab** (existing lab gate + promotion custody),
   one keystroke out, receipted promotion diff back.
8. **`libs/ag_shell_client`** (AG repo) + `docs/specs/shell-contract/` —
   schema-first; de-triplicates framing/socket-path; phosphor backend imports
   it and goes RPC-only (split-brain retired). No TS client.
9. **Phosphor LaneSpec registry** (minimal, new-lanes-only, ratified):
   governed-session lane v0 now; ops-casework lane later on the same
   machinery.

## Forbidden (hard constraints)

- No provider/model adapters in shells — AG owns adapters below the gate.
- No multi-party approval/voting (single-operator constellation).
- No notifier/mobile/desktop surfaces (operator.watch is the future hook).
- No MCP server in maude; no chat generation in shells (GovernorHooks stays AG).
- No mid-session budget mutation (pause, or kill+fork, or scope.escalate).
- No promotion auto-approve — promotion is the custody moment; graduated
  autonomy applies pre-act only. No intervention-timeout extension RPC
  (pause-freezes-timers is the semantic).
- No session-DAG visualization beyond the lineage tree v1.
- No feed ingestion of campaign DECISIONS.md (document, not queue) or
  nightshift unsettled claims as a sixth kind (freshness already reaches the
  docket via `_freshness_to_case`).
- No TS client library. No generic dashboards (that was guvnah; retired).
- Shell-synthesized autonomy offers are forbidden always — if offers ever
  ship (parked), AG mints them.
- Program-wide constraints inherit: no bounded autopilot; generated text is
  not self-authorizing; receipts ≠ authority.

## Evidence base

Three explorations 2026-07-02 (maude internals; AG runtime/RPC boundary
analysis incl. the five-queue decision inventory and missing-hooks analysis;
phosphor lane architecture + duplication audit) + design synthesis, ratified
by operator same day (see DECISIONS). Key file anchors:
`src/governor/runtime/supervisor.py` (FSM, `_handle_tool_proposed`,
resume_session:1259), `src/governor/daemon.py` (runtime.* registry,
register_streaming/chat.delta precedent), `src/governor/docket.py`,
`src/governor/scope.py` (escalate + ttl), maude `src/maude/app.py` (the
monolith), gov-webui `src/gov_webui/adapter.py` (mode branches) +
`tests/test_parity.py` (the tripwire pattern).
