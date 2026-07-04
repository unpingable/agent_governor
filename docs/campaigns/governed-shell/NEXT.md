# Next — governed-shell slices (GS-series)

Order: GS-0 → GS-1 → daemon {GS-2→GS-3, GS-4, GS-5, GS-6 anytime, GS-7 deferred}
→ GS-8 → GS-8b → maude track (GS-9→GS-10→GS-11/12/13/14→GS-15) ∥ phosphor track
(GS-16→GS-17). Six-field shape per `docs/roadmaps/ROUTING.md`; sandwich slices
marked. Small-model eligible: parts of GS-6, GS-14.

### GS-0 — campaign capsule + four design docs  **(EXECUTED with filing, 2026-07-02)**
tier: conceptual · executor: fable+operator · prereq: []
- purpose: the design exists as governed artifacts, not session memory — loop UX, shell contract, maude boundary (R-MAUDE-3), lane machinery (feeds R-PHOS-2).
- files: this capsule; docs/design/governed-shell/{loop-ux, shell-contract-v0, maude-boundary, phosphor-lanes}.md.
- tests: cross-references resolve; exporter scans capsule (planned_slice/operator_decision records).
- refusal mode: n/a (design). · receipt shape: the filing commits.
- stop condition: n/a — done.

### GS-1 — decision envelope + watch-notification vocabulary  **(EXECUTED with filing — lives in shell-contract-v0.md, CANDIDATE)**
tier: conceptual · executor: fable · prereq: [GS-0]
- purpose: the closed vocabulary (decision kinds ×6, urgency ×4, option-key schema, refs[], notification names, resume rules) minted ONCE so GS-2/3/4/5 are mechanical.
- files: docs/design/governed-shell/shell-contract-v0.md.
- tests: every downstream slice cites the contract section it implements; vocabulary additions after GS-1 require a contract version bump.
- refusal mode: defines none; enumerates how existing closed refusal vocab surfaces in cards.
- receipt shape: the filing commit; CANDIDATE until GS-2/3 implement against it.
- stop condition: any GS-2..5 need for a NEW kind/field → return here, bump contract, do not improvise.

### GS-2 — daemon: `operator.decisions.list` + docket/admissibility read RPC
tier: mechanical · executor: codex · review checkpoint: codex-exec (schema-bearing) · prereq: [GS-1]
- purpose: one read RPC aggregating the five decision sources into the envelope; docket.list/get + admissibility.assessment reads exposed.
- files: src/governor/daemon.py (new methods), src/governor/operator_decisions.py (new aggregator, pure), tests/test_operator_decisions.py.
- tests: `python3 -m pytest tests/test_operator_decisions.py -v` exit 0; fixture per kind incl. empty-feed; envelope fields exactly per contract §2 (unknown-field test).
- refusal mode: n/a (exposure-only read; aggregator mints nothing).
- receipt shape: commit citing shell-contract §2; no receipts emitted by reads.
- stop condition: a source whose native shape can't fill a required envelope field — obstruction note + contract question; do not stretch.

### GS-3 — daemon: `operator.decisions.resolve` routing  **(FULL SANDWICH)**
tier: conceptual work-order → mechanical · codex → mandatory review · codex-exec · prereq: [GS-2]
- purpose: the ONE mutation door — routes {decision_id, option_key, args} to the owning subsystem (intervention/violation/promotion/docket/admissibility); mints no authority; receipts come from the routed subsystem.
- files: daemon.py, operator_decisions.py (routing table keyed on source.subsystem), tests/test_operator_decisions_resolve.py.
- tests: per-kind routing pin + mis-route negative (unknown decision_id / stale option_key → typed error, nothing mutated) + double-resolve idempotence pin.
- refusal mode: typed errors decision_not_found / option_not_available / already_resolved (contract §3); underlying refusals pass through verbatim.
- receipt shape: NONE of its own — the routed subsystem's receipt is the receipt (pin this).
- stop condition: any temptation to short-circuit a subsystem (e.g. resolve promotion without supervisor) — STOP; the door forwards, never replaces.

### GS-4 — daemon: `operator.watch` streaming
tier: mechanical · executor: codex · prereq: [GS-1]
- purpose: JSON-RPC notifications (runtime.event, decision.event) pushed over a held request on the existing socket; lossy accelerant, EventBus canonical.
- files: daemon.py (register_streaming pattern per chat.stream), tests/test_operator_watch.py.
- tests: notification carries seq; kill-connection → reconnect → resume via events-since_seq loses nothing (pin); channels filter honored.
- refusal mode: n/a (exposure-only).
- receipt shape: commit citing contract §4; stream emits no receipts.
- stop condition: any design where the stream becomes source of truth (client state not reconstructible from since_seq) — obstruction note.

### GS-5 — daemon: `runtime.session.send_input` + OPERATOR_INPUT event  **(SANDWICH, thin)**
tier: conceptual (event-kind mint, thin) → mechanical · codex → review · codex-exec · prereq: [GS-1]
- purpose: shells steer the RUNNING agent; input rides ControlAction(kind=send_input) to the adapter; new canonical EventKind OPERATOR_INPUT records it. Downstream tool calls remain fully intercepted — steering widens nothing.
- files: daemon.py, runtime/events.py (EventKind), runtime/supervisor.py (conduit), tests/test_send_input.py.
- tests: input reaches adapter (fake adapter pin); OPERATOR_INPUT event emitted with source_layer=OPERATOR; adapter without capability → typed refusal not crash.
- refusal mode: send_input_unsupported (adapter capability honest — gemini_cli lacks it).
- receipt shape: OPERATOR_INPUT event in the canonical ledger (event, not gate receipt).
- stop condition: input path that bypasses the event ledger — STOP (unrecorded steering is invisible authority).

### GS-6 — daemon exposure batch: `why.chain` + `runtime.adapters.list` + probe state in session.get
tier: mechanical · executor: codex (adapters.list: local-qwen eligible) · prereq: []
- purpose: pure reads the shell needs for the w key, backend picker, and probe-state badges.
- files: daemon.py; why.py (already has ChainLink), tests additions.
- tests: chain-walk on a fixture receipt chain incl. DRILL prefix pin; adapters.list capability truth (claude_code send_input=true, gemini_cli=false).
- refusal mode: n/a. · receipt shape: commit only.
- stop condition: none — pure read.

### GS-7 — daemon: `runtime.autopilot.get/set`  **(EXECUTED 2026-07-03; FULL SANDWICH → MERGE-SAFE)**
tier: conceptual → mechanical → review · prereq: [GS-1]
- purpose: envelope strip truth + profile switch (workspace default and at-create); set changes violation defaults/approval paths = refusal-placement config.
- files: daemon.py, autopilot.py, tests.
- tests: set emits a receipt; get reflects; invalid profile → typed refusal.
- refusal mode: unknown_profile.
- receipt shape: profile-change receipt citing operator.
- stop condition: any per-RUNNING-session mutation semantics — that's mid-session envelope change, forbidden; create-time and workspace-default only.

### GS-8 — extract `libs/ag_shell_client` + `docs/specs/shell-contract/`
tier: mechanical · executor: codex · prereq: [GS-0, GS-1]
- purpose: one Python client (framing, XDG socket-path de-triplicated, JSON-RPC, -32001, streaming iterators, typed envelope models w/ safe-defaults idiom); contract doc promoted from CANDIDATE draft.
- files: libs/ag_shell_client/** (pyproject, src, tests), docs/specs/shell-contract/v0.md; daemon untouched.
- tests: client-vs-live-daemon integration tests in AG CI (`python3 -m pytest libs/ag_shell_client/tests -v` exit 0).
- refusal mode: n/a. · receipt shape: commit; contract version pinned in package.
- stop condition: scope creep toward UI/retry-policy/rendering — NOT in the library.

### GS-8b — ag_shell_client live-socket client class  **(filed 2026-07-03, maude repositioning pass)**
tier: mechanical · executor: codex · prereq: [GS-8]
- purpose: the library today is codec + envelope models + injected-read-fn reader only — no connect/call/stream client class, so GS-9 has nothing to consume. Add the async Unix-socket client (connect, close, `call(method, params)`, streaming iterator, -32001 → DaemonAuthError) wrapping the existing codec. Zero consumers exist yet, so no compat burden.
- files: libs/ag_shell_client/src/ag_shell_client/ (new client module + __init__ export), libs/ag_shell_client/tests/.
- tests: `python3 -m pytest libs/ag_shell_client/tests -v` exit 0; live-daemon integration smoke per the GS-8 pattern (call `governor.hello` round-trip; streaming method yields deltas then final result).
- refusal mode: n/a (transport). · receipt shape: commit citing GS-8 + this filing.
- stop condition: UI/retry-policy/rendering creep — GS-8's own stop condition applies; the client class is framing + dispatch, nothing more.

### GS-9 — maude consumes ag_shell_client; deletes duplicated transport/client
tier: mechanical · executor: codex · prereq: [GS-8b]
- purpose: maude's client/ dir replaced by the package; **narrows R-MAUDE-2** (old-client resync is dead work).
- files: maude repo (delete src/maude/client/, add dependency, adapt imports).
- tests: maude suite bare exit 0; live daemon smoke.
- refusal mode: n/a. · receipt shape: maude-side commits citing GS-8.
- stop condition: behavior difference between old client and package — obstruction note (fix belongs in the package, not a maude shim).

### GS-10 — maude: ScreenManager + CommandRegistry skeleton
tier: mechanical · executor: codex (split a/b if diff >150 lines) · prereq: [GS-0 loop-ux, GS-9]
- purpose: the monolith seams — screens (queue/session/board/diff) + overlay stack + command objects replacing the if/elif chain; DecisionFeedController stub.
- files: maude repo src/maude/{screens/, commands/, feed.py}; app.py shrinks to bootstrap.
- tests: maude suite exit 0; each screen mountable in isolation (Textual pilot tests).
- refusal mode: n/a. · receipt shape: maude commits citing loop-ux.md.
- stop condition: any authority logic creeping into screens — render + RPC only.

### GS-11 — maude: queue home
tier: mechanical · executor: codex · prereq: [GS-2, GS-3, GS-4, GS-10]
- purpose: THE QUEUE over decisions.list/resolve + watch; card-printed option keys from envelope; queue-first focus (ratified); interrupt/accumulate split per loop-ux §4.
- files: maude screens/queue.py, feed.py.
- tests: keymap derives from options[].key (pin); bell only on blocking/expiring kinds (pin); resolve round-trip against fake feed.
- refusal mode: renders envelope typed errors verbatim.
- receipt shape: maude commits.
- stop condition: any shell-side decision synthesis (auto-answer, batching approvals across kinds) — STOP.

### GS-12 — maude: sessions board + session view with steering line
tier: mechanical · executor: codex · prereq: [GS-5, GS-10]
- purpose: N-session board (waiting-on-you sorts top) + transcript stream + receipt rail + send_input steering line with capability degradation.
- files: maude screens/{board,session}.py.
- tests: steering line disabled for adapters without send_input (pin); event render since_seq resume (pin).
- refusal mode: send_input_unsupported rendered, not hidden.
- receipt shape: maude commits.
- stop condition: transcript mutation or event re-ordering — ledger order is truth.

### GS-13 — maude: why overlay + receipt rail + refusal→route map
tier: mechanical · executor: codex · prereq: [GS-6, GS-10]
- purpose: `w` anywhere; refusal cards carry the named next safe move from a table keyed on the CLOSED refusal vocabulary.
- files: maude overlays/why.py, routes.py (the map — data, not logic).
- tests: every refusal kind in the closed vocab has a route or an explicit `no_route` entry (exhaustiveness pin); unknown kind renders raw + flagged, never guessed.
- refusal mode: n/a (rendering).
- receipt shape: maude commits citing ROUTING closed-vocab source.
- stop condition: a route that performs the move without a keystroke — routes PROPOSE, operator acts.

### GS-14 — maude: envelope strip + `: widen` one-liner
tier: mechanical · executor: local-qwen candidate · prereq: [GS-10]
- purpose: ambient envelope display + operator-initiated widening over EXISTING scope.escalate (zero daemon change); expiry badge; scar-shrink renders.
- files: maude widgets/envelope.py, commands/widen.py.
- tests: widen calls scope.escalate with ttl (pin); envelope re-renders on receipt; expired grant drops from strip.
- refusal mode: scope refusals pass through verbatim.
- receipt shape: the scope.escalate receipt (AG-side, existing).
- stop condition: any widening without ttl, or any auto-widen — STOP.

### GS-15 — maude: remove PLAN/BUILD, v3.0 release + contract pin
tier: mechanical · executor: codex · prereq: [GS-11..GS-14]
- purpose: cut the chat/spec-lock paradigm (ratified); prune intents; pin ag_shell_client + contract version; release notes state the relocation (lock-before-act → admissibility; plan-first → profile).
- files: maude repo-wide prune; README/ROADMAP rewrite.
- tests: full suite exit 0; no dangling PLAN/BUILD intents (grep pin).
- refusal mode: n/a. · receipt shape: maude v3.0.0 tag.
- stop condition: discovery of a PLAN/BUILD behavior with no relocation home — obstruction note, don't silently drop capability.

### GS-16 — phosphor: LaneSpec registry + per-lane parity test generation
tier: mechanical · executor: codex (LaneSpec design done in GS-0) · prereq: [R-PHOS-1 compat audit]
- purpose: the minimal registry (frozen dataclass + dispatcher) + generated per-lane tripwires (mutating actions only via daemon_methods allowlist; no direct governor imports on mutating paths; refusals rendered verbatim). New-lanes-only (ratified) — existing modes untouched.
- files: gov-webui src/gov_webui/lanes.py (new), tests/test_lane_contract.py (generator).
- tests: gov-webui suite exit 0 + generated tests green for a fixture lane.
- refusal mode: lane contract rule 2 enforced by test.
- receipt shape: gov-webui commits citing phosphor-lanes.md.
- stop condition: framework creep (middleware, plugins, hooks) — a dataclass and a dispatcher, nothing more.

### GS-17 — phosphor: governed-session lane v0
tier: mechanical · executor: codex · prereq: [GS-8, GS-16, GS-2..GS-5]
- purpose: web mirror of the desk — queue + session pages + board; backend proxies ag_shell_client; SSE relay of operator.watch; daemon_methods = {operator.decisions.*, operator.watch, runtime.session.*, why.chain}.
- files: gov-webui lane module + Svelte pages.
- tests: generated lane-contract tests green; SSE relay resume pin.
- refusal mode: renders substrate refusals verbatim, adds none.
- receipt shape: gov-webui commits.
- stop condition: any direct governor import on a mutating path — the tripwire fires; this lane is RPC-only by construction.
